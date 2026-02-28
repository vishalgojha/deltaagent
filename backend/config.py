from functools import lru_cache
import json
from typing import Annotated, Any
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

LOCAL_CORS_DEFAULTS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]
LOCAL_CORS_REGEX = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "trading-agent"
    api_prefix: str = "/"
    app_env: str = Field(default="development", alias="APP_ENV")

    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    database_url: str = Field(
        default="sqlite+aiosqlite:///./trading.db",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    jwt_secret: str = Field(default="change_me", alias="JWT_SECRET")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    encryption_key: str = Field(
        default="00000000000000000000000000000000",
        alias="ENCRYPTION_KEY",
    )

    ibkr_gateway_host: str = Field(default="localhost", alias="IBKR_GATEWAY_HOST")
    ibkr_gateway_port: int = Field(default=4002, alias="IBKR_GATEWAY_PORT")
    phillip_api_base: str = Field(
        default="https://api.phillipcapital.com.au", alias="PHILLIP_API_BASE"
    )
    phillip_client_id: str | None = Field(default=None, alias="PHILLIP_CLIENT_ID")
    phillip_client_secret: str | None = Field(
        default=None,
        alias="PHILLIP_CLIENT_SECRET",
    )
    use_mock_broker: bool = Field(default=True, alias="USE_MOCK_BROKER")
    autonomous_enabled: bool = Field(default=False, alias="AUTONOMOUS_ENABLED")
    decision_backend_default: str = Field(default="ollama", alias="DECISION_BACKEND_DEFAULT")
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="llama3.1:8b", alias="OLLAMA_MODEL")
    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL")
    openrouter_model: str = Field(default="openai/gpt-4o-mini", alias="OPENROUTER_MODEL")
    openrouter_site_url: str | None = Field(default=None, alias="OPENROUTER_SITE_URL")
    openrouter_app_name: str | None = Field(default="deltaagent", alias="OPENROUTER_APP_NAME")
    xai_api_key: str | None = Field(default=None, alias="XAI_API_KEY")
    xai_base_url: str = Field(default="https://api.x.ai/v1", alias="XAI_BASE_URL")
    xai_model: str = Field(default="grok-2-latest", alias="XAI_MODEL")
    admin_api_key: str | None = Field(default=None, alias="ADMIN_API_KEY")
    auto_create_tables: bool = Field(default=True, alias="AUTO_CREATE_TABLES")
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: list(LOCAL_CORS_DEFAULTS),
        alias="CORS_ORIGINS",
    )
    cors_origin_regex: str | None = Field(
        default=None,
        alias="CORS_ORIGIN_REGEX",
    )

    @field_validator("app_env", mode="before")
    @classmethod
    def _normalize_app_env(cls, value: Any) -> str:
        if isinstance(value, str):
            raw = value.strip().lower()
            return raw or "development"
        return "development"

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, value: Any) -> str:
        if not isinstance(value, str):
            return "sqlite+aiosqlite:///./trading.db"
        raw = value.strip()
        if raw.startswith("postgres://"):
            return "postgresql+asyncpg://" + raw[len("postgres://") :]
        if raw.startswith("postgresql://"):
            return "postgresql+asyncpg://" + raw[len("postgresql://") :]
        if raw.startswith("postgresql+psycopg2://"):
            return "postgresql+asyncpg://" + raw[len("postgresql+psycopg2://") :]
        return raw

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _normalize_cors_origins(cls, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        if isinstance(value, str):
            raw = value.strip()
            if raw.startswith("[") and raw.endswith("]"):
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        return [str(v).strip() for v in parsed if str(v).strip()]
                except Exception:  # noqa: BLE001
                    pass
            return [item.strip() for item in value.split(",") if item.strip()]
        return list(LOCAL_CORS_DEFAULTS)

    @field_validator("cors_origin_regex", mode="before")
    @classmethod
    def _normalize_cors_origin_regex(cls, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            raw = value.strip()
            return raw or None
        return None

    @model_validator(mode="after")
    def _finalize_cors(self) -> "Settings":
        is_dev = self.app_env in {"dev", "development", "local"}
        if is_dev:
            if not self.cors_origins:
                self.cors_origins = list(LOCAL_CORS_DEFAULTS)
            if not self.cors_origin_regex:
                self.cors_origin_regex = LOCAL_CORS_REGEX
            return self

        if not self.cors_origins:
            raise ValueError("CORS_ORIGINS must be set outside development.")

        if self.cors_origin_regex and "localhost" in self.cors_origin_regex:
            self.cors_origin_regex = None
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
