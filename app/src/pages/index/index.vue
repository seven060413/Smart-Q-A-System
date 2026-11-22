<template>
  <view class="tab-root theme-root" :class="{ 'is-dark': isDark }" :style="themeVars">
    <!-- 主题插件背景图：手机/平板自动选图 -->
    <ThemeBackground />

    <!-- 引入侧边栏（放在 swiper 外层，抽屉可盖住底部导航） -->
    <Sidebar
      :visible="showSidebar"
      :currentMenu="currentMenu"
      :drag-offset="edgeDrag"
      :dragging="edgeDragging"
      @close="showSidebar = false"
      @select-menu="onSelectMenu"
    />

    <!-- 左边缘手势区：高于 swiper、低于抽屉，避免和 tab 左右滑动抢手势 -->
    <view
      v-if="!showSidebar"
      class="drawer-edge"
      @touchstart.stop="onEdgeStart"
      @touchmove.stop.prevent="onEdgeMove"
      @touchend.stop="onEdgeEnd"
      @touchcancel.stop="onEdgeEnd"
    />

    <!-- 宿主页：item 0 = 学习首页，item 1 = 我的 -->
    <swiper
      class="tab-swiper"
      :current="activeTab"
      :duration="280"
      easing-function="easeOutCubic"
      :disable-touch="showSidebar"
      @change="onSwiperChange"
    >
      <swiper-item class="tab-swiper-item">
        <view class="page">
    <!-- 自定义导航栏：无标题，左侧菜单 + 右侧快捷操作 -->
    <view class="topbar" :style="{ paddingTop: statusBarHeight + 'px' }">
      <view
        class="topbar-icon-btn"
        aria-label="打开菜单"
        @click="showSidebar = true"
      >
        <wd-icon name="menu" custom-class="topbar-icon" />
      </view>

      <view class="topbar-actions">
        <view
          v-if="store.auth.user"
          class="topbar-icon-btn"
          aria-label="新对话"
          @click="newConversation"
        >
          <wd-icon name="plus" custom-class="topbar-icon topbar-icon--primary" />
        </view>
        <view
          class="topbar-icon-btn"
          aria-label="语音设置"
          @click="showVoiceSettings = true"
        >
          <wd-icon name="settings" custom-class="topbar-icon" />
        </view>
        <view
          class="topbar-icon-btn"
          :class="{ 'is-off': !autoPlayEnabled }"
          :aria-label="autoPlayEnabled ? '关闭自动朗读' : '开启自动朗读'"
          @click="toggleAutoPlay"
        >
          <wd-icon
            :name="autoPlayEnabled ? 'sound' : 'mute'"
            custom-class="topbar-icon"
          />
        </view>
      </view>
    </view>

    <!-- 聊天消息区 -->
    <scroll-view class="chat" scroll-y :scroll-into-view="scrollTo" scroll-with-animation>
      <!-- 今日建议：错题 / 趋势 / 聊天三路信号，年级只影响排序 -->
      <view
        v-if="todaySuggestions.length && !todayDismissed"
        class="today-card"
      >
        <view class="today-head">
          <view class="today-head-main">
            <text class="today-title">今日建议</text>
            <text class="today-sub">根据你的错题、趋势和聊天记录</text>
          </view>
          <text class="today-close" @click.stop="dismissTodaySuggestions">×</text>
        </view>
        <view class="today-list">
          <view
            v-for="item in todaySuggestions"
            :key="item.node_key || item.kind"
            class="today-item"
            @click="openTodaySuggestion(item)"
          >
            <view class="today-item-main">
              <view class="today-item-title">
                <text class="today-badge" :class="'is-' + item.kind">{{ item.badge }}</text>
                <text class="today-name">{{ item.name }}</text>
                <text
                  v-if="item.grade && todayGrade && item.grade !== todayGrade"
                  class="today-grade"
                >{{ gradeLabel(item.grade) }}</text>
              </view>
              <text class="today-reason">{{ item.reason }}</text>
            </view>
            <text class="today-arrow">›</text>
          </view>
        </view>
      </view>

      <!-- 历史消息分页 -->
      <view v-if="hasEarlier" class="load-earlier" @click="loadEarlier">
        {{ loadingEarlier ? '加载中…' : '加载更早的消息' }}
      </view>

      <!-- 欢迎提示 -->
      <view v-if="messages.length === 0 && !loading && !historyLoading" class="welcome">
        <image src="/static/math-assistant.svg" class="welcome-mark" mode="aspectFit" />
        <text class="welcome-text">我是中小学数学助教，选一个问题开始吧</text>
        <view class="quick-list">
          <view
            v-for="q in quickQuestions"
            :key="q"
            class="quick-item"
            @click="askQuick(q)"
          >
            {{ q }}
          </view>
        </view>
      </view>

      <!-- 消息列表 -->
      <view
        v-for="(msg, i) in messages"
        :key="msg.id || i"
        :id="msg.id ? 'message-' + msg.id : 'msg-' + i"
        class="msg-row"
      >
        <view v-if="msg.role === 'user'" class="msg msg-user">
          <view class="msg-content">
            <view v-if="msg.attachment" class="question-card">
              <view class="question-card-head"><text>{{ msg.attachment.mediaType === 'application/pdf' ? 'PDF 题目' : '题目图片' }}</text><text class="question-status">{{ msg.attachment.statusText }}</text></view>
              <text v-if="msg.attachment.errorText" class="question-error">{{ msg.attachment.errorText }}</text>
              <button v-if="msg.attachment.statusText === '解答失败'" class="question-retry" :disabled="attachmentBusy" @click="solveMessageAttachment(msg)">重试解答</button>
              <button v-if="msg.attachment.statusText === '上传失败'" class="question-retry" :disabled="attachmentBusy" @click="retryAttachmentUpload(msg)">重新上传</button>
              <text v-if="typeof msg.attachment.ocr_confidence === 'number' && msg.attachment.ocr_confidence < 0.7" class="ocr-warning">识别结果可能有误，请检查数字、分数和运算符</text>
              <image v-if="msg.attachment.filePath && msg.attachment.mediaType !== 'application/pdf'" :src="msg.attachment.filePath" mode="widthFix" class="question-image" @click="previewMessageAttachment(msg)" />
              <view class="question-file">{{ msg.attachment.name }} · {{ formatBytes(msg.attachment.size) }}<text v-if="msg.attachment.pageCount"> · {{ msg.attachment.pageCount }} 页</text></view>
              <button v-if="msg.attachment.id" class="question-preview" @click="previewMessageAttachment(msg)">{{ msg.attachment.mediaType === 'application/pdf' ? '打开 PDF 文件' : '查看原图' }}</button>
              <view v-if="msg.attachment.failedPages && msg.attachment.failedPages.length" class="question-error">第 {{ msg.attachment.failedPages.join('、') }} 页识别失败，已保留其他页面结果</view>
              <text class="question-label">识别出的题目</text>
              <textarea v-model="msg.attachment.ocrText" class="question-text" maxlength="20000" placeholder="等待识别或请输入题目" @input="onMessageOcrInput(msg)" />
              <view class="question-actions">
                <button v-if="msg.attachment.id" :disabled="attachmentBusy" @click="recognizeMessageAttachment(msg)">重新识别</button>
                <button v-if="pendingQuestions.length > 1 && msg.attachment.id && msg.attachment.id === attachment.id" :disabled="attachmentBusy" @click="questionPickerOpen = true">选择题目</button>
                <button :disabled="attachmentBusy || !msg.attachment.id || !msg.attachment.ocrText.trim()" @click="solveMessageAttachment(msg)">{{ attachmentBusy ? '正在处理…' : '重新生成解答' }}</button>
              </view>
            </view>
            <view v-else class="bubble bubble-user">{{ msg.text }}</view>
          </view>
        </view>

        <view v-else class="msg msg-ai">
          <image src="/static/math-assistant.svg" class="message-avatar" mode="aspectFill" />
          <view class="msg-content">
            <view class="assistant-name">数学助教</view>
            <view class="bubble bubble-ai">
            <view v-if="msg.failed" class="failed-card">
              <view class="failed-title">回答生成失败</view>
              <view class="failed-text">{{ msg.error_message || '请稍后重新提问' }}</view>
              <button v-if="msg.retryQuestion" class="retry-btn" @click="retry(msg)">重新提问</button>
            </view>

            <view v-else-if="msg.refused" class="refuse-card">
              <view class="refuse-title"><MathText :text="msg.answer" inline /></view>
              <view v-if="msg.knowledge_point" class="refuse-closest">最接近知识点：{{ msg.knowledge_point }}</view>
            </view>

            <template v-else>
              <view class="answer-summary">
                <text class="summary-label">{{ msg.knowledge_confidence < 0.35 ? '知识点未可靠匹配' : '知识点匹配' }}</text>
                <view class="head">
                <text class="chip">{{ msg.knowledge_point }}</text>
                <text v-if="msg.knowledge_confidence !== undefined" class="confidence">匹配 {{ Math.round(msg.knowledge_confidence * 100) }}%</text>
                </view>
                <text v-if="msg.source" class="source">{{ msg.source }}</text>
              </view>
              <view v-if="msg.knowledge_candidates && msg.knowledge_candidates.length" class="candidate-list">
                <text class="candidate-label">请选择更符合的知识点</text>
                <button v-for="candidate in msg.knowledge_candidates" :key="candidate.id" class="candidate-item candidate-button" :disabled="attachmentBusy" @click.stop="solveWithCandidate(msg, candidate)">{{ candidate.name }} · {{ Math.round(candidate.confidence * 100) }}%</button>
              </view>

              <!-- 三层折叠：前置知识 -->
              <view class="section" @click="toggle(msg, 'pre')">
                <view class="section-head">
                  <text>前置知识</text>
                  <text class="arrow">{{ msg.open.pre ? '▾' : '▸' }}</text>
                </view>
                <view v-if="msg.open.pre" class="section-body" @click.stop>
                  <view v-for="(g, j) in msg.prerequisite_gaps" :key="g.id || j" class="gap-block">
                    <view class="gap">
                      <text class="gap-name">{{ g.name }}</text>
                      <text class="gap-tag" :class="g.required ? 't-required' : 't-suggest'">{{ g.required ? '必需' : '建议' }}</text>
                    </view>

                    <view v-if="g.videos && g.videos.length" class="video-list">
                      <view
                        v-for="(v, k) in g.videos"
                        :key="v.video_id"
                        class="video-card"
                        @click.stop="openVideo(g, v)"
                      >
                        <view class="video-cover">
                          <image v-if="v.cover_url && !v.coverFailed" :src="v.cover_url" mode="aspectFill" class="video-cover-img" referrerpolicy="no-referrer" @error="v.coverFailed = true" />
                          <view v-else class="video-cover-fallback">B站</view>
                          <view class="video-play">▶</view>
                          <text v-if="v.duration_seconds" class="video-duration">{{ formatDuration(v.duration_seconds) }}</text>
                        </view>
                        <view class="video-meta">
                          <text class="video-title">{{ v.title }}</text>
                          <text class="video-author">{{ v.author || 'B 站' }}</text>
                        </view>
                      </view>

                      <!-- #ifdef H5 -->
                      <view
                        v-if="activeVideo && activeVideo.node_key === g.id"
                        class="video-player"
                        @click.stop
                      >
                        <iframe
                          :src="activeVideo.embed_url"
                          class="video-iframe"
                          allow="autoplay; fullscreen; picture-in-picture"
                          referrerpolicy="no-referrer-when-downgrade"
                          frameborder="0"
                        ></iframe>
                        <view class="video-actions">
                          <text class="video-action" @click.stop="closeVideo">收起播放器</text>
                          <text class="video-action" @click.stop="openMobilePlayer(activeVideo)">移动版播放器</text>
                          <text class="video-action" @click.stop="openWatchPage(activeVideo)">在 B 站打开</text>
                        </view>
                        <text v-if="!h264Supported" class="video-hint warn">当前浏览器缺少 H.264 解码能力，请改用 Chrome/Edge，或点“在 B 站打开”。</text>
                        <text class="video-hint">若提示“不支持 HTML5 播放器”，请点“移动版播放器”或“在 B 站打开”。</text>
                      </view>
                      <!-- #endif -->
                    </view>

                    <view v-else-if="g.videosLoaded" class="video-empty-row">
                      <text class="video-empty">暂无审核通过的视频</text>
                      <text class="video-retry" @click.stop="loadVideos(msg, true)">刷新</text>
                    </view>
                  </view>

                  <!-- 本体视频讲解：当前知识点自身的视频（前置 gap 不一定有视频） -->
                  <view v-if="msg.bodyVideos && msg.bodyVideos.length" class="video-list body-video-list">
                    <text class="video-section-label">本体视频讲解</text>
                    <view
                      v-for="(v, k) in msg.bodyVideos"
                      :key="v.video_id"
                      class="video-card"
                      @click.stop="openVideo({ id: msg.learning_path.body_id }, v)"
                    >
                      <view class="video-cover">
                        <image v-if="v.cover_url && !v.coverFailed" :src="v.cover_url" mode="aspectFill" class="video-cover-img" referrerpolicy="no-referrer" @error="v.coverFailed = true" />
                        <view v-else class="video-cover-fallback">B站</view>
                        <view class="video-play">▶</view>
                        <text v-if="v.duration_seconds" class="video-duration">{{ formatDuration(v.duration_seconds) }}</text>
                      </view>
                      <view class="video-meta">
                        <text class="video-title">{{ v.title }}</text>
                        <text class="video-author">{{ v.author || 'B 站' }}</text>
                      </view>
                    </view>

                    <!-- #ifdef H5 -->
                    <view
                      v-if="activeVideo && activeVideo.node_key === msg.learning_path.body_id"
                      class="video-player"
                      @click.stop
                    >
                      <iframe
                        :src="activeVideo.embed_url"
                        class="video-iframe"
                        allow="autoplay; fullscreen; picture-in-picture"
                        referrerpolicy="no-referrer-when-downgrade"
                        frameborder="0"
                      ></iframe>
                      <view class="video-actions">
                        <text class="video-action" @click.stop="closeVideo">收起播放器</text>
                        <text class="video-action" @click.stop="openMobilePlayer(activeVideo)">移动版播放器</text>
                        <text class="video-action" @click.stop="openWatchPage(activeVideo)">在 B 站打开</text>
                      </view>
                      <text v-if="!h264Supported" class="video-hint warn">当前浏览器缺少 H.264 解码能力，请改用 Chrome/Edge，或点“在 B 站打开”。</text>
                      <text class="video-hint">若提示“不支持 HTML5 播放器”，请点“移动版播放器”或“在 B 站打开”。</text>
                    </view>
                    <!-- #endif -->
                  </view>

                  <text v-if="msg.prerequisite_gaps.length === 0 && !(msg.bodyVideos && msg.bodyVideos.length)" class="empty">无前置知识</text>
                  <text v-if="msg.videosNoIds" class="video-empty">当前消息缺少知识点编号，请重新提问或刷新页面</text>
                  <text v-if="msg.videosError" class="video-empty">视频加载失败，重新展开可重试</text>
                </view>
              </view>

              <!-- 解题过程 -->
              <view class="section answer-section" @click="toggle(msg, 'body')">
                <view class="section-head">
                  <text>解题过程</text>

                  <text class="arrow">{{ msg.open.body ? '▾' : '▸' }}</text>
                </view>

                <view v-if="msg.open.body" class="section-body">
                  <view
                    v-for="(step, stepIndex) in answerStepList(msg)"
                    :key="stepIndex"
                    class="solution-step"
                  >
                    <view class="solution-step-head">
                      <text class="solution-step-no">{{ stepIndex + 1 }}</text>
                      <MathText
                        class="solution-step-title"
                        :text="step.title || `第 ${stepIndex + 1} 步`"
                        inline
                      />
                    </view>
                    <MathText class="solution-step-content" :text="step.content" />
                  </view>

    <view
      v-if="msg.final_answer || finalAnswer(msg.answer)"
      class="final-answer"
    >
      <text class="final-label">最终答案</text>
      <MathText class="final-text" :text="msg.final_answer || finalAnswer(msg.answer)" />
    </view>

    <view class="answer-actions">
      <button
        class="tts-btn"
        :class="{ 'tts-playing': playingIndex === i }"
        @click.stop="playTTS(getSpeechText(msg), i)"
      >
        {{ playingIndex === i ? '停止朗读' : '朗读答案' }}
      </button>
    </view>
  </view>
