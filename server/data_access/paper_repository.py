import json
from typing import Dict, Iterable, List, Optional

from storage.sqlite.database import get_connection


def ensure_papers_table() -> None:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS papers (
                paper_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                abstract TEXT,
                authors_json TEXT,
                publication_year INTEGER,
                publication_date TEXT,
                url TEXT,
                pdf_url TEXT,
                source TEXT,
                cited_by_count INTEGER DEFAULT 0,
                raw_json TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_fulltext (
                paper_id TEXT PRIMARY KEY,
                plain_text TEXT,
                sections_json TEXT,
                tables_json TEXT,
                metadata_json TEXT,
                structured_sections_json TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(publication_year)")
        conn.commit()


class PaperRepository:
    def __init__(self) -> None:
        ensure_papers_table()

    def upsert_many(self, papers: Iterable[Dict]) -> None:
        rows: List[tuple] = []
        for paper in papers:
            paper_id = paper.get("id") or paper.get("paper_id")
            if not paper_id:
                continue
            title = (paper.get("title") or paper.get("display_name") or "").strip()
            abstract = paper.get("summary") or paper.get("abstract")
            authors = paper.get("authors") or []
            publication_date = paper.get("publication_date") or ""
            publication_year: Optional[int] = None
            if isinstance(paper.get("publication_year"), int):
                publication_year = paper.get("publication_year")
            elif publication_date:
                try:
                    publication_year = int(str(publication_date)[:4])
                except ValueError:
                    publication_year = None
            rows.append(
                (
                    paper_id,
                    title,
                    abstract,
                    json.dumps(authors, ensure_ascii=False),
                    publication_year,
                    publication_date,
                    paper.get("link") or paper.get("url") or "",
                    paper.get("pdf_url") or "",
                    paper.get("source") or "",
                    int(paper.get("cited_by_count") or 0),
                    json.dumps(paper, ensure_ascii=False),
                )
            )

        if not rows:
            return

        with get_connection() as conn:
            cur = conn.cursor()
            cur.executemany(
                """
                INSERT INTO papers (
                    paper_id, title, abstract, authors_json, publication_year,
                    publication_date, url, pdf_url, source, cited_by_count, raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(paper_id) DO UPDATE SET
                    title = excluded.title,
                    abstract = excluded.abstract,
                    authors_json = excluded.authors_json,
                    publication_year = excluded.publication_year,
                    publication_date = excluded.publication_date,
                    url = excluded.url,
                    pdf_url = excluded.pdf_url,
                    source = excluded.source,
                    cited_by_count = excluded.cited_by_count,
                    raw_json = excluded.raw_json
                """,
                rows,
            )
            conn.commit()

    def fetch_many(self, paper_ids: Iterable[str]) -> List[Dict]:
        ids = [pid for pid in set(paper_ids) if pid]
        if not ids:
            return []

        placeholders = ",".join("?" for _ in ids)
        with get_connection() as conn:
            conn.row_factory = lambda cursor, row: {col[0]: row[idx] for idx, col in enumerate(cursor.description)}
            cur = conn.cursor()
            cur.execute(
                f"SELECT * FROM papers WHERE paper_id IN ({placeholders})",
                ids,
            )
            rows = []
            for record in cur.fetchall():
                authors_json = record.get("authors_json")
                if authors_json:
                    try:
                        record["authors"] = json.loads(authors_json)
                    except json.JSONDecodeError:
                        record["authors"] = []
                else:
                    record["authors"] = []
                rows.append(record)
        fulltext_map = self.fetch_fulltext_map(ids)
        for record in rows:
            payload = fulltext_map.get(record["paper_id"])
            if payload:
                record["full_text"] = payload.get("plain_text", "")
                record["sections"] = payload.get("sections", [])
                record["tables"] = payload.get("tables", [])
                record["fulltext_metadata"] = payload.get("metadata", {})
        return rows

    def upsert_fulltext(self, paper_id: str, payload: Dict[str, object]) -> None:
        if not paper_id:
            return
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO paper_fulltext (paper_id, plain_text, sections_json, tables_json, metadata_json, structured_sections_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(paper_id) DO UPDATE SET
                    plain_text = excluded.plain_text,
                    sections_json = excluded.sections_json,
                    tables_json = excluded.tables_json,
                    metadata_json = excluded.metadata_json,
                    structured_sections_json = excluded.structured_sections_json,
                    updated_at = datetime('now')
                """,
                (
                    paper_id,
                    payload.get("plain_text"),
                    json.dumps(payload.get("sections") or [], ensure_ascii=False),
                    json.dumps(payload.get("tables") or [], ensure_ascii=False),
                    json.dumps(payload.get("metadata") or {}, ensure_ascii=False),
                    json.dumps(payload.get("structured_sections") or {}, ensure_ascii=False),
                ),
            )
            conn.commit()

    def fetch_fulltext_map(self, paper_ids: Iterable[str]) -> Dict[str, Dict[str, object]]:
        ids = [pid for pid in set(paper_ids) if pid]
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        with get_connection() as conn:
            conn.row_factory = lambda cursor, row: {col[0]: row[idx] for idx, col in enumerate(cursor.description)}
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT paper_id, plain_text, sections_json, tables_json, metadata_json, structured_sections_json
                FROM paper_fulltext
                WHERE paper_id IN ({placeholders})
                """,
                ids,
            )
            rows = cur.fetchall()
        result: Dict[str, Dict[str, object]] = {}
        for record in rows:
            sections = []
            tables = []
            metadata = {}
            structured = {}
            if record.get("sections_json"):
                try:
                    sections = json.loads(record["sections_json"])
                except json.JSONDecodeError:
                    sections = []
            if record.get("tables_json"):
                try:
                    tables = json.loads(record["tables_json"])
                except json.JSONDecodeError:
                    tables = []
            if record.get("metadata_json"):
                try:
                    metadata = json.loads(record["metadata_json"])
                except json.JSONDecodeError:
                    metadata = {}
            if record.get("structured_sections_json"):
                try:
                    structured = json.loads(record["structured_sections_json"])
                except json.JSONDecodeError:
                    structured = {}
            result[record["paper_id"]] = {
                "plain_text": record.get("plain_text") or "",
                "sections": sections,
                "tables": tables,
                "metadata": metadata,
                "structured_sections": structured,
            }
        return result
