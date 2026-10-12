"""Application settings, loaded from environment variables / .env.

See apps/api/.env.example for the full list of variables and their defaults.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    environment: str = "development"
    # The frontend's origin(s) allowed to call this API with credentials (cookies).
    # "*" doesn't work with allow_credentials=True, so this must be an explicit list.
    cors_origins: list[str] = ["http://localhost:3000"]

    database_url: str = (
        "postgresql+psycopg://ifc_ibis:ifc_ibis_dev@localhost:5432/ifc_ibis"
    )
    redis_url: str = "redis://localhost:6379/0"

    s3_endpoint_url: str = "http://localhost:3900"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "ifc-uploads"
    s3_region: str = "garage"

    jwt_secret: str = "change-me-in-every-environment-min-32-bytes"
    jwt_expires_minutes: int = 60

    llm_api_key: str = ""
    jev_api_url: str = ""
    jev_api_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