</view>

              <!-- 三层折叠：巩固练习 -->
              <view class="section" @click="toggle(msg, 'cons')">
                <view class="section-head">
                  <text>巩固练习</text>
                  <text class="section-count">{{ exerciseCount(msg) ? `有 ${exerciseCount(msg)} 道巩固练习` : '暂无巩固练习' }}</text>
                  <text class="arrow">{{ msg.open.cons ? '▾' : '▸' }}</text>
                </view>
                <view v-if="msg.open.cons" class="section-body">
                  <template v-if="exerciseCount(msg)">
                    <view v-for="(ex, j) in (msg.exercises && msg.exercises.length ? msg.exercises : msg.learning_path.exercises)" :key="j" class="exercise">
                      <text class="exercise-no">第 {{ j + 1 }} 题</text>
                      <MathText class="exercise-text" :text="ex" />
                    </view>
                  </template>
                  <template v-else-if="msg.learning_path.consolidation.length">
                    <text class="exercise-hint">图谱后续知识点（供参考）</text>
                    <view v-for="(c, j) in msg.learning_path.consolidation" :key="j" class="gap">
                      <text class="gap-name">{{ c }}</text>
                    </view>
                  </template>
                  <text v-else class="empty">暂无巩固练习</text>
                </view>
              </view>

                <button class="path-btn" @click="goPath(msg)">查看学习路径</button>
            </template>
            </view>
          </view>
        </view>
      </view>

      <!-- 加载历史会话 -->
      <view v-if="historyLoading" class="msg msg-ai">
        <view class="bubble bubble-ai typing">正在加载历史会话…</view>
      </view>

      <!-- 思考中 -->
      <view v-if="loading" class="msg msg-ai">
        <view class="bubble bubble-ai typing">思考中…</view>
      </view>
    </scroll-view>

    <!-- 底部输入区 -->
    <view class="composer">
      <view v-if="attachment.filePath && !attachmentMessage" class="attachment-draft">
        <view v-if="attachment.mediaType === 'application/pdf'" class="attachment-thumb attachment-pdf">PDF</view>
        <image v-else :src="attachment.filePath" mode="aspectFill" class="attachment-thumb" @click="previewDraftAttachment" />
        <view class="attachment-draft-meta">
          <text class="attachment-name">{{ attachment.name }}</text>
          <text class="attachment-size">{{ formatBytes(attachment.size) }} · {{ attachment.statusText }}</text>
        </view>
        <button class="attachment-remove" :disabled="attachmentBusy" aria-label="删除图片" @click="clearAttachment">×</button>
      </view>
      <view v-if="attachment.id && !attachmentMessage" class="attachment-text-editor">
        <textarea v-model="attachment.ocrText" maxlength="20000" placeholder="请核对或修改识别出的题目" @input="syncOcrText" />
        <view class="attachment-actions">
          <button :disabled="attachmentBusy" @click="recognizeAttachment">重新识别</button>
          <button :disabled="attachmentBusy || !attachment.ocrText.trim()" @click="solveAttachment">重新生成解答</button>
        </view>
      </view>
      <view class="input-bar">
        <textarea
          class="input"
          v-model="question"
          placeholder="输入你的问题…"
          :disabled="loading || recordStarting || recordState !== 'idle'"
          :auto-height="true"
          :maxlength="-1"
          confirm-type="send"
          @confirm="send"
        />
        <button
          v-if="voiceSupported"
          class="voice-btn"
          :class="[recordState, { starting: recordStarting, 'will-cancel': voiceWillCancel }]"
          :disabled="loading || recordState === 'uploading'"
          aria-label="按住说话，松开发送"
          @touchstart.stop.prevent="onVoiceStart"
          @touchmove.stop.prevent="onVoiceMove"
          @touchend.stop.prevent="onVoiceEnd"
          @touchcancel.stop.prevent="onVoiceCancel"
          @mousedown.stop.prevent="onVoiceStart"
          @mousemove.stop.prevent="onVoiceMove"
          @mouseup.stop.prevent="onVoiceEnd"
          @mouseleave="onVoiceMouseLeave"
        >
          <svg class="voice-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
            <g
              transform="rotate(90 12 12)"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
            >
              <path d="M2 8.82a15 15 0 0 1 20 0" />
              <path d="M5 12.859a10 10 0 0 1 14 0" />
              <path d="M8.5 16.429a5 5 0 0 1 7 0" />
            </g>
          </svg>
          <text class="sr-only">语音输入</text>
        </button>
        <button
          class="plus-btn"
          :disabled="loading || attachmentBusy || recordStarting || recordState !== 'idle'"
          aria-label="添加题目"
          @click="toggleAttachmentMenu"
        >
          <svg class="plus-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
            <path
              d="M12 5v14M5 12h14"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
            />
          </svg>
        </button>
        <button
          class="send-btn"
          :disabled="loading || attachmentBusy || (!question && (!attachment.filePath || attachment.id)) || recordStarting || recordState !== 'idle'"
          @click="send"
        >发送</button>
      </view>
    </view>

        </view>
      </swiper-item>

      <!-- 顺序必须是：0 学习 / 1 自律 / 2 我的 -->
      <swiper-item class="tab-swiper-item">
        <SelfDisciplineView :refresh-key="sdRefresh" />
      </swiper-item>

      <swiper-item class="tab-swiper-item">
        <MyView :refresh-key="myRefresh" />
      </swiper-item>
    </swiper>

    <AppTabBar :active="activePath" @change="onTabbarChange" />

    <!-- 按住说话浮层：放在 swiper 外层，避免被 transform 裁剪；pointer-events 关闭，不拦截触摸 -->
    <view
      v-if="recordStarting || recordState === 'starting' || recordState === 'recording' || recordState === 'uploading'"
      class="voice-overlay"
    >
      <view class="voice-overlay-card" :class="{ 'is-cancel': voiceWillCancel }">
        <text class="voice-overlay-title">{{ voiceOverlayTitle }}</text>
        <text class="voice-overlay-hint">{{ voiceOverlayHint }}</text>
        <text v-if="recordState === 'recording'" class="voice-overlay-time">{{ recordSeconds }}s</text>
        <view v-if="recordState === 'recording'" class="voice-wave" :class="{ 'is-cancel': voiceWillCancel }">
          <view v-for="n in 5" :key="n" class="voice-wave-bar" :style="{ animationDelay: `${n * 0.12}s` }"></view>
        </view>
      </view>
    </view>

    <!-- 附件选择：底部弹层（放在 swiper 外层，避免被 swiper 的 transform 裁剪） -->
    <wd-popup
      v-model="attachment.menuOpen"
      position="bottom"
      round
      safe-area-inset-bottom
      :z-index="1100"
    >
      <view class="attach-sheet">
        <view class="attach-sheet__handle" />
        <view class="attach-sheet__head">
          <text class="attach-sheet__title">添加题目</text>
          <text class="attach-sheet__sub">支持 JPG / PNG / PDF，单个不超过 20 MB</text>
        </view>

        <view class="attach-grid">
          <view class="attach-item" @click="chooseAttachment('album')">
            <view class="attach-item__icon">
              <wd-icon name="image" custom-class="attach-icon" />
            </view>
            <text class="attach-item__label">相册</text>
          </view>
          <view class="attach-item" @click="chooseAttachment('camera')">
            <view class="attach-item__icon">
              <wd-icon name="camera" custom-class="attach-icon" />
            </view>
            <text class="attach-item__label">拍照</text>
          </view>
          <view class="attach-item" @click="choosePdf">
            <view class="attach-item__icon">
              <wd-icon name="file" custom-class="attach-icon" />
            </view>
            <text class="attach-item__label">文件</text>
          </view>
        </view>

        <view class="attach-cancel" @click="attachment.menuOpen = false">取消</view>
      </view>
    </wd-popup>

    <!-- 语音设置：松手后直接发送 / 先确认 -->
    <wd-popup
      v-model="showVoiceSettings"
      position="bottom"
      round
      safe-area-inset-bottom
      :z-index="1100"
    >
      <view class="voice-settings">
        <view class="voice-settings__head">
          <text class="voice-settings__title">语音设置</text>
          <text class="voice-settings__close" @click="showVoiceSettings = false">关闭</text>
        </view>
        <view class="voice-settings__row">
          <view class="voice-settings__copy">
            <text class="voice-settings__label">语音识别后先确认</text>
            <text class="voice-settings__desc">关闭：松手识别完直接发送；开启：先填入输入框，确认后再发送。</text>
          </view>
          <switch :checked="voiceConfirmBeforeSend" color="#2b6cb0" @change="onVoiceConfirmChange" />
        </view>
      </view>
    </wd-popup>

    <!-- 多题选择：识别到多道题时让用户选一道 -->
    <wd-popup
      v-model="questionPickerOpen"
      position="bottom"
      round
      safe-area-inset-bottom
      :z-index="1100"
    >
      <view class="question-picker">
        <view class="question-picker__head">
          <text class="question-picker__title">识别到 {{ pendingQuestions.length }} 道题</text>
          <text class="question-picker__sub">请选择要解答的一道</text>
        </view>
        <scroll-view scroll-y class="question-picker__list">
          <view
            v-for="(q, index) in pendingQuestions"
            :key="index"
            class="question-picker__item"
            @click="chooseQuestion(index)"
          >
            <text class="question-picker__index">第 {{ index + 1 }} 题</text>
            <MathText class="question-picker__text" :text="q" />
          </view>
        </scroll-view>
        <view class="question-picker__cancel" @click="questionPickerOpen = false">先不解答</view>
      </view>
    </wd-popup>
  </view>
</template>

<script setup>
import { computed, reactive, ref, watch,nextTick } from 'vue'
import { onHide, onLoad, onShow, onUnload } from '@dcloudio/uni-app'
import { askQuestion, attachmentAction, attachmentContent, attachmentStatus, deleteAttachment, getTodayRecommendations, listMessages, listVideos, transcribeAudio, uploadAttachment } from '../../api.js'
import AppTabBar from '../../components/AppTabBar.vue'
import MyView from '../../components/my/MyView.vue'
import SelfDisciplineView from '../../components/selfdiscipline/SelfDisciplineView.vue'
import MathText from '../../components/ui/MathText.vue'
import Sidebar from './Sidebar.vue'
import { splitLinesOutsideMath, textToSpeech } from '../../math/latex.js'
import { splitQuestionText } from '../../question-split.js'
import { cropSession, resetCropSession } from '../../crop-session.js'
import { pdfTempName, removeTempFile } from '../../temp-files.js'
import { TAB_ITEMS, tabIndexByPath, tabPathByIndex } from '../../tabbar.js'
import { isDark, themeVars } from '../../theme/theme.js'
import { store } from '../../store.js'
import { BASE_URL } from '../../config.js'
import { formatDuration, buildBilibiliMobileUrl } from '../../video.js'
// 全局自动朗读开关，默认开启
const autoPlayEnabled = ref(true)

// 切换声音开关
function toggleAutoPlay() {
  autoPlayEnabled.value = !autoPlayEnabled.value

  // 关闭声音时，立即停止当前朗读
  if (!autoPlayEnabled.value) {
    stopTTS()
  }

  uni.showToast({
    title: autoPlayEnabled.value ? '自动朗读已开启' : '自动朗读已关闭',
    icon: 'none'
  })
}
// ==================== TTS 文字转语音 ====================


// 当前正在朗读的消息下标，-1 表示没有播放
const playingIndex = ref(-1)

// 音频播放器
let ttsAudioContext = null

// 请求序号：防止连续点击时，旧请求返回后又开始播放
let ttsRequestToken = 0

/**
 * 从 AI 消息中提取适合朗读的文字
 * 优先读取解题步骤和最终答案，避免直接朗读 JSON
 */
function getSpeechText(msg) {
  if (!msg || msg.failed || msg.refused) return ''

  const steps = Array.isArray(msg.solution_steps) && msg.solution_steps.length
    ? msg.solution_steps
    : (msg.learning_path && Array.isArray(msg.learning_path.steps) && msg.learning_path.steps.length
        ? msg.learning_path.steps
        : answerStepList(msg))

  const stepTexts = steps
    .map((step) => {
      if (typeof step === 'string') return step.trim()
      if (!step || typeof step !== 'object') return ''
      return [step.title, step.content].filter(Boolean).join('，').trim()
    })
    .filter(Boolean)

  const answer = msg.final_answer ||
    (msg.learning_path && msg.learning_path.final_answer) ||
    finalAnswer(msg.answer)

  const parts = []

  if (stepTexts.length) {
    parts.push('解题过程。')
    stepTexts.forEach((text, index) => {
      parts.push(`第${index + 1}步，${text}`)
    })
  }

  if (answer) {
    parts.push(`最终答案：${answer}`)
  }

  // 如果没有步骤和最终答案，则回退到原始回答文本
  if (!parts.length) {
    let raw = String(msg.answer || '').trim()
    const trimmed = raw.startsWith('(') && raw.endsWith(')')
      ? raw.slice(1, -1)
      : raw

    if (trimmed.startsWith('{')) {
      try {
        const parsed = JSON.parse(trimmed)
        raw = [
          ...(Array.isArray(parsed.steps)
            ? parsed.steps.map((item) => typeof item === 'string' ? item : item.content || '')
            : []),
          parsed.final_answer || '',
        ].filter(Boolean).join('。')
      } catch (e) {}
    }

    parts.push(raw)
  }

  return textToSpeech(parts.join('。').replace(/\s+/g, ' ').trim())
}

/**
 * 创建音频播放器
 */
function initTtsAudioContext() {
  if (ttsAudioContext) return ttsAudioContext

  if (typeof uni.createInnerAudioContext !== 'function') {
    throw new Error('当前平台不支持音频播放')
  }

  const context = uni.createInnerAudioContext()

  context.onEnded(() => {
    playingIndex.value = -1
  })

  context.onError((error) => {
    playingIndex.value = -1
    console.error('[TTS] 音频播放失败：', error)
    uni.showToast({ title: '语音播放失败，请重试', icon: 'none' })
  })

  ttsAudioContext = context
  return context
}

/**
 * 停止当前朗读
 * destroy 为 true 时同时销毁播放器
 */
function stopTTS(destroy = false) {
  // 让尚未返回的旧请求失效
  ttsRequestToken += 1
  playingIndex.value = -1

  if (!ttsAudioContext) return

  try {
    ttsAudioContext.stop()
  } catch (e) {}

  if (destroy) {
    try {
      ttsAudioContext.destroy()
    } catch (e) {}
    ttsAudioContext = null
  }
}


function cleanTTSContent(text) {
  return String(text || '')
    // 合并重复的步骤编号，例如：第1步，第 1 步 → 第1步
    .replace(
      /第\s*([一二三四五六七八九十\d]+)\s*步\s*[，,、]\s*第\s*\1\s*步/g,
      '第$1步'
    )
    .trim()
}

/**
 * 播放指定消息的语音
 */
 async function playTTS(text, index) {
  const speechText = cleanTTSContent(text).trim()
  console.log('实际发送给 TTS 的文本：', speechText)

  if (!speechText) {
    uni.showToast({ title: '没有可朗读的内容', icon: 'none' })
    return
  }

  // 再次点击当前消息的朗读按钮：停止播放
  if (playingIndex.value === index) {
    stopTTS()
    return
  }

  // 停止上一条消息的朗读
  stopTTS()

  const requestToken = ttsRequestToken
  playingIndex.value = index

  try {
    const context = initTtsAudioContext()

    // 请求后端创建流式 TTS 会话
    const data = await new Promise((resolve, reject) => {
      uni.request({
        url: `${BASE_URL}/api/tts/stream/session`,
        method: 'POST',
        header: {
          'Content-Type': 'application/json',
        },
        data: {
          text: speechText,
        },
        success: (res) => {
          if (res.statusCode >= 200 && res.statusCode < 300) {
            resolve(res.data)
          } else {
            const message = res.data && (
              res.data.detail || res.data.message
            )
            reject(new Error(message || `语音请求失败（${res.statusCode}）`))
          }
        },
        fail: (error) => {
          reject(new Error(error.errMsg || '无法连接语音服务'))
        },
      })
    })

    // 如果用户已经停止播放或切换了其他消息，不再继续
    if (requestToken !== ttsRequestToken) return

    if (!data || !data.audio_url) {
      throw new Error('后端没有返回音频地址')
    }

    // 兼容后端返回完整 URL 或相对路径
    const audioUrl = /^https?:\/\//i.test(data.audio_url)
      ? data.audio_url
      : `${BASE_URL.replace(/\/$/, '')}/${String(data.audio_url).replace(/^\//, '')}`

    context.src = audioUrl
    context.play()
  } catch (error) {
    if (requestToken !== ttsRequestToken) return

    playingIndex.value = -1
    console.error('[TTS] 朗读请求失败：', error)
    uni.showToast({
      title: (error && error.message) || '语音生成失败，请重试',
      icon: 'none',
    })
  }
}

