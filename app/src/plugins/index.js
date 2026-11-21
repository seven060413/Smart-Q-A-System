import * as demo from './com.example.demo/index.js'

export function activateBuiltinPlugins() {
  try {
    if (typeof demo.activate === 'function') demo.activate()
  } catch (e) {
    console.error('[plugin] activate failed', e)
  }
}
