import { reactive } from 'vue'

// 跨页面共享数据（首页拿到答案后，学习路径页从这里读）
export const store = reactive({
  learningPath: null, // { prerequisites: [], body: '', consolidation: [] }
  knowledgePoint: '',
  source: '',
  // 当前正在查看/继续的会话 id；为空表示下一次提问时由后端自动新建。
  currentConversationId: '',

  // 登录状态：token/user 只来自后端响应；ready 表示是否已完成启动校验。
  auth: {
    token: '',
    user: null,
    expiresAt: '',
    ready: false,
  },
})

export function setAuthState(token, user, expiresAt) {
  store.auth.token = token || ''
  store.auth.user = user || null
  store.auth.expiresAt = expiresAt || ''
  store.auth.ready = true
}

export function resetAuth() {
  store.auth.token = ''
  store.auth.user = null
  store.auth.expiresAt = ''
  // 退出/401 后不再继续写入上一位学生的会话。
  store.currentConversationId = ''
}