// 侧边栏控制状态
const showSidebar = ref(false)
const currentMenu = ref('study')

// ==================== 左边缘滑出抽屉 ====================
// 手指从左边缘向右拖，抽屉跟随手指移动；松手过阈值则展开。
const edgeDrag = ref(0)       // 当前拖动距离（px）
const edgeDragging = ref(false)
let edgeStartX = 0
let edgeStartY = 0
let edgeStartedAt = 0
let edgeAxisLocked = false

function drawerWidthPx() {
  try {
    const width = uni.getSystemInfoSync().windowWidth || 375
    return Math.min(width * 0.76, 320)
  } catch (e) {
    return 280
  }
}

function onEdgeStart(e) {
  const t = e.touches && e.touches[0]
  if (!t) return
  edgeStartX = t.clientX
  edgeStartY = t.clientY
  edgeStartedAt = Date.now()
  edgeAxisLocked = false
  edgeDrag.value = 0
  edgeDragging.value = true
}

function onEdgeMove(e) {
  if (!edgeDragging.value) return
  const t = e.touches && e.touches[0]
  if (!t) return
  const dx = t.clientX - edgeStartX
  const dy = t.clientY - edgeStartY
  if (!edgeAxisLocked) {
    if (Math.abs(dx) < 10 && Math.abs(dy) < 10) return
    // 判定为竖向手势时放弃，交还页面滚动
    if (Math.abs(dy) > Math.abs(dx)) {
      edgeDragging.value = false
      edgeDrag.value = 0
      return
    }
    edgeAxisLocked = true
  }
  edgeDrag.value = Math.max(0, Math.min(dx, drawerWidthPx()))
}

function onEdgeEnd() {
  if (!edgeDragging.value) return
  const width = drawerWidthPx()
  const threshold = Math.max(56, width * 0.25)
  const fast = Date.now() - edgeStartedAt < 220
  const shouldOpen = edgeDrag.value > threshold || (fast && edgeDrag.value > 24)
  edgeDragging.value = false
  edgeDrag.value = 0
  if (shouldOpen) showSidebar.value = true
}

// ==================== 宿主页 tab 状态 ====================
// 0 = 学习首页，1 = 自律，2 = 我的；底部导航只发事件，真正切页由 swiper 的 current 控制
const activeTab = ref(0)
const myRefresh = ref(0)
const sdRefresh = ref(0)
const activePath = computed(() => tabPathByIndex(activeTab.value))

function onSwiperChange(e) {
  activeTab.value = e.detail.current
}

function onTabbarChange(path) {
  activeTab.value = tabIndexByPath(path)
}

// 切到自律/我的时重新读取数据
watch(activeTab, (v) => {
  if (v === 1) sdRefresh.value++
  if (v === 2) myRefresh.value++
})

// 状态栏高度（自定义导航栏适配）
const statusBarHeight = ref(0)
// #ifdef H5
statusBarHeight.value = 0
// #endif
// #ifdef APP-PLUS
try {
  const sysInfo = uni.getSystemInfoSync()
  statusBarHeight.value = (sysInfo && sysInfo.statusBarHeight) || 0
} catch (e) {
  statusBarHeight.value = 0
}
// #endif

// 用于实时显示最新的本地缓存昵称
const currentNickname = ref('')
const userAvatar = ref('')
const attachmentMessage = ref(null)
const previewingAttachment = ref(false)

// 处理侧边栏点击菜单事件
function loadUserAvatar() {
  userAvatar.value = uni.getStorageSync('user_avatar') || ''
}

function exerciseCount(msg) {
  if (Array.isArray(msg && msg.exercises) && msg.exercises.length) return msg.exercises.length
  return Array.isArray(msg && msg.learning_path && msg.learning_path.exercises)
    ? msg.learning_path.exercises.length
    : 0
}

function answerStepList(msg) {
  if (Array.isArray(msg && msg.solution_steps) && msg.solution_steps.length) return msg.solution_steps
  const text = String((msg && msg.answer) || '')
  const trimmed = text.trim()
  // 兼容后端返回的 JSON 字符串可能被括号包裹，如 ({"steps":[...],"final_answer":"..."})
  const jsonStr = (trimmed.startsWith('(') && trimmed.endsWith(')')) ? trimmed.slice(1, -1) : trimmed
  if (jsonStr.startsWith('{')) {
    try {
      const parsed = JSON.parse(jsonStr)
      if (Array.isArray(parsed.steps)) return parsed.steps.map((step, index) => ({
        title: typeof step === 'object' ? (step.title || `第 ${index + 1} 步`) : `第 ${index + 1} 步`,
        content: typeof step === 'object' ? (step.content || '') : String(step),
      })).filter((step) => step.content)
    } catch (e) {}
  }
  const clean = text.replace(/(?:最终答案|答案)\s*[:：].*$/is, '').trim()
  return splitLinesOutsideMath(clean).map((line, index) => ({ title: `第 ${index + 1} 步`, content: line.replace(/^\s*\d+[.、)）]\s*/, '') })).filter((step) => step.content)
}

function finalAnswer(answer) {
  // 先尝试从纯文本中正则匹配
  const textMatch = String(answer || '').match(/(?:最终答案|答案)\s*[:：]\s*(.+)$/is)
  if (textMatch) return textMatch[1].trim()
  // 再尝试从 JSON 结构中提取 final_answer 字段（兼容后端返回的括号包裹格式）
  const trimmed = String(answer || '').trim()
  const jsonStr = (trimmed.startsWith('(') && trimmed.endsWith(')')) ? trimmed.slice(1, -1) : trimmed
  if (jsonStr.startsWith('{')) {
    try {
      const parsed = JSON.parse(jsonStr)
      if (parsed.final_answer) return parsed.final_answer
    } catch (e) {}
  }
  return ''
}

function onSelectMenu(menu) {
  currentMenu.value = menu.key
  showSidebar.value = false

  if (menu.key === 'study') {
    activeTab.value = 0
  } else if (menu.key === 'self') {
    activeTab.value = 1
  } else if (menu.key === 'profile') {
    activeTab.value = 2
  } else if (menu.key === 'history') {
    goHistory()
  } else if (menu.key === 'diagnosis') {
    uni.navigateTo({ url: '/pages/diagnosis/diagnosis' })
  } else if (menu.key === 'path') {
    uni.navigateTo({ url: '/pages/path/path' })
  } else {
    uni.showToast({ title: `即将开发：${menu.name}`, icon: 'none' })
  }
}

const question = ref('')
const loading = ref(false)
const attachmentBusy = ref(false)

// 空状态快捷提问
const quickQuestions = [
  '分数为什么要通分？',
  '圆的面积怎么算？',
  '一元一次方程怎么解？',
]

function askQuick(text) {
  if (loading.value || attachmentBusy.value || recordStarting.value || recordState.value !== 'idle') return
  question.value = text
  send()
}

// ---------- 今日建议 ----------
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
const todaySuggestions = ref([])
const todayLoading = ref(false)
const todayDismissed = ref(false)
const todayGrade = computed(() =>
  Number.isInteger(store.auth.user && store.auth.user.grade)
    ? store.auth.user.grade
    : null
)

function gradeLabel(value) {
  return GRADE_LABELS[value] || `${value}年级`
}

function todayStorageKey() {
  const date = new Date()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

function readTodayDismissed() {
  try {
    return uni.getStorageSync('today_suggestions_dismissed') === todayStorageKey()
  } catch (e) {
    return false
  }
}

function dismissTodaySuggestions() {
  todayDismissed.value = true
  try {
    uni.setStorageSync('today_suggestions_dismissed', todayStorageKey())
  } catch (e) {
    // 本地缓存不可用时只在本次页面生效。
  }
}

async function loadTodaySuggestions() {
  if (!(store.auth.user && store.auth.token)) {
    todaySuggestions.value = []
    return
  }
  if (todayDismissed.value) return
  todayLoading.value = true
  try {
    const data = await getTodayRecommendations({ limit: 3 })
    todaySuggestions.value = (data && data.items) || []
  } catch (e) {
    todaySuggestions.value = []
  } finally {
    todayLoading.value = false
  }
}

function openTodaySuggestion(item) {
  const action = (item.actions || [])[0]
  if (!action) return
  if (action.type === 'diagnose') {
    const query = item.node_key
      ? `?node_key=${encodeURIComponent(item.node_key)}`
      : ''
    uni.navigateTo({ url: `/pages/diagnosis/diagnosis${query}` })
    return
  }
  if (action.type === 'chat') {
    question.value = action.question || `帮我讲讲「${item.name}」`
    uni.showToast({ title: '已填入输入框', icon: 'none' })
    return
  }
  if (action.type === 'video' && action.video) {
    uni.navigateTo({
      url: `/pages/video/video?bvid=${encodeURIComponent(action.video.bvid || '')}`
        + `&page=${encodeURIComponent(action.video.page || 1)}`
        + `&aid=${encodeURIComponent(action.video.aid || '')}`
        + `&cid=${encodeURIComponent(action.video.cid || '')}`
        + `&title=${encodeURIComponent(action.video.title || item.name)}`,
    })
  }
}

const attachment = reactive({
  filePath: '', file: null, name: '', size: 0, id: '', ocrText: '', statusText: '', menuOpen: false, mediaType: '', pageCount: 0, failedPages: [],
})
const historyLoading = ref(false)
const loadingEarlier = ref(false)
const messages = reactive([])
const scrollTo = ref('')
const messagesCursor = ref('')
const hasEarlier = ref(false)
const activeVideo = ref(null)
const h264Supported = ref(true)

// #ifdef H5
if (typeof document !== 'undefined') {
  const probe = document.createElement('video')
  h264Supported.value = !!probe.canPlayType('video/mp4; codecs="avc1.42E01E"')
}
// #endif

const recordState = ref('idle')
const recordSeconds = ref(0)
const recordStarting = ref(false)
const voiceSupported = ref(false)
const voiceWillCancel = ref(false)
const showVoiceSettings = ref(false)
const voiceConfirmBeforeSend = ref(false)
const questionPickerOpen = ref(false)
const pendingQuestions = ref([])
let voiceStartY = 0
let recorder = null
let recordTimer = null
let pendingCancel = false
let pendingStart = false
let recordSession = 0
let activeRecordSession = 0

try {
  voiceConfirmBeforeSend.value = !!uni.getStorageSync('voice_confirm_before_send')
} catch (e) {}

const voiceOverlayTitle = computed(() => {
  if (recordState.value === 'uploading') return '正在识别…'
  if (recordStarting.value || recordState.value === 'starting') return '正在准备…'
  if (voiceWillCancel.value) return '松开取消'
  return '松开发送'
})

const voiceOverlayHint = computed(() => {
  if (recordState.value === 'uploading') {
    return voiceConfirmBeforeSend.value ? '识别完成后先填入输入框' : '识别完成后自动发送'
  }
  if (recordStarting.value || recordState.value === 'starting') return '请保持按住'
  if (voiceWillCancel.value) return '已进入取消区域'
  return '上滑取消'
})

// #ifdef APP-PLUS
voiceSupported.value = true
recorder = uni.getRecorderManager()
// #endif

// #ifdef H5
voiceSupported.value = true
let h5Stream = null
let h5Recorder = null
let h5Chunks = []
let h5MimeType = ''
const H5_MIME_CANDIDATES = [
  'audio/mp4;codecs=mp4a.40.2',
  'audio/mp4',
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/ogg;codecs=opus',
  'audio/ogg',
]
// #endif

function recordErrorMessage(err) {
  const msg = (err && err.errMsg) || ''
  if (/auth|permission|denied|deny|权限|授权/i.test(msg)) {
    return '没有麦克风权限，请在系统设置中允许后重试'
  }
  if (/cancel/i.test(msg)) return '录音已取消'
  if (/not support|unsupport|device/i.test(msg)) return '当前设备不支持录音'
  return '录音失败，请重试'
}

function startRecordTimer() {
  stopRecordTimer()
  recordTimer = setInterval(() => {
    recordSeconds.value += 1
    if (recordSeconds.value >= 30) {
      stopRecordTimer()
      if (recordState.value === 'recording') stopCurrentRecording()
    }
  }, 1000)
}

function stopRecordTimer() {
  if (recordTimer) {
    clearInterval(recordTimer)
    recordTimer = null
  }
}

// #ifdef APP-PLUS
function stopCurrentRecording() {
  if (!recorder) return
  try {
    recorder.stop()
  } catch (e) {
    resetRecordState()
  }
}
// #endif

// #ifdef H5
function stopCurrentRecording() {
  if (h5Recorder && h5Recorder.state !== 'inactive') {
    try {
      h5Recorder.stop()
    } catch (e) {
      resetRecordState()
    }
  }
}
// #endif

// #ifndef APP-PLUS
// #ifndef H5
function stopCurrentRecording() {}
// #endif
// #endif

function stopTracks(stream) {
  if (!stream) return
  stream.getTracks().forEach((track) => {
    try {
      track.stop()
    } catch (e) {}
  })
}

function releaseH5Resources() {
  // #ifdef H5
  const stream = h5Stream
  h5Stream = null
  h5Recorder = null
  h5Chunks = []
  h5MimeType = ''
  stopTracks(stream)
  // #endif
}

function resetRecordState() {
  stopRecordTimer()
  pendingCancel = false
  recordState.value = 'idle'
  recordSeconds.value = 0
}

function invalidateRecordSession() {
  recordSession += 1
  pendingCancel = true
  pendingStart = false
  recordStarting.value = false
  stopRecordTimer()
  if (recordState.value === 'recording') stopCurrentRecording()
  releaseH5Resources()
  recordState.value = 'idle'
  recordSeconds.value = 0
}

function showRecordPermissionModal(deniedAlways) {
  uni.showModal({
    title: '需要麦克风权限',
    content: deniedAlways
      ? '麦克风权限已被拒绝，请到系统设置中手动开启后重试。'
      : '请允许使用麦克风后重试。',
    showCancel: false,
    confirmText: '知道了',
  })
}

function requestRecordPermission() {
  return new Promise((resolve) => {
    // #ifdef APP-PLUS
    if (typeof plus !== 'undefined' && plus.android && plus.android.requestPermissions) {
      const permission = 'android.permission.RECORD_AUDIO'
      try {
        if (plus.android.hasPermission && plus.android.hasPermission(permission)) {
          resolve(true)
          return
        }
        plus.android.requestPermissions(
          [permission],
          (e) => {
            const granted = !!(e && e.granted && e.granted.length > 0)
            if (granted) {
              resolve(true)
              return
            }
            const deniedAlways = !!(e && e.deniedAlways && e.deniedAlways.length > 0)
            showRecordPermissionModal(deniedAlways)
            resolve(false)
          },
          () => {
            showRecordPermissionModal(false)
            resolve(false)
          }
        )
      } catch (err) {
        resolve(true)
      }
      return
    }
    resolve(true)
    // #endif
    // #ifndef APP-PLUS
    resolve(false)
    // #endif
  })
}

function isIndexPageActive() {
  const pages = getCurrentPages()
  const current = pages[pages.length - 1]
  const route = current && current.route ? String(current.route).replace(/^\//, '') : ''
  return route === 'pages/index/index'
}

// #ifdef H5
function checkH5RecorderSupport() {
  if (typeof window === 'undefined' || window.isSecureContext === false) {
    uni.showToast({ title: '麦克风需要 HTTPS 或 localhost 环境', icon: 'none' })
    return false
  }
  if (typeof MediaRecorder === 'undefined') {
    uni.showToast({ title: '当前浏览器不支持录音', icon: 'none' })
    return false
  }
  if (!navigator.mediaDevices || typeof navigator.mediaDevices.getUserMedia !== 'function') {
    uni.showToast({ title: '当前浏览器不支持麦克风采集', icon: 'none' })
    return false
  }
  if (typeof File === 'undefined') {
    uni.showToast({ title: '当前浏览器不支持录音上传', icon: 'none' })
    return false
  }
  return true
}

function pickH5MimeType() {
  if (typeof MediaRecorder === 'undefined' || typeof MediaRecorder.isTypeSupported !== 'function') {
    return ''
  }
  for (const type of H5_MIME_CANDIDATES) {
    if (MediaRecorder.isTypeSupported(type)) return type
  }
  return ''
}

function h5MicErrorMessage(err) {
  const name = (err && err.name) || ''
  if (name === 'NotAllowedError' || name === 'PermissionDeniedError' || name === 'SecurityError') {
    return '麦克风权限被拒绝，请在浏览器设置中允许'
  }
  if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
    return '没有找到可用的麦克风'
  }
  if (name === 'NotReadableError' || name === 'TrackStartError') {
    return '麦克风被其他应用占用，请关闭后重试'
  }
  return '无法访问麦克风，请重试'
}

function isQwenFriendlyMime(mimeType) {
  const type = (mimeType || '').toLowerCase()
  return (
    type.includes('mp4') ||
    type.includes('aac') ||
    type.includes('mpeg') ||
    type.includes('mp3') ||
    type.includes('wav')
  )
}

function h5FileExtension(mimeType) {
  const type = (mimeType || '').toLowerCase()
  if (type.includes('mp4') || type.includes('aac')) return 'm4a'
  if (type.includes('wav')) return 'wav'
  if (type.includes('mpeg') || type.includes('mp3')) return 'mp3'
  if (type.includes('ogg')) return 'ogg'
  return 'webm'
}

function encodeWav(audioBuffer) {
  const samples = audioBuffer.getChannelData(0)
  const buffer = new ArrayBuffer(44 + samples.length * 2)
  const view = new DataView(buffer)
  const writeString = (offset, text) => {
    for (let i = 0; i < text.length; i += 1) {
      view.setUint8(offset + i, text.charCodeAt(i))
    }
  }
  writeString(0, 'RIFF')
  view.setUint32(4, 36 + samples.length * 2, true)
  writeString(8, 'WAVE')
  writeString(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, audioBuffer.sampleRate, true)
  view.setUint32(28, audioBuffer.sampleRate * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  writeString(36, 'data')
  view.setUint32(40, samples.length * 2, true)
  let offset = 44
  for (let i = 0; i < samples.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, samples[i]))
    view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true)
    offset += 2
  }
  return new Blob([view], { type: 'audio/wav' })
}

