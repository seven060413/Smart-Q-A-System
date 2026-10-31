<template>
  <view class="page">
    <!-- 登录状态栏：游客也能问答，登录用于保存账号状态 -->
    <view class="topbar">
      <text class="topbar-state">{{ authStateText }}</text>
      <view class="topbar-actions">
        <text v-if="store.auth.user" class="topbar-link" @click="newConversation">新对话</text>
        <text v-if="store.auth.user" class="topbar-link" @click="goHistory">历史</text>
        <text class="topbar-link" @click="goAuth">{{ store.auth.user ? '账号' : '登录 / 注册' }}</text>
      </view>
    </view>

    <!-- 聊天消息区 -->
    <scroll-view class="chat" scroll-y :scroll-into-view="scrollTo" scroll-with-animation>
      <!-- 历史消息分页 -->
      <view v-if="hasEarlier" class="load-earlier" @click="loadEarlier">
        {{ loadingEarlier ? '加载中…' : '加载更早的消息' }}
      </view>

      <!-- 欢迎提示 -->
      <view v-if="messages.length === 0 && !loading && !historyLoading" class="welcome">
        <text class="welcome-emoji">📚</text>
        <text class="welcome-text">我是小学数学助教，问我教材里的知识吧～\n例如：为什么异分母分数相加要先通分</text>
      </view>

      <!-- 消息列表 -->
      <view v-for="(msg, i) in messages" :key="i" :id="'msg-' + i" class="msg-row">
        <!-- 用户气泡（右） -->
        <view v-if="msg.role === 'user'" class="msg msg-user">
          <view class="bubble bubble-user">{{ msg.text }}</view>
        </view>

        <!-- AI 回答气泡（左） -->
        <view v-else class="msg msg-ai">
          <view class="bubble bubble-ai">
            <!-- 生成失败卡 -->
            <view v-if="msg.failed" class="failed-card">
              <view class="failed-title">⚠️ 回答生成失败</view>
              <view class="failed-text">{{ msg.error_message || '请稍后重新提问' }}</view>
              <button v-if="msg.retryQuestion" class="retry-btn" @click="retry(msg)">重新提问</button>
            </view>

            <!-- 拒答卡 -->
            <view v-else-if="msg.refused" class="refuse-card">
              <view class="refuse-title">⚠️ {{ msg.answer }}</view>
              <view v-if="msg.knowledge_point" class="refuse-closest">最接近知识点：{{ msg.knowledge_point }}</view>
            </view>

            <!-- 正常回答 -->
            <template v-else>
              <view class="head">
                <text class="chip">{{ msg.knowledge_point }}</text>
                <text class="source">📚 {{ msg.source }}</text>
              </view>

              <!-- 三层折叠：前置知识 -->
              <view class="section" @click="toggle(msg, 'pre')">
                <view class="section-head">
                  <text>📖 前置知识</text>
                  <text class="arrow">{{ msg.open.pre ? '▾' : '▸' }}</text>
                </view>
                <view v-if="msg.open.pre" class="section-body">
                  <view v-for="(g, j) in msg.prerequisite_gaps" :key="j" class="gap">
                    <text class="gap-name">{{ g.name }}</text>
                    <text class="gap-tag" :class="g.required ? 't-required' : 't-suggest'">{{ g.required ? '必需' : '建议' }}</text>
                  </view>
                  <text v-if="msg.prerequisite_gaps.length === 0" class="empty">无</text>
                </view>
              </view>

              <!-- 三层折叠：本体讲解 -->
              <view class="section" @click="toggle(msg, 'body')">
                <view class="section-head">
                  <text>💡 本体讲解</text>
                  <text class="arrow">{{ msg.open.body ? '▾' : '▸' }}</text>
                </view>
                <view v-if="msg.open.body" class="section-body">
                  <text class="answer">{{ msg.answer }}</text>
                </view>
              </view>

              <!-- 三层折叠：巩固练习 -->
              <view class="section" @click="toggle(msg, 'cons')">
                <view class="section-head">
                  <text>✏️ 巩固练习</text>
                  <text class="arrow">{{ msg.open.cons ? '▾' : '▸' }}</text>
                </view>
                <view v-if="msg.open.cons" class="section-body">
                  <view v-for="(c, j) in msg.learning_path.consolidation" :key="j" class="gap">
                    <text class="gap-name">{{ c }}</text>
                  </view>
                  <text v-if="msg.learning_path.consolidation.length === 0" class="empty">无</text>
                </view>
              </view>

              <button class="path-btn" @click="goPath(msg)">🗺 查看学习路径</button>
            </template>
          </view>
        </view>
      </view>

      <!-- 加载历史会话 -->
      <view v-if="historyLoading" class="msg msg-ai">
        <view class="bubble bubble-ai typing">正在加载历史会话…</view>
      </view>

      <!-- 思考中 -->
      <view v-if="loading" class="msg msg-ai">
        <view class="bubble bubble-ai typing">思考中…</view>
      </view>
    </scroll-view>

    <!-- 底部输入区：状态行在上方，控件顺序固定为 输入框 → 语音 → 发送 -->
    <view class="composer">
      <view class="record-row">
        <template v-if="voiceSupported && recordState === 'recording'">
          <text class="record-text">正在录音 · {{ recordSeconds }}s</text>
          <text class="record-cancel" @click="cancelRecord">取消</text>
        </template>
        <text v-else-if="voiceSupported && recordState === 'uploading'" class="record-text subtle">正在识别…</text>
        <text v-else-if="voiceSupported && recordStarting" class="record-text subtle">正在准备…</text>
      </view>

      <view class="input-bar">
        <input
          class="input"
          v-model="question"
          placeholder="输入你的问题…"
          confirm-type="send"
          :disabled="loading || recordStarting || recordState !== 'idle'"
          @confirm="send"
        />
        <button
          v-if="voiceSupported"
          class="voice-btn"
          :class="[recordState, { starting: recordStarting }]"
          :disabled="loading || recordStarting || recordState === 'uploading'"
          aria-label="语音输入"
          @click="toggleRecord"
        >
          <svg class="voice-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
            <g
              transform="rotate(90 12 12)"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
            >
              <path d="M2 8.82a15 15 0 0 1 20 0" />
              <path d="M5 12.859a10 10 0 0 1 14 0" />
              <path d="M8.5 16.429a5 5 0 0 1 7 0" />
            </g>
          </svg>
          <text class="sr-only">语音输入</text>
        </button>
        <button
          class="send-btn"
          :disabled="loading || !question || recordStarting || recordState !== 'idle'"
          @click="send"
        >发送</button>
      </view>
    </view>

    <AppTabBar :active="TAB_INDEX" />
  </view>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { onHide, onLoad, onShow, onUnload } from '@dcloudio/uni-app'
