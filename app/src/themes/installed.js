import { reactive } from 'vue'
import { applyThemeManifest, clearPluginTheme, themeState } from '../theme/theme.js'
import { BUILTIN_THEMES } from './index.js'

/**
 * 运行时主题插件安装器
 *
 * 支持两种清单：
 *   1) BiliLite 风格 plugin.json：theme 里平铺 bg/card/...（#AARRGGBB）
 *   2) IKGR 风格 theme.json：theme.colors / theme.darkColors（#RRGGBBAA）
 *
 * 包结构：
 *   theme.zip
 *   ├── plugin.json | theme.json
 *   └── assets/*.jpg
 *
 * 平台差异：
 *   - H5：fflate 解压 → 图片转 data URL → IndexedDB 持久化
 *   - App：plus.zip 解压到 _doc/ikgr_themes/ → 绝对路径 → uni.storage 存索引
 *
 * 安装后立即 applyThemeManifest；启动时 restoreInstalledThemes() 恢复当前主题。
 */

const STORAGE_KEY = 'ikgr_installed_themes_v1'
const DB_NAME = 'ikgr_plugin_store'
const DB_STORE = 'themes'
const APP_ROOT = '_doc/ikgr_themes'

const MAX_ZIP_BYTES = 10 * 1024 * 1024
const MAX_FILE_BYTES = 4 * 1024 * 1024
const MAX_FILES = 60

const TOKEN_KEYS = [
  'bg', 'card', 't1', 't2', 't3', 'line',
  'primary', 'primaryWeak', 'onPrimary',
  'block', 'onBlock', 'soft', 'inputBg',
  'danger', 'success',
]

const BG_KEYS = [
  'backgroundImage',
  'backgroundImageDark',
  'backgroundImageTablet',
  'backgroundImageTabletDark',
]

const IMAGE_EXT = ['jpg', 'jpeg', 'png', 'webp', 'gif']

/** 运行时已安装主题（响应式，主题页直接渲染） */
export const installedThemes = reactive([])

// ---------------------------------------------------------------------------
// 通用校验 / 规范化
// ---------------------------------------------------------------------------

function fail(message) {
  throw new Error(message)
}

function assert(condition, message) {
  if (!condition) fail(message)
}

function basename(path) {
  return String(path).replace(/\\/g, '/').split('/').pop()
}

/** BiliLite 的 #AARRGGBB → CSS 的 #RRGGBBAA */
function toCssColor(value) {
  const m = /^#([0-9a-fA-F]{8})$/.exec(value)
  if (!m) return value
  const h = m[1]
  return `#${h.slice(2)}${h.slice(0, 2)}`
}

function mimeOf(ext) {
  switch (String(ext).toLowerCase()) {
    case 'jpg':
    case 'jpeg': return 'image/jpeg'
    case 'png': return 'image/png'
    case 'webp': return 'image/webp'
    case 'gif': return 'image/gif'
    default: return ''
  }
}

function validateManifest(manifest) {
  assert(manifest && typeof manifest === 'object', '清单格式错误')
  assert(manifest.type === 'theme', '不是主题插件：type 必须为 theme')
  const id = String(manifest.id || '').trim()
  assert(/^[A-Za-z0-9._-]{3,64}$/.test(id), '主题 id 非法（只允许字母数字 . _ -）')
  assert(!BUILTIN_THEMES.some((t) => t.id === id), `主题 id 与内置主题冲突：${id}`)
  return id
}

function pickThemeObject(manifest) {
  return (manifest.theme && typeof manifest.theme === 'object')
    ? manifest.theme
    : manifest
}

/**
 * 把清单里的 theme 规范化成 IKGR 的 theme 结构。
 * resolveImage(name) 负责把相对文件名解析成当前平台可加载的 URL。
 */
