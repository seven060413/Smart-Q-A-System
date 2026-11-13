<template>
  <view class="page">
    <!-- 引入侧边栏 -->
    <Sidebar 
      :visible="showSidebar" 
      :currentMenu="currentMenu"
      @close="showSidebar = false"
      @select-menu="onSelectMenu"
    />

    <!-- 登录状态栏 -->
    <view class="topbar">
      <view class="topbar-left">
        <!-- 汉堡菜单按钮 -->
        <text class="menu-btn" @click="showSidebar = true" aria-label="打开菜单">☰</text>
        <text class="topbar-state">{{ authStateText }}</text>
      </view>
      
      <view class="topbar-actions">
        <text v-if="store.auth.user" class="topbar-link" @click="newConversation">新对话</text>
        <!-- 历史链接跳转到历史页面 -->
        <text v-if="store.auth.user" class="topbar-link" @click="goHistory">历史</text>
        <!-- 账号链接保持不变 -->
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
        <text class="welcome-text">我是中小学数学助教，问我教材里的知识吧～\n例如：为什么异分母分数相加要先通分</text>
      </view>

      <!-- 消息列表 -->
      <view v-for="(msg, i) in messages" :key="i" :id="'msg-' + i" class="msg-row">
        <view v-if="msg.role === 'user'" class="msg msg-user">
          <view class="bubble bubble-user">{{ msg.text }}</view>
        </view>

        <view v-else class="msg msg-ai">
          <view class="bubble bubble-ai">
            <view v-if="msg.failed" class="failed-card">
              <view class="failed-title">⚠️ 回答生成失败</view>
              <view class="failed-text">{{ msg.error_message || '请稍后重新提问' }}</view>
              <button v-if="msg.retryQuestion" class="retry-btn" @click="retry(msg)">重新提问</button>
            </view>

            <view v-else-if="msg.refused" class="refuse-card">
              <view class="refuse-title">⚠️ {{ msg.answer }}</view>
              <view v-if="msg.knowledge_point" class="refuse-closest">最接近知识点：{{ msg.knowledge_point }}</view>
            </view>

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
                <view v-if="msg.open.pre" class="section-body" @click.stop>
                  <view v-for="(g, j) in msg.prerequisite_gaps" :key="g.id || j" class="gap-block">
                    <view class="gap">
                      <text class="gap-name">{{ g.name }}</text>
                      <text class="gap-tag" :class="g.required ? 't-required' : 't-suggest'">{{ g.required ? '必需' : '建议' }}</text>
                    </view>

                    <view v-if="g.videos && g.videos.length" class="video-list">
                      <view
                        v-for="(v, k) in g.videos"
                        :key="v.video_id"
                        class="video-card"
                        @click.stop="openVideo(g, v)"
                      >
                        <view class="video-cover">
                          <image v-if="v.cover_url" :src="v.cover_url" mode="aspectFill" class="video-cover-img" />
                          <view v-else class="video-cover-fallback">B站</view>
                          <view class="video-play">▶</view>
                          <text v-if="v.duration_seconds" class="video-duration">{{ formatDuration(v.duration_seconds) }}</text>
                        </view>
                        <view class="video-meta">
                          <text class="video-title">{{ v.title }}</text>
                          <text class="video-author">{{ v.author || 'B 站' }}</text>
                        </view>
                      </view>

                      <!-- #ifdef H5 -->
                      <view
                        v-if="activeVideo && activeVideo.node_key === g.id"
                        class="video-player"
                        @click.stop
                      >
                        <iframe
                          :src="activeVideo.embed_url"
                          class="video-iframe"
                          allowfullscreen="true"
                          allow="autoplay; fullscreen; picture-in-picture"
                          referrerpolicy="no-referrer-when-downgrade"
                          frameborder="0"
                        ></iframe>
                        <view class="video-actions">
                          <text class="video-action" @click.stop="closeVideo">收起播放器</text>
                          <text class="video-action" @click.stop="openMobilePlayer(activeVideo)">移动版播放器</text>
                          <text class="video-action" @click.stop="openWatchPage(activeVideo)">在 B 站打开</text>
                        </view>
                        <text v-if="!h264Supported" class="video-hint warn">当前浏览器缺少 H.264 解码能力，请改用 Chrome/Edge，或点“在 B 站打开”。</text>
                        <text class="video-hint">若提示“不支持 HTML5 播放器”，请点“移动版播放器”或“在 B 站打开”。</text>
                      </view>
                      <!-- #endif -->
                    </view>

                    <view v-else-if="g.videosLoaded" class="video-empty-row">
                      <text class="video-empty">暂无审核通过的视频</text>
                      <text class="video-retry" @click.stop="loadVideos(msg)">刷新</text>
                    </view>
                  </view>

                  <text v-if="msg.prerequisite_gaps.length === 0" class="empty">无</text>
                  <text v-if="msg.videosNoIds" class="video-empty">当前消息缺少知识点编号，请重新提问或刷新页面</text>
                  <text v-if="msg.videosError" class="video-empty">视频加载失败，重新展开可重试</text>
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
                  <template v-if="msg.learning_path.exercises.length">
                    <view v-for="(ex, j) in msg.learning_path.exercises" :key="j" class="exercise">
                      <text class="exercise-no">第 {{ j + 1 }} 题</text>
                      <text class="exercise-text">{{ ex }}</text>
                    </view>
                  </template>
                  <template v-else-if="msg.learning_path.consolidation.length">
                    <text class="exercise-hint">图谱后续知识点（供参考）</text>
                    <view v-for="(c, j) in msg.learning_path.consolidation" :key="j" class="gap">
                      <text class="gap-name">{{ c }}</text>
                    </view>
                  </template>
                  <text v-else class="empty">暂无巩固练习</text>
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

    <!-- 底部输入区 -->
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
import { askQuestion, listMessages, listVideos, transcribeAudio } from '../../api.js'
import AppTabBar from '../../components/AppTabBar.vue'
import Sidebar from './Sidebar.vue' 
import { TAB_INDEX, hideNativeTabBar } from '../../tabbar.js'
import { store } from '../../store.js'
import { formatDuration, buildBilibiliMobileUrl } from '../../video.js'

