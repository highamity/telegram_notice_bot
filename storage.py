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
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS notices (
                        chat_id INTEGER NOT NULL,
                        key TEXT NOT NULL,
                        value TEXT NOT NULL,
                        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                        PRIMARY KEY (chat_id, key)
                    );
                    CREATE TABLE IF NOT EXISTS schedules (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        chat_id INTEGER NOT NULL,
                        remind_at TEXT NOT NULL,
                        content TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        created_at TEXT NOT NULL DEFAULT (datetime('now'))
                    );
                    CREATE INDEX IF NOT EXISTS idx_schedules_pending 
                    ON schedules (status, remind_at);

                    CREATE TABLE IF NOT EXISTS ddays (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        chat_id INTEGER NOT NULL,
                        name TEXT NOT NULL,
                        target_date TEXT NOT NULL,
                        repeat_yearly INTEGER NOT NULL DEFAULT 0,
                        last_notified_year INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL DEFAULT (datetime('now')),
                        UNIQUE(chat_id, name)
                    );
                    CREATE INDEX IF NOT EXISTS idx_ddays_chat 
                    ON ddays (chat_id, name);
                    """
                )
                try:
                    conn.execute("ALTER TABLE ddays ADD COLUMN repeat_yearly INTEGER NOT NULL DEFAULT 0")
                except Exception:
                    pass
                try:
                    conn.execute("ALTER TABLE ddays ADD COLUMN last_notified_year INTEGER NOT NULL DEFAULT 0")
                except Exception:
                    pass
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

    # --- Schedules ---

    async def add_schedule(self, chat_id: int, remind_at: str, content: str) -> int:
        return await asyncio.to_thread(self._add_schedule_sync, chat_id, remind_at, content)

    def _add_schedule_sync(self, chat_id: int, remind_at: str, content: str) -> int:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    """
                    INSERT INTO schedules (chat_id, remind_at, content, status, created_at)
                    VALUES (?, ?, ?, 'pending', datetime('now'))
                    """,
                    (chat_id, remind_at, content),
                )
                conn.commit()
                return int(cur.lastrowid)
            finally:
                conn.close()

    async def list_upcoming_schedules(self, chat_id: int, limit: int = 20) -> list[dict]:
        return await asyncio.to_thread(self._list_upcoming_schedules_sync, chat_id, limit)

    def _list_upcoming_schedules_sync(self, chat_id: int, limit: int) -> list[dict]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """
                    SELECT id, remind_at, content, status
                    FROM schedules
                    WHERE chat_id = ? AND status = 'pending'
                    ORDER BY remind_at ASC
                    LIMIT ?
                    """,
                    (chat_id, limit),
                ).fetchall()
                return [
                    {
                        "id": int(r["id"]),
                        "remind_at": str(r["remind_at"]),
                        "content": str(r["content"]),
                        "status": str(r["status"]),
                    }
                    for r in rows
                ]
            finally:
                conn.close()

    async def delete_schedule(self, chat_id: int, schedule_id: int) -> bool:
        return await asyncio.to_thread(self._delete_schedule_sync, chat_id, schedule_id)

    def _delete_schedule_sync(self, chat_id: int, schedule_id: int) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "DELETE FROM schedules WHERE chat_id = ? AND id = ?",
                    (chat_id, schedule_id),
                )
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    async def pop_due_schedules(self, now_iso: str) -> list[dict]:
        return await asyncio.to_thread(self._pop_due_schedules_sync, now_iso)

    def _pop_due_schedules_sync(self, now_iso: str) -> list[dict]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """
                    SELECT id, chat_id, remind_at, content
                    FROM schedules
                    WHERE status = 'pending' AND remind_at <= ?
                    ORDER BY remind_at ASC
                    """,
                    (now_iso,),
                ).fetchall()
                if not rows:
                    return []
                due = [
                    {
                        "id": int(r["id"]),
                        "chat_id": int(r["chat_id"]),
                        "remind_at": str(r["remind_at"]),
                        "content": str(r["content"]),
                    }
                    for r in rows
                ]
                ids = [d["id"] for d in due]
                placeholders = ",".join("?" * len(ids))
                conn.execute(
                    f"UPDATE schedules SET status = 'sent' WHERE id IN ({placeholders})",
                    ids,
                )
                conn.commit()
                return due
            finally:
                conn.close()

    # --- D-Days ---

    async def put_dday(self, chat_id: int, name: str, target_date: str, repeat_yearly: int = 0) -> None:
        await asyncio.to_thread(self._put_dday_sync, chat_id, name, target_date, repeat_yearly)

    def _put_dday_sync(self, chat_id: int, name: str, target_date: str, repeat_yearly: int = 0) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO ddays (chat_id, name, target_date, repeat_yearly, last_notified_year, created_at)
                    VALUES (?, ?, ?, ?, 0, datetime('now'))
                    ON CONFLICT(chat_id, name) DO UPDATE SET
                        target_date = excluded.target_date,
                        repeat_yearly = excluded.repeat_yearly,
                        last_notified_year = 0,
                        created_at = datetime('now')
                    """,
                    (chat_id, name, target_date, repeat_yearly),
                )
                conn.commit()
            finally:
                conn.close()

    async def get_dday(self, chat_id: int, name: str) -> dict | None:
        return await asyncio.to_thread(self._get_dday_sync, chat_id, name)

    def _get_dday_sync(self, chat_id: int, name: str) -> dict | None:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT id, name, target_date, repeat_yearly, last_notified_year FROM ddays WHERE chat_id = ? AND name = ?",
                    (chat_id, name),
                ).fetchone()
                if not row:
                    return None
                return {
                    "id": int(row["id"]),
                    "name": str(row["name"]),
                    "target_date": str(row["target_date"]),
                    "repeat_yearly": int(row["repeat_yearly"]),
                    "last_notified_year": int(row["last_notified_year"]),
                }
            finally:
                conn.close()

    async def list_ddays(self, chat_id: int) -> list[dict]:
        return await asyncio.to_thread(self._list_ddays_sync, chat_id)

    def _list_ddays_sync(self, chat_id: int) -> list[dict]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT id, name, target_date, repeat_yearly, last_notified_year FROM ddays WHERE chat_id = ? ORDER BY target_date ASC, name ASC",
                    (chat_id,),
                ).fetchall()
                return [
                    {
                        "id": int(r["id"]),
                        "name": str(r["name"]),
                        "target_date": str(r["target_date"]),
                        "repeat_yearly": int(r["repeat_yearly"]),
                        "last_notified_year": int(r["last_notified_year"]),
                    }
                    for r in rows
                ]
            finally:
                conn.close()

    async def delete_dday(self, chat_id: int, name: str) -> bool:
        return await asyncio.to_thread(self._delete_dday_sync, chat_id, name)

    def _delete_dday_sync(self, chat_id: int, name: str) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "DELETE FROM ddays WHERE chat_id = ? AND name = ?",
                    (chat_id, name),
                )
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    async def pop_due_ddays(self, today_date: str, current_year: int) -> list[dict]:
        return await asyncio.to_thread(self._pop_due_ddays_sync, today_date, current_year)

    def _pop_due_ddays_sync(self, today_date: str, current_year: int) -> list[dict]:
        with self._lock:
            conn = self._connect()
            try:
                month_day = today_date[5:]  # "MM-DD"
                rows = conn.execute(
                    """
                    SELECT id, chat_id, name, target_date, repeat_yearly, last_notified_year
                    FROM ddays
                    WHERE last_notified_year < ?
                      AND (
                        (repeat_yearly = 1 AND substr(target_date, 6, 5) = ?)
                        OR
                        (repeat_yearly = 0 AND target_date = ?)
                      )
                    ORDER BY id ASC
                    """,
                    (current_year, month_day, today_date),
                ).fetchall()
                if not rows:
                    return []
                due = [
                    {
                        "id": int(r["id"]),
                        "chat_id": int(r["chat_id"]),
                        "name": str(r["name"]),
                        "target_date": str(r["target_date"]),
                        "repeat_yearly": int(r["repeat_yearly"]),
                        "last_notified_year": int(r["last_notified_year"]),
                    }
                    for r in rows
                ]
                ids = [d["id"] for d in due]
                placeholders = ",".join("?" * len(ids))
                conn.execute(
                    f"UPDATE ddays SET last_notified_year = ? WHERE id IN ({placeholders})",
                    [current_year] + ids,
                )
                conn.commit()
                return due
            finally:
                conn.close()

