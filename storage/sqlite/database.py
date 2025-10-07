import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path("storage/sqlite/research.db")


def init_db() -> None:
    # TODO: Implement schema migrations or integrate with SQLAlchemy ORM
    raise NotImplementedError("Database initialization not implemented")


@contextmanager
def get_connection():
    # TODO: Replace raw sqlite3 usage with ORM session management
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    try:
        yield connection
    finally:
        connection.close()
