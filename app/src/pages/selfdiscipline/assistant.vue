<template>
  <view class="assistant-page theme-root" :class="{ 'is-dark': isDark }" :style="themeVars">
    <ThemeBackground />
    <view class="assistant-head">
      <EyeGaze :state="headerEye" :size="190" />
      <text class="head-line">{{ headLine }}</text>
    </view>

    <scroll-view
      class="chat-scroll"
      scroll-y
      :scroll-into-view="scrollTo"
      scroll-with-animation
    >
      <view class="chat-inner">
        <view
          v-for="msg in messages"
          :id="'msg-' + msg.id"
          :key="msg.id"
          class="msg-row"
          :class="msg.role"
        >
          <view v-if="msg.role === 'assistant'" class="avatar">它</view>

          <view class="msg-body" :class="{ 'has-draft': msg.items && msg.items.length }">
            <view class="bubble" :class="msg.role">
              <text v-if="msg.pending" class="typing">正在整理…</text>
              <template v-else>
                <text v-if="msg.text" class="msg-text">{{ msg.text }}</text>
                <AiItemDraftList
                  v-if="msg.items && msg.items.length"
                  :items="msg.items"
                  :source="msg.source"
                  :done="msg.added"
                  :busy="msg.adding"
                  @confirm="onConfirm(msg, $event)"
                />
                <text v-if="msg.error" class="msg-error">{{ msg.error }}</text>
              </template>
            </view>
          </view>

          <view v-if="msg.role === 'user'" class="avatar user-avatar">我</view>
        </view>

        <view v-if="!loggedIn" class="login-card">
          <text class="login-title">登录后才能使用 AI 助手</text>
          <text class="login-sub">手动添加事项不受影响，可以在打卡页继续使用。</text>
          <button class="login-btn" @click="goLogin">去登录</button>
        </view>

        <view id="chat-bottom" class="chat-bottom"></view>
      </view>
    </scroll-view>

    <view class="composer">
      <view v-if="voiceState === 'recording'" class="record-row">
        <text class="record-text">{{ voiceWillCancel ? '松开取消' : `正在录音 · ${voiceSeconds}s` }}</text>
        <text class="record-cancel" @click="cancelVoice">取消</text>
      </view>
      <view v-else-if="voiceState === 'uploading'" class="record-row">
        <text class="record-text subtle">正在识别…</text>
      </view>
      <view v-else-if="voiceState === 'starting'" class="record-row">
        <text class="record-text subtle">正在准备…</text>
      </view>

      <view class="input-row">
        <textarea
          v-model="draftText"
          class="chat-input"
          :disabled="!loggedIn || sending"
          :auto-height="true"
          :maxlength="500"
          placeholder="说说今天要做什么…"
          confirm-type="send"
          @confirm="send"
        />
        <button
          class="voice-btn"
          :class="{ 'is-recording': voiceState === 'recording', 'will-cancel': voiceWillCancel }"
          :disabled="!loggedIn || sending || voiceState === 'uploading'"
          aria-label="按住说话，松开发送"
          @touchstart.stop.prevent="onVoiceStart"
          @touchmove.stop.prevent="onVoiceMove"
          @touchend.stop.prevent="onVoiceEnd"
          @touchcancel.stop.prevent="onVoiceCancel"
          @mousedown.stop.prevent="onVoiceStart"
          @mousemove.stop.prevent="onVoiceMove"
          @mouseup.stop.prevent="onVoiceEnd"
          @mouseleave="onVoiceMouseLeave"
        >
          <VoiceWaveIcon />
        </button>
        <button
          class="send-btn"
          :disabled="!loggedIn || sending || !draftText.trim()"
          @click="send"
        >发送</button>
      </view>
    </view>
  </view>
</template>

