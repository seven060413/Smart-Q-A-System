/**
 * 选图和裁切页之间传递数据。
 *
 * 选图页把原图信息写进 session，裁切页完成后把 result 写回；
 * 选图页在 onShow 时消费 result。
 */
export const cropSession = {
  src: '',
  file: null,
  name: '',
  size: 0,
  result: null,
}

export function resetCropSession() {
  cropSession.src = ''
  cropSession.file = null
  cropSession.name = ''
  cropSession.size = 0
  cropSession.result = null
}
