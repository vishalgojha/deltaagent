import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.api import agent as agent_api
from backend.api.deps import get_current_client
from backend.db.session import get_db_session


class _StubDbSession:
    def __init__(self) -> None:
        self.commit_count = 0

    async def commit(self) -> None:
        self.commit_count += 1


@pytest.mark.asyncio
async def test_get_llm_credentials_status_uses_client_and_env_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    client_id = uuid.uuid4()
    app = FastAPI()
    app.include_router(agent_api.router)

    current_client = SimpleNamespace(
        id=client_id,
        broker_type="ibkr",
        encrypted_creds="enc-1",
    )

    async def override_current_client() -> SimpleNamespace:
        return current_client

    async def override_db_session():
        yield _StubDbSession()

    app.dependency_overrides[get_current_client] = override_current_client
    app.dependency_overrides[get_db_session] = override_db_session
    monkeypatch.setattr(
        agent_api.vault,
        "decrypt",
        lambda _ciphertext: {
            "host": "localhost",
            "llm_credentials": {
                "openai_api_key": "sk-client-openai",
                "xai_api_key": "xai-client",
            },
        },
    )
    monkeypatch.setattr(
        agent_api,
        "get_settings",
        lambda: SimpleNamespace(
            openai_api_key="",
            anthropic_api_key="env-anthropic",
            openrouter_api_key="env-openrouter",
            xai_api_key="",
        ),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        response = await http.get(f"/clients/{client_id}/agent/llm-credentials")

    assert response.status_code == 200
    payload = response.json()
    assert payload["openai"] == {"configured": True, "source": "client"}
    assert payload["anthropic"] == {"configured": True, "source": "env"}
    assert payload["openrouter"] == {"configured": True, "source": "env"}
    assert payload["xai"] == {"configured": True, "source": "client"}


@pytest.mark.asyncio
async def test_update_llm_credentials_persists_into_encrypted_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    client_id = uuid.uuid4()
    app = FastAPI()
    app.include_router(agent_api.router)

    current_client = SimpleNamespace(
        id=client_id,
        broker_type="ibkr",
        encrypted_creds="enc-old",
    )
    db_stub = _StubDbSession()
    encrypted_payloads: list[dict] = []

    async def override_current_client() -> SimpleNamespace:
        return current_client

    async def override_db_session():
        yield db_stub

    app.dependency_overrides[get_current_client] = override_current_client
    app.dependency_overrides[get_db_session] = override_db_session
    monkeypatch.setattr(
        agent_api.vault,
        "decrypt",
        lambda _ciphertext: {"host": "localhost", "port": 4002},
    )
    monkeypatch.setattr(
        agent_api.vault,
        "encrypt",
        lambda payload: encrypted_payloads.append(dict(payload)) or "enc-new",
    )
    monkeypatch.setattr(
        agent_api,
        "get_settings",
        lambda: SimpleNamespace(
            openai_api_key="",
            anthropic_api_key="",
            openrouter_api_key="",
            xai_api_key="",
        ),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        response = await http.post(
            f"/clients/{client_id}/agent/llm-credentials",
            json={
                "openai_api_key": " sk-openai ",
                "anthropic_api_key": "sk-ant",
            },
        )

    assert response.status_code == 200
    assert db_stub.commit_count == 1
    assert current_client.encrypted_creds == "enc-new"
    assert encrypted_payloads
    saved = encrypted_payloads[0]
    assert saved["host"] == "localhost"
    assert saved["port"] == 4002
    assert saved["llm_credentials"]["openai_api_key"] == "sk-openai"
    assert saved["llm_credentials"]["anthropic_api_key"] == "sk-ant"