async function normalizeTheme(raw, resolveImage) {
  const theme = { ...(raw || {}) }

  // BiliLite 平铺写法：token 直接挂在 theme 下，且是 #AARRGGBB
  if (!theme.colors && !theme.darkColors) {
    const colors = {}
    for (const key of TOKEN_KEYS) {
      const value = theme[key]
      if (typeof value === 'string' && value.trim()) {
        colors[key] = toCssColor(value.trim())
      }
    }
    if (Object.keys(colors).length) {
      theme.colors = { ...colors }
      // 插件只有一套配色时，深色模式也用它，避免深色下回退成默认蓝
      theme.darkColors = { ...colors }
    }
  }

  // 已经是可直接加载的地址（外链 / data URL / 内置 static）就原样保留
  const isExternal = (value) => /^(https?:|data:|blob:|\/)/i.test(value)

  for (const key of BG_KEYS) {
    const value = typeof theme[key] === 'string' ? theme[key].trim() : ''
    if (!value) {
      delete theme[key]
      continue
    }
    if (isExternal(value)) {
      theme[key] = value
      continue
    }
    const resolved = await resolveImage(value)
    assert(resolved, `压缩包缺少背景图：${value}`)
    theme[key] = resolved
  }
  return theme
}

function buildRecord(manifest, id, theme, dir) {
  return {
    id,
    name: String(manifest.name || id),
    version: String(manifest.version || '1.0.0'),
    author: String(manifest.author || ''),
    description: String(manifest.description || ''),
    theme,
    dir: dir || '',
    installedAt: Date.now(),
  }
}

function applyRecord(record) {
  const materialized = materialize(record)
  applyThemeManifest({
    id: materialized.id,
    name: materialized.name,
    type: 'theme',
    theme: materialized.theme,
  })
}

/** App 端把 _doc/... 路径转成 <image> 能直接加载的绝对路径 */
function materialize(record) {
  const theme = { ...(record.theme || {}) }
  // #ifdef APP-PLUS
  for (const key of BG_KEYS) {
    const value = theme[key]
    if (typeof value === 'string' && value && !/^(data:|blob:|https?:|\/)/.test(value)) {
      try {
        theme[key] = plus.io.convertLocalFileSystemURL(value)
      } catch (e) {}
    }
  }
  // #endif
  return { ...record, theme }
}

// ---------------------------------------------------------------------------
// 注册表持久化
// ---------------------------------------------------------------------------

// #ifdef H5
function openDb() {
  return new Promise((resolve, reject) => {
    try {
      const req = indexedDB.open(DB_NAME, 1)
      req.onupgradeneeded = () => {
        const db = req.result
        if (!db.objectStoreNames.contains(DB_STORE)) {
          db.createObjectStore(DB_STORE, { keyPath: 'id' })
        }
      }
      req.onsuccess = () => resolve(req.result)
      req.onerror = () => reject(req.error || new Error('IndexedDB 打开失败'))
    } catch (e) {
      reject(e)
    }
  })
}

async function idbPut(record) {
  const db = await openDb()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(DB_STORE, 'readwrite')
    tx.objectStore(DB_STORE).put(record)
    tx.oncomplete = () => { db.close(); resolve() }
    tx.onerror = () => { db.close(); reject(tx.error) }
  })
}

async function idbAll() {
  const db = await openDb()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(DB_STORE, 'readonly')
    const req = tx.objectStore(DB_STORE).getAll()
    req.onsuccess = () => { db.close(); resolve(req.result || []) }
    req.onerror = () => { db.close(); reject(req.error) }
  })
}

async function idbDelete(id) {
  const db = await openDb()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(DB_STORE, 'readwrite')
    tx.objectStore(DB_STORE).delete(id)
    tx.oncomplete = () => { db.close(); resolve() }
    tx.onerror = () => { db.close(); reject(tx.error) }
  })
}

function storageRecords() {
  try {
    const raw = uni.getStorageSync(STORAGE_KEY)
    return Array.isArray(raw) ? raw : []
  } catch (e) {
    return []
  }
}

function storageSave(records) {
  uni.setStorageSync(STORAGE_KEY, records)
}
// #endif

// #ifdef APP-PLUS
function storageRecords() {
  try {
    const raw = uni.getStorageSync(STORAGE_KEY)
    return Array.isArray(raw) ? raw : []
  } catch (e) {
    return []
  }
}

function storageSave(records) {
  uni.setStorageSync(STORAGE_KEY, records)
}
// #endif

/** 读取全部已安装主题，并同步到响应式列表 */
export async function loadInstalledThemes() {
  let records = []
  // #ifdef H5
  try {
    records = await idbAll()
  } catch (e) {
    records = storageRecords()
  }
  // #endif
  // #ifdef APP-PLUS
  records = storageRecords()
  // #endif
  installedThemes.splice(0, installedThemes.length, ...records)
  return records
}

