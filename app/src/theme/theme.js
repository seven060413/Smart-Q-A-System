import { reactive, computed, ref, watch } from 'vue'
import { TOKENS, TOKEN_CSS, LIGHT, DARK, DEFAULT_RADIUS } from './tokens.js'

const STORAGE_KEY = 'ikgr_theme_v1'

function readSaved() {
  try {
    const raw = uni.getStorageSync(STORAGE_KEY)
    return raw && typeof raw === 'object' ? raw : null
  } catch (e) {
    return null
  }
}

const saved = readSaved()

/**
 * 主题状态：
 * - mode: 'light' | 'dark' | 'system'
 * - pluginId: 当前启用的主题插件 id（空 = 默认）
 * - light / dark: 插件写入的 token 覆盖（优先于默认）
 * - lightRadius / darkRadius: 圆角覆盖，单位 rpx
 * - lightBg / darkBg: 背景图 URL（手机）
 * - lightBgTablet / darkBgTablet: 背景图 URL（平板，未配置时回退手机图）
 */
export const themeState = reactive({
  mode: saved?.mode || 'system',
  systemDark: false,
  pluginId: saved?.pluginId || '',
  light: saved?.light || {},
  dark: saved?.dark || {},
  lightRadius: saved?.lightRadius ?? null,
  darkRadius: saved?.darkRadius ?? null,
  lightBg: saved?.lightBg || '',
  darkBg: saved?.darkBg || '',
  lightBgTablet: saved?.lightBgTablet || '',
  darkBgTablet: saved?.darkBgTablet || '',
})

export const isDark = computed(() =>
  themeState.mode === 'dark' ||
  (themeState.mode === 'system' && themeState.systemDark)
)

export const tokens = computed(() => ({
  ...(isDark.value ? DARK : LIGHT),
  ...(isDark.value ? themeState.dark : themeState.light),
}))

export const radius = computed(() => {
  const value = isDark.value
    ? (themeState.darkRadius ?? themeState.lightRadius ?? DEFAULT_RADIUS)
    : (themeState.lightRadius ?? DEFAULT_RADIUS)
  return value
})

// 平板判定：deviceType 为 tablet，或窗口宽度 >= 600px（与 BiliLite 的阈值一致）
export const isTablet = ref(false)

function detectTablet() {
  try {
    const info = uni.getSystemInfoSync()
    const width = info.windowWidth || info.screenWidth || 0
    isTablet.value = info.deviceType === 'tablet' || width >= 600
  } catch (e) {
    isTablet.value = false
  }
}

/**
 * 当前应使用的背景图：
 * - 平板优先用平板图，没有则回退手机图
 * - 深色优先用深色图，没有则回退浅色图
 */
export const backgroundImage = computed(() => {
  const phone = isDark.value
    ? (themeState.darkBg || themeState.lightBg)
    : themeState.lightBg
  const tablet = isDark.value
    ? (themeState.darkBgTablet || themeState.lightBgTablet)
    : themeState.lightBgTablet
  return (isTablet.value && tablet) ? tablet : phone
})

export const themeVars = computed(() => {
  const vars = {}
  for (const key of TOKENS) {
    const cssName = TOKEN_CSS[key]
    const value = tokens.value[key]
    if (cssName && value) vars[cssName] = value
  }
  vars['--ik-radius'] = `${radius.value}rpx`
  return vars
})

export function saveTheme() {
  try {
    uni.setStorageSync(STORAGE_KEY, {
      mode: themeState.mode,
      pluginId: themeState.pluginId,
      light: themeState.light,
      dark: themeState.dark,
      lightRadius: themeState.lightRadius,
      darkRadius: themeState.darkRadius,
      lightBg: themeState.lightBg,
      darkBg: themeState.darkBg,
      lightBgTablet: themeState.lightBgTablet,
      darkBgTablet: themeState.darkBgTablet,
    })
  } catch (e) {}
}

/**
 * 启动时重新读一次持久化状态。
 * 模块顶层读取时 uni 运行时可能尚未就绪，这里在 onLaunch 再兜底一次。
 */
