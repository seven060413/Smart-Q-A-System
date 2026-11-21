<template>
  <view class="page theme-root" :class="{ 'is-dark': isDark }" :style="themeVars">
    <ThemeBackground />

    <view v-if="!loggedIn" class="state">
      <text class="state-title">登录后查看错题集</text>
      <text class="state-sub">答错的题会按题目保存作答时的题干、答案和解析，题库更新也不影响。</text>
      <button class="primary" @click="goAuth">去登录</button>
    </view>

    <block v-else>
      <!-- 概览：先回答“我哪里错得多、复习到哪了”，再进入筛选和列表 -->
      <view v-if="!loading && !error && summary.total > 0" class="overview card">
        <view class="overview-stats">
          <view class="overview-stat">
            <text class="overview-value">{{ summary.total }}</text>
            <text class="overview-label">当前错题</text>
          </view>
          <view class="overview-stat">
            <text class="overview-value">{{ summary.node_count }}</text>
            <text class="overview-label">涉及知识点</text>
          </view>
          <view class="overview-stat">
            <text class="overview-value">{{ oldestDays }}</text>
            <text class="overview-label">最久未复习</text>
          </view>
        </view>

        <view class="progress-head">
          <text class="progress-label">复习进度</text>
          <text class="progress-value">{{ markCounts.mastered }}/{{ markTotal }} 已掌握</text>
        </view>
        <view class="progress-track">
          <view class="progress-fill" :style="{ width: progressPercent + '%' }"></view>
        </view>

        <view class="overview-cta" @click="openAllGraph">
          <wd-icon name="branch" size="32rpx" />
          <text class="overview-cta-text">查看错题知识图谱</text>
          <text class="overview-cta-meta">{{ summary.node_count }} 个知识点 ›</text>
        </view>
      </view>

      <!-- 筛选：状态 / 时间 / 年级；章节筛选下放到热度卡片 -->
      <view class="toolbar">
        <scroll-view scroll-x class="chip-scroll">
          <view class="chips">
            <view
              v-for="option in statusOptions"
              :key="option.key"
              class="chip"
              :class="{ active: status === option.key }"
              @click="setStatus(option.key)"
            >{{ option.label }}</view>
          </view>
        </scroll-view>
        <scroll-view scroll-x class="chip-scroll second">
          <view class="chips">
            <view
              v-for="option in dayOptions"
              :key="option.key"
              class="chip small"
              :class="{ active: days === option.key }"
              @click="setDays(option.key)"
            >{{ option.label }}</view>
          </view>
        </scroll-view>
        <scroll-view v-if="gradeOptions.length > 1" scroll-x class="chip-scroll second">
          <view class="chips">
            <view
              class="chip small"
              :class="{ active: gradeFilter === null }"
              @click="setGrade(null)"
            >全部年级</view>
            <view
              v-for="option in gradeOptions"
              :key="option.grade"
              class="chip small"
              :class="{ active: gradeFilter === option.grade }"
              @click="setGrade(option.grade)"
            >{{ gradeLabel(option.grade) }} {{ option.count }}</view>
          </view>
        </scroll-view>
        <view v-if="nodeFilter" class="filter-note">
          <text>仅看知识点：{{ nodeFilter }}</text>
          <text class="clear" @click="clearNodeFilter">清除</text>
        </view>
        <text v-if="!loading" class="total-note">当前筛选 {{ total }} 题</text>
      </view>

      <view v-if="loading" class="state">
        <text class="state-sub">正在加载错题…</text>
      </view>

      <view v-else-if="error" class="state">
        <text class="state-sub">{{ error }}</text>
        <button class="ghost" @click="load()">重试</button>
      </view>

      <view v-else-if="!items.length" class="state">
        <text class="state-title">还没有错题</text>
        <text class="state-sub">做一次诊断试试，答错的题会自动收集到这里。</text>
        <button class="primary" @click="goDiagnosis">去诊断</button>
      </view>

      <block v-else>
        <!-- 章节热度：条长 + 色深表达错题数量，点击即筛选 -->
        <view v-if="chapterOptions.length" class="card heat-card">
          <view class="card-head-row">
            <text class="section-title">章节错题热度</text>
            <text class="section-hint">点击筛选</text>
          </view>
          <view
            v-for="item in chapterHeat"
            :key="item.chapter"
            class="heat-row"
            :class="{ active: chapterFilter === item.chapter }"
            @click="toggleChapter(item.chapter)"
          >
            <text class="heat-label">{{ item.label }}</text>
            <view class="heat-track">
              <view
                class="heat-fill"
                :style="{ width: item.width, opacity: item.opacity, background: heatColor }"
              ></view>
            </view>
            <text class="heat-count" :style="{ color: heatColor }">{{ item.count }}</text>
          </view>
          <text
            v-if="hasMoreChapters"
            class="more-link"
            @click="showAllChapters = !showAllChapters"
          >{{ showAllChapters ? '收起章节' : '显示全部章节' }}</text>
        </view>

        <!-- 知识点分布：色块大小/色深表达错题量，点击筛选该知识点 -->
        <view v-if="nodeStats.length" class="card">
          <view class="card-head-row">
            <text class="section-title">知识点分布</text>
            <text class="section-hint">色深 = 错题多</text>
          </view>
          <view class="node-grid">
            <view
              v-for="node in nodeBlocks"
              :key="node.node_key"
              class="node-block"
              :class="[nodeCountClass(node), { active: nodeFilter === node.node_key }]"
              :style="nodeStyle(node)"
              @click="toggleNodeFilter(node.node_key)"
            >
              <text class="node-block-name">{{ node.node_name }}</text>
              <text class="node-block-count">{{ node.wrong_count }} 题</text>
            </view>
          </view>
          <text
            v-if="hasMoreNodes"
            class="more-link"
            @click="showAllNodes = !showAllNodes"
          >{{ showAllNodes ? '收起知识点' : `显示全部 ${nodeStats.length} 个知识点` }}</text>
        </view>

        <!-- 错题列表：默认收起答案/解析，减少扫读噪音 -->
        <view class="list">
          <view
            v-for="item in items"
            :key="itemKey(item)"
            class="card question-card"
            :class="item.mark_status"
          >
            <view class="card-head" @click="toggleItem(item)">
              <view class="card-head-main">
                <text class="card-topic">{{ item.node_name }}</text>
                <text class="card-meta">
                  {{ gradeLabel(item.grade) }} · {{ item.chapter_label || item.chapter }} · 错 {{ item.wrong_count }} 次
                </text>
              </view>
              <text class="status-tag" :class="item.mark_status">{{ markLabel(item.mark_status) }}</text>
            </view>

            <MathText class="card-prompt" :text="item.prompt" />

            <!-- 配图是题干的一部分，收起时也保留，避免“如图”却看不到图 -->
            <image
              v-if="item.figure"
              :src="svgUri(item.figure)"
              class="card-figure"
              mode="widthFix"
            />

            <view v-if="isExpanded(item)" class="card-body">
              <view v-if="item.choices && item.choices.length" class="choices">
                <view v-for="choice in item.choices" :key="choice.key" class="choice">
                  <text class="choice-key">{{ choice.key }}</text>
                  <image
                    v-if="choice.figure && !choice.text"
                    :src="svgUri(choice.figure)"
                    class="choice-figure"
                    mode="widthFix"
                  />
                  <MathText v-else class="choice-text" :text="choice.text" inline />
                </view>
              </view>

              <view class="answer-box">
                <view class="answer-line">
                  <text class="answer-label">我的答案</text><MathText :text="item.student_answer || '未作答'" inline />
                </view>
                <view class="answer-line">
                  <text class="answer-label correct">正确答案</text><MathText :text="item.correct_answer" inline />
                </view>
                <MathText v-if="item.explanation" class="explanation" :text="'解析：' + item.explanation" />
              </view>

              <text class="foot-meta">
                错 {{ item.wrong_count }} 次 · {{ formatTime(item.last_wrong_at) }} · 来源诊断 {{ shortSession(item.session_id) }}
              </text>

              <view class="actions">
                <button class="action primary" @click.stop="redo(item)">重做</button>
                <button class="action" @click.stop="openGraph(item)">看图谱</button>
                <button class="action" @click.stop="mark(item, 'mastered')">标记已掌握</button>
                <button class="action" @click.stop="mark(item, 'ignored')">忽略</button>
              </view>
            </view>

            <view v-else class="expand-hint" @click="toggleItem(item)">
              <text>展开答案与解析</text>
              <text class="expand-chevron">▾</text>
            </view>
          </view>

          <view v-if="loadingMore" class="list-end"><text>加载中…</text></view>
          <view v-else-if="!hasMore" class="list-end"><text>没有更多了</text></view>
        </view>
      </block>

      <view class="footer-note">
        <text>题目与知识点来自 cn-math-taxonomy（CC BY-NC 4.0），由 AI 生成、未经一线教师审核，仅用于薄弱点筛查。</text>
      </view>
    </block>
  </view>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { onLoad, onReachBottom } from '@dcloudio/uni-app'