async function saveRecord(record) {
  let index = installedThemes.findIndex((t) => t.id === record.id)
  if (index >= 0) installedThemes.splice(index, 1, record)
  else installedThemes.push(record)

  // #ifdef H5
  try {
    await idbPut(record)
    return
  } catch (e) {
    // IndexedDB 不可用（如隐私模式）时退回 localStorage
  }
  // #endif
  const records = installedThemes.map((t) => ({ ...t }))
  storageSave(records)
}

async function deleteRecord(id) {
  // #ifdef H5
  try {
    await idbDelete(id)
  } catch (e) {
    const records = installedThemes.filter((t) => t.id !== id).map((t) => ({ ...t }))
    storageSave(records)
  }
  // #endif
  // #ifdef APP-PLUS
  const records = installedThemes.filter((t) => t.id !== id).map((t) => ({ ...t }))
  storageSave(records)
  // #endif
  const index = installedThemes.findIndex((t) => t.id === id)
  if (index >= 0) installedThemes.splice(index, 1)
}

// ---------------------------------------------------------------------------
// H5：解压 + data URL
// ---------------------------------------------------------------------------

function normalizeEntryName(raw) {
  const name = String(raw).replace(/\\/g, '/')
  if (name.startsWith('/') || name.split('/').includes('..')) return null
  return name
}

function bytesToBase64(bytes) {
  let binary = ''
  const chunk = 0x8000
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk))
  }
  return btoa(binary)
}

function decodeUtf8(bytes) {
  try {
    return new TextDecoder('utf-8').decode(bytes)
  } catch (e) {
    return ''
  }
}

function findBasePrefix(names) {
  if (names.includes('plugin.json') || names.includes('theme.json')) return ''
  for (const name of names) {
    const m = /^(.*\/)(plugin|theme)\.json$/.exec(name)
    if (m) return m[1]
  }
  return ''
}

