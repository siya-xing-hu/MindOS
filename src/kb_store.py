"""SQLite 存储知识库实例配置。

每个知识库实例独立配置：数据源、workspace 路径、embedding、LLM。
支持一键复制（复制配置，collection 名和 workspace 路径需改）。
"""
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

from .config import SQLITE_PATH


SCHEMA = """
CREATE TABLE IF NOT EXISTS kb_config (
    kb_name            TEXT PRIMARY KEY,
    display_name       TEXT NOT NULL,
    source             TEXT NOT NULL,
    collection         TEXT NOT NULL,
    workspace          TEXT NOT NULL,
    embedding_provider TEXT NOT NULL,
    embedding_model    TEXT NOT NULL,
    embedding_base_url TEXT,
    llm_provider       TEXT NOT NULL,
    llm_model          TEXT NOT NULL,
    llm_base_url       TEXT,
    created_at         REAL NOT NULL,
    updated_at         REAL NOT NULL
);
"""


class KBStore:
    def __init__(self, db_path: str = SQLITE_PATH):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False：FastAPI 同步端点跑在线程池里，多线程共享连接
        # 配合 self._lock 保证写操作串行
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    def list_kbs(self) -> list[dict]:
        with self._lock:
            cur = self.conn.execute("SELECT * FROM kb_config ORDER BY created_at")
            return [dict(r) for r in cur.fetchall()]

    def get_kb(self, kb_name: str) -> Optional[dict]:
        with self._lock:
            cur = self.conn.execute(
                "SELECT * FROM kb_config WHERE kb_name = ?", [kb_name]
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def create_kb(self, kb: dict) -> dict:
        now = time.time()
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO kb_config (
                    kb_name, display_name, source, collection, workspace,
                    embedding_provider, embedding_model, embedding_base_url,
                    llm_provider, llm_model, llm_base_url,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    kb["kb_name"], kb["display_name"], kb["source"],
                    kb["collection"], kb["workspace"],
                    kb["embedding_provider"], kb["embedding_model"],
                    kb.get("embedding_base_url"),
                    kb["llm_provider"], kb["llm_model"], kb.get("llm_base_url"),
                    now, now,
                ],
            )
            self.conn.commit()
        return self.get_kb(kb["kb_name"])

    def update_kb(self, kb_name: str, kb: dict) -> Optional[dict]:
        existing = self.get_kb(kb_name)
        if not existing:
            return None
        merged = {**existing, **kb, "updated_at": time.time()}
        with self._lock:
            self.conn.execute(
                """
                UPDATE kb_config SET
                    display_name = ?, source = ?, collection = ?, workspace = ?,
                    embedding_provider = ?, embedding_model = ?, embedding_base_url = ?,
                    llm_provider = ?, llm_model = ?, llm_base_url = ?,
                    updated_at = ?
                WHERE kb_name = ?
                """,
                [
                    merged["display_name"], merged["source"], merged["collection"],
                    merged["workspace"],
                    merged["embedding_provider"], merged["embedding_model"],
                    merged.get("embedding_base_url"),
                    merged["llm_provider"], merged["llm_model"],
                    merged.get("llm_base_url"),
                    merged["updated_at"], kb_name,
                ],
            )
            self.conn.commit()
        return self.get_kb(kb_name)

    def delete_kb(self, kb_name: str) -> bool:
        with self._lock:
            cur = self.conn.execute(
                "DELETE FROM kb_config WHERE kb_name = ?", [kb_name]
            )
            self.conn.commit()
            return cur.rowcount > 0

    def close(self):
        with self._lock:
            self.conn.close()
