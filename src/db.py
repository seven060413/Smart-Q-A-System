"""SQLite 连接管理：统一 PRAGMA 与路径解析。

本模块只负责「怎么连」，不负责「建什么表」；建表与迁移见 src/schema.py，
命令行入口见 scripts/migrate.py。所有连接都开启外键约束，业务代码不用自己记住
PRAGMA foreign_keys=ON。
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Union

# 项目根目录（src/db.py 的上一级）
ROOT = Path(__file__).resolve().parents[1]

# 数据库文件默认放在 data/app/ 下，与图谱 JSON 分离，且不入库（见 .gitignore）。
# 可用环境变量 IKGR_DB_PATH 覆盖，便于测试与部署指定不同位置。
DEFAULT_DB_PATH = ROOT / "data" / "app" / "ikgr.db"

# SQLite 连接需要的统一配置：外键约束、WAL、写锁等待。
PRAGMAS = (
    "PRAGMA foreign_keys = ON",
    "PRAGMA journal_mode = WAL",
    "PRAGMA busy_timeout = 5000",
)


def resolve_db_path(path: Union[str, Path, None] = None) -> Path:
    """解析数据库文件路径：显式参数 > 环境变量 > 默认值。"""
    if path is not None:
        return Path(path)
    env = os.getenv("IKGR_DB_PATH")
    if env:
        return Path(env)
    return DEFAULT_DB_PATH


def connect(path: Union[str, Path, None] = None) -> sqlite3.Connection:
    """打开数据库连接并应用统一 PRAGMA。

    - path 为 ``None`` 时使用默认文件路径（会自动创建父目录）；
    - path 为 ``":memory:"`` 时使用内存库（测试用），WAL 对其无意义但无害。
    """
    resolved = resolve_db_path(path)
    if str(resolved) != ":memory:":
        resolved.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(resolved))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def backup(conn: sqlite3.Connection, dest: Union[str, Path]) -> Path:
    """用 SQLite 在线备份 API 把当前库复制到 dest，返回 dest 路径。

    用于迁移前、导入前的快照；在线备份比复制文件安全（不会拿到半写状态）。
    """
    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_conn = sqlite3.connect(str(dest_path))
    try:
        with dest_conn:
            conn.backup(dest_conn)
    finally:
        dest_conn.close()
    return dest_path
