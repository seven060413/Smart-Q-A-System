// B 站官方嵌入播放器与观看页 URL 工具。
// 只使用 bvid/page 生成 URL，不接收或拼接触任意 URL。

const BVID_RE = /^BV[0-9A-Za-z]{10}$/

export function isBvid(value) {
  return BVID_RE.test(String(value || '').trim())
}

export function buildBilibiliEmbedUrl(bvid, page = 1, aid = null, cid = null) {
  const value = String(bvid || '').trim()
  if (!BVID_RE.test(value)) return ''
  const p = Math.max(1, Number(page) || 1)
  const parts = ['isOutside=true']
  if (aid) parts.push(`aid=${encodeURIComponent(aid)}`)
  parts.push(`bvid=${value}`)
  if (cid) parts.push(`cid=${encodeURIComponent(cid)}`)
  parts.push(`p=${p}`, 'autoplay=0', 'danmaku=0')
  return `https://player.bilibili.com/player.html?${parts.join('&')}`
}

// 备用播放器：官方移动版 H5 页面。仅在官方嵌入播放器报错时由用户手动切换。
export function buildBilibiliMobileUrl(bvid, page = 1) {
  const value = String(bvid || '').trim()
  if (!BVID_RE.test(value)) return ''
  const p = Math.max(1, Number(page) || 1)
  return (
    'https://www.bilibili.com/blackboard/html5mobileplayer.html' +
    `?bvid=${value}&page=${p}&danmaku=0&high_quality=1`
  )
}

export function buildBilibiliWatchUrl(bvid, page = 1) {
  const value = String(bvid || '').trim()
  if (!BVID_RE.test(value)) return ''
  const p = Math.max(1, Number(page) || 1)
  return `https://www.bilibili.com/video/${value}${p > 1 ? `?p=${p}` : ''}`
}

export function formatDuration(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0))
  if (!total) return ''
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const mm = h ? String(m).padStart(2, '0') : String(m)
  const ss = String(s).padStart(2, '0')
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`
}
