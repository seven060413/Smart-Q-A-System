<template>
  <view class="persona-card">
    <EyeGaze :state="state" :progress="progress" :size="360" on-block />
    <text class="persona-line">{{ line }}</text>
    <text v-if="hint" class="persona-hint">{{ hint }}</text>
  </view>
</template>

<script setup>
import EyeGaze from './EyeGaze.vue'

defineProps({
  line: { type: String, default: '' },
  hint: { type: String, default: '' },
  state: { type: String, default: 'idle' },
  progress: { type: Number, default: 1 },
})
</script>

<!-- scoped 防止跨页面同名按钮样式互相覆盖 -->
<style scoped>
.persona-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  background: var(--ik-block);
  color: var(--ik-on-block);
  border-radius: var(--ik-radius);
  padding: 32rpx 28rpx 30rpx;
  margin-bottom: 24rpx;
  box-sizing: border-box;
}
.persona-line {
  margin-top: 20rpx;
  font-size: 30rpx;
  font-weight: 600;
  line-height: 1.5;
  color: var(--ik-on-block);
  text-align: center;
}
.persona-hint {
  margin-top: 8rpx;
  font-size: 24rpx;
  line-height: 1.5;
  color: var(--ik-on-block);
  opacity: 0.66;
  text-align: center;
}
</style>