import { askQuestion, listMessages, transcribeAudio } from '../../api.js'
import AppTabBar from '../../components/AppTabBar.vue'
import { TAB_INDEX, hideNativeTabBar } from '../../tabbar.js'
import { store } from '../../store.js'

const question = ref('')
const loading = ref(false)
const historyLoading = ref(false)
const loadingEarlier = ref(false)
const messages = reactive([])
const scrollTo = ref('')
const messagesCursor = ref('')
const hasEarlier = ref(false)

// 语音输入：idle → recording → uploading → idle 的小状态机。
// App 用 uni.getRecorderManager；H5 官方不支持该 API，改用浏览器 MediaRecorder。
const recordState = ref('idle')
const recordSeconds = ref(0)
const recordStarting = ref(false)
const voiceSupported = ref(false)
let recorder = null
let recordTimer = null
let pendingCancel = false
let pendingStart = false
// 每次开始/中止录音都递增，用于丢弃过期回调（取消、离开页面、旧上传）
let recordSession = 0
let activeRecordSession = 0

// #ifdef APP-PLUS
voiceSupported.value = true
recorder = uni.getRecorderManager()
// #endif

// #ifdef H5
voiceSupported.value = true
let h5Stream = null
let h5Recorder = null
let h5Chunks = []
let h5MimeType = ''
// 优先选 Qwen-ASR 明确支持的 MP4/AAC；浏览器只提供 webm/ogg 时，
// 上传前转换成 WAV（Qwen 文档明确支持）。
const H5_MIME_CANDIDATES = [
  'audio/mp4;codecs=mp4a.40.2',
  'audio/mp4',
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/ogg;codecs=opus',
  'audio/ogg',
]
// #endif

function recordErrorMessage(err) {
  const msg = (err && err.errMsg) || ''
  if (/auth|permission|denied|deny|权限|授权/i.test(msg)) {
    return '没有麦克风权限，请在系统设置中允许后重试'
  }
  if (/cancel/i.test(msg)) return '录音已取消'
  if (/not support|unsupport|device/i.test(msg)) return '当前设备不支持录音'
  return '录音失败，请重试'
}

function startRecordTimer() {
  stopRecordTimer()
  recordTimer = setInterval(() => {
    recordSeconds.value += 1
    // 30 秒上限：App 端由 start(duration) 自动停止，这里计时并兜底
    if (recordSeconds.value >= 30) {
      stopRecordTimer()
      if (recordState.value === 'recording') stopCurrentRecording()
    }
  }, 1000)
}

function stopRecordTimer() {
  if (recordTimer) {
    clearInterval(recordTimer)
    recordTimer = null
  }
}

// 停止当前录音（上传/清理由各自的 onStop 处理）
// #ifdef APP-PLUS
function stopCurrentRecording() {
  if (!recorder) return
  try {
    recorder.stop()
  } catch (e) {
    resetRecordState()
  }
}
// #endif

// #ifdef H5
function stopCurrentRecording() {
  if (h5Recorder && h5Recorder.state !== 'inactive') {
    try {
      h5Recorder.stop()
    } catch (e) {
      resetRecordState()
    }
  }
}
// #endif

// #ifndef APP-PLUS
// #ifndef H5
function stopCurrentRecording() {}
// #endif
// #endif

function stopTracks(stream) {
  if (!stream) return
  stream.getTracks().forEach((track) => {
    try {
      track.stop()
    } catch (e) {}
  })
}

