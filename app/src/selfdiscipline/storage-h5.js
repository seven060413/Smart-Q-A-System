// H5 存储适配器：整个库序列化成 JSON 存进 uni storage。
// 接口与 App 端 SQLite 适配器保持一致，页面永远只依赖 repository.js。

const STORAGE_KEY = 'ikgr_sd_v1'

export const TABLES = [
  'focus_sessions',
  'checkin_items',
  'checkin_records',
  'reports',
  'points_ledger',
  'reminders',
  'settings',
]

function emptyDb() {
  const db = {}
  for (const name of TABLES) db[name] = []
  return db
}

function normalize(raw) {
  const db = emptyDb()
  if (!raw || typeof raw !== 'object') return db
  for (const name of TABLES) {
    db[name] = Array.isArray(raw[name]) ? raw[name] : []
  }
  return db
}

let db = null
let loaded = false

function loadDb() {
  if (loaded) return db
  try {
    const raw = uni.getStorageSync(STORAGE_KEY)
    db = normalize(typeof raw === 'string' ? safeParse(raw) : raw)
  } catch (e) {
    db = emptyDb()
  }
  loaded = true
  return db
}

function safeParse(text) {
  try {
    return JSON.parse(text)
  } catch (e) {
    return null
  }
}

function saveDb() {
  try {
    uni.setStorageSync(STORAGE_KEY, JSON.stringify(db))
  } catch (e) {
    // 存储失败不应打断业务流程，下一次写操作会再尝试。
  }
}

function pkOf(table) {
  return table === 'settings' ? 'key' : 'id'
}

function clone(row) {
  return row ? { ...row } : row
}

export function createH5Storage() {
  return {
    async init() {
      loadDb()
    },

    async readTable(table) {
      const data = loadDb()
      return (data[table] || []).map(clone)
    },

    async insert(table, row) {
      const data = loadDb()
      if (!data[table]) data[table] = []
      const pk = pkOf(table)
      const list = data[table]
      const index = list.findIndex((item) => String(item[pk]) === String(row[pk]))
      const record = { ...row }
      if (index >= 0) list.splice(index, 1, record)
      else list.push(record)
      saveDb()
      return clone(record)
    },

    async insertMany(table, rows) {
      const data = loadDb()
      if (!data[table]) data[table] = []
      for (const row of rows || []) {
        const pk = pkOf(table)
        const list = data[table]
        const index = list.findIndex((item) => String(item[pk]) === String(row[pk]))
        const record = { ...row }
        if (index >= 0) list.splice(index, 1, record)
        else list.push(record)
      }
      saveDb()
    },

    async update(table, pkValue, patch) {
      const data = loadDb()
      const pk = pkOf(table)
      const list = data[table] || []
      const index = list.findIndex((item) => String(item[pk]) === String(pkValue))
      if (index < 0) return null
      list.splice(index, 1, { ...list[index], ...patch })
      saveDb()
      return clone(list[index])
    },

    async remove(table, pkValue) {
      const data = loadDb()
      const pk = pkOf(table)
      if (!data[table]) return
      data[table] = data[table].filter((item) => String(item[pk]) !== String(pkValue))
      saveDb()
    },

    async clearAll() {
      db = emptyDb()
      loaded = true
      saveDb()
    },

    async exportAll() {
      const data = loadDb()
      const out = {}
      for (const name of TABLES) out[name] = (data[name] || []).map(clone)
      return out
    },
  }
}
