<template>
  <view class="page theme-root" :style="themeVars">
    <ThemeBackground />
    <view class="header">
      <view class="header-text">
        <text class="title">历史会话</text>
        <text class="subtitle">只显示当前账号的会话</text>
      </view>
      <view class="header-actions">
        <text v-if="loggedIn" class="link" @click="newConversation">新对话</text>
        <text class="link" @click="goHome">返回问答</text>
      </view>
    </view>

    <!-- 搜索框 -->
    <view class="search-container">
      <view class="search-box">
        <view class="search-icon-css"></view>
        <input 
          class="search-input" 
          v-model="keyword" 
          placeholder="搜索" 
          placeholder-class="search-placeholder"
          confirm-type="search"
        />
        <text v-if="keyword" class="clear-icon" @click="keyword = ''">✕</text>
      </view>
    </view>

    <!-- 未登录 -->
    <view v-if="!loggedIn" class="empty">
      <text class="empty-title">登录后查看历史会话</text>
      <text class="empty-text">游客问答不会保存记录。</text>
      <button class="primary" @click="goAuth">去登录</button>
    </view>

    <!-- 首次加载 -->
    <view v-else-if="loading && items.length === 0" class="empty">
      <text class="empty-text">正在加载…</text>
    </view>

    <!-- 空列表 -->
    <view v-else-if="items.length === 0" class="empty">
      <text class="empty-title">还没有历史会话</text>
      <text class="empty-text">登录状态下在问答页提问后，会自动保存到这里。</text>
      <button class="primary" @click="goHome">去提问</button>
    </view>

    <!-- 列表 -->
    <scroll-view v-else class="list" scroll-y>
      <!-- 搜索无结果 -->
      <view v-if="groupedItems.length === 0 && keyword" class="empty-search">
        没有找到包含“{{ keyword }}”的会话
      </view>

      <!-- 分组/平铺渲染 -->
      <view v-else>
        <!-- 搜索状态提示 -->
        <view v-if="keyword" class="search-result-tip">
          找到 {{ searchTotal }} 个相关会话
        </view>

        <view v-for="group in groupedItems" :key="group.name" class="group-section">
          <!-- 如果是搜索状态，就不显示分组标题了 -->
          <view v-if="!keyword" class="group-title">{{ group.name }}</view>
          
          <view
  v-for="item in group.items"
  :key="item.id"
  class="conversation-entry"
>
  <!-- 会话卡片 -->
  <view class="item" @click="openConversation(item)">

    <!-- 左侧展开箭头 -->
   <view class="expand-toggle" @click.stop="toggleExpand(item)">
  <text class="arrow">
    {{ expandedIds.includes(item.id) ? '▾' : '▸' }}
  </text>
</view>

    <!-- 会话标题和时间 -->
    <view class="item-main">
      <text class="item-title">
        <text
          v-for="(chunk, index) in highlightText(item.title || '新对话', keyword)"
          :key="index"
          :class="{ 'highlight-text': chunk.isMatch }"
        >{{ chunk.text }}</text>
      </text>

      <text class="item-meta">
        {{ formatTime(item.last_message_at) }} · {{ item.message_count || 0 }} 条消息
      </text>
    </view>

    <!-- 删除 -->
    <text class="delete" @click.stop="removeConversation(item)">
      删除
    </text>
  </view>

  <!-- 展开的问题列表 -->
  <view
    v-if="expandedIds.includes(item.id)"
    class="question-list"
  >
    <view
      v-if="loadingQuestions[item.id]"
      class="question-loading"
    >
      正在加载问题…
    </view>

    <view
      v-else-if="conversationQuestions[item.id] && conversationQuestions[item.id].length"
      class="question-list-inner"
    >
      <view
        v-for="(question, qIndex) in conversationQuestions[item.id]"
        :key="question.id"
        class="question-item"
        @click.stop="openQuestion(item, question)"
      >
        <text class="question-number">{{ qIndex + 1 }}.</text>
        <MathText class="question-content" :text="question.content" />
        <text class="question-arrow">›</text>
      </view>
    </view>

    <view
      v-else-if="conversationQuestions[item.id]"
      class="question-loading"
    >
      这个会话还没有问题
    </view>
  </view>
</view>
        </view>

        <view v-if="hasMore" class="load-more" @click="loadMore">
          {{ loadingMore ? '加载中…' : '加载更多' }}
        </view>
      </view>
    </scroll-view>
  </view>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import {
  deleteConversation,
  listConversations,
  listMessages
} from '../../api.js'
import { store } from '../../store.js'
import { themeVars, applyNativeNavigationBar } from '../../theme/theme.js'
import MathText from '../../components/ui/MathText.vue'

