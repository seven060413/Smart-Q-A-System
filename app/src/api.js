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
      // 👇 修改了这里：接收 err 参数，打印详细原因，并带入提示中
      fail: (err) => {
        console.error(`[网络请求失败] 路径: ${path}`, err)
        const errMsg = (err && err.errMsg) || '未知错误'
        reject(
          new ApiError(`网络连接失败（${errMsg}），请检查后端服务地址`, {
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
export function uploadAttachment(filePath, { file = null, conversationId = null } = {}) {
  // H5 的 uni.uploadFile 仍会校验 filePath.indexOf，即使同时提供 file；
  // 使用原生 FormData 可直接发送浏览器 File，避免把 File 对象误当路径。
  if (file && typeof window !== 'undefined' && typeof FormData !== 'undefined' && typeof fetch === 'function') {
    return new Promise(async (resolve, reject) => {
      const form = new FormData()
      form.append('file', file, file.name || 'attachment')
      if (conversationId) form.append('conversation_id', conversationId)
      const headers = {}
      const token = getStoredToken()
      if (token) headers.Authorization = `Bearer ${token}`
      try {
        const response = await fetch(`${BASE_URL}/api/attachments`, { method: 'POST', headers, body: form })
        const body = await response.json().catch(() => null)
        if (response.ok) {
          resolve(body)
          return
        }
        const error = body && body.error
        reject(new ApiError((error && error.message) || `附件上传失败（HTTP ${response.status}）`, {
          status: response.status,
          code: (error && error.code) || 'HTTP_ERROR',
          details: (error && error.details) || null,
        }))
      } catch (error) {
        // 保留浏览器原始错误（Failed to fetch / net::ERR_* / CORS），否则无法区分失败原因
        if (!(error instanceof ApiError)) console.error('attachment upload failed:', error)
        reject(error instanceof ApiError ? error : new ApiError(
          `附件上传失败，请检查网络${error && error.message ? `（${error.message}）` : ''}`,
          { status: 0, code: 'NETWORK_ERROR' }
        ))
      }
    })
  }
  return new Promise((resolve, reject) => {
    const token = getStoredToken()
    const formData = conversationId ? { conversation_id: conversationId } : {}
    const options = {
      url: `${BASE_URL}/api/attachments`,
      name: 'file',
      filePath: file ? (file.name || 'image') : filePath,
      formData,
      timeout: 30000,
      header: token ? { Authorization: `Bearer ${token}` } : {},
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          try { resolve(typeof res.data === 'string' ? JSON.parse(res.data) : res.data) } catch (e) { reject(new ApiError('附件响应解析失败', { status: 0, code: 'PARSE_ERROR' })) }
          return
        }
        reject(parseError(res))
      },
      fail: (err) => {
        const detail = (err && err.errMsg) || ''
        if (detail) console.error('attachment uploadFile failed:', detail)
        reject(new ApiError(`图片上传失败，请检查网络${detail ? `（${detail}）` : ''}`, { status: 0, code: 'NETWORK_ERROR' }))
      },
    }
    if (file) options.file = file
    uni.uploadFile(options)
  })
}

export function attachmentStatus(id) {
  return request(`/api/attachments/${encodeURIComponent(id)}/status`, { auth: true, timeout: 15000 })
}

export function attachmentAction(id, action, data = null) {
  return request(`/api/attachments/${encodeURIComponent(id)}/${action}`, {
    method: 'POST', data, auth: true, timeout: action === 'recognize' ? 60000 : 120000,
  })
}

export function deleteAttachment(id) {
  return request(`/api/attachments/${encodeURIComponent(id)}`, { method: 'DELETE', auth: true })
}

export function attachmentContent(id) {
  return new Promise((resolve, reject) => {
    uni.request({
      url: `${BASE_URL}/api/attachments/${encodeURIComponent(id)}/content`,
      method: 'GET',
      responseType: 'arraybuffer',
      header: { Authorization: `Bearer ${getStoredToken()}` },
      success: (res) => {
        if (res.statusCode < 200 || res.statusCode >= 300) { reject(parseError(res)); return }
        const contentType = (res.header && (res.header['content-type'] || res.header['Content-Type'])) || 'application/octet-stream'
        try {
          if (typeof URL !== 'undefined' && typeof URL.createObjectURL === 'function' && typeof Blob !== 'undefined') {
            resolve(URL.createObjectURL(new Blob([res.data], { type: contentType })))
            return
          }
          const bytes = new Uint8Array(res.data)
          let binary = ''
          for (let offset = 0; offset < bytes.length; offset += 0x8000) {
            binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000))
          }
          const base64 = typeof btoa === 'function' ? btoa(binary) : uni.arrayBufferToBase64(res.data)
          resolve(`data:${contentType};base64,${base64}`)
        } catch (e) { reject(new ApiError('附件加载失败', { status: 0, code: 'ATTACHMENT_LOAD_ERROR' })) }
      },
      fail: () => reject(new ApiError('附件加载失败', { status: 0, code: 'NETWORK_ERROR' })),
    })
  })
}

