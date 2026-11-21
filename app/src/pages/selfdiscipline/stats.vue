<template>
  <view class="stats-page theme-root" :class="{ 'is-dark': isDark }" :style="themeVars">
    <ThemeBackground />
    <scroll-view class="stats-scroll" scroll-y>
      <view class="stats-body">
        <view class="segment-wrap">
          <wd-segmented
            :value="segValue"
            :options="segOptions"
            @change="onSegChange"
          />
        </view>

        <template v-if="summary">
          <view class="stats-row">
            <StatTile label="专注分钟" :value="summary.focusMinutes" unit="分" tone="primary" />
            <StatTile label="点数净变化" :value="signed(summary.netPoints)" tone="success" />
            <StatTile label="打卡完成率" :value="summary.checkinRate" unit="%" tone="success" />
          </view>

          <view class="stats-row wide">
            <StatTile
              label="专注完成率"
              :value="summary.focusDoneRate"
              unit="%"
              :hint="`${summary.focusSessions} 场已结算`"
            />
            <StatTile
              label="报备按时率"
              :value="summary.reportOnTimeRate"
              unit="%"
              :hint="`${summary.reportOnTime}/${summary.reportEnded} 次`"
            />
          </view>

          <view class="stats-card">
            <view class="card-head">
              <text class="card-title">专注趋势</text>
              <text class="card-sub">{{ summary.fromLabel }} → {{ summary.toLabel }}</text>
            </view>
            <TrendChart :data="trendData" unit="分钟/天" />
          </view>

          <view class="stats-card">
            <view class="card-head">
              <text class="card-title">专注任务占比</text>
            </view>
            <view v-if="!summary.taskShares.length" class="empty">还没有专注记录。</view>
            <view v-for="row in summary.taskShares" :key="'task-' + row.label" class="share-row">
              <view class="share-head">
                <text class="share-label">{{ row.label }}</text>
                <text class="share-value">{{ row.value }} 分钟 · {{ row.percent }}%</text>
              </view>
              <view class="share-track">
                <view class="share-fill" :style="{ width: row.percent + '%' }"></view>
              </view>
            </view>
          </view>

          <view class="stats-card">
            <view class="card-head">
              <text class="card-title">报备目标占比</text>
            </view>
            <view v-if="!summary.targetShares.length" class="empty">还没有报备记录。</view>
            <view v-for="row in summary.targetShares" :key="'target-' + row.label" class="share-row">
              <view class="share-head">
                <text class="share-label">{{ row.label }}</text>
                <text class="share-value">{{ row.value }} 分钟 · {{ row.percent }}%</text>
              </view>
              <view class="share-track">
                <view class="share-fill alt" :style="{ width: row.percent + '%' }"></view>
              </view>
            </view>
          </view>

          <view class="stats-card">
            <view class="card-head">
              <text class="card-title">最近记录</text>
            </view>
            <view v-if="!summary.recent.length" class="empty">还没有记录。</view>
            <view v-for="row in summary.recent" :key="row.key" class="recent-row">
              <view class="recent-main">
                <text class="recent-title">{{ row.title }}</text>
                <text class="recent-sub">{{ row.subtitle }}</text>
              </view>
              <text v-if="row.points" class="recent-points">+{{ row.points }}</text>
            </view>
          </view>

          <view v-if="!summary.hasData" class="empty-state">
            <text class="empty-title">{{ emptyLine }}</text>
            <text class="empty-sub">去做一点，再回来看。</text>
          </view>
        </template>

        <view v-else class="empty-state">
          <text class="empty-title">{{ loading ? '正在统计…' : '统计加载失败' }}</text>
        </view>

        <text class="foot-hint">统计口径：专注分钟按实际投入计算；打卡完成率只统计到今天为止。</text>
      </view>
    </scroll-view>
  </view>
</template>