import {
  listWrongQuestions,
  markWrongQuestion,
} from '../../api.js'
import { store } from '../../store.js'
import { themeVars, isDark } from '../../theme/theme.js'
import MathText from '../../components/ui/MathText.vue'

const GRADE_LABELS = {
  1: '一年级', 2: '二年级', 3: '三年级', 4: '四年级', 5: '五年级',
  6: '六年级', 7: '七年级', 8: '八年级', 9: '九年级',
  10: '高一', 11: '高二', 12: '选必一', 13: '选必二', 14: '选必三',
}

const statusOptions = [
  { key: 'open', label: '待复习' },
  { key: 'mastered', label: '已掌握' },
  { key: 'ignored', label: '已忽略' },
  { key: 'all', label: '全部' },
]

const dayOptions = [
  { key: 0, label: '全部时间' },
  { key: 7, label: '最近 7 天' },
  { key: 30, label: '最近 30 天' },
  { key: 90, label: '最近 90 天' },
]

const markLabels = {
  open: '待复习',
  mastered: '已掌握',
  ignored: '已忽略',
}

const loggedIn = computed(() => !!(store.auth.user && store.auth.token))
const status = ref('open')
const days = ref(0)
const nodeFilter = ref('')
const userGrade = Number.isInteger(store.auth.user && store.auth.user.grade)
  ? store.auth.user.grade
  : null
