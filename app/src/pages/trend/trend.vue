<template>
  <view class="page theme-root" :class="{ 'is-dark': isDark }" :style="themeVars">
    <ThemeBackground />

    <!-- 默认跟随学生年级；随时可切回全部年级看历史。 -->
    <view v-if="loggedIn && userGrade" class="grade-filter">
      <scroll-view scroll-x class="chip-scroll">
        <view class="chips">
          <view
            class="chip"
            :class="{ active: gradeFilter === userGrade }"
            @click="setGradeFilter(userGrade)"
          >我的年级 · {{ gradeLabel(userGrade) }}</view>
          <view
            class="chip"
            :class="{ active: gradeFilter === null }"
            @click="setGradeFilter(null)"
          >全部年级</view>
        </view>
      </scroll-view>
    </view>

    <view v-if="!loggedIn" class="state">
      <text class="state-title">登录后查看学情趋势</text>
      <text class="state-sub">登录后，每次诊断的掌握率、薄弱点与知识点状态都会留下记录。</text>
      <button class="primary" @click="goAuth">去登录</button>
    </view>

    <view v-else-if="loading" class="state">
      <text class="state-sub">正在计算趋势…</text>
    </view>

    <view v-else-if="error" class="state">
      <text class="state-sub">{{ error }}</text>
      <button class="ghost" @click="load">重试</button>
    </view>

    <view v-else-if="isEmpty" class="state">
      <text class="state-title">还没有足够数据形成趋势</text>
      <text class="state-sub">至少完成 2 次诊断后，才能比较掌握率、薄弱点和覆盖范围的变化。</text>
      <button class="primary" @click="goDiagnosis">去诊断</button>
    </view>

    <block v-else-if="data">
      <view class="hero">
        <text class="hero-title">学情趋势</text>
        <text class="hero-sub">
          最近 {{ data.range.session_count }} 次诊断 · {{ rangeText }}
        </text>
      </view>

      <!-- 主视觉：最近一次诊断的掌握结构 -->
      <view class="card hero-card">
        <view class="hero-main">
          <view class="donut-wrap">
            <view class="donut" :style="donutStyle">
              <view class="donut-hole">
                <text class="donut-value">{{ percent(latest.mastery_rate) }}</text>
                <text class="donut-label">掌握率</text>
              </view>
            </view>
            <text class="donut-delta" :class="deltaClass(masteryDelta)">
              {{ deltaText(masteryDelta, '%') }} 较上次
            </text>
          </view>

          <view class="hero-metrics">
            <view class="hero-metric">
              <text class="hero-metric-label">薄弱点</text>
              <text class="hero-metric-value weak-text">{{ latest.counts.weak || 0 }}</text>
              <text class="hero-metric-delta" :class="deltaClass(weakImprovement)">
                {{ deltaText(weakImprovement) }}
              </text>
            </view>
            <view class="hero-metric">
              <text class="hero-metric-label">覆盖率</text>
              <text class="hero-metric-value">{{ percent(latest.coverage) }}</text>
              <text class="hero-metric-delta" :class="deltaClass(coverageDelta)">
                {{ deltaText(coverageDelta, '%') }}
              </text>
            </view>
            <view class="hero-metric">
              <text class="hero-metric-label">本次已测</text>
              <text class="hero-metric-value">{{ latest.assessed || 0 }}</text>
              <text class="hero-metric-delta flat">个知识点</text>
            </view>
          </view>
        </view>

        <view class="donut-legend">
          <view v-for="seg in donutSegments" :key="seg.key" class="legend-item">
            <text class="dot" :class="seg.key"></text>
            <text>{{ seg.label }} {{ seg.value }}</text>
          </view>
        </view>
      </view>

      <text class="compare-note">
        上次掌握率 {{ percent(previous.mastery_rate) }} · 首次 {{ percent(first.mastery_rate) }}
      </text>
      <text class="compare-note">
        较首次：掌握率 {{ deltaText(masteryDeltaFirst, '%') }} · 薄弱点 {{ deltaText(weakImprovementFirst) }} · 覆盖率 {{ deltaText(coverageDeltaFirst, '%') }}
      </text>

      <!-- 每次诊断一条 100% 堆叠条：同时看趋势和结构 -->
      <view class="card">
        <view class="card-head-row">
          <text class="section-title">掌握结构变化</text>
          <text class="section-hint">每次诊断一条</text>
        </view>
        <view
          v-for="item in data.sessions"
          :key="item.session_id"
          class="stack-row"
          :class="{ 'break-start': isBreakStart(item) }"
        >
          <text class="bar-label">{{ formatDate(item.created_at) }}</text>
          <view class="stack-track">
            <view
              v-for="seg in stackSegments(item)"
              :key="seg.key"
              class="stack-seg"
              :class="seg.key"
              :style="{ width: seg.width }"
            ></view>
            <view v-if="!stackSegments(item).length" class="stack-empty"></view>
          </view>
          <text class="bar-value">{{ percent(item.mastery_rate) }}</text>
          <text v-if="isBreakStart(item)" class="bar-break">新版本</text>
        </view>

        <view class="stack-legend">
          <view v-for="item in stackLegend" :key="item.key" class="legend-item">
            <text class="dot" :class="item.key"></text>
            <text>{{ item.label }}</text>
          </view>
        </view>
        <text class="section-hint">
          右侧数字是掌握率；不同次诊断覆盖范围不同，请优先比较比率与覆盖率。
        </text>
      </view>

      <view v-if="data.version_breaks && data.version_breaks.length" class="note">
        题库版本发生变化（{{ data.version_breaks.length }} 处），版本前后不做连续比较。
      </view>

      <!-- 薄弱知识链：从先修到本次薄弱点，回答“先补哪个” -->
      <view v-if="chainLayers.length" class="card">
        <view class="card-head-row">
          <view class="card-head-main">
            <text class="section-title">薄弱知识链</text>
            <text class="section-hint">{{ chainSeedName }}：从上到下依次补</text>
          </view>
          <text class="link" @click="openFullGraph">完整图谱 ›</text>
        </view>
        <view class="chain">
          <view v-for="(layer, index) in chainLayers" :key="layer.depth" class="chain-layer">
            <text class="chain-depth">{{ layer.title }}</text>
            <view class="chain-nodes">
              <text
                v-for="node in layer.nodes"
                :key="node.id"
                class="chain-node"
                :class="chainNodeClass(node)"
              >{{ node.name }}</text>
            </view>
            <text v-if="index < chainLayers.length - 1" class="chain-arrow">↓</text>
          </view>
        </view>
      </view>

      <!-- 知识点 × 时间热力矩阵 -->
      <view class="card">
        <view class="card-head-row">
          <text class="section-title">知识点状态热力</text>
          <text v-if="hasMorePoints" class="link" @click="showAllPoints = !showAllPoints">
            {{ showAllPoints ? '收起' : '全部' }}
          </text>
        </view>

        <scroll-view scroll-x class="chip-scroll">
          <view class="chips">
            <view
              class="chip"
              :class="{ active: chapterFilter === '' }"
              @click="setChapter('')"
            >全部章节</view>
            <view
              v-for="option in chapterOptions"
              :key="option.key"
              class="chip"
              :class="{ active: chapterFilter === option.key }"
              @click="setChapter(option.key)"
            >{{ option.label }}</view>
          </view>
        </scroll-view>

        <view class="heat-legend">
          <view class="legend-item"><text class="dot weak"></text><text>薄弱</text></view>
          <view class="legend-item"><text class="dot unstable"></text><text>不稳</text></view>
          <view class="legend-item"><text class="dot mastered"></text><text>掌握</text></view>
          <view class="legend-item"><text class="dot proficient"></text><text>熟练</text></view>
          <view class="legend-item"><text class="dot empty"></text><text>未考</text></view>
        </view>

        <view class="heat-table">
          <view class="heat-row heat-header">
            <text class="heat-name">知识点</text>
            <text
              v-for="session in data.sessions"
              :key="'h-' + session.session_id"
              class="heat-date"
            >{{ formatDate(session.created_at) }}</text>
          </view>
          <view v-for="point in visiblePoints" :key="point.node_key" class="heat-row">
            <text class="heat-name">{{ point.name }}</text>
            <view
              v-for="session in data.sessions"
              :key="point.node_key + ':' + session.session_id"
              class="heat-cell-wrap"
              @click="selectCell(point, session)"
            >
              <view
                class="heat-cell"
                :class="[cellClass(point, session), { selected: isCellSelected(point, session) }]"
              ></view>
            </view>
          </view>
        </view>

        <text v-if="selectedCell" class="cell-detail">{{ selectedCell }}</text>
        <text v-if="!visiblePoints.length" class="section-hint">该章节暂无时间线数据。</text>
      </view>

      <!-- 学习变化清单 -->
      <view class="card">
        <view class="trend-section">
          <view class="card-head-row">
            <text class="section-title">持续薄弱</text>
            <text class="section-hint">{{ data.continuous_weak.length }} 个</text>
          </view>
          <view
            v-for="item in data.continuous_weak"
            :key="item.node_key"
            class="row-item"
          >
            <text class="row-name">{{ item.name }}</text>
            <text class="row-meta weak-text">连续 {{ item.count }} 次薄弱</text>
          </view>
          <text v-if="!data.continuous_weak.length" class="section-hint">
            暂时没有连续 2 次以上薄弱的知识点。
          </text>
        </view>

        <view class="divider"></view>

        <view class="trend-section">
          <view class="card-head-row">
            <text class="section-title">已改善</text>
            <text class="section-hint">{{ data.improved.length }} 个</text>
          </view>
          <view
            v-for="item in data.improved"
            :key="item.node_key"
            class="row-item"
          >
            <text class="row-name">{{ item.name }}</text>
            <text class="row-meta good-text">{{ statusText[item.from] || item.from }} → {{ statusText[item.to] || item.to }}</text>
          </view>
          <text v-if="!data.improved.length" class="section-hint">
            还没有从薄弱 / 不稳变为掌握的知识点。
          </text>
        </view>

        <view class="divider"></view>

        <view class="trend-section">
          <view class="card-head-row">
            <text class="section-title">反复错题</text>
            <text class="section-hint">{{ data.repeated_wrong.length }} 道</text>
          </view>
          <view
            v-for="item in data.repeated_wrong"
            :key="item.question_id"
            class="row-item"
          >
            <view class="row-main">
              <text class="row-name">{{ item.name }}</text>
              <text class="row-sub">{{ item.question_id }}</text>
            </view>
            <text class="row-meta weak-text">错 {{ item.wrong_count }} 次</text>
          </view>
          <text v-if="!data.repeated_wrong.length" class="section-hint">
            没有同一道题错 2 次以上的记录。
          </text>
        </view>
      </view>

      <view class="footer-note">
        <text>知识点与题目来自 cn-math-taxonomy（CC BY-NC 4.0），由 AI 生成、未经一线教师审核。</text>
      </view>
    </block>
  </view>
