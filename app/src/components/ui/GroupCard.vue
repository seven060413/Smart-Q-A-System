<template>
  <view class="group-card" :class="{ 'is-tiles': variant === 'tiles' }">
    <text v-if="title" class="group-title">{{ title }}</text>
    <view class="grid">
      <view
        v-for="(item, i) in items"
        :key="item.key || item.label + i"
        class="cell"
        :class="[
          { 'is-disabled': item.disabled },
          item.tone ? 'tone-' + item.tone : '',
        ]"
        :style="{ width: cellWidth }"
        @click="onTap(item)"
      >
        <template v-if="variant === 'tiles'">
          <view class="cell-icon-wrap">
            <wd-icon v-if="item.icon" :name="item.icon" size="40rpx" />
            <text v-if="hasTag(item)" class="cell-tag" :class="{ 'is-muted': item.tagMuted }">
              {{ item.tag }}
            </text>
          </view>
          <text class="cell-label">{{ item.label }}</text>
        </template>
        <template v-else>
          <wd-icon v-if="item.icon" :name="item.icon" size="34rpx" custom-class="cell-inline-icon" />
          <text class="cell-label">{{ item.label }}</text>
          <text v-if="item.tag" class="cell-tag">{{ item.tag }}</text>
        </template>
      </view>
    </view>
  </view>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  title: { type: String, default: '' },
  items: { type: Array, default: () => [] },
  cols: { type: Number, default: 2 },
  // grid：原先的横向文字格；tiles：图标 + 文字平铺（BiliLite 风格）
  variant: { type: String, default: 'grid' },
})

const cellWidth = computed(() => `calc(${100 / Math.max(1, props.cols)}% - 16rpx)`)

function hasTag(item) {
  return item.tag !== undefined && item.tag !== null && item.tag !== ''
}

function onTap(item) {
  if (item.disabled) return
  if (typeof item.action === 'function') item.action()
}
</script>

<style>
.group-card {
  background: var(--ik-card);
  border-radius: var(--ik-radius);
  padding: 28rpx;
  margin-bottom: 24rpx;
  box-sizing: border-box;
}
.group-title {
  display: block;
  font-size: 24rpx;
  font-weight: 600;
  color: var(--ik-t2);
  margin-bottom: 18rpx;
}
.grid {
  display: flex;
  flex-wrap: wrap;
  margin: -8rpx;
}
.cell {
  height: 76rpx;
  margin: 8rpx;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1rpx solid var(--ik-line);
  border-radius: var(--ik-radius);
  background: transparent;
}
.cell-label {
  font-size: 26rpx;
  color: var(--ik-t1);
}
.cell-tag {
  margin-left: 8rpx;
  font-size: 20rpx;
  color: var(--ik-t3);
}
.is-disabled {
  opacity: 0.5;
}

/* ---------- tiles：图标 + 文字平铺 ---------- */
.is-tiles .cell {
  height: auto;
  min-height: 154rpx;
  flex-direction: column;
  justify-content: flex-start;
  padding: 12rpx 0 8rpx;
  border: none;
  background: transparent;
}

.cell-icon-wrap {
  position: relative;
  width: 84rpx;
  height: 84rpx;
  border-radius: 26rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--ik-soft);
  margin-bottom: 10rpx;
}

.cell-inline-icon {
  margin-right: 8rpx;
}

.is-tiles .cell-label {
  font-size: 24rpx;
  line-height: 1.3;
  text-align: center;
  color: var(--ik-t1);
}

.is-tiles .cell-tag {
  position: absolute;
  top: -8rpx;
  right: -10rpx;
  min-width: 30rpx;
  height: 30rpx;
  line-height: 30rpx;
  padding: 0 8rpx;
  margin: 0;
  border-radius: 999rpx;
  background: var(--ik-danger);
  color: #fff;
  font-size: 18rpx;
  text-align: center;
  box-sizing: border-box;
}

.is-tiles .cell-tag.is-muted {
  background: var(--ik-line);
  color: var(--ik-t2);
}

/* 图标语义色（背景保持中性，深浅色主题都能用；label 单独固定为 t1） */
.cell.tone-blue { color: var(--ik-primary); }
.cell.tone-red { color: var(--ik-danger); }
.cell.tone-green { color: var(--ik-success); }
.cell.tone-orange { color: #d69e2e; }
.cell.tone-purple { color: #8b5cf6; }
.cell.tone-teal { color: #319795; }
</style>