function releaseH5Resources() {
  // #ifdef H5
  const stream = h5Stream
  h5Stream = null
  h5Recorder = null
  h5Chunks = []
  h5MimeType = ''
  stopTracks(stream)
  // #endif
}

function resetRecordState() {
  stopRecordTimer()
  pendingCancel = false
  recordState.value = 'idle'
  recordSeconds.value = 0
}

// 取消/离开页面：让进行中的回调与上传结果全部失效，并复位界面
function invalidateRecordSession() {
  recordSession += 1
  pendingCancel = true
  pendingStart = false
  stopRecordTimer()
  if (recordState.value === 'recording') stopCurrentRecording()
  releaseH5Resources()
  recordState.value = 'idle'
  recordSeconds.value = 0
}

function showRecordPermissionModal(deniedAlways) {
  uni.showModal({
    title: '需要麦克风权限',
    content: deniedAlways
      ? '麦克风权限已被拒绝，请到系统设置中手动开启后重试。'
      : '请允许使用麦克风后重试。',
    showCancel: false,
    confirmText: '知道了',
  })
}

function requestRecordPermission() {
  return new Promise((resolve) => {
    // #ifdef APP-PLUS
    // uni.authorize 不支持 App 端；Android 用 5+ 原生运行时权限 API。
    if (typeof plus !== 'undefined' && plus.android && plus.android.requestPermissions) {
      const permission = 'android.permission.RECORD_AUDIO'
      try {
        if (plus.android.hasPermission && plus.android.hasPermission(permission)) {
          resolve(true)
          return
        }
        plus.android.requestPermissions(
          [permission],
          (e) => {
            const granted = !!(e && e.granted && e.granted.length > 0)
            if (granted) {
              resolve(true)
              return
            }
            const deniedAlways = !!(e && e.deniedAlways && e.deniedAlways.length > 0)
            showRecordPermissionModal(deniedAlways)
            resolve(false)
          },
          () => {
            showRecordPermissionModal(false)
            resolve(false)
          }
        )
      } catch (err) {
        // 无法判断权限时，交给录音 API 自行触发系统授权
        resolve(true)
      }
      return
    }
    // iOS 等平台：首次录音时由系统弹窗
    resolve(true)
    // #endif
    // #ifndef APP-PLUS
    resolve(false)
    // #endif
  })
}

// 等待授权期间可能已跳到其他页面
function isIndexPageActive() {
  const pages = getCurrentPages()
  const current = pages[pages.length - 1]
  const route = current && current.route ? String(current.route).replace(/^\//, '') : ''
  return route === 'pages/index/index'
}

// ===== H5 录音（浏览器 MediaRecorder）=====
// #ifdef H5
function checkH5RecorderSupport() {
  if (typeof window === 'undefined' || window.isSecureContext === false) {
    uni.showToast({ title: '麦克风需要 HTTPS 或 localhost 环境', icon: 'none' })
    return false
  }
  if (typeof MediaRecorder === 'undefined') {
    uni.showToast({ title: '当前浏览器不支持录音', icon: 'none' })
    return false
  }
  if (!navigator.mediaDevices || typeof navigator.mediaDevices.getUserMedia !== 'function') {
    uni.showToast({ title: '当前浏览器不支持麦克风采集', icon: 'none' })
    return false
  }
  if (typeof File === 'undefined') {
    uni.showToast({ title: '当前浏览器不支持录音上传', icon: 'none' })
    return false
  }
  return true
}

function pickH5MimeType() {
  if (typeof MediaRecorder === 'undefined' || typeof MediaRecorder.isTypeSupported !== 'function') {
    return ''
  }
  for (const type of H5_MIME_CANDIDATES) {
    if (MediaRecorder.isTypeSupported(type)) return type
  }
  return ''
}

function h5MicErrorMessage(err) {
  const name = (err && err.name) || ''
  if (name === 'NotAllowedError' || name === 'PermissionDeniedError' || name === 'SecurityError') {
    return '麦克风权限被拒绝，请在浏览器设置中允许'
  }
  if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
    return '没有找到可用的麦克风'
  }
  if (name === 'NotReadableError' || name === 'TrackStartError') {
    return '麦克风被其他应用占用，请关闭后重试'
  }
  return '无法访问麦克风，请重试'
}

function isQwenFriendlyMime(mimeType) {
  const type = (mimeType || '').toLowerCase()
  return (
    type.includes('mp4') ||
    type.includes('aac') ||
    type.includes('mpeg') ||
    type.includes('mp3') ||
    type.includes('wav')
  )
}

function h5FileExtension(mimeType) {
  const type = (mimeType || '').toLowerCase()
  if (type.includes('mp4') || type.includes('aac')) return 'm4a'
  if (type.includes('wav')) return 'wav'
  if (type.includes('mpeg') || type.includes('mp3')) return 'mp3'
  if (type.includes('ogg')) return 'ogg'
  return 'webm'
}

