// 自律模块的唯一数据入口。页面和业务模块只调用这里，不直接碰存储实现。
// 所有方法返回 Promise；写操作串行执行，避免并发读写互相覆盖。

import { createH5Storage } from './storage-h5.js'
// #ifdef APP-PLUS
import { createAppStorage } from './storage-app.js'
// #endif

const storage = (() => {
  // #ifdef APP-PLUS
  return createAppStorage()
  // #endif
  // #ifndef APP-PLUS
  return createH5Storage()
  // #endif
})()

let initPromise = null
let writeQueue = Promise.resolve()

function enqueue(task) {
  const next = writeQueue.then(task, task)
  // 吞掉失败，避免队列永久中断；调用方仍然能从返回的 Promise 拿到错误。
  writeQueue = next.catch(() => {})
  return next
}

function sortBy(rows, key, desc = false) {
  return [...rows].sort((a, b) => {
    const av = Number(a[key]) || 0
    const bv = Number(b[key]) || 0
    return desc ? bv - av : av - bv
  })
}

function inRange(ms, fromMs, toMs) {
  const value = Number(ms) || 0
  return value >= fromMs && value <= toMs
}

export function newId(prefix = '') {
  let id = ''
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      id = crypto.randomUUID()
    }
  } catch (e) {}
  if (!id) id = `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
  return prefix ? `${prefix}_${id}` : id
}

export function init() {
  if (!initPromise) initPromise = storage.init()
  return initPromise
}

export function storageMode() {
  return storage.mode || 'json'
}

// ---------- 设置 ----------

export async function getSetting(key, fallback = null) {
  await init()
  const rows = await storage.readTable('settings')
  const row = rows.find((item) => item.key === key)
  if (!row) return fallback
  try {
    const parsed = JSON.parse(row.value)
    return parsed === undefined ? fallback : parsed
  } catch (e) {
    return row.value
  }
}

export async function setSetting(key, value) {
  await init()
  return enqueue(() =>
    storage.insert('settings', { key, value: JSON.stringify(value === undefined ? null : value) })
  )
}

// ---------- 专注 ----------

export async function insertFocusSession(row) {
  await init()
  return enqueue(() => storage.insert('focus_sessions', row))
}

export async function updateFocusSession(id, patch) {
  await init()
  return enqueue(() => storage.update('focus_sessions', id, patch))
}

export async function getFocusSession(id) {
  await init()
  const rows = await storage.readTable('focus_sessions')
  return rows.find((item) => item.id === id) || null
}

export async function getRunningFocus() {
  await init()
  const rows = await storage.readTable('focus_sessions')
  const running = rows.filter((item) => item.status === 'running')
  if (!running.length) return null
  return sortBy(running, 'started_at', true)[0]
}

export async function listFocusSessions(fromMs, toMs) {
  await init()
  const rows = await storage.readTable('focus_sessions')
  return sortBy(
    rows.filter((item) => inRange(item.started_at, fromMs, toMs)),
    'started_at',
    true
  )
}

// ---------- 报备 ----------

export async function insertReport(row) {
  await init()
  return enqueue(() => storage.insert('reports', row))
}

export async function updateReport(id, patch) {
  await init()
  return enqueue(() => storage.update('reports', id, patch))
}

export async function getReport(id) {
  await init()
  const rows = await storage.readTable('reports')
  return rows.find((item) => item.id === id) || null
}

export async function getActiveReport() {
  await init()
  const rows = await storage.readTable('reports')
  const active = rows.filter((item) => item.status === 'active')
  if (!active.length) return null
  return sortBy(active, 'started_at', true)[0]
}

export async function listReports(fromMs, toMs) {
  await init()
  const rows = await storage.readTable('reports')
  return sortBy(
    rows.filter((item) => inRange(item.started_at, fromMs, toMs)),
    'started_at',
    true
  )
}

// ---------- 每日打卡 ----------

export async function upsertCheckinItem(item) {
  await init()
  return enqueue(() => storage.insert('checkin_items', item))
}

export async function listCheckinItems() {
  await init()
  const rows = await storage.readTable('checkin_items')
  return sortBy(rows, 'created_at')
}

export async function getCheckinItem(id) {
  await init()
  const rows = await storage.readTable('checkin_items')
  return rows.find((item) => item.id === id) || null
}

export async function deleteCheckinItem(id) {
  await init()
  return enqueue(() => storage.remove('checkin_items', id))
}

export async function getCheckinRecord(itemId, date) {
  await init()
  const rows = await storage.readTable('checkin_records')
  return rows.find((item) => item.item_id === itemId && item.date === date) || null
}

export async function insertCheckinRecord(row) {
  await init()
  return enqueue(() => storage.insert('checkin_records', row))
}

export async function deleteCheckinRecord(itemId, date) {
  await init()
  const rows = await storage.readTable('checkin_records')
  const record = rows.find((item) => item.item_id === itemId && item.date === date)
  if (!record) return
  return enqueue(() => storage.remove('checkin_records', record.id))
}

export async function listCheckinRecords(fromDate, toDate) {
  await init()
  const rows = await storage.readTable('checkin_records')
  return rows
    .filter((item) => String(item.date) >= String(fromDate) && String(item.date) <= String(toDate))
    .sort((a, b) => Number(b.done_at) - Number(a.done_at))
}

// ---------- 点数账本 ----------

export async function addLedger(entry) {
  await init()
  const row = {
    id: entry.id || newId('lg'),
    delta: Number(entry.delta) || 0,
    reason: entry.reason || 'manual',
    ref_type: entry.ref_type || '',
    ref_id: entry.ref_id || '',
    created_at: entry.created_at || Date.now(),
  }
  return enqueue(() => storage.insert('points_ledger', row))
}

export async function getLedgerById(id) {
  await init()
  const rows = await storage.readTable('points_ledger')
  return rows.find((item) => item.id === id) || null
}

export async function listLedger(fromMs, toMs) {
  await init()
  const rows = await storage.readTable('points_ledger')
  return sortBy(
    rows.filter((item) => inRange(item.created_at, fromMs, toMs)),
    'created_at',
    true
  )
}

export async function sumPoints() {
  await init()
  const rows = await storage.readTable('points_ledger')
  return rows.reduce((sum, item) => sum + (Number(item.delta) || 0), 0)
}

// ---------- 提醒持久化 ----------

export async function addReminder(row) {
  await init()
  return enqueue(() => storage.insert('reminders', row))
}

export async function updateReminder(id, patch) {
  await init()
  return enqueue(() => storage.update('reminders', id, patch))
}

export async function removeReminder(id) {
  await init()
  return enqueue(() => storage.remove('reminders', id))
}

export async function listReminders(status) {
  await init()
  const rows = await storage.readTable('reminders')
  const filtered = status ? rows.filter((item) => item.status === status) : rows
  return sortBy(filtered, 'trigger_at')
}

// ---------- 导出 / 清空 ----------

export async function exportAll() {
  await init()
  return storage.exportAll()
}

export async function clearAll() {
  await init()
  return enqueue(() => storage.clearAll())
}

/** 导出给用户看的 JSON 字符串 */
export async function exportJson() {
  const data = await exportAll()
  return JSON.stringify(
    {
      app: 'ikgr-selfdiscipline',
      version: 1,
      exportedAt: new Date().toISOString(),
      data,
    },
    null,
    2
  )
}