<script setup>
import { computed, nextTick, ref } from 'vue'
import { onHide, onShow } from '@dcloudio/uni-app'
import EyeGaze from '../../components/selfdiscipline/EyeGaze.vue'
import VoiceWaveIcon from '../../components/ui/VoiceWaveIcon.vue'
import AiItemDraftList from '../../components/selfdiscipline/AiItemDraftList.vue'
import { isDark, themeVars, applyNativeNavigationBar } from '../../theme/theme.js'
import { store } from '../../store.js'
import { parseSelfDisciplineItems } from '../../api.js'
import * as checkin from '../../selfdiscipline/checkin.js'
import * as focus from '../../selfdiscipline/focus.js'
import { dateKey, formatHm, weekdayIso } from '../../selfdiscipline/dates.js'
import { useVoiceInput } from '../../voice-input.js'

const messages = ref([])
const draftText = ref('')
const scrollTo = ref('')
const sending = ref(false)
const headerEye = ref('idle')
const headLine = ref('告诉我今天要做什么，我整理成事项给你确认。')
let seq = 0
let strictness = 'A'

const loggedIn = computed(() => !!(store.auth.user && store.auth.token))

const {
  supported: voiceSupported,
  state: voiceState,
  seconds: voiceSeconds,
  start: startVoice,
  finish: finishVoice,
  cancel: cancelVoice,
} = useVoiceInput((text) => {
  const current = draftText.value.trim()
  draftText.value = current ? `${current} ${text}` : text
  uni.showToast({ title: '识别完成，正在发送', icon: 'none' })
  scrollBottom()
  send()
})

// 按住说话：上滑超过阈值松手即取消
const voiceWillCancel = ref(false)
let voiceStartY = 0

function newId() {
  seq += 1
  return `${Date.now()}_${seq}`
}

// 明确的取消/闲聊短语在本地短路，避免被模型当成待办标题。
const CANCEL_PHRASES = new Set([
  '不用',
  '不用了',
  '不用啦',
  '算了',
  '取消',
  '不要了',
  '不做了',
  '不加了',
  '没有了',
  '没了',
  '先不了',
  '先不加了',
  '那不用了',
  '这个不用了',
  '还是不用了',
  '先放着',
  '先放着吧',
  '再说吧',
  '以后再说',
  '先这样',
  '暂时不用',
  '先不弄了',
  '暂时不要',
])

const CHAT_PHRASES = new Set([
  '谢谢',
  '多谢',
  '好的',
  '好',
  '嗯',
  '你好',
  '您好',
  '在吗',
  'hi',
  'hello',
  'ok',
])

function normalizePhrase(text) {
  return String(text || '').replace(/[。！!？?，,、\s]/g, '')
}

function pendingDraftMessage() {
  for (let i = messages.value.length - 1; i >= 0; i -= 1) {
    const msg = messages.value[i]
    if (msg.role === 'assistant' && msg.items && msg.items.length && !msg.added) return msg
  }
  return null
}

function handleLocalIntent(text) {
  const phrase = normalizePhrase(text)
  if (CANCEL_PHRASES.has(phrase)) {
    const draft = pendingDraftMessage()
    if (draft) {
      draft.items = null
      draft.text = '这一项已取消。'
      return '好，这件不加了。'
    }
    return '好。'
  }
  if (CHAT_PHRASES.has(phrase)) {
    if (phrase === '谢谢' || phrase === '多谢') return '不客气。'
    return '嗯，我在。要说今天做什么吗？'
  }
  return ''
}

function pushWelcome() {
  messages.value.push({
    id: newId(),
    role: 'assistant',
    text:
      strictness === 'B'
        ? '说。我整理成事项，你确认。要有提醒就说时间。'
        : '告诉我今天要做什么。我会先整理成事项，等你确认后再添加；需要提醒，就把时间一起说出来。',
    items: null,
  })
}

function timezoneName() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Shanghai'
  } catch (e) {
    return 'Asia/Shanghai'
  }
}

