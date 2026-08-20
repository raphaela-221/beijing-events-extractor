"""SQLite 元数据存储。日志走文件，DB 只存路径与字节数（指南 §3.1）。"""
from __future__ import annotations

import sqlite3
from datetime import datetime

from . import config

# 指南 §3.2 表结构
SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id                TEXT PRIMARY KEY,
  op_id                 TEXT NOT NULL,
  op_label              TEXT NOT NULL,
  op_group              TEXT NOT NULL,
  preset                TEXT,
  params_json           TEXT NOT NULL,
  status                TEXT NOT NULL,
  current_stage         TEXT,
  stage_index           INTEGER,
  started_at            TEXT NOT NULL,
  ended_at              TEXT,
  duration_ms           INTEGER,
  exit_code             INTEGER,
  operator              TEXT NOT NULL,
  log_path              TEXT NOT NULL,
  log_lines             INTEGER DEFAULT 0,
  log_bytes             INTEGER DEFAULT 0,
  summary_json          TEXT,
  llm_json              TEXT,
  error_summary         TEXT,
  error_kind             TEXT,
  canonical_backup_path TEXT,
  artifacts_json        TEXT,
  pinned                INTEGER DEFAULT 0,
  deleted_at            TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_started ON runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_op      ON runs(op_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_status  ON runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_deleted ON runs(deleted_at);

CREATE TABLE IF NOT EXISTS run_deletions (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id            TEXT NOT NULL,
  op_label          TEXT NOT NULL,
  run_started_at    TEXT,
  deleted_at        TEXT NOT NULL,
  deleted_by        TEXT NOT NULL,
  mode              TEXT NOT NULL,
  reason            TEXT,
  artifacts_deleted INTEGER NOT NULL DEFAULT 0,
  freed_bytes       INTEGER
);

-- P1: 发布历史（预览发布页 mark-done 写入）
CREATE TABLE IF NOT EXISTS publishes (
  publish_id  TEXT PRIMARY KEY,
  created_at  TEXT NOT NULL,
  operator    TEXT NOT NULL,
  zip_path    TEXT,
  note        TEXT
);
CREATE INDEX IF NOT EXISTS idx_publishes_created ON publishes(created_at DESC);

-- P1: canonical 下载哈希记录（核对往返防旧版本覆盖，§5.5）
CREATE TABLE IF NOT EXISTS canonical_downloads (
  download_id   TEXT PRIMARY KEY,
  hash          TEXT NOT NULL,
  downloaded_at TEXT NOT NULL,
  operator      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cdownloads_operator ON canonical_downloads(operator, downloaded_at DESC);
"""


def connect() -> sqlite3.Connection:
    """每次调用新建连接。sqlite 本地文件足够快，避免跨线程共享状态。"""
    conn = sqlite3.connect(str(config.DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    config.ensure_dirs()
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def recover_orphans() -> int:
    """服务启动时把 queued/running 标为 failed/interrupted（指南 §3.5）。
    否则历史页永远挂假「运行中」，编辑锁也放不出来。"""
    now = datetime.now().isoformat(timespec="seconds")
    conn = connect()
    try:
        cur = conn.execute(
            """UPDATE runs
               SET status='failed',
                   error_kind='interrupted',
                   error_summary='服务重启，任务中断',
                   ended_at=?
             WHERE status IN ('queued','running')""",
            (now,),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()
