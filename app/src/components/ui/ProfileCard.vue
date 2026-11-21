<template>
  <view class="profile-card">
    <image v-if="avatar" class="avatar-img" :src="avatar" mode="aspectFill" />
    <view v-else class="avatar-fallback">{{ initial }}</view>

    <view class="profile-meta">
      <view class="profile-name-row">
        <text class="profile-name">{{ name }}</text>
        <text v-if="badge" class="profile-badge" :class="{ muted: badgeMuted }">
          {{ badge }}
        </text>
      </view>
      <text class="profile-sub">{{ subtitle }}</text>
    </view>

    <view class="profile-action" @click="$emit('action')">
      {{ actionText }}
    </view>
  </view>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  avatar: { type: String, default: '' },
  name: { type: String, default: '未登录' },
  subtitle: { type: String, default: '游客模式' },
  actionText: { type: String, default: '登录' },
  // 名字右侧的年级徽章；为空时不渲染。
  badge: { type: String, default: '' },
  badgeMuted: { type: Boolean, default: false },
})

defineEmits(['action'])

const initial = computed(() => {
  const n = (props.name || '我').trim()
  return n ? n.slice(0, 1).toUpperCase() : '我'
})
</script>

<style>
.profile-card {
  display: flex;
  align-items: center;
  background: var(--ik-card);
  border-radius: var(--ik-radius);
  padding: 32rpx 28rpx;
  margin-bottom: 24rpx;
  box-sizing: border-box;
}
.avatar-img,
.avatar-fallback {
  width: 128rpx;
  height: 128rpx;
  border-radius: 50%;
  flex: 0 0 auto;
}
.avatar-img {
  background: var(--ik-soft);
}
.avatar-fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--ik-primary-weak);
  color: var(--ik-primary);
  font-size: 52rpx;
  font-weight: 700;
}
.profile-meta {
  flex: 1;
  min-width: 0;
  margin-left: 24rpx;
  display: flex;
  flex-direction: column;
}
.profile-name-row {
  display: flex;
  align-items: center;
  min-width: 0;
}
.profile-name {
  flex: 0 1 auto;
  min-width: 0;
  font-size: 36rpx;
  font-weight: 700;
  color: var(--ik-t1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.profile-badge {
  flex: 0 0 auto;
  margin-left: 12rpx;
  padding: 2rpx 12rpx;
  border-radius: 999rpx;
  background: var(--ik-primary-weak);
  color: var(--ik-primary);
  font-size: 20rpx;
  line-height: 1.6;
  white-space: nowrap;
}
.profile-badge.muted {
  background: var(--ik-soft);
  color: var(--ik-t3);
}
.profile-sub {
  margin-top: 8rpx;
  font-size: 24rpx;
  color: var(--ik-t3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.profile-action {
  flex: 0 0 auto;
  margin-left: 16rpx;
  padding: 12rpx 24rpx;
  border-radius: 999rpx;
  border: 1rpx solid var(--ik-primary);
  color: var(--ik-primary);
  font-size: 24rpx;
}
</style>
