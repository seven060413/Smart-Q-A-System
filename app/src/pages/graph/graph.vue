<template>
  <view class="page theme-root" :class="{ 'is-dark': isDark }" :style="themeVars">
    <ThemeBackground />
    <view class="legend">
      <view class="legend-item"><text class="dot weak"></text><text>薄弱</text></view>
      <view class="legend-item"><text class="dot unstable"></text><text>不稳</text></view>
      <view class="legend-item"><text class="dot mastered"></text><text>掌握</text></view>
      <view class="legend-item"><text class="dot proficient"></text><text>熟练</text></view>
      <view class="legend-item"><text class="dot untested"></text><text>未测</text></view>
    </view>
    <view class="edge-legend">
      <view class="legend-item"><view class="line hard"></view><text>必修先修</text></view>
      <view class="legend-item"><view class="line soft"></view><text>建议先修</text></view>
    </view>

    <view v-if="loading" class="state">
      <text class="state-sub">正在生成知识图谱…</text>
    </view>

    <view v-else-if="error" class="state">
      <text class="state-sub">{{ error }}</text>
      <button class="ghost" @click="load">重试</button>
    </view>

    <view v-else-if="!nodes.length" class="state">
      <text class="state-title">没有可展示的知识点</text>
      <text class="state-sub">请从诊断结果或错题集里选择一个薄弱点。</text>
    </view>

    <view v-else class="graph">
      <text class="graph-hint">
        先修关系在上，错题知识点在下方。点击节点查看详情。
      </text>

      <view v-for="layer in layers" :key="layer.depth" class="layer">
        <view class="layer-head">
          <text class="layer-title">{{ layer.title }}</text>
          <text class="layer-count">{{ layer.nodes.length }} 点</text>
        </view>

        <scroll-view scroll-x class="node-scroll">
          <view class="node-row">
            <view
              v-for="node in layer.nodes"
              :key="node.id"
              class="node"
              :class="statusClass(node)"
              @click="selectNode(node)"
            >
              <text class="node-name">{{ node.name }}</text>
              <text class="node-meta">{{ gradeLabel(node.grade) }}</text>
            </view>
          </view>
        </scroll-view>

        <view v-if="layer.depth > 0 && visibleEdges(layer.depth).length" class="edges">
          <view
            v-for="(edge, index) in visibleEdges(layer.depth)"
            :key="edge.source + ':' + edge.target + ':' + index"
            class="edge-row"
          >
            <text class="edge-label">{{ nameOf(edge.source) }}</text>
            <view class="edge-line" :class="edge.strength"></view>
            <text class="edge-label">{{ nameOf(edge.target) }}</text>
          </view>
          <text v-if="hiddenEdgeCount(layer.depth) > 0" class="edge-more">
            另有 {{ hiddenEdgeCount(layer.depth) }} 条先修关系未显示
          </text>
        </view>
      </view>

      <view v-if="maxDepth > depthLimit" class="expand">
        <button class="primary" @click="expanded = true">
          展开更多（还有 {{ hiddenNodeCount }} 个先修点）
        </button>
      </view>
      <view v-else-if="expanded && maxDepth > 1" class="expand">
        <button class="ghost" @click="expanded = false">收起深层先修</button>
      </view>

      <view class="footer-note">
        <text>知识图谱来自 cn-math-taxonomy（CC BY-NC 4.0），仅限非商业使用。</text>
      </view>
    </view>

    <view v-if="selected" class="sheet-mask" @click="selected = null">
      <view class="sheet" @click.stop>
        <view class="sheet-head">
          <text class="sheet-title">{{ selected.name }}</text>
          <text class="status-pill" :class="statusClass(selected)">{{ statusLabel(selected) }}</text>
        </view>
        <text class="sheet-meta">
          {{ gradeLabel(selected.grade) }} · {{ selected.chapter_label || selected.chapter }}
        </text>
        <text class="sheet-depth">
          {{ selected.depth === 0 ? '本次错题 / 薄弱知识点' : `向上第 ${selected.depth} 层先修` }}
        </text>
        <text
          v-if="selected.asked_count !== null && selected.asked_count !== undefined"
          class="sheet-depth"
        >答对 {{ correctCount(selected) }}/{{ selected.asked_count }}，错 {{ selected.wrong_count || 0 }} 题</text>
        <view class="sheet-actions">
          <button class="sheet-btn primary" @click="openWrong(selected)">看错题</button>
          <button class="sheet-btn" @click="retest(selected)">再测这个点</button>
          <button class="sheet-btn" @click="learn(selected)">去学习</button>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { getDiagnosisGraph } from '../../api.js'
