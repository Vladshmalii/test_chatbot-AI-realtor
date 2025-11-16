from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    telegram_token: str = Field(alias="TELEGRAM_TOKEN")
    database_url: str = Field(alias="DATABASE_URL")
    google_spreadsheet_id: str = Field(alias="GOOGLE_SPREADSHEET_ID")
    google_service_account_file: str = Field(alias="GOOGLE_SERVICE_ACCOUNT_FILE")
    listings_api_url: str = Field(alias="LISTINGS_API_URL")
    listings_media_base: str = Field(alias="LISTINGS_MEDIA_BASE")
    listings_api_key: str = Field(alias="LISTINGS_API_KEY")
    listings_limit: int = Field(3, alias="LISTINGS_LIMIT")
    listings_offset: int = Field(0, alias="LISTINGS_OFFSET")
    sheets_cache_ttl: int = Field(300, alias="SHEETS_CACHE_TTL")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


settings = Settings()