const gradeFilter = ref(userGrade)
const chapterFilter = ref('')
const gradeOptions = ref([])
const chapterOptions = ref([])
const items = ref([])
const cursor = ref(null)
const hasMore = ref(false)
const total = ref(0)
const loading = ref(false)
const loadingMore = ref(false)
const error = ref('')

const summary = ref({ total: 0, node_count: 0, oldest_at: null })
const markCounts = ref({ open: 0, mastered: 0, ignored: 0 })
const nodeStats = ref([])
const showAllChapters = ref(false)
const showAllNodes = ref(false)
const expandedMap = reactive({})

const markTotal = computed(
  () =>
    (markCounts.value.open || 0) +
    (markCounts.value.mastered || 0) +
    (markCounts.value.ignored || 0)
)
const progressPercent = computed(() => {
  if (!markTotal.value) return 0
  return Math.round((markCounts.value.mastered / markTotal.value) * 100)
})
const oldestDays = computed(() => {
  if (!summary.value.oldest_at) return '—'
  const time = Date.parse(summary.value.oldest_at)
  if (!Number.isFinite(time)) return '—'
  const daysValue = Math.floor((Date.now() - time) / 86400000)
  return daysValue <= 0 ? '今天' : `${daysValue} 天`
})

const chapterHeat = computed(() => {
  const list = [...chapterOptions.value].sort((a, b) => b.count - a.count)
  const max = list[0] && list[0].count ? list[0].count : 1
  const shown = showAllChapters.value ? list : list.slice(0, 6)
  return shown.map((item) => ({
    ...item,
    width: `${Math.max(10, Math.round((item.count / max) * 100))}%`,
    opacity: 0.45 + 0.55 * (item.count / max),
  }))
})
const hasMoreChapters = computed(() => chapterOptions.value.length > 6)
// 热度条的颜色跟随当前状态筛选：待复习红、已掌握绿、已忽略灰。
const heatColor = computed(() => {
  if (status.value === 'mastered') return 'var(--ik-success)'
  if (status.value === 'ignored') return 'var(--ik-t3)'
  return 'var(--ik-danger)'
})

