from server.data_access.paper_repository import PaperRepository
from server.services.docling_service import DoclingIngestionService, is_probably_pdf_url


class _FakeBlock:
    def __init__(self, text: str):
        self.text = text


class _FakePage:
    def __init__(self, blocks):
        self.blocks = blocks


class _FakeDoc:
    def __init__(self, *, with_sections: bool = True, with_blocks: bool = False):
        self.plain_text = ""
        self.sections = (
            [{"title": "Intro", "text": "hello world"}]
            if with_sections
            else []
        )
        self.tables = []
        self.metadata = {"title": "Demo"}
        self.pages = [
            _FakePage([_FakeBlock("block-one"), _FakeBlock("block-two")]) if with_blocks else _FakePage([])
        ]


class _FakeConversion:
    def __init__(self, *, with_sections: bool = True, with_blocks: bool = False):
        self.document = _FakeDoc(with_sections=with_sections, with_blocks=with_blocks)
        self.documents = [self.document]


class _FakeConverter:
    def __init__(self, *, with_sections: bool = True, with_blocks: bool = False):
        self._with_sections = with_sections
        self._with_blocks = with_blocks

    def convert(self, path: str):
        return _FakeConversion(with_sections=self._with_sections, with_blocks=self._with_blocks)


def test_docling_service_ingests_pdf_into_repository(temp_db):
    repo = PaperRepository()
    service = DoclingIngestionService(
        paper_repository=repo,
        converter=_FakeConverter(),
        downloader=lambda url: b"%PDF-1.4 fake",
    )
    service.ingest_pdf_now("paper-123", "https://example.com/demo.pdf")

    stored = repo.fetch_fulltext_map(["paper-123"])
    payload = stored["paper-123"]
    assert payload["plain_text"] == "hello world"
    assert payload["sections"][0]["title"] == "Intro"


def test_docling_ingests_from_cached_file(temp_db, tmp_path):
    pdf_path = tmp_path / "demo.pdf"
    pdf_path.write_bytes(b"fake")
    repo = PaperRepository()
    service = DoclingIngestionService(
        paper_repository=repo,
        converter=_FakeConverter(),
    )
    service.ingest_pdf_now("paper-file", file_path=str(pdf_path))

    stored = repo.fetch_fulltext_map(["paper-file"])
    assert stored["paper-file"]["plain_text"] == "hello world"


def test_docling_block_fallback(temp_db, tmp_path):
    pdf_path = tmp_path / "demo.pdf"
    pdf_path.write_bytes(b"fake")
    repo = PaperRepository()
    service = DoclingIngestionService(
        paper_repository=repo,
        converter=_FakeConverter(with_sections=False, with_blocks=True),
    )
    service.ingest_pdf_now("paper-block", file_path=str(pdf_path))

    stored = repo.fetch_fulltext_map(["paper-block"])
    assert "block-one" in stored["paper-block"]["plain_text"]


def test_paper_repository_fetch_many_includes_fulltext(temp_db):
    repo = PaperRepository()
    repo.upsert_many(
        [
            {
                "id": "paper-xyz",
                "title": "Demo",
                "summary": "short abstract",
                "authors": ["Alice"],
                "publication_year": 2024,
                "publication_date": "2024-01-01",
                "link": "https://example.com/paper",
                "pdf_url": "https://example.com/paper.pdf",
                "source": "arXiv",
                "cited_by_count": 10,
            }
        ]
    )
    repo.upsert_fulltext(
        "paper-xyz",
        {
            "plain_text": "Full article text",
            "sections": [{"title": "Background"}],
            "tables": [],
            "metadata": {"doc": "meta"},
        },
    )

    rows = repo.fetch_many(["paper-xyz"])
    assert rows[0]["full_text"] == "Full article text"
    assert rows[0]["sections"][0]["title"] == "Background"
    assert rows[0]["fulltext_metadata"]["doc"] == "meta"


def test_is_probably_pdf_url_checks_format():
    assert is_probably_pdf_url("https://arxiv.org/pdf/1234.5678.pdf")
    assert is_probably_pdf_url("https://arxiv.org/pdf/1234.5678")
    assert not is_probably_pdf_url("https://openalex.org/W12345")
    assert not is_probably_pdf_url("ftp://example.com/file.pdf")
