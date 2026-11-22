// 语音输入：App 用原生录音，H5 用 MediaRecorder，识别后回调文字。
// 只负责“录音 → 转文字”，不负责把文字发出去，页面可以决定放入输入框还是直接发送。

import { onUnmounted, ref } from 'vue'
import { transcribeAudio } from './api.js'

const MAX_SECONDS = 30

export function useVoiceInput(onText) {
  const supported = ref(false)
  const state = ref('idle') // idle | recording | uploading | starting
  const seconds = ref(0)

  let timer = null
  let session = 0
  let pendingCancel = false
  let starting = false
  // 按住说话：用户已经松手。用于取消“权限弹窗还没结束”时的那次录音。
  let released = false

  function startTimer() {
    stopTimer()
    timer = setInterval(() => {
      seconds.value += 1
      if (seconds.value >= MAX_SECONDS) {
        stopTimer()
        if (state.value === 'recording') stopRecording()
      }
    }, 1000)
  }

  function stopTimer() {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }

  function reset() {
    stopTimer()
    pendingCancel = false
    starting = false
    released = false
    state.value = 'idle'
    seconds.value = 0
  }

  function toast(message) {
    uni.showToast({ title: message, icon: 'none' })
  }

  function uploadRecording(filePath, options = {}) {
    const current = session
    state.value = 'uploading'
    transcribeAudio(filePath, options)
      .then((data) => {
        if (current !== session) return
        const text = data && data.text ? String(data.text).trim() : ''
        if (!text) {
          toast('未识别到有效语音，请重试')
          return
        }
        onText(text)
      })
      .catch((e) => {
        if (current !== session) return
        toast((e && e.message) || '语音识别失败，请重试')
      })
      .finally(() => {
        if (current === session) reset()
      })
  }

  // #ifdef APP-PLUS
  supported.value = true
  let recorder = null

  function recordErrorMessage(err) {
    const msg = (err && err.errMsg) || ''
    if (/auth|permission|denied|deny|权限|授权/i.test(msg)) {
      return '没有麦克风权限，请在系统设置中允许后重试'
    }
    if (/cancel/i.test(msg)) return '录音已取消'
    if (/not support|unsupport|device/i.test(msg)) return '当前设备不支持录音'
    return '录音失败，请重试'
  }

  function showPermissionModal(deniedAlways) {
    uni.showModal({
      title: '需要麦克风权限',
      content: deniedAlways
        ? '麦克风权限已被拒绝，请到系统设置中手动开启后重试。'
        : '请允许使用麦克风后重试。',
      showCancel: false,
      confirmText: '知道了',
    })
  }

  function requestPermission() {
    return new Promise((resolve) => {
      try {
        if (typeof plus !== 'undefined' && plus.android && plus.android.requestPermissions) {
          const permission = 'android.permission.RECORD_AUDIO'
          if (plus.android.hasPermission && plus.android.hasPermission(permission)) {
            resolve(true)
            return
          }
          plus.android.requestPermissions(
            [permission],
            (e) => {
              const granted = !!(e && e.granted && e.granted.length > 0)
              if (!granted) showPermissionModal(!!(e && e.deniedAlways && e.deniedAlways.length))
              resolve(granted)
            },
            () => {
              showPermissionModal(false)
              resolve(false)
            }
          )
          return
        }
      } catch (e) {}
      resolve(true)
    })
  }

  try {
    recorder = uni.getRecorderManager()
  } catch (e) {
    supported.value = false
  }
  // #endif

  // #ifdef H5
  supported.value = true
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

  function checkH5Support() {
    if (typeof window === 'undefined' || window.isSecureContext === false) {
      toast('麦克风需要 HTTPS 或 localhost 环境')
      return false
    }
    if (typeof MediaRecorder === 'undefined') {
      toast('当前浏览器不支持录音')
      return false
    }
    if (!navigator.mediaDevices || typeof navigator.mediaDevices.getUserMedia !== 'function') {
      toast('当前浏览器不支持麦克风采集')
      return false
    }
    if (typeof File === 'undefined') {
      toast('当前浏览器不支持录音上传')
      return false
    }
    return true
  }

  function pickMimeType() {
    if (typeof MediaRecorder === 'undefined' || typeof MediaRecorder.isTypeSupported !== 'function') {
      return ''
    }
    for (const type of H5_MIME_CANDIDATES) {
      if (MediaRecorder.isTypeSupported(type)) return type
    }
    return ''
  }

  function micErrorMessage(err) {
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

  function fileExtension(mimeType) {
    const type = (mimeType || '').toLowerCase()
    if (type.includes('mp4') || type.includes('aac')) return 'm4a'
    if (type.includes('wav')) return 'wav'
    if (type.includes('mpeg') || type.includes('mp3')) return 'mp3'
    if (type.includes('ogg')) return 'ogg'
    return 'webm'
  }

  function stopTracks(stream) {
    if (!stream) return
    stream.getTracks().forEach((track) => {
      try {
        track.stop()
      } catch (e) {}
    })
  }

  function releaseH5Resources() {
    const stream = h5Stream
    h5Stream = null
    h5Recorder = null
    h5Chunks = []
    h5MimeType = ''
    stopTracks(stream)
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

  async function finishH5Recording(current, chunks, stream, detectedType) {
    if (current !== session) {
      stopTracks(stream)
      reset()
      return
    }
    const recordedSeconds = seconds.value
    const copy = chunks.slice()
    stopTimer()
    h5Stream = null
    h5Recorder = null
    h5Chunks = []
    h5MimeType = ''
    stopTracks(stream)

    if (pendingCancel) {
      reset()
      return
    }
    if (!copy.length || recordedSeconds * 1000 < 500) {
      reset()
      toast('没有录到有效语音')
      return
    }

    let blob = new Blob(copy, { type: detectedType || 'audio/webm' })
    if (!blob.size) {
      reset()
      toast('没有录到有效语音')
      return
    }

    state.value = 'uploading'
    let mimeType = 'audio/wav'
    try {
      blob = await blobToWav(blob)
    } catch (err) {
      if (!isQwenFriendlyMime(detectedType)) {
        reset()
        toast('浏览器无法转换录音格式，请使用 Chrome/Edge 或 App')
        return
      }
      mimeType = (detectedType || blob.type || 'audio/mp4').split(';')[0].trim()
    }

    if (current !== session) return
    const file = new File([blob], `audio.${fileExtension(mimeType)}`, {
      type: mimeType || 'audio/wav',
    })
    uploadRecording(null, { file })
  }
  // #endif

  // #ifdef APP-PLUS
  if (recorder) {
    recorder.onStart(() => {
      if (pendingCancel) {
        try {
          recorder.stop()
        } catch (e) {}
        return
      }
      state.value = 'recording'
      seconds.value = 0
      startTimer()
    })

    recorder.onStop((res) => {
      const current = session
      const recordedSeconds = seconds.value
      stopTimer()
      if (pendingCancel) {
        reset()
        return
      }
      const filePath = res && res.tempFilePath
      const durationMs = (res && res.duration) || recordedSeconds * 1000
      if (!filePath || durationMs < 500) {
        reset()
        toast('没有录到有效语音')
        return
      }
      uploadRecording(filePath)
    })

    recorder.onError((err) => {
      reset()
      toast(recordErrorMessage(err))
    })
  }
  // #endif

  // #ifdef APP-PLUS
  async function startRecording() {
    if (!recorder) {
      toast('当前设备不支持录音')
      return
    }
    starting = true
    state.value = 'starting'
    try {
      const allowed = await requestPermission()
      if (!allowed) {
        reset()
        return
      }
      // 授权期间用户已经松手：取消这次录音，避免权限弹窗关闭后还在录。
      if (released) {
        reset()
        return
      }
      session += 1
      pendingCancel = false
      recorder.start({ format: 'mp3', sampleRate: 16000, duration: MAX_SECONDS * 1000 })
    } catch (e) {
      reset()
      toast('无法开始录音')
    } finally {
      starting = false
    }
  }

  function stopRecording() {
    try {
      recorder.stop()
    } catch (e) {
      reset()
    }
  }
  // #endif

  // #ifdef H5
  async function startRecording() {
    if (!checkH5Support()) return
    starting = true
    state.value = 'starting'
    let stream
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      })
    } catch (err) {
      toast(micErrorMessage(err))
      reset()
      return
    }

    if (pendingCancel || released) {
      stopTracks(stream)
      reset()
      return
    }

    const mimeType = pickMimeType()
    let mediaRecorder
    try {
      mediaRecorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream)
    } catch (err) {
      stopTracks(stream)
      reset()
      toast('当前浏览器不支持录音')
      return
    }

    session += 1
    const current = session
    pendingCancel = false
    seconds.value = 0
    h5Stream = stream
    h5Recorder = mediaRecorder
    const chunks = []
    h5Chunks = chunks
    h5MimeType = mimeType || mediaRecorder.mimeType || ''
    const detectedType = h5MimeType

    mediaRecorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) chunks.push(event.data)
    }
    mediaRecorder.onerror = () => {
      if (current !== session) return
      releaseH5Resources()
      reset()
      toast('录音失败，请重试')
    }
    mediaRecorder.onstop = () => {
      finishH5Recording(current, chunks, stream, detectedType).catch(() => {
        if (current === session) {
          reset()
          toast('录音处理失败，请重试')
        }
      })
    }

    const audioTrack = stream.getAudioTracks()[0]
    if (audioTrack) {
      audioTrack.onended = () => {
        if (state.value !== 'recording' || current !== session) return
        releaseH5Resources()
        reset()
        toast('录音已中断，请重试')
      }
    }

    try {
      mediaRecorder.start(1000)
    } catch (e) {
      stopTracks(stream)
      reset()
      toast('无法开始录音，请重试')
      return
    }

    state.value = 'recording'
    startTimer()
    starting = false
  }

  function stopRecording() {
    if (h5Recorder && h5Recorder.state !== 'inactive') {
      try {
        h5Recorder.stop()
      } catch (e) {
        reset()
      }
    } else {
      reset()
    }
  }
  // #endif

  // #ifndef APP-PLUS
  // #ifndef H5
  async function startRecording() {
    toast('当前平台不支持语音输入')
  }

  function stopRecording() {}
  // #endif
  // #endif

  async function start() {
    if (state.value !== 'idle' || starting) return
    released = false
    await startRecording()
  }

  /**
   * 松手：真正开始录音了就停止并识别；还在申请权限/启动中则直接放弃。
   */
  function finish() {
    if (state.value === 'recording') {
      stopRecording()
      return
    }
    if (state.value === 'starting') {
      released = true
      pendingCancel = true
      session += 1
      stopTimer()
      state.value = 'idle'
      seconds.value = 0
      starting = false
    }
  }

  async function toggle() {
    if (state.value === 'recording') {
      stopRecording()
      return
    }
    if (state.value !== 'idle' || starting) return
    released = false
    await startRecording()
  }

  function cancel() {
    pendingCancel = true
    session += 1
    if (state.value === 'recording') stopRecording()
    // 无论原生录音是否已经回调 onStop，先把 UI 恢复为可输入状态。
    // #ifdef H5
    releaseH5Resources()
    // #endif
    reset()
  }

  onUnmounted(() => {
    pendingCancel = true
    released = true
    session += 1
    stopTimer()
    // #ifdef H5
    releaseH5Resources()
    // #endif
  })

  return {
    supported,
    state,
    seconds,
    start,
    finish,
    toggle,
    cancel,
  }
}
