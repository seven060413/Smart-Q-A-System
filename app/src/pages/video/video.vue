<template>
  <view class="page">
    <!-- H5：独立页也保留 iframe，作为从其他入口进入时的兜底 -->
    <!-- #ifdef H5 -->
    <view class="h5-wrap">
      <iframe
        v-if="activeEmbedUrl"
        :src="activeEmbedUrl"
        class="iframe"
        allowfullscreen="true"
        allow="autoplay; fullscreen; picture-in-picture"
        referrerpolicy="no-referrer-when-downgrade"
        frameborder="0"
      ></iframe>
      <view v-else class="invalid">视频地址无效</view>
      <view class="actions">
        <button v-if="mobileUrl" class="open-btn" @click="toggleMobile">
          {{ mobileMode ? '官方播放器' : '移动版播放器' }}
        </button>
        <button v-if="watchUrl" class="open-btn secondary" @click="openExternal">在 B 站打开</button>
      </view>
    </view>
    <!-- #endif -->

    <!-- App：web-view 是原生全屏容器，由原生返回键回到问答页 -->
    <!-- #ifdef APP-PLUS -->
    <web-view v-if="activeEmbedUrl" :src="activeEmbedUrl" />
    <view v-else class="invalid">视频地址无效</view>
    <!-- #endif -->
  </view>
</template>

<script setup>
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import {
  buildBilibiliEmbedUrl,
  buildBilibiliMobileUrl,
  buildBilibiliWatchUrl,
} from '../../video.js'

const bvid = ref('')
const page = ref(1)
const aid = ref('')
const cid = ref('')
const title = ref('视频讲解')
const mobileMode = ref(false)

const embedUrl = computed(() =>
  bvid.value ? buildBilibiliEmbedUrl(bvid.value, page.value, aid.value, cid.value) : ''
)
const mobileUrl = computed(() =>
  bvid.value ? buildBilibiliMobileUrl(bvid.value, page.value) : ''
)
const activeEmbedUrl = computed(() =>
  mobileMode.value ? mobileUrl.value : embedUrl.value
)
const watchUrl = computed(() =>
  bvid.value ? buildBilibiliWatchUrl(bvid.value, page.value) : ''
)

function toggleMobile() {
  mobileMode.value = !mobileMode.value
}

function safeDecode(value) {
  try {
    return decodeURIComponent(value)
  } catch (e) {
    return value
  }
}

onLoad((options = {}) => {
  bvid.value = options.bvid || ''
  page.value = Number(options.page || 1) || 1
  aid.value = options.aid || ''
  cid.value = options.cid || ''
  title.value = options.title ? safeDecode(String(options.title)) : '视频讲解'
  uni.setNavigationBarTitle({ title: title.value })
})

function openExternal() {
  if (!watchUrl.value) return
  // #ifdef H5
  window.open(watchUrl.value, '_blank')
  // #endif
  // #ifdef APP-PLUS
  plus.runtime.openURL(watchUrl.value)
  // #endif
}
</script>

<style>
.page {
  min-height: 100vh;
  background: #000;
}

/* #ifdef H5 */
.page {
  background: #0f1115;
}
.h5-wrap {
  padding: 24rpx;
}
.iframe {
  width: 100%;
  height: 420rpx;
  border: 0;
  border-radius: 12rpx;
  background: #000;
  display: block;
}
.actions {
  display: flex;
  gap: 16rpx;
  margin-top: 24rpx;
}
.open-btn {
  flex: 1;
  margin-top: 0;
  background: #2b6cb0;
  color: #fff;
  font-size: 28rpx;
  border-radius: 999rpx;
  border: none;
}
.open-btn.secondary {
  background: #334155;
}
.open-btn::after {
  border: none;
}
/* #endif */

.invalid {
  color: #fff;
  font-size: 28rpx;
  text-align: center;
  padding-top: 120rpx;
}
</style>
