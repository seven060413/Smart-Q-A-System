<template>
  <view class="perm-page theme-root" :class="{ 'is-dark': isDark }" :style="themeVars">
    <ThemeBackground />
    <scroll-view class="perm-scroll" scroll-y>
      <view class="perm-body">
        <view v-if="!readiness.supported" class="platform-banner">
          网页版仅支持页面内提醒，不支持后台通知、精确闹钟与悬浮窗。完整能力请使用安卓 App。
        </view>

        <view class="perm-card">
          <view class="perm-row">
            <view class="perm-main">
              <text class="perm-label">通知权限</text>
              <text class="perm-sub">到点提醒需要通知权限</text>
            </view>
            <text class="perm-state" :class="readiness.notifications ? 'ok' : 'bad'">
              {{ readiness.notifications ? '已开启' : '未开启' }}
            </text>
          </view>
          <button
            v-if="!readiness.notifications"
            class="primary-btn"
            :disabled="busy"
            @click="requestNotify"
          >申请通知权限</button>
          <button
            v-else-if="readiness.supported"
            class="ghost-btn"
            @click="openNotifySettings"
          >去系统设置</button>
          <text class="perm-note">Android 13+ 需要手动允许通知。</text>
        </view>

        <view class="perm-card">
          <view class="perm-row">
            <view class="perm-main">
              <text class="perm-label">精确闹钟</text>
              <text class="perm-sub">没有它时提醒可能延迟几分钟</text>
            </view>
            <text class="perm-state" :class="exactTextClass">{{ exactText }}</text>
          </view>
          <button
            v-if="readiness.supported && !exactAlarm"
            class="primary-btn"
            @click="openExactSettings"
          >去开启“闹钟和提醒”</button>
          <text class="perm-note">Android 12+ 需要授权；Android 14+ 新装默认关闭。</text>
        </view>

        <view class="perm-card">
          <view class="perm-row">
            <view class="perm-main">
              <text class="perm-label">悬浮窗</text>
              <text class="perm-sub">专注中离开 App 时显示眼睛</text>
            </view>
            <text class="perm-state" :class="guardReady ? (guardStatus.overlay ? 'ok' : 'bad') : 'muted'">
              {{ guardReady ? (guardStatus.overlay ? '已开启' : '未开启') : '不支持' }}
            </text>
          </view>
          <button
            v-if="guardReady && !guardStatus.overlay"
            class="primary-btn"
            @click="openOverlay"
          >去开启悬浮窗</button>
          <text class="perm-note">未开启时专注与提醒照常，只是不显示悬浮窗。</text>
        </view>

        <view class="perm-card">
          <view class="perm-row">
            <view class="perm-main">
              <text class="perm-label">前台服务</text>
              <text class="perm-sub">让守护悬浮窗在后台存活</text>
            </view>
            <text class="perm-state" :class="guardReady ? (guardStatus.serviceRunning ? 'ok' : 'muted') : 'muted'">
              {{ guardReady ? (guardStatus.serviceRunning ? '运行中' : '未运行') : '不支持' }}
            </text>
          </view>
          <text class="perm-note">只有专注进行中才运行；通知栏会有一条常驻通知，这是 Android 的要求。</text>
        </view>

        <view class="perm-card">
          <view class="perm-row">
            <view class="perm-main">
              <text class="perm-label">开机重排</text>
              <text class="perm-sub">重启后恢复未来的提醒</text>
            </view>
            <text class="perm-state ok">已声明</text>
          </view>
          <text class="perm-note">前提是系统没有禁止 App 自启动。</text>
        </view>

        <view class="perm-card">
          <text class="perm-label">电池优化与自启动</text>
          <text class="perm-line">这部分无法用 API 检测，也不会主动申请。若提醒经常延迟，请到系统设置中：</text>
          <text class="perm-line">1. 允许 App 自启动 / 后台运行；</text>
          <text class="perm-line">2. 把电池优化设为“不限制”；</text>
          <text class="perm-line">3. 允许“闹钟和提醒”特殊权限。</text>
        </view>

        <view class="perm-card">
          <view class="perm-row">
            <view class="perm-main">
              <text class="perm-label">精确前台应用（v1.1）</text>
              <text class="perm-sub">当前版本不读取使用情况</text>
            </view>
            <text class="perm-state muted">未启用</text>
          </view>
          <text class="perm-note">v1 只通过 App 进入后台触发守护，不申请 PACKAGE_USAGE_STATS。</text>
        </view>

        <button class="ghost-btn wide" @click="refresh">刷新状态</button>
        <text class="foot-hint">拒绝权限不会阻止使用专注与打卡，只会少掉对应的提醒或悬浮窗。</text>
      </view>
    </scroll-view>
  </view>
