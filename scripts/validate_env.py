#!/usr/bin/env python3
"""Validate deployment environment variables for DeltaAgent."""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ValidationResult:
    errors: list[str]
    warnings: list[str]


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'").strip('"')
    return values


def value_for(key: str, env_file_values: dict[str, str]) -> str | None:
    return os.getenv(key) or env_file_values.get(key)


def is_url(value: str) -> bool:
    return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", value))


def validate(target: str, env_file_values: dict[str, str]) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    required = [
        "DATABASE_URL",
        "REDIS_URL",
        "JWT_SECRET",
        "ENCRYPTION_KEY",
        "CORS_ORIGINS",
        "ADMIN_API_KEY",
    ]
    for key in required:
        if not value_for(key, env_file_values):
            errors.append(f"Missing required variable: {key}")

    database_url = value_for("DATABASE_URL", env_file_values) or ""
    redis_url = value_for("REDIS_URL", env_file_values) or ""
    jwt_secret = value_for("JWT_SECRET", env_file_values) or ""
    encryption_key = value_for("ENCRYPTION_KEY", env_file_values) or ""
    cors_origins = value_for("CORS_ORIGINS", env_file_values) or ""
    auto_create_tables = (value_for("AUTO_CREATE_TABLES", env_file_values) or "false").lower() == "true"
    use_mock_broker = (value_for("USE_MOCK_BROKER", env_file_values) or "true").lower() == "true"
    decision_backend = (value_for("DECISION_BACKEND_DEFAULT", env_file_values) or "ollama").lower()
    anthropic_api_key = value_for("ANTHROPIC_API_KEY", env_file_values) or ""

    if database_url and not is_url(database_url):
        errors.append("DATABASE_URL must be a valid URL.")
    if redis_url and not is_url(redis_url):
        errors.append("REDIS_URL must be a valid URL.")

    if len(encryption_key) != 32:
        errors.append("ENCRYPTION_KEY must be exactly 32 characters for AES-256.")
    if jwt_secret == "change_me":
        errors.append("JWT_SECRET cannot be 'change_me' in deployment.")
    if encryption_key == "00000000000000000000000000000000":
        errors.append("ENCRYPTION_KEY cannot use the default placeholder value.")

    if decision_backend == "anthropic" and not anthropic_api_key:
        errors.append("ANTHROPIC_API_KEY is required when DECISION_BACKEND_DEFAULT=anthropic.")

    if not use_mock_broker:
        ib_host = value_for("IBKR_GATEWAY_HOST", env_file_values)
        ib_port = value_for("IBKR_GATEWAY_PORT", env_file_values)
        if not ib_host or not ib_port:
            warnings.append("Live broker mode enabled but IBKR gateway host/port is missing.")

    if target == "production":
        if "sqlite" in database_url:
            errors.append("Production deployment must not use sqlite DATABASE_URL.")
        if auto_create_tables:
            errors.append("AUTO_CREATE_TABLES must be false in production.")
        if "localhost" in cors_origins or "127.0.0.1" in cors_origins:
            warnings.append("CORS_ORIGINS still includes localhost; confirm this is intended.")

    return ValidationResult(errors=errors, warnings=warnings)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate DeltaAgent deployment environment variables.")
    parser.add_argument("--target", choices=["staging", "production"], default="production")
    parser.add_argument("--env-file", default=".env", help="Path to .env file for fallback values.")
    parser.add_argument(
        "--strict-warnings",
        action="store_true",
        help="Treat warnings as errors.",
    )
    args = parser.parse_args()

    env_file_values = parse_env_file(Path(args.env_file))
    result = validate(args.target, env_file_values)

    if result.errors:
        print("Environment validation failed:")
        for error in result.errors:
            print(f"- ERROR: {error}")
    if result.warnings:
        print("Environment validation warnings:")
        for warning in result.warnings:
            print(f"- WARN: {warning}")

    if not result.errors and not result.warnings:
        print("Environment validation passed.")

    if result.errors:
        return 2
    if args.strict_warnings and result.warnings:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
