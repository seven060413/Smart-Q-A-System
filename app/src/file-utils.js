// 跨平台本地文件读取/删除。
// 小程序专有的 uni.getFileSystemManager 在 App 端不存在，App 必须走 plus.io。

/** 读取本地文件为 data URL。 */
export function readFileAsDataUrl(filePath) {
  // #ifdef APP-PLUS
  return new Promise((resolve, reject) => {
    plus.io.resolveLocalFileSystemURL(
      filePath,
      (entry) => {
        entry.file(
          (file) => {
            const reader = new plus.io.FileReader()
            reader.onloadend = (event) => {
              resolve(String((event && event.target && event.target.result) || ''))
            }
            reader.onerror = () => reject(new Error('文件读取失败'))
            reader.readAsDataURL(file)
          },
          () => reject(new Error('文件读取失败'))
        )
      },
      () => reject(new Error('文件读取失败'))
    )
  })
  // #endif
  // #ifdef H5
  return fetch(filePath)
    .then((response) => response.blob())
    .then(
      (blob) =>
        new Promise((resolve, reject) => {
          const reader = new FileReader()
          reader.onload = () => resolve(String(reader.result || ''))
          reader.onerror = () => reject(new Error('文件读取失败'))
          reader.readAsDataURL(blob)
        })
    )
  // #endif
  // #ifndef H5
  // #ifndef APP-PLUS
  return Promise.reject(new Error('当前平台不支持文件读取'))
  // #endif
  // #endif
}

/** 删除 App 私有目录里的临时文件；其它平台忽略。 */
export function removeLocalFile(filePath) {
  // #ifdef APP-PLUS
  if (!filePath) return
  try {
    plus.io.resolveLocalFileSystemURL(
      filePath,
      (entry) => {
        entry.remove(
          () => {},
          () => {}
        )
      },
      () => {}
    )
  } catch (e) {}
  // #endif
}
