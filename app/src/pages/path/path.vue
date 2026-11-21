<template>
  <view class="map-page theme-root" :style="themeVars">
    <ThemeBackground />
    <!-- 顶部信息栏 -->
    <view class="map-header">
      <view class="header-left">
        <text class="header-icon">🗺️</text>
        <view class="header-text">
          <text class="header-title">{{ body || '知识探险' }}</text>
          <text class="header-sub">{{ store.source || '数学' }}</text>
          <view class="progress-bar-wrap">
            <view class="progress-bar">
              <view class="progress-fill" :style="{ width: progressPercent + '%' }"></view>
            </view>
            <text class="progress-text">已点亮 {{ exploredCount }}/{{ totalNodes }}</text>
            <button class="reset-btn" @click="resetProgress">重置</button>
          </view>
        </view>
      </view>
      <view class="header-right">
        <button class="notebook-btn" @click="showNotebook = !showNotebook">
          📓 笔记本<text class="badge" v-if="notebook.length">{{ notebook.length }}</text>
        </button>
        <text class="auth-link" @click="goAuth">{{ store.auth.user ? '账号' : '登录' }}</text>
      </view>
    </view>

    <!-- 地图画布区域 -->
    <scroll-view class="map-canvas" scroll-x scroll-y :scroll-top="scrollTop" :scroll-left="scrollLeft">
      <view class="canvas-inner" :style="{ width: canvasWidth + 'px', height: canvasHeight + 'px' }">
        
        <!-- SVG 连线层 -->
        <svg class="links-layer" :viewBox="`0 0 ${canvasWidth} ${canvasHeight}`">
          <defs>
            <marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
              <path d="M0,0 L0,6 L8,3 z" fill="#b8a37c"/>
            </marker>
            <marker id="arrow-active" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
              <path d="M0,0 L0,6 L8,3 z" fill="#c97b4a"/>
            </marker>
          </defs>
          <path v-for="(link, idx) in visibleLinks" :key="'link-'+idx"
            :d="link.d" 
            class="link-path" 
            :class="{ 'link-active': link.active, 'link-done': link.done }"
            :marker-end="link.direct ? '#arrow' : undefined"/>
        </svg>

        <!-- 节点层 -->
        <view 
          v-for="node in visibleNodes" 
          :key="node.id"
          class="map-node" 
          :class="[`node-${node.kind}`, `state-${getNodeState(node)}`, { 'node-active': activeNode && activeNode.id === node.id }]"
          :style="{ left: node.x + 'px', top: node.y + 'px' }"
          @click="onNodeClick(node)"
        >
          <view class="node-disc"></view>
          <text class="node-emoji">{{ node.emoji }}</text>
          <text class="node-label">{{ node.name }}</text>
          <view v-if="!isExplored(node) && node.kind !== 'next'" class="node-badge badge-hint">💡</view>
          <view v-if="isExplored(node) && hasUnexploredChildren(node)" class="node-badge badge-more">!</view>
          <view v-if="isCompleted(node)" class="node-check">✓</view>
          <view v-if="isMastered(node)" class="node-master">🏆</view>
        </view>
      </view>
    </scroll-view>

    <!-- 内容卡片（点击节点后弹出） -->
    <view v-if="activeNode" class="card-overlay" @click.self="activeNode = null">
      <view class="content-card" :class="{ 'card-show': cardVisible }">
        <view class="card-tail"></view>
        <view class="card-header">
          <text class="card-emoji">{{ activeNode.emoji }}</text>
          <view class="card-title-area">
            <text class="card-kind">{{ activeNode.kindLabel }}</text>
            <text class="card-name">{{ activeNode.name }}</text>
          </view>
          <text class="card-close" @click="activeNode = null">×</text>
        </view>
        
        <view class="card-body">
          <!-- 加载中状态 -->
          <view v-if="loadingDetail" class="loading-state">
            <text class="loading-icon">⏳</text>
            <text class="loading-text">正在加载知识点内容...</text>
          </view>

          <template v-else>
            <!-- 知识点定义（从API获取） -->
            <view class="card-section" v-if="detailData.definition">
              <text class="section-title">📖 知识点定义</text>
              <MathText class="definition-text" :text="detailData.definition" />
            </view>

            <!-- 重要性说明 -->
            <view class="card-section" v-if="detailData.importance">
              <text class="section-title">💡 为什么重要</text>
              <MathText class="section-text importance-text" :text="detailData.importance" />
            </view>

            <!-- 教材页码 -->
            <view class="card-section" v-if="detailData.pages">
              <text class="section-title">📚 教材位置</text>
              <text class="section-text">第 {{ detailData.pages }} 页</text>
            </view>

            <!-- 例子 -->
            <view class="card-section" v-if="detailData.examples && detailData.examples.length">
              <text class="section-title">📝 学习示例</text>
              <view v-for="(example, i) in detailData.examples" :key="i" class="example-item">
                <MathText class="example-content" :text="typeof example === 'string' ? example : example.content || example" />
              </view>
            </view>

            <!-- 目标说明（通用） -->
            <view class="card-section">
              <text class="section-title">🎯 本关目标</text>
              <text class="section-text">{{ getGoalText(activeNode) }}</text>
            </view>

            <!-- ========== 验收测试区 ========== -->
            <view class="card-section quiz-section" v-if="canQuiz(activeNode)">
              <text class="section-title">⚔️ 掌握度验收</text>
              <text class="quiz-hint">完成以下练习来证明你已掌握此知识点：</text>
              
              <!-- 练习列表 -->
              <view class="quiz-list">
                <view v-for="(q, i) in currentQuiz" :key="i" class="quiz-item" :class="{ 'quiz-correct': quizAnswers[i] === true, 'quiz-wrong': quizAnswers[i] === false }">
                  <view class="quiz-q">
                    <text class="quiz-num">{{ i + 1 }}</text>
                    <MathText class="quiz-stem" :text="q.stem || q.name || q" inline />
                  </view>
                  
                  <!-- 选项（如果是选择题） -->
                  <view v-if="q.options && q.options.length" class="quiz-options">
                    <view 
                      v-for="(opt, oi) in q.options" :key="oi"
                      class="quiz-option"
                      :class="{ 
                        'option-selected': selectedOptions[i] === oi,
                        'option-correct': showAnswer && oi === q.answer,
                        'option-wrong': showAnswer && selectedOptions[i] === oi && oi !== q.answer
                      }"
                      @click="selectOption(i, oi)"
                    >
                      <text class="option-letter">{{ ['A','B','C','D'][oi] }}</text>
                      <MathText class="option-text" :text="opt" inline />
                    </view>
                  </view>
                  
                  <!-- 填空题/简答题的输入框 -->
                  <view v-else class="quiz-input-wrap">
                    <textarea 
                      class="quiz-input quiz-textarea" 
                      v-model="quizAnswers[i]" 
                      placeholder="输入你的答案..."
                      :disabled="showAnswer"
                      :auto-height="true"
                      :maxlength="200"
                    ></textarea>
                  </view>

                  <!-- 解析（显示答案后） -->
                  <view v-if="showAnswer" class="quiz-analysis">
                    <text class="analysis-label">📋 参考答案</text>
                    <MathText class="analysis-text" :text="q.answer || '见解析'" />
                    <MathText v-if="q.analysis" class="analysis-detail" :text="q.analysis" />
                  </view>
                </view>
              </view>

              <!-- 操作按钮 -->
              <view class="action-row" v-if="!isMastered(activeNode)">
                <button v-if="!showAnswer" class="btn btn-submit" @click="submitQuiz" :disabled="!canSubmitQuiz">
                  提交答案
                </button>
                <button v-else class="btn btn-retry" @click="retryQuiz">
                  重新作答
                </button>
                <button 
                  v-if="showAnswer && quizPassed" 
                  class="btn btn-pass" 
                  @click="masterNode(activeNode)"
                >
                  🏆 确认掌握
                </button>
              </view>

              <!-- 通过/未通过提示 -->
              <view v-if="showAnswer" class="quiz-result" :class="{ 'result-pass': quizPassed, 'result-fail': !quizPassed }">
                <text v-if="quizPassed" class="result-text">🎉 太棒了！你已经掌握了这个知识点！</text>
                <text v-else class="result-text">💪 还需要再接再厉！可以查看解析后重新尝试。</text>
              </view>
            </view>

            <!-- 已掌握状态 -->
            <view class="mastered-banner" v-if="isMastered(activeNode)">
              <text class="mastered-icon">🏆</text>
              <view class="mastered-info">
                <text class="mastered-title">已掌握此知识点</text>
                <text class="mastered-time">掌握时间：{{ masteredTime(activeNode) }}</text>
              </view>
            </view>

            <!-- 无练习时的手动完成按钮 -->
            <view class="card-section" v-if="activeNode.kind === 'target' && (!currentQuiz || !currentQuiz.length) && !isMastered(activeNode)">
              <text class="section-title">✅ 完成挑战</text>
              <text class="section-text">该知识点暂无配套练习，你可以通过对话中的题目来检验学习效果。</text>
              <button class="btn btn-pass" @click="completeNode(activeNode)">标记为已完成</button>
            </view>

            <!-- 前置/后续提示 -->
            <view class="card-section" v-if="activeNode.kind !== 'target'">
              <text class="section-title">{{ activeNode.kind === 'pre' ? '🔑 解锁条件' : '🌟 后续探索' }}</text>
              <text class="section-text">{{ activeNode.kind === 'pre' ? '掌握此基础知识后，主线关卡将更容易理解。' : '完成当前目标后，可以继续挑战这些延伸知识。' }}</text>
            </view>
          </template>
        </view>

        <view class="card-footer">
          <text class="footer-status">
            <text v-if="isMastered(activeNode)" class="status-mastered">🏆 已掌握</text>
            <text v-else-if="isCompleted(activeNode)" class="status-done">✓ 已通关</text>
            <text v-else-if="activeNode.kind === 'target'" class="status-current">⚔️ 当前挑战</text>
            <text v-else class="status-preview">👁 可预览</text>
          </text>
        </view>
      </view>
    </view>

    <!-- 笔记本侧边栏 -->
    <view class="notebook-panel" :class="{ 'panel-open': showNotebook }">
      <view class="notebook-header">
        <text class="notebook-title">📓 知识笔记本</text>
        <text class="notebook-close" @click="showNotebook = false">×</text>
      </view>
      <input class="notebook-search" v-model="notebookFilter" placeholder="搜索已收集的概念..." />
      <scroll-view class="notebook-list" scroll-y>
        <view v-if="filteredNotebook.length === 0" class="notebook-empty">
          <text>还没有收集任何概念</text>
          <text class="empty-hint">点击地图上的圆圈开始探索吧！</text>
        </view>
        <view v-for="(item, i) in filteredNotebook" :key="i" class="notebook-item" @click="goToNotebookItem(item)">
          <text class="item-name">{{ item.name }}</text>
          <MathText class="item-explain" :text="item.explain" />
          <text v-if="item.mastered" class="item-mastered">🏆 已掌握</text>
        </view>
      </scroll-view>
    </view>
    <view v-if="showNotebook" class="notebook-mask" @click="showNotebook = false"></view>

    <!-- Toast 提示 -->
    <view class="toast-container">
      <view v-for="(toast, i) in toasts" :key="i" class="toast" :class="{ 'toast-show': toast.show }">
        <text class="toast-emoji">{{ toast.emoji }}</text>
        <text class="toast-text">{{ toast.text }}</text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { computed, ref, watch, nextTick } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { askQuestion, attachmentAction, attachmentContent, attachmentStatus, deleteAttachment, listMessages, listVideos, transcribeAudio, uploadAttachment, getKnowledgeDetail, checkAnswer } from '../../api.js'
