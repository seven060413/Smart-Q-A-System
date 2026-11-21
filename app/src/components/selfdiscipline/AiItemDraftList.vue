<template>
  <view class="draft-card">
    <view class="draft-head">
      <text class="draft-title">{{ done ? '已加入今日事项' : '确认后添加' }}</text>
      <text v-if="source === 'local' && !done" class="draft-source">离线规则整理，请检查</text>
    </view>

    <template v-if="done">
      <view v-for="(item, index) in drafts" :key="'done-' + index" class="done-row">
        <text class="done-title">{{ item.title }}</text>
        <text class="done-meta">{{ repeatLabel(item) }}{{ item.remind_time ? ` · ${item.remind_time}` : ' · 不提醒' }}</text>
      </view>
    </template>

    <template v-else>
      <view v-for="(item, index) in drafts" :key="index" class="draft-row">
        <wd-input v-model="item.title" placeholder="事项标题" :maxlength="60" clearable />

        <view class="chip-row">
          <text
            v-for="mode in modes"
            :key="mode.key"
            class="chip"
            :class="{ 'is-active': modeOf(item) === mode.key }"
            @click="setMode(item, mode.key)"
          >{{ mode.label }}</text>
          <text v-if="modeOf(item) === 'custom'" class="custom">{{ customLabel(item) }}</text>
        </view>

        <view class="meta-row">
          <text class="time" @click="openTime(index)">
            {{ item.remind_time ? `提醒 ${item.remind_time}` : '不提醒' }}
          </text>
          <text v-if="item.remind_time" class="clear" @click="item.remind_time = ''">清除</text>
          <text v-if="item.kind === 'once' && item.date" class="date">{{ dateLabel(item.date) }}</text>
          <text class="del" @click="removeDraft(index)">删除</text>
        </view>
      </view>

      <button class="confirm-btn" :disabled="busy || !valid" @click="confirm">
        {{ busy ? '正在添加…' : `添加到今日事项 ${drafts.length} 项` }}
      </button>
    </template>

    <wd-datetime-picker
      :model-value="pickerValue"
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
import { computed, ref } from 'vue'
import { dateKey, formatMonthDay, parseHHmm } from '../../selfdiscipline/dates.js'

const props = defineProps({
  items: { type: Array, default: () => [] },
  source: { type: String, default: 'ai' },
  done: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
})

const emit = defineEmits(['confirm'])

const modes = [
  { key: 'once', label: '仅今天' },
  { key: 'daily', label: '每天' },
  { key: 'workday', label: '工作日' },
]

function cloneDraft(raw) {
  const kind = raw && raw.kind === 'once' ? 'once' : 'daily'
  const days = Array.isArray(raw && raw.days)
    ? raw.days.map(Number).filter((n) => n >= 1 && n <= 7)
    : []
  const remind = String((raw && raw.remind_time) || '').trim()
  return {
    title: String((raw && raw.title) || '').trim(),
    note: String((raw && raw.note) || '').trim(),
    kind,
    days: kind === 'once' ? [] : days.length ? days : [1, 2, 3, 4, 5, 6, 7],
    date: kind === 'once' ? String((raw && raw.date) || dateKey(Date.now())) : '',
    remind_time: /^([01]\d|2[0-3]):[0-5]\d$/.test(remind) ? remind : '',
    enabled: true,
  }
}

const drafts = ref((props.items || []).map(cloneDraft))
const timePickerVisible = ref(false)
const timePickerIndex = ref(-1)
const pickerValue = ref('09:00')

const valid = computed(
  () => drafts.value.length > 0 && drafts.value.every((item) => String(item.title || '').trim())
)

function modeOf(item) {
  if (item.kind === 'once') return 'once'
  const days = [...item.days].sort((a, b) => a - b).join(',')
  if (days === '1,2,3,4,5,6,7') return 'daily'
  if (days === '1,2,3,4,5') return 'workday'
  return 'custom'
}

function customLabel(item) {
  const labels = ['一', '二', '三', '四', '五', '六', '日']
  return item.days
    .slice()
    .sort((a, b) => a - b)
    .map((day) => `周${labels[day - 1]}`)
    .join('、')
}

