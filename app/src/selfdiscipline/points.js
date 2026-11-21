// 点数账本：所有加减分只在这里生成流水，任何地方都不直接改“当前点数”。

import * as repo from './repository.js'
import { todayKey } from './dates.js'

export const RULES = {
  focusPerMinute: 1,
  focusEarlyPerMinute: 1,
  reportComplete: 5,
  checkin: 5,
  checkinAll: 5,
}

export async function awardFocusComplete(session) {
  const delta = Number(session.planned_min) || 0
  if (!delta) return null
  return repo.addLedger({
    id: `ledger:focus_complete:${session.id}`,
    delta,
    reason: 'focus_complete',
    ref_type: 'focus',
    ref_id: session.id,
    created_at: session.ended_at || Date.now(),
  })
}

export async function awardFocusEarly(session) {
  const delta = Math.max(0, Math.floor(Number(session.actual_min) || 0))
  if (!delta) return null
  return repo.addLedger({
    id: `ledger:focus_early:${session.id}`,
    delta,
    reason: 'focus_early',
    ref_type: 'focus',
    ref_id: session.id,
    created_at: session.ended_at || Date.now(),
  })
}

export async function awardReportComplete(report) {
  return repo.addLedger({
    id: `ledger:report_complete:${report.id}`,
    delta: RULES.reportComplete,
    reason: 'report_complete',
    ref_type: 'report',
    ref_id: report.id,
    created_at: report.ended_at || Date.now(),
  })
}

export async function awardCheckin(itemId, date) {
  return repo.addLedger({
    id: `ledger:checkin:${itemId}:${date}`,
    delta: RULES.checkin,
    reason: 'checkin',
    ref_type: 'checkin',
    ref_id: `${itemId}:${date}`,
    created_at: Date.now(),
  })
}

export async function undoCheckin(itemId, date) {
  return repo.addLedger({
    id: `ledger:checkin_undo:${itemId}:${date}:${Date.now()}`,
    delta: -RULES.checkin,
    reason: 'checkin_undo',
    ref_type: 'checkin',
    ref_id: `${itemId}:${date}`,
    created_at: Date.now(),
  })
}

/** 当日全部完成 +5，每天只记一次（固定 id 防重复） */
export async function awardCheckinAll(date = todayKey()) {
  const id = `checkin_all:${date}`
  const exists = await repo.getLedgerById(id)
  if (exists) return null
  return repo.addLedger({
    id,
    delta: RULES.checkinAll,
    reason: 'checkin_all',
    ref_type: 'checkin_all',
    ref_id: date,
    created_at: Date.now(),
  })
}

/** 撤销“当日全部完成”奖励，成对记 -5 */
export async function undoCheckinAll(date = todayKey()) {
  const bonus = await repo.getLedgerById(`checkin_all:${date}`)
  if (!bonus) return null
  const undoId = `checkin_all_undo:${date}`
  const undone = await repo.getLedgerById(undoId)
  if (undone) return null
  return repo.addLedger({
    id: undoId,
    delta: -RULES.checkinAll,
    reason: 'checkin_all_undo',
    ref_type: 'checkin_all',
    ref_id: date,
    created_at: Date.now(),
  })
}

export async function manualAdjust(delta) {
  const value = Number(delta)
  if (!Number.isFinite(value) || !value) return null
  return repo.addLedger({
    delta: value,
    reason: 'manual',
    ref_type: 'manual',
    ref_id: '',
    created_at: Date.now(),
  })
}