import { store } from '../../store.js'
import { themeVars, applyNativeNavigationBar } from '../../theme/theme.js'
import { formatDuration, buildBilibiliMobileUrl } from '../../video.js'
import MathText from '../../components/ui/MathText.vue'

// ==================== 数据源 ====================
const lp = computed(() => store.learningPath || { prerequisites: [], body: '', consolidation: [] })
const body = computed(() => lp.value.body || store.knowledgePoint || '')
const bodyId = computed(() => lp.value.body_id || body.value)
const prerequisites = computed(() => lp.value.prerequisites || [])
const prerequisiteIds = computed(() => lp.value.prerequisite_ids || [])
const consolidation = computed(() => lp.value.consolidation || [])
const consolidationIds = computed(() => lp.value.consolidation_ids || [])
const exercises = computed(() => lp.value.exercises || [])
const solutionText = computed(() => {
  const steps = lp.value.steps
  if (Array.isArray(steps)) return steps.map((s, i) => `${i+1}. ${typeof s === 'string' ? s : s.content || ''}`).join('\n')
  return String(steps || '')
})

// ==================== 状态管理 ====================
const explored = ref({})       // { nodeId: true }
const completed = ref({})     // { nodeId: true }
const mastered = ref({})       // { nodeId: timestamp }
const activeNode = ref(null)
const cardVisible = ref(false)
const showAnswer = ref(false)
const showNotebook = ref(false)
const notebookFilter = ref('')
const toasts = ref([])
const scrollTop = ref(0)
const scrollLeft = ref(0)

// 详情数据（从API加载）
const detailData = ref({})
const loadingDetail = ref(false)

