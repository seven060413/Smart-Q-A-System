<template>
  <view class="page">
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
            class="item"
            @click="openConversation(item)"
          >
            <view class="item-main">
              <!-- 核心：高亮显示匹配的文字 -->
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
            <text class="delete" @click.stop="removeConversation(item)">删除</text>
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
import { deleteConversation, listConversations } from '../../api.js'
import { store } from '../../store.js'

const items = ref([])
const cursor = ref('')
const hasMore = ref(false)
const loading = ref(false)
const loadingMore = ref(false)
const keyword = ref('') 

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
  uni.switchTab({ url: '/pages/index/index' })
}

function newConversation() {
  store.pendingIndexAction = { type: 'new' }
  uni.switchTab({ url: '/pages/index/index' })
}

function goHome() {
  store.pendingIndexAction = { type: 'home' }
  uni.switchTab({ url: '/pages/index/index' })
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
  background: #f5f6f8;
  display: flex;
  flex-direction: column;
}

.header {
  background: #fff;
  padding: 28rpx 30rpx;
  border-bottom: 1rpx solid #eee;
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
  color: #2b6cb0;
}
.subtitle {
  margin-top: 8rpx;
  font-size: 24rpx;
  color: #999;
}
.header-actions {
  display: flex;
  gap: 24rpx;
  flex-shrink: 0;
}
.link {
  font-size: 24rpx;
  color: #2b6cb0;
}

/* 搜索框样式 */
.search-container {
  padding: 24rpx 30rpx 0 30rpx;
}
.search-box {
  display: flex;
  align-items: center;
  background: #eef0f4; 
  border-radius: 40rpx; 
  padding: 20rpx 28rpx;
  border: none; 
}
.search-input {
  flex: 1;
  font-size: 30rpx;
  color: #333;
  background: transparent; 
  border: none;
  outline: none;
}
.search-placeholder {
  color: #a0a5b0;
}
.search-icon-css {
  width: 24rpx;
  height: 24rpx;
  border: 4rpx solid #a0a5b0;
  border-radius: 50%;
  position: relative;
  margin-right: 16rpx;
}
.search-icon-css::after {
  content: '';
  position: absolute;
  width: 4rpx;
  height: 14rpx;
  background: #a0a5b0;
  bottom: -10rpx;
  right: -4rpx;
  transform: rotate(-45deg);
}
.clear-icon {
  color: #a0a5b0;
  font-size: 28rpx;
  padding: 0 10rpx;
  cursor: pointer;
}

/* 搜索结果提示 */
.search-result-tip {
  font-size: 24rpx;
  color: #999;
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
  color: #666;
  font-weight: 500;
  margin-bottom: 16rpx;
  padding-left: 8rpx;
}

.item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-radius: 20rpx;
  padding: 26rpx 24rpx;
  margin-bottom: 18rpx;
  box-shadow: 0 2rpx 10rpx rgba(0, 0, 0, 0.04);
}
.item-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.item-title {
  font-size: 30rpx;
  color: #333;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 匹配关键字高亮样式 */
.highlight-text {
  color: #2b6cb0; /* 蓝色高亮 */
  font-weight: bold;
}

.item-meta {
  margin-top: 10rpx;
  font-size: 24rpx;
  color: #999;
}
.delete {
  margin-left: 20rpx;
  font-size: 24rpx;
  color: #e53e3e;
  flex-shrink: 0;
}

.load-more {
  text-align: center;
  font-size: 26rpx;
  color: #2b6cb0;
  padding: 24rpx 0 40rpx;
}

.empty-search {
  text-align: center;
  color: #999;
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
  color: #444;
}
.empty-text {
  margin-top: 16rpx;
  font-size: 26rpx;
  color: #999;
  line-height: 1.6;
}
.primary {
  margin-top: 36rpx;
  height: 84rpx;
  line-height: 84rpx;
  padding: 0 60rpx;
  background: #2b6cb0;
  color: #fff;
  font-size: 28rpx;
  border-radius: 42rpx;
  border: none;
}
.primary::after {
  border: none;
}
</style>