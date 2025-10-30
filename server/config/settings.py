from dataclasses import asdict, dataclass
from typing import Dict


@dataclass
class BaseConfig:
    DEBUG: bool = False
    TESTING: bool = False
    SECRET_KEY: str = "change-me"
    DATABASE_URL: str = "sqlite:///storage/sqlite/research.db"
    VECTOR_STORE_PATH: str = "storage/vector_store"
    LLM_MODEL: str = "gemini-pro"
    ARXIV_API_URL: str = "https://export.arxiv.org/api/query"
    CORS_ORIGINS: str = "http://localhost:5173"

    JWT_EXPIRE_HOURS: int = 2
    AI_DEFAULT_LANGUAGE: str = "en"
    AI_MAX_SUMMARY_ITEMS: int = 12
    AI_MAX_KEYWORD_TERMS: int = 10


@dataclass
class DevelopmentConfig(BaseConfig):
    DEBUG: bool = True


@dataclass
class TestingConfig(BaseConfig):
    TESTING: bool = True
    DATABASE_URL: str = "sqlite:///:memory:"


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": BaseConfig
}


def load_config(name: str) -> Dict[str, object]:
    # TODO: Merge environment variables or external config service overrides
    config_class = CONFIG_MAP.get(name, BaseConfig)
    return asdict(config_class())
