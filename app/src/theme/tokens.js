// 语义色 token：与 docs/设计界面优化.md 第 4 节一一对应
export const TOKENS = [
  'bg', 'card',
  't1', 't2', 't3', 'line',
  'primary', 'primaryWeak', 'onPrimary',
  'block', 'onBlock', 'soft', 'inputBg',
  'danger', 'success',
]

// token 名 -> CSS 变量名。CSS 变量名区分大小写，
// 所以 primaryWeak 必须映射成 --ik-primary-weak，不能直接拼接。
export const TOKEN_CSS = {
  bg: '--ik-bg',
  card: '--ik-card',
  t1: '--ik-t1',
  t2: '--ik-t2',
  t3: '--ik-t3',
  line: '--ik-line',
  primary: '--ik-primary',
  primaryWeak: '--ik-primary-weak',
  onPrimary: '--ik-on-primary',
  block: '--ik-block',
  onBlock: '--ik-on-block',
  soft: '--ik-soft',
  inputBg: '--ik-input-bg',
  danger: '--ik-danger',
  success: '--ik-success',
}

export const LIGHT = {
  bg: '#f5f6f8',
  card: '#ffffff',
  t1: '#1f2937',
  t2: '#4b5563',
  t3: '#8a8f99',
  line: '#e5e7eb',
  primary: '#2b6cb0',
  primaryWeak: '#e8f0fb',
  onPrimary: '#ffffff',
  block: '#1f2937',
  onBlock: '#ffffff',
  soft: '#f0f2f5',
  inputBg: '#ffffff',
  danger: '#e53e3e',
  success: '#2f9e68',
}

export const DARK = {
  bg: '#14161a',
  card: '#1e2126',
  t1: '#e8eaed',
  t2: '#aab1ba',
  t3: '#8b929b',
  line: '#33373d',
  primary: '#5b9bd5',
  primaryWeak: '#1f2d3d',
  onPrimary: '#0b1220',
  block: '#e8eaed',
  onBlock: '#14161a',
  soft: '#262a30',
  inputBg: '#22262c',
  danger: '#ff6b6b',
  success: '#4ade80',
}

export const DEFAULT_RADIUS = 24