</template>

<script setup>
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { getDiagnosisGraph, getDiagnosisTrends } from '../../api.js'
import { store } from '../../store.js'
import { themeVars, isDark, tokens } from '../../theme/theme.js'

const statusText = {
  proficient: '熟练',
  mastered: '掌握',
  unstable: '不稳',
  weak: '薄弱',
}

const stackLegend = [
  { key: 'proficient', label: '熟练' },
  { key: 'mastered', label: '掌握' },
  { key: 'unstable', label: '不稳' },
  { key: 'weak', label: '薄弱' },
  { key: 'untested', label: '未测' },
]

const GRADE_LABELS = {
  1: '一年级',
  2: '二年级',
  3: '三年级',
  4: '四年级',
  5: '五年级',
  6: '六年级',
  7: '七年级',
  8: '八年级',
  9: '九年级',
}

const loggedIn = computed(() => !!(store.auth.user && store.auth.token))
const userGrade = Number.isInteger(store.auth.user && store.auth.user.grade)
  ? store.auth.user.grade
  : null
// 默认只看当前年级；用户可临时切到全部年级，不写回资料。
const gradeFilter = ref(userGrade)
const data = ref(null)
const loading = ref(false)
const error = ref('')
const chapterFilter = ref('')
const showAllPoints = ref(false)
const selectedCell = ref('')
const selectedKey = ref('')
const chain = ref(null)

