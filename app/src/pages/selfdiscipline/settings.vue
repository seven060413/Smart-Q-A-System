<template>
  <view class="settings-page theme-root" :class="{ 'is-dark': isDark }" :style="themeVars">
    <ThemeBackground />
    <scroll-view class="settings-scroll" scroll-y>
      <view class="settings-body">
        <view class="settings-card">
          <view class="card-head">
            <text class="card-title">提醒与权限</text>
            <text class="card-link" @click="openPermissions">去检查</text>
          </view>
          <view v-for="row in statusRows" :key="row.key" class="status-row">
            <text class="status-label">{{ row.label }}</text>
            <text class="status-value" :class="row.ok ? 'ok' : (row.unsupported ? 'muted' : 'bad')">
              {{ row.text }}
            </text>
          </view>
          <text v-if="!readiness.supported" class="card-hint">
            网页版只在页面打开时提醒，也不支持悬浮窗；完整提醒请使用安卓 App。
          </text>
        </view>

        <view class="settings-card">
          <text class="card-title">说话方式</text>
          <view class="segment-wrap">
            <wd-segmented :value="strictnessText" :options="strictOptions" @change="onStrictChange" />
          </view>
          <text class="card-hint">严格度只改变它说话的方式，不会替你锁应用，也不影响点数。</text>
        </view>

        <view class="settings-card">
          <view class="setting-row">
            <view class="setting-main">
              <text class="setting-label">默认专注时长</text>
              <text class="setting-sub">开始专注时默认选中</text>
            </view>
            <wd-input-number
              v-model="defaultFocusMin"
              :min="5"
              :max="180"
              :step="5"
              input-width="110rpx"
              @change="onFocusMinChange"
            />
          </view>
          <view class="setting-row">
            <view class="setting-main">
              <text class="setting-label">默认延长分钟</text>
              <text class="setting-sub">专注页“延长”按钮的步长</text>
            </view>
            <wd-input-number
              v-model="defaultExtendMin"
              :min="5"
              :max="60"
              :step="5"
              input-width="110rpx"
              @change="onExtendMinChange"
            />
          </view>
          <view class="setting-row">
            <view class="setting-main">
              <text class="setting-label">专注守护</text>
              <text class="setting-sub">专注中离开 App 时，显示眼睛悬浮窗</text>
            </view>
            <wd-switch v-model="guardEnabled" size="20px" @change="onGuardChange" />
          </view>
          <text class="card-hint">
            守护需要悬浮窗与前台服务权限；它只占右上角一小块，不遮全屏、不阻止操作。
          </text>
        </view>

        <view class="settings-card">
          <text class="card-title">数据</text>
          <view class="data-row">
            <text class="data-label">今日点数</text>
            <text class="data-value">{{ todayPoints }}</text>
          </view>
          <view class="data-row">
            <text class="data-label">累计点数</text>
            <text class="data-value">{{ totalPoints }}</text>
          </view>
          <view class="data-row">
            <text class="data-label">记录条数</text>
            <text class="data-value">{{ recordCount }}</text>
          </view>
          <view class="data-row">
            <text class="data-label">存储方式</text>
            <text class="data-value">{{ storageLabel }}</text>
          </view>
          <button class="ghost-btn" @click="exportData">导出 JSON 到剪贴板</button>
          <button class="danger-btn" @click="clearData">清空所有自律数据</button>
        </view>

        <view class="settings-card">
          <text class="card-title">关于</text>
          <text class="about-line">自律模块 v1.0.0 · 本地存储，不上传服务器。</text>
          <text class="about-line">提醒依赖系统精确闹钟；强行停止 App 后系统会清空闹钟，直到再次打开。</text>
          <text class="about-line">部分国产 ROM 可能延迟提醒，需要允许自启动、关闭省电限制。</text>
          <text class="about-line">不读取其他应用的使用时长，不拦截、不自动拉起任何应用。</text>
        </view>

        <text class="foot-hint">点数只来自流水求和；撤销打卡会成对记账。</text>
      </view>
    </scroll-view>
  </view>
</template>

