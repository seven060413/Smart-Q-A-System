// App 端提醒后端：封装 UTS 插件 ik-reminder。该文件只在 APP-PLUS 下被引用。

// #ifdef APP-PLUS
// 临时禁用：ik-reminder UTS 模块在当前 HBuilderX 版本编译失败，源码已移到
// app/uts-disabled/ik-reminder。恢复时把目录移回 src/uni_modules 并恢复此 import。
// import * as native from '@/uni_modules/ik-reminder'
// #endif

function call(name, fallback, ...args) {
  // 原生精确提醒暂不可用，返回降级值；通知权限申请仍走下面的 plus.android。
  return fallback
}

export function getStatus() {
  return call('getStatus', {
    supported: false,
    notifications: false,
    exactAlarm: false,
    exactAlarmNeeded: false,
    sdk: 0,
    vendor: ''
  })
}

export function requestNotificationPermission() {
  return new Promise((resolve) => {
    // #ifdef APP-PLUS
    try {
      if (typeof plus !== 'undefined' && plus.android && plus.android.requestPermissions) {
        plus.android.requestPermissions(
          ['android.permission.POST_NOTIFICATIONS'],
          (e) => {
            const granted = !!(e && e.granted && e.granted.length > 0)
            if (!granted) {
              try {
                call('openNotificationSettings', undefined)
              } catch (err) {}
            }
            resolve(granted)
          },
          () => resolve(false)
        )
        return
      }
    } catch (e) {}
    // #endif
    resolve(false)
  })
}

export function openNotificationSettings() {
  return call('openNotificationSettings', undefined)
}

export function canScheduleExactAlarms() {
  return call('canScheduleExactAlarms', false)
}

export function openExactAlarmSettings() {
  return call('openExactAlarmSettings', undefined)
}

export function schedule(id, triggerAt, title, body, kind, refId) {
  return call('schedule', { ok: false, exact: false, reason: 'unsupported' }, id, triggerAt, title, body, kind, refId)
}

export function cancel(id) {
  return call('cancel', undefined, id)
}

export function cancelAll() {
  return call('cancelAll', undefined)
}

export function getScheduled() {
  return call('getScheduled', [])
}

export function postNow(title, body, kind, refId) {
  return call('postNow', undefined, title, body, kind, refId)
}