const isEmpty = computed(
  () => !data.value || data.value.reason === 'not_enough_sessions' || !(data.value.sessions || []).length
)

const sessions = computed(() => (data.value && data.value.sessions) || [])
const latest = computed(() => sessions.value[sessions.value.length - 1] || {})
const previous = computed(() => sessions.value[sessions.value.length - 2] || {})
const first = computed(() => sessions.value[0] || {})

const masteryDelta = computed(() =>
  numericDelta(latest.value.mastery_rate, previous.value.mastery_rate)
)
const coverageDelta = computed(() =>
  numericDelta(latest.value.coverage, previous.value.coverage)
)
const weakImprovement = computed(() => weakImprovementAgainst(previous.value))
const weakImprovementFirst = computed(() => weakImprovementAgainst(first.value))
const masteryDeltaFirst = computed(() =>
  numericDelta(latest.value.mastery_rate, first.value.mastery_rate)
)
const coverageDeltaFirst = computed(() =>
  numericDelta(latest.value.coverage, first.value.coverage)
)

function weakImprovementAgainst(reference) {
  const before = numberOrNull(reference.counts && reference.counts.weak)
  const after = numberOrNull(latest.value.counts && latest.value.counts.weak)
  if (before === null || after === null) return null
  return before - after
}

// ---------- 环形图 ----------
const donutSegments = computed(() => {
  const counts = (latest.value && latest.value.counts) || {}
  const proficient = counts.proficient || 0
  const masteredOnly = Math.max(0, (counts.mastered || 0) - proficient)
  return [
    {
      key: 'proficient',
      label: '熟练',
      value: proficient,
      color: isDark.value ? '#86efac' : '#1d6b45',
    },
    { key: 'mastered', label: '掌握', value: masteredOnly, color: tokens.value.success },
    { key: 'unstable', label: '不稳', value: counts.unstable || 0, color: '#d69e2e' },
    { key: 'weak', label: '薄弱', value: counts.weak || 0, color: tokens.value.danger },
  ]
})