const items = ref([])
const cursor = ref('')
const hasMore = ref(false)
const loading = ref(false)
const loadingMore = ref(false)
const keyword = ref('') 
// 已展开的会话 ID
const expandedIds = ref([])

// 各会话的问题列表缓存
const conversationQuestions = ref({})

// 正在加载问题列表的会话
const loadingQuestions = ref({})

const loggedIn = computed(() => !!(store.auth.user && store.auth.token))

// 计算搜索到的总数量
const searchTotal = computed(() => {
  const searchStr = keyword.value.trim().toLowerCase()
  if (!searchStr) return 0
  return items.value.filter(item => (item.title || '').toLowerCase().includes(searchStr)).length
})

const groupedItems = computed(() => {
  if (!items.value.length) return []

  // 1. 搜索过滤
  const searchStr = keyword.value.trim().toLowerCase()
  let filteredItems = items.value
  if (searchStr) {
    filteredItems = items.value.filter(item => {
      const title = (item.title || '').toLowerCase()
      return title.includes(searchStr)
    })
  }

  if (!filteredItems.length) return []

  // 2. 如果有搜索词，就不再按时间分组，直接平铺展示！
  if (searchStr) {
    return [{ name: '搜索结果', items: filteredItems }]
  }

  // 3. 按时间分组（无搜索词时）
  const groups = {}
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const todayTime = today.getTime()
  const oneDay = 24 * 60 * 60 * 1000

  filteredItems.forEach(item => {
    const dateStr = item.last_message_at
    if (!dateStr) return
    
    const d = new Date(dateStr)
    const itemTime = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
    const diffDays = Math.floor((todayTime - itemTime) / oneDay)

    let groupName = ''
    if (diffDays <= 0) {
      groupName = '今天'
    } else if (diffDays === 1) {
      groupName = '昨天'
    } else if (diffDays <= 3) {
      groupName = '三天内'
    } else if (diffDays <= 7) {
      groupName = '七天内'
    } else if (diffDays <= 30) {
      groupName = '30天内'
    } else {
      groupName = `${d.getFullYear()}年${d.getMonth() + 1}月`
    }

    if (!groups[groupName]) {
      groups[groupName] = []
    }
    groups[groupName].push(item)
  })

  return Object.keys(groups).map(key => ({
    name: key,
    items: groups[key]
  }))
})

// 将字符串切割成数组，用于高亮匹配
function highlightText(text, search) {
  if (!search || !text) return [{ text, isMatch: false }]
  
  // 转义正则特殊字符
  const safeSearch = search.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const regex = new RegExp(`(${safeSearch})`, 'gi')
  const parts = text.split(regex)
  
  return parts.map(part => ({
    text: part,
    // 判断当前碎片是否是搜索词（忽略大小写）
    isMatch: part.toLowerCase() === search.toLowerCase()
  }))
}

async function loadFirstPage() {
  if (!loggedIn.value) {
    items.value = []
    cursor.value = ''
    hasMore.value = false
    return
  }
  loading.value = true
  try {
    const page = await listConversations({ limit: 20 })
    items.value = page.items || []
    cursor.value = page.next_cursor || ''
    hasMore.value = !!page.has_more
  } catch (e) {
    if (e && e.status === 401) {
      items.value = []
      uni.showToast({ title: '登录已过期，请重新登录', icon: 'none' })
    } else {
      uni.showToast({ title: (e && e.message) || '加载历史失败', icon: 'none' })
    }
  } finally {
    loading.value = false
  }
}

async function loadMore() {
  if (!hasMore.value || loadingMore.value || !cursor.value) return
  loadingMore.value = true
  try {
    const page = await listConversations({ limit: 20, cursor: cursor.value })
    items.value = items.value.concat(page.items || [])
    cursor.value = page.next_cursor || ''
    hasMore.value = !!page.has_more
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '加载更多失败', icon: 'none' })
  } finally {
    loadingMore.value = false
  }
}

function openConversation(item) {
  store.pendingIndexAction = { type: 'open', conversationId: item.id }
  uni.reLaunch({ url: '/pages/index/index?tab=0' })
}

