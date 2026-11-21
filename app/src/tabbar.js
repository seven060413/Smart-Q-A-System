// 底部导航集中配置：三项（自律/我的都不是独立页面，仅作为 tab 标识）
export const TAB_INDEX = 'pages/index/index'
export const TAB_SELF = 'pages/selfdiscipline/self' // 逻辑标识，不对应真实路由
export const TAB_MY = 'pages/my/my' // 逻辑标识，不再对应真实路由

// 顺序固定为 学习 / 自律 / 我的，与 swiper 的 item 索引一一对应。
export const TAB_ITEMS = [
  { path: TAB_INDEX, title: '学习', icon: 'book' },
  { path: TAB_SELF, title: '自律', icon: 'clock-circle' },
  { path: TAB_MY, title: '我的', icon: 'user' },
]

export function tabIndexByPath(path) {
  const i = TAB_ITEMS.findIndex((item) => item.path === path)
  return i < 0 ? 0 : i
}

export function tabPathByIndex(index) {
  return (TAB_ITEMS[index] || TAB_ITEMS[0]).path
}

/** 从外部页面回到宿主页的指定 tab（替代 uni.switchTab） */
export function requestTab(index = 0) {
  uni.reLaunch({ url: `/pages/index/index?tab=${index}` })
}

/** 原生 tabBar 已删除，保留空实现以防旧页面调用 */
export function hideNativeTabBar() {}