const maxNodeWrong = computed(() =>
  Math.max(1, (nodeStats.value[0] && nodeStats.value[0].wrong_count) || 1)
)
const nodeBlocks = computed(() =>
  showAllNodes.value ? nodeStats.value : nodeStats.value.slice(0, 12)
)
const hasMoreNodes = computed(() => nodeStats.value.length > 12)

onLoad((query) => {
  if (query && query.node_key) nodeFilter.value = String(query.node_key)
  load().then(() => {
    // 默认跟随学生年级；该年级没有错题时回退到全部年级，避免一进来就是空白。
    if (
      gradeFilter.value !== null &&
      !gradeOptions.value.some((option) => option.grade === gradeFilter.value)
    ) {
      gradeFilter.value = null
      load()
    }
  })
})

onReachBottom(() => {
  load(false)
})

async function load(reset = true) {
  if (!loggedIn.value) return
  if (!reset && (!hasMore.value || loadingMore.value)) return
  if (reset) {
    loading.value = true
    cursor.value = null
  } else {
    loadingMore.value = true
  }
  error.value = ''
  try {
    const params = { status: status.value, limit: 10 }
    if (days.value) params.days = days.value
    if (nodeFilter.value) params.node_key = nodeFilter.value
    if (gradeFilter.value !== null) params.grade = gradeFilter.value
    if (chapterFilter.value) params.chapter = chapterFilter.value
    if (!reset && cursor.value) params.cursor = cursor.value
    const data = await listWrongQuestions(params)
    const list = data.items || []
    items.value = reset ? list : items.value.concat(list)
    cursor.value = data.next_cursor || null
    hasMore.value = !!data.next_cursor
    total.value = data.total || 0
    summary.value = data.summary || {
      total: data.total || 0,
      node_count: (data.nodes || []).length,
      oldest_at: null,
    }
    markCounts.value = data.mark_counts || { open: 0, mastered: 0, ignored: 0 }
    nodeStats.value = data.nodes || []
    if (reset) {
      gradeOptions.value = data.grades || []
      chapterOptions.value = data.chapters || []
    }
  } catch (err) {
    error.value = err.message || '错题加载失败'
  } finally {
    loading.value = false
    loadingMore.value = false
  }
}

function setStatus(key) {
  if (status.value === key) return
  status.value = key
  load()
}

function setDays(value) {
  if (days.value === value) return
  days.value = value
  load()
}

function setGrade(value) {
  if (gradeFilter.value === value) return
  gradeFilter.value = value
  load()
}

function toggleChapter(chapter) {
  const next = chapterFilter.value === chapter ? '' : chapter
  if (chapterFilter.value === next) return
  chapterFilter.value = next
  load()
}

function toggleNodeFilter(nodeKey) {
  const next = nodeFilter.value === nodeKey ? '' : nodeKey
  nodeFilter.value = next
  load()
}

function clearNodeFilter() {
  nodeFilter.value = ''
  load()
}

function itemKey(item) {
  return `${item.dataset_version}:${item.question_id}`
}

function isExpanded(item) {
  return !!expandedMap[itemKey(item)]
}

function toggleItem(item) {
  const key = itemKey(item)
  expandedMap[key] = !expandedMap[key]
}

function nodeCountClass(node) {
  return node.mark_status || 'open'
}

function nodeStyle(node) {
  const ratio = Math.min(1, (node.wrong_count || 0) / maxNodeWrong.value)
  const rgb =
    node.mark_status === 'mastered'
      ? '47,158,104'
      : node.mark_status === 'ignored'
        ? '138,143,153'
        : '229,62,62'
  return { background: `rgba(${rgb}, ${(0.08 + ratio * 0.16).toFixed(3)})` }
}

async function openAllGraph() {
  if (nodeFilter.value) {
    uni.navigateTo({
      url: `/pages/graph/graph?node_key=${encodeURIComponent(nodeFilter.value)}`,
    })
    return
  }
  try {
    const params = { status: status.value, limit: 100 }
    if (days.value) params.days = days.value
    if (gradeFilter.value !== null) params.grade = gradeFilter.value
    const data = await listWrongQuestions(params)
    const keys = Array.from(
      new Set((data.items || []).map((item) => item.node_key).filter(Boolean))
    ).slice(0, 20)
    if (!keys.length) {
      uni.showToast({ title: '当前没有可展示的错题', icon: 'none' })
      return
    }
    uni.navigateTo({
      url: `/pages/graph/graph?node_keys=${encodeURIComponent(keys.join(','))}`,
    })
  } catch (err) {
    uni.showToast({ title: err.message || '图谱加载失败', icon: 'none' })
  }
}

