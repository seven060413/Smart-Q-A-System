<template>
  <view class="stat-tile">
    <view class="stat-value-row">
      <text class="stat-value" :class="`tone-${tone}`">{{ value }}</text>
      <text v-if="unit" class="stat-unit">{{ unit }}</text>
    </view>
    <text class="stat-label">{{ label }}</text>
    <text v-if="hint" class="stat-hint">{{ hint }}</text>
  </view>
</template>

<script setup>
defineProps({
  label: { type: String, default: '' },
  value: { type: [String, Number], default: '0' },
  unit: { type: String, default: '' },
  hint: { type: String, default: '' },
  tone: { type: String, default: 'default' }, // default | primary | success | danger
})
</script>

<!-- scoped 防止跨页面同名按钮样式互相覆盖 -->
<style scoped>
.stat-tile {
  flex: 1;
  min-width: 0;
  background: var(--ik-card);
  border-radius: var(--ik-radius);
  padding: 24rpx 20rpx;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
}
.stat-value-row {
  display: flex;
  align-items: baseline;
}
.stat-value {
  font-size: 44rpx;
  font-weight: 700;
  line-height: 1.1;
  color: var(--ik-t1);
}
.tone-primary {
  color: var(--ik-primary);
}
.tone-success {
  color: var(--ik-success);
}
.tone-danger {
  color: var(--ik-danger);
}
.stat-unit {
  margin-left: 6rpx;
  font-size: 22rpx;
  color: var(--ik-t3);
}
.stat-label {
  margin-top: 10rpx;
  font-size: 24rpx;
  color: var(--ik-t2);
}
.stat-hint {
  margin-top: 4rpx;
  font-size: 20rpx;
  color: var(--ik-t3);
}
</style>
