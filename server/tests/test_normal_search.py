import json
import os

import pytest

from server import create_app

@pytest.fixture(scope="module")
def client():
    app = create_app("development")
    app.testing = True
    with app.test_client() as c:
        yield c

@pytest.mark.skipif(
    os.environ.get("ENABLE_ONLINE_OPENALEX") != "1",
    reason="OpenAlex integration test requires external network; set ENABLE_ONLINE_OPENALEX=1 to enable.",
)
def test_normal_search_openalex_example(client):
    """
    Integration test against OpenAlex:
    results = search_openalex_papers(
        keywords=["large language model", "transformer"],
        date_range=("2024-01-01", "2025-01-01"),
        concepts=["C41008148"],  # NLP
        limit=30
    )
    """
    payload = {
        "keywords": ["large language model", "transformer"],
        "date_range": ["2024-01-01", "2025-01-01"],
        "concepts": ["C41008148"],
        "limit": 30,
    }
    resp = client.post("/api/normal_search", data=json.dumps(payload), content_type="application/json")
    # Basic status check; network errors should surface clearly
    assert resp.status_code == 200, f"unexpected status: {resp.status_code}, body={resp.get_data(as_text=True)}"

    data = resp.get_json() or {}
    assert "results" in data and isinstance(data["results"], list), "results should be a list"
    # At least one result expected under normal network conditions; if flaky APIs, this may need relaxation
    assert len(data["results"]) > 0, "expected at least one result"

    first = data["results"][0]
    # Schema sanity checks
    for key in ["id", "title", "authors", "publication_date", "pdf_url", "link", "cited_by_count"]:
        assert key in first, f"missing key '{key}' in first result"
    assert isinstance(first["authors"], list)
    assert isinstance(first["cited_by_count"], int)
