import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.api import websocket as websocket_api
from backend.db.models import Base, Client, Trade


class _FakeAgent:
    async def status(self, client_id: uuid.UUID) -> dict:
        return {
            "client_id": client_id,
            "mode": "confirmation",
            "last_action": None,
            "healthy": True,
            "net_greeks": {"delta": 0, "gamma": 0, "theta": 0, "vega": 0},
        }


class _FakeManager:
    async def get_agent(self, *_args, **_kwargs) -> _FakeAgent:
        return _FakeAgent()


@pytest.mark.asyncio
async def test_websocket_stream_emits_order_status_event(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    client_id = uuid.uuid4()

    async with session_maker() as db:
        db.add(
            Client(
                id=client_id,
                email="ws-order-status@example.com",
                hashed_password="hashed",
                broker_type="ibkr",
                encrypted_creds="enc",
                risk_params={"delta_threshold": 0.2},
                mode="confirmation",
                tier="basic",
                is_active=True,
            )
        )
        db.add(
            Trade(
                client_id=client_id,
                action="SELL",
                symbol="ES",
                instrument="FOP",
                qty=1,
                fill_price=21.5,
                order_id="OID-WS-1",
                agent_reasoning="stream test",
                mode="confirmation",
                status="filled",
                pnl=0.0,
            )
        )
        await db.commit()

    app = FastAPI()
    app.include_router(websocket_api.router)
    app.state.db_sessionmaker = session_maker
    app.state.agent_manager = _FakeManager()

    monkeypatch.setattr(websocket_api, "decode_access_token", lambda _token: client_id)
    monkeypatch.setattr(websocket_api.vault, "decrypt", lambda _cipher: {"host": "localhost", "port": 4002, "client_id": 1})

    with TestClient(app) as test_client:
        with test_client.websocket_connect(f"/clients/{client_id}/stream?token=test-token") as ws:
            first = ws.receive_json()
            second = ws.receive_json()

    event_types = {first.get("type"), second.get("type")}
    assert "agent_status" in event_types
    assert "order_status" in event_types

    order_event = first if first.get("type") == "order_status" else second
    payload = order_event["data"]
    assert payload["client_id"] == str(client_id)
    assert payload["order_id"] == "OID-WS-1"
    assert payload["status"] == "filled"

    await engine.dispose()

