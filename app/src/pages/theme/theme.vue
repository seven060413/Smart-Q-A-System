<template>
  <view class="theme-root theme-page" :class="{ 'is-dark': isDark }" :style="themeVars">
    <ThemeBackground />
    <!-- 外观模式 -->
    <view class="section">
      <text class="section-title">外观模式</text>
      <view class="mode-row">
        <view
          v-for="m in modes"
          :key="m.value"
          class="mode-item"
          :class="{ active: themeState.mode === m.value }"
          @click="setMode(m.value)"
        >
          {{ m.label }}
        </view>
      </view>
    </view>

    <!-- 自定义主色 -->
    <view class="section">
      <text class="section-title">自定义</text>
      <text class="section-sub">选一个主色，背景与文字保持默认</text>

      <view class="accent-row">
        <view
          v-for="a in accents"
          :key="a.key"
          class="accent-item"
          :class="{ active: isAccentActive(a) }"
          @click="useAccent(a)"
        >
          <view class="accent-ring">
            <view class="accent-dot" :style="{ background: isDark ? a.dark.primary : a.light.primary }" />
          </view>
          <text class="accent-name">{{ a.name }}</text>
        </view>
      </view>

      <view class="radius-row">
        <text class="radius-label">圆角</text>
        <view
          v-for="r in radii"
          :key="r.value"
          class="radius-item"
          :class="{ active: currentRadius === r.value }"
          @click="useRadius(r.value)"
        >
          {{ r.label }}
        </view>
      </view>
    </view>

    <!-- 主题 -->
    <view class="section">
      <text class="section-title">主题</text>

      <view class="theme-grid">
        <!-- 默认 -->
        <view
          class="theme-card"
          :class="{ active: themeState.pluginId === '' }"
          @click="restore"
        >
          <view class="preview" :style="{ background: defaultPreview.bg }">
            <view class="preview-card" :style="{ background: defaultPreview.card }">
              <view class="preview-line" :style="{ background: defaultPreview.t1 }" />
              <view class="preview-line short" :style="{ background: defaultPreview.t3 }" />
              <view class="preview-pill" :style="{ background: defaultPreview.primary }" />
            </view>
          </view>
          <view class="theme-card-meta">
            <text class="theme-card-name">默认</text>
            <text class="theme-card-check">{{ themeState.pluginId === '' ? '✓' : '' }}</text>
          </view>
          <text class="theme-card-desc">清爽蓝白</text>
        </view>

        <!-- 预设主题 -->
        <view
          v-for="item in themeCards"
          :key="item.id"
          class="theme-card"
          :class="{ active: themeState.pluginId === item.id }"
          @click="useTheme(item)"
        >
          <view class="preview" :style="{ background: item.preview.bg }">
            <view class="preview-card" :style="{ background: item.preview.card }">
              <view class="preview-line" :style="{ background: item.preview.t1 }" />
              <view class="preview-line short" :style="{ background: item.preview.t3 }" />
              <view class="preview-pill" :style="{ background: item.preview.primary }" />
            </view>
          </view>
          <view class="theme-card-meta">
            <text class="theme-card-name">{{ item.name }}</text>
            <text class="theme-card-check">{{ themeState.pluginId === item.id ? '✓' : '' }}</text>
          </view>
          <text class="theme-card-desc">{{ item.description || '' }}</text>
          <view v-if="item.installed" class="theme-card-actions">
            <text class="theme-card-badge">已安装</text>
            <text class="theme-card-uninstall" @click.stop="removeTheme(item)">卸载</text>
          </view>
        </view>
      </view>

      <view class="restore" @click="restore">恢复默认主题</view>
    </view>

    <!-- 导入运行时主题 -->
    <view class="section">
      <text class="section-title">导入主题</text>
      <text class="section-sub">
        支持 BiliLite 的 plugin.json 或 IKGR 的 theme.json；压缩包内可带 assets 背景图
      </text>

      <!-- #ifdef H5 -->
      <view class="import-btn" @click="pickZip">导入主题 zip</view>
      <!-- #endif -->

      <view class="url-row">
        <input
          v-model="installUrl"
          class="url-input"
          placeholder="或粘贴 zip 下载链接（https://…）"
        />
        <view class="url-btn" @click="installByUrl">安装</view>
      </view>

      <text class="example-title">示例插件（随包内置，手机一键安装）</text>
      <view v-for="ex in examples" :key="ex.file" class="example-row">
        <view class="example-meta">
          <text class="example-name">{{ ex.name }}</text>
          <text class="example-desc">{{ ex.description }}</text>
        </view>
        <view class="url-btn" @click="installExample(ex)">安装</view>
      </view>
    </view>

    <view class="section">
      <text class="section-title">开发者</text>
      <text class="dev-note">
        在 app/src/themes/&lt;id&gt;/theme.json 新建主题后重启 dev server，即可在上方看到。
        主题 token 与设计文档第 4 节一致；圆角单位 rpx。
        背景图：backgroundImage（手机）/ backgroundImageTablet（平板），
        深色变体 backgroundImageDark / backgroundImageTabletDark；
        图片放 src/static/themes/ 下，路径写 /static/themes/xxx.jpg，全页面自动生效。
      </text>
    </view>
  </view>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { BUILTIN_THEMES } from '../../themes/index.js'
