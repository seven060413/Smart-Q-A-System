<template>
  <view class="page">
    <!-- 聊天消息区 -->
    <scroll-view class="chat" scroll-y :scroll-into-view="scrollTo" scroll-with-animation>
      <!-- 欢迎提示 -->
      <view v-if="messages.length === 0 && !loading" class="welcome">
        <text class="welcome-emoji">📚</text>
        <text class="welcome-text">我是小学数学助教，问我教材里的知识吧～\n例如：为什么异分母分数相加要先通分</text>
      </view>

      <!-- 消息列表 -->
      <view v-for="(msg, i) in messages" :key="i" :id="'msg-' + i" class="msg-row">
        <!-- 用户气泡（右） -->
        <view v-if="msg.role === 'user'" class="msg msg-user">
          <view class="bubble bubble-user">{{ msg.text }}</view>
        </view>

        <!-- AI 回答气泡（左） -->
        <view v-else class="msg msg-ai">
          <view class="bubble bubble-ai">
            <!-- 拒答卡 -->
            <view v-if="msg.refused" class="refuse-card">
              <view class="refuse-title">⚠️ {{ msg.answer }}</view>
              <view v-if="msg.knowledge_point" class="refuse-closest">最接近知识点：{{ msg.knowledge_point }}</view>
            </view>

            <!-- 正常回答 -->
            <template v-else>
              <view class="head">
                <text class="chip">{{ msg.knowledge_point }}</text>
                <text class="source">📚 {{ msg.source }}</text>
              </view>

              <!-- 三层折叠：前置知识 -->
              <view class="section" @click="toggle(msg, 'pre')">
                <view class="section-head">
                  <text>📖 前置知识</text>
                  <text class="arrow">{{ msg.open.pre ? '▾' : '▸' }}</text>
                </view>
                <view v-if="msg.open.pre" class="section-body">
                  <view v-for="(g, j) in msg.prerequisite_gaps" :key="j" class="gap">
                    <text class="gap-name">{{ g.name }}</text>
                    <text class="gap-tag" :class="g.required ? 't-required' : 't-suggest'">{{ g.required ? '必需' : '建议' }}</text>
                  </view>
                  <text v-if="msg.prerequisite_gaps.length === 0" class="empty">无</text>
                </view>
              </view>

              <!-- 三层折叠：本体讲解 -->
              <view class="section" @click="toggle(msg, 'body')">
                <view class="section-head">
                  <text>💡 本体讲解</text>
                  <text class="arrow">{{ msg.open.body ? '▾' : '▸' }}</text>
                </view>
                <view v-if="msg.open.body" class="section-body">
                  <text class="answer">{{ msg.answer }}</text>
                </view>
              </view>

              <!-- 三层折叠：巩固练习 -->
              <view class="section" @click="toggle(msg, 'cons')">
                <view class="section-head">
                  <text>✏️ 巩固练习</text>
                  <text class="arrow">{{ msg.open.cons ? '▾' : '▸' }}</text>
                </view>
                <view v-if="msg.open.cons" class="section-body">
                  <view v-for="(c, j) in msg.learning_path.consolidation" :key="j" class="gap">
                    <text class="gap-name">{{ c }}</text>
                  </view>
                  <text v-if="msg.learning_path.consolidation.length === 0" class="empty">无</text>
                </view>
              </view>

              <button class="path-btn" @click="goPath(msg)">🗺 查看学习路径</button>
            </template>
          </view>
        </view>
      </view>

      <!-- 思考中 -->
      <view v-if="loading" class="msg msg-ai">
        <view class="bubble bubble-ai typing">思考中…</view>
      </view>
    </scroll-view>

    <!-- 底部输入栏 -->
    <view class="input-bar">
      <input
        class="input"
        v-model="question"
        placeholder="输入你的问题…"
        confirm-type="send"
        :disabled="loading"
        @confirm="send"
      />
      <button class="send-btn" :disabled="loading || !question" @click="send">发送</button>
    </view>
  </view>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { askQuestion } from '../../api.js'
import { store } from '../../store.js'

const question = ref('')
const loading = ref(false)
const messages = reactive([])
const scrollTo = ref('')

function scrollBottom() {
  // 先清空再赋值，触发 scroll-into-view 重新定位
  scrollTo.value = ''
  setTimeout(() => {
    scrollTo.value = 'msg-' + (messages.length - 1)
  }, 50)
}

function send() {
  const q = question.value.trim()
  if (!q || loading.value) return
  messages.push({ role: 'user', text: q })
  question.value = ''
  loading.value = true
  scrollBottom()

  askQuestion(q)
    .then((data) => {
      messages.push({
        role: 'ai',
        answer: data.answer || '',
        knowledge_point: data.knowledge_point || '',
        prerequisite_gaps: data.prerequisite_gaps || [],
        learning_path: data.learning_path || { prerequisites: [], body: '', consolidation: [] },
        source: data.source || '',
        refused: !!data.refused,
        open: { pre: false, body: true, cons: false },
      })
    })
    .catch(() => {
      messages.push({
        role: 'ai',
        refused: true,
        answer: '网络请求失败，请检查后端是否启动、地址是否配置正确',
        knowledge_point: '',
        prerequisite_gaps: [],
        learning_path: { prerequisites: [], body: '', consolidation: [] },
        source: '',
        open: { pre: false, body: true, cons: false },
      })
    })
    .finally(() => {
      loading.value = false
      scrollBottom()
    })
}

