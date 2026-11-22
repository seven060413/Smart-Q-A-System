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

// 头像单独存 user_avatar，不再在缓存的 user JSON 里重复存一份 base64。
function slimUser(user) {
  if (!user || typeof user !== 'object') return user
  const copy = { ...user }
  delete copy.avatar
  return copy
}

// 退出登录会清掉 user_avatar；重新登录/恢复会话时把服务端头像写回本地缓存，
// 否则只读 user_avatar 的页面（如侧边栏）会显示成默认头像。
function syncAvatarCache(user) {
  const avatar = user && typeof user.avatar === 'string' ? user.avatar : ''
  if (avatar) safeSet('user_avatar', avatar)
}

export function saveStoredAuth({ token, user, expiresAt }) {
  syncAvatarCache(user)
  safeSet(TOKEN_KEY, token)
  safeSet(USER_KEY, JSON.stringify(slimUser(user)))
  safeSet(EXPIRES_KEY, expiresAt || '')
}

export function updateStoredUser(user) {
  syncAvatarCache(user)
  safeSet(USER_KEY, JSON.stringify(slimUser(user)))
}

// 与账号绑定的本地资料缓存。退出/换账号时必须清掉，否则会串号。
export const PROFILE_OWNER_KEY = 'ikgr.profile.owner'
const PROFILE_CACHE_KEYS = [
  'user_avatar',
  'custom_nickname',
  'user_grade',
  'last_conversation_id',
]

export function clearProfileCaches() {
  for (const key of PROFILE_CACHE_KEYS) safeRemove(key)
  safeRemove(PROFILE_OWNER_KEY)
}

/** 登录/恢复会话时认领缓存；发现是另一位用户则先清空。 */
export function claimProfileCaches(userId) {
  if (!userId) return
  const owner = safeGet(PROFILE_OWNER_KEY, '')
  if (owner && owner !== userId) clearProfileCaches()
  safeSet(PROFILE_OWNER_KEY, userId)
}

export function clearStoredAuth() {
  safeRemove(TOKEN_KEY)
  safeRemove(USER_KEY)
  safeRemove(EXPIRES_KEY)
  // 401、退出、令牌过期都会走到这里；资料缓存一并清掉。
  clearProfileCaches()
}
