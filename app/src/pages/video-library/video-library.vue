<template>
  <view class="page">
    <!-- 搜索 -->
    <view class="search-box">
      <text class="search-icon">🔍</text>
      <input
        v-model="keyword"
        class="search-input"
        type="text"
        placeholder="搜索视频标题、知识点、UP主"
        placeholder-class="search-placeholder"
        confirm-type="search"
        @input="onSearchInput"
        @confirm="onSearchConfirm"
      />
      <text v-if="keyword" class="search-clear" @click.stop="clearSearch">✕</text>
    </view>

    <!-- 教材册筛选 -->
    <scroll-view class="chips" scroll-x :show-scrollbar="false">
      <view
        v-for="chip in chips"
        :key="chip.key || 'all'"
        class="chip"
        :class="{ active: book === chip.key }"
        @click.stop="selectBook(chip.key)"
      >
        <text>{{ chip.label }}</text>
        <text v-if="chip.count" class="chip-count">{{ chip.count }}</text>
      </view>
    </scroll-view>

    <text class="summary">
      {{ keyword ? `找到 ${total} 个相关视频` : `共 ${total} 个视频` }}
    </text>

    <!-- 首次加载 -->
    <view v-if="loading && items.length === 0" class="skeleton-list">
      <view v-for="n in 6" :key="n" class="skeleton-card">
        <view class="skeleton-cover"></view>
        <view class="skeleton-meta">
          <view class="skeleton-line w80"></view>
          <view class="skeleton-line w50"></view>
          <view class="skeleton-line w30"></view>
        </view>
      </view>
    </view>

    <!-- 空/错误 -->
    <view v-else-if="items.length === 0" class="empty">
      <text class="empty-title">{{ error ? '视频库加载失败' : '没有找到相关视频' }}</text>
      <text class="empty-text">
        {{ error ? '请检查后端地址或网络后重试。' : '换个关键词，或切换教材册试试。' }}
      </text>
      <button class="retry" @click="reload">{{ error ? '重试' : '清空搜索' }}</button>
    </view>

    <!-- 列表 -->
    <view v-else class="groups">
      <view v-for="group in groups" :key="group.key" class="group">
        <view class="group-head">
          <text class="group-title">
            {{ group.book === '示例' ? group.chapter : `${group.book} · ${group.chapter}` }}
          </text>
          <text class="group-count">{{ group.count }} 个</text>
        </view>

        <view
          v-for="video in group.items"
          :key="video.video_id"
          class="video-card"
          @click.stop="openVideo(video)"
        >
          <view class="cover">
            <image
              v-if="video.cover_url && !failedCovers[video.video_id]"
              :src="video.cover_url"
              mode="aspectFill"
              class="cover-img"
              referrerpolicy="no-referrer"
              @error="onCoverError(video)"
            />
            <view v-else class="cover-fallback">B站</view>
            <view class="play">▶</view>
            <text v-if="video.duration_seconds" class="duration">{{ formatDuration(video.duration_seconds) }}</text>
          </view>

          <view class="meta">
            <text class="title">{{ video.title }}</text>
            <text class="author">{{ video.author || 'B 站' }}</text>
            <view class="points">
              <text
                v-for="point in video.knowledge_points.slice(0, 2)"
                :key="point"
                class="point"
              >{{ point }}</text>
              <text v-if="video.knowledge_points.length > 2" class="point more">
                +{{ video.knowledge_points.length - 2 }}
              </text>
            </view>
          </view>
        </view>
      </view>

      <view v-if="loadingMore" class="loading-more">加载中…</view>
      <view v-else-if="items.length >= total" class="loading-more">已经到底了</view>
    </view>
  </view>
</template>

<script setup>
import { computed, ref } from 'vue'
import { onLoad, onReachBottom, onUnload } from '@dcloudio/uni-app'
import { listVideoLibrary } from '../../api.js'
import { formatDuration } from '../../video.js'

const PAGE_SIZE = 20
const BOOKS = [
  { key: '七上', label: '七上' },
  { key: '七下', label: '七下' },
  { key: '八上', label: '八上' },
  { key: '八下', label: '八下' },
  { key: '九上', label: '九上' },
  { key: '九下', label: '九下' },
]

