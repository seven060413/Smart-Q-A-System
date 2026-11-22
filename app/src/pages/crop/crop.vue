<template>
  <view class="crop-page" :style="{ paddingTop: statusBarHeight + 'px' }">
    <view class="crop-topbar">
      <text class="crop-action" @click="cancel">取消</text>
      <text class="crop-title">裁切图片</text>
      <text class="crop-action crop-action--primary" @click="confirm">完成</text>
    </view>

    <view class="crop-body">
      <view
        class="crop-stage"
        :style="{ width: stageW + 'px', height: stageH + 'px' }"
        @touchmove.stop.prevent
      >
        <image
          v-if="src"
          :src="src"
          class="crop-image"
          :style="imageStyle"
          mode="scaleToFill"
        />

        <svg
          v-if="ready"
          class="crop-lines"
          :width="stageW"
          :height="stageH"
          :viewBox="`0 0 ${stageW} ${stageH}`"
        >
          <polygon
            :points="polygonPoints"
            fill="rgba(43,108,176,0.18)"
            stroke="#ffffff"
            stroke-width="2"
          />
        </svg>

        <view
          v-for="(point, index) in points"
          :key="index"
          class="crop-handle"
          :style="{ left: point.x + 'px', top: point.y + 'px' }"
          @touchstart.stop.prevent="onHandleStart(index, $event)"
          @touchmove.stop.prevent="onHandleMove(index, $event)"
          @touchend.stop.prevent="onHandleEnd"
          @touchcancel.stop.prevent="onHandleEnd"
          @mousedown.stop.prevent="onHandleStart(index, $event)"
          @mousemove.stop.prevent="onHandleMove(index, $event)"
          @mouseup.stop.prevent="onHandleEnd"
        >
          <view class="crop-handle-dot" />
        </view>

        <view v-if="imageLoading" class="crop-loading">图片加载中…</view>
      </view>

      <text class="crop-hint">拖动四个角，框住试卷边缘</text>
    </view>

    <view class="crop-footer">
      <button class="crop-secondary" :disabled="warping" @click="useOriginal">使用原图</button>
      <button class="crop-primary" :disabled="warping || !ready" @click="confirm">
        {{ warping ? '正在校正…' : '完成裁切' }}
      </button>
    </view>

    <view v-if="warping" class="crop-warping">
      <view class="crop-warping-card">
        <text class="crop-warping-title">正在校正…</text>
        <text class="crop-warping-desc">透视校正可能需要几秒钟</text>
      </view>
    </view>

    <!-- renderjs 桥：变化时触发离屏 canvas 透视校正 -->
    <view
      class="crop-warp-bridge"
      :prop="warpPayload"
      :change:prop="warper.warp"
    ></view>
  </view>
</template>

<script setup>
import { computed, getCurrentInstance, nextTick, ref } from 'vue'
import { onLoad, onReady, onUnload } from '@dcloudio/uni-app'
import { cropSession, resetCropSession } from '../../crop-session.js'
import { cropBridge } from '../../crop-bridge.js'
import { cropTempName } from '../../temp-files.js'
import { quadArea } from '../../perspective.js'

const instance = getCurrentInstance()
const src = ref('')
const name = ref('')
const naturalW = ref(0)
const naturalH = ref(0)
const stageW = ref(320)
const stageH = ref(420)
const imgLeft = ref(0)
const imgTop = ref(0)
const imgW = ref(0)
const imgH = ref(0)
const points = ref([])
const imageLoading = ref(true)
const ready = ref(false)
const warping = ref(false)
const warpPayload = ref(null)
const statusBarHeight = ref(0)

let dragIndex = -1
let stageRect = null

const imageStyle = computed(() => ({
  left: `${imgLeft.value}px`,
  top: `${imgTop.value}px`,
  width: `${imgW.value}px`,
  height: `${imgH.value}px`,
}))

const polygonPoints = computed(() =>
  points.value.map((point) => `${point.x},${point.y}`).join(' ')
)

function toast(message) {
  uni.showToast({ title: message, icon: 'none' })
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value))
}

