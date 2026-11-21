<template>
  <view class="page theme-root" :class="{ 'is-dark': isDark }" :style="themeVars">
    <ThemeBackground />
    <view class="hero" :style="{ paddingTop: heroTop + 'px' }">
      <view class="hero-top">
        <text class="hero-back" @click="goBack">‹</text>
        <text class="hero-title">学情诊断</text>
        <text class="hero-spacer"></text>
      </view>
      <text class="hero-sub">先选范围，系统按你的作答逐题判断；答错会向上追先修。</text>
    </view>

    <view v-if="loading" class="state">
      <text class="state-text">正在加载诊断目录…</text>
    </view>

    <view v-else-if="error" class="state">
      <text class="state-text">{{ error }}</text>
      <button class="ghost" @click="loadCatalog">重试</button>
    </view>

    <!-- ==================== 设置 ==================== -->
    <view v-else-if="view === 'setup'" class="setup">
      <view v-if="lastSession" class="resume-card">
        <view class="resume-main">
          <text class="resume-title">
            {{ lastSession.status === 'active' ? '上次诊断还没做完' : '上次诊断已完成' }}
          </text>
          <text class="resume-sub">{{ resumeSubtitle }}</text>
        </view>
        <view class="resume-actions">
          <button
            v-if="lastSession.status === 'active'"
            class="resume-btn primary small-btn"
            @click="resumeLastSession"
          >继续</button>
          <button
            v-else
            class="resume-btn primary small-btn"
            @click="viewLastResult"
          >查看上次结果</button>
          <button class="resume-btn ghost small-btn" @click="discardLastSession">重新开始</button>
        </view>
      </view>

      <view class="tabs">
        <view
          v-for="tab in tabs"
          :key="tab.key"
          class="tab"
          :class="{ active: mode === tab.key }"
          @click="switchMode(tab.key)"
        >{{ tab.label }}</view>
      </view>

      <!-- 单点诊断 -->
      <view v-if="mode === 'single'" class="card">
        <text class="section-title">选择知识点</text>
        <view class="search">
          <text class="search-icon">🔍</text>
          <input
            v-model="search"
            class="search-input"
            placeholder="例如：配方法、20 以内加法、一次函数"
            confirm-type="search"
          />
        </view>
        <view class="chips">
          <view
            v-for="s in stageOptions"
            :key="s.key"
            class="chip"
            :class="{ active: stage === s.key }"
            @click="stage = s.key"
          >{{ s.label }}</view>
        </view>

        <scroll-view scroll-y class="topic-list">
          <view
            v-for="t in filteredTopics"
            :key="t.id"
            class="topic-item"
            :class="{ selected: selectedTopicId === t.id }"
            @click="selectedTopicId = t.id"
          >
            <view class="topic-main">
              <text class="topic-name">{{ t.name }}</text>
              <text class="topic-meta">{{ t.grade_label }} · {{ t.chapter_label }}</text>
            </view>
            <text v-if="selectedTopicId === t.id" class="topic-check">✓</text>
          </view>
          <view v-if="!filteredTopics.length" class="empty">没有匹配的知识点</view>
        </scroll-view>
        <text v-if="matchedTopics.length > filteredTopics.length" class="section-hint">
          共 {{ matchedTopics.length }} 个知识点，当前显示前 {{ filteredTopics.length }} 个，输入关键词可继续缩小。
        </text>
      </view>

      <!-- 章节诊断 -->
      <view v-if="mode === 'chapter'" class="card">
        <text class="section-title">选择教材范围</text>
        <text class="section-hint">勾选要检查的章；未选中的知识点不参与本次诊断。</text>

        <scroll-view scroll-x class="book-scroll">
          <view
            v-for="b in books"
            :key="b.key"
            class="book-chip"
            :class="{ active: selectedBookKey === b.key }"
            @click="selectedBookKey = b.key"
          >{{ b.book }}</view>
        </scroll-view>

        <view class="chapter-head">
          <text class="chapter-head-title">{{ currentBook ? currentBook.book : '' }}</text>
          <text class="link" @click="toggleAllChapters">
            {{ allChaptersSelected ? '取消全选' : '全选本册' }}
          </text>
        </view>

        <scroll-view scroll-y class="chapter-list">
          <view
            v-for="ch in chapters"
            :key="ch.chapter"
            class="chapter-item"
            @click="toggleChapter(ch.chapter)"
          >
            <view class="checkbox" :class="{ on: chapterChecks[ch.chapter] }">
              {{ chapterChecks[ch.chapter] ? '✓' : '' }}
            </view>
            <view class="chapter-main">
              <text class="chapter-name">{{ ch.label }}</text>
              <text class="chapter-meta">{{ ch.topic_count }} 个知识点 · {{ ch.question_count }} 题</text>
            </view>
          </view>
          <view v-if="!chapters.length" class="empty">本册暂无章节</view>
        </scroll-view>

        <text class="summary">
          已选 {{ selectedChapters.length }} 章 · {{ selectedChapterNodes.length }} 个知识点 · 题库 {{ selectedChapterQuestionCount }} 题
        </text>
      </view>

      <!-- 整年级摸底 -->
      <view v-if="mode === 'grade'" class="card">
        <text class="section-title">选择年级</text>
        <view class="grade-grid">
          <view
            v-for="g in catalog.grades"
            :key="g.grade"
            class="grade-item"
            :class="{ active: selectedGrade === g.grade }"
            @click="selectGrade(g.grade)"
          >
            <text class="grade-name">{{ g.label }}</text>
            <text class="grade-meta">{{ g.topic_count }} 点</text>
          </view>
        </view>

        <view v-if="semesterOptions.length > 1" class="segmented">
          <view
            v-for="s in semesterOptions"
            :key="s.key"
            class="seg-item"
            :class="{ active: semester === s.key }"
            @click="semester = s.key"
          >{{ s.label }}</view>
        </view>

        <text class="section-hint">
          检查本年级掌握情况，不做竞赛拔高。题量有限，到上限后没测到的知识点标为「未测」。
        </text>
      </view>

      <!-- 高级设置 -->
      <view class="card">
        <view class="settings-head" @click="showSettings = !showSettings">
          <text class="section-title">高级设置</text>
          <text class="chevron">{{ showSettings ? '▴' : '▾' }}</text>
        </view>

        <view v-if="showSettings" class="settings-body">
          <view class="setting-row">
            <text class="setting-label">本次最多出多少题</text>
            <text class="setting-value">{{ maxQuestions }}</text>
          </view>
          <slider
            :min="questionRange[0]"
            :max="questionRange[1]"
            :value="maxQuestions"
            :active-color="tokens.primary"
            :background-color="tokens.line"
            block-size="20"
            @change="onMaxQuestions"
          />

          <view class="setting-row">
            <text class="setting-label">掌握标准：连续答对</text>
            <text class="setting-value">{{ masteryStreak }} 题</text>
          </view>
          <view class="segmented small">
            <view
              v-for="n in [2, 3, 5]"
              :key="n"
              class="seg-item"
              :class="{ active: masteryStreak === n }"
              @click="masteryStreak = n"
            >{{ n }} 题</view>
          </view>

          <text class="setting-tip">
            答错后会追加 1 道确认题；确认题也错判为薄弱。选 5 时，题量不足的知识点按实际题量判定。
          </text>
        </view>
      </view>

      <view class="start-wrap">
        <button
          class="start-btn"
          :class="{ disabled: !canStart || starting }"
          :disabled="!canStart || starting"
          @click="beginDiagnosis()"
        >
          {{ startLabel }}
        </button>
      </view>

      <view class="footer-note">
        <text>题目来源：cn-math-taxonomy（CC BY-NC 4.0）· 由 AI 生成，未经一线教师审核，仅用于薄弱点筛查。</text>
      </view>
    </view>

    <!-- ==================== 答题 ==================== -->
    <view v-else-if="view === 'quiz'" class="quiz">
      <view class="quiz-head">
        <text class="quiz-progress">第 {{ displayIndex }} 题 / 最多 {{ session.settings.max_questions }} 题</text>
        <text class="quiz-exit" @click="confirmExit">退出</text>
      </view>
      <view class="progress-bar">
        <view class="progress-fill" :style="{ width: progressWidth }"></view>
      </view>

      <view class="quiz-meta">
        <text class="quiz-topic">{{ currentQuestion.node_name }}</text>
        <text class="difficulty">{{ difficultyLabel }}</text>
      </view>
      <text class="quiz-sub">{{ currentQuestion.chapter_label }}</text>
      <MathText class="quiz-prompt" :text="currentQuestion.prompt" />
      <image
        v-if="currentQuestion.figure"
        :src="svgUri(currentQuestion.figure)"
        class="quiz-figure"
        mode="widthFix"
      />

      <view v-if="currentQuestion.choices && currentQuestion.choices.length" class="choices">
        <view
          v-for="c in currentQuestion.choices"
          :key="c.key"
          class="choice"
          :class="{
            selected: selectedChoice === c.key,
            correct: feedback && feedback.is_correct && selectedChoice === c.key,
            wrong: feedback && !feedback.is_correct && selectedChoice === c.key,
          }"
          @click="selectChoice(c.key)"
        >
          <text class="choice-key">{{ c.key }}</text>
          <image
            v-if="c.figure && currentQuestion.hide_choice_text"
            :src="svgUri(c.figure)"
            class="choice-figure"
            mode="widthFix"
          />
          <MathText v-else class="choice-text" :text="c.text" inline />
        </view>
      </view>

      <view v-else class="answer-input">
        <input
          v-model="answerText"
          class="input"
          placeholder="输入你的答案"
          :disabled="!!feedback"
          confirm-type="done"
        />
      </view>

      <view
        v-if="feedback"
        class="feedback"
        :class="feedback.is_correct ? 'ok' : 'bad'"
      >
        <text class="feedback-title">{{ feedback.is_correct ? '✓ 回答正确' : '✗ 回答错误' }}</text>
        <MathText v-if="feedback.explanation" class="feedback-text" :text="'解析：' + feedback.explanation" />
        <text v-if="feedback.node_status === 'weak'" class="feedback-text">
          这个点还需要补一补，继续看看它的先修知识。
        </text>
        <text v-else-if="feedback.node_status === 'unstable'" class="feedback-text">
          这个点不太稳，建议再练几题。
        </text>
      </view>

      <view class="quiz-actions">
        <button
          v-if="!feedback"
          class="primary"
          :class="{ disabled: !canSubmit }"
          :disabled="!canSubmit"
          @click="submitAnswer"
        >
          {{ submitting ? '提交中…' : '提交' }}
        </button>
        <button v-else class="primary" @click="nextStep">
          {{ feedback.result ? '查看结果' : '下一题' }}
        </button>
      </view>
    </view>

    <!-- ==================== 结果 ==================== -->
    <view v-else class="result">
      <view class="result-hero">
        <text class="result-title">{{ activeMode === 'grade' ? '摸底完成' : '诊断完成' }}</text>
        <text class="result-sub">本次作答 {{ result.answered }} 题</text>
      </view>

      <view class="counts">
        <view v-if="proficientCount" class="count">
          <text class="num proficient-num">{{ proficientCount }}</text>
          <text class="label">熟练</text>
        </view>
        <view class="count">
          <text class="num">{{ masteredOnlyCount }}</text>
          <text class="label">掌握</text>
        </view>
        <view class="count">
          <text class="num">{{ result.counts.unstable || 0 }}</text>
          <text class="label">不稳</text>
        </view>
        <view class="count">
          <text class="num weak-num">{{ result.counts.weak || 0 }}</text>
          <text class="label">薄弱</text>
        </view>
        <view class="count">
          <text class="num">{{ result.counts.untested || 0 }}</text>
          <text class="label">未测</text>
        </view>
        <view v-if="result.counts.insufficient" class="count">
          <text class="num">{{ result.counts.insufficient }}</text>
          <text class="label">题量不足</text>
        </view>
      </view>

      <view v-if="activeMode === 'single' && targetAssessment" class="card">
        <text class="section-title">诊断结论</text>
        <view class="status-banner" :class="targetAssessment.status">
          <text class="status-name">{{ targetAssessment.name }}</text>
          <text class="status-value">{{ levelLabel(targetAssessment) }}</text>
        </view>
        <text v-if="targetAssessment.status === 'weak'" class="section-hint">
          根因在更基础的知识点，建议按下面的顺序补。
        </text>
        <text v-else-if="targetAssessment.status === 'unstable'" class="section-hint">
          这个点不太稳，建议再练几题巩固。
        </text>
      </view>

      <view v-if="activeMode !== 'grade'" class="card">
        <text class="section-title">根因与学习顺序</text>
        <view v-if="rootCauseNodes.length" class="pill-list">
          <text v-for="n in rootCauseNodes" :key="n.id" class="pill weak">{{ n.name }}</text>
        </view>
        <text v-else class="section-hint">没有发现更基础的根因。</text>

        <view v-if="learningPathNodes.length" class="path">
          <text class="path-label">建议顺序（先补最基础）</text>
          <text class="path-text">{{ learningPathNodes.map((n) => n.name).join(' → ') }}</text>
        </view>
      </view>

      <view class="card breakdown">
        <view class="breakdown-head">
          <text class="section-title">逐点清单</text>
          <text class="section-count">共 {{ assessments.length }} 个知识点</text>
        </view>
        <text class="section-hint">按章节分组；每一行都可以看错题、看图谱或单独再测。</text>

        <scroll-view scroll-x class="filter-scroll">
          <view class="filter-chips">
            <view
              v-for="f in filterOptions"
              :key="f.key"
              class="filter-chip"
              :class="{ active: statusFilter === f.key }"
              @click="statusFilter = f.key"
            >
              <text>{{ f.label }}</text>
              <text class="filter-count">{{ f.count }}</text>
            </view>
          </view>
        </scroll-view>

        <view
          v-for="group in groupedAssessments"
          :key="group.key"
          class="assess-group"
        >
          <view class="assess-group-head" @click="toggleGroup(group.key)">
            <view class="assess-group-main">
              <text class="assess-group-name">{{ group.label }}</text>
              <text class="assess-group-meta">{{ groupSummary(group) }}</text>
            </view>
            <text class="chevron">{{ isGroupOpen(group.key) ? '▴' : '▾' }}</text>
          </view>

          <view v-if="isGroupOpen(group.key)" class="assess-rows">
            <view v-for="a in group.items" :key="a.id" class="assess-row">
              <view class="assess-line">
                <text class="status-pill" :class="levelClass(a)">{{ levelLabel(a) }}</text>
                <text class="assess-name">{{ a.name }}</text>
              </view>
              <text class="assess-meta">{{ assessmentMeta(a) }}</text>
              <view class="assess-actions">
                <text
                  v-if="wrongCountOf(a) > 0"
                  class="mini-link"
                  @click.stop="openWrong(a.id)"
                >看错题</text>
                <text
                  v-if="a.status === 'weak' || a.status === 'unstable'"
                  class="mini-link"
                  @click.stop="openGraph(a.id)"
                >看图谱</text>
                <text class="mini-link" @click.stop="retestNode(a.id)">再测</text>
              </view>
            </view>
          </view>
        </view>

        <text v-if="!groupedAssessments.length" class="section-hint">当前筛选下没有知识点。</text>
      </view>

      <view v-if="result.counts.untested" class="note">
        题量上限到了，还有 {{ result.counts.untested }} 个知识点未测。可以再测一次并提高题量上限。
      </view>

      <view class="result-actions">
        <button v-if="weakNodes.length" class="primary" @click="retestWeak">
          只测薄弱点（{{ weakNodes.length }}）
        </button>
        <button v-if="loggedIn" class="ghost" @click="openTrend">查看学情趋势</button>
        <button class="ghost" @click="restart">再测一次</button>
        <button class="ghost" @click="goBack">返回</button>
      </view>
    </view>
  </view>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import {
  abortDiagnosis as abortDiagnosisApi,
  answerDiagnosis as answerDiagnosisApi,
  getDiagnosisCatalog as getDiagnosisCatalogApi,
  getDiagnosisSession as getDiagnosisSessionApi,
  startDiagnosis as startDiagnosisApi,
} from '../../api.js'
import { store } from '../../store.js'
import { themeVars, isDark, tokens } from '../../theme/theme.js'
import MathText from '../../components/ui/MathText.vue'

