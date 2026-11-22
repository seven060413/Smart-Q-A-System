// 专注守护：原生悬浮窗 + 前台服务的 JS 适配层。
// H5 下所有能力降级为空实现，页面与 App.vue 可以无条件调用。

import * as repo from './repository.js'

// #ifdef APP-PLUS
import * as nativeGuard from '@/uni_modules/ik-guard'
// #endif

let activeSession = null

function call(name, fallback, ...args) {
  // #ifdef APP-PLUS
  try {
    if (nativeGuard && typeof nativeGuard[name] === 'function') {
      return nativeGuard[name](...args)
    }
  } catch (e) {
    console.error(`[ik-guard] ${name} 调用失败`, e)
  }
  // #endif
  return fallback
}

function endAtOf(session) {
  if (!session) return 0
  return Number(session.started_at) + Number(session.planned_min) * 60000
}

export function getGuardStatus() {
  return call('getStatus', {
    supported: false,
    overlay: false,
    notifications: false,
    serviceRunning: false,
    guardEnabled: true,
    sdk: 0,
    vendor: '',
  })
}

export function hasOverlayPermission() {
  return call('hasOverlayPermission', false)
}

export function openOverlaySettings() {
  return call('openOverlaySettings', undefined)
}

/** 专注开始后调用：启动前台服务并登记当前会话 */
export async function startGuard(session) {
  activeSession = session ? { ...session } : null
  if (!session) return { ok: false, overlay: false, service: false, reason: 'no-session' }
  try {
    const enabled = await repo.getSetting('guardEnabled', true)
    if (enabled === false) {
      activeSession = null
      call('stopGuard', undefined)
      return { ok: false, overlay: false, service: false, reason: 'disabled' }
    }
  } catch (e) {}

  return call(
    'startGuard',
    { ok: false, overlay: false, service: false, reason: 'unsupported' },
    String(session.id || ''),
    endAtOf(session),
    String(session.task || ''),
    '专注中'
  )
}

export function stopGuard() {
  activeSession = null
  return call('stopGuard', undefined)
}

/** App 进入后台：原生层延迟 1.5 秒再显示悬浮窗 */
export function onAppBackground() {
  if (!activeSession) return
  const endAt = endAtOf(activeSession)
  if (endAt && endAt <= Date.now()) {
    call('updateGuard', undefined, endAt, String(activeSession.task || ''), 'due')
  }
  return call('onAppBackground', undefined)
}

/** App 回到前台：立即隐藏悬浮窗 */
export function onAppForeground() {
  return call('onAppForeground', undefined)
}

export function updateGuard(session, state = 'focus') {
  if (!session) return
  activeSession = { ...session }
  return call('updateGuard', undefined, endAtOf(session), String(session.task || ''), state)
}

/**
 * 对账：启动或回到前台时调用。
 * 有进行中的专注 → 确保服务在；没有 → 停掉服务。
 */
export async function reconcileGuard() {
  let running = null
  try {
    running = await repo.getRunningFocus()
  } catch (e) {
    running = null
  }

  if (!running) {
    activeSession = null
    call('stopGuard', undefined)
    return { ok: true, running: false }
  }

  let enabled = true
  try {
    enabled = (await repo.getSetting('guardEnabled', true)) !== false
  } catch (e) {}

  if (!enabled) {
    activeSession = null
    call('stopGuard', undefined)
    return { ok: true, running: true, disabled: true }
  }

  activeSession = running
  return call(
    'startGuard',
    { ok: false, overlay: false, service: false, reason: 'unsupported' },
    String(running.id),
    endAtOf(running),
    String(running.task || ''),
    '专注中'
  )
}

export function currentGuardSession() {
  return activeSession
}

/** v1.1 预留：读取悬浮窗按钮留下的动作 */
export function takePendingAction() {
  return call('takePendingAction', null)
}