import {
  installedThemes, loadInstalledThemes, installThemeFromFile, installThemeFromUrl,
  installExamplePlugin, EXAMPLE_PLUGINS, applyInstalledTheme, uninstallTheme,
} from '../../themes/installed.js'
import { ACCENTS, RADII } from '../../theme/accents.js'
import { LIGHT, DARK } from '../../theme/tokens.js'
import {
  themeState, themeVars, isDark, setMode, applyThemeManifest, applyCustomTheme,
  clearPluginTheme, applyNativeNavigationBar,
} from '../../theme/theme.js'

onShow(() => {
  applyNativeNavigationBar()
  // 每次进入主题页都刷新一次已安装列表（可能在别处安装过）
  loadInstalledThemes()
})

// 在主题页内切换模式/主题时，让原生导航栏立即跟随
watch(themeVars, () => applyNativeNavigationBar())

const accents = ACCENTS
const radii = RADII

const modes = [
  { value: 'system', label: '跟随系统' },
  { value: 'light', label: '浅色' },
  { value: 'dark', label: '深色' },
]

const defaultPreview = computed(() => {
  const p = isDark.value ? DARK : LIGHT
  return { bg: p.bg, card: p.card, t1: p.t1, t3: p.t3, primary: p.primary }
})

function previewOf(item) {
  const t = item && item.theme ? item.theme : {}
  const useDark = isDark.value && t.darkColors && Object.keys(t.darkColors).length
  const colors = useDark ? t.darkColors : (t.colors || {})
  const fallback = defaultPreview.value
  return {
    bg: colors.bg || fallback.bg,
    card: colors.card || fallback.card,
    t1: colors.t1 || fallback.t1,
    t3: colors.t3 || fallback.t3,
    primary: colors.primary || fallback.primary,
  }
}

const themeCards = computed(() => [
  ...BUILTIN_THEMES.map((item) => ({
    ...item,
    preview: previewOf(item),
  })),
  ...installedThemes.map((item) => ({
    ...item,
    installed: true,
    preview: previewOf(item),
  })),
])

// ---- 运行时安装 ----
const installUrl = ref('')
const installing = ref(false)
const examples = EXAMPLE_PLUGINS

async function runInstall(task, okText) {
  if (installing.value) return false
  installing.value = true
  uni.showLoading({ title: '安装中…', mask: true })
  try {
    // 原生 zip/文件 API 在异常路径上可能不回调，总超时避免界面永远停在“安装中”。
    const record = await Promise.race([
      task(),
      new Promise((_, reject) => {
        setTimeout(() => reject(new Error('安装超时，请重试或检查文件权限')), 45000)
      }),
    ])
    uni.hideLoading()
    uni.showToast({ title: okText || `已应用「${record && record.name ? record.name : '主题'}」`, icon: 'none' })
    return true
  } catch (e) {
    uni.hideLoading()
    uni.showModal({
      title: '安装失败',
      content: (e && e.message) || String(e) || '未知错误',
      showCancel: false,
    })
    return false
  } finally {
    installing.value = false
  }
}

function pickZip() {
  // #ifdef H5
  if (typeof uni.chooseFile !== 'function') {
    uni.showToast({ title: '当前环境不支持文件选择', icon: 'none' })
    return
  }
  uni.chooseFile({
    count: 1,
    type: 'all',
    success: (res) => {
      const file = res && res.tempFiles && res.tempFiles[0]
      if (!file) return
      // H5 返回 File 对象（带 blob path），直接读 arrayBuffer
      if (typeof file.arrayBuffer === 'function') {
        runInstall(() => installThemeFromFile(file))
      } else if (file.path) {
        fetch(file.path)
          .then((r) => r.arrayBuffer())
          .then((buf) => runInstall(() => installThemeFromFile(new File([buf], file.name || 'theme.zip'))))
          .catch(() => uni.showToast({ title: '读取文件失败', icon: 'none' }))
      }
    },
    fail: (err) => {
      const msg = typeof err === 'string' ? err : ((err && err.errMsg) || '')
      if (!/cancel/i.test(msg)) {
        uni.showToast({ title: '选择文件失败', icon: 'none' })
      }
    },
  })
  // #endif
  // #ifndef H5
  uni.showToast({ title: 'App 端请使用链接安装', icon: 'none' })
  // #endif
}

