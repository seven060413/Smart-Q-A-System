<template>
  <scroll-view class="sd-scroll" scroll-y>
    <view class="sd-page" :style="{ paddingTop: statusBarHeight + 'px' }">
      <view class="sd-head">
        <text class="sd-title">自律</text>
        <text class="sd-date">{{ todayLabel }}</text>
      </view>

      <view v-if="errorText" class="sd-error">{{ errorText }}</view>

      <PersonaCard :line="persona" :hint="personaHint" :state="eyeState" :progress="eyeProgress" />

      <view class="stats-row">
        <StatTile label="今日专注" :value="today.focusMinutes" unit="分" tone="primary" />
        <StatTile
          label="今日打卡"
          :value="`${today.checkinDone}/${today.checkinTotal}`"
          tone="success"
        />
        <StatTile label="当前点数" :value="today.points" tone="default" />
      </view>

      <!-- 进行中的专注 -->
      <view v-if="focusCard" class="sd-card active-card">
        <view class="active-head">
          <text class="active-title">专注中</text>
          <text class="active-time" :class="{ 'is-due': focusCard.due }">
            {{ focusCard.due ? '到点待结算' : focusCard.remaining }}
          </text>
        </view>
        <text class="active-task">{{ focusCard.task }}</text>
        <view class="active-actions">
          <button class="sd-btn ghost" @click="go('focus')">继续</button>
          <button class="sd-btn" @click="go('focus')">结算</button>
        </view>
      </view>

      <!-- 进行中的报备 -->
      <view v-if="reportCard" class="sd-card active-card">
        <view class="active-head">
          <text class="active-title">报备中 · {{ reportCard.target_app }}</text>
          <text class="active-time" :class="{ 'is-due': reportCard.due }">
            {{ reportCard.due ? '已到点' : reportCard.remaining }}
          </text>
        </view>
        <text class="active-task">
          已用 {{ reportCard.used }} / 计划 {{ reportCard.minutes }} 分钟
          <text v-if="reportCard.overdue" class="overdue">已超时</text>
        </text>
        <view class="active-actions">
          <button class="sd-btn ghost" @click="extendReport">延长 5 分钟</button>
          <button class="sd-btn" @click="finishReport">结束</button>
        </view>
      </view>

      <GroupCard title="快捷入口" :items="quickItems" />

      <view class="sd-card">
        <view class="card-head">
          <text class="card-title">今日事项</text>
          <view class="card-actions">
            <text class="card-link" @click="go('assistant')">AI 助手</text>
            <text class="card-link" @click="go('checkin')">查看全部</text>
          </view>
        </view>
        <view v-if="todayItemsPreview.length === 0" class="sd-empty">
          还没有今日事项，手动添加一条，或让 AI 帮你整理。
        </view>
        <view
          v-for="item in todayItemsPreview"
          :key="item.id"
          class="todo-row"
          @click="toggleItem(item)"
        >
          <view class="todo-check" :class="{ 'is-done': item.done }">
            <text v-if="item.done" class="todo-check-mark">✓</text>
          </view>
          <view class="todo-main">
            <text class="todo-title" :class="{ 'is-done': item.done }">{{ item.title }}</text>
            <text v-if="itemSub(item)" class="todo-sub">{{ itemSub(item) }}</text>
          </view>
        </view>
      </view>

      <view class="sd-card">
        <view class="card-head">
          <text class="card-title">最近记录</text>
        </view>
        <view v-if="recent.length === 0" class="sd-empty">还没有记录。先做一件小事？</view>
        <view v-for="row in recent" :key="row.key" class="recent-row">
          <view class="recent-main">
            <text class="recent-title">{{ row.title }}</text>
            <text class="recent-sub">{{ row.subtitle }}</text>
          </view>
          <text v-if="row.points" class="recent-points">+{{ row.points }}</text>
        </view>
      </view>

      <view class="foot-link" @click="go('settings')">设置与提醒权限</view>
      <view class="foot-space"></view>
    </view>
  </scroll-view>
</template>