async function blobToWav(blob) {
  const AudioCtor = window.AudioContext || window.webkitAudioContext
  const OfflineCtor = window.OfflineAudioContext || window.webkitOfflineAudioContext
  if (!AudioCtor || !OfflineCtor) throw new Error('AudioContext unsupported')

  const arrayBuffer = await blob.arrayBuffer()
  const ctx = new AudioCtor()
  let decoded
  try {
    decoded = await new Promise((resolve, reject) => {
      ctx.decodeAudioData(arrayBuffer.slice(0), resolve, reject)
    })
  } finally {
    if (ctx.close) ctx.close()
  }

  const targetRate = 16000
  const frames = Math.max(1, Math.ceil(decoded.duration * targetRate))
  const offline = new OfflineCtor(1, frames, targetRate)
  const source = offline.createBufferSource()
  source.buffer = decoded
  source.connect(offline.destination)
  source.start(0)
  const rendered = await offline.startRendering()
  return encodeWav(rendered)
}

function abortH5Recording(message) {
  recordSession += 1
  pendingCancel = true
  stopRecordTimer()
  const activeRecorder = h5Recorder
  const stream = h5Stream
  h5Recorder = null
  h5Stream = null
  h5Chunks = []
  h5MimeType = ''
  if (activeRecorder && activeRecorder.state !== 'inactive') {
    try {
      activeRecorder.stop()
    } catch (e) {}
  }
  stopTracks(stream)
  recordState.value = 'idle'
  recordSeconds.value = 0
  pendingCancel = false
  uni.showToast({ title: message, icon: 'none' })
}

async function beginH5Recording(token) {
  let stream
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    })
  } catch (err) {
    if (token === recordSession) {
      uni.showToast({ title: h5MicErrorMessage(err), icon: 'none' })
    }
    return
  }

  if (token !== recordSession || !isIndexPageActive()) {
    stopTracks(stream)
    return
  }

  const mimeType = pickH5MimeType()
  let mediaRecorder
  try {
    mediaRecorder = mimeType
      ? new MediaRecorder(stream, { mimeType })
      : new MediaRecorder(stream)
  } catch (err) {
    stopTracks(stream)
    uni.showToast({ title: '当前浏览器不支持录音', icon: 'none' })
    return
  }

  recordSession += 1
  const session = recordSession
  activeRecordSession = session
  pendingCancel = false
  recordSeconds.value = 0
  h5Stream = stream
  h5Recorder = mediaRecorder
  const sessionChunks = []
  h5Chunks = sessionChunks
  h5MimeType = mimeType || mediaRecorder.mimeType || ''
  const sessionMimeType = h5MimeType

  mediaRecorder.ondataavailable = (event) => {
    if (event.data && event.data.size > 0) sessionChunks.push(event.data)
  }
  mediaRecorder.onerror = () => {
    if (session !== recordSession) return
    abortH5Recording('录音失败，请重试')
  }
  mediaRecorder.onstop = () => {
    finishH5Recording(session, sessionChunks, stream, sessionMimeType).catch(() => {
      if (session === recordSession) {
        resetRecordState()
        uni.showToast({ title: '录音处理失败，请重试', icon: 'none' })
      }
    })
  }

  const audioTrack = stream.getAudioTracks()[0]
  if (audioTrack) {
    audioTrack.onended = () => {
      if (recordState.value !== 'recording' || session !== recordSession) return
      abortH5Recording('录音已中断，请重试')
    }
  }

  try {
    mediaRecorder.start(1000)
  } catch (err) {
    abortH5Recording('无法开始录音，请重试')
    return
  }

  recordState.value = 'recording'
  startRecordTimer()
}

async function finishH5Recording(session, sessionChunks, stream, detectedType) {
  if (session !== recordSession) {
    stopTracks(stream)
    return
  }

  const recordedSeconds = recordSeconds.value
  const chunks = sessionChunks.slice()
  stopRecordTimer()
  h5Stream = null
  h5Recorder = null
  h5Chunks = []
  h5MimeType = ''
  stopTracks(stream)

  if (session !== recordSession) return
  if (pendingCancel) {
    resetRecordState()
    return
  }
  if (!chunks.length) {
    resetRecordState()
    uni.showToast({ title: '没有录到有效语音', icon: 'none' })
    return
  }
  if (recordedSeconds * 1000 < 500) {
    resetRecordState()
    uni.showToast({ title: '按住说话，松开发送', icon: 'none' })
    return
  }

  let blob = new Blob(chunks, { type: detectedType || 'audio/webm' })
  if (!blob.size) {
    resetRecordState()
    uni.showToast({ title: '没有录到有效语音', icon: 'none' })
    return
  }

  recordState.value = 'uploading'
  let mimeType = 'audio/wav'
  try {
    blob = await blobToWav(blob)
  } catch (err) {
    if (!isQwenFriendlyMime(detectedType)) {
      if (session !== recordSession) return
      resetRecordState()
      uni.showToast({
        title: '浏览器无法转换录音格式，请使用 Chrome/Edge 或 App',
        icon: 'none',
      })
      return
    }
    mimeType = (detectedType || blob.type || 'audio/mp4').split(';')[0].trim()
  }
  if (session !== recordSession) return

  const file = new File([blob], `audio.${h5FileExtension(mimeType)}`, {
    type: mimeType || 'audio/wav',
  })
  uploadRecording(null, session, { file })
}
// #endif

async function startRecording() {
  if (loading.value) {
    uni.showToast({ title: '回答生成中，请稍后再录音', icon: 'none' })
    return
  }
  if (recordState.value !== 'idle' || pendingStart || recordStarting.value) return

  pendingStart = true
  recordStarting.value = true
  const token = recordSession
  try {
    // #ifdef APP-PLUS
    const allowed = await requestRecordPermission()
    if (!allowed) return
    // #endif
    // #ifdef H5
    if (!checkH5RecorderSupport()) return
    // #endif
    if (token !== recordSession || !isIndexPageActive()) return

    // #ifdef APP-PLUS
    beginAppRecording()
    // #endif
    // #ifdef H5
    await beginH5Recording(token)
    // #endif
  } catch (e) {
    releaseH5Resources()
    resetRecordState()
    uni.showToast({ title: '无法开始录音', icon: 'none' })
  } finally {
    pendingStart = false
    recordStarting.value = false
  }
}

// #ifdef APP-PLUS
function beginAppRecording() {
  recordSession += 1
  activeRecordSession = recordSession
  pendingCancel = false
  recordSeconds.value = 0
  // 真正的 recording 状态等 recorder.onStart 再切，避免“已松手但录音还没启动”的竞态
  recordState.value = 'starting'
  try {
    recorder.start({
      format: 'mp3',
      sampleRate: 16000,
      duration: 30000,
    })
  } catch (e) {
    if (activeRecordSession === recordSession) resetRecordState()
    uni.showToast({ title: '当前设备不支持录音', icon: 'none' })
  }
}
// #endif

function cancelRecord() {
  if (recordState.value !== 'recording') return
  pendingCancel = true
  stopCurrentRecording()
}

// ==================== 按住说话 ====================

function onVoiceStart(e) {
  if (!voiceSupported.value) {
    uni.showToast({ title: '当前平台不支持语音输入', icon: 'none' })
    return
  }
  if (loading.value || attachmentBusy.value) {
    uni.showToast({
      title: loading.value ? '回答生成中，请稍后' : '附件处理中，请稍后',
      icon: 'none',
    })
    return
  }
  if (attachment.filePath && !attachment.id) {
    uni.showToast({ title: '请先发送或删除当前附件', icon: 'none' })
    return
  }
  if (recordState.value !== 'idle' || pendingStart || recordStarting.value) return

  const point = (e.touches && e.touches[0]) || e
  voiceStartY = (point && (point.clientY != null ? point.clientY : point.pageY)) || 0
  voiceWillCancel.value = false
  try {
    uni.vibrateShort({ type: 'light' })
  } catch (err) {}
  startRecording()
}

function onVoiceMove(e) {
  if (recordState.value !== 'recording' && !recordStarting.value && recordState.value !== 'starting') return
  const point = (e.touches && e.touches[0]) || e
  if (!point) return
  const y = point.clientY != null ? point.clientY : point.pageY
  if (typeof y !== 'number') return

  const next = voiceStartY - y > 80
  if (next !== voiceWillCancel.value) {
    voiceWillCancel.value = next
    try {
      uni.vibrateShort({ type: next ? 'heavy' : 'light' })
    } catch (err) {}
  }
}

function onVoiceEnd() {
  // 权限弹窗/录音启动还没完成时松手：直接取消，不发送
  if (recordStarting.value || pendingStart || recordState.value === 'starting') {
    voiceWillCancel.value = false
    invalidateRecordSession()
    return
  }
  if (recordState.value !== 'recording') return

  if (voiceWillCancel.value) {
    cancelRecord()
  } else {
    stopCurrentRecording()
  }
  voiceWillCancel.value = false
}

function onVoiceCancel() {
  voiceWillCancel.value = false
  if (recordState.value === 'recording' || recordState.value === 'starting' || recordStarting.value) {
    invalidateRecordSession()
  }
}

function onVoiceMouseLeave() {
  if (recordState.value === 'recording') {
    uni.showToast({ title: '已取消录音', icon: 'none' })
    onVoiceCancel()
  }
}

function onVoiceConfirmChange(e) {
  const value = !!(e && e.detail && e.detail.value)
  voiceConfirmBeforeSend.value = value
  try {
    uni.setStorageSync('voice_confirm_before_send', value)
  } catch (err) {}
}

/**
 * 语音识别完成后的落点：
 * - 默认直接发送
 * - 开启“先确认”时填入输入框，等用户点发送
 */
function submitVoiceText(text) {
  const current = question.value.trim()
  const finalText = current ? `${current} ${text}` : text

  if (voiceConfirmBeforeSend.value) {
    question.value = finalText
    uni.showToast({ title: '识别完成，请确认后发送', icon: 'none' })
    return
  }

  question.value = finalText
  if (loading.value || attachmentBusy.value) {
    uni.showToast({ title: '当前正在处理，已填入输入框', icon: 'none' })
    return
  }

  resetRecordState()
  send()
}

function uploadRecording(filePath, session, options = {}) {
  recordState.value = 'uploading'
  transcribeAudio(filePath, options)
    .then((data) => {
      if (session !== recordSession) return
      const text = data && data.text ? String(data.text).trim() : ''
      if (!text) {
        uni.showToast({ title: '未识别到有效语音，请重试', icon: 'none' })
        return
      }
      submitVoiceText(text)
    })
    .catch((e) => {
      if (session !== recordSession) return
      uni.showToast({ title: (e && e.message) || '语音识别失败，请重试', icon: 'none' })
    })
    .finally(() => {
      // App：识别完成（成功或失败）后删除录音临时文件。
      removeTempFile(filePath)
      if (session === recordSession) resetRecordState()
    })
}

if (recorder) {
  recorder.onStart(() => {
    if (activeRecordSession !== recordSession || pendingCancel) {
      try {
        recorder.stop()
      } catch (e) {}
      return
    }
    recordState.value = 'recording'
    recordSeconds.value = 0
    startRecordTimer()
  })

  recorder.onStop((res) => {
    const session = activeRecordSession
    const recordedSeconds = recordSeconds.value
    stopRecordTimer()

    const filePath = res && res.tempFilePath
    if (session !== recordSession) {
      removeTempFile(filePath)
      return
    }

    if (pendingCancel) {
      removeTempFile(filePath)
      resetRecordState()
      return
    }

    if (!filePath) {
      resetRecordState()
      uni.showToast({ title: '录音失败，请重试', icon: 'none' })
      return
    }

    const durationMs = (res && res.duration) || recordedSeconds * 1000
    if (durationMs < 500) {
      removeTempFile(filePath)
      resetRecordState()
      uni.showToast({ title: '按住说话，松开发送', icon: 'none' })
      return
    }

    uploadRecording(filePath, session)
  })

  recorder.onError((err) => {
    if (activeRecordSession !== recordSession) return
    resetRecordState()
    uni.showToast({ title: recordErrorMessage(err), icon: 'none' })
  })
}

onShow(() => {
  loadUserAvatar()
})

onHide(() => {
  // 离开页面时停止语音
  stopTTS()

  // #ifdef H5
  if (recordState.value !== 'idle' || pendingStart) invalidateRecordSession()
  // #endif
  // #ifdef APP-PLUS
  if (recordState.value !== 'idle') invalidateRecordSession()
  // #endif
})

onUnload(() => {
  stopTTS(true)
  invalidateRecordSession()
})

// 优先读取本地缓存昵称
const authStateText = computed(() => {
  if (!store.auth.ready) return '正在检查登录状态…'
  if (store.auth.user) {
    return '已登录：' + (currentNickname.value || store.auth.user.display_name || store.auth.user.username)
  }
  return '游客模式'
})

function goAuth() {
  uni.navigateTo({ url: '/pages/auth/auth' })
}

function goHistory() {
  uni.navigateTo({ url: '/pages/history/history' })
}