async function installByUrl() {
  const url = installUrl.value.trim()
  if (!url) {
    uni.showToast({ title: '请先粘贴 zip 链接', icon: 'none' })
    return
  }
  const ok = await runInstall(() => installThemeFromUrl(url))
  if (ok) installUrl.value = ''
}

function installExample(example) {
  runInstall(() => installExamplePlugin(example))
}

function removeTheme(item) {
  uni.showModal({
    title: '卸载主题',
    content: `确定卸载「${item.name}」？`,
    success: async (res) => {
      if (!res.confirm) return
      try {
        await uninstallTheme(item.id)
        uni.showToast({ title: '已卸载', icon: 'none' })
      } catch (e) {
        uni.showModal({
          title: '卸载失败',
          content: (e && e.message) || String(e),
          showCancel: false,
        })
      }
    },
  })
}

const currentAccent = computed(() => {
  if (themeState.pluginId !== 'custom') return null
  const primary = String(themeState.light.primary || '').toLowerCase()
  return ACCENTS.find((a) => a.light.primary.toLowerCase() === primary) || null
})

const currentRadius = computed(() =>
  themeState.pluginId === 'custom' ? (themeState.lightRadius ?? 24) : 24
)

function isAccentActive(a) {
  return !!currentAccent.value && currentAccent.value.key === a.key
}

function useAccent(a) {
  applyCustomTheme(a, currentRadius.value)
}

function useRadius(value) {
  applyCustomTheme(currentAccent.value || ACCENTS[0], value)
}

function useTheme(item) {
  if (item.installed) {
    applyInstalledTheme(item)
    uni.showToast({ title: `已应用「${item.name}」`, icon: 'none' })
    return
  }
  const ok = applyThemeManifest(item)
  uni.showToast({ title: ok ? `已应用「${item.name}」` : '主题数据无效', icon: 'none' })
}

function restore() {
  clearPluginTheme()
  uni.showToast({ title: '已恢复默认主题', icon: 'none' })
}
</script>

<style>
.theme-page {
  min-height: 100vh;
  padding: 32rpx;
  box-sizing: border-box;
  background: var(--ik-bg);
}
.section {
  background: var(--ik-card);
  border-radius: var(--ik-radius);
  padding: 28rpx;
  margin-bottom: 24rpx;
  box-sizing: border-box;
}
.section-title {
  display: block;
  font-size: 28rpx;
  font-weight: 700;
  color: var(--ik-t1);
  margin-bottom: 20rpx;
}
.section-sub {
  display: block;
  margin: -12rpx 0 4rpx;
  font-size: 22rpx;
  color: var(--ik-t3);
}
.mode-row { display: flex; }
.mode-item {
  flex: 1;
  height: 72rpx;
  line-height: 72rpx;
  text-align: center;
  font-size: 26rpx;
  color: var(--ik-t2);
  border: 1rpx solid var(--ik-line);
  border-radius: var(--ik-radius);
  margin-right: 16rpx;
}
.mode-item:last-child { margin-right: 0; }
.mode-item.active {
  color: var(--ik-primary);
  border-color: var(--ik-primary);
  background: var(--ik-primary-weak);
}

/* 自定义主色 */
.accent-row {
  display: flex;
  margin-top: 20rpx;
}
.accent-item {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
}
.accent-ring {
  width: 56rpx;
  height: 56rpx;
  border-radius: 50%;
  border: 3rpx solid transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
}
.accent-item.active .accent-ring {
  border-color: var(--ik-primary);
}
.accent-dot {
  width: 38rpx;
  height: 38rpx;
  border-radius: 50%;
}
.accent-name {
  margin-top: 8rpx;
  font-size: 20rpx;
  color: var(--ik-t3);
  white-space: nowrap;
}
.accent-item.active .accent-name {
  color: var(--ik-primary);
}

