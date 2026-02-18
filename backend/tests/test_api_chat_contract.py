import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.api import agent as agent_api
from backend.api.deps import get_current_client
from backend.db.session import get_db_session


class _FakeAgent:
    async def chat(self, _client_id: uuid.UUID, _message: str) -> dict:
        return {
            "mode": "confirmation",
            "message": "proposal generated",
            "executed": False,
            "proposal_id": 42,
            "proposal": {"action": "SELL", "symbol": "ES", "qty": 1},
            "tool_trace_id": "trace-42",
            "planned_tools": [{"name": "get_portfolio_greeks", "input": {}}],
            "tool_calls": [
                {
                    "tool_use_id": "tool-1",
                    "name": "get_portfolio_greeks",
                    "input": {},
                    "started_at": "2026-02-18T00:00:00Z",
                    "completed_at": "2026-02-18T00:00:00Z",
                    "duration_ms": 12,
                }
            ],
            "tool_results": [
                {
                    "tool_use_id": "tool-1",
                    "name": "get_portfolio_greeks",
                    "output": {"net_greeks": {"delta": 0.5}},
                    "success": True,
                    "error": None,
                    "started_at": "2026-02-18T00:00:00Z",
                    "completed_at": "2026-02-18T00:00:00Z",
                    "duration_ms": 12,
                }
            ],
        }


class _FakeManager:
    async def get_agent(self, *_args, **_kwargs) -> _FakeAgent:
        return _FakeAgent()


@pytest.mark.asyncio
async def test_chat_endpoint_response_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    client_id = uuid.uuid4()
    app = FastAPI()
    app.include_router(agent_api.router)
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
    monkeypatch.setattr(agent_api.vault, "decrypt", lambda _ciphertext: {})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        response = await http.post(f"/clients/{client_id}/agent/chat", json={"message": "hedge delta"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["tool_trace_id"] == "trace-42"
    assert isinstance(payload["planned_tools"], list)
    assert isinstance(payload["tool_calls"], list)
    assert isinstance(payload["tool_results"], list)
    assert payload["tool_calls"][0]["name"] == "get_portfolio_greeks"
    assert payload["tool_calls"][0]["duration_ms"] == 12
    assert payload["tool_results"][0]["success"] is True
    assert payload["tool_results"][0]["output"]["net_greeks"]["delta"] == 0.5
