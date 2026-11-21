<template>
  <scroll-view class="my-scroll" scroll-y>
    <view class="my-page" :style="{ paddingTop: statusBarHeight + 'px' }">

      <text class="page-title">我的</text>

      <ProfileCard
        :avatar="avatar"
        :name="displayName"
        :subtitle="subtitle"
        :badge="gradeBadge"
        :badge-muted="!gradeText"
        :action-text="loggedIn ? '编辑' : '登录'"
        @action="onProfileAction"
      />

      <!-- 最近知识点卡：有数据时才显示 -->
      <view v-if="knowledgePoint" class="knowledge-card">
        <text class="knowledge-label">最近学习</text>
        <text class="knowledge-title">{{ knowledgePoint }}</text>
        <text v-if="knowledgeSource" class="knowledge-source">📚 {{ knowledgeSource }}</text>
        <view class="knowledge-action" @click="go('/pages/path/path')">
          查看学习路径 ›
        </view>
      </view>

      <GroupCard title="学习数据" :items="studyItems" variant="tiles" :cols="3" />
      <GroupCard title="账号" :items="accountItems" />
      <GroupCard title="设置" :items="settingItems" />
      <GroupCard
        v-if="pluginMenus.length"
        title="插件功能"
        :items="pluginItems"
      />

      <text class="footer-hint">
        {{ loggedIn
          ? '账号资料、历史记录与学习数据会同步到你的账号。'
          : '游客也可以直接问答；登录后可保存账号状态和聊天记录。' }}
      </text>
    </view>
  </scroll-view>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import ProfileCard from '../ui/ProfileCard.vue'
import GroupCard from '../ui/GroupCard.vue'
import { listVideoLibrary, listWrongQuestions } from '../../api.js'
import { store } from '../../store.js'
import { pluginMenus, runPluginMenu } from '../../plugin/menus.js'

const props = defineProps({
  refreshKey: { type: Number, default: 0 },
})

const statusBarHeight = (() => {
  try {
    return uni.getSystemInfoSync().statusBarHeight || 0
  } catch (e) {
    return 0
  }
})()

const avatar = ref('')
const nickname = ref('')
const wrongCount = ref(0)
const videoCount = ref(0)

const loggedIn = computed(() => !!(store.auth.user && store.auth.token))

const displayName = computed(() => {
  if (!store.auth.ready) return '…'
  if (!loggedIn.value) return '未登录'
  return nickname.value || store.auth.user.display_name || store.auth.user.username || '用户'
})

const subtitle = computed(() => {
  if (!store.auth.ready) return '正在检查登录状态…'
  if (loggedIn.value) return '@' + (store.auth.user.username || '')
  return '游客模式'
})

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

const gradeText = computed(() => {
  const grade = store.auth.user && store.auth.user.grade
  return GRADE_LABELS[grade] || ''
})

// 登录用户未设置年级时给一个轻提示；游客不显示。
const gradeBadge = computed(() => {
  if (!loggedIn.value) return ''
  return gradeText.value || '未设置年级'
})

function loadLocalProfile() {
  const user = store.auth.user || {}
  // 本地缓存优先：编辑资料页写入后，从该页返回可立即看到新头像/昵称
  avatar.value = uni.getStorageSync('user_avatar') || user.avatar || ''
  nickname.value = uni.getStorageSync('custom_nickname') || user.display_name || ''
}
watch(() => props.refreshKey, () => {
  loadLocalProfile()
  loadWrongCount()
  loadVideoCount()
}, { immediate: true })
// 启动校验完成后，再用后端返回的头像/昵称补一次
watch(() => store.auth.ready, (ready) => {
  if (ready) {
    loadLocalProfile()
    loadWrongCount()
  }
})
watch(loggedIn, loadWrongCount)

function onProfileAction() {
  uni.navigateTo({ url: loggedIn.value ? '/pages/profile/edit' : '/pages/auth/auth' })
}

function go(url) {
  uni.navigateTo({ url })
}