const donutStyle = computed(() => {
  const total = donutSegments.value.reduce((sum, seg) => sum + seg.value, 0)
  if (!total) {
    return { background: `conic-gradient(${tokens.value.line} 0% 100%)` }
  }
  let acc = 0
  const stops = []
  donutSegments.value.forEach((seg) => {
    if (!seg.value) return
    const start = (acc / total) * 100
    acc += seg.value
    const end = (acc / total) * 100
    stops.push(`${seg.color} ${start}% ${end}%`)
  })
  return { background: `conic-gradient(${stops.join(', ')})` }
})

// ---------- 堆叠条 ----------
function stackSegments(session) {
  const counts = (session && session.counts) || {}
  const proficient = counts.proficient || 0
  const masteredOnly = Math.max(0, (counts.mastered || 0) - proficient)
  const unstable = counts.unstable || 0
  const weak = counts.weak || 0
  const untested = (counts.untested || 0) + (counts.insufficient || 0)
  const total = proficient + masteredOnly + unstable + weak + untested
  if (!total) return []
  return [
    { key: 'proficient', value: proficient },
    { key: 'mastered', value: masteredOnly },
    { key: 'unstable', value: unstable },
    { key: 'weak', value: weak },
    { key: 'untested', value: untested },
  ]
    .filter((seg) => seg.value > 0)
    .map((seg) => ({ ...seg, width: `${(seg.value / total) * 100}%` }))
}

const rangeText = computed(() => {
  if (!data.value || !data.value.range) return ''
  const from = formatDate(data.value.range.from)
  const to = formatDate(data.value.range.to)
  return from && to ? `${from} – ${to}` : ''
})

// ---------- 章节筛选与热力矩阵 ----------
const chapterOptions = computed(() => {
  const map = new Map()
  ;((data.value && data.value.points) || []).forEach((point) => {
    const key = point.chapter || '未分章'
    if (!map.has(key)) map.set(key, point.chapter_label || key)
  })
  return Array.from(map.entries()).map(([key, label]) => ({ key, label }))
})

const filteredPoints = computed(() => {
  const points = (data.value && data.value.points) || []
  if (!chapterFilter.value) return points
  return points.filter((point) => (point.chapter || '未分章') === chapterFilter.value)
})

