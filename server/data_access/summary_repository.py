from __future__ import annotations

from typing import Dict, List, Optional

from storage.sqlite.database import get_connection


def ensure_summary_tables() -> None:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                history_id INTEGER,
                session_id TEXT NOT NULL,
                summary_type TEXT NOT NULL,
                focus_aspect TEXT,
                summary_text TEXT NOT NULL,
                pdf_path TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_summaries_session ON conversation_summaries(session_id, created_at DESC)"
        )
        conn.commit()


class SummaryRepository:
    def __init__(self) -> None:
        ensure_summary_tables()

    def create_summary(
        self,
        *,
        history_id: Optional[int],
        session_id: str,
        summary_type: str,
        summary_text: str,
        pdf_path: str,
        focus_aspect: Optional[str] = None,
    ) -> int:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO conversation_summaries (
                    history_id, session_id, summary_type, focus_aspect, summary_text, pdf_path
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (history_id, session_id, summary_type, focus_aspect, summary_text, pdf_path),
            )
            conn.commit()
            return int(cur.lastrowid)

    def list_by_session(self, session_id: str) -> List[Dict]:
        with get_connection() as conn:
            conn.row_factory = lambda cursor, row: {col[0]: row[idx] for idx, col in enumerate(cursor.description)}
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, history_id, session_id, summary_type, focus_aspect, summary_text, pdf_path, created_at
                FROM conversation_summaries
                WHERE session_id = ?
                ORDER BY datetime(created_at) DESC
                """,
                (session_id,),
            )
            return cur.fetchall()

    def get_summary(self, summary_id: int) -> Optional[Dict]:
        with get_connection() as conn:
            conn.row_factory = lambda cursor, row: {col[0]: row[idx] for idx, col in enumerate(cursor.description)}
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, history_id, session_id, summary_type, focus_aspect, summary_text, pdf_path, created_at
                FROM conversation_summaries
                WHERE id = ?
                """,
                (summary_id,),
            )
            return cur.fetchone()
