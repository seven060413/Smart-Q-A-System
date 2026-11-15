<template>
  <view class="page">
    <!-- 引入侧边栏 -->
    <Sidebar 
      :visible="showSidebar" 
      :currentMenu="currentMenu"
      @close="showSidebar = false"
      @select-menu="onSelectMenu"
    />

    <!-- 自定义导航栏 -->
    <view class="topbar" :style="{ paddingTop: statusBarHeight + 'px' }">
      <view class="topbar-left">
        <!-- 汉堡菜单按钮 -->
        <text class="menu-btn" @click="showSidebar = true" aria-label="打开菜单">☰</text>
        <text class="topbar-title">数学知识问答</text>
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
          <view class="msg-content">
            <view v-if="msg.attachment" class="question-card">
              <view class="question-card-head"><text>{{ msg.attachment.mediaType === 'application/pdf' ? 'PDF 题目' : '题目图片' }}</text><text class="question-status">{{ msg.attachment.statusText }}</text></view>
              <text v-if="msg.attachment.errorText" class="question-error">{{ msg.attachment.errorText }}</text>
              <button v-if="msg.attachment.statusText === '解答失败'" class="question-retry" :disabled="attachmentBusy" @click="solveMessageAttachment(msg)">重试解答</button>
              <button v-if="msg.attachment.statusText === '上传失败'" class="question-retry" :disabled="attachmentBusy" @click="retryAttachmentUpload(msg)">重新上传</button>
              <text v-if="typeof msg.attachment.ocr_confidence === 'number' && msg.attachment.ocr_confidence < 0.7" class="ocr-warning">⚠ 识别结果可能有误，请检查数字、分数和运算符</text>
              <image v-if="msg.attachment.filePath && msg.attachment.mediaType !== 'application/pdf'" :src="msg.attachment.filePath" mode="widthFix" class="question-image" @click="previewMessageAttachment(msg)" />
              <view class="question-file">{{ msg.attachment.name }} · {{ formatBytes(msg.attachment.size) }}<text v-if="msg.attachment.pageCount"> · {{ msg.attachment.pageCount }} 页</text></view>
              <button v-if="msg.attachment.id" class="question-preview" @click="previewMessageAttachment(msg)">{{ msg.attachment.mediaType === 'application/pdf' ? '打开 PDF 文件' : '查看原图' }}</button>
              <view v-if="msg.attachment.failedPages && msg.attachment.failedPages.length" class="question-error">第 {{ msg.attachment.failedPages.join('、') }} 页识别失败，已保留其他页面结果</view>
              <text class="question-label">识别出的题目</text>
              <textarea v-model="msg.attachment.ocrText" class="question-text" maxlength="20000" placeholder="等待识别或请输入题目" />
              <view class="question-actions">
                <button v-if="msg.attachment.id" :disabled="attachmentBusy" @click="recognizeMessageAttachment(msg)">重新识别</button>
                <button :disabled="attachmentBusy || !msg.attachment.id || !msg.attachment.ocrText.trim()" @click="solveMessageAttachment(msg)">{{ attachmentBusy ? '正在处理…' : '确认题目并生成解答' }}</button>
              </view>
            </view>
            <view v-else class="bubble bubble-user">{{ msg.text }}</view>
          </view>
          <image v-if="userAvatar" :src="userAvatar" class="message-avatar" mode="aspectFill" />
          <view v-else class="message-avatar avatar-fallback" aria-label="用户头像"></view>
        </view>

        <view v-else class="msg msg-ai">
          <image src="/static/math-assistant.svg" class="message-avatar" mode="aspectFill" />
          <view class="msg-content">
            <view class="assistant-name">数学助教</view>
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
              <view class="answer-summary">
                <text class="summary-label">{{ msg.knowledge_confidence < 0.35 ? '知识点未可靠匹配' : '知识点匹配' }}</text>
                <view class="head">
                <text class="chip">{{ msg.knowledge_point }}</text>
                <text v-if="msg.knowledge_confidence !== undefined" class="confidence">匹配 {{ Math.round(msg.knowledge_confidence * 100) }}%</text>
                <text class="source">📚 {{ msg.source }}</text>
                </view>
              </view>
              <view v-if="msg.knowledge_candidates && msg.knowledge_candidates.length" class="candidate-list">
                <text class="candidate-label">请选择更符合的知识点</text>
                <button v-for="candidate in msg.knowledge_candidates" :key="candidate.id" class="candidate-item candidate-button" :disabled="attachmentBusy" @click.stop="solveWithCandidate(msg, candidate)">{{ candidate.name }} · {{ Math.round(candidate.confidence * 100) }}%</button>
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

              <!-- 解题过程 -->
              <view class="section answer-section" @click="toggle(msg, 'body')">
                <view class="section-head">
                  <text>🧩 解题过程</text>
                  <text class="arrow">{{ msg.open.body ? '▾' : '▸' }}</text>
                </view>
                <view v-if="msg.open.body" class="section-body">
                  <view v-for="(step, stepIndex) in answerStepList(msg)" :key="stepIndex" class="solution-step">
                    <view class="solution-step-head"><text class="solution-step-no">{{ stepIndex + 1 }}</text><text class="solution-step-title">{{ step.title || `第 ${stepIndex + 1} 步` }}</text></view>
                    <text class="solution-step-content">{{ step.content }}</text>
                  </view>
                  <view v-if="msg.final_answer || finalAnswer(msg.answer)" class="final-answer"><text class="final-label">最终答案</text><text class="final-text">{{ msg.final_answer || finalAnswer(msg.answer) }}</text></view>
                </view>
              </view>

              <!-- 三层折叠：巩固练习 -->
              <view class="section" @click="toggle(msg, 'cons')">
                <view class="section-head">
                  <text>✏️ 巩固练习</text>
                  <text class="section-count">{{ exerciseCount(msg) ? `有 ${exerciseCount(msg)} 道巩固练习` : '暂无巩固练习' }}</text>
                  <text class="arrow">{{ msg.open.cons ? '▾' : '▸' }}</text>
                </view>
                <view v-if="msg.open.cons" class="section-body">
                  <template v-if="exerciseCount(msg)">
                    <view v-for="(ex, j) in (msg.exercises && msg.exercises.length ? msg.exercises : msg.learning_path.exercises)" :key="j" class="exercise">
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

      <view v-if="attachment.filePath && !attachmentMessage" class="attachment-draft">
        <view v-if="attachment.mediaType === 'application/pdf'" class="attachment-thumb attachment-pdf">PDF</view>
        <image v-else :src="attachment.filePath" mode="aspectFill" class="attachment-thumb" @click="previewDraftAttachment" />
        <view class="attachment-draft-meta">
          <text class="attachment-name">{{ attachment.name }}</text>
          <text class="attachment-size">{{ formatBytes(attachment.size) }} · {{ attachment.statusText }}</text>
        </view>
        <button class="attachment-remove" :disabled="attachmentBusy" aria-label="删除图片" @click="clearAttachment">×</button>
      </view>
      <view v-if="attachment.id" class="attachment-text-editor">
        <textarea v-model="attachment.ocrText" maxlength="20000" placeholder="请核对或修改识别出的题目" @input="syncOcrText" />
        <view class="attachment-actions">
          <button :disabled="attachmentBusy" @click="recognizeAttachment">重新识别</button>
          <button :disabled="attachmentBusy || !attachment.ocrText.trim()" @click="solveAttachment">提交题目</button>
        </view>
      </view>
      <view class="input-bar">
        <textarea
          class="input"
          v-model="question"
          placeholder="输入你的问题…"
          :disabled="loading || recordStarting || recordState !== 'idle'"
          :auto-height="true"
          :maxlength="-1"
          confirm-type="send"
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
          class="plus-btn"
          :disabled="loading || attachmentBusy || recordStarting || recordState !== 'idle'"
          aria-label="添加图片题目"
          @click="toggleAttachmentMenu"
        >＋</button>
        <button
          class="send-btn"
          :disabled="loading || attachmentBusy || (!question && (!attachment.filePath || attachment.id)) || recordStarting || recordState !== 'idle'"
          @click="send"
        >发送</button>
      </view>
      <view v-if="attachment.menuOpen" class="attachment-menu">
        <view class="attachment-menu-item" @click="chooseAttachment('album')">
          <view class="attachment-menu-icon">
            <text class="ami-icon">🖼️</text>
          </view>
          <text class="ami-label">相册</text>
        </view>
        <view class="attachment-menu-item" @click="chooseAttachment('camera')">
          <view class="attachment-menu-icon">
            <text class="ami-icon">📷</text>
          </view>
          <text class="ami-label">拍照</text>
        </view>
        <view class="attachment-menu-item" @click="choosePdf">
          <view class="attachment-menu-icon">
            <text class="ami-icon">📄</text>
          </view>
          <text class="ami-label">文件</text>
        </view>
      </view>
    </view>

    <AppTabBar :active="TAB_INDEX" />
  </view>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { onHide, onLoad, onShow, onUnload } from '@dcloudio/uni-app'