import { store } from '../../store.js'
import { themeVars, isDark } from '../../theme/theme.js'

const GRADE_LABELS = {
  1: '一年级', 2: '二年级', 3: '三年级', 4: '四年级', 5: '五年级',
  6: '六年级', 7: '七年级', 8: '八年级', 9: '九年级',
  10: '高一', 11: '高二', 12: '选必一', 13: '选必二', 14: '选必三',
}

const statusText = {
  proficient: '熟练',
  mastered: '掌握',
  unstable: '不稳',
  weak: '薄弱',
}

const loggedIn = computed(() => !!(store.auth.user && store.auth.token))
const nodes = ref([])
const edges = ref([])
const loading = ref(true)
const error = ref('')
const expanded = ref(false)
const maxDepth = ref(0)
const selected = ref(null)
const nodeKey = ref('')
const nodeKeys = ref([])
const sessionId = ref('')

const EDGE_LIMIT_EXPANDED = 40
const EDGE_LIMIT_COLLAPSED = 12

const nodeById = computed(() => {
  const map = {}
  nodes.value.forEach((node) => (map[node.id] = node))
  return map
})

const depthLimit = computed(() =>
  expanded.value ? maxDepth.value : Math.min(1, maxDepth.value)
)

const layers = computed(() => {
  const byDepth = new Map()
  nodes.value.forEach((node) => {
    if (node.depth > depthLimit.value) return
    if (!byDepth.has(node.depth)) byDepth.set(node.depth, [])
    byDepth.get(node.depth).push(node)
  })
  return Array.from(byDepth.entries())
    .sort((a, b) => b[0] - a[0])
    .map(([depth, items]) => ({
      depth,
      title: depth === 0 ? '错题 / 薄弱知识点' : `先修第 ${depth} 层`,
      nodes: items,
    }))
})

const hiddenNodeCount = computed(
  () => nodes.value.filter((node) => node.depth > depthLimit.value).length
)

onLoad((query) => {
  if (query && query.node_key) nodeKey.value = String(query.node_key)
  if (query && query.node_keys) {
    nodeKeys.value = String(query.node_keys)
      .split(',')
      .map((key) => key.trim())
      .filter(Boolean)
  }
  if (query && query.session_id) sessionId.value = String(query.session_id)
  load()
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const params = { depth: 2 }
    if (sessionId.value) params.session_id = sessionId.value
    if (nodeKeys.value.length) params.node_keys = nodeKeys.value
    else if (nodeKey.value) params.node_keys = nodeKey.value
    const data = await getDiagnosisGraph(params)
    nodes.value = data.nodes || []
    edges.value = data.edges || []
    maxDepth.value = nodes.value.reduce(
      (max, node) => Math.max(max, node.depth || 0),
      0
    )
    // 节点过多时默认只展示种子 + 1 层先修。
    expanded.value = nodes.value.length <= 24
  } catch (err) {
    error.value = err.message || '图谱加载失败'
  } finally {
    loading.value = false
  }
}

function nameOf(nodeId) {
  const node = nodeById.value[nodeId]
  return node ? node.name : nodeId
}