const visiblePoints = computed(() =>
  showAllPoints.value ? filteredPoints.value : filteredPoints.value.slice(0, 8)
)
const hasMorePoints = computed(() => filteredPoints.value.length > 8)

const breakSessions = computed(() => {
  const set = new Set()
  ;((data.value && data.value.version_breaks) || []).forEach((brk) => {
    set.add(brk.before_session)
  })
  return set
})

function setChapter(key) {
  if (chapterFilter.value === key) return
  chapterFilter.value = key
  selectedCell.value = ''
  selectedKey.value = ''
}

function cellEntry(point, session) {
  return (
    (point.history || []).find((entry) => entry.session_id === session.session_id) ||
    null
  )
}

function cellClass(point, session) {
  const entry = cellEntry(point, session)
  if (!entry) return 'empty'
  if (entry.mastery_level === 'proficient') return 'proficient'
  return entry.status || 'empty'
}

function cellLabel(point, session) {
  const entry = cellEntry(point, session)
  if (!entry) return '未考'
  const key = entry.mastery_level === 'proficient' ? 'proficient' : entry.status
  return statusText[key] || '未考'
}

function isCellSelected(point, session) {
  return selectedKey.value === `${point.node_key}:${session.session_id}`
}

function selectCell(point, session) {
  selectedKey.value = `${point.node_key}:${session.session_id}`
  selectedCell.value = `${point.name} · ${formatDate(session.created_at)} · ${cellLabel(
    point,
    session
  )}`
}

// ---------- 薄弱知识链 ----------
const chainSeedName = computed(() => {
  if (!chain.value) return ''
  const node = (chain.value.nodes || []).find((item) => item.id === chain.value.seed)
  return node ? node.name : ''
})

const chainLayers = computed(() => {
  if (!chain.value) return []
  const byDepth = new Map()
  ;(chain.value.nodes || []).forEach((node) => {
    const depth = node.depth || 0
    if (!byDepth.has(depth)) byDepth.set(depth, [])
    byDepth.get(depth).push(node)
  })
  return Array.from(byDepth.entries())
    .sort((a, b) => b[0] - a[0])
    .map(([depth, nodes]) => ({
      depth,
      title: depth === 0 ? '当前薄弱点' : `第 ${depth} 层先修`,
      nodes: nodes.sort((a, b) => (a.name || '').localeCompare(b.name || '')),
    }))
})

function chainNodeClass(node) {
  if (node.mastery_level === 'proficient') return 'proficient'
  return node.status || 'untested'
}

async function loadChain() {
  chain.value = null
  const latestSession = sessions.value[sessions.value.length - 1]
  if (!latestSession) return
  const seed = pickWeakSeed(latestSession.session_id)
  if (!seed) return
  try {
    // session_id 提供状态颜色；前端再裁剪成 seed 的先修子链，避免多个种子混成一片。
    const graph = await getDiagnosisGraph({
      session_id: latestSession.session_id,
      node_keys: [seed],
      depth: 2,
    })
    const nodes = buildAncestorChain(graph, seed)
    if (nodes.length) chain.value = { seed, nodes }
  } catch (e) {
    chain.value = null
  }
}

function pickWeakSeed(latestSessionId) {
  const points = (data.value && data.value.points) || []
  const inLatest = (point) =>
    (point.history || []).find((entry) => entry.session_id === latestSessionId)
  const weak = points.find((point) => {
    const entry = inLatest(point)
    return entry && entry.status === 'weak'
  })
  if (weak) return weak.node_key
  const unstable = points.find((point) => {
    const entry = inLatest(point)
    return entry && entry.status === 'unstable'
  })
  if (unstable) return unstable.node_key
  // 最近一次没测到薄弱点时，退回到持续薄弱清单。
  const continuous = (data.value && data.value.continuous_weak) || []
  return continuous.length ? continuous[0].node_key : ''
}