import { askQuestion, attachmentAction, attachmentContent, attachmentStatus, deleteAttachment, listMessages, listVideos, transcribeAudio, uploadAttachment } from '../../api.js'
import AppTabBar from '../../components/AppTabBar.vue'
import Sidebar from './Sidebar.vue' 
import { TAB_INDEX, hideNativeTabBar } from '../../tabbar.js'
import { store } from '../../store.js'
import { BASE_URL } from '../../config.js'
import { formatDuration, buildBilibiliMobileUrl } from '../../video.js'

// 侧边栏控制状态
const showSidebar = ref(false)
const currentMenu = ref('study')

// 状态栏高度（自定义导航栏适配）
const statusBarHeight = ref(0)
// #ifdef H5
statusBarHeight.value = 0
// #endif
// #ifdef APP-PLUS
try {
  const sysInfo = uni.getSystemInfoSync()
  statusBarHeight.value = (sysInfo && sysInfo.statusBarHeight) || 0
} catch (e) {
  statusBarHeight.value = 0
}
// #endif

// 用于实时显示最新的本地缓存昵称
const currentNickname = ref('')
const userAvatar = ref('')
const attachmentMessage = ref(null)
const previewingAttachment = ref(false)

// 处理侧边栏点击菜单事件
function loadUserAvatar() {
  userAvatar.value = uni.getStorageSync('user_avatar') || ''
}

