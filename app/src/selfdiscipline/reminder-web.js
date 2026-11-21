// H5 降级提醒：只在页面打开期间有效，不支持被杀后提醒与悬浮窗。

const timers = new Map()

function notificationSupported() {
  try {
    return typeof window !== 'undefined' && typeof window.Notification !== 'undefined'
  } catch (e) {
    return false
  }
}

function notificationsGranted() {
  try {
    return notificationSupported() && window.Notification.permission === 'granted'
  } catch (e) {
    return false
  }
}

function fire(entry) {
  try {
    uni.showToast({ title: entry.title || '提醒', icon: 'none', duration: 2600 })
  } catch (e) {}
  if (notificationsGranted()) {
    try {
      const n = new window.Notification(entry.title || '提醒', {
        body: entry.body || '',
        tag: entry.id,
      })
      n.onclick = () => {
        try {
          n.close()
        } catch (e) {}
        try {
          window.focus()
        } catch (e) {}
      }
    } catch (e) {}
  }
}

export function getStatus() {
  return {
    supported: false,
    notifications: notificationsGranted(),
    exactAlarm: false,
    exactAlarmNeeded: false,
    sdk: 0,
    vendor: 'web'
  }
}

export function requestNotificationPermission() {
  return new Promise((resolve) => {
    if (!notificationSupported()) {
      resolve(false)
      return
    }
    try {
      const result = window.Notification.requestPermission((permission) => {
        resolve(permission === 'granted')
      })
      if (result && typeof result.then === 'function') {
        result.then((permission) => resolve(permission === 'granted')).catch(() => resolve(false))
      }
    } catch (e) {
      resolve(false)
    }
  })
}

export function openNotificationSettings() {
  uni.showToast({ title: '请在浏览器设置中允许通知', icon: 'none' })
}

export function canScheduleExactAlarms() {
  return false
}

export function openExactAlarmSettings() {
  uni.showToast({ title: '网页版不支持精确闹钟，请使用安卓 App', icon: 'none' })
}

export function schedule(id, triggerAt, title, body, kind, refId) {
  cancel(id)
  const delay = Number(triggerAt) - Date.now()
  if (!Number.isFinite(delay) || delay <= 0) {
    return { ok: false, exact: false, reason: 'past' }
  }
  // setTimeout 最大约 24.8 天，超出的提醒交给下次打开页面时重排。
  if (delay > 2147483000) {
    return { ok: false, exact: false, reason: 'too-far' }
  }
  const timer = setTimeout(() => {
    timers.delete(id)
    fire({ id, title, body, kind, refId })
  }, delay)
  timers.set(id, { id, triggerAt: Number(triggerAt), title, body, kind, refId, timer })
  return { ok: true, exact: false, reason: 'web-timer' }
}

export function cancel(id) {
  const entry = timers.get(id)
  if (!entry) return
  try {
    clearTimeout(entry.timer)
  } catch (e) {}
  timers.delete(id)
}

export function cancelAll() {
  for (const id of [...timers.keys()]) cancel(id)
}

export function getScheduled() {
  const now = Date.now()
  return [...timers.values()]
    .filter((entry) => Number(entry.triggerAt) > now)
    .map((entry) => ({
      id: entry.id,
      triggerAt: entry.triggerAt,
      title: entry.title,
      body: entry.body,
      kind: entry.kind,
      refId: entry.refId
    }))
}

export function postNow(title, body, kind, refId) {
  fire({ id: `now:${Date.now()}`, title, body, kind, refId })
}