function normalizeItems(items) {
  return (items || [])
    .map((raw) => {
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
    })
    .filter((item) => item.title)
}

async function scrollBottom() {
  scrollTo.value = ''
  await nextTick()
  scrollTo.value = 'chat-bottom'
}

onShow(async () => {
  applyNativeNavigationBar()
  if (!messages.value.length) {
    try {
      const prefs = await focus.getPrefs()
      strictness = prefs.strictness
      headLine.value =
        strictness === 'B'
          ? '说。我把它变成事项。'
          : '告诉我今天要做什么，我整理成事项给你确认。'
    } catch (e) {}
    pushWelcome()
  }
  await scrollBottom()
})

onHide(() => {
  voiceWillCancel.value = false
  if (voiceState.value === 'recording' || voiceState.value === 'starting') cancelVoice()
})

function requireLogin() {
  if (loggedIn.value) return true
  uni.showModal({
    title: '需要登录',
    content: '登录后才能使用 AI 助手；手动添加事项不需要登录。',
    confirmText: '去登录',
    success: (res) => {
      if (res.confirm) goLogin()
    },
  })
  return false
}

function goLogin() {
  uni.navigateTo({ url: '/pages/auth/auth' })
}

async function send() {
  if (sending.value) return
  const text = draftText.value.trim()
  if (!text) return
  if (!requireLogin()) return

  // 取消/闲聊不调用模型，也不会生成待办。
  const localReply = handleLocalIntent(text)
  if (localReply) {
    messages.value.push({ id: newId(), role: 'user', text })
    messages.value.push({ id: newId(), role: 'assistant', text: localReply })
    draftText.value = ''
    await scrollBottom()
    return
  }

  const userMessage = { id: newId(), role: 'user', text }
  const pendingId = newId()
  messages.value.push(userMessage)
  messages.value.push({ id: pendingId, role: 'assistant', pending: true })
  draftText.value = ''
  sending.value = true
  headerEye.value = 'focus'
  await scrollBottom()

  try {
    const now = Date.now()
    const data = await parseSelfDisciplineItems({
      text,
      today: dateKey(now),
      weekday: weekdayIso(now),
      now: formatHm(now),
      timezone: timezoneName(),
      clientRequestId: `sd_chat_${now}_${Math.random().toString(36).slice(2, 8)}`,
    })
    const items = normalizeItems(data && data.items)
    if (!items.length) {
      // 非创建意图（取消/闲聊/追问）：只显示助手回复，不显示错误。
      const intent = data && data.intent ? data.intent : 'chat'
      if (intent === 'cancel') {
        const draft = pendingDraftMessage()
        if (draft) {
          draft.items = null
          draft.text = '这一项已取消。'
        }
      }
      replaceMessage(pendingId, {
        id: pendingId,
        role: 'assistant',
        text: String((data && data.reply) || '好。'),
      })
      headerEye.value = 'idle'
      return
    }
    replaceMessage(pendingId, {
      id: pendingId,
      role: 'assistant',
      text: String((data && data.reply) || '整理好了，检查一下。'),
      items,
      source: data && data.source === 'local' ? 'local' : 'ai',
      added: false,
      adding: false,
    })
    headerEye.value = 'due'
  } catch (e) {
    replaceMessage(pendingId, {
      id: pendingId,
      role: 'assistant',
      error: (e && e.message) || '整理失败，请换个说法再试',
    })
    headerEye.value = 'idle'
    if (e && e.status === 401) {
      uni.showToast({ title: '登录已过期，请重新登录', icon: 'none' })
    }
  } finally {
    sending.value = false
    await scrollBottom()
    if (headerEye.value === 'due') {
      setTimeout(() => {
        if (!sending.value) headerEye.value = 'idle'
      }, 1800)
    }
  }
}

function replaceMessage(id, next) {
  const index = messages.value.findIndex((msg) => msg.id === id)
  if (index >= 0) messages.value.splice(index, 1, next)
  else messages.value.push(next)
}