const LAST_SESSION_KEY = 'ikgr_last_diagnosis_session'

const tabs = [
  { key: 'single', label: '单点诊断' },
  { key: 'chapter', label: '章节诊断' },
  { key: 'grade', label: '整年级摸底' },
]

const stageOptions = [
  { key: 'all', label: '全部' },
  { key: 'primary', label: '小学' },
  { key: 'junior', label: '初中' },
  { key: 'senior', label: '高中' },
]

const statusText = {
  proficient: '熟练',
  mastered: '掌握',
  unstable: '不稳',
  weak: '薄弱',
  untested: '未测',
  insufficient: '题量不足',
  pending: '未测',
}

const modeText = {
  single: '单点诊断',
  chapter: '章节诊断',
  grade: '整年级摸底',
}

const filterDefs = [
  { key: 'all', label: '全部' },
  { key: 'proficient', label: '熟练' },
  { key: 'mastered', label: '掌握' },
  { key: 'unstable', label: '不稳' },
  { key: 'weak', label: '薄弱' },
  { key: 'untested', label: '未测' },
  { key: 'insufficient', label: '题量不足' },
]

const difficultyText = {
  basic: '基础',
  standard: '提高',
  challenge: '拓展',
  advanced: '拓展',
}

const view = ref('setup')
const activeMode = ref('single')
const loading = ref(true)
const error = ref('')
const lastSession = ref(null)
const statusFilter = ref('all')
const collapsedGroups = reactive({})
const autoNodeId = ref('')
const loggedIn = computed(() => !!(store.auth.user && store.auth.token))

