// 自律模块的本地时间工具：全部使用本地时区，中国无夏令时，不做 DST 处理。

export function pad2(n) {
  return String(n).padStart(2, '0')
}

/** 本地 YYYY-MM-DD */
export function dateKey(ms = Date.now()) {
  const d = new Date(ms)
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`
}

export function todayKey() {
  return dateKey(Date.now())
}

export function startOfDay(ms = Date.now()) {
  const d = new Date(ms)
  d.setHours(0, 0, 0, 0)
  return d.getTime()
}

export function endOfDay(ms = Date.now()) {
  const d = new Date(ms)
  d.setHours(23, 59, 59, 999)
  return d.getTime()
}

export function addDays(ms, n) {
  const d = new Date(ms)
  d.setDate(d.getDate() + n)
  return d.getTime()
}

/** ISO 星期：1=周一 ... 7=周日 */
export function weekdayIso(ms = Date.now()) {
  const day = new Date(ms).getDay()
  return day === 0 ? 7 : day
}

export const WEEKDAY_LABELS = ['一', '二', '三', '四', '五', '六', '日']

export function weekdayLabel(iso) {
  return WEEKDAY_LABELS[Number(iso) - 1] || ''
}

/** 把 'YYYY-MM-DD' + 'HH:mm' 解析成本地 epoch 毫秒 */
export function parseHHmm(dayKey, hhmm) {
  if (!dayKey || !hhmm) return 0
  const dm = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(dayKey))
  const tm = /^(\d{1,2}):(\d{2})$/.exec(String(hhmm))
  if (!dm || !tm) return 0
  const d = new Date(
    Number(dm[1]),
    Number(dm[2]) - 1,
    Number(dm[3]),
    Number(tm[1]),
    Number(tm[2]),
    0,
    0
  )
  return d.getTime()
}

/** 毫秒 -> 'HH:mm' */
export function formatHm(ms) {
  const d = new Date(ms)
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`
}

/** 毫秒 -> 'mm:ss'（分钟可能超过 60） */
export function formatClock(ms) {
  const total = Math.max(0, Math.floor(ms / 1000))
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${pad2(m)}:${pad2(s)}`
}

/** 毫秒 -> 'M月D日' */
export function formatMonthDay(ms = Date.now()) {
  const d = new Date(ms)
  return `${d.getMonth() + 1}月${d.getDate()}日`
}

/** 毫秒 -> 'M月D日 HH:mm' */
export function formatDateTime(ms) {
  const d = new Date(ms)
  return `${d.getMonth() + 1}月${d.getDate()}日 ${pad2(d.getHours())}:${pad2(d.getMinutes())}`
}

/** 判断毫秒是否属于某个本地日期键 */
export function isSameDay(ms, dayKey) {
  return dateKey(ms) === dayKey
}

/** '1,2,3' -> [1,2,3] */
export function parseDays(value) {
  if (!value) return []
  return String(value)
    .split(',')
    .map((n) => Number(n))
    .filter((n) => n >= 1 && n <= 7)
}

/** [1,2,3] -> '1,2,3' */
export function daysToString(days) {
  const list = Array.isArray(days) ? days : []
  return list
    .map((n) => Number(n))
    .filter((n) => n >= 1 && n <= 7)
    .sort((a, b) => a - b)
    .join(',')
}

/** 生成从 fromMs 到 toMs（按天）的日期键数组，包含两端 */
export function dayKeysBetween(fromMs, toMs) {
  const out = []
  let cursor = startOfDay(fromMs)
  const end = startOfDay(toMs)
  let guard = 0
  while (cursor <= end && guard < 2000) {
    out.push(dateKey(cursor))
    cursor = addDays(cursor, 1)
    guard += 1
  }
  return out
}
