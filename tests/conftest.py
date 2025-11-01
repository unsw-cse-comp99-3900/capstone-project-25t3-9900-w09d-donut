import os
import sys

import pytest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from storage.sqlite import database

os.environ.setdefault("GEMINI_API_KEY", "test-key")


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_research.db"
    monkeypatch.setattr(database, "DB_PATH", db_path)
    return db_path