export function restoreSavedState() {
  const state = readSaved()
  if (!state) return
  Object.assign(themeState, {
    mode: ['light', 'dark', 'system'].includes(state.mode) ? state.mode : 'system',
    pluginId: state.pluginId || '',
    light: state.light && typeof state.light === 'object' ? state.light : {},
    dark: state.dark && typeof state.dark === 'object' ? state.dark : {},
    lightRadius: typeof state.lightRadius === 'number' ? state.lightRadius : null,
    darkRadius: typeof state.darkRadius === 'number' ? state.darkRadius : null,
    lightBg: state.lightBg || '',
    darkBg: state.darkBg || '',
    lightBgTablet: state.lightBgTablet || '',
    darkBgTablet: state.darkBgTablet || '',
  })
}

export function setMode(mode) {
  if (!['light', 'dark', 'system'].includes(mode)) return
  themeState.mode = mode
  saveTheme()
}

export function toggleDark() {
  setMode(isDark.value ? 'light' : 'dark')
}

function detectSystemDark() {
  try {
    const info = uni.getSystemInfoSync()
    if (info && typeof info.theme === 'string') return info.theme === 'dark'
  } catch (e) {}
  // #ifdef H5
  try {
    if (typeof window !== 'undefined' && window.matchMedia) {
      return window.matchMedia('(prefers-color-scheme: dark)').matches
    }
  } catch (e) {}
  // #endif
  return false
}

export function initSystemTheme() {
  themeState.systemDark = detectSystemDark()
  try {
    if (typeof uni.onThemeChange === 'function') {
      uni.onThemeChange((res) => {
        themeState.systemDark = res.theme === 'dark'
      })
    }
  } catch (e) {}

  // #ifdef H5
  try {
    if (typeof window !== 'undefined' && window.matchMedia) {
      const media = window.matchMedia('(prefers-color-scheme: dark)')
      const handler = (event) => {
        themeState.systemDark = !!event.matches
      }
      if (typeof media.addEventListener === 'function') {
        media.addEventListener('change', handler)
      } else if (typeof media.addListener === 'function') {
        media.addListener(handler)
      }
    }
  } catch (e) {}
  // #endif
}

// ---------- 插件主题 ----------

function pickTokens(source) {
  const out = {}
  if (!source || typeof source !== 'object') return out
  for (const key of TOKENS) {
    const value = source[key]
    if (typeof value === 'string' && /^#([0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/.test(value.trim())) {
      out[key] = value.trim()
    }
  }
  return out
}

/**
 * 应用主题插件 manifest。
 * 兼容两种写法：
 * 1) 推荐：theme.colors / theme.darkColors
 * 2) 兼容 BiliLite：theme 顶层直接写 token（如 theme.bg）
 */
export function applyThemeManifest(manifest) {
  if (!manifest || manifest.type !== 'theme') return false
  const theme = manifest.theme || {}

  const lightSource = theme.colors || theme
  const darkSource = theme.darkColors || theme.dark || {}
  const light = pickTokens(lightSource)
  const dark = pickTokens(darkSource)

  if (!Object.keys(light).length && !Object.keys(dark).length) return false

  const radiusValue =
    typeof theme.radius === 'number' && theme.radius >= 0 ? theme.radius : null
  const darkRadiusValue =
    typeof theme.darkRadius === 'number' && theme.darkRadius >= 0
      ? theme.darkRadius
      : radiusValue

  Object.assign(themeState, {
    pluginId: manifest.id || '',
    light,
    dark,
    lightRadius: radiusValue,
    darkRadius: darkRadiusValue,
    lightBg: typeof theme.backgroundImage === 'string' ? theme.backgroundImage : '',
    darkBg: typeof theme.backgroundImageDark === 'string'
      ? theme.backgroundImageDark
      : (typeof theme.backgroundImage === 'string' ? theme.backgroundImage : ''),
    lightBgTablet: typeof theme.backgroundImageTablet === 'string'
      ? theme.backgroundImageTablet
      : '',
    darkBgTablet: typeof theme.backgroundImageTabletDark === 'string'
      ? theme.backgroundImageTabletDark
      : (typeof theme.backgroundImageTablet === 'string' ? theme.backgroundImageTablet : ''),
  })
  saveTheme()
  return true
}

