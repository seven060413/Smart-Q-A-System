import { createPluginApi } from '../../plugin/runtime.js'

export const manifest = {
  id: 'com.example.demo',
  name: '示例功能插件',
  version: '1.0.0',
  type: 'feature',
  permissions: ['ui'],
}

export function activate() {
  const api = createPluginApi(manifest)
  api.ui.registerMenu({
    id: 'com.example.demo.entry',
    label: '插件示例',
    handler() {
      api.ui.toast('插件入口被点击了')
    },
  })
}
