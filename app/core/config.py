from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = Field(
        default="development",
        validation_alias=AliasChoices("APP_ENV", "app_env"),
    )
    bot_token: str = Field(
        ..., validation_alias=AliasChoices("BOT_TOKEN", "bot_token")
    )
    database_url: str = Field(
        ..., validation_alias=AliasChoices("DATABASE_URL", "database_url")
    )
    timezone: str = Field(
        default="Asia/Almaty",
        validation_alias=AliasChoices("TZ", "timezone"),
    )
    ilya_telegram_id: int | None = Field(
        default=None,
        validation_alias=AliasChoices("ILYA_TELEGRAM_ID", "ilya_telegram_id"),
    )
    asan_telegram_id: int | None = Field(
        default=None,
        validation_alias=AliasChoices("ASAN_TELEGRAM_ID", "asan_telegram_id"),
    )
    alisher_telegram_id: int | None = Field(
        default=None,
        validation_alias=AliasChoices("ALISHER_TELEGRAM_ID", "alisher_telegram_id"),
    )
    ilya_full_name: str = Field(
        default="Илья",
        validation_alias=AliasChoices("ILYA_FULL_NAME", "ilya_full_name"),
    )
    asan_full_name: str = Field(
        default="Асан",
        validation_alias=AliasChoices("ASAN_FULL_NAME", "asan_full_name"),
    )
    alisher_full_name: str = Field(
        default="Alisher",
        validation_alias=AliasChoices("ALISHER_FULL_NAME", "alisher_full_name"),
    )

    model_config = SettingsConfigDict(
        env_file=None,
        extra="ignore",
        case_sensitive=False,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