</template>

<script setup>
import { computed, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { isDark, themeVars, applyNativeNavigationBar } from '../../theme/theme.js'
import * as reminder from '../../selfdiscipline/reminder.js'
import * as guard from '../../selfdiscipline/guard.js'

const readiness = ref({})
const guardStatus = ref({})
const busy = ref(false)

const guardReady = computed(() => !!guardStatus.value.supported)
const exactAlarm = computed(() => !!readiness.value.exactAlarm)

const exactText = computed(() => {
  const r = readiness.value || {}
  if (!r.supported) return '不支持'
  if (r.exactAlarm) return '已开启'
  return r.exactAlarmNeeded ? '未开启' : '不需要'
})

const exactTextClass = computed(() => {
  if (!readiness.value.supported) return 'muted'
  return readiness.value.exactAlarm ? 'ok' : 'bad'
})

async function refresh() {
  applyNativeNavigationBar()
  readiness.value = await reminder.getReadiness()
  guardStatus.value = guard.getGuardStatus() || {}
}

onShow(refresh)

async function requestNotify() {
  if (busy.value) return
  busy.value = true
  try {
    await reminder.requestNotificationPermission()
    await refresh()
    if (!readiness.value.notifications) {
      uni.showToast({ title: '未获得通知权限，可去系统设置开启', icon: 'none' })
    }
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '申请失败', icon: 'none' })
  } finally {
    busy.value = false
  }
}

function openNotifySettings() {
  reminder.openNotificationSettings()
}

function openExactSettings() {
  reminder.openExactAlarmSettings()
}

function openOverlay() {
  guard.openOverlaySettings()
}
</script>

<!-- scoped 防止跨页面同名按钮样式互相覆盖 -->
<style scoped>
.perm-page {
  min-height: 100vh;
  background: var(--ik-bg);
}
.perm-scroll {
  height: 100vh;
}
.perm-body {
  padding: 28rpx 32rpx calc(48rpx + env(safe-area-inset-bottom));
  box-sizing: border-box;
}
.platform-banner {
  background: var(--ik-soft);
  color: var(--ik-t2);
  border-radius: var(--ik-radius);
  padding: 20rpx 24rpx;
  margin-bottom: 24rpx;
  font-size: 24rpx;
  line-height: 1.6;
}
.perm-card {
  background: var(--ik-card);
  border-radius: var(--ik-radius);
  padding: 26rpx 28rpx;
  margin-bottom: 20rpx;
  box-sizing: border-box;
}
.perm-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16rpx;
}
.perm-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.perm-label {
  font-size: 28rpx;
  font-weight: 600;
  color: var(--ik-t1);
}
.perm-sub {
  margin-top: 4rpx;
  font-size: 22rpx;
  color: var(--ik-t3);
}
.perm-state {
  flex: 0 0 auto;
  font-size: 24rpx;
}
.perm-state.ok {
  color: var(--ik-success);
}
.perm-state.bad {
  color: var(--ik-danger);
}
.perm-state.muted {
  color: var(--ik-t3);
}
.perm-note {
  display: block;
  margin-top: 12rpx;
  font-size: 22rpx;
  line-height: 1.6;
  color: var(--ik-t3);
}
.perm-line {
  display: block;
  margin-top: 10rpx;
  font-size: 23rpx;
  line-height: 1.7;
  color: var(--ik-t2);
}
.primary-btn {
  width: 100%;
  margin: 18rpx 0 0;
  height: 76rpx;
  line-height: 76rpx;
  border-radius: 999rpx;
  font-size: 26rpx;
  background: var(--ik-primary);
  color: var(--ik-on-primary);
  border: none;
}
.primary-btn::after {
  border: none;
}
.ghost-btn {
  width: 100%;
  margin: 18rpx 0 0;
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
.ghost-btn.wide {
  margin-top: 8rpx;
}
.foot-hint {
  display: block;
  margin-top: 18rpx;
  font-size: 22rpx;
  line-height: 1.6;
  color: var(--ik-t3);
  text-align: center;
}
</style>
