"""Application settings, loaded from the environment (and an optional .env file)."""

from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Database -----------------------------------------------------------
    # A full SQLAlchemy URL wins; otherwise one is assembled from the parts below
    # so that plain MYSQL_* variables (what most hosts hand you) are enough.
    database_url: str | None = None

    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_database: str = "seatbooking"

    # --- HTTP ---------------------------------------------------------------
    # Comma-separated list of origins allowed to call the API from a browser.
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # --- Behaviour ----------------------------------------------------------
    # Guard rails on event creation so a typo cannot ask for a million seats.
    max_rows_per_event: int = Field(default=50, ge=1)
    max_columns_per_event: int = Field(default=60, ge=1)
    max_seats_per_event: int = Field(default=2000, ge=1)
    max_seats_per_booking: int = Field(default=10, ge=1)

    # Create tables on startup. Handy for demos; use schema.sql in production.
    auto_create_tables: bool = True

    # Log a fake "confirmation email" after a successful booking.
    mock_email_enabled: bool = True

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"mysql+pymysql://{quote_plus(self.mysql_user)}:{quote_plus(self.mysql_password)}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            "?charset=utf8mb4"
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
