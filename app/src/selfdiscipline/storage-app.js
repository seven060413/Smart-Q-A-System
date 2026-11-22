// App 端存储适配器：优先使用 plus.sqlite，异常时降级为 JSON 存储。
// 注意：plus.sqlite 不支持参数绑定，所有字符串都必须经 sqlEscape 转义。

import { createH5Storage } from './storage-h5.js'

const DB_NAME = 'ikgr_sd'
const DB_PATH = '_doc/ikgr_sd.db'

const SCHEMA = [
  `CREATE TABLE IF NOT EXISTS focus_sessions (
    id TEXT PRIMARY KEY,
    task TEXT NOT NULL,
    planned_min INTEGER NOT NULL,
    actual_min INTEGER NOT NULL DEFAULT 0,
    started_at INTEGER NOT NULL,
    ended_at INTEGER,
    status TEXT NOT NULL,
    points INTEGER NOT NULL DEFAULT 0
  )`,
  `CREATE TABLE IF NOT EXISTS checkin_items (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    note TEXT DEFAULT '',
    remind_time TEXT DEFAULT '',
    days TEXT NOT NULL DEFAULT '1,2,3,4,5,6,7',
    enabled INTEGER NOT NULL DEFAULT 1,
    kind TEXT NOT NULL DEFAULT 'daily',
    date TEXT DEFAULT '',
    created_at INTEGER NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS checkin_records (
    id TEXT PRIMARY KEY,
    item_id TEXT NOT NULL,
    date TEXT NOT NULL,
    done_at INTEGER NOT NULL,
    points INTEGER NOT NULL DEFAULT 0,
    UNIQUE(item_id, date)
  )`,
  `CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    target_app TEXT NOT NULL,
    purpose TEXT NOT NULL,
    minutes INTEGER NOT NULL,
    started_at INTEGER NOT NULL,
    reminder_at INTEGER NOT NULL,
    ended_at INTEGER,
    status TEXT NOT NULL,
    points INTEGER NOT NULL DEFAULT 0
  )`,
  `CREATE TABLE IF NOT EXISTS points_ledger (
    id TEXT PRIMARY KEY,
    delta INTEGER NOT NULL,
    reason TEXT NOT NULL,
    ref_type TEXT DEFAULT '',
    ref_id TEXT DEFAULT '',
    created_at INTEGER NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS reminders (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    ref_id TEXT DEFAULT '',
    trigger_at INTEGER NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
  )`,
  `CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
  )`,
  'CREATE INDEX IF NOT EXISTS idx_focus_started ON focus_sessions(started_at)',
  'CREATE INDEX IF NOT EXISTS idx_report_started ON reports(started_at)',
  'CREATE INDEX IF NOT EXISTS idx_record_date ON checkin_records(date)',
  'CREATE INDEX IF NOT EXISTS idx_ledger_created ON points_ledger(created_at)',
  'CREATE INDEX IF NOT EXISTS idx_reminder_status ON reminders(status)',
]

// 旧库升级：逐条执行并忽略“列已存在”错误，不能因为迁移失败而降级整个存储。
const MIGRATIONS = [
  "ALTER TABLE checkin_items ADD COLUMN kind TEXT NOT NULL DEFAULT 'daily'",
  "ALTER TABLE checkin_items ADD COLUMN date TEXT DEFAULT ''",
]

const TABLES = [
  'focus_sessions',
  'checkin_items',
  'checkin_records',
  'reports',
  'points_ledger',
  'reminders',
  'settings',
]

