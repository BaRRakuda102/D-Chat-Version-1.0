from __future__ import annotations

import os
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


_CSV_ENV_FIELDS = {"ALLOWED_ORIGINS", "ALLOWED_HOSTS"}


def _env_or_default(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None:
        return default
    stripped = value.strip()
    return stripped or default


class _CsvListSettingsMixin:
    def prepare_field_value(
        self,
        field_name: str,
        field: Any,
        value: Any,
        value_is_complex: bool,
    ) -> Any:
        if field_name in _CSV_ENV_FIELDS and isinstance(value, str):
            raw_value = value.strip()
            if raw_value.startswith("["):
                return super().prepare_field_value(field_name, field, value, value_is_complex)
            return [item.strip() for item in raw_value.split(",") if item.strip()]
        return super().prepare_field_value(field_name, field, value, value_is_complex)


class CsvEnvSettingsSource(_CsvListSettingsMixin, EnvSettingsSource):
    pass


class CsvDotEnvSettingsSource(_CsvListSettingsMixin, DotEnvSettingsSource):
    pass


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    APP_NAME: str = "D-Chat API"
    API_V1_PREFIX: str = "/api/v1"
    APP_VERSION: str = "1.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    DATABASE_URL: str = Field(
        default_factory=lambda: _env_or_default(
            "DATABASE_URL",
            "postgresql+asyncpg://dchat:dchat@localhost:5432/dchat",
        )
    )
    REDIS_URL: str = Field(default_factory=lambda: _env_or_default("REDIS_URL", "redis://localhost:6379/0"))

    SECRET_KEY: str = "change-me-before-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    EMAIL_VERIFICATION_EXPIRE_HOURS: int = 24
    PASSWORD_RESET_EXPIRE_MINUTES: int = 30
    ALGORITHM: str = "HS256"

    AUTH_COOKIE_NAME: str = "access_token"
    REFRESH_COOKIE_NAME: str = "refresh_token"
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"
    COOKIE_DOMAIN: str | None = None

    ALLOWED_ORIGINS: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost"]
    )
    ALLOWED_HOSTS: list[str] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "backend", "nginx"]
    )

    UPLOAD_DIR: str = "/app/uploads"
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024

    FRONTEND_URL: str = "http://localhost"
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_TLS: bool = True
    SMTP_SSL: bool = False
    SMTP_TIMEOUT_SECONDS: int = 15
    EMAIL_FROM: str | None = None
    EMAIL_FROM_NAME: str = "D-Chat"

    RATE_LIMIT_DEFAULT: str = "120/minute"
    RATE_LIMIT_AUTH: str = "10/minute"
    RATE_LIMIT_MESSAGES: str = "60/minute"
    RATE_LIMIT_PASSWORD_RESET: str = "5/hour"

    PROFILE_CACHE_TTL_SECONDS: int = 120

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            CsvEnvSettingsSource(settings_cls),
            CsvDotEnvSettingsSource(settings_cls),
            file_secret_settings,
        )

    @field_validator("ALLOWED_ORIGINS", "ALLOWED_HOSTS", mode="before")
    @classmethod
    def _split_csv(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if normalized.startswith("postgresql+asyncpg://"):
            return normalized
        if normalized.startswith("postgresql://"):
            return normalized.replace("postgresql://", "postgresql+asyncpg://", 1)
        if normalized.startswith("postgres://"):
            return normalized.replace("postgres://", "postgresql+asyncpg://", 1)
        return normalized

    @field_validator("COOKIE_SAMESITE")
    @classmethod
    def _validate_same_site(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {"lax", "strict", "none"}:
            raise ValueError("COOKIE_SAMESITE must be lax, strict, or none")
        return normalized

    @field_validator("SMTP_TIMEOUT_SECONDS")
    @classmethod
    def _validate_smtp_timeout(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("SMTP_TIMEOUT_SECONDS must be greater than zero")
        return value

    @field_validator("SMTP_SSL")
    @classmethod
    def _validate_smtp_ssl(cls, value: bool, info) -> bool:
        smtp_tls = info.data.get("SMTP_TLS", False)
        if value and smtp_tls:
            raise ValueError("SMTP_SSL and SMTP_TLS cannot both be enabled at the same time")
        return value

    @property
    def access_cookie_max_age(self) -> int:
        return self.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    @property
    def refresh_cookie_max_age(self) -> int:
        return self.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60


settings = Settings()