function statusClass(node) {
  if (node.mastery_level === 'proficient') return 'proficient'
  if (node.status === 'mastered') return 'mastered'
  if (node.status === 'unstable') return 'unstable'
  if (node.status === 'weak') return 'weak'
  return 'untested'
}

function statusLabel(node) {
  return statusText[statusClass(node)] || '未测'
}

function correctCount(node) {
  const asked = Number(node.asked_count) || 0
  const wrong = Number(node.wrong_count) || 0
  return Math.max(0, asked - wrong)
}

function visibleEdges(depth) {
  const limit = expanded.value ? EDGE_LIMIT_EXPANDED : EDGE_LIMIT_COLLAPSED
  return edges
    .value.filter((edge) => {
      const source = nodeById.value[edge.source]
      const target = nodeById.value[edge.target]
      return (
        source &&
        target &&
        source.depth === depth &&
        target.depth < depth &&
        target.depth <= depthLimit.value
      )
    })
    .slice(0, limit)
}

function hiddenEdgeCount(depth) {
  const total = edges.value.filter((edge) => {
    const source = nodeById.value[edge.source]
    const target = nodeById.value[edge.target]
    return (
      source &&
      target &&
      source.depth === depth &&
      target.depth < depth &&
      target.depth <= depthLimit.value
    )
  }).length
  return Math.max(0, total - visibleEdges(depth).length)
}

function selectNode(node) {
  selected.value = node
}

function openWrong(node) {
  if (!loggedIn.value) {
    uni.navigateTo({ url: '/pages/auth/auth' })
    return
  }
  selected.value = null
  uni.navigateTo({
    url: `/pages/wrong/wrong?node_key=${encodeURIComponent(node.id)}`,
  })
}

function retest(node) {
  selected.value = null
  uni.navigateTo({
    url: `/pages/diagnosis/diagnosis?node_key=${encodeURIComponent(node.id)}&auto=1`,
  })
}

function learn(node) {
  selected.value = null
  uni.reLaunch({ url: '/pages/index/index' })
}

function gradeLabel(grade) {
  return GRADE_LABELS[grade] || '—'
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

.legend,
.edge-legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  padding: 16rpx 20rpx;
  margin-bottom: 12rpx;
  background: var(--ik-card);
  border-radius: 14rpx;
}

.legend-item {
  display: flex;
  align-items: center;
  margin-right: 26rpx;
  font-size: 21rpx;
  color: var(--ik-t2);
}

.dot {
  width: 18rpx;
  height: 18rpx;
  border-radius: 50%;
  margin-right: 8rpx;
}

