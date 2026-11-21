// 每日打卡：事项、完成/撤销、连续完成与提醒重排。

import * as repo from './repository.js'
import * as points from './points.js'
import * as reminder from './reminder.js'
import { dateKey, daysToString, parseDays, weekdayIso } from './dates.js'

export const ALL_DAYS = [1, 2, 3, 4, 5, 6, 7]

export function normalizeItem(row) {
  if (!row) return null
  const days = Array.isArray(row.days) ? row.days.map(Number) : parseDays(row.days)
  const kind = row.kind === 'once' ? 'once' : 'daily'
  return {
    ...row,
    kind,
    date: kind === 'once' ? String(row.date || '') : '',
    days,
    daysText: daysToString(days),
    enabled: row.enabled === true || Number(row.enabled) === 1,
  }
}

export async function listItems() {
  const rows = await repo.listCheckinItems()
  return rows.map(normalizeItem)
}

function enabledForDay(item, ms) {
  if (!item || !item.enabled) return false
  if (item.kind === 'once') return item.date === dateKey(ms)
  return item.days.includes(weekdayIso(ms))
}

/** 今日应打卡事项，附带完成状态 */
export async function todayItems(now = Date.now()) {
  const items = await listItems()
  const key = dateKey(now)
  const records = await repo.listCheckinRecords(key, key)
  const byItem = new Map(records.map((r) => [r.item_id, r]))
  return items
    .filter((item) => enabledForDay(item, now))
    .map((item) => {
      const record = byItem.get(item.id) || null
      return {
        ...item,
        done: !!record,
        doneAt: record ? Number(record.done_at) || 0 : 0,
      }
    })
}

export function completionOf(items) {
  const total = items.length
  const done = items.filter((item) => item.done).length
  return { done, total, ratio: total ? done / total : 0, all: total > 0 && done === total }
}

async function persistItem(input) {
  const now = Date.now()
  const existing = input.id ? await repo.getCheckinItem(input.id) : null
  const kind = input.kind === 'once' ? 'once' : 'daily'
  const days =
    kind === 'once'
      ? []
      : Array.isArray(input.days) && input.days.length
        ? input.days
        : ALL_DAYS
  const item = normalizeItem({
    id: existing ? existing.id : repo.newId('item'),
    title: String(input.title || '').trim(),
    note: String(input.note || '').trim(),
    remind_time: String(input.remind_time || '').trim(),
    days: daysToString(days),
    enabled: input.enabled === false ? 0 : 1,
    kind,
    date: kind === 'once' ? String(input.date || dateKey(now)) : '',
    created_at: existing ? existing.created_at : now,
  })
  if (!item.title) throw new Error('请填写事项标题')
  await repo.upsertCheckinItem({
    id: item.id,
    title: item.title,
    note: item.note,
    remind_time: item.remind_time,
    days: item.daysText,
    enabled: item.enabled ? 1 : 0,
    kind: item.kind,
    date: item.date,
    created_at: item.created_at,
  })
  return item
}

export async function saveItem(input) {
  const item = await persistItem(input)
  await rescheduleReminders()
  return item
}

/** AI 整理后批量创建；只重排一次提醒。 */
export async function createItems(inputs) {
  const created = []
  for (const input of inputs || []) {
    created.push(await persistItem(input))
  }
  await rescheduleReminders()
  return created
}

export async function removeItem(id) {
  const item = await repo.getCheckinItem(id)
  if (!item) return
  await reminder.cancelCheckinForItem(id)
  await repo.deleteCheckinItem(id)
  await rescheduleReminders()
}

export async function setEnabled(id, enabled) {
  const item = await repo.getCheckinItem(id)
  if (!item) return
  await repo.upsertCheckinItem({ ...item, enabled: enabled ? 1 : 0 })
  await rescheduleReminders()
}

/** 今日全部完成后加一次全清奖励 */
async function awardAllIfDone(now = Date.now()) {
  const items = await todayItems(now)
  const completion = completionOf(items)
  if (completion.all) await points.awardCheckinAll(dateKey(now))
}

async function undoAllIfNeeded(now = Date.now()) {
  const items = await todayItems(now)
  const completion = completionOf(items)
  if (!completion.all) await points.undoCheckinAll(dateKey(now))
}

/**
 * 勾选/取消今日事项。返回最新事项状态。
 */
export async function toggleToday(item, now = Date.now()) {
  if (!item || !item.id) return null
  const key = dateKey(now)
  const record = await repo.getCheckinRecord(item.id, key)

  if (record) {
    await repo.deleteCheckinRecord(item.id, key)
    await points.undoCheckin(item.id, key)
    await undoAllIfNeeded(now)
  } else {
    await repo.insertCheckinRecord({
      id: repo.newId('rec'),
      item_id: item.id,
      date: key,
      done_at: Date.now(),
      points: points.RULES.checkin,
    })
    await points.awardCheckin(item.id, key)
    // 已完成的事项不再提醒。
    try {
      await reminder.cancelReminder(`checkin:${item.id}:${key}`)
    } catch (e) {}
    await awardAllIfDone(now)
  }

  const items = await todayItems(now)
  return items.find((row) => row.id === item.id) || { ...item, done: !record }
}

/** 为所有启用事项排未来 7 天提醒 */
export async function rescheduleReminders() {
  try {
    const items = await listItems()
    await reminder.scheduleCheckinReminders(items)
  } catch (e) {
    console.error('[checkin] 重排提醒失败', e)
  }
}

/** 某一天应打卡次数（用于统计分母） */
export function expectedCount(items, ms) {
  // 历史打卡完成率只统计每日重复事项；一次性事项不进入长期分母。
  let count = 0
  for (const item of items) {
    if (item.kind === 'once') continue
    if (item.enabled && item.days.includes(weekdayIso(ms))) count += 1
  }
  return count
}
