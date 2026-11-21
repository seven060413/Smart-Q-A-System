import { applyThemeManifest, clearPluginTheme } from '../theme/theme.js'
import { registerMenu, unregisterMenu } from './menus.js'

/**
 * 创建插件 API。插件是“静态 JS 模块 + manifest”，不使用 eval。
 * 典型用法（app/src/plugins/index.js）：
 *
 *   import * as demo from './com.example.demo/index.js'
 *   const api = createPluginApi(demo.manifest)
 *   demo.activate?.(api)
 */
export function createPluginApi(manifest = {}) {
  return {
    manifest,
    ui: {
      /** 写入主题：theme 的格式与 theme.json 的 theme 字段一致 */
      setTheme(theme, options = {}) {
        return applyThemeManifest({
          id: options.id || manifest.id || '',
          name: options.name || manifest.name || '',
          type: 'theme',
          theme,
        })
      },
      resetTheme() {
        clearPluginTheme()
      },
      registerMenu(menu) {
        registerMenu({ ...menu, pluginId: manifest.id || '' })
      },
      unregisterMenu(id) {
        unregisterMenu(id)
      },
      toast(title) {
        uni.showToast({ title: String(title || ''), icon: 'none' })
      },
    },
  }
}
