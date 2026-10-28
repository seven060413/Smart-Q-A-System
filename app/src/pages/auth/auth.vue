<template>
  <view class="page">
    <!-- 已登录：账号信息 + 退出 -->
    <view v-if="loggedIn" class="card account-card">
      <view class="avatar">👤</view>
      <text class="display-name">{{ store.auth.user.display_name || store.auth.user.username }}</text>
      <text class="username">@{{ store.auth.user.username }}</text>

      <view class="info-list">
        <view class="info-row">
          <text class="label">角色</text>
          <text class="value">{{ roleLabel }}</text>
        </view>
        <view class="info-row">
          <text class="label">登录有效期至</text>
          <text class="value">{{ formatTime(store.auth.expiresAt) }}</text>
        </view>
      </view>

      <view v-if="error" class="error">{{ error }}</view>

      <button class="primary" @click="goBack">返回问答</button>
      <button class="ghost history-btn" @click="goHistory">历史会话</button>
      <button class="ghost" :disabled="loading" @click="doLogout">
        {{ loading ? '退出中…' : '退出登录' }}
      </button>
    </view>

    <!-- 未登录：登录 / 注册 -->
    <view v-else class="card">
      <view class="tabs">
        <view class="tab" :class="{ active: mode === 'login' }" @click="switchMode('login')">登录</view>
        <view class="tab" :class="{ active: mode === 'register' }" @click="switchMode('register')">注册</view>
      </view>

      <view class="form">
        <input
          class="input"
          v-model="form.username"
          placeholder="用户名（3-32 位字母/数字/下划线）"
          :maxlength="32"
        />
        <input
          v-if="mode === 'register'"
          class="input"
          v-model="form.displayName"
          placeholder="昵称（可选，默认等于用户名）"
          :maxlength="32"
        />
        <input
          class="input"
          v-model="form.password"
          :password="true"
          placeholder="密码（至少 8 位）"
          :maxlength="128"
        />
        <input
          v-if="mode === 'register'"
          class="input"
          v-model="form.confirm"
          :password="true"
          placeholder="再次输入密码"
          :maxlength="128"
        />

        <view v-if="error" class="error">{{ error }}</view>

        <button class="primary" :disabled="loading" @click="submit">
          {{ loading ? (mode === 'login' ? '登录中…' : '注册中…') : (mode === 'login' ? '登录' : '注册并登录') }}
        </button>

        <text class="hint">游客也可以直接问答；登录用于保存账号状态，聊天记录功能将在后续阶段接入。</text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { store } from '../../store.js'
import { login, logout, register } from '../../auth.js'

const mode = ref('login')
const loading = ref(false)
const error = ref('')
const form = reactive({
  username: '',
  password: '',
  confirm: '',
  displayName: '',
})

const loggedIn = computed(() => !!(store.auth.user && store.auth.token))
const roleLabel = computed(() => {
  const role = store.auth.user && store.auth.user.role
  if (role === 'teacher') return '老师'
  if (role === 'admin') return '管理员'
  return '学生'
})

function switchMode(next) {
  if (loading.value) return
  mode.value = next
  error.value = ''
  form.password = ''
  form.confirm = ''
}

function validate() {
  const username = form.username.trim()
  const password = form.password

  if (!/^[A-Za-z0-9_]{3,32}$/.test(username)) {
    error.value = '用户名需为 3-32 位字母、数字或下划线'
    return false
  }

  if (mode.value === 'login') {
    if (!password) {
      error.value = '请输入密码'
      return false
    }
    return true
  }

  if (password.length < 8 || password.length > 128) {
    error.value = '密码长度需为 8-128 位'
    return false
  }
  if (!password.trim()) {
    error.value = '密码不能全为空白字符'
    return false
  }
  if (password !== form.confirm) {
    error.value = '两次输入的密码不一致'
    return false
  }
  if (form.displayName && form.displayName.trim().length > 32) {
    error.value = '昵称不能超过 32 个字符'
    return false
  }
  return true
}

function messageFor(err) {
  if (!err) return '操作失败，请稍后重试'
  switch (err.code) {
    case 'USERNAME_TAKEN':
      return '用户名已被使用，请换一个'
    case 'INVALID_CREDENTIALS':
      return '用户名或密码错误'
    case 'ACCOUNT_DISABLED':
      return '账号已被禁用'
    case 'RATE_LIMITED':
      return '操作过于频繁，请稍后再试'
    case 'VALIDATION_ERROR':
      return (err.details && err.details[0] && err.details[0].msg) || '请检查输入内容'
    case 'NETWORK_ERROR':
      return '网络连接失败，请检查网络或后端服务地址'
    default:
      return err.message || '操作失败，请稍后重试'
  }
}

