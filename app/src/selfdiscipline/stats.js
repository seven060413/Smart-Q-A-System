// 统计聚合：仓库层拉原始行，这里在 JS 里聚合，兼容 H5 与 App。

import * as repo from './repository.js'
import * as checkin from './checkin.js'
import { isOnTime } from './report.js'
import {
  addDays,
  dateKey,
  dayKeysBetween,
  formatDateTime,
  parseHHmm,
  startOfDay,
  endOfDay,
} from './dates.js'

function sum(list, key) {
  return list.reduce((total, item) => total + (Number(item[key]) || 0), 0)
}

function percent(part, total) {
  if (!total) return 0
  return Math.round((part / total) * 100)
}

function sharesFrom(map, valueKey) {
  const list = [...map.values()].filter((item) => item[valueKey] > 0)
  const total = list.reduce((s, item) => s + item[valueKey], 0)
  return list
    .sort((a, b) => b[valueKey] - a[valueKey])
    .map((item) => ({
      label: item.label,
      value: item[valueKey],
      percent: percent(item[valueKey], total),
    }))
}

function addToMap(map, key, field, value, extras = {}) {
  const label = key || '未命名'
  if (!map.has(label)) map.set(label, { label, [field]: 0, ...extras })
  map.get(label)[field] += value
}

/** 今日概览：专注分钟、打卡完成、点数净变化 */
export async function todayStats(now = Date.now()) {
  const from = startOfDay(now)
  const to = endOfDay(now)
  const [sessions, ledger, items] = await Promise.all([
    repo.listFocusSessions(from, to),
    repo.listLedger(from, to),
    checkin.todayItems(now),
  ])
  const completion = checkin.completionOf(items)
  return {
    focusMinutes: sum(sessions, 'actual_min'),
    focusSessions: sessions.length,
    netPoints: sum(ledger, 'delta'),
    points: await repo.sumPoints(),
    checkinDone: completion.done,
    checkinTotal: completion.total,
    checkinAll: completion.all,
  }
}

/**
 * 统计区间汇总。
 * @param {number} days 7 / 30 / 90
 */
export async function summarize(days = 7, now = Date.now()) {
  const span = Math.max(1, Math.round(Number(days) || 7))
  const fromMs = startOfDay(addDays(now, -(span - 1)))
  const toMs = endOfDay(now)

  const [sessions, ledger, reports, items, records] = await Promise.all([
    repo.listFocusSessions(fromMs, toMs),
    repo.listLedger(fromMs, toMs),
    repo.listReports(fromMs, toMs),
    checkin.listItems(),
    repo.listCheckinRecords(dateKey(fromMs), dateKey(toMs)),
  ])

  const settled = sessions.filter((row) => row.status !== 'running')
  const completed = settled.filter((row) => row.status === 'completed')
  const focusMinutes = sum(settled, 'actual_min')
  const netPoints = sum(ledger, 'delta')

  // 打卡分母：区间内每一天（不含未来）的应打卡次数
  const keys = dayKeysBetween(fromMs, toMs).filter((key) => key <= dateKey(now))
  let expected = 0
  for (const key of keys) {
    expected += checkin.expectedCount(items, parseHHmm(key, '00:00'))
  }
  // 历史完成率的分子也只算每日重复事项，避免一次性事项拉高比例。
  const dailyItemIds = new Set(
    items.filter((item) => item.kind !== 'once').map((item) => item.id)
  )
  const doneRecords = records.filter((row) => dailyItemIds.has(row.item_id)).length

  const endedReports = reports.filter((row) => row.status === 'ended')
  const onTimeReports = endedReports.filter((row) => isOnTime(row))

  // 每日序列
  const sessionByDay = new Map()
  for (const row of settled) {
    const key = dateKey(Number(row.started_at))
    sessionByDay.set(key, (sessionByDay.get(key) || 0) + (Number(row.actual_min) || 0))
  }
  const ledgerByDay = new Map()
  for (const row of ledger) {
    const key = dateKey(Number(row.created_at))
    ledgerByDay.set(key, (ledgerByDay.get(key) || 0) + (Number(row.delta) || 0))
  }
  const daily = keys.map((key) => {
    const d = new Date(parseHHmm(key, '00:00'))
    return {
      date: key,
      label: `${d.getMonth() + 1}/${d.getDate()}`,
      focusMinutes: sessionByDay.get(key) || 0,
      netPoints: ledgerByDay.get(key) || 0,
    }
  })

  // 占比
  const taskMap = new Map()
  for (const row of settled) {
    addToMap(taskMap, row.task, 'minutes', Number(row.actual_min) || 0)
  }
  const targetMap = new Map()
  for (const row of reports) {
    addToMap(targetMap, row.target_app, 'minutes', Number(row.minutes) || 0)
  }

  // 最近记录
  const itemTitle = new Map(items.map((item) => [item.id, item.title]))
  const recent = []
  for (const row of settled.slice(0, 5)) {
    recent.push({
      key: `focus:${row.id}`,
      type: 'focus',
      title: row.task || '专注',
      subtitle: `${row.actual_min || 0} 分钟 · ${formatDateTime(Number(row.started_at))}`,
      at: Number(row.started_at),
      points: Number(row.points) || 0,
    })
  }
  for (const row of reports.slice(0, 5)) {
    recent.push({
      key: `report:${row.id}`,
      type: 'report',
      title: row.target_app || '报备',
      subtitle: `${row.minutes} 分钟 · ${formatDateTime(Number(row.started_at))}`,
      at: Number(row.started_at),
      points: Number(row.points) || 0,
    })
  }
  for (const row of records.slice(0, 5)) {
    recent.push({
      key: `checkin:${row.id}`,
      type: 'checkin',
      title: itemTitle.get(row.item_id) || '每日打卡',
      subtitle: `打卡 · ${formatDateTime(Number(row.done_at))}`,
      at: Number(row.done_at),
      points: Number(row.points) || 0,
    })
  }
  recent.sort((a, b) => b.at - a.at)

  const hasData = settled.length > 0 || reports.length > 0 || records.length > 0

  return {
    days: span,
    fromMs,
    toMs,
    fromLabel: dateKey(fromMs),
    toLabel: dateKey(toMs),
    focusMinutes,
    focusSessions: settled.length,
    focusDoneRate: percent(completed.length, settled.length),
    netPoints,
    checkinDone: doneRecords,
    checkinExpected: expected,
    checkinRate: percent(doneRecords, expected),
    reportEnded: endedReports.length,
    reportOnTime: onTimeReports.length,
    reportOnTimeRate: percent(onTimeReports.length, endedReports.length),
    daily,
    taskShares: sharesFrom(taskMap, 'minutes'),
    targetShares: sharesFrom(targetMap, 'minutes'),
    recent: recent.slice(0, 8),
    hasData,
  }
}