function buildAncestorChain(graph, seed) {
  const nodeMap = new Map((graph.nodes || []).map((node) => [node.id, node]))
  if (!nodeMap.has(seed)) return []
  const parents = new Map()
  ;(graph.edges || []).forEach((edge) => {
    if (!parents.has(edge.target)) parents.set(edge.target, [])
    parents.get(edge.target).push(edge.source)
  })
  const level = { [seed]: 0 }
  let frontier = [seed]
  for (let depth = 1; depth <= 2; depth += 1) {
    const next = []
    frontier.forEach((id) => {
      ;(parents.get(id) || []).forEach((parent) => {
        if (!(parent in level) && nodeMap.has(parent)) {
          level[parent] = depth
          next.push(parent)
        }
      })
    })
    frontier = next
  }
  return Object.entries(level)
    .map(([id, depth]) => ({ ...nodeMap.get(id), depth }))
    .filter((node) => node && node.id)
}

function openFullGraph() {
  if (!chain.value) return
  const latestSession = sessions.value[sessions.value.length - 1]
  const sessionQuery = latestSession
    ? `&session_id=${encodeURIComponent(latestSession.session_id)}`
    : ''
  uni.navigateTo({
    url: `/pages/graph/graph?node_key=${encodeURIComponent(chain.value.seed)}${sessionQuery}`,
  })
}

function gradeLabel(value) {
  return GRADE_LABELS[value] || `${value}年级`
}

function setGradeFilter(value) {
  if (gradeFilter.value === value) return
  gradeFilter.value = value
  load()
}

onLoad(() => {
  if (!loggedIn.value) return
  load()
})

async function load() {
  if (!loggedIn.value) return
  loading.value = true
  error.value = ''
  try {
    data.value = await getDiagnosisTrends({ grade: gradeFilter.value })
    selectedCell.value = ''
    selectedKey.value = ''
  } catch (err) {
    error.value = err.message || '趋势加载失败'
  } finally {
    loading.value = false
  }
  // 知识链是二级数据，不阻塞主趋势渲染。
  if (data.value) loadChain()
}

function numberOrNull(value) {
  return typeof value === 'number' && !Number.isNaN(value) ? value : null
}

function numericDelta(current, previousValue) {
  const a = numberOrNull(current)
  const b = numberOrNull(previousValue)
  if (a === null || b === null) return null
  return a - b
}

function percent(value) {
  const number = numberOrNull(value)
  return number === null ? '—' : `${Math.round(number * 100)}%`
}

function deltaText(value, suffix = '') {
  const number = numberOrNull(value)
  if (number === null) return '—'
  if (Math.abs(number) < 0.0001) return '持平'
  const up = number > 0
  const amount =
    suffix === '%' ? Math.round(number * 100) : Math.round(Math.abs(number))
  return `${up ? '↑' : '↓'}${Math.abs(amount)}${suffix}`
}

function deltaClass(value) {
  const number = numberOrNull(value)
  if (number === null || Math.abs(number) < 0.0001) return 'flat'
  return number > 0 ? 'good' : 'bad'
}

function isBreakStart(session) {
  return breakSessions.value.has(session.session_id)
}

function formatDate(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return `${date.getMonth() + 1}/${date.getDate()}`
}

function goAuth() {
  uni.navigateTo({ url: '/pages/auth/auth' })
}

function goDiagnosis() {
  uni.navigateTo({ url: '/pages/diagnosis/diagnosis' })
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

.hero {
  padding: 6rpx 6rpx 18rpx;
}

.hero-title {
  display: block;
  font-size: 38rpx;
  font-weight: 700;
  color: var(--ik-t1);
}

.hero-sub {
  display: block;
  margin-top: 6rpx;
  font-size: 22rpx;
  color: var(--ik-t3);
}

.card {
  background: var(--ik-card);
  border-radius: 16rpx;
  padding: 24rpx;
  margin-top: 20rpx;
}

.card-head-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}

.card-head-main {
  flex: 1;
  min-width: 0;
}

.section-title {
  display: block;
  font-size: 29rpx;
  font-weight: 600;
  color: var(--ik-t1);
}

.section-hint {
  display: block;
  margin-top: 6rpx;
  font-size: 21rpx;
  line-height: 1.6;
  color: var(--ik-t3);
}

.link {
  flex-shrink: 0;
  margin-left: 16rpx;
  font-size: 22rpx;
  color: var(--ik-primary);
}

/* ---------- 英雄卡：环形图 ---------- */
.hero-card {
  margin-top: 8rpx;
}

.hero-main {
  display: flex;
  align-items: center;
}