async function submit() {
  if (loading.value) return
  error.value = ''
  if (!validate()) return

  loading.value = true
  try {
    const payload = {
      username: form.username.trim(),
      password: form.password,
    }
    if (mode.value === 'register') {
      const displayName = form.displayName.trim()
      if (displayName) {
        payload.display_name = displayName
      }
      await register(payload)
    } else {
      await login(payload)
    }

    // 成功后立刻清掉页面里的密码，避免停留在内存/输入框里。
    form.password = ''
    form.confirm = ''
    uni.showToast({
      title: mode.value === 'login' ? '登录成功' : '注册成功',
      icon: 'success',
    })
    setTimeout(goBack, 400)
  } catch (e) {
    error.value = messageFor(e)
  } finally {
    loading.value = false
  }
}

function doLogout() {
  if (loading.value) return
  uni.showModal({
    title: '退出登录',
    content: '确定退出当前账号吗？',
    success: async (res) => {
      if (!res.confirm) return
      loading.value = true
      error.value = ''
      try {
        await logout()
        uni.showToast({ title: '已退出', icon: 'success' })
      } finally {
        loading.value = false
      }
    },
  })
}

function goBack() {
  const pages = typeof getCurrentPages === 'function' ? getCurrentPages() : []
  if (pages.length > 1) {
    uni.navigateBack()
  } else {
    uni.reLaunch({ url: '/pages/index/index' })
  }
}

function goHistory() {
  uni.navigateTo({ url: '/pages/history/history' })
}

function formatTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString()
}
</script>

<style>
.page {
  min-height: 100vh;
  padding: 48rpx 32rpx calc(48rpx + env(safe-area-inset-bottom));
  box-sizing: border-box;
  background: #f5f6f8;
}

.card {
  background: #fff;
  border-radius: 24rpx;
  padding: 40rpx 32rpx;
  box-shadow: 0 8rpx 28rpx rgba(0, 0, 0, 0.06);
}

/* 登录 / 注册切换 */
.tabs {
  display: flex;
  border-bottom: 1rpx solid #eee;
  margin-bottom: 32rpx;
}
.tab {
  flex: 1;
  text-align: center;
  padding: 20rpx 0;
  font-size: 30rpx;
  color: #888;
  border-bottom: 4rpx solid transparent;
}
.tab.active {
  color: #2b6cb0;
  font-weight: 600;
  border-bottom-color: #2b6cb0;
}

/* 表单 */
.form {
  display: flex;
  flex-direction: column;
}
.input {
  height: 88rpx;
  background: #f2f3f5;
  border-radius: 16rpx;
  padding: 0 24rpx;
  font-size: 28rpx;
  margin-bottom: 20rpx;
}
.primary {
  margin-top: 12rpx;
  height: 88rpx;
  line-height: 88rpx;
  background: #2b6cb0;
  color: #fff;
  font-size: 30rpx;
  border-radius: 44rpx;
  border: none;
}
.primary[disabled] {
  background: #b0c4de;
}
.primary::after,
.ghost::after {
  border: none;
}
.ghost {
  margin-top: 20rpx;
  height: 84rpx;
  line-height: 84rpx;
  background: #fff;
  color: #e53e3e;
  font-size: 28rpx;
  border-radius: 42rpx;
  border: 1rpx solid #feb2b2;
}
.ghost[disabled] {
  color: #bbb;
  border-color: #eee;
}
.ghost.history-btn {
  color: #2b6cb0;
  border-color: #bcd3f0;
}

.error {
  background: #fff5f5;
  border: 1rpx solid #feb2b2;
  color: #c53030;
  font-size: 26rpx;
  line-height: 1.5;
  padding: 18rpx 20rpx;
  border-radius: 12rpx;
  margin-bottom: 20rpx;
}

.hint {
  margin-top: 24rpx;
  font-size: 24rpx;
  color: #999;
  line-height: 1.6;
  text-align: center;
}

/* 已登录账号卡片 */
.account-card {
  display: flex;
  flex-direction: column;
  align-items: center;
}
.avatar {
  width: 120rpx;
  height: 120rpx;
  border-radius: 50%;
  background: #e8f0fb;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 56rpx;
}
.display-name {
  margin-top: 20rpx;
  font-size: 36rpx;
  font-weight: 700;
  color: #2b6cb0;
}
.username {
  margin-top: 8rpx;
  font-size: 24rpx;
  color: #999;
}
.info-list {
  width: 100%;
  margin: 32rpx 0 16rpx;
  border-top: 1rpx solid #f0f0f0;
}
.info-row {
  display: flex;
  justify-content: space-between;
  padding: 20rpx 0;
  border-bottom: 1rpx solid #f0f0f0;
  font-size: 26rpx;
}
.info-row .label {
  color: #888;
}
.info-row .value {
  color: #333;
}
</style>