<script setup>
import { computed, onUnmounted, reactive, ref, watch } from 'vue'
import PersonaCard from './PersonaCard.vue'
import StatTile from './StatTile.vue'
import GroupCard from '../ui/GroupCard.vue'
import * as repo from '../../selfdiscipline/repository.js'
import * as focus from '../../selfdiscipline/focus.js'
import * as reportModule from '../../selfdiscipline/report.js'
import * as checkin from '../../selfdiscipline/checkin.js'
import * as stats from '../../selfdiscipline/stats.js'
import { personaLine } from '../../selfdiscipline/persona.js'
import {
  addDays,
  endOfDay,
  formatClock,
  formatDateTime,
  formatMonthDay,
  startOfDay,
  todayKey
} from '../../selfdiscipline/dates.js'

const props = defineProps({
  refreshKey: { type: Number, default: 0 },
})

const statusBarHeight = (() => {
  try {
    return uni.getSystemInfoSync().statusBarHeight || 0
  } catch (e) {
    return 0
  }
})()

const now = ref(Date.now())
const loading = ref(true)
const errorText = ref('')
const prefs = ref({ strictness: 'A' })
const state = reactive({
  focus: null,
  report: null,
  items: [],
  today: {
    focusMinutes: 0,
    checkinDone: 0,
    checkinTotal: 0,
    points: 0,
  },
  recent: [],
})

let tickTimer = null

// 模板里直接使用 today / recent，避免 state.xxx 的冗长写法。
const today = computed(() => state.today)
const recent = computed(() => state.recent)

const todayLabel = computed(() => formatMonthDay(now.value))

const focusRuntime = computed(() => focus.focusRuntime(state.focus, now.value))
const reportRuntime = computed(() => reportModule.reportRuntime(state.report, now.value))

const focusCard = computed(() => {
  if (!state.focus) return null
  const rt = focusRuntime.value
  return {
    ...state.focus,
    remaining: formatClock(rt.remainingMs),
    due: rt.due,
  }
})

const reportCard = computed(() => {
  if (!state.report) return null
  const rt = reportRuntime.value
  return {
    ...state.report,
    remaining: formatClock(rt.remainingMs),
    used: Math.max(0, Math.floor(rt.usedMs / 60000)),
    due: rt.due,
    overdue: rt.overdue,
  }
})

const todayItemsPreview = computed(() => {
  const list = [...state.items]
  list.sort((a, b) => Number(a.done) - Number(b.done))
  return list.slice(0, 5)
})

const completion = computed(() => checkin.completionOf(state.items))

const eyeState = computed(() => {
  if (focusCard.value) return focusCard.value.due ? 'due' : 'focus'
  if (completion.value.all) return 'done'
  return 'idle'
})

const eyeProgress = computed(() => {
  if (!focusCard.value) return 1
  return focusRuntime.value.ratio
})

const personaHint = computed(() => {
  if (focusCard.value) {
    return focusCard.value.due
      ? '回专注页结算这一段'
      : `还剩 ${focusCard.value.remaining} · ${focusCard.value.task}`
  }
  if (reportCard.value) {
    return reportCard.value.due
      ? `报备的 ${reportCard.value.minutes} 分钟到了`
      : `还剩 ${reportCard.value.remaining} · ${reportCard.value.target_app}`
  }
  if (state.items.length) {
    return `今日打卡 ${completion.value.done}/${completion.value.total}`
  }
  return '先开一场 25 分钟'
})

// 文案只在“事件”变化时更新，避免每秒倒计时刷新时轮换句子。
const personaEvent = computed(() => {
  if (focusCard.value) return focusCard.value.due ? 'focus_done' : 'focus_start'
  if (reportCard.value) return reportCard.value.due ? 'report_due' : 'report_start'
  if (state.items.length) return completion.value.all ? 'checkin_all' : 'checkin_due'
  return 'empty_today'
})

const persona = ref('')

watch(
  [personaEvent, () => prefs.value.strictness],
  () => {
    persona.value = personaLine(personaEvent.value, prefs.value.strictness, {
      task: focusCard.value ? focusCard.value.task : '',
      minutes: reportCard.value ? reportCard.value.minutes : '',
    })
  },
  { immediate: true }
)

function itemSub(item) {
  const parts = []
  if (item.remind_time) parts.push(item.remind_time)
  if (item.note) parts.push(item.note)
  return parts.join(' · ')
}