// 展开或收起某个会话的问题列表
async function toggleExpand(item) {
  const id = item.id

  // 如果已经展开，就收起
  if (expandedIds.value.includes(id)) {
    expandedIds.value = expandedIds.value.filter(x => x !== id)
    return
  }

  // 展开
  expandedIds.value = [...expandedIds.value, id]

  // 已经加载过就不重复请求
  if (conversationQuestions.value[id]) return

  loadingQuestions.value = {
    ...loadingQuestions.value,
    [id]: true
  }

  try {
    let allMessages = []
    let nextCursor = null
    let hasMoreMessages = true

    // 分页获取该会话的全部消息
    while (hasMoreMessages) {
      const page = await listMessages(id, {
        limit: 50,
        cursor: nextCursor
      })

      allMessages = allMessages.concat(page.items || [])
      nextCursor = page.next_cursor || null
      hasMoreMessages = !!page.has_more

      // 防止异常分页数据造成无限循环
      if (hasMoreMessages && !nextCursor) {
        break
      }
    }

    // 只保留用户提出的问题
    const questions = allMessages
      .filter(message => message.role === 'user')
      .map(message => ({
        id: message.id,
        content:
          message.content ||
          (message.attachment && (
            message.attachment.question_text ||
            message.attachment.original_name ||
            message.attachment.name
          )) ||
          '附件题目'
      }))

    conversationQuestions.value = {
      ...conversationQuestions.value,
      [id]: questions
    }
  } catch (e) {
    uni.showToast({
      title: (e && e.message) || '加载问题列表失败',
      icon: 'none'
    })

    // 加载失败时允许再次展开重试
    expandedIds.value = expandedIds.value.filter(x => x !== id)
  } finally {
    loadingQuestions.value = {
      ...loadingQuestions.value,
      [id]: false
    }
  }
}

// 点击某个问题，跳转到问答页并传递消息 ID
function openQuestion(item, question) {
  store.pendingIndexAction = {
    type: 'open',
    conversationId: item.id,
    messageId: question.id
  }

  uni.reLaunch({
    url: '/pages/index/index?tab=0'
  })
}

function newConversation() {
  store.pendingIndexAction = { type: 'new' }
  uni.reLaunch({ url: '/pages/index/index?tab=0' })
}

function goHome() {
  store.pendingIndexAction = { type: 'home' }
  uni.reLaunch({ url: '/pages/index/index?tab=0' })
}

function goAuth() {
  uni.navigateTo({ url: '/pages/auth/auth' })
}

function removeConversation(item) {
  uni.showModal({
    title: '删除会话',
    content: '删除后不会再出现在历史列表里，确定吗？',
    success: async (res) => {
      if (!res.confirm) return
      try {
        await deleteConversation(item.id)
        items.value = items.value.filter((x) => x.id !== item.id)
        uni.showToast({ title: '已删除', icon: 'success' })
      } catch (e) {
        if (e && e.status === 404) {
          items.value = items.value.filter((x) => x.id !== item.id)
        } else if (e && e.status === 401) {
          uni.showToast({ title: '登录已过期，请重新登录', icon: 'none' })
        } else {
          uni.showToast({ title: (e && e.message) || '删除失败', icon: 'none' })
        }
      }
    },
  })
}

function formatTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString()
}

onShow(() => {
  applyNativeNavigationBar()
  loadFirstPage()
})

watch(
  () => store.auth.ready,
  (ready) => {
    if (ready) loadFirstPage()
  }
)
</script>

<style>
.page {
  min-height: 100vh;
  background: var(--ik-bg);
  display: flex;
  flex-direction: column;
}

.header {
  background: var(--ik-card);
  padding: 28rpx 30rpx;
  border-bottom: 1rpx solid var(--ik-line);
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}
.header-text {
  display: flex;
  flex-direction: column;
}
.title {
  font-size: 36rpx;
  font-weight: 700;
  color: var(--ik-primary);
}
.subtitle {
  margin-top: 8rpx;
  font-size: 24rpx;
  color: var(--ik-t3);
}
.header-actions {
  display: flex;
  gap: 24rpx;
  flex-shrink: 0;
}
.link {
  font-size: 24rpx;
  color: var(--ik-primary);
}