function findAssetKey(entries, lowerIndex, base, value) {
  const clean = String(value).replace(/^\.\//, '')
  const name = basename(clean)
  const candidates = [
    `${base}assets/${name}`,
    `${base}${clean}`,
    `${base}assets/${clean}`,
  ]
  for (const key of candidates) {
    if (entries[key]) return key
  }
  // 大小写不敏感 + 允许 assets 子目录
  const lowerCandidates = candidates.map((k) => k.toLowerCase())
  for (const key of Object.keys(entries)) {
    const lower = key.toLowerCase()
    if (lowerCandidates.includes(lower)) return lowerIndex[lower] || key
    if (lower.endsWith(`/assets/${name.toLowerCase()}`)) return lowerIndex[lower] || key
  }
  return ''
}

// #ifdef H5
async function installFromBytes(bytes) {
  const { unzipSync } = await import('fflate')

  let files
  try {
    files = unzipSync(bytes)
  } catch (e) {
    fail('压缩包解析失败，请确认是有效的 zip 文件')
  }

  const entries = {}
  const lowerIndex = {}
  let total = 0
  let count = 0

  for (const [rawName, data] of Object.entries(files)) {
    const name = normalizeEntryName(rawName)
    assert(name !== null, `压缩包包含非法路径：${rawName}`)
    if (name.endsWith('/')) continue
    count += 1
    total += data.length
    assert(count <= MAX_FILES, '压缩包内文件过多')
    assert(data.length <= MAX_FILE_BYTES, `文件过大：${name}`)
    assert(total <= MAX_ZIP_BYTES, '解压后体积过大')
    entries[name] = data
    lowerIndex[name.toLowerCase()] = name
  }

  const base = findBasePrefix(Object.keys(entries))
  const manifestText = entries[`${base}plugin.json`]
    ? decodeUtf8(entries[`${base}plugin.json`])
    : (entries[`${base}theme.json`] ? decodeUtf8(entries[`${base}theme.json`]) : '')
  assert(manifestText, '压缩包缺少 plugin.json 或 theme.json')

  let manifest
  try {
    manifest = JSON.parse(manifestText)
  } catch (e) {
    fail('清单 JSON 解析失败')
  }

  const id = validateManifest(manifest)
  const rawTheme = pickThemeObject(manifest)

  const theme = await normalizeTheme(rawTheme, async (value) => {
    const key = findAssetKey(entries, lowerIndex, base, value)
    if (!key) return ''
    const ext = String(key).split('.').pop().toLowerCase()
    assert(IMAGE_EXT.includes(ext), `不支持的图片格式：${key}`)
    return `data:${mimeOf(ext)};base64,${bytesToBase64(entries[key])}`
  })

  assert(
    theme.colors || theme.darkColors || Object.keys(theme).some((k) => BG_KEYS.includes(k)),
    '主题内容为空',
  )

  const record = buildRecord(manifest, id, theme, '')
  assert(record.theme && Object.keys(record.theme).length, '主题内容为空')
  await saveRecord(record)
  applyRecord(record)
  return record
}
// #endif

// ---------------------------------------------------------------------------
// App：plus.zip 解压 + 文件路径
// ---------------------------------------------------------------------------

// #ifdef APP-PLUS
function plusResolve(path) {
  return new Promise((resolve, reject) => {
    plus.io.resolveLocalFileSystemURL(path, resolve, reject)
  })
}

function plusExists(path) {
  return new Promise((resolve) => {
    plus.io.resolveLocalFileSystemURL(path, () => resolve(true), () => resolve(false))
  })
}

function plusReadText(path) {
  return new Promise((resolve, reject) => {
    plus.io.resolveLocalFileSystemURL(path, (entry) => {
      entry.file((file) => {
        const reader = new plus.io.FileReader()
        reader.onloadend = (e) => resolve(String((e.target && e.target.result) || ''))
        reader.onerror = reject
        reader.readAsText(file, 'utf-8')
      }, reject)
    }, reject)
  })
}

async function plusReadTextOrNull(path) {
  try {
    return await plusReadText(path)
  } catch (e) {
    return null
  }
}

function plusReadDir(path) {
  return plusResolve(path).then((entry) => new Promise((resolve, reject) => {
    const reader = entry.createReader()
    reader.readEntries(resolve, reject)
  }))
}

/** readEntries 在部分设备上分批返回，这里读到空批次为止。 */
function plusReadAllEntries(path) {
  return plusResolve(path).then((entry) => new Promise((resolve, reject) => {
    const reader = entry.createReader()
    const all = []
    const read = () => reader.readEntries((batch) => {
      if (!batch || !batch.length) {
        resolve(all)
        return
      }
      all.push(...batch)
      read()
    }, reject)
    read()
  }))
}

/**
 * App 端解压后校验：文件数、单文件大小、解压后总大小、目录层级。
 * H5 端 installFromBytes 已有同等校验；App 端 plus.zip 不会替我们做。
 */
async function plusDirStats(dir, depth = 0) {
  assert(depth <= 12, '压缩包目录层级过深')
  const entries = await plusReadAllEntries(dir)
  let count = 0
  let total = 0
  for (const entry of entries) {
    if (entry.isDirectory) {
      const sub = await plusDirStats(`${dir}/${entry.name}`, depth + 1)
      count += sub.count
      total += sub.total
      assert(count <= MAX_FILES, '压缩包内文件过多')
      assert(total <= MAX_ZIP_BYTES, '解压后体积过大')
      continue
    }
    count += 1
    assert(count <= MAX_FILES, '压缩包内文件过多')
    const size = await new Promise((resolve) => {
      entry.file((file) => resolve(Number(file.size) || 0), () => resolve(0))
    })
    assert(size <= MAX_FILE_BYTES, `文件过大：${entry.name || ''}`)
    total += size
    assert(total <= MAX_ZIP_BYTES, '解压后体积过大')
  }
  return { count, total }
}

function plusDecompress(zipPath, targetDir) {
  return new Promise((resolve, reject) => {
    plus.zip.decompress(zipPath, targetDir, resolve, reject)
  })
}

/** 逐级创建 _doc 下的目录（plus.zip 不保证创建中间目录） */
function plusEnsureDir(path) {
  return new Promise((resolve) => {
    plus.io.resolveLocalFileSystemURL(path, () => resolve(), () => {
      const cut = path.lastIndexOf('/')
      if (cut <= 0) return resolve()
      const parent = path.slice(0, cut)
      const name = path.slice(cut + 1)
      plusEnsureDir(parent).then(() => {
        plus.io.resolveLocalFileSystemURL(parent, (parentEntry) => {
          parentEntry.getDirectory(name, { create: true }, () => resolve(), () => resolve())
        }, () => resolve())
      }).catch(() => resolve())
    })
  })
}

function plusMoveDir(from, parent, newName) {
  return new Promise((resolve, reject) => {
    plusResolve(from).then((entry) => {
      plusResolve(parent).then((parentEntry) => {
        entry.moveTo(parentEntry, newName, resolve, reject)
      }, reject)
    }, reject)
  })
}

function plusRemoveDir(path) {
  return plusResolve(path).then((entry) => new Promise((resolve) => {
    entry.removeRecursively(resolve, resolve)
  })).catch(() => {})
}

async function findAppBase(dir) {
  if (await plusExists(`${dir}/plugin.json`)) return dir
  if (await plusExists(`${dir}/theme.json`)) return dir
  let entries = []
  try {
    entries = await plusReadDir(dir)
  } catch (e) {}
  for (const entry of entries) {
    if (!entry.isDirectory) continue
    const sub = `${dir}/${entry.name}`
    if (await plusExists(`${sub}/plugin.json`) || await plusExists(`${sub}/theme.json`)) {
      return sub
    }
  }
  fail('压缩包缺少 plugin.json 或 theme.json')
}

async function resolveAppAsset(base, value) {
  const clean = String(value).replace(/^\.\//, '')
  const name = basename(clean)
  const candidates = [
    `${base}/assets/${name}`,
    `${base}/${clean}`,
    `${base}/assets/${clean}`,
  ]
  for (const path of candidates) {
    if (await plusExists(path)) {
      const ext = path.split('.').pop().toLowerCase()
      assert(IMAGE_EXT.includes(ext), `不支持的图片格式：${path}`)
      return path
    }
  }
  return ''
}

async function installFromZipPath(zipPath) {
  const info = await new Promise((resolve) => {
    uni.getFileInfo({
      filePath: zipPath,
      success: resolve,
      fail: () => resolve(null),
    })
  })
  if (info && typeof info.size === 'number') {
    assert(info.size <= MAX_ZIP_BYTES, '压缩包不能超过 10MB')
  }

  const stamp = Date.now()
  const tmpDir = `${APP_ROOT}/tmp_${stamp}`
  await plusEnsureDir(APP_ROOT)
  try {
    await plusDecompress(zipPath, tmpDir)
    await plusDirStats(tmpDir)
  } catch (e) {
    await plusRemoveDir(tmpDir)
    fail(e && e.message ? e.message : '解压失败，请确认 zip 文件有效')
  }

  const tmpBase = await findAppBase(tmpDir)
  const manifestText = (await plusReadTextOrNull(`${tmpBase}/plugin.json`))
    || (await plusReadTextOrNull(`${tmpBase}/theme.json`))
    || ''
  assert(manifestText, '压缩包缺少 plugin.json 或 theme.json')

  let manifest
  try {
    manifest = JSON.parse(manifestText)
  } catch (e) {
    await plusRemoveDir(tmpDir)
    fail('清单 JSON 解析失败')
  }

  let id
  try {
    id = validateManifest(manifest)
  } catch (e) {
    await plusRemoveDir(tmpDir)
    throw e
  }

  // 同一 id 重装：先删旧目录
  const old = installedThemes.find((t) => t.id === id)
  if (old && old.dir && old.dir.startsWith(`${APP_ROOT}/`)) await plusRemoveDir(old.dir)

  const safeId = id.replace(/[^A-Za-z0-9._-]/g, '_')
  const finalName = `${safeId}_${stamp}`
  let finalDir = tmpDir
  let base = tmpBase
  try {
    await plusMoveDir(tmpDir, APP_ROOT, finalName)
    finalDir = `${APP_ROOT}/${finalName}`
    base = finalDir + tmpBase.slice(tmpDir.length)
  } catch (e) {
    // move 失败就直接把临时目录当安装目录
  }

  const rawTheme = pickThemeObject(manifest)
  const theme = await normalizeTheme(rawTheme, (value) => resolveAppAsset(base, value))
  assert(
    theme.colors || theme.darkColors || Object.keys(theme).some((k) => BG_KEYS.includes(k)),
    '主题内容为空',
  )

  const record = buildRecord(manifest, id, theme, finalDir)
  await saveRecord(record)
  applyRecord(record)
  return record
}
// #endif

// ---------------------------------------------------------------------------
// 随包内置示例（app/src/static/plugin-examples/）
// ---------------------------------------------------------------------------

export const EXAMPLE_PLUGINS = [
  {
    file: 'theme_wild.zip',
    name: '原野（BiliLite 格式）',
    description: 'plugin.json 平铺 token + #AARRGGBB，安装时自动转换',
  },
  {
    file: 'theme_sunset.zip',
    name: '日落（IKGR 格式）',
    description: 'theme.json + colors/darkColors + 手机/平板双背景图',
  },
]

// #ifdef APP-PLUS
async function installBundledZipApp(appPath) {
  const srcPath = `_www${appPath}`
  const stamp = Date.now()
  const copyName = `_bundled_${stamp}.zip`
  let copiedPath = ''

  await plusEnsureDir(APP_ROOT)
  try {
    const srcEntry = await plusResolve(srcPath)
    const rootEntry = await plusResolve(APP_ROOT)
    await new Promise((resolve, reject) => {
      srcEntry.copyTo(rootEntry, copyName, resolve, reject)
    })
    copiedPath = `${APP_ROOT}/${copyName}`
  } catch (e) {
    // 部分基座不允许访问 _www，退化为直接解压应用资源路径
  }

  try {
    return await installFromZipPath(copiedPath || srcPath)
  } finally {
    if (copiedPath) {
      try {
        const entry = await plusResolve(copiedPath)
        await new Promise((resolve) => entry.remove(resolve, resolve))
      } catch (e) {}
    }
  }
}
// #endif

/** 安装随包内置的示例插件（H5 / App 都可用，手机无需选文件） */
export async function installExamplePlugin(example) {
  assert(example && example.file, '示例插件无效')
  const appPath = `/static/plugin-examples/${example.file}`
  // #ifdef H5
  const resp = await fetch(appPath)
  assert(resp && resp.ok, `读取示例失败：${example.file}`)
  const bytes = new Uint8Array(await resp.arrayBuffer())
  return installFromBytes(bytes)
  // #endif
  // #ifdef APP-PLUS
  return installBundledZipApp(appPath)
  // #endif
}

// ---------------------------------------------------------------------------
// 对外 API
// ---------------------------------------------------------------------------

/** H5 文件选择后调用（App 端不支持本地文件选择，会抛错） */
export async function installThemeFromFile(file) {
  assert(file, '未选择文件')
  assert(file.size <= MAX_ZIP_BYTES, '压缩包不能超过 10MB')
  // #ifdef H5
  const bytes = new Uint8Array(await file.arrayBuffer())
  return installFromBytes(bytes)
  // #endif
  // #ifndef H5
  fail('当前平台请使用「从链接安装」')
  // #endif
}

/** 从链接安装（H5 / App 都支持；H5 需目标服务器允许跨域） */
export async function installThemeFromUrl(url) {
  const target = String(url || '').trim()
  assert(/^(https?|blob):\/\//i.test(target), '请输入 http(s) 链接')
  const res = await new Promise((resolve, reject) => {
    uni.downloadFile({
      url: target,
      success: resolve,
      fail: (err) => reject(new Error((err && err.errMsg) || '下载失败')),
    })
  })
  assert(res && res.tempFilePath, '下载失败')

  // #ifdef H5
  const resp = await fetch(res.tempFilePath)
  const bytes = new Uint8Array(await resp.arrayBuffer())
  return installFromBytes(bytes)
  // #endif
  // #ifdef APP-PLUS
  return installFromZipPath(res.tempFilePath)
  // #endif
}

/** 应用某个已安装主题（App 端会自动转换本地路径） */
export function applyInstalledTheme(record) {
  applyRecord(record)
}

/** 卸载：删记录 + App 端删文件；若正在使用则恢复默认 */
export async function uninstallTheme(id) {
  const record = installedThemes.find((t) => t.id === id)
  if (!record) return
  // #ifdef APP-PLUS
  if (record.dir && record.dir.startsWith(`${APP_ROOT}/`)) {
    await plusRemoveDir(record.dir)
  }
  // #endif
  await deleteRecord(id)
  if (themeState.pluginId === id) clearPluginTheme()
}

/** 启动时恢复：把当前激活的已安装主题重新应用一遍 */
export async function restoreInstalledThemes() {
  try {
    const records = await loadInstalledThemes()
    const active = records.find((r) => r.id === themeState.pluginId)
    if (active) applyRecord(active)
  } catch (e) {
    console.error('[theme-install] 恢复已安装主题失败', e)
  }
}