function measureStage() {
  if (!instance) return
  try {
    uni.createSelectorQuery()
      .in(instance.proxy)
      .select('.crop-stage')
      .boundingClientRect((rect) => {
        if (rect) stageRect = rect
      })
      .exec()
  } catch (e) {}
}

function computeStageSize() {
  try {
    const info = uni.getSystemInfoSync()
    statusBarHeight.value = info.statusBarHeight || 0
    const width = info.windowWidth || 375
    const height = info.windowHeight || 667
    stageW.value = Math.max(220, width - 24)
    // 顶部栏 + 底部按钮 + 提示 + 边距
    stageH.value = Math.max(260, height - statusBarHeight.value - 180)
  } catch (e) {
    stageW.value = 320
    stageH.value = 420
  }
}

function layoutImage() {
  if (!naturalW.value || !naturalH.value) return
  const scale = Math.min(stageW.value / naturalW.value, stageH.value / naturalH.value)
  imgW.value = naturalW.value * scale
  imgH.value = naturalH.value * scale
  imgLeft.value = (stageW.value - imgW.value) / 2
  imgTop.value = (stageH.value - imgH.value) / 2

  const insetX = imgW.value * 0.06
  const insetY = imgH.value * 0.06
  points.value = [
    { x: imgLeft.value + insetX, y: imgTop.value + insetY },
    { x: imgLeft.value + imgW.value - insetX, y: imgTop.value + insetY },
    { x: imgLeft.value + imgW.value - insetX, y: imgTop.value + imgH.value - insetY },
    { x: imgLeft.value + insetX, y: imgTop.value + imgH.value - insetY },
  ]
}

function loadImage() {
  if (!src.value) return
  imageLoading.value = true
  uni.getImageInfo({
    src: src.value,
    success: (info) => {
      naturalW.value = info.width || 0
      naturalH.value = info.height || 0
      if (!naturalW.value || !naturalH.value) {
        imageLoading.value = false
        toast('无法读取图片尺寸')
        return
      }
      layoutImage()
      imageLoading.value = false
      ready.value = true
      nextTick(() => measureStage())
    },
    fail: () => {
      imageLoading.value = false
      toast('图片加载失败，请返回重试')
    },
  })
}

function pointFromEvent(event) {
  const touch = (event.touches && event.touches[0]) || event
  if (!touch) return null
  const x = touch.clientX != null ? touch.clientX : touch.pageX
  const y = touch.clientY != null ? touch.clientY : touch.pageY
  if (typeof x !== 'number' || typeof y !== 'number') return null
  return { x, y }
}

function onHandleStart(index) {
  dragIndex = index
  if (!stageRect) measureStage()
}

function onHandleMove(index, event) {
  if (dragIndex !== index) return
  const point = pointFromEvent(event)
  if (!point || !stageRect) return

  const x = clamp(point.x - stageRect.left, imgLeft.value, imgLeft.value + imgW.value)
  const y = clamp(point.y - stageRect.top, imgTop.value, imgTop.value + imgH.value)
  const next = points.value.slice()
  next[index] = { x, y }
  points.value = next
}

function onHandleEnd() {
  dragIndex = -1
}

function stagePointsToImage(corners) {
  return corners.map((point) => [
    ((point.x - imgLeft.value) / imgW.value) * naturalW.value,
    ((point.y - imgTop.value) / imgH.value) * naturalH.value,
  ])
}

function orientation(a, b, c) {
  const value = (b[1] - a[1]) * (c[0] - b[0]) - (b[0] - a[0]) * (c[1] - b[1])
  if (Math.abs(value) < 1e-9) return 0
  return value > 0 ? 1 : 2
}

function onSegment(a, b, c) {
  return c[0] <= Math.max(a[0], b[0]) && c[0] >= Math.min(a[0], b[0]) &&
    c[1] <= Math.max(a[1], b[1]) && c[1] >= Math.min(a[1], b[1])
}

