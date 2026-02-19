import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.api import clients as clients_api
from backend.api.deps import get_current_client
from backend.db.session import get_db_session


class _FakeBroker:
    @staticmethod
    async def get_market_data(_symbol: str) -> dict:
        return {"underlying_price": 6150.25}


class _FakeAgent:
    broker = _FakeBroker()


class _FakeManager:
    async def get_agent(self, *_args, **_kwargs) -> _FakeAgent:
        return _FakeAgent()


@pytest.mark.asyncio
async def test_ibkr_preflight_success(monkeypatch: pytest.MonkeyPatch) -> None:
    client_id = uuid.uuid4()
    app = FastAPI()
    app.include_router(clients_api.router)
    app.state.agent_manager = _FakeManager()

    async def override_current_client() -> SimpleNamespace:
        return SimpleNamespace(
            id=client_id,
            broker_type="ibkr",
            encrypted_creds="encrypted-creds",
        )

    async def override_db_session():
        yield None

    app.dependency_overrides[get_current_client] = override_current_client
    app.dependency_overrides[get_db_session] = override_db_session
    monkeypatch.setattr(
        clients_api.vault,
        "decrypt",
        lambda _cipher: {"host": "localhost", "port": 4002, "client_id": 11, "underlying_instrument": "IND"},
    )
    monkeypatch.setattr(clients_api, "_check_tcp", lambda *_args, **_kwargs: _true())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        response = await http.post(f"/clients/{client_id}/broker/preflight")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["broker"] == "ibkr"
    keys = {check["key"]: check for check in payload["checks"]}
    assert keys["host"]["status"] == "pass"
    assert keys["port"]["status"] == "pass"
    assert keys["socket"]["status"] == "pass"
    assert keys["market_data"]["status"] == "pass"


@pytest.mark.asyncio
async def test_ibkr_preflight_fails_when_socket_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    client_id = uuid.uuid4()
    app = FastAPI()
    app.include_router(clients_api.router)
    app.state.agent_manager = _FakeManager()

    async def override_current_client() -> SimpleNamespace:
        return SimpleNamespace(
            id=client_id,
            broker_type="ibkr",
            encrypted_creds="encrypted-creds",
        )

    async def override_db_session():
        yield None

    app.dependency_overrides[get_current_client] = override_current_client
    app.dependency_overrides[get_db_session] = override_db_session
    monkeypatch.setattr(
        clients_api.vault,
        "decrypt",
        lambda _cipher: {"host": "localhost", "port": 4002, "client_id": 11, "underlying_instrument": "IND"},
    )
    monkeypatch.setattr(clients_api, "_check_tcp", lambda *_args, **_kwargs: _false())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        response = await http.post(f"/clients/{client_id}/broker/preflight")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert any("Cannot reach IBKR gateway" in issue for issue in payload["blocking_issues"])
    socket_check = next(check for check in payload["checks"] if check["key"] == "socket")
    assert socket_check["status"] == "fail"


@pytest.mark.asyncio
async def test_phillip_preflight_missing_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    client_id = uuid.uuid4()
    app = FastAPI()
    app.include_router(clients_api.router)
    app.state.agent_manager = _FakeManager()

    async def override_current_client() -> SimpleNamespace:
        return SimpleNamespace(
            id=client_id,
            broker_type="phillip",
            encrypted_creds="encrypted-creds",
        )

    async def override_db_session():
        yield None

    app.dependency_overrides[get_current_client] = override_current_client
    app.dependency_overrides[get_db_session] = override_db_session
    monkeypatch.setattr(clients_api.vault, "decrypt", lambda _cipher: {})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        response = await http.post(f"/clients/{client_id}/broker/preflight")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert "Phillip client_id is missing." in payload["blocking_issues"]
    assert "Phillip client_secret is missing." in payload["blocking_issues"]


async def _true() -> bool:
    return True


async def _false() -> bool:
    return False