function exerciseCount(msg) {
  if (Array.isArray(msg && msg.exercises) && msg.exercises.length) return msg.exercises.length
  return Array.isArray(msg && msg.learning_path && msg.learning_path.exercises)
    ? msg.learning_path.exercises.length
    : 0
}

function answerStepList(msg) {
  if (Array.isArray(msg && msg.solution_steps) && msg.solution_steps.length) return msg.solution_steps
  const text = String((msg && msg.answer) || '')
  const trimmed = text.trim()
  // 兼容后端返回的 JSON 字符串可能被括号包裹，如 ({"steps":[...],"final_answer":"..."})
  const jsonStr = (trimmed.startsWith('(') && trimmed.endsWith(')')) ? trimmed.slice(1, -1) : trimmed
  if (jsonStr.startsWith('{')) {
    try {
      const parsed = JSON.parse(jsonStr)
      if (Array.isArray(parsed.steps)) return parsed.steps.map((step, index) => ({
        title: typeof step === 'object' ? (step.title || `第 ${index + 1} 步`) : `第 ${index + 1} 步`,
        content: typeof step === 'object' ? (step.content || '') : String(step),
      })).filter((step) => step.content)
    } catch (e) {}
  }
  const clean = text.replace(/(?:最终答案|答案)\s*[:：].*$/is, '').trim()
  return clean.split(/\n+/).map((line, index) => ({ title: `第 ${index + 1} 步`, content: line.replace(/^\s*\d+[.、)）]\s*/, '') })).filter((step) => step.content)
}

function finalAnswer(answer) {
  // 先尝试从纯文本中正则匹配
  const textMatch = String(answer || '').match(/(?:最终答案|答案)\s*[:：]\s*(.+)$/is)
  if (textMatch) return textMatch[1].trim()
  // 再尝试从 JSON 结构中提取 final_answer 字段（兼容后端返回的括号包裹格式）
  const trimmed = String(answer || '').trim()
  const jsonStr = (trimmed.startsWith('(') && trimmed.endsWith(')')) ? trimmed.slice(1, -1) : trimmed
  if (jsonStr.startsWith('{')) {
    try {
      const parsed = JSON.parse(jsonStr)
      if (parsed.final_answer) return parsed.final_answer
    } catch (e) {}
  }
  return ''
}

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
const attachmentBusy = ref(false)
const attachment = reactive({
  filePath: '', file: null, name: '', size: 0, id: '', ocrText: '', statusText: '', menuOpen: false, mediaType: '', pageCount: 0, failedPages: [],
})
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

