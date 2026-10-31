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

    <!-- 会话列表 -->
    <scroll-view v-else class="list" scroll-y>
      <view
        v-for="item in items"
        :key="item.id"
        class="item"
        @click="openConversation(item)"
      >
        <view class="item-main">
          <text class="item-title">{{ item.title || '新对话' }}</text>
          <text class="item-meta">
            {{ formatTime(item.last_message_at) }} · {{ item.message_count || 0 }} 条消息
          </text>
        </view>
        <text class="delete" @click.stop="removeConversation(item)">删除</text>
      </view>

      <view v-if="hasMore" class="load-more" @click="loadMore">
        {{ loadingMore ? '加载中…' : '加载更多' }}
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

const loggedIn = computed(() => !!(store.auth.user && store.auth.token))

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
  // 首页是 tabBar 页面，switchTab 不支持参数；通过 store 传递一次。
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

// 冷启动时 initAuth 可能还没完成；恢复完成后再拉一次列表。
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

.list {
  flex: 1;
  padding: 24rpx;
  box-sizing: border-box;
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