function clearConversationView() {
  messages.splice(0, messages.length)
  question.value = ''
  clearAttachment()
  store.currentConversationId = ''
  messagesCursor.value = ''
  hasEarlier.value = false
  scrollTo.value = ''
  // 👇 新增：清空时，同时清除本地缓存
  uni.removeStorageSync('last_conversation_id')
}

function newConversation() {
  if (loading.value || recordStarting.value || recordState.value !== 'idle') return
  clearConversationView()
  uni.showToast({ title: '已开始新对话', icon: 'none' })
}

function newRequestId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID()
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`
}

function normalizeLearningPath(payload) {
  const lp = (payload && payload.learning_path) || payload || {}
  let exercises = lp.exercises
  if (!Array.isArray(exercises)) {
    exercises = Array.isArray(payload && payload.exercises) ? payload.exercises : []
  }
  return {
    steps: Array.isArray(lp.steps) ? lp.steps : (Array.isArray(payload && payload.solution_steps) ? payload.solution_steps : []),
    final_answer: lp.final_answer || payload.final_answer || '',
    prerequisites: Array.isArray(lp.prerequisites) ? lp.prerequisites : [],
    prerequisite_ids: Array.isArray(lp.prerequisite_ids) ? lp.prerequisite_ids : [],
    body: lp.body || '',
    body_id: lp.body_id || '',
    consolidation: Array.isArray(lp.consolidation) ? lp.consolidation : [],
    consolidation_ids: Array.isArray(lp.consolidation_ids) ? lp.consolidation_ids : [],
    exercises,
  }
}

function toUiMessages(items) {
  const out = []
  let lastUser = ''
  for (const m of items) {
    if (m.role === 'user') {
      lastUser = m.content || ''
      const item = {
          role: 'user',
          id: m.id || '',
          text: lastUser
        }
      const attachment = m.attachment
      if (attachment) {
        const mediaType = attachment.media_type || ''
        item.attachment = {
          id: attachment.id,
          name: attachment.name || attachment.original_name,
          size: attachment.byte_size || 0,
          mediaType,
          pageCount: attachment.page_count || 0,
          failedPages: attachment.failed_pages || [],
          errorCode: attachment.error_code || '',
          ocrText: attachment.question_text || attachment.ocr_text || lastUser,
          statusText: attachment.ocr_status === 'completed' ? '识别完成，请核对题目' : (attachment.ocr_status || '处理中'),
          ocr_confidence: attachment.ocr_confidence,
          filePath: '',
        }
        if (mediaType !== 'application/pdf') {
          attachmentContent(attachment.id).then((url) => { item.attachment.filePath = url }).catch((error) => {
            item.attachment.statusText = '附件加载失败'
            item.attachment.errorText = (error && error.message) || '无法加载附件文件'
          })
        }
      }
      out.push(item)
    } else if (m.role === 'assistant') {
      out.push({
        role: 'ai',
        id: m.id || '',
        answer: m.content || '',
        final_answer: (m.learning_path && m.learning_path.final_answer) || '',
        steps: (m.learning_path && m.learning_path.steps) || m.content || '',
        exercises: m.exercises || (m.learning_path && m.learning_path.exercises) || [],
        knowledge_point: m.knowledge_point || '',
        prerequisite_gaps: m.prerequisite_gaps || [],
        learning_path: normalizeLearningPath(m),
        source: m.source || '',
        refused: !!m.refused,
        failed: m.status === 'failed',
        error_message: m.error_message || '',
        retryQuestion: lastUser,
        open: { pre: false, body: true, cons: false },
        videosLoaded: false,
        videosLoading: false,
        videosError: false,
        videosNoIds: false,
      })
    }
  }
  return out
}


async function loadConversation(conversationId, targetMessageId = '') {
  if (!store.auth.user) {
    goAuth()
    return
  }

  historyLoading.value = true

  try {
    const page = await listMessages(conversationId, { limit: 50 })

    messages.splice(0, messages.length, ...toUiMessages(page.items))

    store.currentConversationId = conversationId
    uni.setStorageSync('last_conversation_id', conversationId)

    messagesCursor.value = page.next_cursor || ''
    hasEarlier.value = !!page.has_more

    const lastAi = [...messages].reverse().find(
      (m) => m.role === 'ai' && m.learning_path
    )

    if (lastAi) {
      store.learningPath = lastAi.learning_path
      store.knowledgePoint = lastAi.knowledge_point
      store.source = lastAi.source
    }

    // 如果是从历史页面点击某道题进入，则定位到指定消息
    if (targetMessageId) {
      // 如果目标消息不在当前页面，继续加载更早的消息
      while (
        !messages.some(m => m.id === targetMessageId) &&
        hasEarlier.value
      ) {
        const previousLength = messages.length

        await loadEarlier()

        // 防止分页没有返回新消息时无限循环
        if (messages.length === previousLength) {
          break
        }
      }

      // 找到目标消息后，滚动到对应位置
      const targetExists = messages.some(
        m => m.id === targetMessageId
      )

      if (targetExists) {
        scrollTo.value = ''
        await nextTick()

        scrollTo.value = 'message-' + targetMessageId
        await nextTick()
      } else {
        uni.showToast({
          title: '没有找到对应的问题',
          icon: 'none'
        })
        scrollBottom()
      }
    } else {
      // 普通打开历史会话，仍然滚动到底部
      scrollBottom()
    }

  } catch (e) {
    if (e && e.status === 401) {
      uni.showToast({
        title: '登录已过期，请重新登录',
        icon: 'none'
      })
      goAuth()
    } else if (e && e.status === 404) {
      uni.showToast({
        title: '会话不存在',
        icon: 'none'
      })
      newConversation()
    } else {
      uni.showToast({
        title: (e && e.message) || '加载历史失败',
        icon: 'none'
      })
    }
  } finally {
    historyLoading.value = false
  }
}


async function loadEarlier() {
  if (!hasEarlier.value || loadingEarlier.value || !store.currentConversationId) return
  loadingEarlier.value = true
  try {
    const page = await listMessages(store.currentConversationId, {
      limit: 50,
      cursor: messagesCursor.value || null,
    })
    messages.unshift(...toUiMessages(page.items))
    messagesCursor.value = page.next_cursor || ''
    hasEarlier.value = !!page.has_more
  } catch (e) {
    uni.showToast({ title: (e && e.message) || '加载更早消息失败', icon: 'none' })
  } finally {
    loadingEarlier.value = false
  }
}

function retry(msg) {
  if (loading.value) return
  const q = (msg.retryQuestion || '').trim()
  if (!q) return
  question.value = q
  send()
}

onLoad((options) => {
  // 外部 reLaunch 时通过 ?tab=N 打开对应 tab：0 学习 / 1 自律 / 2 我的
  const tab = Number(options && options.tab)
  if (Number.isInteger(tab) && tab >= 0 && tab < TAB_ITEMS.length) {
    activeTab.value = tab
  }

  if (options && options.conversation_id) {
    const conversationId = options.conversation_id
    if (store.auth.ready) {
      loadConversation(conversationId)
    } else {
      const stop = watch(
        () => store.auth.ready,
        (ready) => {
          if (ready) {
            stop()
            loadConversation(conversationId)
          }
        }
      )
    }
  } else {
    // 👇 修复：如果 URL 没有带 id，尝试从本地缓存恢复上次的会话
    const lastId = uni.getStorageSync('last_conversation_id')
    if (lastId && !store.currentConversationId) {
      store.currentConversationId = lastId
    }
  }
})

onShow(() => {
  // 从裁切页返回：消费裁切结果并直接上传解答
  consumeCropResult()

  // 每次页面显示，重新读取最新缓存昵称
  const savedNickname = uni.getStorageSync('custom_nickname')
  currentNickname.value = savedNickname || ''

  // 从子页面返回后刷新“自律”与“我的”
  sdRefresh.value++
  myRefresh.value++

  // 每天首次进入刷新今日建议；从诊断/编辑资料返回时也会重新计算。
  todayDismissed.value = readTodayDismissed()
  loadTodaySuggestions()

  const action = store.pendingIndexAction
  if (action) {
    store.pendingIndexAction = null

   if (action.type === 'open' && action.conversationId) {
  loadConversation(action.conversationId, action.messageId || '')
  return
}
    if (action.type === 'new') {
      if (loading.value || recordStarting.value || recordState.value !== 'idle') return
      clearConversationView()
      return
    }
  }

  // 👇 核心修复：如果页面被重新挂载，但之前有会话 ID 或本地缓存，且消息列表为空，自动重新加载
  let activeId = store.currentConversationId || uni.getStorageSync('last_conversation_id')
  if (activeId && messages.length === 0 && !historyLoading.value && !loading.value) {
    loadConversation(activeId)
  }
})

// 启动时若 onShow 早于登录校验完成，等 ready 后再拉一次。
watch(
  () => store.auth.ready,
  (ready) => {
    if (ready) loadTodaySuggestions()
  }
)

// 登录/退出后立即刷新或清空，避免看到上一位学生的建议。
watch(
  () => store.auth.token,
  (token) => {
    if (!token) {
      todaySuggestions.value = []
      return
    }
    loadTodaySuggestions()
  }
)

function scrollBottom() {
  scrollTo.value = ''
  setTimeout(() => {
    scrollTo.value = 'msg-' + (messages.length - 1)
  }, 50)
}

function formatBytes(size) {
  if (!size) return '大小未知'
  return size < 1024 * 1024 ? `${Math.ceil(size / 1024)} KB` : `${(size / 1024 / 1024).toFixed(1)} MB`
}

async function previewDraftAttachment() {
  if (!attachment.filePath) return
  if (attachment.mediaType === 'application/pdf') {
    uni.showToast({ title: '请先上传 PDF，再从消息中打开原文件', icon: 'none' })
    return
  }
  // #ifdef H5
  if (typeof window !== 'undefined') window.open(attachment.filePath, '_blank', 'noopener')
  // #endif
  // #ifndef H5
  uni.previewImage({ current: attachment.filePath, urls: [attachment.filePath] })
  // #endif
}

async function previewMessageAttachment(msg) {
  if (!msg || !msg.attachment || previewingAttachment.value) return
  const item = msg.attachment
  // Open the tab during the user gesture so H5 browsers do not block it.
  // #ifdef H5
  const pdfWindow = item.mediaType === 'application/pdf' && typeof window !== 'undefined' ? window.open('', '_blank') : null
  // #endif
  previewingAttachment.value = true
  try {
    if (!item.filePath && item.id) item.filePath = await attachmentContent(item.id)
    if (!item.filePath) throw new Error('无法加载附件文件')
    if (item.mediaType === 'application/pdf') {
      await openAttachmentFile(item.id, item.filePath, item.name, item.mediaType, pdfWindow)
    } else {
      // #ifdef H5
      if (typeof window !== 'undefined') window.open(item.filePath, '_blank', 'noopener')
      // #endif
      // #ifndef H5
      uni.previewImage({ current: item.filePath, urls: [item.filePath] })
      // #endif
    }
  } catch (error) {
    // #ifdef H5
    if (pdfWindow && !pdfWindow.closed) pdfWindow.close()
    // #endif
    uni.showToast({ title: (error && error.message) || '附件打开失败', icon: 'none' })
  } finally {
    previewingAttachment.value = false
  }
}

async function openAttachmentFile(attachmentId, url, name, mediaType, pdfWindow = null) {
  // #ifdef H5
  if (url && typeof window !== 'undefined') {
    if (pdfWindow && !pdfWindow.closed) pdfWindow.location.href = url
    else window.open(url, '_blank', 'noopener')
    return
  }
  // #endif
  // #ifdef APP-PLUS
  const token = store.auth.token || ''
  const response = await new Promise((resolve, reject) => uni.request({
    url: `${BASE_URL}/api/attachments/${encodeURIComponent(attachmentId)}/content`,
    method: 'GET',
    responseType: 'arraybuffer',
    header: { Authorization: `Bearer ${token}` },
    success: (res) => res.statusCode >= 200 && res.statusCode < 300 ? resolve(res.data) : reject(new Error('PDF 下载失败')),
    fail: () => reject(new Error('PDF 下载失败')),
  }))
  const filename = pdfTempName(name)
  const entry = await new Promise((resolve, reject) => plus.io.requestFileSystem(plus.io.PRIVATE_DOC, (fs) => fs.root.getFile(filename, { create: true }, resolve, reject), reject))
  await new Promise((resolve, reject) => entry.createWriter((writer) => {
    writer.onwrite = resolve
    writer.onerror = () => reject(new Error('PDF 保存失败'))
    writer.write(new Blob([response], { type: mediaType || 'application/pdf' }))
  }, reject))
  plus.runtime.openFile(entry.toLocalURL(), {}, () => uni.showToast({ title: '当前设备没有可用的 PDF 阅读器', icon: 'none' }))
  // #endif
  // #ifndef H5
  // #ifndef APP-PLUS
  uni.showToast({ title: '当前平台暂不支持打开 PDF', icon: 'none' })
  // #endif
  // #endif
}

function clearAttachment() {
  if (attachment.id) deleteAttachment(attachment.id).catch(() => {})
  Object.assign(attachment, { filePath: '', file: null, name: '', size: 0, id: '', ocrText: '', statusText: '', menuOpen: false, mediaType: '', pageCount: 0, failedPages: [] })
  attachmentMessage.value = null
  pendingQuestions.value = []
  questionPickerOpen.value = false
}

function choosePdf() {
  attachment.menuOpen = false
  // #ifdef H5
  if (typeof document !== 'undefined') {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'application/pdf,.pdf'
    input.onchange = () => {
      const file = input.files && input.files[0]
      if (!file) return
      setPdfDraft(file.name || 'document.pdf', file, file.name || 'document.pdf', file.size || 0)
    }
    input.click()
    return
  }
  // #endif
  if (typeof uni.chooseFile === 'function') {
    uni.chooseFile({ count: 1, type: 'file', extension: ['pdf'], success: (res) => {
      const file = res.tempFiles && res.tempFiles[0]
      const path = (res.tempFilePaths && res.tempFilePaths[0]) || (file && file.path)
      if (file && path) setPdfDraft(path, null, file.name || '题目.pdf', file.size || 0)
    }, fail: () => uni.showToast({ title: '未选择 PDF 文件', icon: 'none' }) })
  } else {
    uni.showToast({ title: '当前平台暂不支持选择 PDF 文件', icon: 'none' })
  }
}

function queueAttachmentDraft(draft) {
  pendingQuestions.value = []
  questionPickerOpen.value = false
  Object.assign(attachment, { ...draft, menuOpen: false })
  const message = { role: 'user', text: '', attachment: { ...draft } }
  messages.push(message)
  attachmentMessage.value = message
  scrollBottom()
  // 选完/裁切完直接上传 + 识别 + 解答
  sendAttachment()
}

function setPdfDraft(filePath, file, name, size) {
  if (size > 20 * 1024 * 1024) {
    uni.showToast({ title: 'PDF 文件不能超过 20 MB', icon: 'none' })
    return
  }
  queueAttachmentDraft({
    filePath: String(filePath || name || 'document.pdf'),
    file: typeof File !== 'undefined' && file instanceof File ? file : null,
    name,
    size,
    id: '',
    ocrText: '',
    statusText: '待发送',
    mediaType: 'application/pdf',
    pageCount: 0,
    failedPages: [],
  })
}

function consumeCropResult() {
  const result = cropSession.result
  if (!result) return
  cropSession.result = null
  if (result.cancelled) {
    resetCropSession()
    return
  }
  if (!result.filePath) {
    resetCropSession()
    return
  }
  queueAttachmentDraft({
    filePath: result.filePath,
    file: result.file || null,
    name: result.name || '题目图片',
    size: result.size || 0,
    id: '',
    ocrText: '',
    statusText: '待发送',
  })
  resetCropSession()
}

function toggleAttachmentMenu() {
  if (!store.auth.user) {
    uni.showToast({ title: '登录后才能上传题目图片', icon: 'none' })
    return
  }
  attachment.menuOpen = !attachment.menuOpen
}

function chooseAttachment(sourceType) {
  attachment.menuOpen = false
  pendingQuestions.value = []
  questionPickerOpen.value = false
  uni.chooseImage({ count: 1, sizeType: ['compressed'], sourceType: [sourceType], success: (res) => {
    const path = res.tempFilePaths && res.tempFilePaths[0]
    const file = res.tempFiles && res.tempFiles[0]
    if (!path) return
    const name = (file && file.name) || path.split('/').pop() || '题目图片'
    const size = (file && file.size) || 0
    const lower = name.toLowerCase()
    if (lower && !/\.(jpe?g|png)$/.test(lower)) {
      uni.showToast({ title: '仅支持 JPG 或 PNG 图片', icon: 'none' })
      return
    }
    const draft = { filePath: path, file: file && typeof File !== 'undefined' && file instanceof File ? file : null, name, size, id: '', ocrText: '', statusText: '待发送' }

    // #ifdef H5 || APP-PLUS
    cropSession.src = path
    cropSession.file = draft.file
    cropSession.name = name
    cropSession.size = size
    cropSession.result = null
    uni.navigateTo({
      url: '/pages/crop/crop',
      fail: () => {
        resetCropSession()
        queueAttachmentDraft(draft)
      },
    })
    // #endif

    // #ifndef H5
    // #ifndef APP-PLUS
    queueAttachmentDraft(draft)
    // #endif
    // #endif
  }, fail: () => uni.showToast({ title: '未选择图片', icon: 'none' }) })
}

async function recognizeAttachment({ fromUpload = false } = {}) {
  const target = attachmentMessage.value && attachmentMessage.value.attachment
  if (!attachment.id || (attachmentBusy.value && !fromUpload)) return
  attachmentBusy.value = true
  attachment.statusText = '识别中'
  try {
    let data
    if (attachment.mediaType === 'application/pdf') {
      data = await attachmentStatus(attachment.id)
      if (data.ocr_status === 'failed') {
        data = await attachmentAction(attachment.id, 'recognize')
      }
      for (let attempt = 0; attempt < 45 && data.ocr_status === 'processing'; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 2000))
        data = await attachmentStatus(attachment.id)
      }
    } else {
      data = await attachmentAction(attachment.id, 'recognize')
    }
    attachment.ocrText = data.ocr_text || ''
    attachment.pageCount = data.page_count || 0
    attachment.failedPages = data.failed_pages || []
    attachment.statusText = data.ocr_status === 'partial' ? '部分页面识别完成' : (data.ocr_status === 'failed' ? `识别失败${data.error_code ? `（${data.error_code}）` : ''}` : '识别完成，请核对题目')
    if (target) Object.assign(target, { id: attachment.id, ocrText: attachment.ocrText, statusText: attachment.statusText, ocr_confidence: data.ocr_confidence, pageCount: attachment.pageCount, failedPages: attachment.failedPages, mediaType: attachment.mediaType, errorCode: data.error_code })
    if (!attachment.ocrText) uni.showToast({ title: '未识别到题目文字，请手动输入', icon: 'none' })
  } catch (e) {
    attachment.statusText = '识别失败'
    if (target) Object.assign(target, { statusText: attachment.statusText, errorText: (e && e.message) || '识别失败，请重试' })
    uni.showToast({ title: (e && e.message) || '图片识别失败', icon: 'none' })
  } finally { attachmentBusy.value = false }
}

async function maybeAutoSolveAttachment() {
  const text = String(attachment.ocrText || '').trim()
  if (!text || /识别失败/.test(attachment.statusText)) return

  const questions = splitQuestionText(text)
  if (questions.length > 1) {
    pendingQuestions.value = questions
    questionPickerOpen.value = true
    attachment.statusText = '识别到多道题，请选择'
    if (attachmentMessage.value) {
      attachmentMessage.value.attachment.statusText = attachment.statusText
    }
    return
  }

  attachment.statusText = '识别完成，正在解答'
  if (attachmentMessage.value) {
    attachmentMessage.value.attachment.statusText = attachment.statusText
  }
  await solveAttachment()
}

function chooseQuestion(index) {
  const text = pendingQuestions.value[index]
  if (!text) return

  questionPickerOpen.value = false
  pendingQuestions.value = []
  attachment.ocrText = text
  if (attachmentMessage.value) {
    attachmentMessage.value.attachment.ocrText = text
    attachmentMessage.value.attachment.statusText = '正在解答'
  }
  attachment.statusText = '正在解答'
  solveAttachment()
}

function onMessageOcrInput(msg) {
  if (!msg || !msg.attachment) return
  attachmentMessage.value = msg
  attachment.ocrText = msg.attachment.ocrText || ''
}

async function recognizeMessageAttachment(msg) {
  if (!msg || !msg.attachment) return
  attachmentMessage.value = msg
  Object.assign(attachment, msg.attachment)
  await recognizeAttachment()
  await maybeAutoSolveAttachment()
}

async function solveMessageAttachment(msg) {
  if (!msg || !msg.attachment) return
  attachmentMessage.value = msg
  // 只同步 id 和状态，不覆盖用户可能在编辑区修改的 ocrText
  attachment.id = msg.attachment.id
  attachment.statusText = msg.attachment.statusText
  attachment.mediaType = msg.attachment.mediaType
  attachment.name = msg.attachment.name
  attachment.size = msg.attachment.size
  attachment.filePath = msg.attachment.filePath
  attachment.pageCount = msg.attachment.pageCount || 0
  attachment.failedPages = msg.attachment.failedPages || []
  // 卡片里的文本是用户最后编辑的版本，优先使用它
  const text = String(msg.attachment.ocrText || attachment.ocrText || '').trim()
  if (text) attachment.ocrText = text
  await solveAttachment()
}

/**
 * 同步编辑区的 OCR 文本到消息卡片，确保两边数据一致
 */
function syncOcrText() {
  if (attachmentMessage.value && attachmentMessage.value.attachment) {
    attachmentMessage.value.attachment.ocrText = attachment.ocrText
  }
}

async function solveWithCandidate(msg, candidate) {
  if (!msg || !candidate || !msg.attachment || attachmentBusy.value) return
  attachmentMessage.value = msg
  // 只同步元数据，保留用户最后编辑的 ocrText
  attachment.id = msg.attachment.id
  attachment.statusText = msg.attachment.statusText
  if (msg.attachment.ocrText) {
    attachment.ocrText = msg.attachment.ocrText
  }
  await solveAttachment(candidate.id)
}


async function solveAttachment(knowledgePointId = null) {
  const text = (typeof attachment.ocrText === 'string')
    ? attachment.ocrText.trim()
    : String(attachment.ocrText || '').trim()

  if (!attachment.id || !text || attachmentBusy.value) return

  attachmentBusy.value = true
  attachment.statusText = '知识点匹配与解答生成中'
  if (attachmentMessage.value) {
    attachmentMessage.value.attachment.statusText = attachment.statusText
  }

  // 构建请求体
  const payload = { text }

  if (store.currentConversationId) {
    payload.conversation_id = store.currentConversationId
  }

  if (typeof knowledgePointId === 'string' && knowledgePointId) {
    payload.knowledge_point_id = knowledgePointId
  }

  try {
    const data = await attachmentAction(attachment.id, 'solve', payload)

    if (attachmentMessage.value) {
      attachmentMessage.value.attachment.ocrText = text
    }

    // 添加 AI 解答消息
    messages.push({
      role: 'ai',
      id: data.assistant_message_id || '',
      answer: data.answer || data.coverage_note || '',
      solution_steps: data.solution_steps || [],
      final_answer: data.final_answer || '',
      exercises: data.exercises || [],
      knowledge_point: data.knowledge_point || '',
      knowledge_confidence: data.knowledge_confidence,
      knowledge_candidates: data.knowledge_candidates || [],
      prerequisite_gaps: data.prerequisite_gaps || [],
      learning_path: normalizeLearningPath(data),
      source: data.source || '',
      refused: !!data.refused,
      failed: false,
      retryQuestion: text,
      open: { pre: false, body: true, cons: false },
      videosLoaded: false,
      videosLoading: false,
      videosError: false,
      videosNoIds: false
    })
    const aiMsg = messages[messages.length - 1]
    if (aiMsg && !aiMsg.refused && !aiMsg.failed) loadVideos(aiMsg)

    attachment.statusText = '已完成'

    if (attachmentMessage.value) {
      attachmentMessage.value.attachment.statusText = attachment.statusText
    }

    clearAttachment()
    scrollBottom()

    // 图片/PDF 解题成功后，自动朗读
if (autoPlayEnabled.value && !messages[messages.length - 1].refused) {
  const currentIndex = messages.length - 1
  const answerText = getSpeechText(messages[currentIndex])

  if (answerText) {
    setTimeout(() => {
      playTTS(answerText, currentIndex)
    }, 300)
  }
}

  } catch (e) {
    // 详细打印错误信息，便于定位问题
    console.error('[solveAttachment] 请求失败:', {
      status: e?.status,
      code: e?.code,
      message: e?.message,
      details: e?.details,
      attachmentId: attachment.id,
      textLength: text?.length,
      payload: JSON.stringify(payload)
    })

    attachment.statusText = '解答失败'

    if (attachmentMessage.value) {
      attachmentMessage.value.attachment.statusText = attachment.statusText
      attachmentMessage.value.attachment.errorText =
        (e && e.message) || '解答失败，请重试'
    }

    uni.showToast({
      title: (e && e.message) || '题目解答失败',
      icon: 'none'
    })

  } finally {
    attachmentBusy.value = false
  }
}


async function retryAttachmentUpload(msg) {
  if (!msg || !msg.attachment || attachmentBusy.value) return
  attachmentMessage.value = msg
  Object.assign(attachment, msg.attachment)
  await sendAttachment()
}

async function sendAttachment() {
  if (!attachment.filePath || attachmentBusy.value) return
  if (!store.auth.user) { uni.showToast({ title: '登录后才能上传题目图片', icon: 'none' }); return }
  attachmentBusy.value = true
  attachment.statusText = '上传中'
  if (attachmentMessage.value) {
    attachmentMessage.value.attachment.statusText = '上传中'
  }
  try {
    const data = await uploadAttachment(attachment.filePath, { file: attachment.file, conversationId: store.currentConversationId || null })
    attachment.mediaType = data.media_type || attachment.mediaType
    attachment.id = data.id
    if (attachmentMessage.value) {
      Object.assign(attachmentMessage.value.attachment, { id: data.id, statusText: '识别中' })
    }
    if (data.conversation_id) {
      store.currentConversationId = data.conversation_id
      uni.setStorageSync('last_conversation_id', data.conversation_id)
    }
    attachment.statusText = '识别中'
    await recognizeAttachment({ fromUpload: true })
    await maybeAutoSolveAttachment()
  } catch (e) {
    attachment.statusText = '上传失败'
    if (attachmentMessage.value) {
      attachmentMessage.value.attachment.statusText = attachment.statusText
      attachmentMessage.value.attachment.errorText = `${(e && e.message) || '附件上传失败，请重试'}${e && e.code ? `（${e.code}）` : ''}`
    }
    uni.showToast({ title: `${(e && e.message) || '附件上传失败，请重试'}${e && e.code ? `（${e.code}）` : ''}`, icon: 'none' })
    attachmentBusy.value = false
  }
}

/** 聊天用年级：登录用户读资料，游客读本地设置；只影响讲解深度。 */
function currentGradeForChat() {
  const grade = store.auth.user && store.auth.user.grade
  if (Number.isInteger(grade)) return grade
  const saved = uni.getStorageSync('user_grade')
  const parsed = Number(saved)
  if (saved !== '' && saved != null && Number.isInteger(parsed) && parsed >= 1 && parsed <= 9) {
    return parsed
  }
  return null
}

function send() {
  if (attachment.filePath && !attachment.id) { sendAttachment(); return }
  const q = question.value.trim()
  if (!q || loading.value || attachmentBusy.value || recordStarting.value || recordState.value !== 'idle') return
  messages.push({ role: 'user', text: q })
  question.value = ''
  loading.value = true
  scrollBottom()

  const loggedIn = !!(store.auth.user && store.auth.token)
  const requestId = newRequestId()

  askQuestion(q, {
    conversationId: loggedIn ? store.currentConversationId || null : null,
    clientRequestId: loggedIn ? requestId : null,
    auth: loggedIn,
    grade: currentGradeForChat(),
  })
    .then((data) => {
      if (data.conversation_id) {
        store.currentConversationId = data.conversation_id
        // 👇 新增：每次提问成功，都把最新会话 ID 保存到本地缓存
        uni.setStorageSync('last_conversation_id', data.conversation_id)
      }
      messages.push({
        role: 'ai',
        id: data.assistant_message_id || '',
        answer: data.answer || '',
        knowledge_point: data.knowledge_point || '',
        prerequisite_gaps: data.prerequisite_gaps || [],
        learning_path: normalizeLearningPath(data),
        source: data.source || '',
        refused: !!data.refused,
        failed: false,
        error_message: '',
        retryQuestion: q,
        open: { pre: false, body: true, cons: false },
        videosLoaded: false,
        videosLoading: false,
        videosError: false,
        videosNoIds: false,
      })
      const aiMsg = messages[messages.length - 1]
      if (aiMsg && !aiMsg.refused && !aiMsg.failed) loadVideos(aiMsg)
            // 普通文字提问成功后，自动朗读
      if (autoPlayEnabled.value && !data.refused) {
        const currentIndex = messages.length - 1
        const answerText = getSpeechText(messages[currentIndex])

        if (answerText) {
          setTimeout(() => {
            playTTS(answerText, currentIndex)
          }, 300)
        }
      }
    })
    .catch((e) => {
      if (e && e.status === 404) {
        store.currentConversationId = ''
        uni.removeStorageSync('last_conversation_id')
      }
      const errMsg =
        e && e.status === 401
          ? '登录已过期，请重新登录后重试'
          : (e && e.message) || '网络请求失败，请检查后端是否启动、地址是否配置正确'
      messages.push({
        role: 'ai',
        id: '',
        answer: '',
        refused: false,
        failed: true,
        error_message: errMsg,
        knowledge_point: '',
        prerequisite_gaps: [],
        learning_path: normalizeLearningPath(null),
        source: '',
        retryQuestion: q,
        open: { pre: false, body: true, cons: false },
        videosLoaded: false,
        videosLoading: false,
        videosError: false,
        videosNoIds: false,
      })
    })
    .finally(() => {
      loading.value = false
      scrollBottom()
    })
}

// 移动端播放器会显示合集总时长/播放量，隐藏封面信息避免被误认为整条合集。
function withHideCoverInfo(url) {
  if (!url || url.includes('hideCoverInfo=')) return url
  return url + (url.includes('?') ? '&' : '?') + 'hideCoverInfo=1'
}

function openVideo(gap, video) {
  // #ifdef H5
  // 移动端内嵌 B 站播放器（mbplayer.html）会尝试跨域设置 window.parent.player，
  // 在 iframe 里会抛未捕获异常导致控件初始化中断；改为顶层新页面打开。
  const ua = navigator.userAgent || ''
  if (/Android|iPhone|iPad|iPod|Mobile/i.test(ua)) {
    const mobileUrl = buildBilibiliMobileUrl(video.bvid, video.page, video.aid, video.cid)
    if (mobileUrl) {
      const win = window.open(mobileUrl, '_blank')
      if (!win) window.location.href = mobileUrl
      return
    }
  }
  const current = activeVideo.value
  if (
    current &&
    current.video_id === video.video_id &&
    current.node_key === gap.id
  ) {
    activeVideo.value = null
  } else {
    activeVideo.value = { ...video, node_key: gap.id, embed_url: withHideCoverInfo(video.embed_url) }
  }
  return
  // #endif
  // #ifndef H5
  const bvid = encodeURIComponent(video.bvid || '')
  const page = Number(video.page || 1)
  const aid = encodeURIComponent(video.aid || '')
  const cid = encodeURIComponent(video.cid || '')
  const title = encodeURIComponent(video.title || '视频讲解')
  uni.navigateTo({
    url: `/pages/video/video?bvid=${bvid}&page=${page}&aid=${aid}&cid=${cid}&title=${title}`,
  })
  // #endif
}

function openMobilePlayer(video) {
  if (!video) return
  const mobileUrl = buildBilibiliMobileUrl(video.bvid, video.page, video.aid, video.cid)
  if (!mobileUrl) return
  // 顶层新窗口打开：避免移动播放器在 iframe 中访问 window.parent 触发跨域异常。
  const win = window.open(mobileUrl, '_blank')
  if (!win) window.location.href = mobileUrl
}

function openWatchPage(video) {
  if (!video || !video.watch_url) return
  // #ifdef H5
  window.open(video.watch_url, '_blank')
  // #endif
  // #ifdef APP-PLUS
  plus.runtime.openURL(video.watch_url)
  // #endif
}

function closeVideo() {
  activeVideo.value = null
}

async function loadVideos(msg, force = false) {
  if (!msg || msg.videosLoading) return
  if (msg.videosLoaded && !force) return
  const gaps = (msg.prerequisite_gaps || []).filter((g) => g && g.id)
  const bodyId = (msg.learning_path && msg.learning_path.body_id) || ''
  const gapIds = Array.from(new Set(gaps.map((g) => g.id)))
  const bodyIds = bodyId && !gapIds.includes(bodyId) ? [bodyId] : []
  // 后端一次最多接受 20 个 node_key，超出会 400；这里截断 gap，优先保留本体
  const ids = [...gapIds.slice(0, 20 - bodyIds.length), ...bodyIds]
  if (!ids.length) {
    msg.videosLoaded = true
    msg.videosNoIds = true
    return
  }
  msg.videosNoIds = false

  msg.videosLoading = true
  msg.videosError = false
  try {
    const data = await listVideos(ids, { limit: 2 })
    const byNode = {}
    for (const item of data.items || []) {
      byNode[item.node_key] = item.videos || []
    }
    for (const gap of gaps) {
      gap.videos = byNode[gap.id] || []
      gap.videosLoaded = true
    }
    // 本体知识点也有视频时，显示在“解题过程”下方
    msg.bodyVideos = bodyId ? (byNode[bodyId] || []) : []
    msg.bodyVideosLoaded = true
    msg.videosLoaded = true
  } catch (e) {
    msg.videosError = true
    uni.showToast({ title: (e && e.message) || '视频加载失败', icon: 'none' })
  } finally {
    msg.videosLoading = false
  }
}

function toggle(msg, key) {
  msg.open[key] = !msg.open[key]
  if (key === 'pre' && msg.open.pre) loadVideos(msg)
}

function goPath(msg) {
  store.learningPath = msg.learning_path
  store.knowledgePoint = msg.knowledge_point
  store.source = msg.source
  uni.navigateTo({ url: '/pages/path/path' })
}
</script>

<style>
/* 局部语义色：警告/成功/危险的浅底在深浅模式下保持可读 */
.tab-root {
  --ik-danger-weak: rgba(229, 62, 62, 0.08);
  --ik-danger-line: rgba(229, 62, 62, 0.32);
  --ik-warn: #c05621;
  --ik-warn-strong: #975a16;
  --ik-warn-weak: rgba(192, 86, 33, 0.1);
  --ik-warn-line: rgba(192, 86, 33, 0.35);
  --ik-success-weak: rgba(47, 158, 104, 0.1);
}
.tab-root.is-dark {
  --ik-danger-weak: rgba(255, 107, 107, 0.14);
  --ik-danger-line: rgba(255, 107, 107, 0.38);
  --ik-warn: #f6ad55;
  --ik-warn-strong: #fbd38d;
  --ik-warn-weak: rgba(246, 173, 85, 0.14);
  --ik-warn-line: rgba(246, 173, 85, 0.4);
  --ik-success-weak: rgba(74, 222, 128, 0.16);
}

.tab-root {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--ik-bg);
  overflow: hidden;
}
/* #ifdef H5 */
.tab-root {
  height: calc(100vh - var(--window-top, 0px) - var(--window-bottom, 0px));
}
/* #endif */

.tab-swiper {
  flex: 1;
  height: 0; /* flex 子项必须显式给 0，否则 swiper 高度异常 */
  min-height: 0;
}
.tab-swiper-item {
  height: 100%;
  overflow: hidden;
}
.tab-swiper-item .page {
  height: 100%;
}

/* 主题背景图由 ThemeBackground 组件统一处理，排除它之外的子元素保持原有层级 */
.tab-root > *:not(.theme-bg) {
  position: relative;
  z-index: 1;
}
/* 按住说话浮层必须真正 fixed，不能被上面的通用规则改成 relative */
.tab-root > .voice-overlay {
  position: fixed;
  z-index: 900;
}
/* 侧边栏必须在底部导航之上，抽屉才能盖住 tabbar */
.tab-root > .sidebar-root {
  z-index: 10;
}

/* 左边缘手势热区：16dp，避开底部导航，避免挡住 tab 点击 */
.tab-root > .drawer-edge {
  position: fixed;
  top: 0;
  left: 0;
  bottom: calc(64px + env(safe-area-inset-bottom));
  width: 32rpx;
  z-index: 5;
  background: transparent;
}

/* wd-popup 需要脱离 .tab-root > * 的层叠上下文，fixed 才能覆盖全局 */
.tab-root > .wd-popup-wrapper {
  position: static;
  z-index: auto;
}

.page {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--ik-bg);
}

/* 深色模式用描边替代黑色阴影 */
.is-dark .bubble-ai {
  box-shadow: none;
  border: 1rpx solid var(--ik-line);
}
.is-dark .input {
  box-shadow: none;
  border: 1rpx solid var(--ik-line);
}

/* 自定义导航栏：56dp 内容高，仅图标操作，不设标题 */
.topbar {
  flex: 0 0 auto;
  height: 112rpx;
  box-sizing: content-box;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 4rpx;
  background: var(--ik-bg);
  position: relative;
  z-index: 10;
}

.topbar-actions {
  display: flex;
  align-items: center;
  gap: 4rpx;
}

/* 48dp 触控区，图标视觉宽度约 22dp */
.topbar-icon-btn {
  width: 96rpx;
  height: 96rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 24rpx;
  color: var(--ik-t1);
  transition: background 0.15s;
}
.topbar-icon-btn:active {
  background: var(--ik-soft);
}
.topbar-icon-btn.is-off {
  opacity: 0.45;
}
.topbar-icon-btn .topbar-icon {
  font-size: 44rpx;
  line-height: 1;
  color: currentColor;
}
.topbar-icon-btn .topbar-icon--primary {
  color: var(--ik-primary);
}

.load-earlier {
  text-align: center;
  font-size: 24rpx;
  color: var(--ik-primary);
  padding: 12rpx 0 24rpx;
}

.chat {
  flex: 1;
  overflow: hidden;
  padding: 24rpx;
  box-sizing: border-box;
}

.welcome {
  margin-top: 96rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
}
.welcome-mark {
  width: 128rpx;
  height: 128rpx;
  margin-bottom: 24rpx;
}
.welcome-text {
  font-size: 28rpx;
  color: var(--ik-t2);
  text-align: center;
  line-height: 1.6;
  padding: 0 24rpx;
}
/* ---------- 今日建议 ---------- */
.today-card {
  margin-bottom: 24rpx;
  padding: 24rpx;
  background: var(--ik-card);
  border: 1rpx solid var(--ik-line);
  border-radius: 20rpx;
  box-shadow: 0 8rpx 24rpx rgba(0, 0, 0, 0.04);
}
.today-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}
.today-head-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.today-title {
  font-size: 30rpx;
  font-weight: 700;
  color: var(--ik-t1);
}
.today-sub {
  margin-top: 4rpx;
  font-size: 22rpx;
  color: var(--ik-t3);
}
.today-close {
  flex: 0 0 auto;
  width: 44rpx;
  height: 44rpx;
  margin-left: 16rpx;
  line-height: 40rpx;
  text-align: center;
  border-radius: 50%;
  color: var(--ik-t3);
  font-size: 32rpx;
}
.today-close:active {
  background: var(--ik-soft);
}
.today-list {
  margin-top: 16rpx;
}
.today-item {
  display: flex;
  align-items: center;
  padding: 16rpx 0;
  border-top: 1rpx solid var(--ik-line);
}
.today-item:first-child {
  padding-top: 8rpx;
  border-top: none;
}
.today-item-main {
  flex: 1;
  min-width: 0;
}
.today-item-title {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8rpx;
}
.today-badge {
  flex: 0 0 auto;
  padding: 2rpx 10rpx;
  border-radius: 999rpx;
  font-size: 20rpx;
  color: var(--ik-primary);
  background: var(--ik-primary-weak);
}
.today-badge.is-wrong {
  color: var(--ik-danger);
  background: var(--ik-danger-weak);
}
.today-badge.is-trend {
  color: var(--ik-warn-strong);
  background: var(--ik-warn-weak);
}
.today-badge.is-prerequisite {
  color: var(--ik-success);
  background: var(--ik-success-weak);
}
.today-badge.is-onboarding {
  color: var(--ik-t2);
  background: var(--ik-soft);
}
.today-name {
  font-size: 27rpx;
  font-weight: 600;
  color: var(--ik-t1);
}
.today-grade {
  font-size: 20rpx;
  color: var(--ik-t3);
}
.today-reason {
  display: block;
  margin-top: 4rpx;
  font-size: 23rpx;
  line-height: 1.5;
  color: var(--ik-t2);
}
.today-arrow {
  flex: 0 0 auto;
  margin-left: 12rpx;
  font-size: 30rpx;
  color: var(--ik-t3);
}

.quick-list {
  width: 100%;
  max-width: 560rpx;
  margin-top: 36rpx;
  display: flex;
  flex-direction: column;
  gap: 12rpx;
}
.quick-item {
  height: 80rpx;
  line-height: 80rpx;
  padding: 0 24rpx;
  text-align: center;
  font-size: 26rpx;
  color: var(--ik-t1);
  background: var(--ik-card);
  border: 1rpx solid var(--ik-line);
  border-radius: 999rpx;
  box-sizing: border-box;
}
.quick-item:active {
  color: var(--ik-primary);
  background: var(--ik-primary-weak);
  border-color: var(--ik-primary);
}

.msg-row {
  margin-bottom: 24rpx;
}
.msg {
  display: flex;
  align-items: flex-start;
  gap: 14rpx;
  width: 100%;
  box-sizing: border-box;
}
.msg-user { justify-content: flex-end; }
.msg-ai { justify-content: flex-start; }
.msg-content { min-width: 0; max-width: calc(100% - 84rpx); }
.message-avatar { flex: 0 0 64rpx; width: 64rpx; height: 64rpx; border-radius: 50%; background: var(--ik-soft); object-fit: cover; }
.assistant-name { margin: 2rpx 0 8rpx 4rpx; color: var(--ik-t2); font-size: 22rpx; }

.bubble {
  max-width: 86%;
  padding: 20rpx 24rpx;
  border-radius: 20rpx;
  font-size: 28rpx;
  line-height: 1.6;
  word-break: break-all;
}
.bubble-user {
  background: var(--ik-primary);
  color: var(--ik-on-primary);
  border-top-right-radius: 6rpx;
}
.msg-user .bubble {
  max-width: 100%;
}
.bubble-ai {
  background: var(--ik-card);
  color: var(--ik-t1);
  border-top-left-radius: 6rpx;
  box-shadow: 0 2rpx 8rpx rgba(0, 0, 0, 0.04);
}
.answer-summary { padding-bottom: 8rpx; }
.summary-label { display: block; margin-bottom: 8rpx; color: var(--ik-t2); font-size: 22rpx; font-weight: 600; }
.final-answer { margin-top: 18rpx; padding: 18rpx; background: var(--ik-success-weak); border-left: 6rpx solid var(--ik-success); border-radius: 8rpx; }
.final-label, .final-text { display: block; }
.final-label { color: var(--ik-success); font-size: 24rpx; font-weight: 700; }
.final-text { margin-top: 6rpx; color: var(--ik-success); font-size: 30rpx; font-weight: 700; line-height: 1.5; white-space: pre-wrap; word-break: break-word; }
.section-count { flex: 1; margin: 0 10rpx; color: var(--ik-t2); font-size: 22rpx; text-align: right; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.question-card { width: min(620rpx, 100%); padding: 18rpx; background: var(--ik-soft); border: 1rpx solid var(--ik-line); border-radius: 14rpx; box-sizing: border-box; }
.question-card-head { display: flex; justify-content: space-between; gap: 12rpx; color: var(--ik-t1); font-size: 26rpx; font-weight: 700; }
.question-status { color: var(--ik-t3); font-size: 22rpx; font-weight: 400; }
.ocr-warning { display: block; margin-top: 10rpx; padding: 10rpx 12rpx; color: var(--ik-warn-strong); background: var(--ik-warn-weak); border-radius: 6rpx; font-size: 22rpx; line-height: 1.45; }
.question-image { display: block; width: 100%; max-height: 520rpx; margin-top: 14rpx; border-radius: 8rpx; background: var(--ik-soft); }
.question-file { margin-top: 8rpx; color: var(--ik-t3); font-size: 21rpx; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.question-label { display: block; margin-top: 16rpx; color: var(--ik-t2); font-size: 23rpx; font-weight: 600; }
.question-text { width: 100%; min-height: 110rpx; margin-top: 8rpx; padding: 14rpx; box-sizing: border-box; background: var(--ik-input-bg); border: 1rpx solid var(--ik-line); border-radius: 8rpx; color: var(--ik-t1); font-size: 26rpx; line-height: 1.55; }
.question-actions { display: flex; gap: 10rpx; margin-top: 10rpx; }
.question-actions button { flex: 1; min-width: 0; margin: 0; padding: 0 10rpx; color: var(--ik-primary); background: var(--ik-primary-weak); border: 0; border-radius: 8rpx; font-size: 23rpx; line-height: 58rpx; }
.typing {
  color: var(--ik-t3);
}

.head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12rpx;
  margin-bottom: 16rpx;
}
.chip {
  background: var(--ik-primary-weak);
  color: var(--ik-primary);
  font-size: 24rpx;
  padding: 4rpx 16rpx;
  border-radius: 999rpx;
}
.source {
  display: block;
  margin-top: 8rpx;
  font-size: 22rpx;
  color: var(--ik-t2);
}

.section {
  border-top: 1rpx solid var(--ik-line);
  padding: 16rpx 0;
}
.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 30rpx;
  font-weight: 600;
  color: var(--ik-t1);
}
.arrow {
  color: var(--ik-t3);
  font-size: 28rpx;
}
.section-body {
  margin-top: 12rpx;
}
.answer {
  font-size: 28rpx;
  color: var(--ik-t1);
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
  color: var(--ik-t1);
}
.gap-tag {
  font-size: 20rpx;
  padding: 2rpx 12rpx;
  border-radius: 999rpx;
}
.t-required {
  background: var(--ik-danger-weak);
  color: var(--ik-danger);
}
.t-suggest {
  background: var(--ik-warn-weak);
  color: var(--ik-warn);
}

.gap-block {
  padding: 8rpx 0;
}
.gap-block + .gap-block {
  border-top: 1rpx dashed var(--ik-line);
}
.video-list {
  display: flex;
  flex-wrap: wrap;
  gap: 16rpx;
  margin: 4rpx 0 12rpx;
}
.body-video-list {
  margin-top: 12rpx;
  padding-top: 12rpx;
  border-top: 1rpx dashed var(--ik-line);
}
.video-section-label {
  width: 100%;
  font-size: 22rpx;
  color: var(--ik-dim);
  margin-bottom: 2rpx;
}
.video-card {
  flex: 1 1 280rpx;
  min-width: 240rpx;
  max-width: 100%;
  display: flex;
  gap: 12rpx;
  padding: 10rpx;
  background: var(--ik-soft);
  border: 1rpx solid var(--ik-line);
  border-radius: 14rpx;
}
.video-cover {
  position: relative;
  width: 160rpx;
  height: 100rpx;
  flex: 0 0 160rpx;
  border-radius: 10rpx;
  overflow: hidden;
  background: #1f2a37;
}
.video-cover-img {
  width: 100%;
  height: 100%;
  display: block;
}
.video-cover-fallback {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--ik-on-primary);
  font-size: 24rpx;
  background: var(--ik-primary);
}
.video-play {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  left: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 30rpx;
  background: rgba(0, 0, 0, 0.28);
}
.video-duration {
  position: absolute;
  right: 6rpx;
  bottom: 6rpx;
  font-size: 18rpx;
  color: #fff;
  background: rgba(0, 0, 0, 0.62);
  padding: 0 6rpx;
  border-radius: 4rpx;
}
.video-meta {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.video-title {
  font-size: 24rpx;
  color: var(--ik-t1);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.video-author {
  margin-top: 6rpx;
  font-size: 20rpx;
  color: var(--ik-t3);
}
.video-empty {
  display: block;
  font-size: 22rpx;
  color: var(--ik-t3);
  padding: 4rpx 0 8rpx;
}
.video-empty-row {
  display: flex;
  align-items: center;
  gap: 16rpx;
}
.video-retry {
  font-size: 22rpx;
  color: var(--ik-primary);
  padding: 4rpx 0 8rpx;
}
.video-player {
  width: 100%;
  flex: 1 0 100%;
  margin: 8rpx 0 16rpx;
}
.video-iframe {
  width: 100%;
  height: 380rpx;
  border: 0;
  border-radius: 12rpx;
  background: #000;
}
.video-close {
  display: block;
  text-align: center;
  font-size: 22rpx;
  color: var(--ik-primary);
  padding: 8rpx 0;
}
.video-actions {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 20rpx;
  padding: 8rpx 0;
}
.video-action {
  font-size: 22rpx;
  color: var(--ik-primary);
}
.video-hint {
  display: block;
  text-align: center;
  font-size: 20rpx;
  color: var(--ik-t3);
  padding: 0 0 8rpx;
}
.video-hint.warn {
  color: var(--ik-warn);
}
.empty {
  font-size: 26rpx;
  color: var(--ik-t3);
}
.exercise {
  padding: 12rpx 0;
  border-bottom: 1rpx dashed var(--ik-line);
}
.exercise:last-child {
  border-bottom: none;
}
.exercise-no {
  display: block;
  font-size: 24rpx;
  font-weight: 600;
  color: var(--ik-primary);
  margin-bottom: 6rpx;
}
.exercise-text {
  display: block;
  font-size: 28rpx;
  color: var(--ik-t1);
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}
.exercise-hint {
  display: block;
  font-size: 22rpx;
  color: var(--ik-t3);
  margin-bottom: 8rpx;
}

.refuse-card {
  background: var(--ik-danger-weak);
  border: 1rpx solid var(--ik-danger-line);
  border-radius: 16rpx;
  padding: 24rpx;
}
.refuse-title {
  font-size: 30rpx;
  font-weight: 600;
  color: var(--ik-danger);
  margin-bottom: 12rpx;
}
.refuse-closest {
  font-size: 26rpx;
  color: var(--ik-danger);
}

.failed-card {
  background: var(--ik-warn-weak);
  border: 1rpx solid var(--ik-warn-line);
  border-radius: 16rpx;
  padding: 24rpx;
}
.failed-title {
  font-size: 30rpx;
  font-weight: 600;
  color: var(--ik-warn);
  margin-bottom: 12rpx;
}
.failed-text {
  font-size: 26rpx;
  color: var(--ik-warn-strong);
  line-height: 1.6;
}
.retry-btn {
  margin-top: 18rpx;
  display: inline-block;
  background: var(--ik-card);
  color: var(--ik-warn);
  font-size: 24rpx;
  border: 1rpx solid var(--ik-warn-line);
  border-radius: 999rpx;
  padding: 0 24rpx;
  line-height: 60rpx;
}
.retry-btn::after {
  border: none;
}

.path-btn {
  display: block;
  width: 100%;
  margin-top: 20rpx;
  background: var(--ik-primary-weak);
  color: var(--ik-primary);
  font-size: 26rpx;
  border-radius: 999rpx;
  padding: 0 24rpx;
  height: 88rpx;
  line-height: 88rpx;
  border: none;
  box-sizing: border-box;
}
.path-btn::after {
  border: none;
}

.attachment-draft {
  display: flex;
  align-items: center;
  gap: 16rpx;
  padding: 12rpx 24rpx;
  background: var(--ik-bg);
  border-top: 1rpx solid var(--ik-line);
}
.attachment-thumb {
  flex: 0 0 88rpx;
  width: 88rpx;
  height: 88rpx;
  border-radius: 8rpx;
  background: var(--ik-soft);
}
.attachment-draft-meta {
  min-width: 0;
  flex: 1;
}
.attachment-name, .attachment-size {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.attachment-name { font-size: 26rpx; color: var(--ik-t1); }
.attachment-size { margin-top: 6rpx; font-size: 22rpx; color: var(--ik-t2); }
.attachment-remove {
  flex: 0 0 64rpx;
  width: 64rpx;
  height: 64rpx;
  padding: 0;
  border: none;
  border-radius: 50%;
  line-height: 64rpx;
  text-align: center;
}
.attachment-remove { color: var(--ik-danger); background: var(--ik-danger-weak); font-size: 36rpx; }
.attachment-text-editor { padding: 12rpx 24rpx; background: var(--ik-bg); }
.attachment-text-editor textarea { width: 100%; min-height: 120rpx; box-sizing: border-box; padding: 16rpx; background: var(--ik-input-bg); border-radius: 8rpx; font-size: 26rpx; }
.attachment-actions { display: flex; gap: 12rpx; margin-top: 10rpx; }
.attachment-actions button { flex: 1; margin: 0; min-width: 0; font-size: 24rpx; line-height: 58rpx; color: var(--ik-primary); background: var(--ik-primary-weak); border: none; border-radius: 8rpx; }
/* 加号：中性 40dp 图标按钮，和语音按钮同一套线性语言 */
.plus-btn {
  flex: 0 0 80rpx;
  width: 80rpx;
  height: 80rpx;
  margin: 0 12rpx 0 0;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 50%;
  background: var(--ik-soft);
  color: var(--ik-t2);
  line-height: 1;
}
.plus-btn::after {
  border: none;
}
.plus-btn[disabled] {
  opacity: 0.45;
}
.plus-icon {
  width: 40rpx;
  height: 40rpx;
  display: block;
}

/* ==================== 附件选择弹层 ==================== */
.attach-sheet {
  padding: 16rpx 32rpx 32rpx;
  background: var(--ik-card);
  box-sizing: border-box;
}
.attach-sheet__handle {
  width: 72rpx;
  height: 8rpx;
  border-radius: 4rpx;
  background: var(--ik-line);
  margin: 0 auto 24rpx;
}
.attach-sheet__head {
  padding: 0 4rpx;
}
.attach-sheet__title {
  display: block;
  font-size: 32rpx;
  font-weight: 700;
  color: var(--ik-t1);
}
.attach-sheet__sub {
  display: block;
  margin-top: 8rpx;
  font-size: 22rpx;
  color: var(--ik-t3);
}
.attach-grid {
  display: flex;
  gap: 20rpx;
  margin-top: 28rpx;
}
.attach-item {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8rpx 0;
  border-radius: var(--ik-radius);
}
.attach-item__icon {
  width: 112rpx;
  height: 112rpx;
  border-radius: 28rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--ik-primary-weak);
  color: var(--ik-primary);
  transition: transform 0.15s ease;
}
.attach-item:active .attach-item__icon {
  transform: scale(0.94);
}
.attach-item__icon .attach-icon {
  font-size: 48rpx;
  color: var(--ik-primary);
}
.attach-item__label {
  margin-top: 12rpx;
  font-size: 26rpx;
  color: var(--ik-t1);
}
.attach-cancel {
  margin-top: 28rpx;
  height: 88rpx;
  line-height: 88rpx;
  text-align: center;
  font-size: 28rpx;
  color: var(--ik-t2);
  background: var(--ik-soft);
  border-radius: var(--ik-radius);
}
.attach-cancel:active {
  opacity: 0.7;
}
.confidence, .candidate-list { font-size: 22rpx; color: var(--ik-t2); }
.candidate-list { padding: 8rpx 0; }
.candidate-label, .candidate-item { display: block; }
.candidate-label { color: var(--ik-t2); font-weight: 600; }
.candidate-item { color: var(--ik-t2); margin-top: 4rpx; }
.candidate-button { display: block; width: 100%; margin: 6rpx 0 0; padding: 0 12rpx; text-align: left; background: var(--ik-soft); border: 1rpx solid var(--ik-line); border-radius: 8rpx; line-height: 52rpx; font-size: 23rpx; }
.solution-list { display: flex; flex-direction: column; gap: 14rpx; }
.solution-step { padding: 16rpx; background: var(--ik-soft); border-left: 6rpx solid var(--ik-primary); border-radius: 6rpx; }
.solution-step-head { display: flex; align-items: center; gap: 12rpx; margin-bottom: 8rpx; }
.solution-step-no { width: 36rpx; height: 36rpx; flex: 0 0 36rpx; border-radius: 50%; text-align: center; line-height: 36rpx; background: var(--ik-primary); color: var(--ik-on-primary); font-size: 22rpx; font-weight: 700; }
.solution-step-title { font-size: 27rpx; line-height: 1.45; font-weight: 700; color: var(--ik-t1); }
.solution-step-content { display: block; font-size: 28rpx; line-height: 1.85; color: var(--ik-t1); white-space: pre-wrap; word-break: break-word; }
.question-preview { display: block; width: 100%; margin: 8rpx 0; padding: 0 16rpx; color: var(--ik-primary); background: var(--ik-primary-weak); border: 1rpx solid var(--ik-line); border-radius: 8rpx; font-size: 24rpx; line-height: 58rpx; text-align: center; }
.question-image { max-width: 100%; max-height: 560rpx; object-fit: contain; cursor: zoom-in; }
.question-error { display: block; margin-top: 8rpx; color: var(--ik-danger); font-size: 23rpx; line-height: 1.45; }
.question-retry { margin: 8rpx 0 0; padding: 0 12rpx; color: var(--ik-warn-strong); background: var(--ik-warn-weak); border: 1rpx solid var(--ik-warn-line); border-radius: 6rpx; font-size: 22rpx; line-height: 48rpx; }

.composer {
  background: var(--ik-bg);
}

.input-bar {
  display: flex;
  align-items: center;
  padding: 12rpx 24rpx;
  background: var(--ik-bg);
}
.input {
  flex: 1;
  min-width: 0;
  height: 80rpx;
  max-height: 240rpx;
  margin-right: 12rpx;
  background: var(--ik-input-bg);
  border-radius: 20rpx;
  padding: 20rpx 28rpx;
  font-size: 28rpx;
  box-sizing: border-box;
  line-height: 1.5;
  box-shadow: 0 2rpx 12rpx rgba(0, 0, 0, 0.08);
}
.voice-btn {
  flex: 0 0 80rpx;
  width: 80rpx;
  height: 80rpx;
  margin: 0 12rpx 0 0;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  background: var(--ik-primary-weak);
  color: var(--ik-primary);
  border: none;
  border-radius: 50%;
  line-height: 1;
  -webkit-touch-callout: none;
  user-select: none;
  touch-action: none;
}
.voice-btn::after {
  border: none;
}
.voice-btn.recording {
  background: var(--ik-danger);
  color: #fff;
}
.voice-btn.uploading {
  background: var(--ik-soft);
  color: var(--ik-t3);
}
.voice-btn.starting {
  opacity: 0.6;
}
.voice-btn.will-cancel {
  background: var(--ik-danger);
  color: #fff;
  transform: scale(0.94);
}

/* 按住说话浮层：pointer-events 关闭，触摸事件仍然落在按钮上 */
.voice-overlay {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  left: 0;
  z-index: 900;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(15, 23, 42, 0.35);
  pointer-events: none;
}
.voice-overlay-card {
  width: 440rpx;
  padding: 36rpx 32rpx 40rpx;
  border-radius: 32rpx;
  background: rgba(17, 24, 39, 0.92);
  color: #fff;
  display: flex;
  flex-direction: column;
  align-items: center;
  box-shadow: 0 18rpx 60rpx rgba(0, 0, 0, 0.28);
}
.voice-overlay-card.is-cancel {
  background: rgba(127, 29, 29, 0.94);
}
.voice-overlay-title {
  font-size: 34rpx;
  font-weight: 700;
}
.voice-overlay-hint {
  margin-top: 12rpx;
  font-size: 24rpx;
  color: rgba(255, 255, 255, 0.75);
}
.voice-overlay-time {
  margin-top: 18rpx;
  font-size: 28rpx;
  font-variant-numeric: tabular-nums;
}
.voice-wave {
  height: 60rpx;
  margin-top: 18rpx;
  display: flex;
  align-items: center;
  gap: 10rpx;
}
.voice-wave-bar {
  width: 8rpx;
  height: 20rpx;
  border-radius: 8rpx;
  background: #fff;
  animation: voice-wave 0.8s ease-in-out infinite alternate;
}
.voice-wave.is-cancel .voice-wave-bar {
  background: #fecaca;
}
@keyframes voice-wave {
  from { height: 14rpx; opacity: 0.5; }
  to { height: 54rpx; opacity: 1; }
}

/* 语音设置 */
.voice-settings {
  padding: 32rpx 32rpx 48rpx;
  background: var(--ik-card);
}
.voice-settings__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24rpx;
}
.voice-settings__title {
  font-size: 34rpx;
  font-weight: 700;
  color: var(--ik-t1);
}
.voice-settings__close {
  font-size: 26rpx;
  color: var(--ik-t3);
}
.voice-settings__row {
  display: flex;
  align-items: center;
  gap: 24rpx;
}
.voice-settings__copy {
  flex: 1;
  min-width: 0;
}
.voice-settings__label {
  display: block;
  font-size: 30rpx;
  font-weight: 600;
  color: var(--ik-t1);
}
.voice-settings__desc {
  display: block;
  margin-top: 8rpx;
  font-size: 23rpx;
  line-height: 1.5;
  color: var(--ik-t3);
}

/* 多题选择 */
.question-picker {
  max-height: 72vh;
  display: flex;
  flex-direction: column;
  padding: 32rpx 32rpx 28rpx;
  background: var(--ik-card);
}
.question-picker__head {
  margin-bottom: 20rpx;
}
.question-picker__title {
  display: block;
  font-size: 34rpx;
  font-weight: 700;
  color: var(--ik-t1);
}
.question-picker__sub {
  display: block;
  margin-top: 8rpx;
  font-size: 24rpx;
  color: var(--ik-t3);
}
.question-picker__list {
  flex: 1;
  min-height: 0;
  max-height: 50vh;
}
.question-picker__item {
  padding: 22rpx;
  margin-bottom: 16rpx;
  border: 1rpx solid var(--ik-line);
  border-radius: 16rpx;
  background: var(--ik-soft);
}
.question-picker__index {
  display: block;
  margin-bottom: 10rpx;
  font-size: 24rpx;
  font-weight: 700;
  color: var(--ik-primary);
}
.question-picker__text {
  display: block;
  max-height: 200rpx;
  overflow: hidden;
  font-size: 27rpx;
  line-height: 1.7;
  color: var(--ik-t1);
}
.question-picker__cancel {
  padding: 20rpx;
  margin-top: 16rpx;
  text-align: center;
  font-size: 28rpx;
  color: var(--ik-t3);
}

.voice-icon {
  width: 40rpx;
  height: 40rpx;
  display: block;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
.send-btn {
  flex: 0 0 140rpx;
  width: 140rpx;
  height: 80rpx;
  line-height: 80rpx;
  margin: 0;
  background: var(--ik-primary);
  color: var(--ik-on-primary);
  font-size: 28rpx;
  border-radius: 40rpx;
  border: none;
  padding: 0;
}
.send-btn[disabled] {
  background: var(--ik-soft);
  color: var(--ik-t3);
}
.send-btn::after {
  border: none;
}
/* TTS 朗读：纯文字动作，放在答案底部 */
.answer-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 8rpx;
}
.tts-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin: 0;
  padding: 0 12rpx;
  height: 80rpx;
  line-height: 80rpx;
  font-size: 24rpx;
  color: var(--ik-primary);
  background: transparent;
  border: none;
}

.tts-btn::after {
  border: none;
}

.tts-btn.tts-playing {
  color: var(--ik-t2);
}

</style>