// 验收测试相关
const currentQuiz = ref([])
const quizAnswers = ref({})   // { questionIndex: answer }
const selectedOptions = ref({}) // { questionIndex: optionIndex }
const quizPassed = ref(false)

// 笔记本数据
const notebook = ref([])

// 进度存储键
const progressKey = computed(() => {
  const uid = store.auth.user?.id || 'guest'
  return `learning_map_v3:${uid}:${body.value}`
})

function loadProgress() {
  try {
    const data = uni.getStorageSync(progressKey.value) || {}
    explored.value = data.explored || {}
    completed.value = data.completed || {}
    mastered.value = data.mastered || {}
    notebook.value = data.notebook || []
  } catch(e) {
    explored.value = {}
    completed.value = {}
    mastered.value = {}
    notebook.value = []
  }
}

function saveProgress() {
  try {
    uni.setStorageSync(progressKey.value, { explored: explored.value, completed: completed.value, mastered: mastered.value, notebook: notebook.value })
  } catch(e) {}
}

// ==================== 学习路径持久化 ====================
const LP_STORAGE_KEY = 'learningPath_cache'

// 保存学习路径到本地存储
function saveLearningPathToStorage() {
  try {
    if (store.learningPath) {
      uni.setStorageSync(LP_STORAGE_KEY, {
        data: store.learningPath,
        knowledgePoint: store.knowledgePoint,
        source: store.source,
        timestamp: Date.now()
      })
      console.log('[Path] 学习路径已缓存')
    }
  } catch(e) {
    console.warn('[Path] 缓存学习路径失败:', e)
  }
}

// 从本地存储恢复学习路径
function restoreLearningPathFromStorage() {
  try {
    const cached = uni.getStorageSync(LP_STORAGE_KEY)
    if (cached && cached.data) {
      // 只有当 store 中没有数据时才恢复
      if (!store.learningPath) {
        store.learningPath = cached.data
        if (cached.knowledgePoint) store.knowledgePoint = cached.knowledgePoint
        if (cached.source) store.source = cached.source
        console.log('[Path] 从缓存恢复学习路径:', cached.data.body)
        return true
      }
    }
  } catch(e) {
    console.warn('[Path] 恢复学习路径失败:', e)
  }
  return false
}

// 监听 learningPath 变化，自动缓存
watch(() => store.learningPath, (newVal) => {
  if (newVal) {
    saveLearningPathToStorage()
  }
}, { immediate: true })

// ==================== 页面生命周期 ====================
// 每次页面显示时重新加载进度，并检查学习路径数据
onShow(() => {
  applyNativeNavigationBar()
  loadProgress()
  
  // 如果没有学习路径数据，尝试从缓存恢复
  if (!store.learningPath && !body.value) {
    const restored = restoreLearningPathFromStorage()
    if (!restored) {
      console.log('[Path] 等待学习路径数据...')
    }
  }
})

// ==================== 节点数据构建 ====================
const NODE_CONFIG = {
  pre: { emoji: '📚', kindLabel: '前置知识', color: '#5b8c5a' },
  target: { emoji: '⚔️', kindLabel: '主线关卡', color: '#c97b4a' },
  next: { emoji: '🌟', kindLabel: '延伸挑战', color: '#7b6bc9' }
}

const allNodes = computed(() => {
  const nodes = []
  
  // 前置知识节点 - 优先使用prerequisite_ids中的真实ID
  prerequisites.value.forEach((name, i) => {
    const n = typeof name === 'object' ? name : { name }
    const realId = prerequisiteIds.value[i] || n.id || undefined
    nodes.push({
      id: `pre-${i}-${n.name || i}`,
      rawName: n.name || String(name),
      name: n.name || String(name),
      kind: 'pre',
      ...NODE_CONFIG.pre,
      level: 0,
      index: i,
      nodeId: realId, // 使用真实的知识点ID
    })
  })
  
  // 主线目标节点 - 使用body_id
  if (body.value) {
    nodes.push({
      id: `target-${body.value}`,
      rawName: body.value,
      name: body.value,
      kind: 'target',
      ...NODE_CONFIG.target,
      level: 1,
      index: prerequisites.value.length,
      nodeId: bodyId.value, // 使用真实的知识点ID
    })
  }
  
  // 后续延伸节点 - 优先使用consolidation_ids中的真实ID
  consolidation.value.forEach((name, i) => {
    const n = typeof name === 'object' ? name : { name }
    const realId = consolidationIds.value[i] || n.id || undefined
    nodes.push({
      id: `next-${i}-${n.name || i}`,
      rawName: n.name || String(name),
      name: n.name || String(name),
      kind: 'next',
      ...NODE_CONFIG.next,
      level: 2,
      index: prerequisites.value.length + 1 + i,
      nodeId: realId, // 使用真实的知识点ID
    })
  })
  
  return nodes
})

const totalNodes = computed(() => allNodes.value.length)
const exploredCount = computed(() => Object.keys(explored.value).length)
const progressPercent = computed(() => {
  if (totalNodes.value === 0) return 0
  return Math.round((exploredCount.value / totalNodes.value) * 100)
})

// ==================== 布局计算 ====================
const CANVAS_PADDING = 80
const NODE_SIZE = 100
const LEVEL_GAP = 180
const SIBLING_GAP = 140

const canvasWidth = computed(() => {
  const maxPerLevel = Math.max(
    prerequisites.value.length || 1,
    1,
    consolidation.value.length || 1
  )
  return maxPerLevel * SIBLING_GAP + CANVAS_PADDING * 2
})

const canvasHeight = computed(() => {
  return LEVEL_GAP * 2 + CANVAS_PADDING * 2 + NODE_SIZE
})

// 计算每个节点的位置
const positionedNodes = computed(() => {
  const pres = allNodes.value.filter(n => n.kind === 'pre')
  const target = allNodes.value.find(n => n.kind === 'target')
  const nexts = allNodes.value.filter(n => n.kind === 'next')
  
  const result = []
  const centerX = canvasWidth.value / 2
  const startY = CANVAS_PADDING + 60
  
  // 前置节点：分布在上方，交错排列
  pres.forEach((node, i) => {
    const count = pres.length
    const offsetX = (i - (count - 1) / 2) * SIBLING_GAP
    result.push({
      ...node,
      x: centerX + offsetX - NODE_SIZE / 2,
      y: startY - NODE_SIZE / 2
    })
  })
  
  // 目标节点：居中
  if (target) {
    result.push({
      ...target,
      x: centerX - NODE_SIZE / 2,
      y: startY + LEVEL_GAP - NODE_SIZE / 2
    })
  }
  
  // 后续节点：分布在下方
  nexts.forEach((node, i) => {
    const count = nexts.length
    const offsetX = (i - (count - 1) / 2) * SIBLING_GAP
    result.push({
      ...node,
      x: centerX + offsetX - NODE_SIZE / 2,
      y: startY + LEVEL_GAP * 2 - NODE_SIZE / 2
    })
  })
  
  return result
})

