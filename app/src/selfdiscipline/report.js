// 报备：自我承诺提醒，不读取、不拦截目标应用。

import * as repo from './repository.js'
import * as points from './points.js'
import * as reminder from './reminder.js'

export const TARGET_PRESETS = ['微信', '抖音', 'B站', '游戏', '浏览器']
export const MIN_MINUTES = 5
export const MAX_MINUTES = 180
export const DURATION_PRESETS = [5, 15, 25, 30, 60]
export const OVERDUE_GRACE_MS = 5 * 60000

export function clampReportMinutes(value) {
  const n = Math.round(Number(value) || 0)
  if (!Number.isFinite(n)) return MIN_MINUTES
  return Math.min(MAX_MINUTES, Math.max(MIN_MINUTES, n))
}

export async function getActive(now = Date.now()) {
  const report = await repo.getActiveReport()
  if (!report) return null
  return { ...report, runtime: reportRuntime(report, now) }
}

export function reportRuntime(report, now = Date.now()) {
  if (!report) return { remainingMs: 0, usedMs: 0, totalMs: 0, ratio: 0, due: false, overdue: false }
  const totalMs = Number(report.minutes) * 60000
  const reminderAt = Number(report.reminder_at)
  const usedMs = now - Number(report.started_at)
  const remainingMs = Math.max(0, reminderAt - now)
  return {
    totalMs,
    reminderAt,
    usedMs,
    remainingMs,
    ratio: totalMs > 0 ? Math.min(1, Math.max(0, usedMs / totalMs)) : 0,
    due: report.status === 'active' && now >= reminderAt,
    overdue: report.status === 'active' && now > reminderAt + OVERDUE_GRACE_MS,
  }
}

export async function startReport({ targetApp, purpose, minutes }) {
  const app = String(targetApp || '').trim()
  const why = String(purpose || '').trim()
  if (!app) throw new Error('请选择或填写目标应用')
  if (!why) throw new Error('请填写报备目的')
  await repo.init()

  const active = await repo.getActiveReport()
  if (active) throw new Error('还有一条报备没有结束')

  const value = clampReportMinutes(minutes)
  const now = Date.now()
  const report = {
    id: repo.newId('report'),
    target_app: app,
    purpose: why,
    minutes: value,
    started_at: now,
    reminder_at: now + value * 60000,
    ended_at: null,
    status: 'active',
    points: 0,
  }
  await repo.insertReport(report)
  try {
    await reminder.scheduleReport(report)
  } catch (e) {}
  return report
}

export async function extendReport(addMinutes = 5) {
  const report = await repo.getActiveReport()
  if (!report) throw new Error('没有进行中的报备')
  const add = clampReportMinutes(addMinutes)
  const minutes = Number(report.minutes) + add
  const reminderAt = Number(report.reminder_at) + add * 60000
  const patch = { minutes, reminder_at: reminderAt }
  await repo.updateReport(report.id, patch)
  const next = { ...report, ...patch }
  try {
    await reminder.scheduleReport(next)
  } catch (e) {}
  return next
}

/**
 * 结束报备。
 * @param {boolean} completed true=完成了(+5)，false=放弃(0)
 */
export async function finishReport(completed = true) {
  const report = await repo.getActiveReport()
  if (!report) throw new Error('没有进行中的报备')
  const now = Date.now()
  const patch = {
    status: 'ended',
    ended_at: now,
    points: completed ? points.RULES.reportComplete : 0,
  }
  await repo.updateReport(report.id, patch)
  const settled = { ...report, ...patch }
  if (completed) await points.awardReportComplete(settled)
  try {
    await reminder.cancelReminder(`report:${report.id}`)
  } catch (e) {}
  return settled
}

/** 按时结束：ended 且 ended_at <= reminder_at + 5 分钟 */
export function isOnTime(report) {
  if (!report || report.status !== 'ended' || !report.ended_at) return false
  return Number(report.ended_at) <= Number(report.reminder_at) + OVERDUE_GRACE_MS
}
