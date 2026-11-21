<template>
  <view class="checkin-page theme-root" :class="{ 'is-dark': isDark }" :style="themeVars">
    <ThemeBackground />
    <scroll-view class="checkin-scroll" scroll-y>
      <view class="checkin-body">
        <view class="head-card">
          <view class="head-row">
            <text class="head-date">{{ todayLabel }}</text>
            <text class="head-count">{{ completion.done }}/{{ completion.total }}</text>
          </view>
          <view class="progress-track">
            <view
              class="progress-fill"
              :style="{ width: Math.round(completion.ratio * 100) + '%' }"
            ></view>
          </view>
          <text v-if="completion.all" class="all-banner">今日清空。没有欠账。</text>
          <text v-else-if="completion.total" class="head-hint">
            还有 {{ completion.total - completion.done }} 项没划掉。
          </text>
          <text v-else class="head-hint">今天没有安排。先加一条。</text>
        </view>

        <view class="list-card">
          <view class="card-head">
            <text class="card-title">今日清单</text>
          </view>
          <view v-if="!items.length" class="empty">还没有今日事项，手动添加一条，或让 AI 帮你整理。</view>
          <view v-for="item in items" :key="item.id" class="today-row" @click="toggle(item)">
            <view class="check" :class="{ 'is-done': item.done }">
              <text v-if="item.done" class="check-mark">✓</text>
            </view>
            <view class="row-main">
              <text class="row-title" :class="{ 'is-done': item.done }">{{ item.title }}</text>
              <text v-if="itemSub(item)" class="row-sub">{{ itemSub(item) }}</text>
            </view>
            <text class="row-tag" v-if="item.kind === 'once'">仅今天</text>
            <text class="row-tag" v-if="item.remind_time">{{ item.remind_time }}</text>
          </view>
        </view>

        <view class="list-card">
          <view class="card-head">
            <text class="card-title">事项管理</text>
            <text class="card-link" @click="openAdd">+ 添加事项</text>
          </view>
          <view v-if="!allItems.length" class="empty">还没有事项。</view>
          <view v-for="item in allItems" :key="item.id" class="manage-row">
            <view class="row-main" @click="openEdit(item)">
              <text class="row-title" :class="{ 'is-disabled': !item.enabled }">{{ item.title }}</text>
              <text class="row-sub">{{ manageSub(item) }}</text>
            </view>
            <wd-switch
              :model-value="item.enabled"
              size="20px"
              @change="(e) => onToggleEnabled(item, e.value)"
            />
            <text class="edit-link" @click="openEdit(item)">编辑</text>
          </view>
        </view>

        <button class="primary-btn" @click="openAdd">+ 添加今日事项</button>

        <!-- 编辑/新增面板 -->
        <view v-if="editorVisible" class="list-card editor-card">
          <view class="card-head">
            <text class="card-title">{{ editor.id ? '编辑事项' : '新增事项' }}</text>
            <text class="card-link" @click="closeEditor">取消</text>
          </view>

          <text class="field-label">标题</text>
          <wd-input v-model="editor.title" placeholder="例如：背 20 个单词" :maxlength="30" clearable />

          <text class="field-label field-gap">备注（可选）</text>
          <wd-input v-model="editor.note" placeholder="写一句提醒自己的话" :maxlength="60" clearable />

          <text class="field-label field-gap">提醒时间</text>
          <view class="time-cell" @click="timePickerVisible = true">
            <text class="time-value">{{ editor.remindTime || '不提醒' }}</text>
            <text class="time-action">{{ editor.remindTime ? '修改' : '选择' }}</text>
          </view>
          <text
            v-if="editor.remindTime"
            class="clear-time"
            @click="editor.remindTime = ''"
          >清除提醒时间</text>

          <text class="field-label field-gap">类型</text>
          <view class="chip-row">
            <view
              class="day-chip"
              :class="{ 'is-active': editor.kind === 'once' }"
              @click="setEditorKind('once')"
            >仅今天</view>
            <view
              class="day-chip"
              :class="{ 'is-active': editor.kind === 'daily' }"
              @click="setEditorKind('daily')"
            >每日重复</view>
          </view>
          <text v-if="editor.kind === 'once'" class="once-date">
            日期：{{ editorDateLabel }}
          </text>

          <template v-if="editor.kind !== 'once'">
            <text class="field-label field-gap">重复</text>
            <view class="chip-row">
              <view
                v-for="day in 7"
                :key="day"
                class="day-chip"
                :class="{ 'is-active': editor.days.includes(day) }"
                @click="toggleDay(day)"
              >
                周{{ dayLabel(day) }}
              </view>
            </view>
          </template>

          <view class="switch-row">
            <text class="field-label inline">启用</text>
            <wd-switch v-model="editor.enabled" size="20px" />
          </view>

          <button class="primary-btn" :disabled="saving" @click="save">
            {{ saving ? '保存中…' : '保存' }}
          </button>
          <button v-if="editor.id" class="danger-btn" @click="removeCurrent">删除事项</button>
        </view>

        <text class="foot-hint">
          打卡提醒会为未来 7 天排好；删除事项会取消它未来的提醒，历史记录保留。
        </text>
      </view>
    </scroll-view>

    <wd-datetime-picker
      :model-value="editor.remindTime || '09:00'"
      :visible="timePickerVisible"
      root-portal
      type="time"
      title="选择提醒时间"
      @update:visible="timePickerVisible = $event"
      @confirm="onTimeConfirm"
      @cancel="timePickerVisible = false"
    />
  </view>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { isDark, themeVars, tokens, applyNativeNavigationBar } from '../../theme/theme.js'
