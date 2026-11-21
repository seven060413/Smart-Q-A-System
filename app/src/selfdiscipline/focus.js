// 专注计时：状态机、点数结算、提醒与守护联动。
// 运行中会话在内存里保留一份，App.vue onHide 时可以同步读取。

import * as repo from './repository.js'
import * as points from './points.js'
import * as reminder from './reminder.js'
import * as guard from './guard.js'

export const MIN_MINUTES = 5
export const MAX_MINUTES = 180
export const FOCUS_PRESETS = [15, 25, 45, 60, 90]

let memorySession = null

export function currentFocusSession() {
  return memorySession
}

export function clampMinutes(value) {
  const n = Math.round(Number(value) || 0)
  if (!Number.isFinite(n)) return MIN_MINUTES
  return Math.min(MAX_MINUTES, Math.max(MIN_MINUTES, n))
}

export function setKeepScreenOn(on) {
  keepScreenOn(on)
}

function keepScreenOn(on) {
  // #ifdef APP-PLUS
  try {
    uni.setKeepScreenOn({ keepScreenOn: !!on, fail: () => {} })
  } catch (e) {}
  // #endif
}

export async function getPrefs() {
  const strictness = await repo.getSetting('strictness', 'A')
  const defaultFocusMin = clampMinutes(await repo.getSetting('defaultFocusMin', 25))
  const defaultExtendMin = clampMinutes(await repo.getSetting('defaultExtendMin', 10))
  const guardEnabled = (await repo.getSetting('guardEnabled', true)) !== false
  return { strictness: strictness === 'B' ? 'B' : 'A', defaultFocusMin, defaultExtendMin, guardEnabled }
}

export async function setPref(key, value) {
  return repo.setSetting(key, value)
}

/** 读取进行中的会话；页面启动/恢复时调用 */
export async function loadRunningFocus() {
  const row = await repo.getRunningFocus()
  memorySession = row || null
  return memorySession
}

export function focusRuntime(session, now = Date.now()) {
  if (!session) return { totalMs: 0, remainingMs: 0, ratio: 0, percent: 0, due: false }
  const totalMs = Number(session.planned_min) * 60000
  const endAt = Number(session.started_at) + totalMs
  const remainingMs = Math.max(0, endAt - now)
  const ratio = totalMs > 0 ? remainingMs / totalMs : 0
  return {
    totalMs,
    endAt,
    remainingMs,
    ratio,
    percent: Math.round((1 - ratio) * 100),
    due: remainingMs <= 0,
  }
}

/**
 * 开始一场专注。
 * @returns {Promise<object>} 已写入数据库的会话
 */
export async function startFocus({ task, minutes }) {
  const cleanTask = String(task || '').trim()
  if (!cleanTask) throw new Error('请先填写任务')
  await repo.init()

  const running = await repo.getRunningFocus()
  if (running) {
    memorySession = running
    throw new Error('还有一场专注没结束')
  }

  const planned = clampMinutes(minutes)
  const now = Date.now()
  const session = {
    id: repo.newId('focus'),
    task: cleanTask,
    planned_min: planned,
    actual_min: 0,
    started_at: now,
    ended_at: null,
    status: 'running',
    points: 0,
  }

  await repo.insertFocusSession(session)
  memorySession = session
  keepScreenOn(true)

  try {
    await reminder.scheduleFocus(session)
  } catch (e) {}

  try {
    const prefs = await getPrefs()
    if (prefs.guardEnabled) await guard.startGuard(session)
  } catch (e) {
    // 守护启动失败不阻断专注。
  }

  return session
}

export async function extendFocus(addMinutes) {
  const session = await loadRunningFocus()
  if (!session) throw new Error('没有进行中的专注')
  const add = clampMinutes(addMinutes)
  const planned = clampMinutes(Number(session.planned_min) + add)
  await repo.updateFocusSession(session.id, { planned_min: planned })
  const next = { ...session, planned_min: planned }
  memorySession = next
  try {
    await reminder.scheduleFocus(next)
  } catch (e) {}
  try {
    await guard.updateGuard(next, 'focus')
  } catch (e) {}
  return next
}

/**
 * 结算专注。
 * @param {{early?: boolean}} options early=true 表示未到点提前完成
 */
export async function completeFocus({ early = false } = {}) {
  const session = await loadRunningFocus()
  if (!session) throw new Error('没有进行中的专注')

  const now = Date.now()
  const runtime = focusRuntime(session, now)
  const isEarly = runtime.remainingMs > 0
  const elapsedMin = Math.max(0, Math.floor((now - Number(session.started_at)) / 60000))
  const actual = Math.min(Number(session.planned_min), elapsedMin)
  const earned = isEarly ? actual : Number(session.planned_min)

  const patch = {
    status: 'completed',
    ended_at: now,
    actual_min: actual,
    points: earned,
  }
  await repo.updateFocusSession(session.id, patch)
  const settled = { ...session, ...patch }

  if (isEarly) await points.awardFocusEarly(settled)
  else await points.awardFocusComplete(settled)

  await afterSettle(session.id)
  return { session: settled, early: isEarly, earned }
}

export async function abandonFocus() {
  const session = await loadRunningFocus()
  if (!session) throw new Error('没有进行中的专注')
  const now = Date.now()
  const elapsedMin = Math.max(0, Math.floor((now - Number(session.started_at)) / 60000))
  const actual = Math.min(Number(session.planned_min), elapsedMin)
  const patch = {
    status: 'abandoned',
    ended_at: now,
    actual_min: actual,
    points: 0,
  }
  await repo.updateFocusSession(session.id, patch)
  await afterSettle(session.id)
  return { session: { ...session, ...patch }, early: false, earned: 0 }
}

async function afterSettle(sessionId) {
  memorySession = null
  keepScreenOn(false)
  try {
    await reminder.cancelReminder(`focus:${sessionId}`)
  } catch (e) {}
  try {
    guard.stopGuard()
  } catch (e) {}
}

/** 已过点但尚未结算的会话，页面显示“时间到了，待结算” */
export function isDue(session, now = Date.now()) {
  if (!session) return false
  return focusRuntime(session, now).due
}
