import json
from typing import Dict, Iterable, List, Optional

from storage.sqlite.database import get_connection


def ensure_conversation_tables() -> None:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_sessions (
                session_id TEXT PRIMARY KEY,
                history_id INTEGER NOT NULL,
                user_id INTEGER,
                last_selected_json TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata_json TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (session_id) REFERENCES conversation_sessions(session_id) ON DELETE CASCADE
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversation_messages_session ON conversation_messages(session_id, created_at)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversation_sessions_history ON conversation_sessions(history_id)"
        )
        conn.commit()


class ConversationRepository:
    def __init__(self) -> None:
        ensure_conversation_tables()

    def upsert_session(self, session_id: str, *, history_id: int, user_id: Optional[int], selected_ids: Optional[Iterable[str]] = None) -> None:
        selected_json = json.dumps(list(selected_ids) if selected_ids is not None else None, ensure_ascii=False)
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO conversation_sessions (session_id, history_id, user_id, last_selected_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    history_id = excluded.history_id,
                    user_id = excluded.user_id,
                    last_selected_json = excluded.last_selected_json,
                    updated_at = datetime('now')
                """,
                (session_id, history_id, user_id, selected_json),
            )
            conn.commit()

    def get_session(self, session_id: str) -> Optional[Dict]:
        with get_connection() as conn:
            conn.row_factory = lambda cursor, row: {col[0]: row[idx] for idx, col in enumerate(cursor.description)}
            cur = conn.cursor()
            cur.execute(
                """
                SELECT session_id, history_id, user_id, last_selected_json, created_at, updated_at
                FROM conversation_sessions
                WHERE session_id = ?
                """,
                (session_id,),
            )
            record = cur.fetchone()
        if not record:
            return None
        record["selected_ids"] = self._parse_selected(record.pop("last_selected_json", None))
        return record

    def find_latest_session_for_history(self, history_id: int, user_id: Optional[int]) -> Optional[Dict]:
        with get_connection() as conn:
            conn.row_factory = lambda cursor, row: {col[0]: row[idx] for idx, col in enumerate(cursor.description)}
            cur = conn.cursor()
            cur.execute(
                """
                SELECT session_id, history_id, user_id, last_selected_json, created_at, updated_at
                FROM conversation_sessions
                WHERE history_id = ? AND (user_id IS NULL OR user_id = ?)
                ORDER BY datetime(updated_at) DESC
                LIMIT 1
                """,
                (history_id, user_id),
            )
            record = cur.fetchone()
        if not record:
            return None
        record["selected_ids"] = self._parse_selected(record.pop("last_selected_json", None))
        return record

    def append_messages(self, session_id: str, entries: Iterable[Dict]) -> None:
        rows: List[tuple] = []
        for entry in entries:
            role = entry.get("role")
            content = entry.get("content")
            if not role or content is None:
                continue
            metadata = entry.get("metadata")
            rows.append(
                (
                    session_id,
                    role,
                    str(content),
                    json.dumps(metadata, ensure_ascii=False) if metadata is not None else None,
                )
            )
        if not rows:
            return
        with get_connection() as conn:
            cur = conn.cursor()
            cur.executemany(
                """
                INSERT INTO conversation_messages (session_id, role, content, metadata_json)
                VALUES (?, ?, ?, ?)
                """,
                rows,
            )
            cur.execute(
                "UPDATE conversation_sessions SET updated_at = datetime('now') WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()

    def list_messages(self, session_id: str) -> List[Dict]:
        with get_connection() as conn:
            conn.row_factory = lambda cursor, row: {col[0]: row[idx] for idx, col in enumerate(cursor.description)}
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, session_id, role, content, metadata_json, created_at
                FROM conversation_messages
                WHERE session_id = ?
                ORDER BY datetime(created_at) ASC, id ASC
                """,
                (session_id,),
            )
            rows = cur.fetchall()
        for row in rows:
            metadata_json = row.pop("metadata_json", None)
            if metadata_json:
                try:
                    row["metadata"] = json.loads(metadata_json)
                except json.JSONDecodeError:
                    row["metadata"] = {}
            else:
                row["metadata"] = {}
        return rows

    @staticmethod
    def _parse_selected(value: Optional[str]) -> Optional[List[str]]:
        if not value:
            return None
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
        return None