<script setup>
import { computed, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { isDark, themeVars, tokens, applyNativeNavigationBar } from '../../theme/theme.js'
import * as repo from '../../selfdiscipline/repository.js'
import * as reminder from '../../selfdiscipline/reminder.js'
import * as guard from '../../selfdiscipline/guard.js'
import * as focus from '../../selfdiscipline/focus.js'
import * as stats from '../../selfdiscipline/stats.js'

const strictOptions = ['A 基础', 'B 严格']
const strictnessText = ref('A 基础')
const defaultFocusMin = ref(25)
const defaultExtendMin = ref(10)
const guardEnabled = ref(true)
const readiness = ref({})
const guardStatus = ref({})
const todayPoints = ref(0)
const totalPoints = ref(0)
const recordCount = ref(0)
const storageLabel = ref('本地')

const statusRows = computed(() => {
  const r = readiness.value || {}
  const g = guardStatus.value || {}
  const supported = !!r.supported
  return [
    {
      key: 'notifications',
      label: '通知权限',
      ok: !!r.notifications,
      unsupported: !supported,
      text: !supported ? '网页版不支持' : (r.notifications ? '已开启' : '未开启'),
    },
    {
      key: 'exact',
      label: '精确闹钟',
      ok: !!r.exactAlarm,
      unsupported: !supported,
      text: !supported ? '网页版不支持' : (r.exactAlarm ? '已开启' : (r.exactAlarmNeeded ? '未开启' : '不需要')),
    },
    {
      key: 'overlay',
      label: '悬浮窗',
      ok: !!g.overlay,
      unsupported: !supported || !g.supported,
      text: (!supported || !g.supported) ? '当前平台不支持' : (g.overlay ? '已开启' : '未开启'),
    },
    {
      key: 'service',
      label: '前台服务',
      ok: !!g.serviceRunning,
      unsupported: !supported || !g.supported,
      text: (!supported || !g.supported) ? '当前平台不支持' : (g.serviceRunning ? '运行中' : '未运行'),
    },
  ]
})

async function load() {
  await repo.init()
  const [prefs, ready, guardState, today, points, exported] = await Promise.all([
    focus.getPrefs(),
    reminder.getReadiness(),
    Promise.resolve(guard.getGuardStatus()),
    stats.todayStats(Date.now()),
    repo.sumPoints(),
    repo.exportAll(),
  ])
  strictnessText.value = prefs.strictness === 'B' ? strictOptions[1] : strictOptions[0]
  defaultFocusMin.value = prefs.defaultFocusMin
  defaultExtendMin.value = prefs.defaultExtendMin
  guardEnabled.value = prefs.guardEnabled
  readiness.value = ready
  guardStatus.value = guardState || {}
  todayPoints.value = today.netPoints
  totalPoints.value = points
  let count = 0
  for (const key of Object.keys(exported || {})) {
    if (key === 'settings') continue
    count += Array.isArray(exported[key]) ? exported[key].length : 0
  }
  recordCount.value = count
  storageLabel.value = repo.storageMode() === 'sqlite' ? 'SQLite' : '本地 JSON'
}

async function refresh() {
  applyNativeNavigationBar()
  try {
    await load()
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '加载失败', icon: 'none' })
  }
}

onShow(refresh)

async function onStrictChange(payload) {
  const value = payload && payload.value !== undefined ? payload.value : payload
  strictnessText.value = value
  const valueKey = value === strictOptions[1] ? 'B' : 'A'
  await focus.setPref('strictness', valueKey)
  uni.showToast({ title: '已更新说话方式', icon: 'none' })
}

async function onFocusMinChange(e) {
  const value = focus.clampMinutes(e && e.value !== undefined ? e.value : defaultFocusMin.value)
  defaultFocusMin.value = value
  await focus.setPref('defaultFocusMin', value)
}

async function onExtendMinChange(e) {
  const value = focus.clampMinutes(e && e.value !== undefined ? e.value : defaultExtendMin.value)
  defaultExtendMin.value = value
  await focus.setPref('defaultExtendMin', value)
}

async function onGuardChange(e) {
  const value = !!(e && e.value !== undefined ? e.value : guardEnabled.value)
  guardEnabled.value = value
  await focus.setPref('guardEnabled', value)
  try {
    if (!value) guard.stopGuard()
    else await guard.reconcileGuard()
  } catch (err) {}
  uni.showToast({ title: value ? '专注守护已开启' : '专注守护已关闭', icon: 'none' })
}

function openPermissions() {
  uni.navigateTo({ url: '/pages/selfdiscipline/permissions' })
}