.donut-wrap {
  width: 240rpx;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.donut {
  width: 200rpx;
  height: 200rpx;
  border-radius: 50%;
  position: relative;
}

.donut-hole {
  position: absolute;
  top: 28rpx;
  left: 28rpx;
  right: 28rpx;
  bottom: 28rpx;
  border-radius: 50%;
  background: var(--ik-card);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.donut-value {
  font-size: 40rpx;
  font-weight: 700;
  color: var(--ik-t1);
}

.donut-label {
  margin-top: 2rpx;
  font-size: 19rpx;
  color: var(--ik-t3);
}

.donut-delta {
  margin-top: 12rpx;
  font-size: 20rpx;
  color: var(--ik-t3);
}

.hero-metrics {
  flex: 1;
  margin-left: 18rpx;
}

.hero-metric {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  padding: 10rpx 0;
  border-bottom: 1rpx solid var(--ik-line);
}

.hero-metric:last-child {
  border-bottom: none;
}

.hero-metric-label {
  font-size: 21rpx;
  color: var(--ik-t3);
}

.hero-metric-value {
  font-size: 30rpx;
  font-weight: 700;
  color: var(--ik-t1);
}

.hero-metric-delta {
  font-size: 19rpx;
  color: var(--ik-t3);
}

.donut-legend,
.stack-legend,
.heat-legend {
  display: flex;
  flex-wrap: wrap;
  margin-top: 14rpx;
}

.legend-item {
  display: flex;
  align-items: center;
  margin-right: 20rpx;
  font-size: 20rpx;
  color: var(--ik-t2);
}

.dot {
  width: 16rpx;
  height: 16rpx;
  border-radius: 50%;
  margin-right: 6rpx;
}

.dot.proficient { background: #1d6b45; }
.dot.mastered { background: var(--ik-success); }
.dot.unstable { background: #d69e2e; }
.dot.weak { background: var(--ik-danger); }
.dot.untested { background: var(--ik-t3); }
.dot.empty { background: var(--ik-soft); border: 1rpx dashed var(--ik-t3); }
.page.is-dark .dot.proficient { background: #86efac; }

.good { color: var(--ik-success); }
.bad { color: var(--ik-danger); }
.flat { color: var(--ik-t3); }
.weak-text { color: var(--ik-danger); }
.good-text { color: var(--ik-success); }

.compare-note {
  display: block;
  margin: 12rpx 6rpx 0;
  font-size: 21rpx;
  color: var(--ik-t3);
}

/* ---------- 堆叠条 ---------- */
.stack-row {
  display: flex;
  align-items: center;
  margin-top: 14rpx;
}

.stack-row.break-start {
  margin-top: 20rpx;
  padding-top: 14rpx;
  border-top: 1rpx dashed var(--ik-line);
}

.bar-label {
  width: 82rpx;
  flex-shrink: 0;
  font-size: 20rpx;
  color: var(--ik-t3);
}

.stack-track {
  flex: 1;
  height: 28rpx;
  margin: 0 12rpx;
  border-radius: 999rpx;
  background: var(--ik-soft);
  display: flex;
  overflow: hidden;
}

.stack-seg {
  height: 28rpx;
  flex-shrink: 0;
}

.stack-seg.proficient { background: #1d6b45; }
.stack-seg.mastered { background: var(--ik-success); }
.stack-seg.unstable { background: #d69e2e; }
.stack-seg.weak { background: var(--ik-danger); }
.stack-seg.untested { background: var(--ik-line); }
.page.is-dark .stack-seg.proficient { background: #86efac; }

.stack-empty {
  width: 100%;
  background: var(--ik-soft);
}

.bar-value {
  width: 72rpx;
  text-align: right;
  font-size: 20rpx;
  color: var(--ik-t2);
}

.bar-break {
  margin-left: 8rpx;
  font-size: 17rpx;
  color: var(--ik-warn-strong);
}

.note {
  margin-top: 16rpx;
  padding: 18rpx 22rpx;
  border-radius: 12rpx;
  background: var(--ik-warn-weak);
  font-size: 22rpx;
  line-height: 1.6;
  color: var(--ik-warn-strong);
}

/* ---------- 薄弱知识链 ---------- */
.chain {
  margin-top: 14rpx;
}

.chain-layer {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.chain-depth {
  font-size: 20rpx;
  color: var(--ik-t3);
}

.chain-nodes {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  margin-top: 8rpx;
}

.chain-node {
  padding: 8rpx 20rpx;
  margin: 0 6rpx 8rpx;
  border-radius: 999rpx;
  background: var(--ik-soft);
  color: var(--ik-t2);
  font-size: 22rpx;
}

.chain-node.weak {
  background: var(--ik-danger-weak);
  color: var(--ik-danger);
}

.chain-node.unstable {
  background: var(--ik-warn-weak);
  color: var(--ik-warn-strong);
}

.chain-node.mastered,
.chain-node.proficient {
  background: var(--ik-success-weak);
  color: var(--ik-success);
}

.chain-arrow {
  margin: 2rpx 0 8rpx;
  font-size: 22rpx;
  color: var(--ik-t3);
}

/* ---------- 年级筛选 ---------- */
.grade-filter {
  margin-bottom: 16rpx;
}
.grade-filter .chip-scroll {
  margin-top: 0;
}

/* ---------- 热力矩阵 ---------- */
.chip-scroll {
  white-space: nowrap;
  margin-top: 14rpx;
}

.chips {
  display: inline-flex;
}

.chip {
  padding: 9rpx 20rpx;
  margin-right: 10rpx;
  border-radius: 999rpx;
  background: var(--ik-soft);
  font-size: 21rpx;
  color: var(--ik-t2);
}

.chip.active {
  background: var(--ik-primary);
  color: var(--ik-on-primary);
}

.heat-table {
  margin-top: 14rpx;
}

.heat-row {
  display: flex;
  align-items: center;
  min-height: 38rpx;
}

.heat-header {
  margin-bottom: 6rpx;
}

.heat-name {
  width: 176rpx;
  flex-shrink: 0;
  padding-right: 8rpx;
  font-size: 21rpx;
  color: var(--ik-t1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  box-sizing: border-box;
}

.heat-header .heat-name {
  font-size: 19rpx;
  color: var(--ik-t3);
}

.heat-date {
  flex: 1;
  text-align: center;
  font-size: 16rpx;
  color: var(--ik-t3);
  overflow: hidden;
  white-space: nowrap;
}

.heat-cell-wrap {
  flex: 1;
  padding: 3rpx 2rpx;
}

.heat-cell {
  height: 30rpx;
  border-radius: 6rpx;
  border: 2rpx solid transparent;
  box-sizing: border-box;
}

.heat-cell.weak { background: var(--ik-danger); }
.heat-cell.unstable { background: #d69e2e; }
.heat-cell.mastered { background: var(--ik-success); }
.heat-cell.proficient { background: #1d6b45; }
.heat-cell.empty {
  background: var(--ik-soft);
  border: 1rpx dashed var(--ik-line);
}
.page.is-dark .heat-cell.proficient { background: #86efac; }

.heat-cell.selected {
  border-color: var(--ik-t1);
}

.cell-detail {
  display: block;
  margin-top: 14rpx;
  padding: 12rpx 16rpx;
  border-radius: 10rpx;
  background: var(--ik-soft);
  font-size: 21rpx;
  color: var(--ik-t2);
}

/* ---------- 学习变化清单 ---------- */
.trend-section {
  min-height: 20rpx;
}

.divider {
  height: 1rpx;
  margin: 22rpx 0;
  background: var(--ik-line);
}

.row-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14rpx 0;
  border-bottom: 1rpx solid var(--ik-line);
}

.row-item:last-of-type {
  border-bottom: none;
}

.row-main {
  flex: 1;
  min-width: 0;
}

.row-name {
  font-size: 24rpx;
  color: var(--ik-t1);
}

.row-sub {
  display: block;
  margin-top: 2rpx;
  font-size: 19rpx;
  color: var(--ik-t3);
}

.row-meta {
  flex-shrink: 0;
  margin-left: 16rpx;
  font-size: 21rpx;
  color: var(--ik-t2);
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

.footer-note {
  padding: 16rpx 8rpx 40rpx;
  text-align: center;
  font-size: 19rpx;
  line-height: 1.6;
  color: var(--ik-t3);
}
</style>
