<template>
  <view class="trend-chart">
    <view class="trend-head">
      <text class="trend-unit">{{ unit }}</text>
      <text class="trend-max">峰值 {{ max }}</text>
    </view>

    <view class="trend-plot">
      <view v-for="(item, index) in data" :key="item.label + index" class="trend-col">
        <view class="trend-bar-track">
          <view
            class="trend-bar"
            :class="{ 'is-empty': !item.value }"
            :style="{ height: barHeight(item.value) }"
          ></view>
        </view>
        <text v-if="showLabel(index)" class="trend-label">{{ item.label }}</text>
        <text v-else class="trend-label"></text>
      </view>
    </view>

    <view v-if="!hasData" class="trend-empty">这段时间还没有数据</view>
  </view>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  // [{ label: '11/21', value: 25 }]
  data: { type: Array, default: () => [] },
  unit: { type: String, default: '分钟' },
  height: { type: Number, default: 200 }, // rpx 基准高度
})

const max = computed(() => {
  const values = props.data.map((item) => Number(item.value) || 0)
  return Math.max(1, ...values)
})

const hasData = computed(() => props.data.some((item) => Number(item.value) > 0))

const barHeight = (value) => {
  const v = Number(value) || 0
  if (v <= 0) return '2rpx'
  return `${Math.max(4, Math.round((v / max.value) * 100))}%`
}

const showLabel = (index) => {
  const total = props.data.length
  if (total <= 7) return true
  const step = Math.ceil(total / 6)
  return index % step === 0 || index === total - 1
}
</script>

<!-- scoped 防止跨页面同名按钮样式互相覆盖 -->
<style scoped>
.trend-chart {
  position: relative;
  width: 100%;
}
.trend-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12rpx;
}
.trend-unit {
  font-size: 22rpx;
  color: var(--ik-t3);
}
.trend-max {
  font-size: 22rpx;
  color: var(--ik-t3);
}
.trend-plot {
  display: flex;
  align-items: flex-end;
  height: 220rpx;
  padding-top: 8rpx;
  box-sizing: border-box;
  border-bottom: 1rpx solid var(--ik-line);
}
.trend-col {
  flex: 1;
  min-width: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  align-items: center;
}
.trend-bar-track {
  width: 100%;
  flex: 1;
  display: flex;
  align-items: flex-end;
  justify-content: center;
}
.trend-bar {
  width: 56%;
  max-width: 22rpx;
  min-width: 3px;
  border-radius: 6rpx 6rpx 0 0;
  background: var(--ik-primary);
  transition: height 0.25s ease;
}
.trend-bar.is-empty {
  background: var(--ik-line);
}
.trend-label {
  display: block;
  height: 30rpx;
  line-height: 30rpx;
  font-size: 18rpx;
  color: var(--ik-t3);
  white-space: nowrap;
  transform: scale(0.92);
}
.trend-empty {
  position: absolute;
  left: 0;
  right: 0;
  top: 96rpx;
  text-align: center;
  font-size: 24rpx;
  color: var(--ik-t3);
}
</style>