// 自定义导航栏：App 端避开状态栏。
const statusBarHeight = ref(0)
// #ifdef H5
statusBarHeight.value = 0
// #endif
// #ifdef APP-PLUS
try {
  statusBarHeight.value = uni.getSystemInfoSync().statusBarHeight || 0
} catch (e) {
  statusBarHeight.value = 0
}
// #endif
const heroTop = computed(() => statusBarHeight.value + 18)

const catalog = ref({ grades: [], topics: [] })
const mode = ref('single')
const search = ref('')
const stage = ref('all')
const selectedTopicId = ref('')

const selectedBookKey = ref('')
const chapterChecks = reactive({})

const selectedGrade = ref(1)
const semester = ref('all')

const maxQuestions = ref(16)
const masteryStreak = ref(3)
const showSettings = ref(false)
const starting = ref(false)

const session = ref(null)
const resultSessionId = ref('')
const currentQuestion = ref(null)
const answered = ref(0)
const feedback = ref(null)
const pendingResult = ref(null)
const selectedChoice = ref('')
const answerText = ref('')
const submitting = ref(false)
const pendingRequestId = ref('')

const books = computed(() =>
  (catalog.value.grades || []).flatMap((g) =>
    (g.books || []).map((b) => ({ ...b, grade: g.grade, key: `${g.grade}:${b.book}` }))
  )
)

const currentBook = computed(
  () => books.value.find((b) => b.key === selectedBookKey.value) || null
)
const chapters = computed(() => (currentBook.value && currentBook.value.chapters) || [])

const chapterMap = computed(() => {
  const map = {}
  books.value.forEach((b) => (b.chapters || []).forEach((ch) => (map[ch.chapter] = ch)))
  return map
})

const selectedChapters = computed(() =>
  Object.keys(chapterChecks).filter((key) => chapterChecks[key])
)
const selectedChapterNodes = computed(() =>
  selectedChapters.value.flatMap((key) => (chapterMap.value[key] && chapterMap.value[key].node_ids) || [])
)
const selectedChapterQuestionCount = computed(() =>
  selectedChapters.value.reduce(
    (sum, key) => sum + ((chapterMap.value[key] && chapterMap.value[key].question_count) || 0),
    0
  )
)
const allChaptersSelected = computed(
  () => chapters.value.length > 0 && chapters.value.every((ch) => chapterChecks[ch.chapter])
)

const selectedGradeInfo = computed(
  () => (catalog.value.grades || []).find((g) => g.grade === selectedGrade.value) || null
)
const semesterOptions = computed(() => {
  const options = [{ key: 'all', label: '整学年' }]
  const semesters = (selectedGradeInfo.value && selectedGradeInfo.value.semesters) || []
  if (semesters.includes('上')) options.push({ key: '上', label: '上册' })
  if (semesters.includes('下')) options.push({ key: '下', label: '下册' })
  return options
})

const matchedTopics = computed(() => {
  let list = catalog.value.topics || []
  if (stage.value !== 'all') {
    const label = { primary: '小学', junior: '初中', senior: '高中' }[stage.value]
    list = list.filter((t) => t.stage === label)
  }
  const keyword = search.value.trim()
  if (keyword) {
    list = list.filter(
      (t) =>
        t.name.includes(keyword) ||
        t.id.includes(keyword) ||
        (t.chapter_label || '').includes(keyword)
    )
  }
  return list
})
const filteredTopics = computed(() => matchedTopics.value.slice(0, 120))