function encodeWav(audioBuffer) {
  const samples = audioBuffer.getChannelData(0)
  const buffer = new ArrayBuffer(44 + samples.length * 2)
  const view = new DataView(buffer)
  const writeString = (offset, text) => {
    for (let i = 0; i < text.length; i += 1) {
      view.setUint8(offset + i, text.charCodeAt(i))
    }
  }
  writeString(0, 'RIFF')
  view.setUint32(4, 36 + samples.length * 2, true)
  writeString(8, 'WAVE')
  writeString(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true) // PCM
  view.setUint16(22, 1, true) // 单声道
  view.setUint32(24, audioBuffer.sampleRate, true)
  view.setUint32(28, audioBuffer.sampleRate * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  writeString(36, 'data')
  view.setUint32(40, samples.length * 2, true)
  let offset = 44
  for (let i = 0; i < samples.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, samples[i]))
    view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true)
    offset += 2
  }
  return new Blob([view], { type: 'audio/wav' })
}

// 浏览器只能录 webm/ogg 时，转成 Qwen 明确支持的 WAV（16kHz 单声道）
async function blobToWav(blob) {
  const AudioCtor = window.AudioContext || window.webkitAudioContext
  const OfflineCtor = window.OfflineAudioContext || window.webkitOfflineAudioContext
  if (!AudioCtor || !OfflineCtor) throw new Error('AudioContext unsupported')

  const arrayBuffer = await blob.arrayBuffer()
  const ctx = new AudioCtor()
  let decoded
  try {
    decoded = await new Promise((resolve, reject) => {
      ctx.decodeAudioData(arrayBuffer.slice(0), resolve, reject)
    })
  } finally {
    if (ctx.close) ctx.close()
  }

  const targetRate = 16000
  const frames = Math.max(1, Math.ceil(decoded.duration * targetRate))
  const offline = new OfflineCtor(1, frames, targetRate)
  const source = offline.createBufferSource()
  source.buffer = decoded
  source.connect(offline.destination)
  source.start(0)
  const rendered = await offline.startRendering()
  return encodeWav(rendered)
}

function abortH5Recording(message) {
  recordSession += 1
  pendingCancel = true
  stopRecordTimer()
  const activeRecorder = h5Recorder
  const stream = h5Stream
  h5Recorder = null
  h5Stream = null
  h5Chunks = []
  h5MimeType = ''
  if (activeRecorder && activeRecorder.state !== 'inactive') {
    try {
      activeRecorder.stop()
    } catch (e) {}
  }
  stopTracks(stream)
  recordState.value = 'idle'
  recordSeconds.value = 0
  pendingCancel = false
  uni.showToast({ title: message, icon: 'none' })
}

async function beginH5Recording(token) {
  let stream
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    })
  } catch (err) {
    if (token === recordSession) {
      uni.showToast({ title: h5MicErrorMessage(err), icon: 'none' })
    }
    return
  }

  // 等待授权期间已取消、离开页面或跳到其他页面
  if (token !== recordSession || !isIndexPageActive()) {
    stopTracks(stream)
    return
  }

  const mimeType = pickH5MimeType()
  let mediaRecorder
  try {
    mediaRecorder = mimeType
      ? new MediaRecorder(stream, { mimeType })
      : new MediaRecorder(stream)
  } catch (err) {
    stopTracks(stream)
    uni.showToast({ title: '当前浏览器不支持录音', icon: 'none' })
    return
  }

  recordSession += 1
  const session = recordSession
  activeRecordSession = session
  pendingCancel = false
  recordSeconds.value = 0
  h5Stream = stream
  h5Recorder = mediaRecorder
  const sessionChunks = []
  h5Chunks = sessionChunks
  h5MimeType = mimeType || mediaRecorder.mimeType || ''
  const sessionMimeType = h5MimeType

  mediaRecorder.ondataavailable = (event) => {
    if (event.data && event.data.size > 0) sessionChunks.push(event.data)
  }
  mediaRecorder.onerror = () => {
    if (session !== recordSession) return
    abortH5Recording('录音失败，请重试')
  }
  mediaRecorder.onstop = () => {
    finishH5Recording(session, sessionChunks, stream, sessionMimeType).catch(() => {
      if (session === recordSession) {
        resetRecordState()
        uni.showToast({ title: '录音处理失败，请重试', icon: 'none' })
      }
    })
  }

  const audioTrack = stream.getAudioTracks()[0]
  if (audioTrack) {
    audioTrack.onended = () => {
      if (recordState.value !== 'recording' || session !== recordSession) return
      abortH5Recording('录音已中断，请重试')
    }
  }

  try {
    mediaRecorder.start(1000)
  } catch (err) {
    abortH5Recording('无法开始录音，请重试')
    return
  }

  recordState.value = 'recording'
  startRecordTimer()
}