import * as repo from '../../selfdiscipline/repository.js'
import * as checkin from '../../selfdiscipline/checkin.js'
import {
  dateKey,
  formatMonthDay,
  weekdayLabel,
  WEEKDAY_LABELS,
} from '../../selfdiscipline/dates.js'

const items = ref([])
const allItems = ref([])
const now = ref(Date.now())
const editorVisible = ref(false)
const timePickerVisible = ref(false)
const saving = ref(false)

const editor = reactive({
  id: '',
  title: '',
  note: '',
  remindTime: '',
  days: [...checkin.ALL_DAYS],
  kind: 'daily',
  date: '',
  enabled: true,
})

const completion = computed(() => checkin.completionOf(items.value))
const todayLabel = computed(() => formatMonthDay(now.value))

const editorDateLabel = computed(() => {
  const value = editor.kind === 'once' ? editor.date || dateKey(now.value) : ''
  if (!value) return ''
  const today = dateKey(now.value)
  if (value === today) return '今天'
  if (value === dateKey(now.value + 86400000)) return '明天'
  return value.slice(5).replace('-', '/')
})

function shortDate(value) {
  if (!value) return ''
  const today = dateKey(now.value)
  if (value === today) return '今天'
  if (value === dateKey(now.value + 86400000)) return '明天'
  return value.slice(5).replace('-', '/')
}

function dayLabel(day) {
  return weekdayLabel(day)
}

function itemSub(item) {
  const parts = []
  if (item.note) parts.push(item.note)
  return parts.join(' · ')
}

function daysText(days) {
  const list = Array.isArray(days) ? days : []
  if (list.length === 7) return '每天'
  if (!list.length) return '不重复'
  return list
    .slice()
    .sort((a, b) => a - b)
    .map((day) => `周${WEEKDAY_LABELS[day - 1]}`)
    .join(' ')
}

function manageSub(item) {
  const parts = []
  if (item.kind === 'once') parts.push(item.date ? `仅 ${shortDate(item.date)}` : '仅一次')
  else parts.push(daysText(item.days))
  if (item.remind_time) parts.push(item.remind_time)
  if (!item.enabled) parts.push('已停用')
  return parts.join(' · ')
}

