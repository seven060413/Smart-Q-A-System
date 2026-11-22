// App 私有目录（_doc）临时文件管理：裁图结果、PDF 预览副本。
// _doc 不会被系统“清除缓存”清掉，必须在 App 启动时主动清理。

import { removeLocalFile } from './file-utils.js'

const CROP_PREFIX = 'ikgr_crop_'
const PDF_PREFIX = 'ikgr_pdf_'
// 兼容旧版本遗留的命名：crop-<时间戳>.jpg / <13位时间戳>-xxx.pdf
const LEGACY_PATTERNS = [/^crop-\d+\.jpg$/i, /^\d{13}-.*\.pdf$/i]

export function cropTempName() {
  return `${CROP_PREFIX}${Date.now()}.jpg`
}

export function pdfTempName(name) {
  const safe = String(name || 'document.pdf')
    .replace(/[\\/:*?"<>|\s]+/g, '_')
    .slice(-80)
  return `${PDF_PREFIX}${Date.now()}_${safe}`
}

/** 上传/识别完成后删除单个临时文件；H5 为空实现。 */
export function removeTempFile(filePath) {
  // #ifdef APP-PLUS
  if (!filePath) return
  removeLocalFile(filePath)
  // #endif
}

/** App 启动时清理裁图/PDF 临时文件，避免 _doc 越积越大。 */
export function cleanupAppTempFiles() {
  // #ifdef APP-PLUS
  try {
    plus.io.requestFileSystem(plus.io.PRIVATE_DOC, (fs) => {
      fs.root.createReader().readEntries(
        (entries) => {
          ;(entries || []).forEach((entry) => {
            if (!entry || entry.isDirectory) return
            const name = String(entry.name || '')
            const isTemp =
              name.startsWith(CROP_PREFIX) || name.startsWith(PDF_PREFIX)
            const isLegacy = LEGACY_PATTERNS.some((pattern) => pattern.test(name))
            if (isTemp || isLegacy) entry.remove(() => {}, () => {})
          })
        },
        () => {}
      )
    }, () => {})
  } catch (e) {}
  // #endif
}