const studyItems = computed(() => [
  {
    key: 'history',
    label: '历史会话',
    icon: 'history',
    tone: 'blue',
    action: () => go('/pages/history/history'),
  },
  {
    key: 'wrong',
    label: '错题集',
    icon: 'exclamation-circle',
    tone: 'red',
    tag: loggedIn.value ? String(wrongCount.value) : '',
    tagMuted: wrongCount.value === 0,
    action: goWrong,
  },
  {
    key: 'trend',
    label: '学情趋势',
    icon: 'arrow-rise',
    tone: 'green',
    action: goTrend,
  },
  {
    key: 'path',
    label: '学习路径',
    icon: 'branch',
    tone: 'teal',
    action: () => go('/pages/path/path'),
  },
  {
    key: 'video',
    label: '视频讲解',
    icon: 'play-circle',
    tone: 'orange',
    tag: videoCount.value ? String(videoCount.value) : '',
    tagMuted: true,
    action: () => go('/pages/video-library/video-library'),
  },
  {
    key: 'knowledge',
    label: '当前知识点',
    icon: 'book',
    tone: 'purple',
    action: () => go('/pages/path/path'),
  },
])

function goWrong() {
  if (!loggedIn.value) return go('/pages/auth/auth')
  go('/pages/wrong/wrong')
}

function goTrend() {
  if (!loggedIn.value) return go('/pages/auth/auth')
  go('/pages/trend/trend')
}

async function loadWrongCount() {
  if (!loggedIn.value) {
    wrongCount.value = 0
    return
  }
  try {
    const data = await listWrongQuestions({ limit: 1, status: 'open' })
    wrongCount.value = data.total || 0
  } catch (e) {
    wrongCount.value = 0
  }
}

async function loadVideoCount() {
  try {
    const data = await listVideoLibrary({ pageSize: 1 })
    videoCount.value = data.total || 0
  } catch (e) {
    videoCount.value = 0
  }
}

const accountItems = computed(() => loggedIn.value
  ? [
      {
        key: 'account',
        label: '账号信息',
        icon: 'user',
        tone: 'blue',
        action: () => go('/pages/auth/auth'),
      },
      {
        key: 'edit',
        label: '编辑资料',
        icon: 'edit',
        tone: 'teal',
        action: () => go('/pages/profile/edit'),
      },
    ]
  : [
      {
        key: 'login',
        label: '登录 / 注册',
        icon: 'user-add',
        tone: 'blue',
        action: () => go('/pages/auth/auth'),
      },
    ])

const knowledgePoint = computed(() => store.knowledgePoint || '')
const knowledgeSource = computed(() => store.source || '')

const settingItems = [
  {
    key: 'theme',
    label: '主题外观',
    icon: 'skin',
    tone: 'purple',
    action: () => go('/pages/theme/theme'),
  },
  {
    key: 'about',
    label: '关于',
    icon: 'info-circle',
    tone: 'blue',
    action: showAbout,
  },
]

const pluginItems = computed(() => pluginMenus.map((m) => ({
  key: m.id,
  label: m.label,
  icon: 'apps',
  tone: 'teal',
  action: () => runPluginMenu(m),
})))

function showAbout() {
  uni.showModal({
    title: '数学知识问答',
    content: 'K12 数学知识图谱问答助手\n前端：uni-app + Vue 3 + wot-ui',
    showCancel: false,
  })
}
</script>

<style>
.my-scroll {
  height: 100%;
  background: var(--ik-bg);
}
.my-page {
  min-height: 100%;
  padding: 24rpx 32rpx 48rpx;
  box-sizing: border-box;
}
.page-title {
  display: block;
  font-size: 40rpx;
  font-weight: 700;
  color: var(--ik-t1);
  margin: 8rpx 0 28rpx;
}
.knowledge-card {
  background: var(--ik-card);
  border-radius: var(--ik-radius);
  padding: 28rpx;
  margin-bottom: 24rpx;
  box-sizing: border-box;
}
.knowledge-label {
  display: block;
  font-size: 24rpx;
  color: var(--ik-t3);
  margin-bottom: 10rpx;
}
.knowledge-title {
  display: block;
  font-size: 34rpx;
  font-weight: 700;
  color: var(--ik-t1);
  line-height: 1.4;
}
.knowledge-source {
  display: block;
  margin-top: 8rpx;
  font-size: 24rpx;
  color: var(--ik-t2);
}
.knowledge-action {
  margin-top: 18rpx;
  font-size: 26rpx;
  color: var(--ik-primary);
}
.footer-hint {
  display: block;
  margin-top: 16rpx;
  padding: 0 8rpx;
  font-size: 24rpx;
  line-height: 1.6;
  color: var(--ik-t3);
  text-align: center;
}
</style>
