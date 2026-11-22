<template>
  <view class="focus-page theme-root" :class="{ 'is-dark': isDark }" :style="themeVars">
    <ThemeBackground />
    <scroll-view class="focus-scroll" scroll-y>
      <view class="focus-body">
        <!-- 未开始 -->
        <template v-if="mode === 'idle'">
          <view class="focus-eye">
            <EyeGaze state="idle" :size="420" />
          </view>
          <text class="focus-slogan">{{ idleLine }}</text>

          <view class="focus-card">
            <text class="field-label">任务</text>
            <wd-input
              v-model="task"
              placeholder="这 25 分钟要做什么？"
              :maxlength="60"
              clearable
            />

            <text class="field-label field-gap">时长</text>
            <view class="chip-row">
              <view
                v-for="preset in presets"
                :key="preset"
                class="chip"
                :class="{ 'is-active': minutes === preset }"
                @click="selectPreset(preset)"
              >
                {{ preset }} 分钟
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
              {{ busy ? '正在开始…' : '开始专注' }}
            </button>
            <text class="field-hint">开始后离开 App，会让它替你盯着。它只提醒，不拦你。</text>
          </view>
        </template>

        <!-- 进行中 -->
        <template v-else-if="mode === 'running' || mode === 'due'">
          <view class="focus-eye">
            <EyeGaze
              :state="mode === 'due' ? 'due' : 'focus'"
              :progress="runtime.ratio"
              :size="520"
            />
          </view>

          <view class="circle-wrap">
            <wd-circle
              :model-value="runtime.percent"
              :size="circleSize"
              :stroke-width="12"
              :text="remainingClock"
              :color="tokens.primary"
              :layer-color="tokens.line"
            />
            <text class="circle-caption">{{ mode === 'due' ? '时间到了，回来看一眼' : stageLine }}</text>
          </view>

          <view class="focus-card">
            <view class="task-line">
              <text class="task-name">{{ session.task }}</text>
              <text class="task-plan">计划 {{ session.planned_min }} 分钟</text>
            </view>
            <view v-if="mode === 'due'" class="due-banner">到点了，等你结算</view>
            <view class="action-row">
              <button class="ghost-btn" :disabled="busy" @click="extend">
                延长 {{ extendMinutes }} 分钟
              </button>
              <button class="primary-btn flex1" :disabled="busy" @click="onComplete">
                {{ mode === 'due' ? '完成' : '提前完成' }}
              </button>
            </view>
            <button class="danger-btn" :disabled="busy" @click="onAbandon">放弃这一场</button>
          </view>
        </template>

        <!-- 结算结果 -->
        <template v-else-if="mode === 'result'">
          <view class="focus-eye">
            <EyeGaze :state="resultEye" :size="400" />
          </view>
          <text class="result-title">
            {{ result && result.abandoned ? '这一场停在这里' : '这一段结束了' }}
          </text>
          <text class="result-points">
            {{ result && result.earned ? `+${result.earned} 点` : '0 点' }}
          </text>
          <text class="result-line">{{ resultLine }}</text>

          <view class="focus-card">
            <view class="result-row">
              <text class="result-label">实际专注</text>
              <text class="result-value">{{ result ? result.session.actual_min : 0 }} 分钟</text>
            </view>
            <view class="result-row">
              <text class="result-label">任务</text>
              <text class="result-value ellipsis">{{ result ? result.session.task : '' }}</text>
            </view>
            <button class="primary-btn" @click="back">回到自律</button>
          </view>
        </template>
      </view>
    </scroll-view>
  </view>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { onHide, onShow, onUnload } from '@dcloudio/uni-app'
import EyeGaze from '../../components/selfdiscipline/EyeGaze.vue'
import { isDark, themeVars, tokens, applyNativeNavigationBar } from '../../theme/theme.js'
import * as repo from '../../selfdiscipline/repository.js'
import * as focus from '../../selfdiscipline/focus.js'
import * as guard from '../../selfdiscipline/guard.js'
import { personaLine } from '../../selfdiscipline/persona.js'
import { formatClock } from '../../selfdiscipline/dates.js'

const presets = focus.FOCUS_PRESETS
const mode = ref('idle')
const session = ref(null)
const now = ref(Date.now())
const task = ref('')
const minutes = ref(25)
const customMinutes = ref(30)
const busy = ref(false)
const prefs = ref({ defaultFocusMin: 25, defaultExtendMin: 10, strictness: 'A' })
const idleLine = ref('在这里，不说话。')
const stageLine = ref('我在这儿，不说话。')
const result = ref(null)
const resultEye = ref('done')
const resultLine = ref('')
const circleSize = ref(220)

let timer = null
let minutesTouched = false
let abandonTimer = null
// 每次进入专注页最多引导一次，避免用户明确选择“暂不开启”后反复弹窗。
let guardPrompted = false

