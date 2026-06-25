"""
订阅数据模型。
管理创作者、用户订阅、文章评分。
"""

import sqlite3
import os
from datetime import datetime, timezone
from pathlib import Path


def get_db_path() -> Path:
    """数据库文件路径：~/.ainews/subscriptions.db"""
    path = Path.home() / ".ainews"
    path.mkdir(parents=True, exist_ok=True)
    return path / "subscriptions.db"


def get_connection() -> sqlite3.Connection:
    """获取数据库连接（自动创建表）。"""
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _init_tables(conn)
    return conn


def _init_tables(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS creators (
            id              TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            source          TEXT NOT NULL,
            gh_id           TEXT,
            avatar_url      TEXT,
            auto_followed   INTEGER DEFAULT 0,
            quality_score   REAL DEFAULT 0,
            article_count   INTEGER DEFAULT 0,
            first_seen_at   TEXT,
            last_seen_at    TEXT,
            is_followed     INTEGER DEFAULT 1,
            created_at      TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS articles_seen (
            url             TEXT PRIMARY KEY,
            creator_id      TEXT NOT NULL,
            title           TEXT,
            score           REAL DEFAULT 0,
            user_rating     INTEGER,
            rated_at        TEXT,
            seen_at         TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (creator_id) REFERENCES creators(id)
        );

        CREATE INDEX IF NOT EXISTS idx_articles_creator ON articles_seen(creator_id);
        CREATE INDEX IF NOT EXISTS idx_creators_followed ON creators(is_followed);
        CREATE INDEX IF NOT EXISTS idx_creators_score ON creators(quality_score DESC);
    """)
    conn.commit()


def make_creator_id(source: str, name: str) -> str:
    """生成唯一的创作者 ID。"""
    return f"{source}:{name.strip()}"
