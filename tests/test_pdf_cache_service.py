from types import SimpleNamespace

from server.services.pdf_cache_service import PDFCacheService


class _FakeResponse:
    def __init__(self, content: bytes, headers=None, status_code: int = 200):
        self._content = content
        self.headers = headers or {"Content-Type": "application/pdf"}
        self.status_code = status_code

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception("http error")

    def iter_content(self, chunk_size=4096):
        yield self._content


def test_pdf_cache_service_writes_file(tmp_path, monkeypatch):
    target_dir = tmp_path / "cache"

    def fake_get(url, timeout=60, stream=True):  # pylint: disable=unused-argument
        return _FakeResponse(b"%PDF-1.4 fake")

    session = SimpleNamespace(get=fake_get)
    service = PDFCacheService(base_dir=target_dir, session=session)
    path = service.cache_pdf("paper/123", "https://example.com/demo.pdf")
    assert path is not None
    assert (target_dir / "paper123.pdf").exists()


def test_pdf_cache_service_rejects_non_pdf(tmp_path):
    target_dir = tmp_path / "cache"

    def fake_get(url, timeout=60, stream=True):  # pylint: disable=unused-argument
        return _FakeResponse(b"html", headers={"Content-Type": "text/html"})

    session = SimpleNamespace(get=fake_get)
    service = PDFCacheService(base_dir=target_dir, session=session)
    assert service.cache_pdf("paper", "https://example.com/html") is None
    assert not any(target_dir.iterdir())