const runtime = computed(() => focus.focusRuntime(session.value, now.value))
const remainingClock = computed(() => formatClock(runtime.value.remainingMs))
const extendMinutes = computed(() => prefs.value.defaultExtendMin || 10)

watch(
  () => runtime.value.due,
  (due) => {
    if (due && mode.value === 'running') {
      mode.value = 'due'
      stageLine.value = personaLine('focus_done', prefs.value.strictness, {
        task: session.value ? session.value.task : ''
      })
    }
  }
)

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
    circleSize.value = Math.min(260, Math.max(180, uni.upx2px(440)))
  } catch (e) {}
  try {
    await repo.init()
    const prefsValue = await focus.getPrefs()
    prefs.value = prefsValue
    if (!minutesTouched) minutes.value = prefsValue.defaultFocusMin
    if (mode.value !== 'result') {
      idleLine.value = personaLine('empty_today', prefsValue.strictness)
    }

    if (mode.value === 'result') return

    const running = await focus.loadRunningFocus()
    if (running) {
      session.value = running
      now.value = Date.now()
      if (focus.isDue(running)) {
        mode.value = 'due'
        stageLine.value = personaLine('focus_done', prefsValue.strictness, { task: running.task })
      } else {
        mode.value = 'running'
        stageLine.value = personaLine('focus_start', prefsValue.strictness, { task: running.task })
      }
      focus.setKeepScreenOn(true)
      startTimer()
    } else {
      session.value = null
      mode.value = 'idle'
      stopTimer()
    }
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '加载失败', icon: 'none' })
  }
}

onShow(refresh)
onHide(() => {
  stopTimer()
  focus.setKeepScreenOn(false)
})
onUnload(() => {
  stopTimer()
  focus.setKeepScreenOn(false)
  if (abandonTimer) clearTimeout(abandonTimer)
})

function selectPreset(value) {
  minutes.value = value
  minutesTouched = true
}

function useCustom() {
  minutes.value = focus.clampMinutes(customMinutes.value)
  minutesTouched = true
}

/**
 * 专注守护需要悬浮窗权限。开工前引导一次：
 * - 去开启：跳到权限页，回来后重新点开始；
 * - 暂不开启：本次页面不再提示，专注照常开始（只是不显示悬浮窗）。
 */
async function ensureGuardPermission() {
  const prefsValue = prefs.value || {}
  const guardEnabled = prefsValue.guardEnabled !== false
  const status = guard.getGuardStatus() || {}
  if (!guardEnabled || !status.supported || status.overlay) return true
  if (guardPrompted) return true

  return new Promise((resolve) => {
    uni.showModal({
      title: '开启专注守护',
      content: '开启悬浮窗权限后，离开 App 时会显示眼睛提醒。也可以顺便开启通知，避免提醒被系统隐藏。',
      confirmText: '去开启',
      cancelText: '暂不开启',
      success: (res) => {
        guardPrompted = true
        if (res.confirm) {
          uni.navigateTo({ url: '/pages/selfdiscipline/permissions' })
          resolve(false)
        } else {
          resolve(true)
        }
      },
      fail: () => resolve(true),
    })
  })
}

async function start() {
  if (busy.value) return
  const text = task.value.trim()
  if (!text) {
    uni.showToast({ title: '先写下这 25 分钟要做什么', icon: 'none' })
    return
  }
  const allowed = await ensureGuardPermission()
  if (!allowed) return
  busy.value = true
  try {
    const created = await focus.startFocus({ task: text, minutes: minutes.value })
    session.value = created
    now.value = Date.now()
    mode.value = 'running'
    stageLine.value = personaLine('focus_start', prefs.value.strictness, { task: text })
    startTimer()
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '开始失败', icon: 'none' })
    if (e && /没结束/.test(e.message || '')) await refresh()
  } finally {
    busy.value = false
  }
}

async function extend() {
  if (busy.value) return
  busy.value = true
  try {
    const next = await focus.extendFocus(extendMinutes.value)
    session.value = next
    now.value = Date.now()
    if (focus.isDue(next)) mode.value = 'due'
    else mode.value = 'running'
    uni.showToast({ title: `已延长 ${extendMinutes.value} 分钟`, icon: 'none' })
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '延长失败', icon: 'none' })
  } finally {
    busy.value = false
  }
}

function onComplete() {
  if (busy.value) return
  if (mode.value === 'due') {
    settle(false)
    return
  }
  const elapsed = Math.max(0, Math.floor((Date.now() - Number(session.value.started_at)) / 60000))
  uni.showModal({
    title: '提前完成',
    content: `还没到点。现在结束，按实际 ${Math.min(session.value.planned_min, elapsed)} 分钟记点。`,
    confirmText: '提前完成',
    success: (res) => {
      if (res.confirm) settle(true)
    },
  })
}