async function load() {
  await repo.init()
  now.value = Date.now()
  const [todayList, every] = await Promise.all([checkin.todayItems(now.value), checkin.listItems()])
  items.value = todayList
  allItems.value = every
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

async function toggle(item) {
  if (!item.done) {
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

function resetEditor() {
  editor.id = ''
  editor.title = ''
  editor.note = ''
  editor.remindTime = ''
  editor.days = [...checkin.ALL_DAYS]
  editor.kind = 'daily'
  editor.date = ''
  editor.enabled = true
}

function setEditorKind(kind) {
  editor.kind = kind === 'once' ? 'once' : 'daily'
  if (editor.kind === 'once') {
    editor.date = editor.date || dateKey(now.value)
  } else {
    editor.date = ''
    if (!editor.days.length) editor.days = [...checkin.ALL_DAYS]
  }
}


function openAdd() {
  resetEditor()
  editorVisible.value = true
}

function openEdit(item) {
  editor.id = item.id
  editor.title = item.title
  editor.note = item.note || ''
  editor.remindTime = item.remind_time || ''
  editor.days = Array.isArray(item.days) ? [...item.days] : [...checkin.ALL_DAYS]
  editor.kind = item.kind === 'once' ? 'once' : 'daily'
  editor.date = item.date || ''
  editor.enabled = item.enabled !== false
  editorVisible.value = true
}

function closeEditor() {
  editorVisible.value = false
  timePickerVisible.value = false
}

function toggleDay(day) {
  if (editor.days.includes(day)) {
    editor.days = editor.days.filter((value) => value !== day)
  } else {
    editor.days = [...editor.days, day].sort((a, b) => a - b)
  }
}

function onTimeConfirm(event) {
  timePickerVisible.value = false
  const value = event && event.value ? String(event.value) : ''
  if (value) editor.remindTime = value
}

async function save() {
  if (saving.value) return
  if (!editor.title.trim()) {
    uni.showToast({ title: '请填写事项标题', icon: 'none' })
    return
  }
  if (editor.kind !== 'once' && !editor.days.length) {
    uni.showToast({ title: '至少选择一天', icon: 'none' })
    return
  }
  saving.value = true
  try {
    await checkin.saveItem({
      id: editor.id || undefined,
      title: editor.title,
      note: editor.note,
      remind_time: editor.remindTime,
      days: editor.days,
      kind: editor.kind,
      date: editor.kind === 'once' ? editor.date || dateKey(now.value) : '',
      enabled: editor.enabled,
    })
    closeEditor()
    await load()
    uni.showToast({ title: '已保存', icon: 'none' })
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '保存失败', icon: 'none' })
  } finally {
    saving.value = false
  }
}

function removeCurrent() {
  if (!editor.id) return
  const id = editor.id
  uni.showModal({
    title: '删除事项',
    content: '未来的提醒会取消，历史打卡记录保留。',
    confirmText: '删除',
    confirmColor: tokens.value.danger,
    success: async (res) => {
      if (!res.confirm) return
      try {
        await checkin.removeItem(id)
        closeEditor()
        await load()
      } catch (e) {
        uni.showToast({ title: (e && e.message) || '删除失败', icon: 'none' })
      }
    },
  })
}

async function onToggleEnabled(item, value) {
  try {
    await checkin.setEnabled(item.id, !!value)
    await load()
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '操作失败', icon: 'none' })
  }
}

</script>

