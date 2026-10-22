<template>
  <view class="page">
    <!-- 顶部：知识点 + 出处 -->
    <view class="header">
      <text class="kp">{{ body }}</text>
      <text class="source">📚 {{ store.source || '人教版五年级下册' }}</text>
    </view>

    <scroll-view class="body" scroll-y>
      <!-- 前置层 -->
      <view class="layer">
        <text class="layer-title">📖 前置知识（先学）</text>
        <view class="nodes">
          <view v-for="(p, i) in prerequisites" :key="i" class="node node-pre">{{ p }}</view>
          <text v-if="!prerequisites.length" class="empty">无</text>
        </view>
      </view>

      <!-- 连接线 -->
      <view class="connector"></view>

      <!-- 本体层 -->
      <view class="layer">
        <view class="node node-body">🎯 {{ body }}</view>
        <text class="body-tag">本体</text>
      </view>

      <!-- 连接线 -->
      <view class="connector"></view>

      <!-- 巩固层 -->
      <view class="layer">
        <text class="layer-title">✏️ 巩固练习（后学）</text>
        <view class="nodes">
          <view v-for="(c, i) in consolidation" :key="i" class="node node-cons">{{ c }}</view>
          <text v-if="!consolidation.length" class="empty">无</text>
        </view>
      </view>
    </scroll-view>
  </view>
</template>

<script setup>
import { computed } from 'vue'
import { store } from '../../store.js'

const lp = computed(() => store.learningPath || { prerequisites: [], body: '', consolidation: [] })
const body = computed(() => lp.value.body || store.knowledgePoint)
const prerequisites = computed(() => lp.value.prerequisites || [])
const consolidation = computed(() => lp.value.consolidation || [])
</script>

<style>
.page {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f5f6f8;
}

.header {
  background: #fff;
  padding: 32rpx 30rpx;
  border-bottom: 1rpx solid #eee;
}
.kp {
  font-size: 36rpx;
  font-weight: 700;
  color: #2b6cb0;
  display: block;
}
.source {
  margin-top: 8rpx;
  font-size: 24rpx;
  color: #999;
  display: block;
}

.body {
  flex: 1;
  padding: 40rpx 30rpx;
  box-sizing: border-box;
}

.layer {
  text-align: center;
}
.layer-title {
  display: block;
  font-size: 26rpx;
  color: #888;
  margin-bottom: 20rpx;
}
.nodes {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 16rpx;
}
.node {
  padding: 18rpx 28rpx;
  border-radius: 16rpx;
  font-size: 28rpx;
  box-shadow: 0 2rpx 8rpx rgba(0, 0, 0, 0.06);
}
.node-pre {
  background: #e8f0fb;
  color: #2b6cb0;
  border: 1rpx solid #bcd3f0;
}
.node-body {
  display: inline-block;
  background: #2b6cb0;
  color: #fff;
  font-size: 32rpx;
  font-weight: 700;
  padding: 28rpx 48rpx;
  box-shadow: 0 6rpx 18rpx rgba(43, 108, 176, 0.35);
}
.node-cons {
  background: #e6fffa;
  color: #2c7a7b;
  border: 1rpx solid #b2f5ea;
}
.body-tag {
  display: block;
  margin-top: 12rpx;
  font-size: 22rpx;
  color: #2b6cb0;
}
.empty {
  font-size: 26rpx;
  color: #bbb;
}

/* 层与层之间的竖线 + 向下箭头 */
.connector {
  height: 70rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
.connector::before {
  content: '';
  width: 4rpx;
  height: 44rpx;
  background: #cbd5e0;
}
.connector::after {
  content: '';
  width: 0;
  height: 0;
  border-left: 12rpx solid transparent;
  border-right: 12rpx solid transparent;
  border-top: 16rpx solid #cbd5e0;
}
</style>