async function mark(item, nextStatus) {
  try {
    await markWrongQuestion(item.attempt_id, nextStatus)
    uni.showToast({
      title: nextStatus === 'mastered' ? '已标记为掌握' : '已忽略',
      icon: 'none',
    })
    load()
  } catch (err) {
    uni.showToast({ title: err.message || '操作失败', icon: 'none' })
  }
}

function redo(item) {
  uni.navigateTo({
    url: `/pages/diagnosis/diagnosis?node_key=${encodeURIComponent(item.node_key)}&auto=1`,
  })
}

function openGraph(item) {
  const sessionQuery = item.session_id
    ? `&session_id=${encodeURIComponent(item.session_id)}`
    : ''
  uni.navigateTo({
    url: `/pages/graph/graph?node_key=${encodeURIComponent(item.node_key)}${sessionQuery}`,
  })
}

function goAuth() {
  uni.navigateTo({ url: '/pages/auth/auth' })
}

function goDiagnosis() {
  uni.navigateTo({ url: '/pages/diagnosis/diagnosis' })
}

function markLabel(value) {
  return markLabels[value] || '待复习'
}

function gradeLabel(grade) {
  return GRADE_LABELS[grade] || '—'
}

function shortSession(value) {
  if (!value) return '—'
  return value.length > 12 ? `${value.slice(0, 12)}…` : value
}

function formatTime(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getMonth() + 1}/${date.getDate()} ${pad(date.getHours())}:${pad(
    date.getMinutes()
  )}`
}

function svgUri(svg) {
  if (!svg) return ''
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`
}
</script>

<style scoped>
.page {
  --ik-danger-weak: rgba(229, 62, 62, 0.08);
  --ik-warn-weak: rgba(192, 86, 33, 0.1);
  --ik-warn-strong: #975a16;
  --ik-success-weak: rgba(47, 158, 104, 0.1);
  min-height: 100vh;
  background: var(--ik-bg);
  padding: 24rpx;
  box-sizing: border-box;
}

.page.is-dark {
  --ik-danger-weak: rgba(255, 107, 107, 0.14);
  --ik-warn-weak: rgba(246, 173, 85, 0.14);
  --ik-warn-strong: #fbd38d;
  --ik-success-weak: rgba(74, 222, 128, 0.16);
}

.state {
  padding: 120rpx 32rpx;
  text-align: center;
}

.state-title {
  display: block;
  font-size: 32rpx;
  font-weight: 600;
  color: var(--ik-t1);
}

.state-sub {
  display: block;
  margin-top: 14rpx;
  font-size: 24rpx;
  line-height: 1.7;
  color: var(--ik-t3);
}

.state .primary,
.state .ghost {
  margin-top: 28rpx;
}

.card {
  background: var(--ik-card);
  border-radius: 16rpx;
  padding: 24rpx;
  margin-bottom: 20rpx;
}

.card-head-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 14rpx;
}

.section-title {
  font-size: 29rpx;
  font-weight: 600;
  color: var(--ik-t1);
}

.section-hint {
  font-size: 21rpx;
  color: var(--ik-t3);
}

/* ---------- 概览 ---------- */
.overview {
  padding: 26rpx 24rpx;
}

.overview-stats {
  display: flex;
}

.overview-stat {
  flex: 1;
  text-align: center;
}

.overview-value {
  display: block;
  font-size: 40rpx;
  font-weight: 700;
  color: var(--ik-t1);
}

.overview-label {
  display: block;
  margin-top: 2rpx;
  font-size: 20rpx;
  color: var(--ik-t3);
}

.progress-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 22rpx;
}

.progress-label {
  font-size: 21rpx;
  color: var(--ik-t2);
}

.progress-value {
  font-size: 21rpx;
  color: var(--ik-success);
}

.progress-track {
  height: 14rpx;
  margin-top: 8rpx;
  border-radius: 999rpx;
  background: var(--ik-soft);
  overflow: hidden;
}

