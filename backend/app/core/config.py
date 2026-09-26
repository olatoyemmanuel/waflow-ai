from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "WAFlow AI"
    app_env: str = "development"
    debug: bool = True

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    database_url: str
    redis_url: str

    jwt_secret: str
    jwt_refresh_secret: str
    access_token_expire_minutes: int = 15

    openai_api_key: str = ""

    whatsapp_access_token: str = ""
    whatsapp_verify_token: str = ""
    whatsapp_app_secret: str = ""

    paystack_secret_key: str = ""
    paystack_public_key: str = ""

    storage_endpoint: str = ""
    storage_access_key: str = ""
    storage_secret_key: str = ""
    storage_bucket: str = "waflow"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