const keyword = ref('')
const book = ref('')
const items = ref([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const loadingMore = ref(false)
const error = ref(false)
const facets = ref({})
const failedCovers = ref({})

let searchTimer = null
let requestSeq = 0

const chips = computed(() => {
  const counts = {}
  for (const item of facets.value.books || []) counts[item.key] = item.count
  return [
    { key: '', label: '全部', count: facets.value.total_all || 0 },
    ...BOOKS.map((item) => ({ ...item, count: counts[item.key] || 0 })),
  ]
})

const chapterCounts = computed(() => {
  const map = {}
  for (const item of facets.value.chapters || []) {
    map[`${item.book}|${item.chapter}`] = item.count
  }
  return map
})

const groups = computed(() => {
  const map = new Map()
  for (const video of items.value) {
    const key = `${video.book}|${video.chapter}`
    if (!map.has(key)) {
      map.set(key, {
        key,
        book: video.book,
        chapter: video.chapter,
        count: chapterCounts.value[key] || 0,
        items: [],
      })
    }
    map.get(key).items.push(video)
  }
  return Array.from(map.values())
})

function onCoverError(video) {
  failedCovers.value = { ...failedCovers.value, [video.video_id]: true }
}

async function load(reset = false) {
  const seq = ++requestSeq
  if (reset) {
    page.value = 1
    items.value = []
    total.value = 0
    error.value = false
    loading.value = true
    loadingMore.value = false
  } else {
    loadingMore.value = true
  }

  try {
    const data = await listVideoLibrary({
      q: keyword.value.trim(),
      book: book.value,
      page: page.value,
      pageSize: PAGE_SIZE,
    })
    if (seq !== requestSeq) return
    const nextItems = (data.items || []).map((video) => ({
      ...video,
      knowledge_points: Array.isArray(video.knowledge_points) ? video.knowledge_points : [],
    }))
    items.value = reset ? nextItems : items.value.concat(nextItems)
    total.value = data.total || 0
    facets.value = data.facets || {}
    error.value = false
  } catch (e) {
    if (seq !== requestSeq) return
    error.value = true
    if (reset) {
      items.value = []
      total.value = 0
    } else {
      uni.showToast({ title: (e && e.message) || '加载失败', icon: 'none' })
    }
  } finally {
    if (seq === requestSeq) {
      loading.value = false
      loadingMore.value = false
    }
  }
}

function reload() {
  if (error.value) {
    load(true)
    return
  }
  keyword.value = ''
  book.value = ''
  load(true)
}

function onSearchInput() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => load(true), 300)
}

function onSearchConfirm() {
  if (searchTimer) clearTimeout(searchTimer)
  load(true)
}

function clearSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  keyword.value = ''
  load(true)
}

function selectBook(key) {
  if (book.value === key) return
  book.value = key
  load(true)
}

function openVideo(video) {
  const bvid = encodeURIComponent(video.bvid || '')
  const pageNo = Number(video.page || 1)
  const aid = encodeURIComponent(video.aid || '')
  const cid = encodeURIComponent(video.cid || '')
  const title = encodeURIComponent(video.title || '视频讲解')
  uni.navigateTo({
    url: `/pages/video/video?bvid=${bvid}&page=${pageNo}&aid=${aid}&cid=${cid}&title=${title}`,
  })
}

onLoad(() => {
  load(true)
})

onReachBottom(() => {
  if (loading.value || loadingMore.value) return
  if (items.value.length >= total.value) return
  page.value += 1
  load(false)
})

onUnload(() => {
  if (searchTimer) clearTimeout(searchTimer)
})
</script>

<style>
.page {
  min-height: 100vh;
  padding: 24rpx 24rpx 40rpx;
  box-sizing: border-box;
  background: #f5f6f8;
}
/* #ifdef H5 */
.page {
  min-height: calc(100vh - var(--window-top, 0px) - var(--window-bottom, 0px));
}
/* #endif */

.search-box {
  display: flex;
  align-items: center;
  gap: 12rpx;
  padding: 16rpx 24rpx;
  border-radius: 999rpx;
  background: #fff;
  box-shadow: 0 4rpx 16rpx rgba(0, 0, 0, 0.04);
}
.search-icon {
  font-size: 26rpx;
  opacity: 0.55;
}
.search-input {
  flex: 1;
  min-width: 0;
  font-size: 28rpx;
  color: #222;
}
.search-placeholder {
  color: #b0b5bd;
}
.search-clear {
  width: 44rpx;
  height: 44rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  color: #999;
  background: #f0f2f5;
  font-size: 24rpx;
}

