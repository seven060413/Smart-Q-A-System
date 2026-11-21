<template>
  <view class="report-page theme-root" :class="{ 'is-dark': isDark }" :style="themeVars">
    <ThemeBackground />
    <scroll-view class="report-scroll" scroll-y>
      <view class="report-body">
        <view class="report-eye">
          <EyeGaze :state="eyeState" :progress="runtime.ratio" :size="360" />
        </view>

        <!-- 进行中的报备 -->
        <template v-if="mode === 'active'">
          <view class="report-card">
            <view class="active-head">
              <text class="active-app">报备 · {{ active.target_app }}</text>
              <text class="active-time" :class="{ 'is-due': runtime.due }">
                {{ runtime.due ? '已到点' : remainingClock }}
              </text>
            </view>
            <text class="active-purpose">{{ active.purpose }}</text>

            <view class="progress-track">
              <view class="progress-fill" :style="{ width: Math.round(runtime.ratio * 100) + '%' }"></view>
            </view>
            <view class="progress-meta">
              <text>已用 {{ usedMinutes }} 分钟</text>
              <text>计划 {{ active.minutes }} 分钟</text>
            </view>

            <view v-if="runtime.overdue" class="warn-banner">
              已超过报备时间。不扣分，但记着这件事。
            </view>
            <view v-else-if="runtime.due" class="due-banner">报备的时间到了，回来结算。</view>

            <text class="persona-line">{{ activeLine }}</text>

            <view class="action-row">
              <button class="ghost-btn" :disabled="busy" @click="extend">再等等我（+5 分钟）</button>
            </view>
            <button class="primary-btn" :disabled="busy" @click="finish(true)">完成了</button>
            <button class="danger-btn" :disabled="busy" @click="abandon">放弃这次报备</button>
          </view>
          <text class="foot-hint">报备只是提醒，不会读取或拦截目标应用。</text>
        </template>

        <!-- 结束结果 -->
        <template v-else-if="mode === 'result'">
          <view class="report-card result-card">
            <text class="result-points">{{ resultPoints > 0 ? `+${resultPoints} 点` : '0 点' }}</text>
            <text class="result-line">{{ resultLine }}</text>
            <button class="primary-btn" @click="resetForm">再报备一次</button>
            <button class="ghost-btn wide" @click="back">回到自律</button>
          </view>
        </template>

        <!-- 新建报备 -->
        <template v-else>
          <view class="report-card">
            <text class="field-label">目标应用</text>
            <view class="chip-row">
              <view
                v-for="item in targets"
                :key="item"
                class="chip"
                :class="{ 'is-active': target === item }"
                @click="target = item"
              >
                {{ item }}
              </view>
            </view>
            <view v-if="target === '其他'" class="custom-target">
              <wd-input v-model="customTarget" placeholder="填写应用名称" :maxlength="20" clearable />
            </view>

            <text class="field-label field-gap">目的</text>
            <wd-textarea
              v-model="purpose"
              placeholder="我去做什么？例如：回几条消息就回来"
              :maxlength="120"
              show-word-limit
            />

            <text class="field-label field-gap">预定分钟</text>
            <view class="chip-row">
              <view
                v-for="value in durationPresets"
                :key="value"
                class="chip"
                :class="{ 'is-active': minutes === value }"
                @click="selectMinutes(value)"
              >
                {{ value }} 分钟
              </view>
            </view>
            <view class="custom-row">
              <text class="custom-label">自定义</text>
              <wd-input-number
                v-model="customMinutes"
                :min="5"
                :max="180"
                :step="5"
                input-width="120rpx"
              />
              <button class="mini-btn" @click="useCustom">使用</button>
            </view>

            <button class="primary-btn" :disabled="busy" @click="start">
              {{ busy ? '正在报备…' : '开始报备' }}
            </button>
            <text class="foot-hint">这是自我承诺：到点提醒，不统计、不阻止。不会读取应用列表。</text>
          </view>
        </template>
      </view>
    </scroll-view>
  </view>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { onHide, onShow, onUnload } from '@dcloudio/uni-app'
import EyeGaze from '../../components/selfdiscipline/EyeGaze.vue'
import { isDark, themeVars, tokens, applyNativeNavigationBar } from '../../theme/theme.js'
import * as repo from '../../selfdiscipline/repository.js'
import * as reportModule from '../../selfdiscipline/report.js'
import * as focus from '../../selfdiscipline/focus.js'
import { personaLine } from '../../selfdiscipline/persona.js'
import { formatClock } from '../../selfdiscipline/dates.js'

const targets = [...reportModule.TARGET_PRESETS, '其他']
const durationPresets = reportModule.DURATION_PRESETS