const questionRange = computed(() => (mode.value === 'grade' ? [20, 60] : [8, 30]))

const canStart = computed(() => {
  if (starting.value) return false
  if (mode.value === 'single') return !!selectedTopicId.value
  if (mode.value === 'chapter') return selectedChapterNodes.value.length > 0
  return !!selectedGrade.value
})

const startLabel = computed(() => {
  if (starting.value) return '正在准备…'
  if (mode.value === 'single') {
    return selectedTopicId.value ? '开始诊断' : '请先选择一个知识点'
  }
  if (mode.value === 'chapter') {
    const count = selectedChapterNodes.value.length
    return count ? `开始诊断（${count} 个知识点）` : '请先选择章节'
  }
  return '开始整年级摸底'
})

const displayIndex = computed(() => {
  const max = (session.value && session.value.settings.max_questions) || 0
  const index = feedback.value ? answered.value : answered.value + 1
  return max ? Math.min(index, max) : index
})

const progressWidth = computed(() => {
  const max = (session.value && session.value.settings.max_questions) || 0
  if (!max) return '0%'
  return `${Math.round((answered.value / max) * 100)}%`
})

const difficultyLabel = computed(
  () => difficultyText[(currentQuestion.value && currentQuestion.value.difficulty) || ''] || '提高'
)

const canSubmit = computed(() => {
  const q = currentQuestion.value
  if (!q || feedback.value || submitting.value) return false
  if (q.choices && q.choices.length) return !!selectedChoice.value
  return !!answerText.value.trim()
})

const result = computed(
  () =>
    pendingResult.value || {
      answered: 0,
      counts: {},
      assessments: [],
      chapters: [],
      weak: [],
      root_causes: [],
      learning_path: [],
    }
)
const targetAssessment = computed(() => {
  if (activeMode.value !== 'single') return null
  return (result.value.assessments || [])[0] || null
})
const nameById = computed(() => {
  const map = {}
  ;(result.value.assessments || []).forEach((a) => (map[a.id] = a.name))
  return map
})
const rootCauseNodes = computed(() =>
  (result.value.root_causes || []).map((id) => ({ id, name: nameById.value[id] || id }))
)
const learningPathNodes = computed(() =>
  (result.value.learning_path || []).map((id) => ({ id, name: nameById.value[id] || id }))
)
const weakNodes = computed(() =>
  (result.value.weak || []).map((id) => ({ id, name: nameById.value[id] || id }))
)

const assessments = computed(() => result.value.assessments || [])
const proficientCount = computed(() => result.value.counts.proficient || 0)
const masteredOnlyCount = computed(() =>
  Math.max(0, (result.value.counts.mastered || 0) - proficientCount.value)
)

function matchesFilter(assessment, filter) {
  if (filter === 'all') return true
  if (filter === 'proficient') return assessment.mastery_level === 'proficient'
  if (filter === 'mastered') {
    return (
      assessment.status === 'mastered' &&
      assessment.mastery_level !== 'proficient'
    )
  }
  return assessment.status === filter
}

const filterOptions = computed(() =>
  filterDefs.map((def) => ({
    ...def,
    count: assessments.value.filter((a) => matchesFilter(a, def.key)).length,
  }))
)

const groupedAssessments = computed(() => {
  const groups = new Map()
  assessments.value
    .filter((a) => matchesFilter(a, statusFilter.value))
    .forEach((a) => {
      const key = a.chapter || '未分章'
      if (!groups.has(key)) {
        groups.set(key, {
          key,
          label: a.chapter_label || a.chapter || '未分章',
          items: [],
        })
      }
      groups.get(key).items.push(a)
    })
  return Array.from(groups.values())
})

const resumeSubtitle = computed(() => {
  const data = lastSession.value
  if (!data) return ''
  const parts = [modeText[data.mode] || '诊断']
  const when = formatTime(data.created_at)
  if (when) parts.push(when)
  if (data.status === 'active') parts.push(`已完成 ${data.answered || 0} 题`)
  else if (data.counts) parts.push(`薄弱 ${data.counts.weak || 0}`)
  return parts.join(' · ')
})

// ---------- 逐点清单 ----------

function levelClass(assessment) {
  return assessment.mastery_level === 'proficient'
    ? 'proficient'
    : assessment.status
}

function levelLabel(assessment) {
  const key =
    assessment.mastery_level === 'proficient'
      ? 'proficient'
      : assessment.status
  return statusText[key] || '未测'
}

function askedCountOf(assessment) {
  return typeof assessment.asked_count === 'number'
    ? assessment.asked_count
    : (assessment.asked || []).length
}

function wrongCountOf(assessment) {
  return typeof assessment.wrong_count === 'number'
    ? assessment.wrong_count
    : (assessment.wrong || []).length
}

function assessmentMeta(assessment) {
  const asked = askedCountOf(assessment)
  const wrong = wrongCountOf(assessment)
  if (assessment.status === 'mastered') {
    const streak = assessment.streak || assessment.effective_mastery || asked
    const level = difficultyText[assessment.max_correct_difficulty]
    return level ? `连续 ${streak} 题，最高难度：${level}` : `连续 ${streak} 题`
  }
  if (assessment.status === 'weak' || assessment.status === 'unstable') {
    return `答对 ${Math.max(0, asked - wrong)}/${asked}，错 ${wrong} 题`
  }
  if (assessment.status === 'insufficient') return '可用题不足 2 道'
  if (assessment.status === 'untested' || assessment.status === 'pending') {
    return '本次题量上限内未测到'
  }
  return ''
}

function statusCounts(items) {
  const counts = {
    proficient: 0,
    mastered: 0,
    unstable: 0,
    weak: 0,
    untested: 0,
    insufficient: 0,
  }
  items.forEach((item) => {
    if (item.mastery_level === 'proficient') counts.proficient += 1
    else if (counts[item.status] !== undefined) counts[item.status] += 1
  })
  return counts
}

function groupSummary(group) {
  const counts = statusCounts(group.items)
  const parts = [`共 ${group.items.length} 点`]
  if (counts.proficient) parts.push(`熟练 ${counts.proficient}`)
  parts.push(`掌握 ${counts.mastered}`, `不稳 ${counts.unstable}`, `薄弱 ${counts.weak}`)
  if (counts.untested) parts.push(`未测 ${counts.untested}`)
  if (counts.insufficient) parts.push(`题量不足 ${counts.insufficient}`)
  return parts.join(' · ')
}

function isGroupOpen(key) {
  return !collapsedGroups[key]
}

