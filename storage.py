"""SQLite store for per-chat notice key/value pairs."""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from pathlib import Path


class NoticeStore:
    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS notices (
                        chat_id INTEGER NOT NULL,
                        key TEXT NOT NULL,
                        value TEXT NOT NULL,
                        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                        PRIMARY KEY (chat_id, key)
                    )
                    """
                )
                conn.commit()
            finally:
                conn.close()

    async def put(self, chat_id: int, key: str, value: str) -> None:
        await asyncio.to_thread(self._put_sync, chat_id, key, value)

    def _put_sync(self, chat_id: int, key: str, value: str) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO notices (chat_id, key, value, updated_at)
                    VALUES (?, ?, ?, datetime('now'))
                    ON CONFLICT(chat_id, key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = datetime('now')
                    """,
                    (chat_id, key, value),
                )
                conn.commit()
            finally:
                conn.close()

    async def get(self, chat_id: int, key: str) -> str | None:
        return await asyncio.to_thread(self._get_sync, chat_id, key)

    def _get_sync(self, chat_id: int, key: str) -> str | None:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT value FROM notices WHERE chat_id = ? AND key = ?",
                    (chat_id, key),
                ).fetchone()
                return str(row["value"]) if row else None
            finally:
                conn.close()

    async def delete(self, chat_id: int, key: str) -> bool:
        return await asyncio.to_thread(self._delete_sync, chat_id, key)

    def _delete_sync(self, chat_id: int, key: str) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "DELETE FROM notices WHERE chat_id = ? AND key = ?",
                    (chat_id, key),
                )
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    async def list_keys(self, chat_id: int) -> list[str]:
        return await asyncio.to_thread(self._list_keys_sync, chat_id)

    def _list_keys_sync(self, chat_id: int) -> list[str]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT key FROM notices WHERE chat_id = ? ORDER BY key COLLATE NOCASE",
                    (chat_id,),
                ).fetchall()
                return [str(r["key"]) for r in rows]
            finally:
                conn.close()