.chips {
  margin: 20rpx 0 4rpx;
  white-space: nowrap;
}
.chip {
  display: inline-flex;
  align-items: center;
  padding: 12rpx 24rpx;
  margin-right: 16rpx;
  border-radius: 999rpx;
  border: 1rpx solid #e5e9f0;
  background: #fff;
  color: #666;
  font-size: 24rpx;
}
.chip.active {
  background: #2b6cb0;
  border-color: #2b6cb0;
  color: #fff;
}
.chip-count {
  margin-left: 8rpx;
  font-size: 20rpx;
  opacity: 0.7;
}

.summary {
  display: block;
  margin: 14rpx 4rpx 0;
  font-size: 22rpx;
  color: #999;
}

.group {
  margin-top: 24rpx;
}
.group-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6rpx 4rpx 14rpx;
}
.group-title {
  font-size: 24rpx;
  font-weight: 600;
  color: #2b6cb0;
}
.group-count {
  font-size: 20rpx;
  color: #999;
}

.video-card {
  display: flex;
  gap: 16rpx;
  padding: 16rpx;
  margin-bottom: 16rpx;
  border-radius: 20rpx;
  background: #fff;
  box-shadow: 0 4rpx 16rpx rgba(0, 0, 0, 0.04);
}
.cover {
  position: relative;
  width: 200rpx;
  height: 120rpx;
  flex: 0 0 200rpx;
  border-radius: 12rpx;
  overflow: hidden;
  background: #1f2a37;
}
.cover-img {
  width: 100%;
  height: 100%;
  display: block;
}
.cover-fallback {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 22rpx;
  background: #263445;
}
.play {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 44rpx;
  height: 44rpx;
  margin: -22rpx 0 0 -22rpx;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 20rpx;
  background: rgba(0, 0, 0, 0.45);
}
.duration {
  position: absolute;
  right: 8rpx;
  bottom: 8rpx;
  padding: 2rpx 8rpx;
  border-radius: 6rpx;
  color: #fff;
  font-size: 18rpx;
  background: rgba(0, 0, 0, 0.55);
}

.meta {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.title {
  font-size: 28rpx;
  line-height: 1.35;
  color: #222;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.author {
  margin-top: 6rpx;
  font-size: 22rpx;
  color: #999;
}
.points {
  display: flex;
  flex-wrap: wrap;
  gap: 8rpx;
  margin-top: 8rpx;
}
.point {
  padding: 2rpx 8rpx;
  border-radius: 6rpx;
  background: #eaf2fb;
  color: #2b6cb0;
  font-size: 20rpx;
}
.point.more {
  background: #f0f2f5;
  color: #999;
}

.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding-top: 160rpx;
}
.empty-title {
  font-size: 30rpx;
  font-weight: 600;
  color: #444;
}
.empty-text {
  margin-top: 12rpx;
  font-size: 24rpx;
  color: #999;
  text-align: center;
}
.retry {
  margin-top: 32rpx;
  padding: 0 40rpx;
  height: 72rpx;
  line-height: 72rpx;
  border-radius: 999rpx;
  background: #2b6cb0;
  color: #fff;
  font-size: 26rpx;
}

.skeleton-card {
  display: flex;
  gap: 16rpx;
  padding: 16rpx;
  margin-bottom: 16rpx;
  border-radius: 20rpx;
  background: #fff;
}
.skeleton-cover {
  width: 200rpx;
  height: 120rpx;
  flex: 0 0 200rpx;
  border-radius: 12rpx;
  background: #eceff3;
}
.skeleton-meta {
  flex: 1;
  padding-top: 6rpx;
}
.skeleton-line {
  height: 24rpx;
  margin-bottom: 14rpx;
  border-radius: 8rpx;
  background: #eceff3;
}
.skeleton-line.w80 { width: 80%; }
.skeleton-line.w50 { width: 50%; }
.skeleton-line.w30 { width: 30%; }

.loading-more {
  padding: 24rpx 0 12rpx;
  text-align: center;
  font-size: 22rpx;
  color: #999;
}
</style>