.progress-fill {
  height: 14rpx;
  border-radius: 999rpx;
  background: var(--ik-success);
  transition: width 0.3s;
}

.overview-cta {
  display: flex;
  align-items: center;
  margin-top: 22rpx;
  padding: 18rpx 20rpx;
  border-radius: 12rpx;
  background: var(--ik-primary-weak);
  color: var(--ik-primary);
}

.overview-cta-text {
  flex: 1;
  margin-left: 10rpx;
  font-size: 25rpx;
  font-weight: 600;
}

.overview-cta-meta {
  font-size: 21rpx;
  color: var(--ik-primary);
}

/* ---------- 筛选 ---------- */
.toolbar {
  margin-bottom: 18rpx;
}

.chip-scroll {
  white-space: nowrap;
}

.chip-scroll.second {
  margin-top: 12rpx;
}

.chips {
  display: inline-flex;
}

.chip {
  padding: 12rpx 26rpx;
  margin-right: 12rpx;
  border-radius: 999rpx;
  background: var(--ik-card);
  font-size: 24rpx;
  color: var(--ik-t2);
}

.chip.small {
  padding: 9rpx 22rpx;
  font-size: 22rpx;
}

.chip.active {
  background: var(--ik-primary);
  color: var(--ik-on-primary);
}

.filter-note {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 14rpx;
  padding: 14rpx 20rpx;
  border-radius: 12rpx;
  background: var(--ik-primary-weak);
  font-size: 22rpx;
  color: var(--ik-primary);
}

.clear {
  font-size: 22rpx;
  color: var(--ik-primary);
}

.total-note {
  display: block;
  margin-top: 12rpx;
  font-size: 21rpx;
  color: var(--ik-t3);
}

/* ---------- 章节热度 ---------- */
.heat-row {
  display: flex;
  align-items: center;
  padding: 12rpx 10rpx;
  border-radius: 10rpx;
}

.heat-row.active {
  background: var(--ik-primary-weak);
}

