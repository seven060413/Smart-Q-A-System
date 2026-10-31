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
 * 语音转文字：上传录音到 /api/transcribe，返回 { text }。
 * - App 端传本机临时文件路径 filePath；
 * - H5 端传 File 对象 file（uni.uploadFile H5 2.6.15+ 支持），避免 blob URL 丢文件名；
 * 响应 JSON 在 res.data 字符串中，需安全解析；错误沿用 ApiError/parseError 约定。
 */
export function transcribeAudio(filePath, { file = null } = {}) {
  return new Promise((resolve, reject) => {
    const options = {
      url: `${BASE_URL}/api/transcribe`,
      name: 'file',
      timeout: 60000,
      header: {},
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          let data = null
          try {
            data = JSON.parse(res.data)
          } catch (e) {
            reject(new ApiError('识别结果解析失败，请重试', { status: 0, code: 'PARSE_ERROR' }))
            return
          }
          resolve(data)
          return
        }
        reject(parseError(res))
      },
      fail: (err) => {
        const errMsg = (err && err.errMsg) || ''
        const timeout = /timeout|超时/i.test(errMsg)
        reject(
          new ApiError(
            timeout ? '识别请求超时，请重试' : '网络连接失败，请检查网络或后端服务地址',
            { status: 0, code: timeout ? 'TIMEOUT' : 'NETWORK_ERROR' }
          )
        )
      },
    }
    // 与 request() 的认证约定保持一致：已登录时附带令牌（该接口不强制认证）
    const token = getStoredToken()
    if (token) options.header.Authorization = `Bearer ${token}`

    if (file) {
      // H5：uni.uploadFile 即使传了 file 也要求 filePath 非空（内部校验），
      // 这里给一个占位名；实际发送的是 file 对象本身。
      options.file = file
      options.filePath = (file && file.name) || 'audio'
    } else {
      options.filePath = filePath
    }
    uni.uploadFile(options)
  })
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