onShow(() => {
  loadUserAvatar()
})

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
  clearAttachment()
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
    steps: Array.isArray(lp.steps) ? lp.steps : (Array.isArray(payload && payload.solution_steps) ? payload.solution_steps : []),
    final_answer: lp.final_answer || payload.final_answer || '',
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
      const item = { role: 'user', text: lastUser }
      const attachment = m.attachment
      if (attachment) {
        const mediaType = attachment.media_type || ''
        item.attachment = {
          id: attachment.id,
          name: attachment.name || attachment.original_name,
          size: attachment.byte_size || 0,
          mediaType,
          pageCount: attachment.page_count || 0,
          failedPages: attachment.failed_pages || [],
          errorCode: attachment.error_code || '',
          ocrText: attachment.question_text || attachment.ocr_text || lastUser,
          statusText: attachment.ocr_status === 'completed' ? '识别完成，请核对题目' : (attachment.ocr_status || '处理中'),
          ocr_confidence: attachment.ocr_confidence,
          filePath: '',
        }
        if (mediaType !== 'application/pdf') {
          attachmentContent(attachment.id).then((url) => { item.attachment.filePath = url }).catch((error) => {
            item.attachment.statusText = '附件加载失败'
            item.attachment.errorText = (error && error.message) || '无法加载附件文件'
          })
        }
      }
      out.push(item)
    } else if (m.role === 'assistant') {
      out.push({
        role: 'ai',
        id: m.id || '',
        answer: m.content || '',
        final_answer: (m.learning_path && m.learning_path.final_answer) || '',
        steps: (m.learning_path && m.learning_path.steps) || m.content || '',
        exercises: m.exercises || (m.learning_path && m.learning_path.exercises) || [],
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

function formatBytes(size) {
  if (!size) return '大小未知'
  return size < 1024 * 1024 ? `${Math.ceil(size / 1024)} KB` : `${(size / 1024 / 1024).toFixed(1)} MB`
}

async function previewDraftAttachment() {
  if (!attachment.filePath) return
  if (attachment.mediaType === 'application/pdf') {
    uni.showToast({ title: '请先上传 PDF，再从消息中打开原文件', icon: 'none' })
    return
  }
  // #ifdef H5
  if (typeof window !== 'undefined') window.open(attachment.filePath, '_blank', 'noopener')
  // #endif
  // #ifndef H5
  uni.previewImage({ current: attachment.filePath, urls: [attachment.filePath] })
  // #endif
}

async function previewMessageAttachment(msg) {
  if (!msg || !msg.attachment || previewingAttachment.value) return
  const item = msg.attachment
  // Open the tab during the user gesture so H5 browsers do not block it.
  // #ifdef H5
  const pdfWindow = item.mediaType === 'application/pdf' && typeof window !== 'undefined' ? window.open('', '_blank') : null
  // #endif
  previewingAttachment.value = true
  try {
    if (!item.filePath && item.id) item.filePath = await attachmentContent(item.id)
    if (!item.filePath) throw new Error('无法加载附件文件')
    if (item.mediaType === 'application/pdf') {
      await openAttachmentFile(item.id, item.filePath, item.name, item.mediaType, pdfWindow)
    } else {
      // #ifdef H5
      if (typeof window !== 'undefined') window.open(item.filePath, '_blank', 'noopener')
      // #endif
      // #ifndef H5
      uni.previewImage({ current: item.filePath, urls: [item.filePath] })
      // #endif
    }
  } catch (error) {
    // #ifdef H5
    if (pdfWindow && !pdfWindow.closed) pdfWindow.close()
    // #endif
    uni.showToast({ title: (error && error.message) || '附件打开失败', icon: 'none' })
  } finally {
    previewingAttachment.value = false
  }
}

async function openAttachmentFile(attachmentId, url, name, mediaType, pdfWindow = null) {
  // #ifdef H5
  if (url && typeof window !== 'undefined') {
    if (pdfWindow && !pdfWindow.closed) pdfWindow.location.href = url
    else window.open(url, '_blank', 'noopener')
    return
  }
  // #endif
  // #ifdef APP-PLUS
  const token = store.auth.token || ''
  const response = await new Promise((resolve, reject) => uni.request({
    url: `${BASE_URL}/api/attachments/${encodeURIComponent(attachmentId)}/content`,
    method: 'GET',
    responseType: 'arraybuffer',
    header: { Authorization: `Bearer ${token}` },
    success: (res) => res.statusCode >= 200 && res.statusCode < 300 ? resolve(res.data) : reject(new Error('PDF 下载失败')),
    fail: () => reject(new Error('PDF 下载失败')),
  }))
  const filename = `${Date.now()}-${String(name || 'document.pdf').replace(/[^\\w.-]/g, '_')}`
  const entry = await new Promise((resolve, reject) => plus.io.requestFileSystem(plus.io.PRIVATE_DOC, (fs) => fs.root.getFile(filename, { create: true }, resolve, reject), reject))
  await new Promise((resolve, reject) => entry.createWriter((writer) => {
    writer.onwrite = resolve
    writer.onerror = () => reject(new Error('PDF 保存失败'))
    writer.write(new Blob([response], { type: mediaType || 'application/pdf' }))
  }, reject))
  plus.runtime.openFile(entry.toLocalURL(), {}, () => uni.showToast({ title: '当前设备没有可用的 PDF 阅读器', icon: 'none' }))
  // #endif
  // #ifndef H5
  // #ifndef APP-PLUS
  uni.showToast({ title: '当前平台暂不支持打开 PDF', icon: 'none' })
  // #endif
  // #endif
}

function clearAttachment() {
  if (attachment.id) deleteAttachment(attachment.id).catch(() => {})
  Object.assign(attachment, { filePath: '', file: null, name: '', size: 0, id: '', ocrText: '', statusText: '', menuOpen: false, mediaType: '', pageCount: 0, failedPages: [] })
  attachmentMessage.value = null
}

function choosePdf() {
  attachment.menuOpen = false
  // #ifdef H5
  if (typeof document !== 'undefined') {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'application/pdf,.pdf'
    input.onchange = () => {
      const file = input.files && input.files[0]
      if (!file) return
      setPdfDraft(file.name || 'document.pdf', file, file.name || 'document.pdf', file.size || 0)
    }
    input.click()
    return
  }
  // #endif
  if (typeof uni.chooseFile === 'function') {
    uni.chooseFile({ count: 1, type: 'file', extension: ['pdf'], success: (res) => {
      const file = res.tempFiles && res.tempFiles[0]
      const path = (res.tempFilePaths && res.tempFilePaths[0]) || (file && file.path)
      if (file && path) setPdfDraft(path, null, file.name || '题目.pdf', file.size || 0)
    }, fail: () => uni.showToast({ title: '未选择 PDF 文件', icon: 'none' }) })
  } else {
    uni.showToast({ title: '当前平台暂不支持选择 PDF 文件', icon: 'none' })
  }
}

function setPdfDraft(filePath, file, name, size) {
  if (size > 20 * 1024 * 1024) {
    uni.showToast({ title: 'PDF 文件不能超过 20 MB', icon: 'none' })
    return
  }
  const draft = { filePath: String(filePath || name || 'document.pdf'), file: typeof File !== 'undefined' && file instanceof File ? file : null, name, size, id: '', ocrText: '', statusText: '待发送', mediaType: 'application/pdf', pageCount: 0, failedPages: [] }
  Object.assign(attachment, draft)
  const message = { role: 'user', text: '', attachment: { ...draft } }
  messages.push(message)
  attachmentMessage.value = message
  scrollBottom()
}

function toggleAttachmentMenu() {
  if (!store.auth.user) {
    uni.showToast({ title: '登录后才能上传题目图片', icon: 'none' })
    return
  }
  attachment.menuOpen = !attachment.menuOpen
}

function chooseAttachment(sourceType) {
  attachment.menuOpen = false
  uni.chooseImage({ count: 1, sizeType: ['compressed'], sourceType: [sourceType], success: (res) => {
    const path = res.tempFilePaths && res.tempFilePaths[0]
    const file = res.tempFiles && res.tempFiles[0]
    if (!path) return
    const name = (file && file.name) || path.split('/').pop() || '题目图片'
    const size = (file && file.size) || 0
    const lower = name.toLowerCase()
    if (lower && !/\.(jpe?g|png)$/.test(lower)) {
      uni.showToast({ title: '仅支持 JPG 或 PNG 图片', icon: 'none' })
      return
    }
    const draft = { filePath: path, file: file && typeof File !== 'undefined' && file instanceof File ? file : null, name, size, id: '', ocrText: '', statusText: '待发送' }
    Object.assign(attachment, { ...draft, menuOpen: false })
    const message = { role: 'user', text: '', attachment: { ...draft } }
    messages.push(message)
    attachmentMessage.value = message
    scrollBottom()
  }, fail: () => uni.showToast({ title: '未选择图片', icon: 'none' }) })
}

async function recognizeAttachment({ fromUpload = false } = {}) {
  const target = attachmentMessage.value && attachmentMessage.value.attachment
  if (!attachment.id || (attachmentBusy.value && !fromUpload)) return
  attachmentBusy.value = true
  attachment.statusText = '识别中'
  try {
    let data
    if (attachment.mediaType === 'application/pdf') {
      data = await attachmentStatus(attachment.id)
      if (data.ocr_status === 'failed') {
        data = await attachmentAction(attachment.id, 'recognize')
      }
      for (let attempt = 0; attempt < 45 && data.ocr_status === 'processing'; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 2000))
        data = await attachmentStatus(attachment.id)
      }
    } else {
      data = await attachmentAction(attachment.id, 'recognize')
    }
    attachment.ocrText = data.ocr_text || ''
    attachment.pageCount = data.page_count || 0
    attachment.failedPages = data.failed_pages || []
    attachment.statusText = data.ocr_status === 'partial' ? '部分页面识别完成' : (data.ocr_status === 'failed' ? `识别失败${data.error_code ? `（${data.error_code}）` : ''}` : '识别完成，请核对题目')
    if (target) Object.assign(target, { id: attachment.id, ocrText: attachment.ocrText, statusText: attachment.statusText, ocr_confidence: data.ocr_confidence, pageCount: attachment.pageCount, failedPages: attachment.failedPages, mediaType: attachment.mediaType, errorCode: data.error_code })
    if (!attachment.ocrText) uni.showToast({ title: '未识别到题目文字，请手动输入', icon: 'none' })
  } catch (e) {
    attachment.statusText = '识别失败'
    if (target) Object.assign(target, { statusText: attachment.statusText, errorText: (e && e.message) || '识别失败，请重试' })
    uni.showToast({ title: (e && e.message) || '图片识别失败', icon: 'none' })
  } finally { attachmentBusy.value = false }
}

async function recognizeMessageAttachment(msg) {
  if (!msg || !msg.attachment) return
  attachmentMessage.value = msg
  Object.assign(attachment, msg.attachment)
  await recognizeAttachment()
}

async function solveMessageAttachment(msg) {
  if (!msg || !msg.attachment) return
  attachmentMessage.value = msg
  // 只同步 id 和状态，不覆盖用户可能在编辑区修改的 ocrText
  attachment.id = msg.attachment.id
  attachment.statusText = msg.attachment.statusText
  attachment.mediaType = msg.attachment.mediaType
  attachment.name = msg.attachment.name
  attachment.size = msg.attachment.size
  attachment.filePath = msg.attachment.filePath
  attachment.pageCount = msg.attachment.pageCount || 0
  attachment.failedPages = msg.attachment.failedPages || []
  // 确保使用当前编辑区最新的 ocrText，而不是卡片中的旧值
  if (!attachment.ocrText.trim() && msg.attachment.ocrText) {
    attachment.ocrText = msg.attachment.ocrText
  }
  await solveAttachment()
}

/**
 * 同步编辑区的 OCR 文本到消息卡片，确保两边数据一致
 */
function syncOcrText() {
  if (attachmentMessage.value && attachmentMessage.value.attachment) {
    attachmentMessage.value.attachment.ocrText = attachment.ocrText
  }
}

async function solveWithCandidate(msg, candidate) {
  if (!msg || !candidate || !msg.attachment || attachmentBusy.value) return
  attachmentMessage.value = msg
  // 只同步元数据，保留编辑区最新的 ocrText
  attachment.id = msg.attachment.id
  attachment.statusText = msg.attachment.statusText
  if (!attachment.ocrText.trim() && msg.attachment.ocrText) {
    attachment.ocrText = msg.attachment.ocrText
  }
  await solveAttachment(candidate.id)
}

async function solveAttachment(knowledgePointId = null) {
  const text = (typeof attachment.ocrText === 'string') ? attachment.ocrText.trim() : String(attachment.ocrText || '').trim()
  if (!attachment.id || !text || attachmentBusy.value) return
  attachmentBusy.value = true
  attachment.statusText = '知识点匹配与解答生成中'
  // 构建请求体，只包含有效值（注意：knowledgePointId 可能是点击事件对象而非字符串）
  const payload = { text }
  if (store.currentConversationId) payload.conversation_id = store.currentConversationId
  if (typeof knowledgePointId === 'string' && knowledgePointId) payload.knowledge_point_id = knowledgePointId
  try {
    const data = await attachmentAction(attachment.id, 'solve', payload)
    if (attachmentMessage.value) attachmentMessage.value.attachment.ocrText = text
    messages.push({ role: 'ai', id: data.assistant_message_id || '', answer: data.answer || data.coverage_note || '', solution_steps: data.solution_steps || [], final_answer: data.final_answer || '', exercises: data.exercises || [], knowledge_point: data.knowledge_point || '', knowledge_confidence: data.knowledge_confidence, knowledge_candidates: data.knowledge_candidates || [], prerequisite_gaps: data.prerequisite_gaps || [], learning_path: normalizeLearningPath(data), source: data.source || '', refused: !!data.refused, failed: false, retryQuestion: text, open: { pre: false, body: true, cons: false }, videosLoaded: false, videosLoading: false, videosError: false, videosNoIds: false })
    attachment.statusText = '已完成'
    if (attachmentMessage.value) attachmentMessage.value.attachment.statusText = attachment.statusText
    clearAttachment()
    scrollBottom()
  } catch (e) {
    // 详细打印 422 错误信息，便于定位后端验证失败原因
    console.error('[solveAttachment] 请求失败:', {
      status: e?.status,
      code: e?.code,
      message: e?.message,
      details: e?.details,
      attachmentId: attachment.id,
      textLength: text?.length,
      payload: JSON.stringify(payload),
    })
    attachment.statusText = '解答失败'
    if (attachmentMessage.value) {
      attachmentMessage.value.attachment.statusText = attachment.statusText
      attachmentMessage.value.attachment.errorText = (e && e.message) || '解答失败，请重试'
    }
    uni.showToast({ title: (e && e.message) || '题目解答失败', icon: 'none' })
  } finally { attachmentBusy.value = false }
}

async function retryAttachmentUpload(msg) {
  if (!msg || !msg.attachment || attachmentBusy.value) return
  attachmentMessage.value = msg
  Object.assign(attachment, msg.attachment)
  await sendAttachment()
}

async function sendAttachment() {
  if (!attachment.filePath || attachmentBusy.value) return
  if (!store.auth.user) { uni.showToast({ title: '登录后才能上传题目图片', icon: 'none' }); return }
  attachmentBusy.value = true
  attachment.statusText = '上传中'
  try {
    const data = await uploadAttachment(attachment.filePath, { file: attachment.file, conversationId: store.currentConversationId || null })
    attachment.mediaType = data.media_type || attachment.mediaType
    attachment.id = data.id
    if (attachmentMessage.value) {
      Object.assign(attachmentMessage.value.attachment, { id: data.id, statusText: '识别中' })
    }
    if (data.conversation_id) {
      store.currentConversationId = data.conversation_id
      uni.setStorageSync('last_conversation_id', data.conversation_id)
    }
    attachment.statusText = '识别中'
    await recognizeAttachment({ fromUpload: true })
  } catch (e) {
    attachment.statusText = '上传失败'
    if (attachmentMessage.value) {
      attachmentMessage.value.attachment.statusText = attachment.statusText
      attachmentMessage.value.attachment.errorText = `${(e && e.message) || '附件上传失败，请重试'}${e && e.code ? `（${e.code}）` : ''}`
    }
    uni.showToast({ title: `${(e && e.message) || '附件上传失败，请重试'}${e && e.code ? `（${e.code}）` : ''}`, icon: 'none' })
    attachmentBusy.value = false
  }
}

function send() {
  if (attachment.filePath && !attachment.id) { sendAttachment(); return }
  const q = question.value.trim()
  if (!q || loading.value || attachmentBusy.value || recordStarting.value || recordState.value !== 'idle') return
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

/* 自定义导航栏样式 */
.topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20rpx 32rpx; 
  background: #f5f6f8;
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

.topbar-title {
  font-size: 32rpx;
  font-weight: 600;
  color: #333;
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
  align-items: flex-start;
  gap: 14rpx;
  width: 100%;
  box-sizing: border-box;
}
.msg-user { justify-content: flex-end; }
.msg-ai { justify-content: flex-start; }
.msg-content { min-width: 0; max-width: calc(100% - 84rpx); }
.message-avatar { flex: 0 0 64rpx; width: 64rpx; height: 64rpx; border-radius: 50%; background: #e7eef7; object-fit: cover; }
.avatar-fallback { border: 8rpx solid #d9e4f2; box-sizing: border-box; }
.assistant-name { margin: 2rpx 0 8rpx 4rpx; color: #5b6b7f; font-size: 22rpx; }

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
.answer-summary { padding-bottom: 12rpx; border-bottom: 1rpx solid #eef2f6; }
.summary-label { display: block; margin-bottom: 8rpx; color: #718096; font-size: 22rpx; font-weight: 600; }
.final-answer { margin-top: 18rpx; padding: 18rpx; background: #edf8f2; border-left: 6rpx solid #2f9e68; border-radius: 8rpx; }
.final-label, .final-text { display: block; }
.final-label { color: #197247; font-size: 24rpx; font-weight: 700; }
.final-text { margin-top: 6rpx; color: #145c3a; font-size: 30rpx; font-weight: 700; line-height: 1.5; white-space: pre-wrap; word-break: break-word; }
.section-count { flex: 1; margin: 0 10rpx; color: #8793a2; font-size: 22rpx; text-align: right; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.question-card { width: min(620rpx, 100%); padding: 18rpx; background: #f7f9fc; border: 1rpx solid #dce6f0; border-radius: 14rpx; box-sizing: border-box; }
.question-card-head { display: flex; justify-content: space-between; gap: 12rpx; color: #2f4358; font-size: 26rpx; font-weight: 700; }
.question-status { color: #66809a; font-size: 22rpx; font-weight: 400; }
.ocr-warning { display: block; margin-top: 10rpx; padding: 10rpx 12rpx; color: #9a6412; background: #fff7e6; border-radius: 6rpx; font-size: 22rpx; line-height: 1.45; }
.question-image { display: block; width: 100%; max-height: 520rpx; margin-top: 14rpx; border-radius: 8rpx; background: #e9eef5; }
.question-file { margin-top: 8rpx; color: #8592a1; font-size: 21rpx; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.question-label { display: block; margin-top: 16rpx; color: #52657a; font-size: 23rpx; font-weight: 600; }
.question-text { width: 100%; min-height: 110rpx; margin-top: 8rpx; padding: 14rpx; box-sizing: border-box; background: #fff; border: 1rpx solid #d7e0ea; border-radius: 8rpx; color: #263746; font-size: 26rpx; line-height: 1.55; }
.question-actions { display: flex; gap: 10rpx; margin-top: 10rpx; }
.question-actions button { flex: 1; min-width: 0; margin: 0; padding: 0 10rpx; color: #2f6fb3; background: #e6f0fb; border: 0; border-radius: 8rpx; font-size: 23rpx; line-height: 58rpx; }
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

.attachment-draft {
  display: flex;
  align-items: center;
  gap: 16rpx;
  padding: 12rpx 24rpx;
  background: #f5f6f8;
  border-top: 1rpx solid #eee;
}
.attachment-thumb {
  flex: 0 0 88rpx;
  width: 88rpx;
  height: 88rpx;
  border-radius: 8rpx;
  background: #f2f3f5;
}
.attachment-draft-meta {
  min-width: 0;
  flex: 1;
}
.attachment-name, .attachment-size {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.attachment-name { font-size: 26rpx; color: #333; }
.attachment-size { margin-top: 6rpx; font-size: 22rpx; color: #777; }
.attachment-remove, .plus-btn {
  flex: 0 0 64rpx;
  width: 64rpx;
  height: 64rpx;
  padding: 0;
  border: none;
  border-radius: 50%;
  line-height: 64rpx;
  text-align: center;
}
.attachment-remove { color: #c53030; background: #fff5f5; font-size: 36rpx; }
.attachment-text-editor { padding: 12rpx 24rpx; background: #f5f6f8; }
.attachment-text-editor textarea { width: 100%; min-height: 120rpx; box-sizing: border-box; padding: 16rpx; background: #f7f8fa; border-radius: 8rpx; font-size: 26rpx; }
.attachment-actions { display: flex; gap: 12rpx; margin-top: 10rpx; }
.attachment-actions button { flex: 1; margin: 0; min-width: 0; font-size: 24rpx; line-height: 58rpx; color: #2b6cb0; background: #e8f0fb; border: none; border-radius: 8rpx; }
.attachment-menu {
  display: flex;
  gap: 16rpx;
  padding: 16rpx 24rpx 12rpx;
  background: #f5f6f8;
}
.attachment-menu-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8rpx;
  padding: 16rpx 8rpx 12rpx;
  background: #ffffff;
  border-radius: 12rpx;
  box-shadow: 0 1rpx 8rpx rgba(0, 0, 0, 0.05);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.attachment-menu-item:active {
  transform: scale(0.96);
  box-shadow: 0 1rpx 4rpx rgba(0, 0, 0, 0.08);
}
.attachment-menu-icon {
  width: 64rpx;
  height: 64rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f5f7fa;
  border-radius: 50%;
}
.ami-icon {
  font-size: 32rpx;
  line-height: 1;
}
.ami-label {
  font-size: 22rpx;
  color: #555;
  white-space: nowrap;
}
.plus-btn { margin-right: 12rpx; color: #2b6cb0; background: #e8f0fb; font-size: 40rpx; }
.confidence, .candidate-list { font-size: 22rpx; color: #666; }
.candidate-list { padding: 8rpx 0; }
.candidate-label, .candidate-item { display: block; }
.candidate-label { color: #555; font-weight: 600; }
.candidate-item { color: #777; margin-top: 4rpx; }
.candidate-button { display: block; width: 100%; margin: 6rpx 0 0; padding: 0 12rpx; text-align: left; background: #f5f8fc; border: 1rpx solid #d9e4f0; border-radius: 8rpx; line-height: 52rpx; font-size: 23rpx; }
.solution-list { display: flex; flex-direction: column; gap: 14rpx; }
.solution-step { padding: 16rpx; background: #f7f9fc; border-left: 6rpx solid #2b6cb0; border-radius: 6rpx; }
.solution-step-head { display: flex; align-items: center; gap: 12rpx; margin-bottom: 8rpx; }
.solution-step-no { width: 36rpx; height: 36rpx; flex: 0 0 36rpx; border-radius: 50%; text-align: center; line-height: 36rpx; background: #2b6cb0; color: #fff; font-size: 22rpx; font-weight: 700; }
.solution-step-title { font-size: 27rpx; line-height: 1.45; font-weight: 700; color: #243b53; }
.solution-step-content { display: block; font-size: 28rpx; line-height: 1.85; color: #263238; white-space: pre-wrap; word-break: break-word; }
.question-preview { display: block; width: 100%; margin: 8rpx 0; padding: 0 16rpx; color: #2867a8; background: #e8f0fb; border: 1rpx solid #c9d9ec; border-radius: 8rpx; font-size: 24rpx; line-height: 58rpx; text-align: center; }
.question-image { max-width: 100%; max-height: 560rpx; object-fit: contain; cursor: zoom-in; }
.question-error { display: block; margin-top: 8rpx; color: #b42318; font-size: 23rpx; line-height: 1.45; }
.question-retry { margin: 8rpx 0 0; padding: 0 12rpx; color: #9a3412; background: #fff7ed; border: 1rpx solid #fed7aa; border-radius: 6rpx; font-size: 22rpx; line-height: 48rpx; }

.composer {
  background: #f5f6f8;
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
  background: #f5f6f8;
}
.input {
  flex: 1;
  min-width: 0;
  height: 72rpx;
  max-height: 240rpx;
  margin-right: 12rpx;
  background: #ffffff;
  border-radius: 20rpx;
  padding: 18rpx 28rpx;
  font-size: 28rpx;
  box-sizing: border-box;
  line-height: 1.5;
  box-shadow: 0 2rpx 12rpx rgba(0, 0, 0, 0.08);
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