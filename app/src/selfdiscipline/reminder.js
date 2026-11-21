// 提醒统一入口：负责“原生调度 + reminders 表”双写、幂等与对账。
// 页面不直接调用 UTS 插件。

import * as repo from './repository.js'
import { addDays, dateKey, parseDays, parseHHmm, weekdayIso } from './dates.js'
import { notificationText } from './persona.js'

// #ifdef APP-PLUS
import * as backend from './reminder-native.js'
// #endif
// #ifndef APP-PLUS
import * as backend from './reminder-web.js'
// #endif

const CHECKIN_DAYS = 7

export function getStatus() {
  return backend.getStatus()
}

export function canScheduleExactAlarms() {
  return backend.canScheduleExactAlarms()
}

export function requestNotificationPermission() {
  return backend.requestNotificationPermission()
}

export function openNotificationSettings() {
  return backend.openNotificationSettings()
}

export function openExactAlarmSettings() {
  return backend.openExactAlarmSettings()
}

export function cancelAll() {
  return backend.cancelAll()
}

export function postNow(title, body, kind = 'focus', refId = '') {
  return backend.postNow(title, body, kind, refId)
}

export async function getReadiness() {
  const status = backend.getStatus() || {}
  let pending = 0
  try {
    const rows = await repo.listReminders('pending')
    pending = rows.length
  } catch (e) {}
  return {
    ...status,
    pending
  }
}

/**
 * 写入 reminders 表并调度原生提醒。同一 id 先取消再调度，保证只有一条。
 */
async function scheduleInternal({ id, triggerAt, title, body, kind, refId }) {
  const at = Number(triggerAt) || 0
  try {
    backend.cancel(id)
  } catch (e) {}

  if (!at || at <= Date.now()) {
    await repo.removeReminder(id)
    return { ok: false, exact: false, reason: 'past' }
  }

  await repo.addReminder({
    id,
    kind,
    ref_id: refId || '',
    trigger_at: at,
    title,
    body,
    status: 'pending'
  })

  let result = { ok: false, exact: false, reason: 'error' }
  try {
    result = backend.schedule(id, at, title, body, kind, refId || '') || result
  } catch (e) {
    result = { ok: false, exact: false, reason: 'exception' }
  }
  return result
}

export async function scheduleFocus(session) {
  if (!session || !session.id) return { ok: false }
  const id = `focus:${session.id}`
  const triggerAt = Number(session.started_at) + Number(session.planned_min) * 60000
  const text = notificationText('focus')
  return scheduleInternal({
    id,
    triggerAt,
    title: text.title,
    body: text.body,
    kind: 'focus',
    refId: session.id
  })
}

export async function scheduleReport(report) {
  if (!report || !report.id) return { ok: false }
  const id = `report:${report.id}`
  const text = notificationText('report')
  return scheduleInternal({
    id,
    triggerAt: Number(report.reminder_at),
    title: text.title,
    body: text.body,
    kind: 'report',
    refId: report.id
  })
}

export async function cancelReminder(id) {
  if (!id) return
  try {
    backend.cancel(id)
  } catch (e) {}
  await repo.removeReminder(id)
}

export async function cancelCheckinForItem(itemId) {
  const rows = await repo.listReminders('pending')
  for (const row of rows) {
    if (row.kind === 'checkin' && row.id.indexOf(`checkin:${itemId}:`) === 0) {
      await cancelReminder(row.id)
    }
  }
}

function itemDays(item) {
  const list = Array.isArray(item.days) ? item.days : parseDays(item.days)
  return list.map(Number).filter((n) => n >= 1 && n <= 7)
}

/**
 * 为启用的事项排未来 7 天的提醒。
 * 已存在同 id 的先 cancel 再 schedule；不再需要的旧 id 一并取消。
 */
export async function scheduleCheckinReminders(items) {
  const list = Array.isArray(items) ? items : []
  const now = Date.now()
  const desired = new Map()

  for (const item of list) {
    if (!item || item.enabled === false || Number(item.enabled) === 0) continue
    if (!item.remind_time) continue

    // 一次性事项：只在它自己的日期提醒一次。
    if (item.kind === 'once') {
      if (!item.date) continue
      const triggerAt = parseHHmm(item.date, item.remind_time)
      if (!triggerAt || triggerAt <= now + 20000) continue
      const id = `checkin:${item.id}:${item.date}`
      desired.set(id, {
        id,
        triggerAt,
        kind: 'checkin',
        refId: item.id,
        title: notificationText('checkin').title,
        body: notificationText('checkin').body
      })
      continue
    }

    // 每日重复事项：未来 7 天滚动排期。
    for (let offset = 0; offset < CHECKIN_DAYS; offset += 1) {
      const dayMs = addDays(now, offset)
      const key = dateKey(dayMs)
      const weekday = weekdayIso(dayMs)
      if (!itemDays(item).includes(weekday)) continue
      const triggerAt = parseHHmm(key, item.remind_time)
      if (!triggerAt || triggerAt <= now + 20000) continue
      const id = `checkin:${item.id}:${key}`
      desired.set(id, {
        id,
        triggerAt,
        kind: 'checkin',
        refId: item.id,
        title: notificationText('checkin').title,
        body: notificationText('checkin').body
      })
    }
  }

  const existing = await repo.listReminders('pending')
  const existingIds = new Set(
    existing.filter((row) => row.kind === 'checkin').map((row) => row.id)
  )

  for (const id of existingIds) {
    if (!desired.has(id)) await cancelReminder(id)
  }

  for (const entry of desired.values()) {
    await scheduleInternal(entry)
  }
}

/**
 * 对账：启动或回到前台时调用。
 * - 表里已过期的标 fired 并取消原生
 * - 表里未来但原生缺失的补排
 * - 原生有、表里没有的清理掉
 */
export async function reconcile() {
  const rows = await repo.listReminders('pending')
  const now = Date.now()
  const tableIds = new Set()

  for (const row of rows) {
    tableIds.add(row.id)
    if (Number(row.trigger_at) <= now) {
      try {
        backend.cancel(row.id)
      } catch (e) {}
      await repo.updateReminder(row.id, { status: 'fired' })
      continue
    }
    try {
      backend.schedule(row.id, Number(row.trigger_at), row.title, row.body, row.kind, row.ref_id || '')
    } catch (e) {}
  }

  try {
    const scheduled = backend.getScheduled()
    const list = Array.isArray(scheduled) ? scheduled : []
    for (const entry of list) {
      const id = entry && entry.id
      if (!id) continue
      if (!tableIds.has(id) && /^(focus|report|checkin):/.test(id)) {
        backend.cancel(id)
      }
    }
  } catch (e) {}
}

/** 已触发但仍处于 pending 的提醒标为 fired（用于页面展示与清理） */
export async function markExpired() {
  const rows = await repo.listReminders('pending')
  const now = Date.now()
  for (const row of rows) {
    if (Number(row.trigger_at) <= now) {
      await repo.updateReminder(row.id, { status: 'fired' })
    }
  }
}

/** 生成打卡提醒 id 列表（供测试/调试） */
export function checkinReminderIds(items) {
  const out = []
  const now = Date.now()
  for (let offset = 0; offset < CHECKIN_DAYS; offset += 1) {
    const dayMs = addDays(now, offset)
    const key = dateKey(dayMs)
    const weekday = weekdayIso(dayMs)
    for (const item of items || []) {
      if (!item || !item.enabled || !item.remind_time) continue
      if (!itemDays(item).includes(weekday)) continue
      out.push(`checkin:${item.id}:${key}`)
    }
  }
  return out
}
