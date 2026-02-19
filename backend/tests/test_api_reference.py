import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.api import reference as reference_api
from backend.api.deps import get_current_client, set_admin_db_context
from backend.db.models import Base
from backend.db.session import get_db_session


@pytest.mark.asyncio
async def test_seed_and_list_reference_data() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    app = FastAPI()
    app.include_router(reference_api.router)

    async def override_current_client() -> SimpleNamespace:
        return SimpleNamespace(id=uuid.uuid4())

    async def override_admin_context() -> str:
        return "admin"

    async def override_db_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_current_client] = override_current_client
    app.dependency_overrides[set_admin_db_context] = override_admin_context
    app.dependency_overrides[get_db_session] = override_db_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        seed_resp = await http.post("/reference/seed-defaults")
        assert seed_resp.status_code == 200
        seed_payload = seed_resp.json()
        assert seed_payload["ok"] is True
        assert seed_payload["inserted_instruments"] > 0
        assert seed_payload["inserted_strategies"] > 0

        instruments_resp = await http.get("/reference/instruments")
        assert instruments_resp.status_code == 200
        instruments = instruments_resp.json()
        assert any(item["symbol"] == "ES" for item in instruments)
        assert any(item["symbol"] == "AAPL" for item in instruments)

        strategies_resp = await http.get("/reference/strategies")
        assert strategies_resp.status_code == 200
        strategies = strategies_resp.json()
        assert any(item["strategy_id"] == "delta_rebalance_single" for item in strategies)