async function loadRecent() {
  const nowMs = Date.now()
  const from = startOfDay(addDays(nowMs, -6))
  const to = endOfDay(nowMs)
  const [sessions, reports, records, items] = await Promise.all([
    repo.listFocusSessions(from, to),
    repo.listReports(from, to),
    repo.listCheckinRecords(todayKey(addDays(nowMs, -6)), todayKey(nowMs)),
    repo.listCheckinItems(),
  ])
  const titles = new Map(items.map((item) => [item.id, item.title]))
  const rows = []
  for (const row of sessions.slice(0, 4)) {
    rows.push({
      key: `focus:${row.id}`,
      title: row.task || '专注',
      subtitle: `${row.actual_min || 0} 分钟 · ${formatDateTime(Number(row.started_at))}`,
      at: Number(row.started_at),
      points: Number(row.points) || 0,
    })
  }
  for (const row of reports.slice(0, 4)) {
    rows.push({
      key: `report:${row.id}`,
      title: `报备 · ${row.target_app}`,
      subtitle: `${row.minutes} 分钟 · ${formatDateTime(Number(row.started_at))}`,
      at: Number(row.started_at),
      points: Number(row.points) || 0,
    })
  }
  for (const row of records.slice(0, 4)) {
    rows.push({
      key: `checkin:${row.id}`,
      title: titles.get(row.item_id) || '每日打卡',
      subtitle: `打卡 · ${formatDateTime(Number(row.done_at))}`,
      at: Number(row.done_at),
      points: Number(row.points) || 0,
    })
  }
  rows.sort((a, b) => b.at - a.at)
  return rows.slice(0, 3)
}

async function load() {
  loading.value = true
  errorText.value = ''
  try {
    await repo.init()
    await focus.loadRunningFocus()
    const [activeReport, items, today, prefsValue, recent] = await Promise.all([
      reportModule.getActive(Date.now()),
      checkin.todayItems(Date.now()),
      stats.todayStats(Date.now()),
      focus.getPrefs(),
      loadRecent(),
    ])
    state.focus = focus.currentFocusSession()
    state.report = activeReport
    state.items = items
    state.today = today
    prefs.value = prefsValue
    state.recent = recent
    now.value = Date.now()
  } catch (e) {
    errorText.value = (e && e.message) || '加载失败'
  } finally {
    loading.value = false
  }
}

function startTick() {
  stopTick()
  tickTimer = setInterval(() => {
    now.value = Date.now()
  }, 1000)
}

function stopTick() {
  if (tickTimer) {
    clearInterval(tickTimer)
    tickTimer = null
  }
}

watch(
  () => props.refreshKey,
  async () => {
    await load()
    if (state.focus || state.report) startTick()
    else stopTick()
  },
  { immediate: true }
)

onUnmounted(stopTick)

function go(page) {
  uni.navigateTo({ url: `/pages/selfdiscipline/${page}` })
}

async function toggleItem(item) {
  if (!item || !item.done) {
    try {
      await checkin.toggleToday(item)
      await load()
    } catch (e) {
      uni.showToast({ title: (e && e.message) || '操作失败', icon: 'none' })
    }
    return
  }
  uni.showModal({
    title: '撤销打卡',
    content: `撤销「${item.title}」并扣回 5 点？`,
    success: async (res) => {
      if (!res.confirm) return
      try {
        await checkin.toggleToday(item)
        await load()
      } catch (e) {
        uni.showToast({ title: (e && e.message) || '操作失败', icon: 'none' })
      }
    },
  })
}

let reportBusy = false

async function extendReport() {
  if (reportBusy) return
  reportBusy = true
  try {
    await reportModule.extendReport(5)
    await load()
    uni.showToast({ title: '已延长 5 分钟', icon: 'none' })
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '操作失败', icon: 'none' })
  } finally {
    reportBusy = false
  }
}

async function finishReport() {
  if (reportBusy) return
  uni.showModal({
    title: '结束报备',
    content: '确认这次报备完成吗？完成会获得 5 点。',
    confirmText: '完成了',
    cancelText: '再等等',
    success: async (res) => {
      if (!res.confirm) return
      reportBusy = true
      try {
        await reportModule.finishReport(true)
        await load()
      } catch (e) {
        uni.showToast({ title: (e && e.message) || '操作失败', icon: 'none' })
      } finally {
        reportBusy = false
      }
    },
  })
}