const mode = ref('form')
const active = ref(null)
const now = ref(Date.now())
const target = ref(reportModule.TARGET_PRESETS[0])
const customTarget = ref('')
const purpose = ref('')
const minutes = ref(15)
const customMinutes = ref(20)
const busy = ref(false)
const strictness = ref('A')
const resultPoints = ref(0)
const resultLine = ref('')
const activeLine = ref('')

let timer = null
let minutesTouched = false

const runtime = computed(() => reportModule.reportRuntime(active.value, now.value))
const remainingClock = computed(() => formatClock(runtime.value.remainingMs))
const usedMinutes = computed(() => Math.max(0, Math.floor(runtime.value.usedMs / 60000)))

const eyeState = computed(() => {
  if (mode.value === 'active') {
    if (runtime.value.overdue) return 'abandon'
    return runtime.value.due ? 'due' : 'focus'
  }
  if (mode.value === 'result') return resultPoints.value > 0 ? 'done' : 'idle'
  return 'idle'
})

function startTimer() {
  stopTimer()
  timer = setInterval(() => {
    now.value = Date.now()
  }, 1000)
}

function stopTimer() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

async function refresh() {
  applyNativeNavigationBar()
  try {
    await repo.init()
    const prefs = await focus.getPrefs()
    strictness.value = prefs.strictness
    if (!minutesTouched) minutes.value = 15

    if (mode.value === 'result') return

    const current = await reportModule.getActive(Date.now())
    active.value = current
    now.value = Date.now()
    if (current) {
      mode.value = 'active'
      refreshActiveLine()
      startTimer()
    } else {
      mode.value = 'form'
      stopTimer()
    }
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '加载失败', icon: 'none' })
  }
}

function refreshActiveLine() {
  if (!active.value) return
  const rt = reportModule.reportRuntime(active.value, Date.now())
  let event = 'report_start'
  if (rt.overdue) event = 'report_overdue'
  else if (rt.due) event = 'report_due'
  activeLine.value = personaLine(event, strictness.value, { minutes: active.value.minutes })
}

// 到点/超时切换时更新人格文案，不随每秒倒计时变化
watch(
  () => [runtime.value.due, runtime.value.overdue],
  () => {
    if (mode.value === 'active') refreshActiveLine()
  }
)

onShow(refresh)
onHide(stopTimer)
onUnload(stopTimer)

function selectMinutes(value) {
  minutes.value = value
  minutesTouched = true
}

function useCustom() {
  minutes.value = reportModule.clampReportMinutes(customMinutes.value)
  minutesTouched = true
}

async function start() {
  if (busy.value) return
  const app = target.value === '其他' ? customTarget.value.trim() : target.value
  if (!app) {
    uni.showToast({ title: '请填写目标应用', icon: 'none' })
    return
  }
  if (!purpose.value.trim()) {
    uni.showToast({ title: '请填写报备目的', icon: 'none' })
    return
  }
  busy.value = true
  try {
    const created = await reportModule.startReport({
      targetApp: app,
      purpose: purpose.value,
      minutes: minutes.value,
    })
    active.value = created
    now.value = Date.now()
    mode.value = 'active'
    refreshActiveLine()
    startTimer()
    uni.showToast({ title: '报备已开始', icon: 'none' })
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '报备失败', icon: 'none' })
  } finally {
    busy.value = false
  }
}

async function extend() {
  if (busy.value) return
  busy.value = true
  try {
    const next = await reportModule.extendReport(5)
    active.value = { ...active.value, ...next }
    now.value = Date.now()
    activeLine.value = personaLine('report_extend', strictness.value, { minutes: next.minutes })
    uni.showToast({ title: '已延长 5 分钟', icon: 'none' })
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '操作失败', icon: 'none' })
  } finally {
    busy.value = false
  }
}

async function settle(completed) {
  busy.value = true
  try {
    const settled = await reportModule.finishReport(completed)
    stopTimer()
    resultPoints.value = Number(settled.points) || 0
    resultLine.value = personaLine(
      completed ? 'report_done' : 'report_overdue',
      strictness.value,
      { minutes: settled.minutes }
    )
    active.value = null
    mode.value = 'result'
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '操作失败', icon: 'none' })
  } finally {
    busy.value = false
  }
}

function finish(completed) {
  if (busy.value) return
  uni.showModal({
    title: '完成了',
    content: '确认这次报备完成吗？完成会获得 5 点。',
    confirmText: '完成了',
    success: (res) => {
      if (res.confirm) settle(true)
    },
  })
}

function abandon() {
  if (busy.value) return
  uni.showModal({
    title: '放弃这次报备',
    content: '放弃后不计点数。',
    confirmText: '放弃',
    confirmColor: tokens.value.danger,
    success: (res) => {
      if (res.confirm) settle(false)
    },
  })
}

function resetForm() {
  mode.value = 'form'
  purpose.value = ''
  customTarget.value = ''
  target.value = reportModule.TARGET_PRESETS[0]
  resultPoints.value = 0
}