.dot.weak { background: var(--ik-danger); }
.dot.unstable { background: #d69e2e; }
.dot.mastered { background: var(--ik-success); }
.dot.proficient { background: #1d6b45; }
.dot.untested { background: var(--ik-t3); }

.line {
  width: 48rpx;
  height: 0;
  margin-right: 10rpx;
  border-top: 3rpx solid var(--ik-t1);
}

.line.soft {
  border-top-style: dashed;
  border-top-color: var(--ik-t3);
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

.graph-hint {
  display: block;
  margin: 8rpx 4rpx 18rpx;
  font-size: 22rpx;
  color: var(--ik-t3);
}

.layer {
  margin-bottom: 22rpx;
}

.layer-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 10rpx;
}

.layer-title {
  font-size: 26rpx;
  font-weight: 600;
  color: var(--ik-t1);
}

.layer-count {
  font-size: 20rpx;
  color: var(--ik-t3);
}

.node-scroll {
  white-space: nowrap;
}

.node-row {
  display: inline-flex;
  padding: 4rpx 0 10rpx;
}

.node {
  display: inline-flex;
  flex-direction: column;
  justify-content: center;
  width: 210rpx;
  min-height: 116rpx;
  padding: 14rpx 18rpx;
  margin-right: 14rpx;
  border-radius: 14rpx;
  background: var(--ik-card);
  border-left: 8rpx solid var(--ik-t3);
  box-sizing: border-box;
}

.node.weak {
  border-left-color: var(--ik-danger);
  background: var(--ik-danger-weak);
}

.node.unstable {
  border-left-color: #d69e2e;
  background: var(--ik-warn-weak);
}

.node.mastered {
  border-left-color: var(--ik-success);
  background: var(--ik-success-weak);
}

.node.proficient {
  border-left-color: #1d6b45;
  background: var(--ik-success-weak);
}

.node-name {
  font-size: 24rpx;
  font-weight: 600;
  line-height: 1.4;
  color: var(--ik-t1);
  white-space: normal;
}

.node-meta {
  margin-top: 6rpx;
  font-size: 19rpx;
  color: var(--ik-t3);
}

.edges {
  margin-top: 8rpx;
  padding: 12rpx 16rpx;
  background: var(--ik-card);
  border-radius: 12rpx;
}

.edge-row {
  display: flex;
  align-items: center;
  padding: 8rpx 0;
}

.edge-label {
  flex-shrink: 0;
  max-width: 220rpx;
  font-size: 20rpx;
  color: var(--ik-t2);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.edge-line {
  flex: 1;
  height: 0;
  margin: 0 12rpx;
  border-top: 3rpx solid var(--ik-t1);
}

.edge-line.soft {
  border-top-style: dashed;
  border-top-color: var(--ik-t3);
}

.edge-more {
  display: block;
  margin-top: 6rpx;
  font-size: 19rpx;
  color: var(--ik-t3);
}

.expand {
  margin: 20rpx 0 40rpx;
}

.primary {
  background: var(--ik-primary);
  color: var(--ik-on-primary);
  border-radius: 14rpx;
  font-size: 27rpx;
}

.ghost {
  background: var(--ik-card);
  color: var(--ik-primary);
  border: 2rpx solid var(--ik-line);
  border-radius: 14rpx;
  font-size: 27rpx;
}

.sheet-mask {
  position: fixed;
  left: 0;
  right: 0;
  top: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.42);
  display: flex;
  align-items: flex-end;
  z-index: 20;
}

.sheet {
  width: 100%;
  background: var(--ik-card);
  border-radius: 24rpx 24rpx 0 0;
  padding: 30rpx 28rpx 48rpx;
  box-sizing: border-box;
}

.sheet-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.sheet-title {
  flex: 1;
  font-size: 32rpx;
  font-weight: 700;
  color: var(--ik-t1);
}

.status-pill {
  flex-shrink: 0;
  padding: 4rpx 16rpx;
  border-radius: 999rpx;
  font-size: 21rpx;
  background: var(--ik-soft);
  color: var(--ik-t3);
}

.status-pill.weak {
  background: var(--ik-danger-weak);
  color: var(--ik-danger);
}

.status-pill.unstable {
  background: var(--ik-warn-weak);
  color: var(--ik-warn-strong);
}

.status-pill.mastered,
.status-pill.proficient {
  background: var(--ik-success-weak);
  color: var(--ik-success);
}

.sheet-meta {
  display: block;
  margin-top: 12rpx;
  font-size: 23rpx;
  color: var(--ik-t3);
}

.sheet-depth {
  display: block;
  margin-top: 6rpx;
  font-size: 21rpx;
  color: var(--ik-t3);
}

.sheet-actions {
  margin-top: 26rpx;
}

.sheet-btn {
  background: var(--ik-soft);
  color: var(--ik-t2);
  border-radius: 14rpx;
  font-size: 27rpx;
  margin-bottom: 14rpx;
}

.sheet-btn.primary {
  background: var(--ik-primary);
  color: var(--ik-on-primary);
}

.footer-note {
  padding: 12rpx 8rpx 40rpx;
  text-align: center;
  font-size: 19rpx;
  line-height: 1.6;
  color: var(--ik-t3);
}
</style>