async function onConfirm(msg, items) {
  if (!msg || msg.adding || msg.added) return
  msg.adding = true
  msg.error = ''
  try {
    await checkin.createItems(items)
    msg.items = items
    msg.added = true
    messages.value.push({
      id: newId(),
      role: 'assistant',
      text: `已加入今日事项 ${items.length} 项。还要加别的吗？`,
    })
    headerEye.value = 'done'
  } catch (e) {
    msg.error = (e && e.message) || '添加失败，请重试'
  } finally {
    msg.adding = false
    await scrollBottom()
    if (headerEye.value === 'done') {
      setTimeout(() => {
        headerEye.value = 'idle'
      }, 1800)
    }
  }
}

function onVoiceStart(e) {
  if (sending.value) {
    uni.showToast({ title: '正在整理，请稍后', icon: 'none' })
    return
  }
  if (!voiceSupported.value) {
    uni.showToast({ title: '当前平台不支持语音输入', icon: 'none' })
    return
  }
  if (voiceState.value !== 'idle') return

  const point = (e.touches && e.touches[0]) || e
  voiceStartY = (point && (point.clientY != null ? point.clientY : point.pageY)) || 0
  voiceWillCancel.value = false
  try {
    uni.vibrateShort({ type: 'light' })
  } catch (err) {}
  startVoice()
}

function onVoiceMove(e) {
  if (voiceState.value !== 'recording' && voiceState.value !== 'starting') return
  const point = (e.touches && e.touches[0]) || e
  if (!point) return
  const y = point.clientY != null ? point.clientY : point.pageY
  if (typeof y !== 'number') return

  const next = voiceStartY - y > 80
  if (next !== voiceWillCancel.value) {
    voiceWillCancel.value = next
    try {
      uni.vibrateShort({ type: next ? 'heavy' : 'light' })
    } catch (err) {}
  }
}

function onVoiceEnd() {
  if (voiceWillCancel.value) {
    voiceWillCancel.value = false
    cancelVoice()
    return
  }
  voiceWillCancel.value = false
  finishVoice()
}

function onVoiceCancel() {
  voiceWillCancel.value = false
  cancelVoice()
}

function onVoiceMouseLeave() {
  if (voiceState.value === 'recording' || voiceState.value === 'starting') {
    voiceWillCancel.value = false
    cancelVoice()
  }
}
</script>

