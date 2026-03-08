"""Application settings loaded from environment variables.

Uses pydantic-settings for validation and .env file support.
All production secrets are environment-variable-only; never in config.yaml.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Environment ──────────────────────────────────────────────────────────
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://aiblock:aiblock@localhost:5432/aiblock",
        description="Async SQLAlchemy URL (asyncpg driver required).",
    )

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis URL used for caching and Celery broker.",
    )

    # ── S3 / Object storage ───────────────────────────────────────────────────
    s3_bucket: str = "aiblock-audio"
    s3_region: str = "us-east-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    s3_endpoint_url: str = ""  # Leave empty for AWS; set for MinIO / Cloudflare R2

    # ── Stripe ────────────────────────────────────────────────────────────────
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_pro_price_id: str = ""        # monthly Pro plan price ID
    stripe_enterprise_price_id: str = "" # Enterprise price ID

    # ── API ───────────────────────────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: list[str] = ["*"]

    # ── Celery ────────────────────────────────────────────────────────────────
    celery_broker_url: str = ""   # defaults to redis_url
    celery_result_backend: str = ""  # defaults to redis_url

    def celery_broker(self) -> str:
        return self.celery_broker_url or self.redis_url

    def celery_backend(self) -> str:
        return self.celery_result_backend or self.redis_url

    # ── Detection defaults ────────────────────────────────────────────────────
    default_config_path: str = "config.yaml"
    job_ttl_seconds: int = 3600        # how long to keep job results in Redis
    cache_result_ttl_seconds: int = 86400  # 24 h — cache identical URL+model combos


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