async function finishH5Recording(session, sessionChunks, stream, detectedType) {
  // 过期回调（已取消、离开页面或已开始新录音）：不要碰当前录音的状态
  if (session !== recordSession) {
    stopTracks(stream)
    return
  }

  const recordedSeconds = recordSeconds.value
  const chunks = sessionChunks.slice()
  stopRecordTimer()
  h5Stream = null
  h5Recorder = null
  h5Chunks = []
  h5MimeType = ''
  stopTracks(stream)

  if (session !== recordSession) return
  if (pendingCancel) {
    resetRecordState()
    return
  }
  if (!chunks.length || recordedSeconds * 1000 < 500) {
    resetRecordState()
    uni.showToast({ title: '没有录到有效语音', icon: 'none' })
    return
  }

  let blob = new Blob(chunks, { type: detectedType || 'audio/webm' })
  if (!blob.size) {
    resetRecordState()
    uni.showToast({ title: '没有录到有效语音', icon: 'none' })
    return
  }

  // 统一转成 Qwen 明确支持的 WAV（16kHz 单声道）；
  // 转换失败时，若原始格式本身受支持（MP4/AAC），退回原文件上传。
  recordState.value = 'uploading'
  let mimeType = 'audio/wav'
  try {
    blob = await blobToWav(blob)
  } catch (err) {
    if (!isQwenFriendlyMime(detectedType)) {
      if (session !== recordSession) return
      resetRecordState()
      uni.showToast({
        title: '浏览器无法转换录音格式，请使用 Chrome/Edge 或 App',
        icon: 'none',
      })
      return
    }
    mimeType = (detectedType || blob.type || 'audio/mp4').split(';')[0].trim()
  }
  if (session !== recordSession) return

  const file = new File([blob], `audio.${h5FileExtension(mimeType)}`, {
    type: mimeType || 'audio/wav',
  })
  uploadRecording(null, session, { file })
}
// #endif

function toggleRecord() {
  if (!voiceSupported.value) {
    uni.showToast({ title: '当前平台不支持语音输入', icon: 'none' })
    return
  }
  if (recordState.value === 'recording') {
    stopCurrentRecording() // onStop 中决定上传
    return
  }
  if (recordState.value === 'uploading' || pendingStart || recordStarting.value) return
  startRecording()
}

async function startRecording() {
  if (loading.value) {
    uni.showToast({ title: '回答生成中，请稍后再录音', icon: 'none' })
    return
  }
  if (recordState.value !== 'idle' || pendingStart || recordStarting.value) return

  pendingStart = true
  recordStarting.value = true
  const token = recordSession
  try {
    // #ifdef APP-PLUS
    // 只在用户点击麦克风后进入这里申请权限；App 启动时不请求麦克风
    const allowed = await requestRecordPermission()
    if (!allowed) return
    // #endif
    // #ifdef H5
    if (!checkH5RecorderSupport()) return
    // #endif
    // 等待授权期间用户已取消、离开页面或跳到其他页面
    if (token !== recordSession || !isIndexPageActive()) return

    // #ifdef APP-PLUS
    beginAppRecording()
    // #endif
    // #ifdef H5
    await beginH5Recording(token)
    // #endif
  } catch (e) {
    releaseH5Resources()
    resetRecordState()
    uni.showToast({ title: '无法开始录音', icon: 'none' })
  } finally {
    pendingStart = false
    recordStarting.value = false
  }
}

// #ifdef APP-PLUS
function beginAppRecording() {
  recordSession += 1
  activeRecordSession = recordSession
  pendingCancel = false
  recordSeconds.value = 0
  recordState.value = 'recording'
  try {
    // App 端支持的格式：aac / mp3 / wav / PCM，默认 mp3
    recorder.start({
      format: 'mp3',
      sampleRate: 16000,
      duration: 30000,
    })
  } catch (e) {
    if (activeRecordSession === recordSession) resetRecordState()
    uni.showToast({ title: '当前设备不支持录音', icon: 'none' })
  }
}
// #endif

function cancelRecord() {
  if (recordState.value !== 'recording') return
  pendingCancel = true
  stopCurrentRecording()
}

function uploadRecording(filePath, session, options = {}) {
  recordState.value = 'uploading'
  transcribeAudio(filePath, options)
    .then((data) => {
      if (session !== recordSession) return
      const text = data && data.text ? String(data.text).trim() : ''
      if (!text) {
        uni.showToast({ title: '未识别到有效语音，请重试', icon: 'none' })
        return
      }
      // 已有输入时追加并加空格，不静默覆盖
      const current = question.value.trim()
      question.value = current ? `${current} ${text}` : text
      uni.showToast({
        title: current ? '已追加识别结果，请确认' : '识别完成，请确认后发送',
        icon: 'none',
      })
    })
    .catch((e) => {
      if (session !== recordSession) return
      uni.showToast({ title: (e && e.message) || '语音识别失败，请重试', icon: 'none' })
    })
    .finally(() => {
      if (session === recordSession) resetRecordState()
    })
}