<script setup>
import { computed, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import StatTile from '../../components/selfdiscipline/StatTile.vue'
import TrendChart from '../../components/selfdiscipline/TrendChart.vue'
import { isDark, themeVars, applyNativeNavigationBar } from '../../theme/theme.js'
import * as repo from '../../selfdiscipline/repository.js'
import * as stats from '../../selfdiscipline/stats.js'
import * as focus from '../../selfdiscipline/focus.js'
import { personaLine } from '../../selfdiscipline/persona.js'

const segOptions = ['近 7 天', '近 30 天', '近 90 天']
const segValue = ref(segOptions[0])
const summary = ref(null)
const loading = ref(false)
const emptyLine = ref('这段时间没有数据。')
let strictness = 'A'

const trendData = computed(() => {
  if (!summary.value) return []
  return summary.value.daily.map((row) => ({ label: row.label, value: row.focusMinutes }))
})

function signed(value) {
  const n = Number(value) || 0
  return n > 0 ? `+${n}` : String(n)
}

function daysOf(value) {
  if (value === segOptions[1]) return 30
  if (value === segOptions[2]) return 90
  return 7
}

async function load(days) {
  loading.value = true
  try {
    await repo.init()
    const prefs = await focus.getPrefs()
    strictness = prefs.strictness
    summary.value = await stats.summarize(days, Date.now())
    emptyLine.value = personaLine('stats_empty', strictness)
  } catch (e) {
    summary.value = null
    uni.showToast({ title: (e && e.message) || '统计失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}

async function onSegChange(payload) {
  // wd-segmented 的 change 事件对字符串选项返回 { value }
  const value = payload && payload.value !== undefined ? payload.value : payload
  segValue.value = value
  await load(daysOf(value))
}

onShow(async () => {
  applyNativeNavigationBar()
  await load(daysOf(segValue.value))
})
</script>

<!-- scoped 防止跨页面同名按钮样式互相覆盖 -->
<style scoped>
.stats-page {
  min-height: 100vh;
  background: var(--ik-bg);
}
.stats-scroll {
  height: 100vh;
}
.stats-body {
  padding: 28rpx 32rpx calc(48rpx + env(safe-area-inset-bottom));
  box-sizing: border-box;
}
.segment-wrap {
  background: var(--ik-card);
  border-radius: var(--ik-radius);
  padding: 12rpx;
  margin-bottom: 24rpx;
}
.stats-row {
  display: flex;
  gap: 16rpx;
  margin-bottom: 16rpx;
}
.stats-card {
  background: var(--ik-card);
  border-radius: var(--ik-radius);
  padding: 28rpx;
  margin-bottom: 24rpx;
  box-sizing: border-box;
}
.card-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 18rpx;
}
.card-title {
  font-size: 28rpx;
  font-weight: 600;
  color: var(--ik-t1);
}
.card-sub {
  font-size: 20rpx;
  color: var(--ik-t3);
}
.empty {
  font-size: 26rpx;
  color: var(--ik-t3);
  padding: 8rpx 0;
}
.share-row {
  margin-bottom: 20rpx;
}
.share-row:last-child {
  margin-bottom: 0;
}
.share-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16rpx;
}
.share-label {
  font-size: 26rpx;
  color: var(--ik-t1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.share-value {
  flex: 0 0 auto;
  font-size: 22rpx;
  color: var(--ik-t3);
}
.share-track {
  margin-top: 8rpx;
  height: 14rpx;
  border-radius: 999rpx;
  background: var(--ik-soft);
  overflow: hidden;
}
.share-fill {
  height: 100%;
  border-radius: 999rpx;
  background: var(--ik-primary);
}
.share-fill.alt {
  background: var(--ik-success);
}
.recent-row {
  display: flex;
  align-items: center;
  padding: 14rpx 0;
  border-bottom: 1rpx solid var(--ik-line);
}
.recent-row:last-child {
  border-bottom: none;
}
.recent-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.recent-title {
  font-size: 26rpx;
  color: var(--ik-t1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.recent-sub {
  margin-top: 4rpx;
  font-size: 22rpx;
  color: var(--ik-t3);
}
.recent-points {
  flex: 0 0 auto;
  margin-left: 12rpx;
  font-size: 26rpx;
  font-weight: 600;
  color: var(--ik-success);
}
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 48rpx 24rpx;
}
.empty-title {
  font-size: 28rpx;
  color: var(--ik-t2);
  text-align: center;
}
.empty-sub {
  margin-top: 10rpx;
  font-size: 24rpx;
  color: var(--ik-t3);
}
.foot-hint {
  display: block;
  margin-top: 8rpx;
  font-size: 22rpx;
  line-height: 1.6;
  color: var(--ik-t3);
  text-align: center;
}
</style>