<!-- scoped 防止跨页面同名按钮样式互相覆盖 -->
<style scoped>
.checkin-page {
  min-height: 100vh;
  background: var(--ik-bg);
}
.checkin-scroll {
  height: 100vh;
}
.checkin-body {
  padding: 32rpx 32rpx calc(48rpx + env(safe-area-inset-bottom));
  box-sizing: border-box;
}
.head-card,
.list-card {
  background: var(--ik-card);
  border-radius: var(--ik-radius);
  padding: 28rpx;
  margin-bottom: 24rpx;
  box-sizing: border-box;
}
.head-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}
.head-date {
  font-size: 32rpx;
  font-weight: 700;
  color: var(--ik-t1);
}
.head-count {
  font-size: 30rpx;
  font-weight: 700;
  color: var(--ik-primary);
}
.progress-track {
  margin-top: 18rpx;
  height: 16rpx;
  border-radius: 999rpx;
  background: var(--ik-soft);
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  border-radius: 999rpx;
  background: var(--ik-success);
  transition: width 0.3s ease;
}
.all-banner {
  display: block;
  margin-top: 16rpx;
  font-size: 26rpx;
  font-weight: 600;
  color: var(--ik-success);
  text-align: center;
}
.head-hint {
  display: block;
  margin-top: 14rpx;
  font-size: 24rpx;
  color: var(--ik-t3);
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
.card-link {
  font-size: 24rpx;
  color: var(--ik-primary);
}
.empty {
  font-size: 26rpx;
  color: var(--ik-t3);
  padding: 8rpx 0;
}
.today-row {
  display: flex;
  align-items: center;
  padding: 16rpx 0;
  border-bottom: 1rpx solid var(--ik-line);
}
.today-row:last-child {
  border-bottom: none;
}
.check {
  width: 42rpx;
  height: 42rpx;
  border-radius: 50%;
  border: 2rpx solid var(--ik-line);
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
}
.check.is-done {
  background: var(--ik-success);
  border-color: var(--ik-success);
}
.check-mark {
  color: var(--ik-on-primary);
  font-size: 24rpx;
  line-height: 1;
}
.row-main {
  flex: 1;
  min-width: 0;
  margin-left: 18rpx;
  display: flex;
  flex-direction: column;
}
.row-title {
  font-size: 28rpx;
  color: var(--ik-t1);
}
.row-title.is-done {
  color: var(--ik-t3);
  text-decoration: line-through;
}
.row-title.is-disabled {
  color: var(--ik-t3);
}
.row-sub {
  margin-top: 4rpx;
  font-size: 22rpx;
  color: var(--ik-t3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.row-tag {
  flex: 0 0 auto;
  margin-left: 12rpx;
  font-size: 22rpx;
  color: var(--ik-primary);
}
.manage-row {
  display: flex;
  align-items: center;
  gap: 14rpx;
  padding: 16rpx 0;
  border-bottom: 1rpx solid var(--ik-line);
}
.manage-row:last-child {
  border-bottom: none;
}
.manage-row .row-main {
  margin-left: 0;
}
.edit-link {
  flex: 0 0 auto;
  font-size: 24rpx;
  color: var(--ik-primary);
}
.primary-btn {
  width: 100%;
  margin: 0 0 24rpx;
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
.danger-btn {
  width: 100%;
  margin: 16rpx 0 0;
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
.editor-card {
  margin-top: 8rpx;
}
.field-label {
  display: block;
  font-size: 24rpx;
  font-weight: 600;
  color: var(--ik-t2);
  margin-bottom: 12rpx;
}
.field-label.inline {
  margin: 0;
}
.field-gap {
  margin-top: 24rpx;
}
.once-date {
  display: block;
  margin-top: 10rpx;
  font-size: 22rpx;
  color: var(--ik-t3);
}
.time-cell {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 76rpx;
  padding: 0 20rpx;
  border-radius: 16rpx;
  background: var(--ik-input-bg);
  border: 1rpx solid var(--ik-line);
}
.time-value {
  font-size: 28rpx;
  color: var(--ik-t1);
}
.time-action {
  font-size: 24rpx;
  color: var(--ik-primary);
}
.clear-time {
  display: block;
  margin-top: 10rpx;
  font-size: 22rpx;
  color: var(--ik-t3);
}
.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12rpx;
}
.day-chip {
  padding: 12rpx 20rpx;
  border-radius: 999rpx;
  border: 1rpx solid var(--ik-line);
  font-size: 24rpx;
  color: var(--ik-t2);
}
.day-chip.is-active {
  border-color: var(--ik-primary);
  color: var(--ik-primary);
  background: var(--ik-primary-weak);
}
.switch-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 24rpx;
  margin-bottom: 4rpx;
}
.foot-hint {
  display: block;
  margin-top: 6rpx;
  font-size: 22rpx;
  line-height: 1.6;
  color: var(--ik-t3);
  text-align: center;
}
</style>