if (recorder) {
  recorder.onStart(() => {
    // 授权后立刻取消、或页面已离开
    if (activeRecordSession !== recordSession || pendingCancel) {
      try {
        recorder.stop()
      } catch (e) {}
      return
    }
    recordState.value = 'recording'
    recordSeconds.value = 0
    startRecordTimer()
  })

  recorder.onStop((res) => {
    const session = activeRecordSession
    const recordedSeconds = recordSeconds.value
    stopRecordTimer()

    // 已取消、已离开页面或已开始新录音：丢弃这次结果
    if (session !== recordSession) return

    if (pendingCancel) {
      resetRecordState()
      return
    }

    const filePath = res && res.tempFilePath
    if (!filePath) {
      resetRecordState()
      uni.showToast({ title: '录音失败，请重试', icon: 'none' })
      return
    }

    // App 端 onStop 不一定返回 duration，用计时器兜底
    const durationMs = (res && res.duration) || recordedSeconds * 1000
    if (durationMs < 500) {
      resetRecordState()
      uni.showToast({ title: '没有录到有效语音', icon: 'none' })
      return
    }

    uploadRecording(filePath, session)
  })

  recorder.onError((err) => {
    if (activeRecordSession !== recordSession) return
    resetRecordState()
    uni.showToast({ title: recordErrorMessage(err), icon: 'none' })
  })
}

// 离开页面或 App 进入后台：停止录音并复位，不保留未完成的识别结果。
onHide(() => {
  // #ifdef H5
  if (recordState.value !== 'idle' || pendingStart) invalidateRecordSession()
  // #endif
  // #ifdef APP-PLUS
  // 不处理 pendingStart，避免系统权限弹窗触发 onHide 时误中止首次授权
  if (recordState.value !== 'idle') invalidateRecordSession()
  // #endif
})

onUnload(() => {
  invalidateRecordSession()
})

const authStateText = computed(() => {
  if (!store.auth.ready) return '正在检查登录状态…'
  if (store.auth.user) {
    return '已登录：' + (store.auth.user.display_name || store.auth.user.username)
  }
  return '游客模式'
})

function goAuth() {
  uni.navigateTo({ url: '/pages/auth/auth' })
}

function goHistory() {
  uni.navigateTo({ url: '/pages/history/history' })
}

function clearConversationView() {
  messages.splice(0, messages.length)
  question.value = ''
  store.currentConversationId = ''
  messagesCursor.value = ''
  hasEarlier.value = false
  scrollTo.value = ''
}

function newConversation() {
  if (loading.value || recordStarting.value || recordState.value !== 'idle') return
  clearConversationView()
  uni.showToast({ title: '已开始新对话', icon: 'none' })
}

