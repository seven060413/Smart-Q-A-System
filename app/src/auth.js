// 前端登录状态：负责恢复、保存、清除和退出。
// 不保存密码；令牌/用户信息只来自后端响应。

import {
  fetchMe,
  loginUser,
  logoutUser,
  registerUser,
} from './api.js'
import {
  claimProfileCaches,
  clearStoredAuth,
  getStoredExpiresAt,
  getStoredToken,
  getStoredUser,
  saveStoredAuth,
  updateStoredUser,
} from './auth-storage.js'
import { resetAuth, setAuthState, store } from './store.js'

export function saveAuth(data) {
  const token = data.token || ''
  const user = data.user || null
  const expiresAt = data.expires_at || ''
  // 换了账号就先清掉上一位用户的头像/昵称/年级/会话缓存。
  claimProfileCaches(user && user.id)
  saveStoredAuth({ token, user, expiresAt })
  setAuthState(token, user, expiresAt)
}

export function clearAuth() {
  clearStoredAuth()
  resetAuth()
  store.auth.ready = true
}

// App 回到前台时调用：本地过期就直接清掉，避免顶部继续显示“已登录”。
export function checkAuthExpiry() {
  if (!store.auth.token) return
  const expiresMs = Date.parse(store.auth.expiresAt)
  if (Number.isFinite(expiresMs) && expiresMs <= Date.now()) {
    clearAuth()
  }
}

export async function register(payload) {
  const data = await registerUser(payload)
  saveAuth(data)
  return data
}

export async function login(payload) {
  const data = await loginUser(payload)
  saveAuth(data)
  return data
}

export async function logout() {
  let remoteOk = true
  try {
    if (getStoredToken()) {
      await logoutUser()
    }
  } catch (e) {
    // 断网或令牌已失效时仍然清除本地登录状态，避免“退不出去”。
    remoteOk = false
  }
  clearAuth()
  return remoteOk
}

export async function initAuth() {
  store.auth.ready = false
  const token = getStoredToken()
  if (!token) {
    store.auth.ready = true
    return
  }

  const expiresAt = getStoredExpiresAt()
  const expiresMs = Date.parse(expiresAt)
  if (Number.isFinite(expiresMs) && expiresMs <= Date.now()) {
    clearAuth()
    return
  }

  const cachedUser = getStoredUser()
  // 老版本缓存没有 owner 标记：认领给当前缓存用户，保留其资料缓存。
  if (cachedUser && cachedUser.id) {
    claimProfileCaches(cachedUser.id)
    // 旧版缓存里可能还带着 base64 avatar，重写一次去掉重复副本。
    updateStoredUser(cachedUser)
  }
  store.auth.token = token
  store.auth.expiresAt = expiresAt
  store.auth.user = cachedUser

  try {
    const user = await fetchMe()
    store.auth.user = user
    store.auth.token = token
    store.auth.expiresAt = expiresAt
    updateStoredUser(user)
  } catch (e) {
    // 401 已由 api.js 清除本地状态；网络失败时保留缓存，允许稍后重试。
    if (e && e.status === 401) {
      clearAuth()
    }
  } finally {
    store.auth.ready = true
  }
}

export function isLoggedIn() {
  return !!store.auth.token && !!store.auth.user
}

export function openAuthPage() {
  uni.navigateTo({ url: '/pages/auth/auth' })
}