async function settle(early) {
  busy.value = true
  try {
    const res = await focus.completeFocus({ early })
    stopTimer()
    result.value = { ...res, abandoned: false }
    resultEye.value = 'done'
    resultLine.value = personaLine(early ? 'focus_early' : 'focus_done', prefs.value.strictness, {
      task: res.session.task,
      minutes: res.session.actual_min,
    })
    mode.value = 'result'
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '结算失败', icon: 'none' })
  } finally {
    busy.value = false
  }
}

function onAbandon() {
  if (busy.value) return
  uni.showModal({
    title: '放弃这一场',
    content: '放弃后不计点数，已用的时间仍会记入统计。',
    confirmText: '放弃',
    confirmColor: tokens.value.danger,
    success: async (res) => {
      if (!res.confirm) return
      busy.value = true
      try {
        const out = await focus.abandonFocus()
        stopTimer()
        result.value = { ...out, abandoned: true }
        resultEye.value = 'abandon'
        resultLine.value = personaLine('focus_abandon', prefs.value.strictness, {
          task: out.session.task,
        })
        mode.value = 'result'
        if (abandonTimer) clearTimeout(abandonTimer)
        abandonTimer = setTimeout(() => {
          resultEye.value = 'idle'
        }, 1500)
      } catch (e) {
        uni.showToast({ title: (e && e.message) || '操作失败', icon: 'none' })
      } finally {
        busy.value = false
      }
    },
  })
}

function back() {
  uni.navigateBack()
}

// 保证首次进入时 circle 尺寸已按屏幕换算
nextTick(() => {
  try {
    circleSize.value = Math.min(260, Math.max(180, uni.upx2px(440)))
  } catch (e) {}
})
</script>

<!-- scoped 防止跨页面同名按钮样式互相覆盖 -->
<style scoped>
.focus-page {
  min-height: 100vh;
  background: var(--ik-bg);
}
.focus-scroll {
  height: 100vh;
}
.focus-body {
  padding: 40rpx 32rpx calc(48rpx + env(safe-area-inset-bottom));
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  align-items: stretch;
}
.focus-eye {
  display: flex;
  justify-content: center;
  margin: 8rpx 0 4rpx;
}
.focus-slogan {
  text-align: center;
  font-size: 26rpx;
  color: var(--ik-t3);
  margin-bottom: 28rpx;
}
.focus-card {
  background: var(--ik-card);
  border-radius: var(--ik-radius);
  padding: 30rpx 28rpx;
  margin-top: 24rpx;
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
.field-hint {
  display: block;
  margin-top: 18rpx;
  font-size: 22rpx;
  line-height: 1.6;
  color: var(--ik-t3);
  text-align: center;
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
  background: transparent;
}
.chip.is-active {
  border-color: var(--ik-primary);
  color: var(--ik-primary);
  background: var(--ik-primary-weak);
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
.primary-btn {
  width: 100%;
  margin: 28rpx 0 0;
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
.primary-btn.flex1 {
  flex: 1;
  width: auto;
  margin-top: 0;
}
.ghost-btn {
  flex: 1;
  margin: 0;
  height: 80rpx;
  line-height: 80rpx;
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
  margin: 20rpx 0 0;
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
.circle-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-top: 4rpx;
}
.circle-caption {
  margin-top: 14rpx;
  font-size: 26rpx;
  color: var(--ik-t2);
  text-align: center;
}
.task-line {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16rpx;
}
.task-name {
  font-size: 32rpx;
  font-weight: 700;
  color: var(--ik-t1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.task-plan {
  flex: 0 0 auto;
  font-size: 22rpx;
  color: var(--ik-t3);
}
.due-banner {
  margin-top: 18rpx;
  padding: 14rpx 18rpx;
  border-radius: 16rpx;
  background: var(--ik-soft);
  color: var(--ik-danger);
  font-size: 24rpx;
  text-align: center;
}
.action-row {
  display: flex;
  gap: 16rpx;
  margin-top: 24rpx;
}
.result-title {
  margin-top: 16rpx;
  text-align: center;
  font-size: 36rpx;
  font-weight: 700;
  color: var(--ik-t1);
}
.result-points {
  margin-top: 10rpx;
  text-align: center;
  font-size: 48rpx;
  font-weight: 800;
  color: var(--ik-success);
}
.result-line {
  margin-top: 6rpx;
  text-align: center;
  font-size: 26rpx;
  color: var(--ik-t2);
  padding: 0 32rpx;
}
.result-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14rpx 0;
  border-bottom: 1rpx solid var(--ik-line);
}
.result-row:last-of-type {
  border-bottom: none;
}
.result-label {
  font-size: 26rpx;
  color: var(--ik-t2);
}
.result-value {
  font-size: 26rpx;
  color: var(--ik-t1);
  max-width: 60%;
  text-align: right;
}
.ellipsis {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