const visibleNodes = computed(() => positionedNodes.value)

// 计算连线
const visibleLinks = computed(() => {
  const links = []
  const nodes = positionedNodes.value
  const target = nodes.find(n => n.kind === 'target')
  const pres = nodes.filter(n => n.kind === 'pre')
  const nexts = nodes.filter(n => n.kind === 'next')
  
  // 前置 -> 目标 的连线
  pres.forEach(pre => {
    if (target) {
      links.push({
        from: pre, to: target,
        d: makeCurvePath(pre, target),
        done: isExplored(pre) && isExplored(target),
        active: (activeNode.value && (activeNode.value.id === pre.id || activeNode.value.id === target.id)),
        direct: pres.length === 1
      })
    }
  })
  
  // 目标 -> 后续 的连线
  if (target) {
    nexts.forEach(nxt => {
      links.push({
        from: target, to: nxt,
        d: makeCurvePath(target, nxt),
        done: isExplored(target) && isExplored(nxt),
        active: (activeNode.value && (activeNode.value.id === target.id || activeNode.value.id === nxt.id)),
        direct: nexts.length === 1
      })
    })
  }
  
  return links
})

// 生成曲线路径
function makeCurvePath(from, to) {
  const x1 = from.x + NODE_SIZE / 2
  const y1 = from.y + NODE_SIZE / 2
  const x2 = to.x + NODE_SIZE / 2
  const y2 = to.y + NODE_SIZE / 2
  const mx = (x1 + x2) / 2
  const my = (y1 + y2) / 2
  
  const dx = x2 - x1
  const sign = dx >= 0 ? 1 : -1
  const offset = Math.abs(y2 - y1) * 0.3 * sign
  
  return `M ${x1} ${y1} Q ${mx + offset} ${my}, ${x2} ${y2}`
}

// ==================== 节点状态判断 ====================
function isExplored(node) { return !!explored.value[node.id] }
function isCompleted(node) { return !!completed.value[node.id] }
function isMastered(node) { return !!mastered.value[node.id] }
function getNodeState(node) {
  if (isMastered(node)) return 'mastered'
  if (isCompleted(node)) return 'done'
  if (isExplored(node)) return 'visited'
  if (node.kind === 'target') return 'current'
  return 'locked'
}
function hasUnexploredChildren(node) {
  if (node.kind === 'pre') {
    return !isExplored(allNodes.value.find(n => n.kind === 'target'))
  }
  if (node.kind === 'target') {
    return allNodes.value.some(n => n.kind === 'next' && !isExplored(n))
  }
  return false
}

// ==================== 交互处理 ====================
async function onNodeClick(node) {
  // 点击同一个节点 = 关闭卡片
  if (activeNode.value && activeNode.value.id === node.id) {
    activeNode.value = null
    cardVisible.value = false
    return
  }
  
  // 首次探索该节点
  if (!isExplored(node)) {
    explored.value = { ...explored.value, [node.id]: true }
    
    // 添加到笔记本
    addToNotebook(node)
    
    // 显示 Toast
    showToast(`解锁了「${node.name}」`, node.emoji)
    
    saveProgress()
  }
  
  activeNode.value = node
  showAnswer.value = false
  quizAnswers.value = {}
  selectedOptions.value = {}
  quizPassed.value = false
  
  // 加载知识点详情
  await loadNodeDetail(node)
  
  // 动画显示卡片
  nextTick(() => {
    cardVisible.value = true
  })
  
  // 滚动到节点位置
  scrollToNode(node)
}

// 加载节点详情
async function loadNodeDetail(node) {
  detailData.value = {}
  loadingDetail.value = true
  currentQuiz.value = []
  
  try {
    // 尝试用nodeId请求，如果没有则用名称
    let nodeId = node.nodeId || node.rawName
    
    // 清理ID中的特殊字符，尝试匹配图谱中的格式
    if (nodeId && !nodeId.startsWith('math_')) {
      // 可能是显示名称，先尝试直接用
    }
    
    const data = await getKnowledgeDetail(nodeId)
    detailData.value = data || {}
    
    // 设置练习题（优先使用API返回的，其次使用learningPath中的）
    if (data.exercises && data.exercises.length > 0) {
      currentQuiz.value = data.exercises.slice(0, 5) // 最多5道题
    } else if (node.kind === 'target' && exercises.value.length > 0) {
      // 使用learningPath中的练习
      currentQuiz.value = exercises.value.map((ex, i) => ({
        id: `lp-ex-${i}`,
        stem: ex,
        name: `练习${i+1}`,
        answer: '',
        options: [], // 简答题没有选项
      }))
    }
    
  } catch (error) {
    console.warn('加载知识点详情失败:', error)
    detailData.value = {}
    
    // 如果API失败，使用learningPath中的练习作为备选
    if (node.kind === 'target' && exercises.value.length > 0) {
      currentQuiz.value = exercises.value.map((ex, i) => ({
        id: `lp-ex-${i}`,
        stem: ex,
        name: `练习${i+1}`,
        answer: '',
        options: [],
      }))
    }
  } finally {
    loadingDetail.value = false
  }
}

// ==================== 验收测试逻辑 ====================
function canQuiz(node) {
  // 目标节点和前置节点都可以测试（如果有练习的话）
  return currentQuiz.value.length > 0 && !isMastered(node)
}

const canSubmitQuiz = computed(() => {
  // 检查是否所有题目都已回答
  if (!currentQuiz.value.length) return false
  for (let i = 0; i < currentQuiz.value.length; i++) {
    const q = currentQuiz.value[i]
    if (q.options && q.options.length > 0) {
      // 选择题：必须选择了选项
      if (selectedOptions.value[i] === undefined || selectedOptions.value[i] === null) return false
    } else {
      // 填空题/简答题：必须有内容
      if (!quizAnswers.value[i]) return false
    }
  }
  return true
})

function selectOption(questionIndex, optionIndex) {
  if (showAnswer.value) return // 已显示答案后不能修改
  selectedOptions.value = { ...selectedOptions.value, [questionIndex]: optionIndex }
  quizAnswers.value = { ...quizAnswers.value, [questionIndex]: currentQuiz.value[questionIndex].options[optionIndex] }
}