export function askQuestion(
  question,
  { conversationId = null, clientRequestId = null, auth = false, grade = null } = {}
) {
  const data = { question }
  if (conversationId) data.conversation_id = conversationId
  if (clientRequestId) data.client_request_id = clientRequestId
  // 游客用本地年级；登录用户后端会优先用资料里的年级。
  if (Number.isInteger(grade)) data.grade = grade
  return request('/api/ask', {
    method: 'POST',
    data,
    auth,
    timeout: 60000,
  })
}

/**
 * 批量查询知识点关联视频（公开只读，不需要登录）。
 * nodeKeys 为稳定知识点 ID（prerequisite_gaps[i].id / learning_path.body_id）。
 */
export function listVideos(nodeKeys, { limit = 2 } = {}) {
  const keys = (Array.isArray(nodeKeys) ? nodeKeys : [nodeKeys]).filter(Boolean)
  const params = keys.map((key) => `node_key=${encodeURIComponent(key)}`)
  params.push(`limit=${encodeURIComponent(limit)}`)
  // 审核结果会变化，加时间戳绕过浏览器对旧空结果的缓存。
  params.push(`_t=${Date.now()}`)
  return request(`/api/videos?${params.join('&')}`, { timeout: 15000 }).then((data) => {
    // 防止代理把 /api/videos 回退成 index.html 时静默显示“暂无视频”。
    if (!data || !Array.isArray(data.items)) {
      throw new ApiError('视频接口返回格式异常，请检查后端地址', {
        status: 0,
        code: 'BAD_RESPONSE',
      })
    }
    return data
  })
}

/**
 * 视频讲解库：全部已审核视频，支持标题/知识点/UP主搜索与教材册筛选。
 * book: '' | 七上 | 七下 | 八上 | 八下 | 九上 | 九下
 */
