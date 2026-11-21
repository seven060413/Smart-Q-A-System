import { TOKENS } from '../theme/tokens.js'

// Vite 在构建期扫描 JSON，新增主题目录后重启 dev server 即可
const modules = import.meta.glob('./*/theme.json', { eager: true })

function normalizeTheme(mod, path) {
  const manifest = mod.default || mod
  const theme = manifest.theme || {}
  const colors = { ...(theme.colors || {}) }
  const darkColors = { ...(theme.darkColors || theme.dark || {}) }

  // 兼容 BiliLite 平铺写法：theme 顶层直接写 bg/card/t1/...
  if (!Object.keys(colors).length) {
    for (const key of TOKENS) {
      if (typeof theme[key] === 'string') colors[key] = theme[key]
    }
  }

  return {
    ...manifest,
    __path: path,
    theme: { ...theme, colors, darkColors },
  }
}

export const BUILTIN_THEMES = Object.entries(modules)
  .map(([path, mod]) => normalizeTheme(mod, path))
  .filter((m) => m && m.type === 'theme' && m.id && !m.hidden)
  .sort((a, b) => String(a.name).localeCompare(String(b.name), 'zh-Hans-CN'))

export function findTheme(id) {
  return BUILTIN_THEMES.find((m) => m.id === id) || null
}