const quickItems = [
  { key: 'focus', label: '开始专注', action: () => go('focus') },
  { key: 'report', label: '快速报备', action: () => go('report') },
  { key: 'checkin', label: '今日打卡', action: () => go('checkin') },
  { key: 'stats', label: '统计', action: () => go('stats') },
]
</script>

<!-- scoped 防止跨页面同名按钮样式互相覆盖 -->
<style scoped>
.sd-scroll {
  height: 100%;
  background: var(--ik-bg);
}
.sd-page {
  min-height: 100%;
  padding: 24rpx 32rpx 0;
  box-sizing: border-box;
  background: var(--ik-bg);
}
.sd-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin: 8rpx 0 24rpx;
}
.sd-title {
  font-size: 40rpx;
  font-weight: 700;
  color: var(--ik-t1);
}
.sd-date {
  font-size: 24rpx;
  color: var(--ik-t3);
}
.sd-error {
  background: var(--ik-soft);
  color: var(--ik-danger);
  border-radius: var(--ik-radius);
  padding: 16rpx 20rpx;
  margin-bottom: 20rpx;
  font-size: 24rpx;
}
.stats-row {
  display: flex;
  gap: 16rpx;
  margin-bottom: 24rpx;
}
.sd-card {
  background: var(--ik-card);
  border-radius: var(--ik-radius);
  padding: 28rpx;
  margin-bottom: 24rpx;
  box-sizing: border-box;
}
.active-card {
  border-left: 6rpx solid var(--ik-primary);
}
.active-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.active-title {
  font-size: 28rpx;
  font-weight: 600;
  color: var(--ik-t1);
}
.active-time {
  font-size: 30rpx;
  font-weight: 700;
  color: var(--ik-primary);
}
.active-time.is-due {
  color: var(--ik-danger);
}
.active-task {
  display: block;
  margin-top: 10rpx;
  font-size: 26rpx;
  color: var(--ik-t2);
}
.overdue {
  margin-left: 8rpx;
  color: var(--ik-danger);
}
.active-actions {
  display: flex;
  gap: 16rpx;
  margin-top: 20rpx;
}
.sd-btn {
  flex: 1;
  margin: 0;
  padding: 0;
  height: 72rpx;
  line-height: 72rpx;
  border-radius: 999rpx;
  font-size: 26rpx;
  background: var(--ik-primary);
  color: var(--ik-on-primary);
  border: none;
}
.sd-btn::after {
  border: none;
}
.sd-btn.ghost {
  background: transparent;
  color: var(--ik-primary);
  border: 1rpx solid var(--ik-primary);
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16rpx;
}
.card-title {
  font-size: 28rpx;
  font-weight: 600;
  color: var(--ik-t1);
}
.card-actions {
  display: flex;
  align-items: center;
  gap: 18rpx;
}
.card-link {
  font-size: 24rpx;
  color: var(--ik-primary);
}
.sd-empty {
  font-size: 26rpx;
  color: var(--ik-t3);
  line-height: 1.6;
  padding: 8rpx 0;
}
.todo-row {
  display: flex;
  align-items: center;
  padding: 16rpx 0;
  border-bottom: 1rpx solid var(--ik-line);
}
.todo-row:last-child {
  border-bottom: none;
}
.todo-check {
  width: 40rpx;
  height: 40rpx;
  border-radius: 50%;
  border: 2rpx solid var(--ik-line);
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
}
.todo-check.is-done {
  background: var(--ik-success);
  border-color: var(--ik-success);
}
.todo-check-mark {
  font-size: 24rpx;
  color: var(--ik-on-primary);
  line-height: 1;
}
.todo-main {
  flex: 1;
  min-width: 0;
  margin-left: 18rpx;
  display: flex;
  flex-direction: column;
}
.todo-title {
  font-size: 28rpx;
  color: var(--ik-t1);
}
.todo-title.is-done {
  color: var(--ik-t3);
  text-decoration: line-through;
}
.todo-sub {
  margin-top: 4rpx;
  font-size: 22rpx;
  color: var(--ik-t3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.recent-row {
  display: flex;
  align-items: center;
  padding: 16rpx 0;
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
.foot-link {
  text-align: center;
  font-size: 26rpx;
  color: var(--ik-primary);
  padding: 18rpx 0 12rpx;
}
.foot-space {
  height: calc(24rpx + env(safe-area-inset-bottom));
}
</style>