<style scoped>
.assistant-page {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--ik-bg);
  overflow: hidden;
  box-sizing: border-box;
}
/* #ifdef H5 */
/* 子页面有原生导航栏，扣掉导航高度，避免输入框被顶到视口外 */
.assistant-page {
  height: calc(100vh - var(--window-top, 0px));
}
/* #endif */
.assistant-head {
  flex: 0 0 auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 16rpx 32rpx 10rpx;
  background: var(--ik-bg);
}
.head-line {
  margin-top: 4rpx;
  font-size: 24rpx;
  color: var(--ik-t3);
  text-align: center;
}
.chat-scroll {
  flex: 1;
  height: 0;
  min-height: 0;
}
.chat-inner {
  padding: 16rpx 28rpx 24rpx;
  box-sizing: border-box;
}
.msg-row {
  display: flex;
  align-items: flex-start;
  margin-bottom: 22rpx;
}
.msg-row.user {
  justify-content: flex-end;
}
.msg-body {
  max-width: 78%;
  min-width: 0;
}
.msg-body.has-draft {
  max-width: 92%;
}
.avatar {
  flex: 0 0 auto;
  width: 60rpx;
  height: 60rpx;
  border-radius: 50%;
  background: var(--ik-block);
  color: var(--ik-on-block);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24rpx;
  font-weight: 600;
  margin-right: 12rpx;
}
.avatar.user-avatar {
  background: var(--ik-primary-weak);
  color: var(--ik-primary);
  margin-left: 12rpx;
  margin-right: 0;
}
.bubble {
  padding: 18rpx 22rpx;
  border-radius: 22rpx;
  box-sizing: border-box;
}
.bubble.assistant {
  background: var(--ik-card);
  border-top-left-radius: 8rpx;
}
.bubble.user {
  background: var(--ik-primary);
  border-top-right-radius: 8rpx;
}
.msg-text {
  display: block;
  font-size: 27rpx;
  line-height: 1.65;
  color: var(--ik-t1);
  white-space: pre-wrap;
}
.bubble.user .msg-text {
  color: var(--ik-on-primary);
}
.typing {
  font-size: 25rpx;
  color: var(--ik-t3);
}
.msg-error {
  display: block;
  font-size: 24rpx;
  line-height: 1.6;
  color: var(--ik-danger);
}
.login-card {
  margin: 10rpx 0 24rpx;
  padding: 24rpx;
  border-radius: var(--ik-radius);
  background: var(--ik-card);
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}
.login-title {
  font-size: 27rpx;
  font-weight: 600;
  color: var(--ik-t1);
}
.login-sub {
  margin-top: 6rpx;
  font-size: 22rpx;
  color: var(--ik-t3);
}
.login-btn {
  margin: 16rpx 0 0;
  padding: 0 28rpx;
  height: 60rpx;
  line-height: 60rpx;
  border-radius: 999rpx;
  font-size: 24rpx;
  background: var(--ik-primary);
  color: var(--ik-on-primary);
  border: none;
}
.login-btn::after {
  border: none;
}
.chat-bottom {
  height: 8rpx;
}
.composer {
  flex: 0 0 auto;
  padding: 12rpx 24rpx calc(16rpx + env(safe-area-inset-bottom));
  background: var(--ik-card);
  border-top: 1rpx solid var(--ik-line);
}
.record-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8rpx 8rpx 12rpx;
}
.record-text {
  font-size: 24rpx;
  color: var(--ik-danger);
}
.record-text.subtle {
  color: var(--ik-t3);
}
.record-cancel {
  font-size: 24rpx;
  color: var(--ik-t2);
}
.input-row {
  display: flex;
  align-items: flex-end;
  gap: 10rpx;
}
.chat-input {
  flex: 1;
  min-height: 76rpx;
  max-height: 220rpx;
  padding: 18rpx 22rpx;
  border-radius: 22rpx;
  background: var(--ik-input-bg);
  border: 1rpx solid var(--ik-line);
  font-size: 27rpx;
  line-height: 1.5;
  color: var(--ik-t1);
  box-sizing: border-box;
}
.voice-btn,
.send-btn {
  flex: 0 0 auto;
  margin: 0;
  padding: 0;
  height: 76rpx;
  min-width: 76rpx;
  line-height: 76rpx;
  border-radius: 22rpx;
  font-size: 26rpx;
  text-align: center;
  border: none;
}
.voice-btn {
  flex: 0 0 76rpx;
  width: 76rpx;
  height: 76rpx;
  min-width: 76rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
  border-radius: 50%;
  background: var(--ik-primary-weak);
  color: var(--ik-primary);
}
.voice-btn.is-recording {
  background: var(--ik-danger);
  color: var(--ik-on-primary);
}
.voice-btn.will-cancel {
  background: var(--ik-soft);
  color: var(--ik-danger);
}
/* uni-app 默认的 disabled 样式会把图标变成灰块，这里统一成柔和的禁用态 */
.voice-btn[disabled] {
  background: var(--ik-soft);
  color: var(--ik-t3);
  opacity: 1;
}
.voice-icon {
  font-size: 40rpx;
  line-height: 1;
}
.send-btn {
  padding: 0 24rpx;
  background: var(--ik-primary);
  color: var(--ik-on-primary);
}
.voice-btn::after,
.send-btn::after {
  border: none;
}
</style>
