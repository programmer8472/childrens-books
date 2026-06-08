"""Central config. Everything is env-driven; no literals scattered in code."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Database ---
    database_url: str = "postgresql+psycopg://books:books@localhost:5432/books"

    # --- Redis / Celery ---
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # --- Providers ---
    # Set to "fake" for offline dev/test; swap to real provider name in production.
    llm_provider: str = "fake"
    image_provider: str = "fake"

    # --- Storage ---
    # "local" stands in for S3 in dev. The seam stays the same when S3 lands.
    storage_backend: str = "local"
    storage_local_root: str = "./storage"


@lru_cache
def get_settings() -> Settings:
    return Settings()
