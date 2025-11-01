import json
from typing import Dict, Iterable, List, Optional, Sequence

from storage.sqlite.database import get_connection


def ensure_search_history_tables() -> None:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                query TEXT,
                filters_json TEXT,
                result_count INTEGER DEFAULT 0,
                session_id TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS search_history_items (
                search_id INTEGER NOT NULL,
                paper_id TEXT NOT NULL,
                rank INTEGER,
                selected INTEGER DEFAULT 1,
                note TEXT,
                PRIMARY KEY (search_id, paper_id),
                FOREIGN KEY (search_id) REFERENCES search_history(id) ON DELETE CASCADE
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_history_user ON search_history(user_id, created_at DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_history_items_search ON search_history_items(search_id, rank)")
        conn.commit()


class SearchHistoryRepository:
    def __init__(self) -> None:
        ensure_search_history_tables()

    def create_history(
        self,
        *,
        user_id: Optional[int],
        query: str,
        filters: Optional[Dict],
        papers: Sequence[Dict],
        session_id: Optional[str] = None,
    ) -> int:
        filters_json = json.dumps(filters or {}, ensure_ascii=False)

        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO search_history (user_id, query, filters_json, result_count, session_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, query, filters_json, len(papers), session_id),
            )
            history_id = cur.lastrowid

            if papers:
                items = [
                    (
                        history_id,
                        paper.get("id") or paper.get("paper_id"),
                        idx,
                        1,
                        None,
                    )
                    for idx, paper in enumerate(papers, start=1)
                    if paper.get("id") or paper.get("paper_id")
                ]
                cur.executemany(
                    """
                    INSERT INTO search_history_items (search_id, paper_id, rank, selected, note)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    items,
                )
            conn.commit()
        return int(history_id)

    def list_by_user(self, user_id: int, limit: int = 20, offset: int = 0) -> List[Dict]:
        with get_connection() as conn:
            conn.row_factory = lambda cursor, row: {col[0]: row[idx] for idx, col in enumerate(cursor.description)}
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, query, filters_json, result_count, session_id, created_at
                FROM search_history
                WHERE user_id = ?
                ORDER BY datetime(created_at) DESC
                LIMIT ? OFFSET ?
                """,
                (user_id, limit, offset),
            )
            rows = cur.fetchall()
        for row in rows:
            try:
                row["filters"] = json.loads(row.get("filters_json") or "{}")
            except json.JSONDecodeError:
                row["filters"] = {}
        return rows

    def get_history_with_papers(self, history_id: int) -> Optional[Dict]:
        with get_connection() as conn:
            conn.row_factory = lambda cursor, row: {col[0]: row[idx] for idx, col in enumerate(cursor.description)}
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, user_id, query, filters_json, result_count, session_id, created_at
                FROM search_history
                WHERE id = ?
                """,
                (history_id,),
            )
            header = cur.fetchone()
            if not header:
                return None
            cur.execute(
                """
                SELECT i.paper_id,
                       i.rank,
                       i.selected,
                       i.note,
                       p.title,
                       p.abstract,
                       p.authors_json,
                       p.publication_year,
                       p.publication_date,
                       p.url,
                       p.pdf_url,
                       p.source,
                       p.cited_by_count
                FROM search_history_items i
                LEFT JOIN papers p ON p.paper_id = i.paper_id
                WHERE i.search_id = ?
                ORDER BY i.rank
                """,
                (history_id,),
            )
            items = []
            for record in cur.fetchall():
                authors_json = record.get("authors_json")
                if authors_json:
                    try:
                        record["authors"] = json.loads(authors_json)
                    except json.JSONDecodeError:
                        record["authors"] = []
                else:
                    record["authors"] = []
                items.append(record)

        try:
            filters = json.loads(header.get("filters_json") or "{}")
        except json.JSONDecodeError:
            filters = {}

        header["filters"] = filters
        header["papers"] = items
        return header

    def update_selection(self, history_id: int, selected_ids: Iterable[str]) -> None:
        selected_list = [pid for pid in selected_ids if pid]
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE search_history_items SET selected = 0 WHERE search_id = ?",
                (history_id,),
            )
            if selected_list:
                placeholders = ",".join("?" for _ in selected_list)
                cur.execute(
                    f"""
                    UPDATE search_history_items
                    SET selected = 1
                    WHERE search_id = ? AND paper_id IN ({placeholders})
                    """,
                    (history_id, *selected_list),
                )
            conn.commit()

    def update_note(self, history_id: int, paper_id: str, note: Optional[str]) -> None:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE search_history_items
                SET note = ?
                WHERE search_id = ? AND paper_id = ?
                """,
                (note, history_id, paper_id),
            )
            conn.commit()
