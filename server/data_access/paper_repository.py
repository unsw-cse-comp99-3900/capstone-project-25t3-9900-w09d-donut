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
        return rows