function newRequestId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`
}

function toUiMessages(items) {
  const out = []
  let lastUser = ''
  for (const m of items) {
    if (m.role === 'user') {
      lastUser = m.content || ''
      out.push({ role: 'user', text: lastUser })
    } else if (m.role === 'assistant') {
      out.push({
        role: 'ai',
        answer: m.content || '',
        knowledge_point: m.knowledge_point || '',
        prerequisite_gaps: m.prerequisite_gaps || [],
        learning_path: m.learning_path || { prerequisites: [], body: '', consolidation: [] },
        source: m.source || '',
        refused: !!m.refused,
        failed: m.status === 'failed',
        error_message: m.error_message || '',
        retryQuestion: lastUser,
        open: { pre: false, body: true, cons: false },
      })
    }
  }
  return out
}

async function loadConversation(conversationId) {
  if (!store.auth.user) {
    goAuth()
    return
  }
  historyLoading.value = true
  try {
    const page = await listMessages(conversationId, { limit: 50 })
    messages.splice(0, messages.length, ...toUiMessages(page.items))
    store.currentConversationId = conversationId
    messagesCursor.value = page.next_cursor || ''
    hasEarlier.value = !!page.has_more

    const lastAi = [...messages].reverse().find((m) => m.role === 'ai' && m.learning_path)
    if (lastAi) {
      store.learningPath = lastAi.learning_path
      store.knowledgePoint = lastAi.knowledge_point
      store.source = lastAi.source
    }
    scrollBottom()
  } catch (e) {
    if (e && e.status === 401) {
      uni.showToast({ title: '登录已过期，请重新登录', icon: 'none' })
      goAuth()
    } else if (e && e.status === 404) {
      uni.showToast({ title: '会话不存在', icon: 'none' })
      newConversation()
    } else {
      uni.showToast({ title: (e && e.message) || '加载历史失败', icon: 'none' })
    }
  } finally {
    historyLoading.value = false
  }
}

async function loadEarlier() {
  if (!hasEarlier.value || loadingEarlier.value || !store.currentConversationId) return
  loadingEarlier.value = true
  try {
    const page = await listMessages(store.currentConversationId, {
      limit: 50,
      cursor: messagesCursor.value || null,
    })
    messages.unshift(...toUiMessages(page.items))
    messagesCursor.value = page.next_cursor || ''
    hasEarlier.value = !!page.has_more
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '加载更早消息失败', icon: 'none' })
  } finally {
    loadingEarlier.value = false
  }
}

function retry(msg) {
  if (loading.value) return
  const q = (msg.retryQuestion || '').trim()
  if (!q) return
  question.value = q
  send()
}

onLoad((options) => {
  // 使用自定义悬浮导航，隐藏原生 tabBar（只保留 switchTab 能力）
  hideNativeTabBar()

  if (options && options.conversation_id) {
    const conversationId = options.conversation_id
    if (store.auth.ready) {
      loadConversation(conversationId)
    } else {
      // 冷启动直接打开某个历史会话时，等 initAuth 恢复登录态后再加载。
      const stop = watch(
        () => store.auth.ready,
        (ready) => {
          if (ready) {
            stop()
            loadConversation(conversationId)
          }
        }
      )
    }
  } else {
    store.currentConversationId = ''
  }
})

// 首页是 tabBar 页面，switchTab 不能带参数；由历史页通过 store 传递一次性动作。
onShow(() => {
  hideNativeTabBar()

  const action = store.pendingIndexAction
  if (!action) return
  store.pendingIndexAction = null

  if (action.type === 'open' && action.conversationId) {
    loadConversation(action.conversationId)
    return
  }
  if (action.type === 'new') {
    if (loading.value || recordStarting.value || recordState.value !== 'idle') return
    clearConversationView()
  }
  // action.type === 'home'：保持当前问答页不变
})

function scrollBottom() {
  // 先清空再赋值，触发 scroll-into-view 重新定位
  scrollTo.value = ''
  setTimeout(() => {
    scrollTo.value = 'msg-' + (messages.length - 1)
  }, 50)
}

function send() {
  const q = question.value.trim()
  if (!q || loading.value || recordStarting.value || recordState.value !== 'idle') return
  messages.push({ role: 'user', text: q })
  question.value = ''
  loading.value = true
  scrollBottom()

  const loggedIn = !!(store.auth.user && store.auth.token)
  const requestId = newRequestId()

  askQuestion(q, {
    conversationId: loggedIn ? store.currentConversationId || null : null,
    clientRequestId: loggedIn ? requestId : null,
    auth: loggedIn,
  })
    .then((data) => {
      if (data.conversation_id) {
        store.currentConversationId = data.conversation_id
      }
      messages.push({
        role: 'ai',
        answer: data.answer || '',
        knowledge_point: data.knowledge_point || '',
        prerequisite_gaps: data.prerequisite_gaps || [],
        learning_path: data.learning_path || { prerequisites: [], body: '', consolidation: [] },
        source: data.source || '',
        refused: !!data.refused,
        failed: false,
        error_message: '',
        retryQuestion: q,
        open: { pre: false, body: true, cons: false },
      })
    })
    .catch((e) => {
      if (e && e.status === 404) {
        store.currentConversationId = ''
      }
      const errMsg =
        e && e.status === 401
          ? '登录已过期，请重新登录后重试'
          : (e && e.message) || '网络请求失败，请检查后端是否启动、地址是否配置正确'
      messages.push({
        role: 'ai',
        answer: '',
        refused: false,
        failed: true,
        error_message: errMsg,
        knowledge_point: '',
        prerequisite_gaps: [],
        learning_path: { prerequisites: [], body: '', consolidation: [] },
        source: '',
        retryQuestion: q,
        open: { pre: false, body: true, cons: false },
      })
    })
    .finally(() => {
      loading.value = false
      scrollBottom()
    })
}

function toggle(msg, key) {
  msg.open[key] = !msg.open[key]
}

function goPath(msg) {
  store.learningPath = msg.learning_path
  store.knowledgePoint = msg.knowledge_point
  store.source = msg.source
  uni.navigateTo({ url: '/pages/path/path' })
}
</script>

<style>
.page {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f5f6f8;
}

/* H5 的导航栏和 tabBar 是固定定位，页面高度需扣除二者及底部安全区域 */
/* #ifdef H5 */
.page {
  height: calc(100vh - var(--window-top, 0px) - var(--window-bottom, 0px));
}
/* #endif */

/* 登录状态栏 */
.topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14rpx 24rpx;
  background: #fff;
  border-bottom: 1rpx solid #eee;
}
.topbar-state {
  font-size: 24rpx;
  color: #888;
}
.topbar-link {
  font-size: 24rpx;
  color: #2b6cb0;
}
.topbar-actions {
  display: flex;
  gap: 24rpx;
  align-items: center;
}

.load-earlier {
  text-align: center;
  font-size: 24rpx;
  color: #2b6cb0;
  padding: 12rpx 0 24rpx;
}

.chat {
  flex: 1;
  overflow: hidden;
  padding: 24rpx;
  box-sizing: border-box;
}

/* 欢迎 */
.welcome {
  margin-top: 120rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
}
.welcome-emoji {
  font-size: 96rpx;
  margin-bottom: 24rpx;
}
.welcome-text {
  font-size: 28rpx;
  color: #999;
  text-align: center;
  line-height: 1.6;
}

/* 消息行 */
.msg-row {
  margin-bottom: 24rpx;
}
.msg {
  display: flex;
}
.msg-user {
  justify-content: flex-end;
}
.msg-ai {
  justify-content: flex-start;
}

/* 气泡 */
.bubble {
  max-width: 86%;
  padding: 20rpx 24rpx;
  border-radius: 20rpx;
  font-size: 28rpx;
  line-height: 1.6;
  word-break: break-all;
}
.bubble-user {
  background: #2b6cb0;
  color: #fff;
  border-top-right-radius: 6rpx;
}
.bubble-ai {
  background: #fff;
  color: #333;
  border-top-left-radius: 6rpx;
  box-shadow: 0 2rpx 8rpx rgba(0, 0, 0, 0.04);
}
.typing {
  color: #999;
}

/* AI 头部：知识点 + 出处 */
.head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12rpx;
  margin-bottom: 16rpx;
}
.chip {
  background: #e8f0fb;
  color: #2b6cb0;
  font-size: 24rpx;
  padding: 4rpx 16rpx;
  border-radius: 999rpx;
}
.source {
  font-size: 22rpx;
  color: #999;
}

/* 折叠面板 */
.section {
  border-top: 1rpx solid #f0f0f0;
  padding: 16rpx 0;
}
.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 28rpx;
  font-weight: 600;
  color: #444;
}
.arrow {
  color: #bbb;
  font-size: 28rpx;
}
.section-body {
  margin-top: 12rpx;
}
.answer {
  font-size: 28rpx;
  color: #333;
  white-space: pre-wrap;
}
.gap {
  display: flex;
  align-items: center;
  gap: 12rpx;
  padding: 8rpx 0;
}
.gap-name {
  font-size: 28rpx;
  color: #333;
}
.gap-tag {
  font-size: 20rpx;
  padding: 2rpx 12rpx;
  border-radius: 999rpx;
}
.t-required {
  background: #fde8e8;
  color: #e53e3e;
}
.t-suggest {
  background: #fff7e6;
  color: #dd6b20;
}
.empty {
  font-size: 26rpx;
  color: #bbb;
}

/* 拒答卡 */
.refuse-card {
  background: #fff5f5;
  border: 1rpx solid #feb2b2;
  border-radius: 16rpx;
  padding: 24rpx;
}
.refuse-title {
  font-size: 30rpx;
  font-weight: 600;
  color: #e53e3e;
  margin-bottom: 12rpx;
}
.refuse-closest {
  font-size: 26rpx;
  color: #9b2c2c;
}

/* 生成失败卡 */
.failed-card {
  background: #fffaf0;
  border: 1rpx solid #fbd38d;
  border-radius: 16rpx;
  padding: 24rpx;
}
.failed-title {
  font-size: 30rpx;
  font-weight: 600;
  color: #c05621;
  margin-bottom: 12rpx;
}
.failed-text {
  font-size: 26rpx;
  color: #975a16;
  line-height: 1.6;
}
.retry-btn {
  margin-top: 18rpx;
  display: inline-block;
  background: #fff;
  color: #c05621;
  font-size: 24rpx;
  border: 1rpx solid #fbd38d;
  border-radius: 999rpx;
  padding: 0 24rpx;
  line-height: 60rpx;
}
.retry-btn::after {
  border: none;
}

/* 学习路径按钮 */
.path-btn {
  margin-top: 20rpx;
  background: #e8f0fb;
  color: #2b6cb0;
  font-size: 26rpx;
  border-radius: 999rpx;
  padding: 0 24rpx;
  line-height: 64rpx;
  border: none;
}
.path-btn::after {
  border: none;
}

/* 底部输入区 */
.composer {
  background: #fff;
  border-top: 1rpx solid #eee;
}

/* 录音/识别状态行：固定高度，避免输入栏控件上下跳动 */
.record-row {
  height: 44rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24rpx;
  color: #666;
}
.record-text {
  color: #e53e3e;
}
.record-text.subtle {
  color: #888;
}
.record-cancel {
  margin-left: 20rpx;
  color: #2b6cb0;
}

/* 控件顺序：输入框 → 语音 → 发送；输入框自适应，按钮固定宽度 */
.input-bar {
  display: flex;
  align-items: center;
  padding: 12rpx 24rpx;
  background: #fff;
}
.input {
  flex: 1;
  min-width: 0;
  height: 72rpx;
  margin-right: 12rpx;
  background: #f2f3f5;
  border-radius: 36rpx;
  padding: 0 28rpx;
  font-size: 28rpx;
  box-sizing: border-box;
}
.voice-btn {
  flex: 0 0 72rpx;
  width: 72rpx;
  height: 72rpx;
  margin: 0 12rpx 0 0;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  background: #e8f0fb;
  color: #2b6cb0;
  border: none;
  border-radius: 50%;
  line-height: 1;
}
.voice-btn::after {
  border: none;
}
.voice-btn.recording {
  background: #e53e3e;
  color: #fff;
}
.voice-btn.uploading {
  background: #f2f3f5;
  color: #bbb;
}
.voice-btn.starting {
  opacity: 0.6;
}
.voice-icon {
  width: 40rpx;
  height: 40rpx;
  display: block;
}
/* 供读屏软件读取的可访问名称（视觉上隐藏） */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
.send-btn {
  flex: 0 0 140rpx;
  width: 140rpx;
  height: 72rpx;
  line-height: 72rpx;
  margin: 0;
  background: #2b6cb0;
  color: #fff;
  font-size: 28rpx;
  border-radius: 36rpx;
  border: none;
  padding: 0;
}
.send-btn[disabled] {
  background: #b0c4de;
  color: #fff;
}
.send-btn::after {
  border: none;
}
</style>