async function submitQuiz() {
  if (!canSubmitQuiz.value) {
    uni.showToast({ title: '请先完成所有题目', icon: 'none' })
    return
  }
  
  // 显示加载状态
  uni.showLoading({ title: '智能批改中...', mask: true })
  
  try {
    // 使用 API 智能校验每道题
    let correct = 0
    const results = []
    
    for (let i = 0; i < currentQuiz.value.length; i++) {
      const q = currentQuiz.value[i]
      
      if (q.options && q.options.length > 0) {
        // 选择题：直接比对
        if (selectedOptions.value[i] === getCorrectOptionIndex(q)) {
          correct++
          results.push(true)
        } else {
          results.push(false)
        }
      } else {
        // 填空题/简答题：调用智能校验 API
        const userAnswer = (quizAnswers.value[i] || '').trim()
        try {
          const res = await checkAnswer({
            question: q.stem || q.name || `第${i+1}题`,
            user_answer: userAnswer,
            correct_answer: q.answer || '',
            question_type: q.type || 'fill'
          })
          
          if (res.success && res.data.is_correct) {
            correct++
            results.push(true)
          } else {
            results.push(false)
          }
        } catch (err) {
          console.error('[Quiz] API校验失败，使用后备方案:', err)
          // 后备方案：简单的包含判断
          const userClean = userAnswer.toLowerCase()
          const correctClean = (q.answer || '').toLowerCase()
          if (userClean && correctClean && (
            userClean.includes(correctClean) || 
            correctClean.includes(userClean) ||
            userClean.replace(/\s/g, '') === correctClean.replace(/\s/g, '')
          )) {
            correct++
            results.push(true)
          } else {
            results.push(false)
          }
        }
      }
    }
    
    // 显示结果
    showAnswer.value = true  // 只在提交后才显示答案
    quizPassed.value = correct >= Math.ceil(currentQuiz.value.length * 0.6) // 60%及格
    
    if (quizPassed.value) {
      showToast(`答对 ${correct}/${currentQuiz.value.length} 题，太棒了！`, '🎉')
    } else {
      showToast(`答对 ${correct}/${currentQuiz.value.length} 题，继续加油！`, '💪')
    }
  } catch (error) {
    console.error('[Quiz] 提交失败:', error)
    uni.showToast({ title: '批改失败，请重试', icon: 'none' })
  } finally {
    uni.hideLoading()
  }
}

function getCorrectOptionIndex(q) {
  if (!q.options || !q.answer) return -1
  // answer可能是索引或实际值
  if (typeof q.answer === 'number') return q.answer
  const answerStr = String(q.answer).trim()
  const idx = q.options.findIndex(opt => String(opt).trim() === answerStr)
  return idx >= 0 ? idx : 0
}

function retryQuiz() {
  showAnswer.value = false
  quizAnswers.value = {}
  selectedOptions.value = {}
  quizPassed.value = false
}

function masterNode(node) {
  if (!node || isMastered(node)) return
  mastered.value = { ...mastered.value, [node.id]: Date.now() }
  completed.value = { ...completed.value, [node.id]: true } // 掌握也意味着完成
  saveProgress()
  showToast(`「${node.name}」已掌握！🏆`, '🏆')
  
  // 更新笔记本状态
  const item = notebook.value.find(it => it.nodeId === node.id)
  if (item) item.mastered = true
  
  // 自动高亮下一个未探索节点
  nextTick(() => {
    const next = findNextUnexplored()
    if (next) {
      setTimeout(() => onNodeClick(next), 800)
    }
  })
}

function completeNode(node) {
  if (!node || isCompleted(node)) return
  completed.value = { ...completed.value, [node.id]: true }
  saveProgress()
  showToast(`「${node.name}」挑战成功！🎉`, '🎉')
  
  nextTick(() => {
    const next = findNextUnexplored()
    if (next) {
      setTimeout(() => onNodeClick(next), 800)
    }
  })
}

function toggleAnswer() { showAnswer.value = !showAnswer.value }

function goToNode(node) {
  if (node) onNodeClick(node)
}

function findNextUnexplored() {
  return allNodes.value.find(n => !isExplored(n))
}

const prevNode = computed(() => {
  if (!activeNode.value) return null
  const idx = allNodes.value.findIndex(n => n.id === activeNode.value.id)
  return idx > 0 ? allNodes.value[idx - 1] : null
})

const nextUnexplored = computed(() => {
  if (!activeNode.value) return null
  const idx = allNodes.value.findIndex(n => n.id === activeNode.value.id)
  return allNodes.value.slice(idx + 1).find(n => !isMastered(n)) || null
})

function masteredTime(node) {
  const t = mastered.value[node.id]
  if (!t) return ''
  const d = new Date(t)
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
}

// ==================== 笔记本 ====================
function addToNotebook(node) {
  if (notebook.value.some(item => item.name === node.name)) return
  
  notebook.value = [...notebook.value, {
    id: node.id,
    name: node.name,
    explain: detailData.value.definition || getExplainText(node),
    kind: node.kindLabel,
    nodeId: node.id,
    mastered: !!mastered.value[node.id],
  }]
  saveProgress()
}

function getExplainText(node) {
  if (node.kind === 'pre') return `这是当前学习目标的前置知识，掌握它会让后续学习更顺畅。`
  if (node.kind === 'target') return `这是本次问答匹配到的核心知识点，是当前的学习重点。`
  return `这是目标知识的后续延伸，可以作为下一阶段的挑战方向。`
}

function getGoalText(node) {
  if (node.kind === 'pre') return `回顾并掌握「${node.name}」的基础知识，为攻克主线关卡做好准备。`
  if (node.kind === 'target') return `理解并掌握「${node.name}」的核心方法，完成练习挑战以巩固所学。`
  return `在掌握主线知识后，进一步探索「${node.name}」的延伸应用。`
}

const filteredNotebook = computed(() => {
  if (!notebookFilter.value) return notebook.value
  const q = notebookFilter.value.toLowerCase()
  return notebook.value.filter(item => 
    item.name.toLowerCase().includes(q) || 
    item.explain.toLowerCase().includes(q)
  )
})

function goToNotebookItem(item) {
  const node = allNodes.value.find(n => n.id === item.nodeId)
  if (node) {
    showNotebook.value = false
    onNodeClick(node)
  }
}

// ==================== Toast ====================
function showToast(text, emoji = '✨') {
  const id = Date.now() + Math.random()
  const toast = { id, text, emoji, show: false }
  toasts.value = [...toasts.value, toast]
  nextTick(() => {
    const idx = toasts.value.findIndex(t => t.id === id)
    if (idx >= 0) {
      toasts.value[idx].show = true
    }
  })
  setTimeout(() => {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }, 2500)
}

// ==================== 滚动定位 ====================
function scrollToNode(node) {
  if (!node) return
  const targetX = node.x - canvasWidth.value / 2 + NODE_SIZE / 2
  const targetY = node.y - 300
  scrollLeft.value = targetX
  scrollTop.value = targetY
}

