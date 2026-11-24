"""SQLite 持久层：月表、换发申请、批次、格子值。"""

import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator

DB_PATH = os.environ.get("DB_PATH", "/data/port_tables.db")

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS month (
    month       TEXT PRIMARY KEY,
    row_labels  TEXT NOT NULL,
    col_labels  TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS replacement (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    month       TEXT NOT NULL REFERENCES month(month),
    status      TEXT NOT NULL CHECK (status IN ('pending','confirmed')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    confirmed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_replacement_month ON replacement(month);

-- 现用表：每月登记后固定的行列骨架，每个格子一行。
CREATE TABLE IF NOT EXISTS live_cell (
    month   TEXT NOT NULL REFERENCES month(month),
    r       TEXT NOT NULL,
    c       TEXT NOT NULL,
    value   INTEGER NOT NULL CHECK (value >= 0),
    PRIMARY KEY (month, r, c)
);

-- 新表逐格存底：confirmed=1 的格子才对外显示新值。
CREATE TABLE IF NOT EXISTS replacement_cell (
    replacement_id INTEGER NOT NULL REFERENCES replacement(id),
    r              TEXT NOT NULL,
    c              TEXT NOT NULL,
    old_value      INTEGER NOT NULL,
    new_value      INTEGER NOT NULL CHECK (new_value >= 0),
    confirmed      INTEGER NOT NULL DEFAULT 0 CHECK (confirmed IN (0, 1)),
    PRIMARY KEY (replacement_id, r, c)
);
CREATE INDEX IF NOT EXISTS idx_rpcell_conf
    ON replacement_cell(replacement_id, confirmed);

CREATE TABLE IF NOT EXISTS batch (
    replacement_id INTEGER NOT NULL REFERENCES replacement(id),
    batch_no       INTEGER NOT NULL,
    confirmed      INTEGER NOT NULL DEFAULT 0 CHECK (confirmed IN (0, 1)),
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    confirmed_at   TEXT,
    PRIMARY KEY (replacement_id, batch_no)
);

CREATE TABLE IF NOT EXISTS batch_cell (
    replacement_id INTEGER NOT NULL,
    batch_no       INTEGER NOT NULL,
    r              TEXT NOT NULL,
    c              TEXT NOT NULL,
    PRIMARY KEY (replacement_id, batch_no, r, c),
    FOREIGN KEY (replacement_id, batch_no)
        REFERENCES batch(replacement_id, batch_no),
    FOREIGN KEY (replacement_id, r, c)
        REFERENCES replacement_cell(replacement_id, r, c)
);
"""


def connect(db_path: str = None) -> sqlite3.Connection:
    # 默认路径在调用时读取环境变量，便于测试用 monkeypatch 切换库，
    # 也让容器中的 DB_PATH 配置始终生效
    path = db_path if db_path is not None else os.environ.get("DB_PATH", DB_PATH)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: str = None) -> None:
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """串行化写事务：BEGIN IMMEDIATE 让并发确认/申请排队而不是写冲突报错。"""
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


@contextmanager
def read_transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    try:
        conn.execute("BEGIN")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
