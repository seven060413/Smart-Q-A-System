// 登录凭证的本地存储封装。
// 只保存后端返回的令牌、用户展示信息和过期时间；绝不保存密码。

export const TOKEN_KEY = 'ikgr.auth.token'
export const USER_KEY = 'ikgr.auth.user'
export const EXPIRES_KEY = 'ikgr.auth.expires_at'

function safeGet(key, fallback) {
  try {
    const value = uni.getStorageSync(key)
    return value === undefined || value === null || value === '' ? fallback : value
  } catch (e) {
    return fallback
  }
}

function safeSet(key, value) {
  try {
    uni.setStorageSync(key, value)
  } catch (e) {
    // 存储失败时仅影响“下次启动免登录”，不影响当前页面使用。
  }
}

function safeRemove(key) {
  try {
    uni.removeStorageSync(key)
  } catch (e) {
    // 忽略清理失败，避免影响退出流程。
  }
}

export function getStoredToken() {
  return safeGet(TOKEN_KEY, '')
}

export function getStoredExpiresAt() {
  return safeGet(EXPIRES_KEY, '')
}

export function getStoredUser() {
  const raw = safeGet(USER_KEY, '')
  if (!raw) return null
  if (typeof raw === 'object') return raw
  try {
    return JSON.parse(raw)
  } catch (e) {
    return null
  }
}

export function saveStoredAuth({ token, user, expiresAt }) {
  safeSet(TOKEN_KEY, token)
  safeSet(USER_KEY, JSON.stringify(user || null))
  safeSet(EXPIRES_KEY, expiresAt || '')
}

export function updateStoredUser(user) {
  safeSet(USER_KEY, JSON.stringify(user || null))
}

export function clearStoredAuth() {
  safeRemove(TOKEN_KEY)
  safeRemove(USER_KEY)
  safeRemove(EXPIRES_KEY)
}