function toggleGroup(key) {
  collapsedGroups[key] = !collapsedGroups[key]
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

// ---------- 本地会话恢复 ----------

async function restoreLastSession() {
  let saved = null
  try {
    saved = uni.getStorageSync(LAST_SESSION_KEY)
  } catch (e) {
    saved = null
  }
  if (!saved || !saved.session_id) return
  try {
    const data = await getDiagnosisSessionApi(saved.session_id)
    if (!data || data.status === 'aborted') {
      clearLastSession()
      return
    }
    lastSession.value = data
  } catch (e) {
    // 会话不存在 / 不属于当前用户时清掉本地记录。
    clearLastSession()
  }
}

function saveLastSession(data, payload) {
  try {
    uni.setStorageSync(LAST_SESSION_KEY, {
      session_id: data.session_id,
      mode: (payload && payload.mode) || data.mode || 'single',
      created_at: data.created_at || new Date().toISOString(),
    })
  } catch (e) {}
}

function clearLastSession() {
  try {
    uni.removeStorageSync(LAST_SESSION_KEY)
  } catch (e) {}
}

function resumeLastSession() {
  const data = lastSession.value
  if (!data) return
  if (!data.question) {
    uni.showToast({ title: '该会话已无法继续，请重新开始', icon: 'none' })
    clearLastSession()
    lastSession.value = null
    return
  }
  session.value = data
  resultSessionId.value = data.session_id || ''
  activeMode.value = data.mode
  answered.value = (data.progress && data.progress.answered) || data.answered || 0
  currentQuestion.value = data.question
  pendingRequestId.value = genId()
  feedback.value = null
  pendingResult.value = null
  selectedChoice.value = ''
  answerText.value = ''
  lastSession.value = null
  view.value = 'quiz'
}

function viewLastResult() {
  const data = lastSession.value
  if (!data) return
  resultSessionId.value = data.session_id || ''
  activeMode.value = data.mode
  answered.value = data.answered || 0
  pendingResult.value = data
  lastSession.value = null
  view.value = 'result'
}

async function discardLastSession() {
  const data = lastSession.value
  if (data && data.status === 'active') {
    try {
      await abortDiagnosisApi(data.session_id)
    } catch (e) {}
  }
  clearLastSession()
  lastSession.value = null
}

function maybeAutoStart() {
  if (!autoNodeId.value) return
  const nodeId = autoNodeId.value
  autoNodeId.value = ''
  beginWith({
    mode: 'single',
    node_ids: [nodeId],
    max_questions: 16,
    mastery_streak: 3,
  })
}

// ---------- 行内操作 ----------

function openWrong(nodeKey) {
  uni.navigateTo({ url: `/pages/wrong/wrong?node_key=${encodeURIComponent(nodeKey)}` })
}

function openGraph(nodeKey) {
  const sessionQuery = resultSessionId.value
    ? `&session_id=${encodeURIComponent(resultSessionId.value)}`
    : ''
  uni.navigateTo({
    url: `/pages/graph/graph?node_key=${encodeURIComponent(nodeKey)}${sessionQuery}`,
  })
}

function openTrend() {
  uni.navigateTo({ url: '/pages/trend/trend' })
}

function retestNode(nodeId) {
  beginWith({
    mode: 'single',
    node_ids: [nodeId],
    max_questions: 16,
    mastery_streak: 3,
  })
}

onLoad((query) => {
  if (query && query.node_key) {
    autoNodeId.value = String(query.node_key)
    mode.value = 'single'
    selectedTopicId.value = autoNodeId.value
  }
})

onMounted(async () => {
  await loadCatalog()
  await restoreLastSession()
  maybeAutoStart()
})

async function loadCatalog() {
  loading.value = true
  error.value = ''
  try {
    const data = await getDiagnosisCatalogApi()
    catalog.value = data || { grades: [], topics: [] }
    const grades = catalog.value.grades || []
    // 默认跟随学生在「我的」里设置的年级；没设置或目录不包含时回退到第一个年级。
    const userGrade = store.auth.user && store.auth.user.grade
    const preferredGrade = grades.find((g) => g.grade === userGrade) || grades[0]
    if (preferredGrade) selectedGrade.value = preferredGrade.grade
    const preferredBook =
      books.value.find((b) => b.grade === selectedGrade.value) || books.value[0]
    if (preferredBook) selectedBookKey.value = preferredBook.key
  } catch (err) {
    error.value = err.message || '诊断目录加载失败'
  } finally {
    loading.value = false
  }
}

function switchMode(key) {
  if (mode.value === key) return
  mode.value = key
  feedback.value = null
  if (key === 'grade') {
    maxQuestions.value = 40
    masteryStreak.value = 2
  } else {
    maxQuestions.value = 16
    masteryStreak.value = 3
  }
}

function selectGrade(grade) {
  selectedGrade.value = grade
  semester.value = 'all'
}

function toggleChapter(chapter) {
  chapterChecks[chapter] = !chapterChecks[chapter]
}

function toggleAllChapters() {
  const next = !allChaptersSelected.value
  chapters.value.forEach((ch) => (chapterChecks[ch.chapter] = next))
}

function onMaxQuestions(event) {
  maxQuestions.value = Number(event.detail.value)
}

function buildPayload() {
  const payload = {
    mode: mode.value,
    max_questions: maxQuestions.value,
    mastery_streak: masteryStreak.value,
  }
  if (mode.value === 'single') {
    payload.node_ids = [selectedTopicId.value]
  } else if (mode.value === 'chapter') {
    payload.node_ids = selectedChapterNodes.value
  } else {
    payload.grade = selectedGrade.value
    payload.semester = semester.value
  }
  return payload
}

function beginDiagnosis(payload = null) {
  if (!payload && !canStart.value) return
  beginWith(payload || buildPayload())
}

async function beginWith(payload) {
  starting.value = true
  feedback.value = null
  pendingResult.value = null
  try {
    const data = await startDiagnosisApi(payload)
    session.value = data
    resultSessionId.value = data.session_id || ''
    activeMode.value = payload.mode
    answered.value = (data.progress && data.progress.answered) || 0
    selectedChoice.value = ''
    answerText.value = ''
    // 只保存恢复会话所需的 id / 模式 / 时间，不写答案和题目内容。
    saveLastSession(data, payload)

    if (data.result) {
      pendingResult.value = data.result
      view.value = 'result'
      return
    }
    if (!data.question) {
      throw new Error('这个范围暂时没有可用题目')
    }
    currentQuestion.value = data.question
    pendingRequestId.value = genId()
    view.value = 'quiz'
  } catch (err) {
    uni.showToast({ title: err.message || '无法开始诊断', icon: 'none' })
    view.value = 'setup'
  } finally {
    starting.value = false
  }
}

function selectChoice(key) {
  if (!feedback.value) selectedChoice.value = key
}

async function submitAnswer() {
  if (!canSubmit.value) return
  const question = currentQuestion.value
  const answer = question.choices && question.choices.length
    ? selectedChoice.value
    : answerText.value.trim()
  submitting.value = true
  try {
    const data = await answerDiagnosisApi({
      session_id: session.value.session_id,
      question_id: question.id,
      answer,
      // 同一题失败重试复用同一个 id；响应丢失时后端返回首次结果，不会重复推进。
      client_request_id: pendingRequestId.value || genId(),
    })
    answered.value = (data.progress && data.progress.answered) || answered.value + 1
    pendingRequestId.value = ''
    if (data.result) pendingResult.value = data.result
    feedback.value = {
      is_correct: data.is_correct,
      explanation: data.explanation,
      node_status: data.node_status,
      result: data.result,
      next: data.next_question,
    }
  } catch (err) {
    uni.showToast({ title: err.message || '提交失败，请重试', icon: 'none' })
  } finally {
    submitting.value = false
  }
}

function nextStep() {
  const current = feedback.value
  if (!current) return
  if (current.result) {
    view.value = 'result'
    return
  }
  if (current.next) {
    currentQuestion.value = current.next
    pendingRequestId.value = genId()
    feedback.value = null
    selectedChoice.value = ''
    answerText.value = ''
    return
  }
  view.value = 'result'
}

function confirmExit() {
  uni.showModal({
    title: '退出诊断',
    content: '已作答的记录会保留，确定退出吗？',
    success: async (res) => {
      if (!res.confirm) return
      if (session.value && session.value.session_id) {
        try {
          await abortDiagnosisApi(session.value.session_id)
        } catch (e) {
          // 退出失败不阻塞前端
        }
      }
      clearLastSession()
      resetSession()
      view.value = 'setup'
    },
  })
}

function retestWeak() {
  const ids = result.value.weak || []
  if (!ids.length) return
  const limit = Math.max(8, Math.min(30, ids.length * 4))
  beginWith({ mode: 'chapter', node_ids: ids, max_questions: limit, mastery_streak: 3 })
}

function restart() {
  clearLastSession()
  lastSession.value = null
  resetSession()
  view.value = 'setup'
}

function resetSession() {
  session.value = null
  resultSessionId.value = ''
  currentQuestion.value = null
  answered.value = 0
  feedback.value = null
  pendingResult.value = null
  selectedChoice.value = ''
  answerText.value = ''
  pendingRequestId.value = ''
}

function goBack() {
  // 答题中退出需要确认并中止会话；结果页只离开页面，保留本地记录以便再次查看。
  if (view.value === 'quiz') {
    confirmExit()
    return
  }
  uni.navigateBack({
    fail: () => uni.reLaunch({ url: '/pages/index/index' }),
  })
}

function statusLabel(status) {
  return statusText[status] || '未测'
}

function svgUri(svg) {
  if (!svg) return ''
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`
}

function genId() {
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`
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
  padding-bottom: 160rpx;
  box-sizing: border-box;
}

.page.is-dark {
  --ik-danger-weak: rgba(255, 107, 107, 0.14);
  --ik-warn-weak: rgba(246, 173, 85, 0.14);
  --ik-warn-strong: #fbd38d;
  --ik-success-weak: rgba(74, 222, 128, 0.16);
}

.hero {
  background: var(--ik-primary);
  color: var(--ik-on-primary);
  padding: 0 32rpx 56rpx;
  box-sizing: border-box;
}

.hero-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.hero-back {
  width: 60rpx;
  font-size: 52rpx;
  line-height: 1;
  color: var(--ik-on-primary);
}

.hero-title {
  font-size: 40rpx;
  font-weight: 700;
}

.hero-spacer {
  width: 60rpx;
}

.hero-sub {
  display: block;
  margin-top: 18rpx;
  font-size: 24rpx;
  color: rgba(255, 255, 255, 0.82);
  line-height: 1.6;
}

.state {
  padding: 120rpx 40rpx;
  text-align: center;
}

.state-text {
  display: block;
  font-size: 28rpx;
  color: var(--ik-t2);
  margin-bottom: 24rpx;
}

.setup,
.quiz,
.result {
  padding: 0 24rpx;
  margin-top: -28rpx;
}

.tabs {
  display: flex;
  background: var(--ik-card);
  border-radius: 16rpx;
  padding: 8rpx;
  box-shadow: 0 6rpx 20rpx rgba(35, 60, 100, 0.06);
}

.tab {
  flex: 1;
  text-align: center;
  padding: 18rpx 0;
  font-size: 26rpx;
  color: var(--ik-t2);
  border-radius: 12rpx;
}

.tab.active {
  background: var(--ik-primary-weak);
  color: var(--ik-primary);
  font-weight: 600;
}

.card {
  background: var(--ik-card);
  border-radius: 16rpx;
  padding: 24rpx;
  margin-top: 20rpx;
}

.section-title {
  display: block;
  font-size: 30rpx;
  font-weight: 600;
  color: var(--ik-t1);
}

.section-hint {
  display: block;
  font-size: 23rpx;
  color: var(--ik-t3);
  line-height: 1.6;
  margin-top: 10rpx;
}

.search {
  display: flex;
  align-items: center;
  background: var(--ik-soft);
  border-radius: 12rpx;
  padding: 0 20rpx;
  margin-top: 20rpx;
}

.search-icon {
  font-size: 26rpx;
  margin-right: 10rpx;
}

.search-input {
  flex: 1;
  height: 80rpx;
  font-size: 27rpx;
  color: var(--ik-t1);
}

.chips {
  display: flex;
  flex-wrap: wrap;
  margin-top: 16rpx;
}

.chip {
  padding: 10rpx 26rpx;
  margin: 0 12rpx 12rpx 0;
  border-radius: 999rpx;
  background: var(--ik-soft);
  font-size: 24rpx;
  color: var(--ik-t2);
}

.chip.active {
  background: var(--ik-primary);
  color: var(--ik-on-primary);
}

.topic-list {
  height: 46vh;
  margin-top: 10rpx;
}

.topic-item {
  display: flex;
  align-items: center;
  padding: 20rpx 12rpx;
  border-bottom: 1rpx solid var(--ik-line);
}

.topic-item.selected {
  background: var(--ik-primary-weak);
  border-radius: 12rpx;
}

.topic-main {
  flex: 1;
}

.topic-name {
  display: block;
  font-size: 28rpx;
  color: var(--ik-t1);
}

.topic-meta {
  display: block;
  font-size: 21rpx;
  color: var(--ik-t3);
  margin-top: 2rpx;
}

.topic-check {
  color: var(--ik-primary);
  font-size: 32rpx;
  font-weight: 700;
}

.empty {
  padding: 60rpx 0;
  text-align: center;
  font-size: 25rpx;
  color: var(--ik-t3);
}

.book-scroll {
  white-space: nowrap;
  margin-top: 18rpx;
}

.book-chip {
  display: inline-block;
  padding: 12rpx 24rpx;
  margin-right: 12rpx;
  border-radius: 999rpx;
  background: var(--ik-soft);
  font-size: 24rpx;
  color: var(--ik-t2);
}

.book-chip.active {
  background: var(--ik-primary);
  color: var(--ik-on-primary);
}

.chapter-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 22rpx;
}

