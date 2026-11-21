// 自律模块启动引导：初始化存储、恢复专注、对账提醒与守护。

import * as repo from './repository.js'
import * as reminder from './reminder.js'
import * as focus from './focus.js'
import * as checkin from './checkin.js'
import * as guard from './guard.js'

let booted = false
let booting = null

export function bootstrapSelfDiscipline() {
  if (booted) return Promise.resolve()
  if (booting) return booting

  booting = (async () => {
    await repo.init()
    booted = true
    try {
      await focus.loadRunningFocus()
    } catch (e) {}
    try {
      await reminder.reconcile()
    } catch (e) {}
    try {
      await checkin.rescheduleReminders()
    } catch (e) {}
    try {
      await guard.reconcileGuard()
    } catch (e) {}
  })().finally(() => {
    booting = null
  })

  return booting
}

/** 回到前台时轻量对账（不重复排打卡提醒） */
export async function onSelfDisciplineForeground() {
  if (!booted) return
  try {
    await reminder.reconcile()
  } catch (e) {}
  try {
    await guard.reconcileGuard()
  } catch (e) {}
}