/* 搜索框样式 */
.search-container {
  padding: 24rpx 30rpx 0 30rpx;
}
.search-box {
  display: flex;
  align-items: center;
  background: var(--ik-soft); 
  border-radius: 40rpx; 
  padding: 20rpx 28rpx;
  border: none; 
}
.search-input {
  flex: 1;
  font-size: 30rpx;
  color: var(--ik-t1);
  background: transparent; 
  border: none;
  outline: none;
}
.search-placeholder {
  color: var(--ik-t3);
}
.search-icon-css {
  width: 24rpx;
  height: 24rpx;
  border: 4rpx solid var(--ik-t3);
  border-radius: 50%;
  position: relative;
  margin-right: 16rpx;
}
.search-icon-css::after {
  content: '';
  position: absolute;
  width: 4rpx;
  height: 14rpx;
  background: var(--ik-t3);
  bottom: -10rpx;
  right: -4rpx;
  transform: rotate(-45deg);
}
.clear-icon {
  color: var(--ik-t3);
  font-size: 28rpx;
  padding: 0 10rpx;
  cursor: pointer;
}

/* 搜索结果提示 */
.search-result-tip {
  font-size: 24rpx;
  color: var(--ik-t3);
  padding: 20rpx 8rpx 10rpx 8rpx;
}

.list {
  flex: 1;
  padding: 24rpx;
  box-sizing: border-box;
}

.group-section {
  margin-bottom: 32rpx;
}
.group-title {
  font-size: 26rpx;
  color: var(--ik-t2);
  font-weight: 500;
  margin-bottom: 16rpx;
  padding-left: 8rpx;
}

.item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--ik-card);
  border-radius: 20rpx;
  padding: 26rpx 24rpx;
  margin-bottom: 18rpx;
  box-shadow: 0 2rpx 10rpx rgba(0, 0, 0, 0.04);
}
.item-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
  align-items: flex-start;
  text-align: left;
}
.item-title {
  font-size: 30rpx;
  color: var(--ik-t1);
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: left;
}

/* 会话卡片及展开内容 */
.conversation-entry {
  margin-bottom: 18rpx;
}

.conversation-entry .item {
  margin-bottom: 0;
}

/* 左侧展开箭头 */
.expand-toggle {
  width: 48rpx;
  height: 64rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.question-list {
  margin: 12rpx 16rpx 0;
  padding: 12rpx 20rpx;
  background: var(--ik-card);
  border-radius: 16rpx;
  box-shadow: 0 2rpx 10rpx rgba(0, 0, 0, 0.04);
}

.question-item {
  display: flex;
  align-items: center;
  padding: 18rpx 8rpx;
  border-bottom: 1rpx solid var(--ik-line);
}

.question-item:last-child {
  border-bottom: none;
}

.question-number {
  color: var(--ik-t3);
  font-size: 22rpx;
  margin-right: 12rpx;
  flex-shrink: 0;
}

.question-content {
  flex: 1;
  min-width: 0;
  font-size: 26rpx;
  color: var(--ik-t2);
  line-height: 1.5;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.question-arrow {
  color: var(--ik-t3);
  font-size: 28rpx;
  margin-left: 12rpx;
}

.arrow {
  font-size: 26rpx;
  color: var(--ik-t3);
  line-height: 1;
}

.question-loading {
  padding: 24rpx 0;
  color: var(--ik-t3);
  font-size: 24rpx;
  text-align: center;
}

/* 匹配关键字高亮样式 */
.highlight-text {
  color: var(--ik-primary); /* 蓝色高亮 */
  font-weight: bold;
}

.item-meta {
  margin-top: 10rpx;
  font-size: 24rpx;
  color: var(--ik-t3);
  text-align: left;
}

.delete {
  margin-left: 20rpx;
  font-size: 24rpx;
  color: var(--ik-danger);
  flex-shrink: 0;
}

.load-more {
  text-align: center;
  font-size: 26rpx;
  color: var(--ik-primary);
  padding: 24rpx 0 40rpx;
}

.empty-search {
  text-align: center;
  color: var(--ik-t3);
  font-size: 28rpx;
  padding: 60rpx 0;
}

.empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60rpx 48rpx;
  text-align: center;
}
.empty-title {
  font-size: 32rpx;
  font-weight: 600;
  color: var(--ik-t2);
}
.empty-text {
  margin-top: 16rpx;
  font-size: 26rpx;
  color: var(--ik-t3);
  line-height: 1.6;
}
.primary {
  margin-top: 36rpx;
  height: 84rpx;
  line-height: 84rpx;
  padding: 0 60rpx;
  background: var(--ik-primary);
  color: var(--ik-on-primary);
  font-size: 28rpx;
  border-radius: 42rpx;
  border: none;
}
.primary::after {
  border: none;
}
</style>