// ==================== 工具函数 ====================
function goAuth() { uni.navigateTo({ url: '/pages/auth/auth' }) }

// 输入框聚焦处理（解决 scroll-view 内 input 无法点击的问题）
function onInputFocus(event, index) {
  console.log('[Quiz] 输入框聚焦:', index)
  // 延迟滚动到输入框位置，确保可见
  setTimeout(() => {
    // 可以在这里添加额外的滚动逻辑
  }, 100)
}

function resetProgress() {
  uni.showModal({
    title: '重置进度',
    content: '确定要清除当前知识点的所有探索记录吗？',
    success: (res) => {
      if (res.confirm) {
        explored.value = {}
        completed.value = {}
        mastered.value = {}
        notebook.value = []
        activeNode.value = null
        cardVisible.value = false
        saveProgress()
        showToast('进度已重置', '🔄')
      }
    }
  })
}

// ==================== 生命周期 ====================
watch(body, () => {
  loadProgress()
  activeNode.value = null
  cardVisible.value = false
}, { immediate: true })

onShow(loadProgress)
</script>

<style>
/* ========== 全局变量 ========== */
page { height: 100%; background: #f5ecd9; }

/* ========== 页面布局 ========== */
.map-page { 
  display: flex; flex-direction: column; 
  height: 100vh; overflow: hidden;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
  color: #4a3d2a;
}

/* ========== 顶部栏 ========== */
.map-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 20rpx 28rpx; background: #fdf6e6;
  border-bottom: 1rpx solid #d8c8a8;
  flex-shrink: 0; z-index: 10;
}
.header-left { display: flex; align-items: center; gap: 16rpx; min-width: 0; }
.header-icon { font-size: 40rpx; }
.header-text { display: flex; flex-direction: column; gap: 4rpx; min-width: 0; }
.header-title { font-size: 32rpx; font-weight: 700; color: #4a3d2a; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.header-sub { font-size: 22rpx; color: #8a7861; }

/* ========== 进度条 ========== */
.progress-bar-wrap {
  display: flex; align-items: center; gap: 14rpx;
  margin-top: 10rpx;
}
.progress-bar {
  flex: 1; height: 16rpx; min-width: 120rpx;
  background: #e8dcc5; border-radius: 8rpx;
  overflow: hidden;
}
.progress-fill {
  height: 100%; border-radius: 8rpx;
  background: linear-gradient(90deg, #c97b4a, #e8b994);
  transition: width 0.5s cubic-bezier(0.4, 0, 0.2, 1);
  min-width: 0;
}
.progress-text {
  flex-shrink: 0; font-size: 20rpx; color: #8a7861;
  white-space: nowrap;
}
.reset-btn {
  flex-shrink: 0; padding: 6rpx 20rpx;
  background: #fff; border: 1rpx solid #d8c8a8;
  border-radius: 20rpx; font-size: 20rpx; color: #8a7861;
  line-height: 1;
}
.reset-btn::after { border: none; }
.reset-btn:active { background: #f0e6d0; }

.header-right { display: flex; align-items: center; gap: 16rpx; flex-shrink: 0; }

.notebook-btn {
  display: flex; align-items: center; gap: 8rpx;
  padding: 12rpx 24rpx; background: #fff; border: 1rpx solid #d8c8a8;
  border-radius: 40rpx; font-size: 24rpx; color: #4a3d2a;
  line-height: 1;
}
.notebook-btn .badge {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 32rpx; height: 32rpx; padding: 0 8rpx;
  background: #c97b4a; color: #fff; border-radius: 50%;
  font-size: 20rpx; font-weight: 700;
}
.auth-link { color: #c97b4a; font-size: 24rpx; }

/* ========== 地图画布 ========== */
.map-canvas { 
  flex: 1; position: relative; overflow: hidden;
  background: 
    radial-gradient(circle at 30% 20%, rgba(201,123,74,0.06) 0%, transparent 50%),
    radial-gradient(circle at 70% 80%, rgba(91,140,90,0.05) 0%, transparent 50%),
    #f5ecd9;
}
.canvas-inner { position: relative; }

/* ========== SVG 连线 ========== */
.links-layer {
  position: absolute; top: 0; left: 0;
  width: 100%; height: 100%;
  pointer-events: none; z-index: 1;
}
.link-path {
  fill: none; stroke: #d8c8a8; stroke-width: 2;
  stroke-linecap: round;
  opacity: 0;
  animation: drawLine 0.6s ease forwards;
}
@keyframes drawLine {
  from { stroke-dasharray: 0 1000; opacity: 0; }
  to { stroke-dasharray: 1000 0; opacity: 1; }
}
.link-path.link-done { stroke: #b8a37c; stroke-width: 2.5; }
.link-path.link-active { stroke: #c97b4a; stroke-width: 3; }

/* ========== 节点 ========== */
.map-node {
  position: absolute; width: 100rpx; height: 100rpx;
  margin-left: -50rpx; margin-top: -50rpx;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  cursor: pointer; z-index: 5;
  transform: scale(0); opacity: 0;
  animation: nodeIn 0.5s cubic-bezier(0.34, 1.4, 0.64, 1) forwards;
}
@keyframes nodeIn {
  to { transform: scale(1); opacity: 1; }
}
.map-node.state-done .node-disc { 
  border-color: #5b8c5a; background: #eef6ee; 
}
.map-node.state-visited .node-disc { 
  border-color: #c97b4a; background: #f7dfc5; 
}
.map-node.state-current .node-disc { 
  border-color: #c97b4a; border-width: 3rpx;
  box-shadow: 0 0 0 6px rgba(201,123,74,0.15);
}
.map-node.state-locked { opacity: 0.65; }
.map-node.state-locked .node-disc { 
  border-color: #d8c8a8; background: #f0e6d0;
}
.map-node.state-mastered .node-disc { 
  border-color: #d4a017; background: #fef3c7;
  box-shadow: 0 0 0 4px rgba(212,160,23,0.3);
}
.map-node.node-active .node-disc {
  border-color: #a25e30; border-width: 2.5px;
  box-shadow: 0 0 0 8px rgba(201,123,74,0.2);
  animation: pulse 2s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { box-shadow: 0 0 0 8px rgba(201,123,74,0.2); }
  50% { box-shadow: 0 0 0 14px rgba(201,123,74,0.08); }
}

.node-disc {
  position: absolute; inset: 0;
  background: #fdf6e6; border: 2rpx solid #d8c8a8;
  border-radius: 50%; transition: all 0.25s ease;
}
.node-emoji {
  font-size: 36rpx; line-height: 1; z-index: 1;
  position: relative;
}
.node-label {
  position: absolute; bottom: -36rpx;
  left: 50%; transform: translateX(-50%);
  white-space: nowrap; font-size: 20rpx;
  font-weight: 600; color: #4a3d2a;
  text-align: center; max-width: 160rpx;
  overflow: hidden; text-overflow: ellipsis;
  z-index: 1;
}
.node-target .node-label { max-width: 200rpx; font-size: 22rpx; color: #a25e30; font-weight: 700; }
.node-target { width: 120rpx; height: 120rpx; margin-left: -60rpx; margin-top: -60rpx; }
.node-target .node-disc { width: 120rpx; height: 120rpx; background: #4a3d2a; border-color: #4a3d2a; }
.node-target .node-emoji { font-size: 44rpx; }
.node-target.state-done .node-disc { background: #5b8c5a; border-color: #5b8c5a; }
.node-target.state-visited .node-disc { background: #c97b4a; border-color: #c97b4a; }
.node-target.state-mastered .node-disc { background: #d4a017; border-color: #d4a017; }

/* 节点角标 */
.node-badge {
  position: absolute; top: -4rpx; right: -4rpx;
  width: 32rpx; height: 32rpx; border-radius: 50%;
  background: #f7dfc5; border: 2rpx solid #e8b994;
  display: flex; align-items: center; justify-content: center;
  font-size: 18rpx; z-index: 10;
  animation: badgePulse 2s ease-in-out infinite;
}
.badge-hint { background: #f7dfc5; border-color: #e8b994; }
.badge-more { background: #c97b4a; border-color: #a25e30; color: #fff; }
@keyframes badgePulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.15); }
}

/* 已完成勾选 / 已掌握奖杯 */
.node-check {
  position: absolute; bottom: 4rpx; right: 4rpx;
  width: 28rpx; height: 28rpx; border-radius: 50%;
  background: #5b8c5a; color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-size: 18rpx; font-weight: 700; z-index: 10;
}
.node-master {
  position: absolute; top: -8rpx; right: -8rpx;
  font-size: 28rpx; z-index: 11;
  filter: drop-shadow(0 2rpx 4px rgba(0,0,0,0.2));
}

/* ========== 内容卡片 ========== */
.card-overlay {
  position: fixed; inset: 0; z-index: 100;
  display: flex; align-items: center; justify-content: center;
  background: rgba(74,61,42,0.35);
  padding: 30rpx;
}
.content-card {
  width: 100%; max-width: 720rpx; max-height: 88vh;
  background: #fdf6e6; border: 1rpx solid #d8c8a8;
  border-radius: 20rpx; overflow: hidden;
  display: flex; flex-direction: column;
  box-shadow: 0 20rpx 60px rgba(74,61,42,0.15);
  opacity: 0;
  visibility: hidden;
  transition: all 0.35s cubic-bezier(0.34, 1.4, 0.64, 1);
}
.content-card.card-show { 
  opacity: 1; 
  visibility: visible;
}
.card-tail {
  position: absolute; top: -12rpx; left: 50%;
  width: 24rpx; height: 24rpx;
  background: #fdf6e6; border-top: 1rpx solid #d8c8a8; border-left: 1rpx solid #d8c8a8;
  transform: translateX(-50%) rotate(45deg);
}
.card-header {
  display: flex; align-items: center; gap: 16rpx;
  padding: 28rpx 28rpx 20rpx; border-bottom: 1rpx solid #e8dcc5;
}
.card-emoji { font-size: 44rpx; flex-shrink: 0; }
.card-title-area { display: flex; flex-direction: column; gap: 4rpx; min-width: 0; }
.card-kind { font-size: 22rpx; color: #8a7861; }
.card-name { font-size: 34rpx; font-weight: 700; color: #4a3d2a; overflow-wrap: anywhere; }
.card-close {
  margin-left: auto; flex-shrink: 0;
  width: 52rpx; height: 52rpx; line-height: 48rpx;
  text-align: center; font-size: 36rpx; color: #8a7861;
  border-radius: 50%;
}
.card-body { flex: 1; min-height: 0; max-height: calc(88vh - 180rpx); padding: 0 28rpx; overflow-y: auto; overflow-x: hidden; }
.card-footer {
  padding: 20rpx 28rpx; border-top: 1rpx solid #e8dcc5;
  background: #faf3e3;
}

/* 加载状态 */
.loading-state {
  display: flex; flex-direction: column; align-items: center;
  padding: 60rpx 20rpx; color: #8a7861;
}
.loading-icon { font-size: 48rpx; margin-bottom: 16rpx; animation: spin 1s linear infinite; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
.loading-text { font-size: 26rpx; }

/* 卡片内容区 */
.card-section { margin-top: 24rpx; }
.section-title { display: block; font-size: 26rpx; font-weight: 700; color: #4a3d2a; margin-bottom: 10rpx; }
.section-text { font-size: 26rpx; color: #6b5d4a; line-height: 1.75; }

/* 定义文本 */
.definition-text {
  background: #f7f2e3; padding: 20rpx; border-radius: 12rpx;
  border-left: 4rpx solid #c97b4a; font-size: 27rpx; line-height: 1.75; color: #4a3d2a;
  width: 100%; box-sizing: border-box;
  word-wrap: break-word; overflow-wrap: anywhere;
}
.importance-text { color: #8a6d3b; font-style: italic; }

/* 示例 */
.example-item {
  padding: 16rpx; margin-bottom: 12rpx;
  background: #fff; border: 1rpx solid #e8dcc5; border-radius: 10rpx;
}
.example-content { font-size: 26rpx; color: #4a3d2a; line-height: 1.65; }

/* ========== 验收测试区 ========== */
.quiz-section { 
  background: #fff; padding: 24rpx; border-radius: 16rpx;
  border: 2rpx solid #e8dcc5;
}
.quiz-hint { font-size: 24rpx; color: #8a7861; margin-bottom: 16rpx; }
.quiz-list { margin-top: 12rpx; }
.quiz-item {
  padding: 20rpx; margin-bottom: 20rpx;
  background: #faf8f3; border: 1rpx solid #e8dcc5; border-radius: 12rpx;
  transition: all 0.25s ease;
}
.quiz-item.quiz-correct { border-color: #5b8c5a; background: #f0f7ed; }
.quiz-item.quiz-wrong { border-color: #c97b4a; background: #fdf3e9; }

.quiz-q { display: flex; gap: 14rpx; margin-bottom: 12rpx; }
.quiz-num {
  flex-shrink: 0; width: 44rpx; height: 44rpx;
  display: flex; align-items: center; justify-content: center;
  background: #f7dfc5; color: #a25e30;
  border-radius: 50%; font-size: 22rpx; font-weight: 700;
}
.quiz-stem { font-size: 27rpx; color: #4a3d2a; line-height: 1.6; }

/* 选择题选项 */
.quiz-options { display: flex; flex-direction: column; gap: 10rpx; margin-top: 12rpx; }
.quiz-option {
  display: flex; align-items: center; gap: 14rpx;
  padding: 18rpx 20rpx; background: #fff; border: 2rpx solid #e8dcc5;
  border-radius: 10rpx; transition: all 0.2s ease;
}
.quiz-option.option-selected { border-color: #c97b4a; background: #f7dfc5; }
.quiz-option.option-correct { border-color: #5b8c5a; background: #eef6ee; }
.quiz-option.option-wrong { border-color: #c97b4a; background: #fdf3e9; }
.option-letter {
  flex-shrink: 0; width: 40rpx; height: 40rpx;
  display: flex; align-items: center; justify-content: center;
  background: #f0e6d0; color: #8a7861; border-radius: 50%;
  font-size: 22rpx; font-weight: 700;
}
.option-text { font-size: 26rpx; color: #4a3d2a; }

/* 填空题输入 */
.quiz-input-wrap { 
  margin-top: 12rpx; 
}
.quiz-input {
  width: 100%; padding: 18rpx 20rpx; background: #fff;
  border: 2rpx solid #e8dcc5; border-radius: 10rpx;
  font-size: 26rpx; color: #4a3d2a; box-sizing: border-box;
}
.quiz-textarea {
  min-height: 80rpx;
  line-height: 1.5;
}

/* 解析 */
.quiz-analysis {
  margin-top: 16rpx; padding: 18rpx;
  background: #f7f2e3; border-radius: 10rpx;
  border: 1rpx dashed #d8c8a8;
}
.analysis-label { display: block; font-size: 22rpx; color: #8a7861; font-weight: 600; margin-bottom: 8rpx; }
.analysis-text { display: block; font-size: 25rpx; color: #4a3d2a; line-height: 1.6; margin-bottom: 6rpx; }
.analysis-detail { display: block; font-size: 23rpx; color: #8a7861; line-height: 1.55; }

/* 操作按钮 */
.action-row { display: flex; gap: 16rpx; margin-top: 24rpx; }
.btn {
  flex: 1; margin: 0; padding: 0 16rpx; height: 72rpx;
  line-height: 68rpx; border-radius: 12rpx; font-size: 26rpx; font-weight: 600;
  border: none;
}
.btn::after { border: none; }
.btn-hint { background: #f0e6d0; color: #8a7861; }
.btn-pass { background: #c97b4a; color: #fff; }
.btn-submit { background: #c97b4a; color: #fff; }
.btn-submit[disabled] { background: #d8c8a8; color: #b5a288; }
.btn-retry { background: #fff; color: #c97b4a; border: 1rpx solid #c97b4a; }

/* 测试结果 */
.quiz-result {
  margin-top: 20rpx; padding: 20rpx; border-radius: 12rpx;
  text-align: center; font-size: 26rpx; font-weight: 600;
}
.result-pass { background: #eef6ee; color: #3d6b4f; }
.result-fail { background: #fdf3e9; color: #a25e30; }

/* 已掌握横幅 */
.mastered-banner {
  display: flex; align-items: center; gap: 16rpx;
  padding: 20rpx 24rpx; margin-top: 20rpx;
  background: linear-gradient(135deg, #fef3c7, #fde68a);
  border: 2rpx solid #d4a017; border-radius: 12rpx;
}
.mastered-icon { font-size: 48rpx; }
.mastered-info { flex: 1; }
.mastered-title { display: block; font-size: 28rpx; font-weight: 700; color: #92400e; }
.mastered-time { display: block; font-size: 22rpx; color: #b45309; margin-top: 4rpx; }

/* 底部状态 */
.footer-status { font-size: 24rpx; }
.status-done { color: #5b8c5a; font-weight: 600; }
.status-current { color: #c97b4a; font-weight: 600; }
.status-preview { color: #8a7861; }
.status-mastered { color: #92400e; font-weight: 700; }

/* ========== 笔记本面板 ========== */
.notebook-panel {
  position: fixed; top: 0; right: 0; bottom: 0; width: 70%;
  max-width: 480rpx; background: #fdf6e6;
  border-left: 1rpx solid #d8c8a8;
  z-index: 150; display: flex; flex-direction: column;
  transform: translateX(100%); transition: transform 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}
.notebook-panel.panel-open { transform: translateX(0); }
.notebook-mask {
  position: fixed; inset: 0; background: rgba(74,61,42,0.3);
  z-index: 140;
}
.notebook-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 28rpx 24rpx 20rpx; border-bottom: 1rpx solid #e8dcc5;
}
.notebook-title { font-size: 32rpx; font-weight: 700; color: #4a3d2a; }
.notebook-close { font-size: 40rpx; color: #8a7861; padding: 0 10rpx; }
.notebook-search {
  margin: 16rpx 20rpx; padding: 16rpx 20rpx;
  background: #fff; border: 1rpx solid #d8c8a8; border-radius: 12rpx;
  font-size: 26rpx; color: #4a3d2a;
}
.notebook-list { flex: 1; padding: 0 20rpx 20rpx; }
.notebook-empty {
  text-align: center; padding: 80rpx 20rpx; color: #b5a288;
}
.empty-hint { display: block; margin-top: 12rpx; font-size: 24rpx; }
.notebook-item {
  padding: 20rpx 16rpx; margin-bottom: 12rpx;
  background: #fff; border: 1rpx solid #e8dcc5; border-radius: 12rpx;
  position: relative;
}
.item-name { display: block; font-size: 27rpx; font-weight: 600; color: #4a3d2a; margin-bottom: 6rpx; }
.item-explain { display: block; font-size: 23rpx; color: #8a7861; line-height: 1.5; }
.item-mastered {
  position: absolute; top: 16rpx; right: 16rpx;
  font-size: 24rpx;
}

/* ========== Toast ========== */
.toast-container {
  position: fixed; top: 120rpx; left: 50%; transform: translateX(-50%);
  z-index: 200; display: flex; flex-direction: column; align-items: center; gap: 12rpx;
  pointer-events: none;
}
.toast {
  display: flex; align-items: center; gap: 10rpx;
  padding: 18rpx 28rpx; background: #4a3d2a; color: #fdf6e6;
  border-radius: 40rpx; font-size: 25rpx; font-weight: 500;
  box-shadow: 0 8rpx 24px rgba(74,61,42,0.2);
  transform: translateY(-20rpx); opacity: 0;
  transition: all 0.35s cubic-bezier(0.34, 1.4, 0.64, 1);
}
.toast-show { transform: translateY(0); opacity: 1; }
.toast-emoji { font-size: 30rpx; }
</style>