.radius-row {
  display: flex;
  align-items: center;
  margin-top: 24rpx;
}
.radius-label {
  font-size: 24rpx;
  color: var(--ik-t3);
  margin-right: 16rpx;
}
.radius-item {
  flex: 1;
  height: 64rpx;
  line-height: 64rpx;
  text-align: center;
  font-size: 24rpx;
  color: var(--ik-t2);
  border: 1rpx solid var(--ik-line);
  border-radius: 12rpx;
  margin-right: 10rpx;
}
.radius-item:last-child { margin-right: 0; }
.radius-item.active {
  color: var(--ik-primary);
  border-color: var(--ik-primary);
  background: var(--ik-primary-weak);
}

/* 主题卡片 */
.theme-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 16rpx;
}
.theme-card {
  width: calc(50% - 8rpx);
  box-sizing: border-box;
  padding: 12rpx;
  border: 2rpx solid transparent;
  border-radius: var(--ik-radius);
  background: var(--ik-soft);
}
.theme-card.active {
  border-color: var(--ik-primary);
  background: var(--ik-primary-weak);
}
.preview {
  height: 132rpx;
  border-radius: 14rpx;
  padding: 14rpx;
  box-sizing: border-box;
  display: flex;
  align-items: center;
}
.preview-card {
  width: 100%;
  border-radius: 10rpx;
  padding: 14rpx;
  box-sizing: border-box;
}
.preview-line {
  width: 72%;
  height: 10rpx;
  border-radius: 5rpx;
  margin-bottom: 8rpx;
  opacity: 0.85;
}
.preview-line.short {
  width: 46%;
  opacity: 0.55;
}
.preview-pill {
  width: 56rpx;
  height: 18rpx;
  border-radius: 9rpx;
  margin-top: 12rpx;
}
.theme-card-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 12rpx;
}
.theme-card-name {
  font-size: 26rpx;
  font-weight: 600;
  color: var(--ik-t1);
}
.theme-card-check {
  font-size: 26rpx;
  color: var(--ik-primary);
}
.theme-card-desc {
  display: block;
  margin-top: 4rpx;
  font-size: 20rpx;
  color: var(--ik-t3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.theme-card-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 8rpx;
}
.theme-card-badge {
  font-size: 20rpx;
  color: var(--ik-primary);
}
.theme-card-uninstall {
  font-size: 22rpx;
  color: var(--ik-danger);
  padding: 4rpx 8rpx;
}

/* 导入主题 */
.import-btn {
  margin-top: 20rpx;
  height: 76rpx;
  line-height: 76rpx;
  text-align: center;
  font-size: 26rpx;
  color: var(--ik-on-primary);
  background: var(--ik-primary);
  border-radius: var(--ik-radius);
}
.url-row {
  display: flex;
  align-items: center;
  margin-top: 16rpx;
}
.url-input {
  flex: 1;
  min-width: 0;
  height: 72rpx;
  padding: 0 20rpx;
  box-sizing: border-box;
  font-size: 24rpx;
  color: var(--ik-t1);
  background: var(--ik-input-bg);
  border: 1rpx solid var(--ik-line);
  border-radius: var(--ik-radius);
  margin-right: 12rpx;
}
.url-btn {
  flex: 0 0 auto;
  height: 72rpx;
  line-height: 72rpx;
  padding: 0 28rpx;
  font-size: 24rpx;
  color: var(--ik-primary);
  border: 1rpx solid var(--ik-primary);
  border-radius: var(--ik-radius);
}
.example-title {
  display: block;
  margin-top: 28rpx;
  font-size: 22rpx;
  color: var(--ik-t3);
}
.example-row {
  display: flex;
  align-items: center;
  margin-top: 16rpx;
  padding: 16rpx 20rpx;
  box-sizing: border-box;
  background: var(--ik-soft);
  border-radius: var(--ik-radius);
}
.example-meta {
  flex: 1;
  min-width: 0;
  margin-right: 12rpx;
}
.example-name {
  display: block;
  font-size: 24rpx;
  color: var(--ik-t1);
}
.example-desc {
  display: block;
  margin-top: 4rpx;
  font-size: 20rpx;
  color: var(--ik-t3);
}

.restore {
  margin-top: 24rpx;
  height: 76rpx;
  line-height: 76rpx;
  text-align: center;
  font-size: 26rpx;
  color: var(--ik-t2);
  border: 1rpx solid var(--ik-line);
  border-radius: var(--ik-radius);
}
.dev-note {
  font-size: 24rpx;
  line-height: 1.7;
  color: var(--ik-t3);
}
</style>
