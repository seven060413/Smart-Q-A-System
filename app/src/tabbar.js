// 底部导航集中配置：当前两项，后续扩展到三、四项时只改这里。
export const TAB_INDEX = 'pages/index/index'
export const TAB_MY = 'pages/my/my'

export const TAB_ITEMS = [
  { path: TAB_INDEX, title: '学习', icon: 'book' },
  { path: TAB_MY, title: '我的', icon: 'user' },
]

/** 当前页面的路由（去掉开头的 /），用于同步高亮 */
export function getCurrentTabPath() {
  const pages = typeof getCurrentPages === 'function' ? getCurrentPages() : []
  const current = pages[pages.length - 1]
  const route = current && current.route ? String(current.route).replace(/^\//, '') : ''
  return TAB_ITEMS.some((item) => item.path === route) ? route : TAB_INDEX
}

/** 切换 tab 页面；历史、学习路径、账号等普通页面仍走 navigateTo */
export function switchTab(path) {
  if (!path) return
  uni.switchTab({ url: `/${path}` })
}

/**
 * 隐藏原生 tabBar，只保留其路由能力。
 * 原生 tabBar 需要在渲染后隐藏，页面 onLoad/onShow 中调用；失败时忽略。
 */
export function hideNativeTabBar() {
  try {
    uni.hideTabBar({ animation: false, fail: () => {} })
  } catch (e) {}
}
