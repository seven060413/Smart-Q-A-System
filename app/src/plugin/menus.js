import { reactive } from 'vue'

/** 供“我的”页渲染的插件入口 */
export const pluginMenus = reactive([])

export function registerMenu(menu) {
  if (!menu || !menu.id || !menu.label) return
  const item = {
    id: String(menu.id),
    label: String(menu.label),
    pluginId: menu.pluginId || '',
    handler: typeof menu.handler === 'function' ? menu.handler : null,
  }
  const index = pluginMenus.findIndex((m) => m.id === item.id)
  if (index >= 0) pluginMenus.splice(index, 1, item)
  else pluginMenus.push(item)
}

export function unregisterMenu(id) {
  const index = pluginMenus.findIndex((m) => m.id === id)
  if (index >= 0) pluginMenus.splice(index, 1)
}

export function runPluginMenu(menu) {
  try {
    if (menu && typeof menu.handler === 'function') menu.handler()
  } catch (e) {
    console.error('[plugin menu]', e)
    uni.showToast({ title: '插件执行失败', icon: 'none' })
  }
}

export function clearPluginMenus(pluginId) {
  for (let i = pluginMenus.length - 1; i >= 0; i -= 1) {
    if (pluginMenus[i].pluginId === pluginId) pluginMenus.splice(i, 1)
  }
}