function segmentsIntersect(a, b, c, d) {
  const o1 = orientation(a, b, c)
  const o2 = orientation(a, b, d)
  const o3 = orientation(c, d, a)
  const o4 = orientation(c, d, b)
  if (o1 !== o2 && o3 !== o4) return true
  if (o1 === 0 && onSegment(a, b, c)) return true
  if (o2 === 0 && onSegment(a, b, d)) return true
  if (o3 === 0 && onSegment(c, d, a)) return true
  if (o4 === 0 && onSegment(c, d, b)) return true
  return false
}

function isSimpleQuad(corners) {
  return !segmentsIntersect(corners[0], corners[1], corners[2], corners[3]) &&
    !segmentsIntersect(corners[1], corners[2], corners[3], corners[0])
}

function readImageAsDataUrl() {
  return new Promise((resolve, reject) => {
    // #ifdef H5
    if (cropSession.file) {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result || ''))
      reader.onerror = () => reject(new Error('读取图片失败'))
      reader.readAsDataURL(cropSession.file)
      return
    }
    fetch(src.value)
      .then((response) => response.blob())
      .then((blob) => {
        const reader = new FileReader()
        reader.onload = () => resolve(String(reader.result || ''))
        reader.onerror = () => reject(new Error('读取图片失败'))
        reader.readAsDataURL(blob)
      })
      .catch(() => reject(new Error('读取图片失败')))
    // #endif

    // #ifdef APP-PLUS
    const mime = /\.png$/i.test(name.value || src.value) ? 'image/png' : 'image/jpeg'
    uni.getFileSystemManager().readFile({
      filePath: src.value,
      encoding: 'base64',
      success: (res) => resolve(`data:${mime};base64,${res.data}`),
      fail: (err) => reject(new Error((err && err.errMsg) || '读取图片失败')),
    })
    // #endif

    // #ifndef H5
    // #ifndef APP-PLUS
    resolve(src.value)
    // #endif
    // #endif
  })
}

function writeBase64WithPlus(base64, fileName) {
  return new Promise((resolve, reject) => {
    const arrayBuffer = uni.base64ToArrayBuffer(base64)
    plus.io.requestFileSystem(plus.io.PRIVATE_DOC, (fs) => {
      fs.root.getFile(fileName, { create: true }, (entry) => {
        entry.createWriter((writer) => {
          writer.onwrite = () => {
            resolve({
              filePath: entry.fullPath,
              size: arrayBuffer.byteLength,
            })
          }
          writer.onerror = () => reject(new Error('保存裁切图片失败'))
          writer.write(new Blob([arrayBuffer], { type: 'image/jpeg' }))
        }, () => reject(new Error('保存裁切图片失败')))
      }, () => reject(new Error('保存裁切图片失败')))
    }, () => reject(new Error('保存裁切图片失败')))
  })
}

async function saveCroppedImage(dataUrl) {
  // 统一使用 ikgr_crop_ 前缀，App 启动时会清理这批临时文件。
  const fileName = cropTempName()

  // #ifdef H5
  const blob = await (await fetch(dataUrl)).blob()
  const file = new File([blob], fileName, { type: 'image/jpeg' })
  return {
    filePath: URL.createObjectURL(blob),
    file,
    name: fileName,
    size: file.size,
  }
  // #endif

  // #ifdef APP-PLUS
  const base64 = String(dataUrl).split(',')[1] || ''
  const filePath = `_doc/${fileName}`
  try {
    const fs = uni.getFileSystemManager()
    if (fs && typeof fs.writeFile === 'function') {
      await new Promise((resolve, reject) => {
        fs.writeFile({
          filePath,
          data: base64,
          encoding: 'base64',
          success: resolve,
          fail: (err) => reject(new Error((err && err.errMsg) || '保存裁切图片失败')),
        })
      })
      return {
        filePath,
        file: null,
        name: fileName,
        size: Math.floor(base64.length * 0.75),
      }
    }
  } catch (e) {}

  const written = await writeBase64WithPlus(base64, fileName)
  return {
    filePath: written.filePath,
    file: null,
    name: fileName,
    size: written.size,
  }
  // #endif

  // #ifndef H5
  // #ifndef APP-PLUS
  throw new Error('当前平台暂不支持裁切')
  // #endif
  // #endif
}