function sqlEscape(value) {
  return String(value == null ? '' : value).replace(/'/g, "''")
}

function sqlValue(value) {
  if (value === null || value === undefined) return 'NULL'
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  if (typeof value === 'boolean') return value ? '1' : '0'
  return `'${sqlEscape(value)}'`
}

function quoteId(name) {
  return `"${String(name).replace(/"/g, '""')}"`
}

function hasSqlite() {
  try {
    return typeof plus !== 'undefined' && !!plus.sqlite
  } catch (e) {
    return false
  }
}

export function createAppStorage() {
  const fallback = createH5Storage()
  let initPromise = null
  let useSqlite = hasSqlite()

  function openDatabase() {
    return new Promise((resolve, reject) => {
      plus.sqlite.openDatabase({
        name: DB_NAME,
        path: DB_PATH,
        success: () => resolve(),
        fail: () => reject(new Error('openDatabase failed')),
      })
    })
  }

  function executeSql(sql) {
    return new Promise((resolve, reject) => {
      plus.sqlite.executeSql({
        name: DB_NAME,
        sql,
        success: () => resolve(),
        fail: (e) => reject(new Error((e && e.message) || 'executeSql failed')),
      })
    })
  }

  function selectSql(sql) {
    return new Promise((resolve, reject) => {
      plus.sqlite.selectSql({
        name: DB_NAME,
        sql,
        success: (rows) => resolve(Array.isArray(rows) ? rows : []),
        fail: (e) => reject(new Error((e && e.message) || 'selectSql failed')),
      })
    })
  }

  async function insertSqliteRow(table, row) {
    const keys = Object.keys(row || {})
    if (!keys.length) return
    const cols = keys.map(quoteId).join(', ')
    const values = keys.map((key) => sqlValue(row[key])).join(', ')
    await executeSql(
      `INSERT OR REPLACE INTO ${quoteId(table)} (${cols}) VALUES (${values})`
    )
  }

  const LEGACY_IMPORT_KEY = 'legacy_json_imported'

  /**
   * 旧版本在 SQLite 不可用时会把整个库放到 uni storage 的 ikgr_sd_v1。
   * 第一次成功打开 SQLite 时把旧 JSON 数据导入，避免升级后看起来“数据丢了”。
   */
  async function importLegacyJsonIfNeeded() {
    const marker = await selectSql(
      `SELECT value FROM settings WHERE key = '${LEGACY_IMPORT_KEY}' LIMIT 1`
    )
    if (marker && marker.length) return

    await fallback.init()
    const data = await fallback.exportAll()
    for (const table of TABLES) {
      const rows = data && data[table]
      if (!Array.isArray(rows) || !rows.length) continue
      for (const row of rows) await insertSqliteRow(table, row)
    }
    await executeSql(
      `INSERT OR REPLACE INTO settings (key, value) VALUES ('${LEGACY_IMPORT_KEY}', '1')`
    )
  }

  async function ensureOpen() {
    if (!initPromise) {
      initPromise = (async () => {
        if (!useSqlite) return
        try {
          await openDatabase()
        } catch (e) {
          useSqlite = false
          return
        }
        try {
          // 每条 CREATE 分开执行，避免多语句在部分设备上失败。
          for (const sql of SCHEMA) await executeSql(sql)
        } catch (e) {
          // 建表失败时退回 JSON 存储，保证业务可用。
          useSqlite = false
          return
        }
        // 旧库补列；列已存在时 SQLite 会报错，直接忽略。
        for (const sql of MIGRATIONS) {
          try {
            await executeSql(sql)
          } catch (e) {}
        }
        // 迁移失败只记录，不整体降级；下次启动会重试（marker 未写入）。
        try {
          await importLegacyJsonIfNeeded()
        } catch (e) {
          console.error('[ikgr_sd] 旧 JSON 数据导入失败', e)
        }
      })()
    }
    return initPromise
  }

  async function withSqlite(task, fallbackTask) {
    await ensureOpen()
    if (!useSqlite) return fallbackTask()
    try {
      return await task()
    } catch (e) {
      // 单次 SQL 失败不整体降级，避免已经在 SQLite 里的数据“消失”。
      throw e
    }
  }

  return {
    get mode() {
      return useSqlite ? 'sqlite' : 'json'
    },

    async init() {
      await ensureOpen()
      if (!useSqlite) await fallback.init()
    },

    async readTable(table) {
      return withSqlite(
        () => selectSql(`SELECT * FROM ${quoteId(table)}`),
        () => fallback.readTable(table)
      )
    },

    async insert(table, row) {
      return withSqlite(
        async () => {
          await insertSqliteRow(table, row)
          return { ...row }
        },
        () => fallback.insert(table, row)
      )
    },

    async insertMany(table, rows) {
      return withSqlite(
        async () => {
          for (const row of rows || []) await insertSqliteRow(table, row)
        },
        () => fallback.insertMany(table, rows)
      )
    },

    async update(table, pkValue, patch) {
      return withSqlite(
        async () => {
          const keys = Object.keys(patch)
          if (!keys.length) return null
          const pk = table === 'settings' ? 'key' : 'id'
          const sets = keys.map((key) => `${quoteId(key)} = ${sqlValue(patch[key])}`).join(', ')
          await executeSql(
            `UPDATE ${quoteId(table)} SET ${sets} WHERE ${quoteId(pk)} = ${sqlValue(pkValue)}`
          )
          return { ...patch }
        },
        () => fallback.update(table, pkValue, patch)
      )
    },

    async remove(table, pkValue) {
      return withSqlite(
        async () => {
          const pk = table === 'settings' ? 'key' : 'id'
          await executeSql(
            `DELETE FROM ${quoteId(table)} WHERE ${quoteId(pk)} = ${sqlValue(pkValue)}`
          )
        },
        () => fallback.remove(table, pkValue)
      )
    },

    async clearAll() {
      return withSqlite(
        async () => {
          for (const table of TABLES) {
            await executeSql(`DELETE FROM ${quoteId(table)}`)
          }
          // 同时清掉旧 JSON，避免下次启动把已清空的数据重新导入。
          try {
            await fallback.clearAll()
          } catch (e) {}
          await executeSql(
            `INSERT OR REPLACE INTO settings (key, value) VALUES ('${LEGACY_IMPORT_KEY}', '1')`
          )
        },
        () => fallback.clearAll()
      )
    },

    async exportAll() {
      return withSqlite(
        async () => {
          const out = {}
          for (const table of TABLES) {
            out[table] = await selectSql(`SELECT * FROM ${quoteId(table)}`)
          }
          return out
        },
        () => fallback.exportAll()
      )
    },
  }
}
