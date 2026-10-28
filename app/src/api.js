import { BASE_URL } from './config.js'
import { clearStoredAuth, getStoredToken } from './auth-storage.js'
import { resetAuth } from './store.js'

/** 统一 API 错误：status=0 表示网络层失败。 */
export class ApiError extends Error {
  constructor(message, { status = 0, code = '', details = null } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }
}

function parseError(res) {
  let body = res.data
  if (typeof body === 'string') {
    try {
      body = JSON.parse(body)
    } catch (e) {
      body = null
    }
  }
  const error = body && body.error
  const detail = error && Array.isArray(error.details) && error.details[0]
  const message =
    (detail && detail.msg) ||
    (error && error.message) ||
    `请求失败（HTTP ${res.statusCode}）`
  return new ApiError(message, {
    status: res.statusCode,
    code: (error && error.code) || 'HTTP_ERROR',
    details: (error && error.details) || null,
  })
}

/**
 * 统一请求封装。
 * - auth=true 时自动带 Authorization: Bearer <token>；
 * - 受保护接口返回 401 时清除本地登录状态，由调用方决定是否跳登录页；
 * - 绝不把密码写入本地存储。
 */
function request(path, { method = 'GET', data = null, auth = false, timeout = 15000 } = {}) {
  return new Promise((resolve, reject) => {
    const header = { 'Content-Type': 'application/json' }
    const token = getStoredToken()
    if (auth && token) {
      header.Authorization = `Bearer ${token}`
    }

    uni.request({
      url: `${BASE_URL}${path}`,
      method,
      data,
      header,
      timeout,
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data)
          return
        }
        if (res.statusCode === 401 && auth) {
          clearStoredAuth()
          resetAuth()
        }
        reject(parseError(res))
      },
      fail: () => {
        reject(
          new ApiError('网络连接失败，请检查网络或后端服务地址', {
            status: 0,
            code: 'NETWORK_ERROR',
          })
        )
      },
    })
  })
}

function queryString(params) {
  const parts = Object.entries(params)
    .filter(([, value]) => value !== null && value !== undefined && value !== '')
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
  return parts.length ? `?${parts.join('&')}` : ''
}

/**
 * 问答：
 * - 游客不传 auth/conversationId，不落库；
 * - 登录用户传 auth=true，后端按令牌归属保存；
 * - clientRequestId 用于网络重试去重。
 */
export function askQuestion(
  question,
  { conversationId = null, clientRequestId = null, auth = false } = {}
) {
  const data = { question }
  if (conversationId) data.conversation_id = conversationId
  if (clientRequestId) data.client_request_id = clientRequestId
  return request('/api/ask', {
    method: 'POST',
    data,
    auth,
    timeout: 60000,
  })
}

export function createConversation(payload = {}) {
  return request('/api/conversations', {
    method: 'POST',
    data: payload,
    auth: true,
    timeout: 15000,
  })
}

export function listConversations({ limit = 20, cursor = null } = {}) {
  return request(`/api/conversations${queryString({ limit, cursor })}`, {
    auth: true,
    timeout: 15000,
  })
}

export function getConversation(conversationId) {
  return request(`/api/conversations/${encodeURIComponent(conversationId)}`, {
    auth: true,
    timeout: 15000,
  })
}

export function listMessages(conversationId, { limit = 50, cursor = null } = {}) {
  return request(
    `/api/conversations/${encodeURIComponent(conversationId)}/messages${queryString({
      limit,
      cursor,
    })}`,
    { auth: true, timeout: 15000 }
  )
}

export function deleteConversation(conversationId) {
  return request(`/api/conversations/${encodeURIComponent(conversationId)}`, {
    method: 'DELETE',
    auth: true,
    timeout: 15000,
  })
}

export function registerUser(payload) {
  return request('/api/auth/register', {
    method: 'POST',
    data: payload,
    timeout: 15000,
  })
}

export function loginUser(payload) {
  return request('/api/auth/login', {
    method: 'POST',
    data: payload,
    timeout: 15000,
  })
}

export function fetchMe() {
  return request('/api/auth/me', { auth: true, timeout: 15000 })
}

export function logoutUser() {
  return request('/api/auth/logout', { method: 'POST', auth: true, timeout: 15000 })
}
