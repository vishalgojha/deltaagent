from functools import lru_cache
import json
from typing import Any
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "trading-agent"
    api_prefix: str = "/"

    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
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
    admin_api_key: str | None = Field(default=None, alias="ADMIN_API_KEY")
    auto_create_tables: bool = Field(default=True, alias="AUTO_CREATE_TABLES")
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"], alias="CORS_ORIGINS")

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
        return ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
