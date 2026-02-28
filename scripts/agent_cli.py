import argparse
import json
from pathlib import Path
from typing import Any

import httpx


SESSION_PATH = Path(__file__).with_name(".agent_cli_session.json")


def save_session(base_url: str, token: str, client_id: str) -> None:
    SESSION_PATH.write_text(json.dumps({"base_url": base_url, "token": token, "client_id": client_id}, indent=2), encoding="utf-8")


def load_session() -> dict[str, str]:
    if not SESSION_PATH.exists():
        raise SystemExit("No CLI session found. Run `login` first or pass --token and --client-id.")
    payload = json.loads(SESSION_PATH.read_text(encoding="utf-8"))
    return {
        "base_url": str(payload.get("base_url", "http://localhost:8000")).rstrip("/"),
        "token": str(payload.get("token", "")).strip(),
        "client_id": str(payload.get("client_id", "")).strip(),
    }


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def require_value(value: str, label: str) -> str:
    if not value:
        raise SystemExit(f"Missing {label}.")
    return value


def cmd_login(args: argparse.Namespace) -> None:
    base_url = args.base_url.rstrip("/")
    with httpx.Client(timeout=15.0) as client:
        response = client.post(f"{base_url}/auth/login", json={"email": args.email, "password": args.password})
        response.raise_for_status()
        payload = response.json()
    token = require_value(str(payload.get("access_token", "")).strip(), "access_token")
    client_id = require_value(str(payload.get("client_id", "")).strip(), "client_id")
    save_session(base_url, token, client_id)
    print(f"Logged in. client_id={client_id}")


def cmd_set_backend(args: argparse.Namespace) -> None:
    session = load_session()
    base_url = session["base_url"]
    token = args.token or session["token"]
    client_id = args.client_id or session["client_id"]
    token = require_value(token, "token")
    client_id = require_value(client_id, "client_id")

    body = {"risk_parameters": {"decision_backend": args.backend}}
    with httpx.Client(timeout=15.0) as client:
        response = client.post(
            f"{base_url}/clients/{client_id}/agent/parameters",
            headers=auth_headers(token),
            json=body,
        )
        response.raise_for_status()
        payload = response.json()
    print(json.dumps(payload, indent=2))


def cmd_chat(args: argparse.Namespace) -> None:
    session = load_session()
    base_url = session["base_url"]
    token = args.token or session["token"]
    client_id = args.client_id or session["client_id"]
    token = require_value(token, "token")
    client_id = require_value(client_id, "client_id")

    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            f"{base_url}/clients/{client_id}/agent/chat",
            headers=auth_headers(token),
            json={"message": args.message},
        )
        response.raise_for_status()
        payload = response.json()
    print(json.dumps(payload, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DeltaAgent CLI helper")
    sub = parser.add_subparsers(dest="command", required=True)

    login = sub.add_parser("login", help="Login and store session locally")
    login.add_argument("--base-url", default="http://localhost:8000")
    login.add_argument("--email", required=True)
    login.add_argument("--password", required=True)
    login.set_defaults(func=cmd_login)

    set_backend = sub.add_parser("set-backend", help="Set decision backend for a client")
    set_backend.add_argument(
        "--backend",
        choices=["deterministic", "ollama", "openai", "openrouter", "anthropic", "xai"],
        required=True,
    )
    set_backend.add_argument("--token")
    set_backend.add_argument("--client-id")
    set_backend.set_defaults(func=cmd_set_backend)

    chat = sub.add_parser("chat", help="Send message to agent chat endpoint")
    chat.add_argument("--message", required=True)
    chat.add_argument("--token")
    chat.add_argument("--client-id")
    chat.set_defaults(func=cmd_chat)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