.chapter-head-title {
  font-size: 26rpx;
  font-weight: 600;
  color: var(--ik-t1);
}

.link {
  font-size: 24rpx;
  color: var(--ik-primary);
}

.chapter-list {
  height: 38vh;
  margin-top: 8rpx;
}

.chapter-item {
  display: flex;
  align-items: center;
  padding: 18rpx 4rpx;
  border-bottom: 1rpx solid var(--ik-line);
}

.checkbox {
  width: 36rpx;
  height: 36rpx;
  line-height: 34rpx;
  text-align: center;
  border: 2rpx solid var(--ik-line);
  border-radius: 8rpx;
  margin-right: 16rpx;
  font-size: 22rpx;
  color: var(--ik-on-primary);
  box-sizing: border-box;
}

.checkbox.on {
  background: var(--ik-primary);
  border-color: var(--ik-primary);
}

.chapter-main {
  flex: 1;
}

.chapter-name {
  display: block;
  font-size: 26rpx;
  color: var(--ik-t1);
}

.chapter-meta {
  display: block;
  font-size: 21rpx;
  color: var(--ik-t3);
  margin-top: 2rpx;
}

.summary {
  display: block;
  margin-top: 16rpx;
  font-size: 23rpx;
  color: var(--ik-primary);
}

.grade-grid {
  display: flex;
  flex-wrap: wrap;
  margin-top: 16rpx;
}

