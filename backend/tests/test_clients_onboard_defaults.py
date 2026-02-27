import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.api import clients as clients_api
from backend.db.models import Base, Client
from backend.db.session import get_db_session


@pytest.mark.asyncio
async def test_onboard_persists_default_execution_alert_thresholds() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    app = FastAPI()
    app.include_router(clients_api.router)

    async def override_db_session():
        async with session_maker() as db:
            yield db

    app.dependency_overrides[get_db_session] = override_db_session

    payload = {
        "email": "defaults-onboard@example.com",
        "password": "secret",
        "broker_type": "ibkr",
        "broker_credentials": {"host": "localhost", "port": 4002, "client_id": 17},
        "risk_parameters": {"delta_threshold": 0.35, "max_size": 12},
        "subscription_tier": "basic",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        response = await http.post("/clients/onboard", json=payload)

    assert response.status_code == 200
    body = response.json()
    risk = body["risk_params"]

    assert risk["delta_threshold"] == pytest.approx(0.35)
    assert risk["max_size"] == 12
    assert risk["max_loss"] == pytest.approx(5000.0)
    assert risk["max_open_positions"] == 20
    assert risk["execution_alert_slippage_warn_bps"] == pytest.approx(15.0)
    assert risk["execution_alert_slippage_critical_bps"] == pytest.approx(30.0)
    assert risk["execution_alert_latency_warn_ms"] == 3000
    assert risk["execution_alert_latency_critical_ms"] == 8000
    assert risk["execution_alert_fill_coverage_warn_pct"] == pytest.approx(75.0)
    assert risk["execution_alert_fill_coverage_critical_pct"] == pytest.approx(50.0)

    async with session_maker() as db:
        client_id = uuid.UUID(body["id"])
        client = await db.get(Client, client_id)
        assert client is not None
        assert client.risk_params["execution_alert_latency_warn_ms"] == 3000

    await engine.dispose()