async function confirm() {
  if (!ready.value || warping.value) return

  const corners = stagePointsToImage(points.value)
  if (quadArea(corners) < 1000) {
    toast('裁切区域太小，请重新框选')
    return
  }
  if (!isSimpleQuad(corners)) {
    toast('四个角不要交叉')
    return
  }

  warping.value = true
  try {
    const dataUrl = await readImageAsDataUrl()
    warpPayload.value = {
      src: dataUrl,
      corners,
      token: Date.now(),
    }
  } catch (e) {
    warping.value = false
    toast((e && e.message) || '读取图片失败')
  }
}

async function onWarped(payload) {
  if (!payload || !payload.dataUrl) {
    onWarpError(payload)
    return
  }
  try {
    const saved = await saveCroppedImage(payload.dataUrl)
    cropSession.result = {
      filePath: saved.filePath,
      file: saved.file || null,
      name: saved.name,
      size: saved.size,
      width: payload.width,
      height: payload.height,
    }
    uni.navigateBack()
  } catch (e) {
    warping.value = false
    toast((e && e.message) || '保存裁切图片失败')
  }
}

function onWarpError(payload) {
  warping.value = false
  toast((payload && payload.message) || '裁切失败，请重试')
}

function useOriginal() {
  cropSession.result = {
    filePath: cropSession.src,
    file: cropSession.file,
    name: cropSession.name,
    size: cropSession.size,
  }
  uni.navigateBack()
}

function cancel() {
  cropSession.result = { cancelled: true }
  uni.navigateBack()
}

// renderjs 通过 Options API methods 回调到这里
cropBridge.onWarped = onWarped
cropBridge.onWarpError = onWarpError
onUnload(() => {
  cropBridge.onWarped = null
  cropBridge.onWarpError = null
})

onLoad(() => {
  resetResultIfNeeded()
  if (!cropSession.src) {
    toast('没有可裁切的图片')
    setTimeout(() => uni.navigateBack(), 300)
    return
  }
  src.value = cropSession.src
  name.value = cropSession.name || '题目图片'
  computeStageSize()
  loadImage()
})

onReady(() => {
  measureStage()
})

function resetResultIfNeeded() {
  // 打开裁切页时清掉上一次的结果
  cropSession.result = null
}
</script>

<script>
import { cropBridge } from '../../crop-bridge.js'

export default {
  methods: {
    onWarpedBridge(payload) {
      if (cropBridge.onWarped) cropBridge.onWarped(payload)
    },
    onWarpErrorBridge(payload) {
      if (cropBridge.onWarpError) cropBridge.onWarpError(payload)
    },
  },
}
</script>

<script module="warper" lang="renderjs">
import { quadSize, warpRGBA } from '../../perspective.js'

export default {
  methods: {
    warp(payload, oldValue, ownerInstance) {
      if (!payload || !payload.src) return

      const image = new Image()
      image.onload = () => {
        try {
          const naturalW = image.naturalWidth || image.width
          const naturalH = image.naturalHeight || image.height
          if (!naturalW || !naturalH) throw new Error('图片尺寸无效')

          // 源图缩到 1600px 以内，降低手机端像素处理压力
          const srcScale = Math.min(1, 1600 / Math.max(naturalW, naturalH))
          const sourceW = Math.max(1, Math.round(naturalW * srcScale))
          const sourceH = Math.max(1, Math.round(naturalH * srcScale))

          const sourceCanvas = document.createElement('canvas')
          sourceCanvas.width = sourceW
          sourceCanvas.height = sourceH
          const sourceCtx = sourceCanvas.getContext('2d')
          sourceCtx.fillStyle = '#ffffff'
          sourceCtx.fillRect(0, 0, sourceW, sourceH)
          sourceCtx.drawImage(image, 0, 0, sourceW, sourceH)
          const sourceData = sourceCtx.getImageData(0, 0, sourceW, sourceH)

          const corners = payload.corners.map(([x, y]) => [x * srcScale, y * srcScale])
          const size = quadSize(corners)
          const outScale = Math.min(1, 1400 / Math.max(size.width, size.height))
          const outW = Math.max(1, Math.round(size.width * outScale))
          const outH = Math.max(1, Math.round(size.height * outScale))

          const pixels = warpRGBA(
            sourceData.data,
            sourceW,
            sourceH,
            corners,
            outW,
            outH
          )
          if (!pixels) throw new Error('裁切区域无效')

          const outputCanvas = document.createElement('canvas')
          outputCanvas.width = outW
          outputCanvas.height = outH
          const outputCtx = outputCanvas.getContext('2d')
          const outputData = outputCtx.createImageData(outW, outH)
          outputData.data.set(pixels)
          outputCtx.putImageData(outputData, 0, 0)

          ownerInstance.callMethod('onWarpedBridge', {
            dataUrl: outputCanvas.toDataURL('image/jpeg', 0.92),
            width: outW,
            height: outH,
          })
        } catch (error) {
          ownerInstance.callMethod('onWarpErrorBridge', {
            message: (error && error.message) || '裁切失败',
          })
        }
      }
      image.onerror = () => {
        ownerInstance.callMethod('onWarpErrorBridge', { message: '图片加载失败' })
      }
      image.src = payload.src
    },
  },
}
</script>

