from functools import lru_cache
from pydantic import BaseSettings, Field

class Settings(BaseSettings):
    telegram_token: str = Field(..., alias="TELEGRAM_TOKEN")
    telegram_webhook_url: str = Field(..., alias="TELEGRAM_WEBHOOK_URL")
    telegram_webhook_path: str = Field("/webhook", alias="TELEGRAM_WEBHOOK_PATH")
    database_url: str = Field(..., alias="DATABASE_URL")
    google_spreadsheet_id: str = Field(..., alias="GOOGLE_SPREADSHEET_ID")
    google_service_account_json: str = Field(..., alias="GOOGLE_SERVICE_ACCOUNT_JSON")
    listings_api_url: str = Field("https://bots2.tira.com.ua:8443/api/get_apartments", alias="LISTINGS_API_URL")
    listings_api_key: str = Field("tsj3HsMqL136cMxhf5zwcFdniz7a", alias="LISTINGS_API_KEY")
    listings_limit: int = Field(3, alias="LISTINGS_LIMIT")
    default_offset: int = Field(0, alias="LISTINGS_OFFSET")
    cache_ttl_seconds: int = Field(300, alias="SHEETS_CACHE_TTL")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