export function listVideoLibrary({ q = '', book = '', page = 1, pageSize = 20 } = {}) {
  const params = [`page=${encodeURIComponent(page)}`, `page_size=${encodeURIComponent(pageSize)}`]
  if (q) params.push(`q=${encodeURIComponent(q)}`)
  if (book) params.push(`book=${encodeURIComponent(book)}`)
  params.push(`_t=${Date.now()}`)
  return request(`/api/videos/library?${params.join('&')}`, { timeout: 15000 }).then((data) => {
    if (!data || !Array.isArray(data.items)) {
      throw new ApiError('视频库接口返回格式异常，请检查后端地址', {
        status: 0,
        code: 'BAD_RESPONSE',
      })
    }
    return data
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

/**
 * 获取知识点详情（定义、例子、关联练习等）
 * @param {string} nodeId - 知识点ID（如 math_5b_rjb_cpt1）
 */
export function getKnowledgeDetail(nodeId) {
  return request(`/api/knowledge/${encodeURIComponent(nodeId)}`, {
    auth: false, // 知识点详情可公开访问
    timeout: 10000,
  })
}

export function logoutUser() {
  return request('/api/auth/logout', { method: 'POST', auth: true, timeout: 15000 })
}

/**
 * 更新个人资料（昵称、头像、年级）
 * @param {Object} payload - { display_name?, avatar?, grade? }
 *   grade 传 1-9 设置年级；显式传 null 清空年级；不传则保持原值。
 * @returns {Promise<{ id, username, display_name, role, avatar, grade, created_at, last_login_at }>}
 */
export function updateProfile(payload) {
  return request('/api/auth/profile', {
    method: 'PUT',
    data: payload,
    auth: true,
    timeout: 15000,
  })
}

/**
 * 智能答案校验：使用 LLM 判断学生答案是否正确
 * @param {Object} payload - { question, user_answer, correct_answer, question_type }
 * @returns {Promise<{is_correct: boolean, confidence: number, feedback: string}>}
 */
export function checkAnswer(payload) {
  return request('/api/check-answer', {
    method: 'POST',
    data: payload,
    auth: false,
    timeout: 30000, // LLM 调用可能较慢
  })
}

// ==================== 学情诊断 ====================

/** 诊断目录：年级 / 册 / 章 / 知识点。 */
export function getDiagnosisCatalog() {
  return request('/api/diagnose/catalog', { timeout: 20000 })
}

export function startDiagnosis(payload) {
  return request('/api/diagnose/quiz', {
    method: 'POST',
    data: { action: 'start', ...payload },
    auth: true, // 已登录时绑定用户；游客不带令牌也能用
    timeout: 30000,
  })
}

export function answerDiagnosis(payload) {
  return request('/api/diagnose/quiz', {
    method: 'POST',
    data: { action: 'answer', ...payload },
    auth: true,
    timeout: 30000,
  })
}

export function abortDiagnosis(sessionId) {
  return request('/api/diagnose/quiz', {
    method: 'POST',
    data: { action: 'abort', session_id: sessionId },
    auth: true,
    timeout: 15000,
  })
}

// ==================== 持续学习：结果 / 错题 / 图谱 / 趋势 ====================

/** 最近一次完成的诊断（需登录）；没有时返回 null（HTTP 204）。 */
export function getLatestDiagnosisSession() {
  return request('/api/diagnose/sessions/latest', {
    auth: true,
    timeout: 15000,
  }).then((data) => data || null)
}

export function listDiagnosisSessions({ limit = 20, cursor = null, grade = null } = {}) {
  return request(`/api/diagnose/sessions${queryString({ limit, cursor, grade })}`, {
    auth: true,
    timeout: 20000,
  })
}

/** 单次结果；游客凭本地保存的 session_id 也能读取。 */
export function getDiagnosisSession(sessionId) {
  return request(
    `/api/diagnose/sessions/${encodeURIComponent(sessionId)}`,
    { auth: true, timeout: 20000 }
  )
}

export function listWrongQuestions({
  grade = null,
  chapter = null,
  node_key = null,
  status = 'open',
  days = null,
  limit = 20,
  cursor = null,
} = {}) {
  return request(
    `/api/diagnose/wrong-questions${queryString({
      grade,
      chapter,
      node_key,
      status,
      days,
      limit,
      cursor,
    })}`,
    { auth: true, timeout: 20000 }
  )
}

export function markWrongQuestion(attemptId, status) {
  return request(
    `/api/diagnose/wrong-questions/${encodeURIComponent(attemptId)}/mark`,
    { method: 'POST', data: { status }, auth: true, timeout: 15000 }
  )
}

/** 错题知识图谱；node_keys 可为数组或逗号分隔字符串。 */
export function getDiagnosisGraph({ session_id = null, node_keys = null, depth = 2 } = {}) {
  const keys = Array.isArray(node_keys)
    ? node_keys.filter(Boolean).join(',')
    : node_keys
  return request(
    `/api/diagnose/graph${queryString({ session_id, node_keys: keys, depth })}`,
    { auth: true, timeout: 20000 }
  )
}

export function getDiagnosisTrends({ grade = null, limit = 10 } = {}) {
  return request(`/api/diagnose/trends${queryString({ grade, limit })}`, {
    auth: true,
    timeout: 20000,
  })
}

/**
 * 首页「今日建议」：错题 + 趋势 + 聊天知识点，年级只做排序权重。
 * @returns {Promise<{ grade, generated_at, items: Array, reason }>}
 */
export function getTodayRecommendations({ limit = 3 } = {}) {
  return request(`/api/recommendations/today${queryString({ limit })}`, {
    auth: true,
    timeout: 20000,
  })
}

// ==================== 自律事项：AI 整理 ====================

/**
 * 把一句自然语言整理成结构化事项。
 * 必须登录；失败时抛出 ApiError，由页面决定如何提示/回退。
 */
export function parseSelfDisciplineItems({
  text,
  today = null,
  weekday = null,
  now = null,
  timezone = null,
  clientRequestId = null,
} = {}) {
  return request('/api/selfdiscipline/parse-items', {
    method: 'POST',
    auth: true,
    timeout: 20000,
    data: {
      text,
      today,
      weekday,
      now,
      timezone,
      client_request_id: clientRequestId,
    },
  })
}