// 侧边栏控制状态
const showSidebar = ref(false)
const currentMenu = ref('study')

// 用于实时显示最新的本地缓存昵称
const currentNickname = ref('')

// 处理侧边栏点击菜单事件
function onSelectMenu(menu) {
  currentMenu.value = menu.key
  showSidebar.value = false
  
  if (menu.key === 'history') {
    goHistory()
  } else if (menu.key === 'profile') {
    goAuth()
  } else if (menu.key !== 'study') {
    uni.showToast({ title: `即将开发：${menu.name}`, icon: 'none' })
  }
}

const question = ref('')
const loading = ref(false)
const historyLoading = ref(false)
const loadingEarlier = ref(false)
const messages = reactive([])
const scrollTo = ref('')
const messagesCursor = ref('')
const hasEarlier = ref(false)
const activeVideo = ref(null)
const h264Supported = ref(true)

// #ifdef H5
if (typeof document !== 'undefined') {
  const probe = document.createElement('video')
  h264Supported.value = !!probe.canPlayType('video/mp4; codecs="avc1.42E01E"')
}
// #endif

const recordState = ref('idle')
const recordSeconds = ref(0)
const recordStarting = ref(false)
const voiceSupported = ref(false)
let recorder = null
let recordTimer = null
let pendingCancel = false
let pendingStart = false
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
        resolve(true)
      }
      return
    }
    resolve(true)
    // #endif
    // #ifndef APP-PLUS
    resolve(false)
    // #endif
  })
}

