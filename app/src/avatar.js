// 头像压缩与读取：统一输出 data:image/...;base64,...。
// 目标是把头像控制在 300KB 以内，避免「user_avatar + 缓存 user JSON」双份大字符串。

const MAX_AVATAR_CHARS = 400_000
const MAX_EDGE = 320
const QUALITY = 0.82

function assertAvatar(dataUrl) {
  const value = String(dataUrl || '')
  if (!value.startsWith('data:image/')) throw new Error('头像读取失败')
  if (value.length > MAX_AVATAR_CHARS) {
    throw new Error('头像压缩后仍过大，请换一张更小的图片')
  }
  return value
}

function dataUrlFromBase64(base64, fallbackMime = 'image/jpeg') {
  const value = String(base64 || '')
  // PNG 的 base64 以 iVBOR 开头，JPEG 以 /9j/ 开头；按真实格式给 MIME。
  if (value.startsWith('iVBOR')) return `data:image/png;base64,${value}`
  if (value.startsWith('/9j/')) return `data:image/jpeg;base64,${value}`
  return `data:${fallbackMime};base64,${value}`
}

// #ifdef H5
async function compressH5(src, file) {
  let blob = file
  if (!blob) {
    const response = await fetch(src)
    blob = await response.blob()
  }
  const objectUrl = URL.createObjectURL(blob)
  try {
    const image = await new Promise((resolve, reject) => {
      const img = new Image()
      img.onload = () => resolve(img)
      img.onerror = () => reject(new Error('图片读取失败'))
      img.src = objectUrl
    })
    const scale = Math.min(1, MAX_EDGE / Math.max(image.width, image.height))
    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.round(image.width * scale))
    canvas.height = Math.max(1, Math.round(image.height * scale))
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('当前浏览器不支持头像压缩')
    // PNG 透明区域转 JPEG 会变黑，先铺白底。
    ctx.fillStyle = '#ffffff'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(image, 0, 0, canvas.width, canvas.height)
    return canvas.toDataURL('image/jpeg', QUALITY)
  } finally {
    URL.revokeObjectURL(objectUrl)
  }
}
// #endif

// #ifdef APP-PLUS
function readAppFile(filePath) {
  return new Promise((resolve, reject) => {
    uni.getFileSystemManager().readFile({
      filePath,
      encoding: 'base64',
      success: (res) => resolve(dataUrlFromBase64(res.data)),
      fail: () => reject(new Error('头像读取失败')),
    })
  })
}

function compressAppFile(src) {
  if (typeof uni.compressImage !== 'function') return readAppFile(src)
  return new Promise((resolve, reject) => {
    uni.compressImage({
      src,
      quality: 70,
      width: MAX_EDGE,
      height: MAX_EDGE,
      success: (res) => {
        const path =
          res.tempFilePath ||
          (res.tempFilePaths && res.tempFilePaths[0]) ||
          src
        readAppFile(path).then(resolve).catch(reject)
      },
      // 压缩失败时退回原图，再由 assertAvatar 做大小兜底。
      fail: () => readAppFile(src).then(resolve).catch(reject),
    })
  })
}
// #endif

// #ifndef H5
// #ifndef APP-PLUS
function readOther(src) {
  return new Promise((resolve, reject) => {
    if (!uni.getFileSystemManager) {
      reject(new Error('当前平台不支持头像上传'))
      return
    }
    uni.getFileSystemManager().readFile({
      filePath: src,
      encoding: 'base64',
      success: (res) => resolve(dataUrlFromBase64(res.data)),
      fail: () => reject(new Error('头像读取失败')),
    })
  })
}
// #endif
// #endif

export async function prepareAvatar(src, file) {
  let dataUrl = ''
  // #ifdef H5
  dataUrl = await compressH5(src, file)
  // #endif
  // #ifdef APP-PLUS
  dataUrl = await compressAppFile(src)
  // #endif
  // #ifndef H5
  // #ifndef APP-PLUS
  dataUrl = await readOther(src)
  // #endif
  // #endif
  return assertAvatar(dataUrl)
}
