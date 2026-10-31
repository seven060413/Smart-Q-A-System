<template>
  <view class="page">
    <!-- 登录状态 -->
    <view class="card profile">
      <view class="avatar">{{ avatarText }}</view>
      <text class="name">{{ displayName }}</text>
      <text class="state">{{ stateText }}</text>
    </view>

    <!-- 入口：只跳转现有页面，不复制登录/历史逻辑 -->
    <view class="menu">
      <template v-if="loggedIn">
        <view class="menu-item" @click="goAuth">
          <text class="menu-label">账号信息</text>
          <text class="menu-arrow">›</text>
        </view>
        <view class="menu-item" @click="goHistory">
          <text class="menu-label">历史会话</text>
          <text class="menu-arrow">›</text>
        </view>
      </template>
      <view v-else class="menu-item" @click="goAuth">
        <text class="menu-label">登录 / 注册</text>
        <text class="menu-arrow">›</text>
      </view>
    </view>

    <text class="hint">
      {{ loggedIn
        ? '账号资料、退出登录和历史记录都在现有页面中操作。'
        : '游客也可以直接问答；登录后可保存账号状态和聊天记录。' }}
    </text>

    <AppTabBar :active="TAB_MY" />
  </view>
</template>

<script setup>
import { computed } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import AppTabBar from '../../components/AppTabBar.vue'
import { TAB_MY, hideNativeTabBar } from '../../tabbar.js'
import { store } from '../../store.js'

const loggedIn = computed(() => !!(store.auth.user && store.auth.token))

const displayName = computed(() => {
  if (!store.auth.ready) return '…'
  if (!loggedIn.value) return '未登录'
  return store.auth.user.display_name || store.auth.user.username
})

const stateText = computed(() => {
  if (!store.auth.ready) return '正在检查登录状态…'
  if (loggedIn.value) return '@' + store.auth.user.username
  return '游客模式'
})

const avatarText = computed(() => {
  if (!loggedIn.value) return '我'
  const name = displayName.value || ''
  return name.slice(0, 1).toUpperCase() || '我'
})

function goAuth() {
  uni.navigateTo({ url: '/pages/auth/auth' })
}

function goHistory() {
  uni.navigateTo({ url: '/pages/history/history' })
}

onLoad(() => {
  hideNativeTabBar()
})

onShow(() => {
  hideNativeTabBar()
})
</script>

<style>
.page {
  min-height: 100vh;
  padding: 32rpx;
  box-sizing: border-box;
  background: #f5f6f8;
}

/* H5 的导航栏和 tabBar 是固定定位，页面高度需扣除二者及底部安全区域 */
/* #ifdef H5 */
.page {
  min-height: calc(100vh - var(--window-top, 0px) - var(--window-bottom, 0px));
}
/* #endif */

.card {
  background: #fff;
  border-radius: 24rpx;
  box-shadow: 0 8rpx 28rpx rgba(0, 0, 0, 0.06);
}

.profile {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 48rpx 32rpx;
}

.avatar {
  width: 120rpx;
  height: 120rpx;
  border-radius: 50%;
  background: #e8f0fb;
  color: #2b6cb0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 48rpx;
  font-weight: 700;
}

.name {
  margin-top: 20rpx;
  font-size: 36rpx;
  font-weight: 700;
  color: #2b6cb0;
  text-align: center;
  word-break: break-all;
}

.state {
  margin-top: 8rpx;
  font-size: 24rpx;
  color: #999;
}

.menu {
  margin-top: 24rpx;
  background: #fff;
  border-radius: 24rpx;
  overflow: hidden;
  box-shadow: 0 8rpx 28rpx rgba(0, 0, 0, 0.06);
}

.menu-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 30rpx 28rpx;
  border-bottom: 1rpx solid #f0f0f0;
}

.menu-item:last-child {
  border-bottom: none;
}

.menu-label {
  font-size: 30rpx;
  color: #333;
}

.menu-arrow {
  font-size: 34rpx;
  color: #bbb;
}

.hint {
  display: block;
  margin-top: 28rpx;
  padding: 0 8rpx;
  font-size: 24rpx;
  color: #999;
  line-height: 1.6;
  text-align: center;
}
</style>