function isIndexPageActive() {
  const pages = getCurrentPages()
  const current = pages[pages.length - 1]
  const route = current && current.route ? String(current.route).replace(/^\//, '') : ''
  return route === 'pages/index/index'
}

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
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
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
    stopCurrentRecording()
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
    const allowed = await requestRecordPermission()
    if (!allowed) return
    // #endif
    // #ifdef H5
    if (!checkH5RecorderSupport()) return
    // #endif
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

onHide(() => {
  // #ifdef H5
  if (recordState.value !== 'idle' || pendingStart) invalidateRecordSession()
  // #endif
  // #ifdef APP-PLUS
  if (recordState.value !== 'idle') invalidateRecordSession()
  // #endif
})

onUnload(() => {
  invalidateRecordSession()
})

// 优先读取本地缓存昵称
const authStateText = computed(() => {
  if (!store.auth.ready) return '正在检查登录状态…'
  if (store.auth.user) {
    return '已登录：' + (currentNickname.value || store.auth.user.display_name || store.auth.user.username)
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
  // 👇 新增：清空时，同时清除本地缓存
  uni.removeStorageSync('last_conversation_id')
}

function newConversation() {
  if (loading.value || recordStarting.value || recordState.value !== 'idle') return
  clearConversationView()
  uni.showToast({ title: '已开始新对话', icon: 'none' })
}

function newRequestId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID()
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`
}

function normalizeLearningPath(payload) {
  const lp = (payload && payload.learning_path) || payload || {}
  let exercises = lp.exercises
  if (!Array.isArray(exercises)) {
    exercises = Array.isArray(payload && payload.exercises) ? payload.exercises : []
  }
  return {
    prerequisites: Array.isArray(lp.prerequisites) ? lp.prerequisites : [],
    prerequisite_ids: Array.isArray(lp.prerequisite_ids) ? lp.prerequisite_ids : [],
    body: lp.body || '',
    body_id: lp.body_id || '',
    consolidation: Array.isArray(lp.consolidation) ? lp.consolidation : [],
    consolidation_ids: Array.isArray(lp.consolidation_ids) ? lp.consolidation_ids : [],
    exercises,
  }
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
        id: m.id || '',
        answer: m.content || '',
        knowledge_point: m.knowledge_point || '',
        prerequisite_gaps: m.prerequisite_gaps || [],
        learning_path: normalizeLearningPath(m),
        source: m.source || '',
        refused: !!m.refused,
        failed: m.status === 'failed',
        error_message: m.error_message || '',
        retryQuestion: lastUser,
        open: { pre: false, body: true, cons: false },
        videosLoaded: false,
        videosLoading: false,
        videosError: false,
        videosNoIds: false,
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
    // 👇 新增：成功加载后，更新本地缓存
    uni.setStorageSync('last_conversation_id', conversationId)
    
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
  hideNativeTabBar()

  if (options && options.conversation_id) {
    const conversationId = options.conversation_id
    if (store.auth.ready) {
      loadConversation(conversationId)
    } else {
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
    // 👇 修复：如果 URL 没有带 id，尝试从本地缓存恢复上次的会话
    const lastId = uni.getStorageSync('last_conversation_id')
    if (lastId && !store.currentConversationId) {
      store.currentConversationId = lastId
    }
  }
})

onShow(() => {
  hideNativeTabBar()

  // 每次页面显示，重新读取最新缓存昵称
  const savedNickname = uni.getStorageSync('custom_nickname')
  currentNickname.value = savedNickname || ''

  const action = store.pendingIndexAction
  if (action) {
    store.pendingIndexAction = null

    if (action.type === 'open' && action.conversationId) {
      loadConversation(action.conversationId)
      return
    }
    if (action.type === 'new') {
      if (loading.value || recordStarting.value || recordState.value !== 'idle') return
      clearConversationView()
      return
    }
  }

  // 👇 核心修复：如果页面被重新挂载，但之前有会话 ID 或本地缓存，且消息列表为空，自动重新加载
  let activeId = store.currentConversationId || uni.getStorageSync('last_conversation_id')
  if (activeId && messages.length === 0 && !historyLoading.value && !loading.value) {
    loadConversation(activeId)
  }
})

function scrollBottom() {
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
        // 👇 新增：每次提问成功，都把最新会话 ID 保存到本地缓存
        uni.setStorageSync('last_conversation_id', data.conversation_id)
      }
      messages.push({
        role: 'ai',
        id: data.assistant_message_id || '',
        answer: data.answer || '',
        knowledge_point: data.knowledge_point || '',
        prerequisite_gaps: data.prerequisite_gaps || [],
        learning_path: normalizeLearningPath(data),
        source: data.source || '',
        refused: !!data.refused,
        failed: false,
        error_message: '',
        retryQuestion: q,
        open: { pre: false, body: true, cons: false },
        videosLoaded: false,
        videosLoading: false,
        videosError: false,
        videosNoIds: false,
      })
    })
    .catch((e) => {
      if (e && e.status === 404) {
        store.currentConversationId = ''
        uni.removeStorageSync('last_conversation_id')
      }
      const errMsg =
        e && e.status === 401
          ? '登录已过期，请重新登录后重试'
          : (e && e.message) || '网络请求失败，请检查后端是否启动、地址是否配置正确'
      messages.push({
        role: 'ai',
        id: '',
        answer: '',
        refused: false,
        failed: true,
        error_message: errMsg,
        knowledge_point: '',
        prerequisite_gaps: [],
        learning_path: normalizeLearningPath(null),
        source: '',
        retryQuestion: q,
        open: { pre: false, body: true, cons: false },
        videosLoaded: false,
        videosLoading: false,
        videosError: false,
        videosNoIds: false,
      })
    })
    .finally(() => {
      loading.value = false
      scrollBottom()
    })
}

function openVideo(gap, video) {
  // #ifdef H5
  const current = activeVideo.value
  if (
    current &&
    current.video_id === video.video_id &&
    current.node_key === gap.id
  ) {
    activeVideo.value = null
  } else {
    activeVideo.value = { ...video, node_key: gap.id }
  }
  return
  // #endif
  // #ifndef H5
  const bvid = encodeURIComponent(video.bvid || '')
  const page = Number(video.page || 1)
  const aid = encodeURIComponent(video.aid || '')
  const cid = encodeURIComponent(video.cid || '')
  const title = encodeURIComponent(video.title || '视频讲解')
  uni.navigateTo({
    url: `/pages/video/video?bvid=${bvid}&page=${page}&aid=${aid}&cid=${cid}&title=${title}`,
  })
  // #endif
}

function openMobilePlayer(video) {
  if (!video) return
  const mobileUrl = buildBilibiliMobileUrl(video.bvid, video.page)
  if (!mobileUrl) return
  activeVideo.value = { ...video, embed_url: mobileUrl }
}

function openWatchPage(video) {
  if (!video || !video.watch_url) return
  // #ifdef H5
  window.open(video.watch_url, '_blank')
  // #endif
  // #ifdef APP-PLUS
  plus.runtime.openURL(video.watch_url)
  // #endif
}

function closeVideo() {
  activeVideo.value = null
}

async function loadVideos(msg) {
  if (!msg || msg.videosLoading) return
  const gaps = (msg.prerequisite_gaps || []).filter((g) => g && g.id)
  if (!gaps.length) {
    msg.videosLoaded = true
    msg.videosNoIds = true
    return
  }
  msg.videosNoIds = false

  msg.videosLoading = true
  msg.videosError = false
  try {
    const data = await listVideos(gaps.map((g) => g.id), { limit: 2 })
    const byNode = {}
    for (const item of data.items || []) {
      byNode[item.node_key] = item.videos || []
    }
    for (const gap of gaps) {
      gap.videos = byNode[gap.id] || []
      gap.videosLoaded = true
    }
    msg.videosLoaded = true
  } catch (e) {
    msg.videosError = true
    uni.showToast({ title: (e && e.message) || '视频加载失败', icon: 'none' })
  } finally {
    msg.videosLoading = false
  }
}

function toggle(msg, key) {
  msg.open[key] = !msg.open[key]
  if (key === 'pre' && msg.open.pre) loadVideos(msg)
}

function goPath(msg) {
  store.learningPath = msg.learning_path
  store.knowledgePoint = msg.knowledge_point
  store.source = msg.source
  uni.navigateTo({ url: '/pages/path/path' })
}
</script>

<style>
/* ...原有样式全部保留... */
.page {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f5f6f8;
}

/* #ifdef H5 */
.page {
  height: calc(100vh - var(--window-top, 0px) - var(--window-bottom, 0px));
}
/* #endif */

/* 优化后的顶部栏样式 */
.topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20rpx 32rpx; 
  background: #ffffff;
  box-shadow: 0 2rpx 12rpx rgba(0, 0, 0, 0.03);
  position: relative;
  z-index: 10;
}

.topbar-left {
  display: flex;
  align-items: center;
  gap: 16rpx;
}

.menu-btn {
  font-size: 36rpx;
  color: #333;
  cursor: pointer;
  font-weight: bold;
  padding-right: 8rpx;
  transition: transform 0.1s;
}
.menu-btn:active {
  transform: scale(0.9); 
}

.topbar-state {
  font-size: 24rpx;
  color: #888;
  background: #f4f5f7; 
  padding: 4rpx 16rpx;
  border-radius: 20rpx;
}

.topbar-actions {
  display: flex;
  gap: 12rpx; 
  align-items: center;
}

.topbar-link {
  font-size: 26rpx;
  color: #444; 
  padding: 8rpx 16rpx; 
  border-radius: 12rpx;
  cursor: pointer;
  transition: background 0.2s;
}

.topbar-link:active {
  background: #f0f2f5;
  color: #2b6cb0; 
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

.gap-block {
  padding: 8rpx 0;
}
.gap-block + .gap-block {
  border-top: 1rpx dashed #f2f2f2;
}
.video-list {
  display: flex;
  flex-wrap: wrap;
  gap: 16rpx;
  margin: 4rpx 0 12rpx;
}
.video-card {
  flex: 1 1 280rpx;
  min-width: 240rpx;
  max-width: 100%;
  display: flex;
  gap: 12rpx;
  padding: 10rpx;
  background: #f8fafc;
  border: 1rpx solid #e6eef8;
  border-radius: 14rpx;
}
.video-cover {
  position: relative;
  width: 160rpx;
  height: 100rpx;
  flex: 0 0 160rpx;
  border-radius: 10rpx;
  overflow: hidden;
  background: #1f2a37;
}
.video-cover-img {
  width: 100%;
  height: 100%;
  display: block;
}
.video-cover-fallback {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 24rpx;
  background: #2b6cb0;
}
.video-play {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  left: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 30rpx;
  background: rgba(0, 0, 0, 0.28);
}
.video-duration {
  position: absolute;
  right: 6rpx;
  bottom: 6rpx;
  font-size: 18rpx;
  color: #fff;
  background: rgba(0, 0, 0, 0.62);
  padding: 0 6rpx;
  border-radius: 4rpx;
}
.video-meta {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.video-title {
  font-size: 24rpx;
  color: #333;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.video-author {
  margin-top: 6rpx;
  font-size: 20rpx;
  color: #999;
}
.video-empty {
  display: block;
  font-size: 22rpx;
  color: #bbb;
  padding: 4rpx 0 8rpx;
}
.video-empty-row {
  display: flex;
  align-items: center;
  gap: 16rpx;
}
.video-retry {
  font-size: 22rpx;
  color: #2b6cb0;
  padding: 4rpx 0 8rpx;
}
.video-player {
  width: 100%;
  flex: 1 0 100%;
  margin: 8rpx 0 16rpx;
}
.video-iframe {
  width: 100%;
  height: 380rpx;
  border: 0;
  border-radius: 12rpx;
  background: #000;
}
.video-close {
  display: block;
  text-align: center;
  font-size: 22rpx;
  color: #2b6cb0;
  padding: 8rpx 0;
}
.video-actions {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 20rpx;
  padding: 8rpx 0;
}
.video-action {
  font-size: 22rpx;
  color: #2b6cb0;
}
.video-hint {
  display: block;
  text-align: center;
  font-size: 20rpx;
  color: #bbb;
  padding: 0 0 8rpx;
}
.video-hint.warn {
  color: #c05621;
}
.empty {
  font-size: 26rpx;
  color: #bbb;
}
.exercise {
  padding: 12rpx 0;
  border-bottom: 1rpx dashed #eee;
}
.exercise:last-child {
  border-bottom: none;
}
.exercise-no {
  display: block;
  font-size: 24rpx;
  font-weight: 600;
  color: #2b6cb0;
  margin-bottom: 6rpx;
}
.exercise-text {
  display: block;
  font-size: 28rpx;
  color: #333;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}
.exercise-hint {
  display: block;
  font-size: 22rpx;
  color: #999;
  margin-bottom: 8rpx;
}

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

.composer {
  background: #fff;
  border-top: 1rpx solid #eee;
}

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