/**
 * 自定义主色 + 圆角：只覆盖 primary / primaryWeak / onPrimary，
 * 背景、卡片、正文继续沿用默认浅色/深色 token。
 */
export function applyCustomTheme(accent, radiusValue) {
  if (!accent || !accent.light || !accent.dark) return false
  const r = typeof radiusValue === 'number' && radiusValue >= 0
    ? radiusValue
    : DEFAULT_RADIUS
  Object.assign(themeState, {
    pluginId: 'custom',
    light: { ...accent.light },
    dark: { ...accent.dark },
    lightRadius: r,
    darkRadius: r,
    lightBg: '',
    darkBg: '',
    lightBgTablet: '',
    darkBgTablet: '',
  })
  saveTheme()
  return true
}

/** 恢复默认主题（保留用户选择的深浅模式） */
export function clearPluginTheme() {
  Object.assign(themeState, {
    pluginId: '',
    light: {},
    dark: {},
    lightRadius: null,
    darkRadius: null,
    lightBg: '',
    darkBg: '',
    lightBgTablet: '',
    darkBgTablet: '',
  })
  saveTheme()
}

/** 原生导航栏跟随主题主色（auth/history/path 等非自定义导航页用） */
export function applyNativeNavigationBar() {
  try {
    uni.setNavigationBarColor({
      // 深色模式下 primary 是浅蓝，用黑字；浅色模式下 primary 是深蓝，用白字
      frontColor: isDark.value ? '#000000' : '#ffffff',
      backgroundColor: tokens.value.primary,
    })
  } catch (e) {}
}

/**
 * 初始化：H5 把变量挂到 documentElement，保证 wot-ui 的
 * toast/dialog 等挂到 body 的组件也能取到变量。
 * App/小程序端由每个页面根节点 :style="themeVars" 提供。
 */
export function initThemeBridge() {
  restoreSavedState()
  initSystemTheme()
  // 设备形态（手机/平板）与窗口尺寸变化
  detectTablet()
  try {
    if (typeof uni.onWindowResize === 'function') {
      uni.onWindowResize(() => detectTablet())
    }
  } catch (e) {}
  // #ifdef H5
  watch(themeVars, (vars) => {
    try {
      const root = document.documentElement
      Object.entries(vars).forEach(([key, value]) => {
        if (value) root.style.setProperty(key, value)
      })
      // wot-ui 弹层挂到 body，单独映射一次常用变量
      const wotMap = {
        '--wot-toast-bg': tokens.value.card,
        '--wot-toast-color': tokens.value.t1,
        '--wot-dialog-bg': tokens.value.card,
        '--wot-dialog-title-color': tokens.value.t1,
        '--wot-dialog-content-color': tokens.value.t2,
        '--wot-dialog-content-input-bg': tokens.value.inputBg,
        '--wot-dialog-primary-color': tokens.value.primary,
        '--wot-dialog-success-color': tokens.value.success,
        '--wot-dialog-error-color': tokens.value.danger,
        '--wot-popup-bg': tokens.value.card,
        '--wot-action-sheet-bg': tokens.value.card,
        '--wot-action-sheet-action-color': tokens.value.t1,
        '--wot-action-sheet-cancel-bg': tokens.value.card,
        '--wot-action-sheet-cancel-color': tokens.value.t2,
        '--wot-tabbar-bg': tokens.value.card,
      }
      Object.entries(wotMap).forEach(([key, value]) => {
        if (value) root.style.setProperty(key, value)
      })
      root.setAttribute('data-theme', isDark.value ? 'dark' : 'light')
    } catch (e) {}
  }, { immediate: true })
  // #endif
}