<style>
.crop-page {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #0f172a;
  color: #fff;
  overflow: hidden;
  box-sizing: border-box;
}

.crop-topbar {
  height: 88rpx;
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24rpx;
  box-sizing: border-box;
}
.crop-action {
  min-width: 96rpx;
  font-size: 30rpx;
  color: rgba(255, 255, 255, 0.78);
}
.crop-action--primary {
  text-align: right;
  color: #93c5fd;
  font-weight: 700;
}
.crop-title {
  font-size: 32rpx;
  font-weight: 700;
  color: #fff;
}

.crop-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 12rpx 0 0;
}

.crop-stage {
  position: relative;
  overflow: hidden;
  border-radius: 8rpx;
  background: #111827;
  touch-action: none;
}

.crop-image {
  position: absolute;
  display: block;
}

.crop-lines {
  position: absolute;
  top: 0;
  left: 0;
  pointer-events: none;
}

.crop-handle {
  position: absolute;
  width: 52rpx;
  height: 52rpx;
  margin-left: -26rpx;
  margin-top: -26rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 3;
}
.crop-handle-dot {
  width: 24rpx;
  height: 24rpx;
  border-radius: 50%;
  background: #fff;
  border: 4rpx solid #2b6cb0;
  box-shadow: 0 0 0 4rpx rgba(43, 108, 176, 0.28);
}

.crop-hint {
  margin-top: 18rpx;
  font-size: 24rpx;
  color: rgba(255, 255, 255, 0.62);
}

.crop-loading {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  left: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 26rpx;
  color: rgba(255, 255, 255, 0.7);
  background: rgba(15, 23, 42, 0.6);
}

.crop-footer {
  flex: 0 0 auto;
  display: flex;
  gap: 20rpx;
  padding: 20rpx 24rpx 36rpx;
}
.crop-footer button {
  flex: 1;
  margin: 0;
  border: none;
  border-radius: 16rpx;
  font-size: 30rpx;
  line-height: 88rpx;
}
.crop-secondary {
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
}
.crop-primary {
  background: #2b6cb0;
  color: #fff;
  font-weight: 700;
}
.crop-primary[disabled] {
  opacity: 0.6;
}

.crop-warping {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  left: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(15, 23, 42, 0.62);
}
.crop-warping-card {
  width: 420rpx;
  padding: 36rpx 28rpx;
  border-radius: 24rpx;
  background: rgba(17, 24, 39, 0.96);
  display: flex;
  flex-direction: column;
  align-items: center;
}
.crop-warping-title {
  font-size: 32rpx;
  font-weight: 700;
}
.crop-warping-desc {
  margin-top: 12rpx;
  font-size: 24rpx;
  color: rgba(255, 255, 255, 0.68);
}

.crop-warp-bridge {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
  pointer-events: none;
}
</style>
