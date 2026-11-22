// App 端 PDF 选择：uni.chooseFile 在 App 不支持非媒体文件，这里走 Android
// ACTION_GET_CONTENT，拿到 content:// URI 后用 ContentResolver 复制到 _doc，
// 再交给现有的 uni.uploadFile 流程。
// 仅 APP-PLUS 生效；其它平台返回不支持。

import { pdfTempName } from './temp-files.js'

// #ifdef APP-PLUS
const REQUEST_CODE = 71023

function displayNameOf(main, uri) {
  try {
    const resolver = plus.android.invoke(main, 'getContentResolver')
    const cursor = plus.android.invoke(resolver, 'query', uri, null, null, null, null)
    if (cursor && plus.android.invoke(cursor, 'moveToFirst')) {
      const index = plus.android.invoke(cursor, 'getColumnIndex', '_display_name')
      if (index >= 0) {
        const name = plus.android.invoke(cursor, 'getString', index)
        plus.android.invoke(cursor, 'close')
        return String(name || '')
      }
      plus.android.invoke(cursor, 'close')
    }
  } catch (e) {}
  return ''
}

function copyUriToPath(main, uri, targetPath) {
  const resolver = plus.android.invoke(main, 'getContentResolver')
  // ContentResolver 的实例方法不会被自动桥接，必须用 plus.android.invoke。
  const input = plus.android.invoke(resolver, 'openInputStream', uri)
  if (!input) throw new Error('无法读取所选文件')

  const File = plus.android.importClass('java.io.File')
  const FileOutputStream = plus.android.importClass('java.io.FileOutputStream')

  const output = new FileOutputStream(new File(targetPath))
  try {
    let copied = false
    try {
      // Android 13+ 支持 InputStream.transferTo，优先用它。
      plus.android.invoke(input, 'transferTo', output)
      copied = true
    } catch (e) {
      copied = false
    }
    if (!copied) {
      // 旧系统：NIO channel + ByteBuffer 逐块搬运。
      const Channels = plus.android.importClass('java.nio.channels.Channels')
      const ByteBuffer = plus.android.importClass('java.nio.ByteBuffer')
      const inChannel = Channels.newChannel(input)
      const outChannel = plus.android.invoke(output, 'getChannel')
      const buffer = ByteBuffer.allocate(64 * 1024)
      while (true) {
        const read = plus.android.invoke(inChannel, 'read', buffer)
        if (read == null || Number(read) < 0) break
        if (Number(read) === 0) continue
        plus.android.invoke(buffer, 'flip')
        while (plus.android.invoke(buffer, 'hasRemaining')) {
          const written = Number(plus.android.invoke(outChannel, 'write', buffer))
          if (!written) throw new Error('写入 PDF 失败')
        }
        plus.android.invoke(buffer, 'clear')
      }
      plus.android.invoke(outChannel, 'close')
    }
  } finally {
    try {
      plus.android.invoke(output, 'close')
    } catch (e) {}
    try {
      plus.android.invoke(input, 'close')
    } catch (e) {}
  }
}

/** 兜底：部分 ROM 的 content:// 无法直接流复制，先解析真实路径再复制。 */
function copyNativePathToDoc(nativePath, targetName) {
  return new Promise((resolve) => {
    plus.io.resolveLocalFileSystemURL(
      nativePath,
      (entry) => {
        plus.io.requestFileSystem(
          plus.io.PRIVATE_DOC,
          (fs) => {
            entry.copyTo(
              fs.root,
              targetName,
              () => resolve(true),
              () => resolve(false)
            )
          },
          () => resolve(false)
        )
      },
      () => resolve(false)
    )
  })
}

function docAbsoluteDir() {
  let dir = String(plus.io.convertLocalFileSystemURL('_doc/') || '')
  if (dir.startsWith('file://')) dir = dir.slice(7)
  return dir.replace(/\/+$/, '')
}

function docFileSize(filePath) {
  return new Promise((resolve) => {
    plus.io.resolveLocalFileSystemURL(
      filePath,
      (entry) => {
        entry.file(
          (file) => resolve(Number(file.size) || 0),
          () => resolve(0)
        )
      },
      () => resolve(0)
    )
  })
}

function removeDocFile(filePath) {
  return new Promise((resolve) => {
    plus.io.resolveLocalFileSystemURL(
      filePath,
      (entry) => entry.remove(() => resolve(), () => resolve()),
      () => resolve()
    )
  })
}

let pendingPick = null
let resultHandlerInstalled = false
let previousResultHandler = null

function installResultHandler(main) {
  if (resultHandlerInstalled) return
  resultHandlerInstalled = true
  // 只安装一次，避免多次选择时旧 handler 叠加、重复处理同一个结果。
  previousResultHandler = main.onActivityResult
  main.onActivityResult = async (requestCode, resultCode, data) => {
    if (requestCode !== REQUEST_CODE) {
      if (typeof previousResultHandler === 'function') {
        previousResultHandler(requestCode, resultCode, data)
      }
      return
    }
    const task = pendingPick
    pendingPick = null
    if (!task) return
    if (resultCode !== -1) {
      task.reject(new Error('未选择 PDF 文件'))
      return
    }
    try {
      const uri = data.getData()
      if (!uri) throw new Error('未选择 PDF 文件')
      const name = displayNameOf(main, uri) || 'document.pdf'
      // 部分文件管理器不按 MIME 过滤；这里再按后缀兜底。
      if (/\.[a-z0-9]+$/i.test(name) && !/\.pdf$/i.test(name)) {
        throw new Error('请选择 PDF 文件')
      }
      const targetName = pdfTempName(name)
      const targetPath = `${docAbsoluteDir()}/${targetName}`
      copyUriToPath(main, uri, targetPath)
      let size = await docFileSize(`_doc/${targetName}`)
      if (size <= 0) {
        // 兜底：content:// 流复制失败时，尝试解析真实路径再复制。
        try {
          const nativePath = plus.android.resolveNativeUri(uri)
          if (nativePath) {
            // 先删掉流复制留下的 0 字节文件，否则 copyTo 可能因目标已存在失败。
            await removeDocFile(`_doc/${targetName}`)
            if (await copyNativePathToDoc(String(nativePath), targetName)) {
              size = await docFileSize(`_doc/${targetName}`)
            }
          }
        } catch (e) {}
      }
      if (size <= 0) throw new Error('PDF 文件为空')
      task.resolve({ filePath: `_doc/${targetName}`, name, size })
    } catch (e) {
      task.reject(new Error((e && e.message) || '读取 PDF 文件失败'))
    }
  }
}

export function choosePdfNative() {
  return new Promise((resolve, reject) => {
    if (pendingPick) {
      reject(new Error('正在选择 PDF，请稍候'))
      return
    }
    try {
      const Intent = plus.android.importClass('android.content.Intent')
      const main = plus.android.runtimeMainActivity()
      const intent = new Intent(Intent.ACTION_GET_CONTENT)
      intent.setType('application/pdf')
      intent.addCategory(Intent.CATEGORY_OPENABLE)

      installResultHandler(main)
      pendingPick = { resolve, reject }
      main.startActivityForResult(intent, REQUEST_CODE)
    } catch (e) {
      pendingPick = null
      reject(new Error('无法打开文件选择器'))
    }
  })
}
// #endif

// #ifndef APP-PLUS
export function choosePdfNative() {
  return Promise.reject(new Error('当前平台不支持原生 PDF 选择'))
}
// #endif