function toggle(msg, key) {
  msg.open[key] = !msg.open[key]
}

function goPath(msg) {
  store.learningPath = msg.learning_path
  store.knowledgePoint = msg.knowledge_point
  store.source = msg.source
  uni.navigateTo({ url: '/pages/path/path' })
}
</script>

<style>
.page {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f5f6f8;
}

.chat {
  flex: 1;
  overflow: hidden;
  padding: 24rpx;
  box-sizing: border-box;
}

/* 欢迎 */
.welcome {
  margin-top: 120rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
}
.welcome-emoji {
  font-size: 96rpx;
  margin-bottom: 24rpx;
}
.welcome-text {
  font-size: 28rpx;
  color: #999;
  text-align: center;
  line-height: 1.6;
}

/* 消息行 */
.msg-row {
  margin-bottom: 24rpx;
}
.msg {
  display: flex;
}
.msg-user {
  justify-content: flex-end;
}
.msg-ai {
  justify-content: flex-start;
}

/* 气泡 */
.bubble {
  max-width: 86%;
  padding: 20rpx 24rpx;
  border-radius: 20rpx;
  font-size: 28rpx;
  line-height: 1.6;
  word-break: break-all;
}
.bubble-user {
  background: #2b6cb0;
  color: #fff;
  border-top-right-radius: 6rpx;
}
.bubble-ai {
  background: #fff;
  color: #333;
  border-top-left-radius: 6rpx;
  box-shadow: 0 2rpx 8rpx rgba(0, 0, 0, 0.04);
}
.typing {
  color: #999;
}

/* AI 头部：知识点 + 出处 */
.head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12rpx;
  margin-bottom: 16rpx;
}
.chip {
  background: #e8f0fb;
  color: #2b6cb0;
  font-size: 24rpx;
  padding: 4rpx 16rpx;
  border-radius: 999rpx;
}
.source {
  font-size: 22rpx;
  color: #999;
}

/* 折叠面板 */
.section {
  border-top: 1rpx solid #f0f0f0;
  padding: 16rpx 0;
}
.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 28rpx;
  font-weight: 600;
  color: #444;
}
.arrow {
  color: #bbb;
  font-size: 28rpx;
}
.section-body {
  margin-top: 12rpx;
}
.answer {
  font-size: 28rpx;
  color: #333;
  white-space: pre-wrap;
}
.gap {
  display: flex;
  align-items: center;
  gap: 12rpx;
  padding: 8rpx 0;
}
.gap-name {
  font-size: 28rpx;
  color: #333;
}
.gap-tag {
  font-size: 20rpx;
  padding: 2rpx 12rpx;
  border-radius: 999rpx;
}
.t-required {
  background: #fde8e8;
  color: #e53e3e;
}
.t-suggest {
  background: #fff7e6;
  color: #dd6b20;
}
.empty {
  font-size: 26rpx;
  color: #bbb;
}

/* 拒答卡 */
.refuse-card {
  background: #fff5f5;
  border: 1rpx solid #feb2b2;
  border-radius: 16rpx;
  padding: 24rpx;
}
.refuse-title {
  font-size: 30rpx;
  font-weight: 600;
  color: #e53e3e;
  margin-bottom: 12rpx;
}
.refuse-closest {
  font-size: 26rpx;
  color: #9b2c2c;
}

/* 学习路径按钮 */
.path-btn {
  margin-top: 20rpx;
  background: #e8f0fb;
  color: #2b6cb0;
  font-size: 26rpx;
  border-radius: 999rpx;
  padding: 0 24rpx;
  line-height: 64rpx;
  border: none;
}
.path-btn::after {
  border: none;
}

/* 输入栏 */
.input-bar {
  display: flex;
  align-items: center;
  padding: 16rpx 24rpx;
  padding-bottom: calc(16rpx + env(safe-area-inset-bottom));
  background: #fff;
  border-top: 1rpx solid #eee;
}
.input {
  flex: 1;
  height: 72rpx;
  background: #f2f3f5;
  border-radius: 36rpx;
  padding: 0 28rpx;
  font-size: 28rpx;
}
.send-btn {
  margin-left: 16rpx;
  width: 140rpx;
  height: 72rpx;
  line-height: 72rpx;
  background: #2b6cb0;
  color: #fff;
  font-size: 28rpx;
  border-radius: 36rpx;
  border: none;
  padding: 0;
}
.send-btn[disabled] {
  background: #b0c4de;
  color: #fff;
}
.send-btn::after {
  border: none;
}
</style>