async function exportData() {
  try {
    const text = await repo.exportJson()
    uni.setClipboardData({
      data: text,
      success: () => uni.showToast({ title: '已复制导出数据', icon: 'none' }),
      fail: () => uni.showToast({ title: '复制失败', icon: 'none' }),
    })
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '导出失败', icon: 'none' })
  }
}

function clearData() {
  uni.showModal({
    title: '清空所有自律数据',
    content: '专注、报备、打卡、点数和提醒都会被删除，无法恢复。确认继续？',
    confirmText: '清空',
    confirmColor: tokens.value.danger,
    success: async (res) => {
      if (!res.confirm) return
      try {
        reminder.cancelAll()
      } catch (e) {}
      try {
        guard.stopGuard()
      } catch (e) {}
      try {
        await repo.clearAll()
        await load()
        uni.showToast({ title: '已清空', icon: 'none' })
      } catch (e) {
        uni.showToast({ title: (e && e.message) || '清空失败', icon: 'none' })
      }
    },
  })
}
</script>

<!-- scoped 防止跨页面同名按钮样式互相覆盖 -->
<style scoped>
.settings-page {
  min-height: 100vh;
  background: var(--ik-bg);
}
.settings-scroll {
  height: 100vh;
}
.settings-body {
  padding: 28rpx 32rpx calc(48rpx + env(safe-area-inset-bottom));
  box-sizing: border-box;
}
.settings-card {
  background: var(--ik-card);
  border-radius: var(--ik-radius);
  padding: 28rpx;
  margin-bottom: 24rpx;
  box-sizing: border-box;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8rpx;
}
.card-title {
  font-size: 28rpx;
  font-weight: 600;
  color: var(--ik-t1);
}
.card-link {
  font-size: 24rpx;
  color: var(--ik-primary);
}
.card-hint {
  display: block;
  margin-top: 14rpx;
  font-size: 22rpx;
  line-height: 1.6;
  color: var(--ik-t3);
}
.status-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16rpx 0;
  border-bottom: 1rpx solid var(--ik-line);
}
.status-row:last-of-type {
  border-bottom: none;
}
.status-label {
  font-size: 26rpx;
  color: var(--ik-t1);
}
.status-value {
  font-size: 24rpx;
}
.status-value.ok {
  color: var(--ik-success);
}
.status-value.bad {
  color: var(--ik-danger);
}
.status-value.muted {
  color: var(--ik-t3);
}
.segment-wrap {
  margin-top: 18rpx;
}
.setting-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20rpx;
  padding: 16rpx 0;
  border-bottom: 1rpx solid var(--ik-line);
}
.setting-row:last-of-type {
  border-bottom: none;
}
.setting-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.setting-label {
  font-size: 26rpx;
  color: var(--ik-t1);
}
.setting-sub {
  margin-top: 4rpx;
  font-size: 22rpx;
  color: var(--ik-t3);
}
.data-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14rpx 0;
  border-bottom: 1rpx solid var(--ik-line);
}
.data-row:last-of-type {
  border-bottom: none;
}
.data-label {
  font-size: 26rpx;
  color: var(--ik-t2);
}
.data-value {
  font-size: 26rpx;
  font-weight: 600;
  color: var(--ik-t1);
}
.ghost-btn {
  width: 100%;
  margin: 20rpx 0 0;
  height: 76rpx;
  line-height: 76rpx;
  border-radius: 999rpx;
  font-size: 26rpx;
  background: transparent;
  color: var(--ik-primary);
  border: 1rpx solid var(--ik-primary);
}
.ghost-btn::after {
  border: none;
}
.danger-btn {
  width: 100%;
  margin: 16rpx 0 0;
  height: 76rpx;
  line-height: 76rpx;
  border-radius: 999rpx;
  font-size: 26rpx;
  background: transparent;
  color: var(--ik-danger);
  border: 1rpx solid var(--ik-danger);
}
.danger-btn::after {
  border: none;
}
.about-line {
  display: block;
  margin-top: 12rpx;
  font-size: 24rpx;
  line-height: 1.7;
  color: var(--ik-t2);
}
.foot-hint {
  display: block;
  margin-top: 8rpx;
  font-size: 22rpx;
  color: var(--ik-t3);
  text-align: center;
}
</style>
