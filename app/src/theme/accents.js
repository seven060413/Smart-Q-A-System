/**
 * 自定义主色：只覆盖 primary / primaryWeak / onPrimary，
 * 背景、卡片、正文继续使用默认浅色/深色 token，保证对比度可控。
 * 浅色/深色两套值都预先配好，不在运行时算色。
 */
export const ACCENTS = [
  {
    key: 'sea',
    name: '海盐蓝',
    light: { primary: '#2F6FA8', primaryWeak: '#E3EFFA', onPrimary: '#FFFFFF' },
    dark: { primary: '#6FB1E8', primaryWeak: '#1B2E40', onPrimary: '#08131F' },
  },
  {
    key: 'teal',
    name: '青屿',
    light: { primary: '#178A7A', primaryWeak: '#E2F4F0', onPrimary: '#FFFFFF' },
    dark: { primary: '#4FC3B0', primaryWeak: '#1B3330', onPrimary: '#06120F' },
  },
  {
    key: 'indigo',
    name: '靛蓝',
    light: { primary: '#4C6EF5', primaryWeak: '#E9EDFF', onPrimary: '#FFFFFF' },
    dark: { primary: '#8BA4FF', primaryWeak: '#1E2440', onPrimary: '#0B1020' },
  },
  {
    key: 'violet',
    name: '紫罗兰',
    light: { primary: '#7C6BC9', primaryWeak: '#F0ECFB', onPrimary: '#FFFFFF' },
    dark: { primary: '#AE9BF0', primaryWeak: '#241F33', onPrimary: '#120E20' },
  },
  {
    key: 'rose',
    name: '玫红',
    light: { primary: '#C94F7C', primaryWeak: '#FBE9F0', onPrimary: '#FFFFFF' },
    dark: { primary: '#F08CB0', primaryWeak: '#33202A', onPrimary: '#1F0B14' },
  },
  {
    key: 'graphite',
    name: '石墨',
    light: { primary: '#4B5563', primaryWeak: '#EAEDF1', onPrimary: '#FFFFFF' },
    dark: { primary: '#C3C9D2', primaryWeak: '#262B31', onPrimary: '#0E1012' },
  },
]

export const RADII = [
  { label: '小', value: 12 },
  { label: '中', value: 24 },
  { label: '大', value: 32 },
]

export function findAccent(key) {
  return ACCENTS.find((item) => item.key === key) || null
}