function repeatLabel(item) {
  const mode = modeOf(item)
  if (mode === 'once') return item.date ? dateLabel(item.date) : '仅今天'
  if (mode === 'daily') return '每天'
  if (mode === 'workday') return '工作日'
  return customLabel(item)
}

function setMode(item, mode) {
  if (mode === 'once') {
    item.kind = 'once'
    item.days = []
    item.date = item.date || dateKey(Date.now())
    return
  }
  item.kind = 'daily'
  item.date = ''
  item.days = mode === 'workday' ? [1, 2, 3, 4, 5] : [1, 2, 3, 4, 5, 6, 7]
}

function dateLabel(value) {
  const ms = parseHHmm(value, '00:00')
  if (value === dateKey(Date.now())) return '今天'
  if (value === dateKey(Date.now() + 86400000)) return '明天'
  return ms ? formatMonthDay(ms) : value
}

function openTime(index) {
  timePickerIndex.value = index
  const item = drafts.value[index]
  pickerValue.value = (item && item.remind_time) || '09:00'
  timePickerVisible.value = true
}

function onTimeConfirm(event) {
  timePickerVisible.value = false
  const value = event && event.value ? String(event.value) : ''
  const index = timePickerIndex.value
  if (value && index >= 0 && drafts.value[index]) {
    drafts.value[index].remind_time = value
  }
  timePickerIndex.value = -1
}

function removeDraft(index) {
  drafts.value.splice(index, 1)
}

function confirm() {
  if (props.busy || !valid.value) return
  emit(
    'confirm',
    drafts.value.map((item) => ({
      ...item,
      title: item.title.trim(),
      days: [...item.days],
    }))
  )
}
</script>

<style scoped>
.draft-card {
  margin-top: 10rpx;
  padding: 18rpx;
  border-radius: 18rpx;
  background: var(--ik-soft);
  box-sizing: border-box;
}
.draft-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10rpx;
}
.draft-title {
  font-size: 24rpx;
  font-weight: 600;
  color: var(--ik-t1);
}
.draft-source {
  font-size: 19rpx;
  color: var(--ik-t3);
}
.draft-row {
  margin-top: 14rpx;
  padding: 14rpx;
  border-radius: 14rpx;
  background: var(--ik-card);
  border: 1rpx solid var(--ik-line);
}
.chip-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8rpx;
  margin-top: 10rpx;
}
.chip {
  padding: 7rpx 15rpx;
  border-radius: 999rpx;
  border: 1rpx solid var(--ik-line);
  font-size: 20rpx;
  color: var(--ik-t2);
}
.chip.is-active {
  border-color: var(--ik-primary);
  color: var(--ik-primary);
  background: var(--ik-primary-weak);
}
.custom {
  font-size: 20rpx;
  color: var(--ik-t3);
}
.meta-row {
  display: flex;
  align-items: center;
  gap: 12rpx;
  margin-top: 10rpx;
}
.time {
  font-size: 21rpx;
  color: var(--ik-primary);
}
.clear {
  font-size: 19rpx;
  color: var(--ik-t3);
}
.date {
  font-size: 20rpx;
  color: var(--ik-t3);
}
.del {
  margin-left: auto;
  font-size: 21rpx;
  color: var(--ik-danger);
}
.confirm-btn {
  width: 100%;
  margin: 16rpx 0 0;
  height: 68rpx;
  line-height: 68rpx;
  border-radius: 999rpx;
  font-size: 24rpx;
  background: var(--ik-success);
  color: var(--ik-on-primary);
  border: none;
}
.confirm-btn::after {
  border: none;
}
.done-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12rpx;
  padding: 10rpx 0;
  border-bottom: 1rpx solid var(--ik-line);
}
.done-row:last-child {
  border-bottom: none;
}
.done-title {
  font-size: 23rpx;
  color: var(--ik-t1);
}
.done-meta {
  flex: 0 0 auto;
  font-size: 19rpx;
  color: var(--ik-t3);
}
</style>