.heat-label {
  width: 210rpx;
  flex-shrink: 0;
  font-size: 23rpx;
  color: var(--ik-t1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.heat-track {
  flex: 1;
  height: 22rpx;
  margin: 0 14rpx;
  border-radius: 999rpx;
  background: var(--ik-soft);
  overflow: hidden;
}

.heat-fill {
  height: 22rpx;
  border-radius: 999rpx;
  background: var(--ik-danger);
  transition: width 0.3s;
}

.heat-count {
  width: 48rpx;
  text-align: right;
  font-size: 22rpx;
  color: var(--ik-danger);
}

.more-link {
  display: block;
  margin-top: 12rpx;
  font-size: 22rpx;
  color: var(--ik-primary);
  text-align: center;
}

/* ---------- 知识点分布 ---------- */
.node-grid {
  display: flex;
  flex-wrap: wrap;
  margin: -6rpx;
}

.node-block {
  width: calc(50% - 12rpx);
  margin: 6rpx;
  padding: 16rpx 16rpx;
  border-radius: 12rpx;
  border: 2rpx solid transparent;
  box-sizing: border-box;
}

.node-block.open {
  border-color: rgba(229, 62, 62, 0.22);
}

.node-block.mastered {
  border-color: rgba(47, 158, 104, 0.28);
}

.node-block.ignored {
  border-color: var(--ik-line);
}

.node-block.active {
  border-color: var(--ik-primary);
}

.node-block-name {
  display: block;
  font-size: 24rpx;
  font-weight: 600;
  color: var(--ik-t1);
  line-height: 1.35;
}

.node-block.open .node-block-count { color: var(--ik-danger); }
.node-block.mastered .node-block-count { color: var(--ik-success); }
.node-block.ignored .node-block-count { color: var(--ik-t3); }

.node-block-count {
  display: block;
  margin-top: 4rpx;
  font-size: 20rpx;
}

/* ---------- 错题列表 ---------- */
.list {
  padding-bottom: 40rpx;
}

.question-card {
  border-left: 6rpx solid var(--ik-line);
  padding-bottom: 18rpx;
}

.question-card.open { border-left-color: var(--ik-danger); }
.question-card.mastered { border-left-color: var(--ik-success); }
.question-card.ignored { border-left-color: var(--ik-t3); }

.card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}

.card-head-main {
  flex: 1;
  min-width: 0;
}

.card-topic {
  display: block;
  font-size: 29rpx;
  font-weight: 600;
  color: var(--ik-t1);
}

.status-tag {
  flex-shrink: 0;
  margin-left: 12rpx;
  font-size: 20rpx;
  padding: 4rpx 14rpx;
  border-radius: 999rpx;
  background: var(--ik-soft);
  color: var(--ik-t3);
}

.status-tag.open {
  background: var(--ik-danger-weak);
  color: var(--ik-danger);
}

.status-tag.mastered {
  background: var(--ik-success-weak);
  color: var(--ik-success);
}

.status-tag.ignored {
  background: var(--ik-soft);
  color: var(--ik-t3);
}

.card-meta {
  display: block;
  margin-top: 6rpx;
  font-size: 21rpx;
  color: var(--ik-t3);
}

.card-prompt {
  display: block;
  margin-top: 16rpx;
  font-size: 27rpx;
  line-height: 1.7;
  color: var(--ik-t1);
  white-space: pre-wrap;
}

.card-body {
  margin-top: 4rpx;
}

.card-figure {
  width: 100%;
  margin-top: 14rpx;
}

.expand-hint {
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 14rpx;
  padding-top: 12rpx;
  border-top: 1rpx solid var(--ik-line);
  font-size: 22rpx;
  color: var(--ik-t3);
}

.expand-chevron {
  margin-left: 8rpx;
  font-size: 20rpx;
}

.choices {
  margin-top: 16rpx;
}

.choice {
  display: flex;
  align-items: flex-start;
  padding: 14rpx 0;
  border-bottom: 1rpx solid var(--ik-line);
}

.choice:last-child {
  border-bottom: none;
}

.choice-key {
  width: 40rpx;
  height: 40rpx;
  line-height: 40rpx;
  text-align: center;
  border-radius: 50%;
  background: var(--ik-soft);
  color: var(--ik-t2);
  font-size: 22rpx;
  margin-right: 14rpx;
  flex-shrink: 0;
}

.choice-text {
  flex: 1;
  font-size: 25rpx;
  line-height: 1.6;
  color: var(--ik-t1);
}

.choice-figure {
  flex: 1;
  width: 100%;
}

.answer-box {
  margin-top: 18rpx;
  padding: 18rpx;
  border-radius: 12rpx;
  background: var(--ik-soft);
}

.answer-line {
  display: block;
  font-size: 24rpx;
  line-height: 1.8;
  color: var(--ik-t1);
}

.answer-label {
  display: inline-block;
  min-width: 120rpx;
  margin-right: 12rpx;
  font-size: 21rpx;
  color: var(--ik-t3);
}

.answer-label.correct {
  color: var(--ik-success);
}

.explanation {
  display: block;
  margin-top: 10rpx;
  font-size: 23rpx;
  line-height: 1.7;
  color: var(--ik-t2);
}

.foot-meta {
  display: block;
  margin-top: 14rpx;
  font-size: 20rpx;
  color: var(--ik-t3);
}

.actions {
  display: flex;
  flex-wrap: wrap;
  margin-top: 16rpx;
}

.action {
  font-size: 22rpx;
  padding: 0 20rpx;
  height: 58rpx;
  line-height: 58rpx;
  margin: 0 12rpx 12rpx 0;
  border-radius: 999rpx;
  background: var(--ik-soft);
  color: var(--ik-t2);
}

.action.primary {
  background: var(--ik-primary);
  color: var(--ik-on-primary);
}

.primary {
  background: var(--ik-primary);
  color: var(--ik-on-primary);
  border-radius: 14rpx;
  font-size: 28rpx;
}

.ghost {
  background: var(--ik-card);
  color: var(--ik-primary);
  border: 2rpx solid var(--ik-line);
  border-radius: 14rpx;
  font-size: 28rpx;
}

.list-end {
  padding: 24rpx 0;
  text-align: center;
  font-size: 22rpx;
  color: var(--ik-t3);
}

.footer-note {
  padding: 12rpx 8rpx 30rpx;
  text-align: center;
  font-size: 19rpx;
  line-height: 1.6;
  color: var(--ik-t3);
}
</style>