function back() {
  uni.navigateBack()
}
</script>

<!-- scoped 防止跨页面同名按钮样式互相覆盖 -->
<style scoped>
.report-page {
  min-height: 100vh;
  background: var(--ik-bg);
}
.report-scroll {
  height: 100vh;
}
.report-body {
  padding: 40rpx 32rpx calc(48rpx + env(safe-area-inset-bottom));
  box-sizing: border-box;
}
.report-eye {
  display: flex;
  justify-content: center;
  margin-bottom: 8rpx;
}
.report-card {
  background: var(--ik-card);
  border-radius: var(--ik-radius);
  padding: 30rpx 28rpx;
  margin-top: 16rpx;
  box-sizing: border-box;
}
.field-label {
  display: block;
  font-size: 24rpx;
  font-weight: 600;
  color: var(--ik-t2);
  margin-bottom: 12rpx;
}
.field-gap {
  margin-top: 26rpx;
}
.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 14rpx;
}
.chip {
  padding: 14rpx 22rpx;
  border-radius: 999rpx;
  border: 1rpx solid var(--ik-line);
  font-size: 24rpx;
  color: var(--ik-t2);
}
.chip.is-active {
  border-color: var(--ik-primary);
  color: var(--ik-primary);
  background: var(--ik-primary-weak);
}
.custom-target {
  margin-top: 16rpx;
}
.custom-row {
  display: flex;
  align-items: center;
  gap: 16rpx;
  margin-top: 20rpx;
}
.custom-label {
  font-size: 24rpx;
  color: var(--ik-t2);
}
.mini-btn {
  margin: 0;
  padding: 0 22rpx;
  height: 60rpx;
  line-height: 60rpx;
  font-size: 24rpx;
  border-radius: 999rpx;
  background: transparent;
  color: var(--ik-primary);
  border: 1rpx solid var(--ik-primary);
}
.mini-btn::after {
  border: none;
}
.active-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16rpx;
}
.active-app {
  font-size: 32rpx;
  font-weight: 700;
  color: var(--ik-t1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.active-time {
  flex: 0 0 auto;
  font-size: 34rpx;
  font-weight: 700;
  color: var(--ik-primary);
}
.active-time.is-due {
  color: var(--ik-danger);
}
.active-purpose {
  display: block;
  margin-top: 10rpx;
  font-size: 26rpx;
  line-height: 1.6;
  color: var(--ik-t2);
}
.progress-track {
  margin-top: 24rpx;
  height: 16rpx;
  border-radius: 999rpx;
  background: var(--ik-soft);
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  background: var(--ik-primary);
  border-radius: 999rpx;
  transition: width 0.4s linear;
}
.progress-meta {
  display: flex;
  justify-content: space-between;
  margin-top: 10rpx;
  font-size: 22rpx;
  color: var(--ik-t3);
}
.warn-banner,
.due-banner {
  margin-top: 20rpx;
  padding: 14rpx 18rpx;
  border-radius: 16rpx;
  font-size: 24rpx;
  text-align: center;
}
.warn-banner {
  background: var(--ik-soft);
  color: var(--ik-danger);
}
.due-banner {
  background: var(--ik-soft);
  color: var(--ik-primary);
}
.persona-line {
  display: block;
  margin-top: 20rpx;
  font-size: 26rpx;
  color: var(--ik-t2);
  text-align: center;
}
.primary-btn {
  width: 100%;
  margin: 24rpx 0 0;
  height: 84rpx;
  line-height: 84rpx;
  border-radius: 999rpx;
  font-size: 30rpx;
  background: var(--ik-primary);
  color: var(--ik-on-primary);
  border: none;
}
.primary-btn::after {
  border: none;
}
.ghost-btn {
  flex: 1;
  width: 100%;
  margin: 0;
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
  margin-top: 18rpx;
}
.danger-btn {
  width: 100%;
  margin: 18rpx 0 0;
  height: 72rpx;
  line-height: 72rpx;
  border-radius: 999rpx;
  font-size: 26rpx;
  background: transparent;
  color: var(--ik-danger);
  border: 1rpx solid var(--ik-danger);
}
.danger-btn::after {
  border: none;
}
.action-row {
  display: flex;
  gap: 16rpx;
  margin-top: 24rpx;
}
.result-card {
  text-align: center;
}
.result-points {
  display: block;
  font-size: 48rpx;
  font-weight: 800;
  color: var(--ik-success);
}
.result-line {
  display: block;
  margin-top: 8rpx;
  font-size: 26rpx;
  color: var(--ik-t2);
}
.foot-hint {
  display: block;
  margin-top: 20rpx;
  font-size: 22rpx;
  line-height: 1.6;
  color: var(--ik-t3);
  text-align: center;
}
</style>