.grade-item {
  width: 23%;
  margin: 0 1% 16rpx;
  padding: 18rpx 0;
  text-align: center;
  background: var(--ik-soft);
  border-radius: 12rpx;
  box-sizing: border-box;
}

.grade-item.active {
  background: var(--ik-primary-weak);
  color: var(--ik-primary);
}

.grade-name {
  display: block;
  font-size: 26rpx;
  color: var(--ik-t1);
}

.grade-item.active .grade-name {
  color: var(--ik-primary);
  font-weight: 600;
}

.grade-meta {
  display: block;
  font-size: 20rpx;
  color: var(--ik-t3);
  margin-top: 2rpx;
}

.segmented {
  display: flex;
  background: var(--ik-soft);
  border-radius: 12rpx;
  padding: 6rpx;
  margin-top: 16rpx;
}

.segmented.small {
  margin-top: 10rpx;
}

.seg-item {
  flex: 1;
  text-align: center;
  padding: 14rpx 0;
  font-size: 25rpx;
  color: var(--ik-t2);
  border-radius: 10rpx;
}

.seg-item.active {
  background: var(--ik-card);
  color: var(--ik-primary);
  font-weight: 600;
  box-shadow: 0 2rpx 8rpx rgba(35, 60, 100, 0.08);
}

.settings-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.chevron {
  color: var(--ik-t3);
  font-size: 26rpx;
}

.settings-body {
  margin-top: 8rpx;
}

.setting-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 24rpx;
}

.setting-label {
  font-size: 26rpx;
  color: var(--ik-t1);
}

.setting-value {
  font-size: 26rpx;
  color: var(--ik-primary);
  font-weight: 600;
}

.setting-tip {
  display: block;
  margin-top: 18rpx;
  font-size: 22rpx;
  color: var(--ik-t3);
  line-height: 1.6;
}

.start-wrap {
  margin-top: 28rpx;
}

.footer-note {
  margin-top: 24rpx;
  padding: 0 8rpx 24rpx;
  font-size: 20rpx;
  line-height: 1.6;
  color: var(--ik-t3);
  text-align: center;
}

.start-btn {
  background: var(--ik-primary);
  color: var(--ik-on-primary);
  border-radius: 14rpx;
  font-size: 30rpx;
  padding: 10rpx 0;
}

.start-btn[disabled],
.start-btn.disabled {
  background: var(--ik-soft);
  color: var(--ik-t3);
}

.quiz-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 40rpx;
}

.quiz-progress {
  font-size: 25rpx;
  color: var(--ik-t2);
}

.quiz-exit {
  font-size: 24rpx;
  color: var(--ik-t3);
}

.progress-bar {
  height: 8rpx;
  background: var(--ik-line);
  border-radius: 4rpx;
  margin-top: 14rpx;
  overflow: hidden;
}

.progress-fill {
  height: 8rpx;
  background: var(--ik-primary);
  border-radius: 4rpx;
  transition: width 0.25s;
}

.quiz-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 32rpx;
}

.quiz-topic {
  font-size: 30rpx;
  font-weight: 600;
  color: var(--ik-t1);
}

.difficulty {
  font-size: 22rpx;
  color: var(--ik-primary);
  background: var(--ik-primary-weak);
  padding: 4rpx 16rpx;
  border-radius: 999rpx;
}

.quiz-sub {
  display: block;
  margin-top: 6rpx;
  font-size: 21rpx;
  color: var(--ik-t3);
}

.quiz-prompt {
  display: block;
  margin-top: 22rpx;
  font-size: 31rpx;
  line-height: 1.7;
  color: var(--ik-t1);
  white-space: pre-wrap;
}

.quiz-figure {
  width: 100%;
  margin-top: 16rpx;
}

.choices {
  margin-top: 24rpx;
}

.choice {
  display: flex;
  align-items: flex-start;
  padding: 24rpx;
  background: var(--ik-card);
  border: 2rpx solid var(--ik-line);
  border-radius: 14rpx;
  margin-bottom: 16rpx;
}

.choice.selected {
  border-color: var(--ik-primary);
  background: var(--ik-primary-weak);
}

.choice.correct {
  border-color: var(--ik-success);
  background: var(--ik-success-weak);
}

.choice.wrong {
  border-color: var(--ik-danger);
  background: var(--ik-danger-weak);
}

.choice-key {
  width: 44rpx;
  height: 44rpx;
  line-height: 44rpx;
  text-align: center;
  border-radius: 50%;
  background: var(--ik-soft);
  color: var(--ik-t2);
  font-size: 23rpx;
  margin-right: 16rpx;
  flex-shrink: 0;
}

.choice-text {
  flex: 1;
  font-size: 28rpx;
  line-height: 1.6;
  color: var(--ik-t1);
}

.choice-figure {
  flex: 1;
  width: 100%;
}

.answer-input {
  margin-top: 28rpx;
}

.input {
  height: 88rpx;
  padding: 0 24rpx;
  background: var(--ik-card);
  border: 2rpx solid var(--ik-line);
  border-radius: 14rpx;
  font-size: 28rpx;
}

.feedback {
  margin-top: 24rpx;
  padding: 22rpx;
  border-radius: 14rpx;
}

.feedback.ok {
  background: var(--ik-success-weak);
}

.feedback.bad {
  background: var(--ik-danger-weak);
}

.feedback-title {
  display: block;
  font-size: 28rpx;
  font-weight: 600;
  color: var(--ik-t1);
}

.feedback-text {
  display: block;
  margin-top: 8rpx;
  font-size: 24rpx;
  line-height: 1.6;
  color: var(--ik-t2);
}

.quiz-actions {
  margin-top: 28rpx;
}

.primary {
  background: var(--ik-primary);
  color: var(--ik-on-primary);
  border-radius: 14rpx;
  font-size: 30rpx;
  padding: 10rpx 0;
}

.primary[disabled],
.primary.disabled {
  background: var(--ik-soft);
}

.result-hero {
  background: var(--ik-card);
  border-radius: 16rpx;
  padding: 28rpx;
  margin-top: 40rpx;
}

.result-title {
  display: block;
  font-size: 38rpx;
  font-weight: 700;
  color: var(--ik-t1);
}

.result-sub {
  display: block;
  margin-top: 8rpx;
  font-size: 24rpx;
  color: var(--ik-t3);
}

.counts {
  display: flex;
  flex-wrap: wrap;
  background: var(--ik-card);
  border-radius: 16rpx;
  padding: 20rpx 10rpx;
  margin-top: 20rpx;
}

.count {
  flex: 1;
  min-width: 18%;
  box-sizing: border-box;
  text-align: center;
  padding: 8rpx 0;
}

.num {
  display: block;
  font-size: 38rpx;
  font-weight: 700;
  color: var(--ik-primary);
}

.weak-num {
  color: var(--ik-danger);
}

.label {
  display: block;
  margin-top: 2rpx;
  font-size: 21rpx;
  color: var(--ik-t3);
}

.status-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 22rpx;
  border-radius: 12rpx;
  margin-top: 16rpx;
}

.status-banner.mastered {
  background: var(--ik-success-weak);
}

.status-banner.unstable {
  background: var(--ik-warn-weak);
}

.status-banner.weak {
  background: var(--ik-danger-weak);
}

.status-banner.untested,
.status-banner.insufficient {
  background: var(--ik-soft);
}

.status-name {
  font-size: 28rpx;
  font-weight: 600;
  color: var(--ik-t1);
}

.status-value {
  font-size: 26rpx;
  color: var(--ik-primary);
}

.pill-list {
  margin-top: 12rpx;
}

.pill {
  display: inline-block;
  padding: 8rpx 20rpx;
  margin: 0 12rpx 12rpx 0;
  border-radius: 999rpx;
  font-size: 24rpx;
}

.pill.weak {
  background: var(--ik-danger-weak);
  color: var(--ik-danger);
}

.path {
  margin-top: 18rpx;
  padding-top: 18rpx;
  border-top: 1rpx solid var(--ik-line);
}

.path-label {
  display: block;
  font-size: 23rpx;
  color: var(--ik-t3);
}

.path-text {
  display: block;
  margin-top: 6rpx;
  font-size: 26rpx;
  line-height: 1.7;
  color: var(--ik-t1);
}

.chapter-row {
  padding: 18rpx 0;
  border-bottom: 1rpx solid var(--ik-line);
}

.chapter-row-main {
  display: flex;
  flex-direction: column;
}

.chapter-row-name {
  font-size: 26rpx;
  color: var(--ik-t1);
}

.chapter-row.weak .chapter-row-name {
  color: var(--ik-danger);
  font-weight: 600;
}

.chapter-row-meta {
  margin-top: 4rpx;
  font-size: 21rpx;
  color: var(--ik-t3);
}

.note {
  margin-top: 20rpx;
  padding: 20rpx 24rpx;
  background: var(--ik-warn-weak);
  border-radius: 12rpx;
  font-size: 23rpx;
  color: var(--ik-warn-strong);
  line-height: 1.6;
}

.result-actions {
  margin-top: 28rpx;
}

.ghost {
  background: var(--ik-card);
  color: var(--ik-primary);
  border: 2rpx solid var(--ik-line);
  border-radius: 14rpx;
  font-size: 28rpx;
  margin-top: 14rpx;
}

/* ---------- 上次会话恢复 ---------- */
.resume-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--ik-card);
  border-left: 8rpx solid var(--ik-primary);
  border-radius: 16rpx;
  padding: 22rpx 24rpx;
  margin-bottom: 20rpx;
}

.resume-main {
  flex: 1;
  min-width: 0;
}

.resume-title {
  display: block;
  font-size: 27rpx;
  font-weight: 600;
  color: var(--ik-t1);
}

.resume-sub {
  display: block;
  margin-top: 4rpx;
  font-size: 21rpx;
  color: var(--ik-t3);
}

.resume-actions {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  margin-left: 16rpx;
}

.small-btn {
  font-size: 23rpx;
  padding: 0 22rpx;
  height: 60rpx;
  line-height: 60rpx;
  margin: 0 0 0 12rpx;
  border-radius: 999rpx;
}

.resume-btn.primary {
  background: var(--ik-primary);
  color: var(--ik-on-primary);
}

.resume-btn.ghost {
  background: var(--ik-soft);
  color: var(--ik-t2);
  border: none;
  margin-top: 0;
}

/* ---------- 逐点清单 ---------- */
.breakdown-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}

.section-count {
  font-size: 22rpx;
  color: var(--ik-t3);
}

.filter-scroll {
  white-space: nowrap;
  margin-top: 16rpx;
}

.filter-chips {
  display: inline-flex;
}

.filter-chip {
  display: inline-flex;
  align-items: center;
  padding: 10rpx 22rpx;
  margin-right: 12rpx;
  border-radius: 999rpx;
  background: var(--ik-soft);
  font-size: 23rpx;
  color: var(--ik-t2);
}

.filter-chip.active {
  background: var(--ik-primary);
  color: var(--ik-on-primary);
}

.filter-count {
  margin-left: 8rpx;
  font-size: 20rpx;
  opacity: 0.75;
}

.assess-group {
  margin-top: 18rpx;
  border-top: 1rpx solid var(--ik-line);
}

.assess-group-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18rpx 4rpx 10rpx;
}

.assess-group-main {
  flex: 1;
  min-width: 0;
}

.assess-group-name {
  display: block;
  font-size: 26rpx;
  font-weight: 600;
  color: var(--ik-t1);
}

.assess-group-meta {
  display: block;
  margin-top: 4rpx;
  font-size: 20rpx;
  color: var(--ik-t3);
}

.assess-rows {
  padding-bottom: 6rpx;
}

.assess-row {
  padding: 16rpx 16rpx;
  margin-bottom: 10rpx;
  background: var(--ik-soft);
  border-radius: 12rpx;
}

.assess-line {
  display: flex;
  align-items: center;
}

.status-pill {
  display: inline-block;
  flex-shrink: 0;
  padding: 2rpx 14rpx;
  margin-right: 12rpx;
  border-radius: 999rpx;
  font-size: 20rpx;
  font-weight: 600;
}

.status-pill.proficient {
  background: var(--ik-success-weak);
  color: var(--ik-success);
}

.status-pill.mastered {
  background: var(--ik-success-weak);
  color: var(--ik-success);
}

.status-pill.unstable {
  background: var(--ik-warn-weak);
  color: var(--ik-warn-strong);
}

.status-pill.weak {
  background: var(--ik-danger-weak);
  color: var(--ik-danger);
}

.status-pill.untested,
.status-pill.insufficient,
.status-pill.pending {
  background: var(--ik-card);
  color: var(--ik-t3);
}

.assess-name {
  flex: 1;
  min-width: 0;
  font-size: 26rpx;
  color: var(--ik-t1);
}

.assess-meta {
  display: block;
  margin-top: 6rpx;
  font-size: 21rpx;
  color: var(--ik-t3);
}

.assess-actions {
  display: flex;
  align-items: center;
  margin-top: 10rpx;
}

.mini-link {
  font-size: 22rpx;
  color: var(--ik-primary);
  margin-right: 26rpx;
}

.proficient-num {
  color: var(--ik-success);
}
</style>
