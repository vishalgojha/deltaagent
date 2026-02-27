import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.api import trades as trades_api
from backend.api.deps import get_current_client
from backend.auth.jwt import hash_password
from backend.db.models import Base, Client, Trade, TradeFill
from backend.db.session import get_db_session


@pytest.mark.asyncio
async def test_ingest_trade_fill_updates_trade_state() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    client_id = uuid.uuid4()
    async with session_maker() as db:
        db.add(
            Client(
                id=client_id,
                email="fills-a@example.com",
                hashed_password=hash_password("secret"),
                broker_type="ibkr",
                encrypted_creds="enc",
                risk_params={},
                mode="confirmation",
                tier="basic",
                is_active=True,
            )
        )
        db.add(
            Trade(
                client_id=client_id,
                action="BUY",
                symbol="ES",
                instrument="FOP",
                qty=2,
                fill_price=None,
                order_id="OID-FILLS-1",
                agent_reasoning="test",
                mode="confirmation",
                status="submitted",
                pnl=0.0,
            )
        )
        await db.commit()

    app = FastAPI()
    app.include_router(trades_api.router)

    async def override_current_client() -> SimpleNamespace:
        return SimpleNamespace(id=client_id)

    async def override_db_session():
        async with session_maker() as db:
            yield db

    app.dependency_overrides[get_current_client] = override_current_client
    app.dependency_overrides[get_db_session] = override_db_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        first = await http.post(
            f"/clients/{client_id}/trades/1/fills",
            json={
                "status": "partially_filled",
                "qty": 1,
                "fill_price": 10.10,
                "expected_price": 10.00,
                "fees": 1.25,
                "realized_pnl": -25.0,
            },
        )
        second = await http.post(
            f"/clients/{client_id}/trades/1/fills",
            json={
                "status": "filled",
                "qty": 1,
                "fill_price": 9.90,
                "expected_price": 10.00,
                "fees": 1.00,
            },
        )

    assert first.status_code == 200
    payload = first.json()
    assert payload["trade_id"] == 1
    assert payload["status"] == "partially_filled"
    assert payload["slippage_bps"] == pytest.approx(100.0)
    assert second.status_code == 200
    payload_second = second.json()
    assert payload_second["status"] == "filled"
    assert payload_second["slippage_bps"] == pytest.approx(-100.0)

    async with session_maker() as db:
        trade = await db.get(Trade, 1)
        assert trade is not None
        assert trade.status == "filled"
        assert trade.fill_price == pytest.approx(10.0)
        assert trade.pnl == pytest.approx(-25.0)

    await engine.dispose()


@pytest.mark.asyncio
async def test_execution_quality_metrics_aggregates_fill_events() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    client_id = uuid.uuid4()
    async with session_maker() as db:
        db.add(
            Client(
                id=client_id,
                email="fills-b@example.com",
                hashed_password=hash_password("secret"),
                broker_type="ibkr",
                encrypted_creds="enc",
                risk_params={},
                mode="confirmation",
                tier="basic",
                is_active=True,
            )
        )
        db.add(
            Trade(
                id=1,
                client_id=client_id,
                action="BUY",
                symbol="ES",
                instrument="FOP",
                qty=1,
                fill_price=None,
                order_id="OID-FILLS-A",
                agent_reasoning="test",
                mode="confirmation",
                status="submitted",
                pnl=0.0,
            )
        )
        db.add(
            Trade(
                id=2,
                client_id=client_id,
                action="SELL",
                symbol="NQ",
                instrument="FOP",
                qty=1,
                fill_price=None,
                order_id="OID-FILLS-B",
                agent_reasoning="test",
                mode="confirmation",
                status="submitted",
                pnl=0.0,
            )
        )
        db.add(
            TradeFill(
                client_id=client_id,
                trade_id=1,
                order_id="OID-FILLS-A",
                broker_fill_id="FILL-1",
                status="partially_filled",
                qty=1,
                fill_price=10.1,
                expected_price=10.0,
                slippage_bps=100.0,
                fees=1.0,
                realized_pnl=None,
                raw_payload={},
            )
        )
        db.add(
            TradeFill(
                client_id=client_id,
                trade_id=1,
                order_id="OID-FILLS-A",
                broker_fill_id="FILL-2",
                status="filled",
                qty=1,
                fill_price=9.9,
                expected_price=10.0,
                slippage_bps=-100.0,
                fees=1.0,
                realized_pnl=None,
                raw_payload={},
            )
        )
        await db.commit()

    app = FastAPI()
    app.include_router(trades_api.router)

    async def override_current_client() -> SimpleNamespace:
        return SimpleNamespace(id=client_id)

    async def override_db_session():
        async with session_maker() as db:
            yield db

    app.dependency_overrides[get_current_client] = override_current_client
    app.dependency_overrides[get_db_session] = override_db_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        fills = await http.get(f"/clients/{client_id}/trades/1/fills")
        metrics = await http.get(f"/clients/{client_id}/metrics/execution-quality")

    assert fills.status_code == 200
    fill_payload = fills.json()
    assert len(fill_payload) == 2

    assert metrics.status_code == 200
    metrics_payload = metrics.json()
    assert metrics_payload["trades_total"] == 2
    assert metrics_payload["trades_with_fills"] == 1
    assert metrics_payload["fill_events"] == 2
    assert metrics_payload["avg_slippage_bps"] == pytest.approx(0.0)
    assert metrics_payload["median_slippage_bps"] == pytest.approx(0.0)

    async with session_maker() as db:
        fill_rows = await db.execute(select(TradeFill).where(TradeFill.client_id == client_id))
        assert len(fill_rows.scalars().all()) == 2

    await engine.dispose()


@pytest.mark.asyncio
async def test_execution_quality_backfills_filled_trades_without_fill_events() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    client_id = uuid.uuid4()
    async with session_maker() as db:
        db.add(
            Client(
                id=client_id,
                email="fills-backfill@example.com",
                hashed_password=hash_password("secret"),
                broker_type="ibkr",
                encrypted_creds="enc",
                risk_params={},
                mode="confirmation",
                tier="basic",
                is_active=True,
            )
        )
        db.add(
            Trade(
                id=1,
                client_id=client_id,
                action="BUY",
                symbol="ES",
                instrument="FOP",
                qty=1,
                fill_price=12.25,
                order_id="OID-BACKFILL-1",
                agent_reasoning="legacy",
                mode="confirmation",
                status="filled",
                pnl=0.0,
            )
        )
        db.add(
            Trade(
                id=2,
                client_id=client_id,
                action="BUY",
                symbol="NQ",
                instrument="FOP",
                qty=1,
                fill_price=None,
                order_id="OID-BACKFILL-2",
                agent_reasoning="pending",
                mode="confirmation",
                status="submitted",
                pnl=0.0,
            )
        )
        await db.commit()

    app = FastAPI()
    app.include_router(trades_api.router)

    async def override_current_client() -> SimpleNamespace:
        return SimpleNamespace(id=client_id)

    async def override_db_session():
        async with session_maker() as db:
            yield db

    app.dependency_overrides[get_current_client] = override_current_client
    app.dependency_overrides[get_db_session] = override_db_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        metrics_backfill = await http.get(f"/clients/{client_id}/metrics/execution-quality")
        metrics_raw = await http.get(f"/clients/{client_id}/metrics/execution-quality?backfill_missing=false")

    assert metrics_backfill.status_code == 200
    payload = metrics_backfill.json()
    assert payload["trades_total"] == 2
    assert payload["trades_with_fills"] == 1
    assert payload["fill_events"] == 1
    assert payload["backfilled_trades"] == 1
    assert payload["backfilled_fill_events"] == 1
    assert payload["avg_slippage_bps"] == pytest.approx(0.0)
    assert payload["avg_first_fill_latency_ms"] == pytest.approx(0.0)

    assert metrics_raw.status_code == 200
    raw_payload = metrics_raw.json()
    assert raw_payload["trades_with_fills"] == 0
    assert raw_payload["fill_events"] == 0
    assert raw_payload["backfilled_trades"] == 0
    assert raw_payload["backfilled_fill_events"] == 0
    assert raw_payload["avg_slippage_bps"] is None

    await engine.dispose()


@pytest.mark.asyncio
async def test_create_and_list_execution_incident_notes() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    client_id = uuid.uuid4()
    async with session_maker() as db:
        db.add(
            Client(
                id=client_id,
                email="fills-incident@example.com",
                hashed_password=hash_password("secret"),
                broker_type="ibkr",
                encrypted_creds="enc",
                risk_params={},
                mode="confirmation",
                tier="basic",
                is_active=True,
            )
        )
        await db.commit()

    app = FastAPI()
    app.include_router(trades_api.router)

    async def override_current_client() -> SimpleNamespace:
        return SimpleNamespace(id=client_id)

    async def override_db_session():
        async with session_maker() as db:
            yield db

    app.dependency_overrides[get_current_client] = override_current_client
    app.dependency_overrides[get_db_session] = override_db_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        created = await http.post(
            f"/clients/{client_id}/metrics/incidents",
            json={
                "alert_id": "first-fill-latency",
                "severity": "critical",
                "label": "Latency",
                "note": "Paused autonomous mode while validating broker latency.",
                "context": {"source": "dashboard"},
            },
        )
        listed = await http.get(f"/clients/{client_id}/metrics/incidents")

    assert created.status_code == 200
    created_payload = created.json()
    assert created_payload["alert_id"] == "first-fill-latency"
    assert created_payload["severity"] == "critical"
    assert created_payload["label"] == "Latency"
    assert created_payload["note"].startswith("Paused autonomous mode")

    assert listed.status_code == 200
    listed_payload = listed.json()
    assert len(listed_payload) == 1
    assert listed_payload[0]["alert_id"] == "first-fill-latency"
    assert listed_payload[0]["context"]["source"] == "dashboard"

    await engine.dispose()


@pytest.mark.asyncio
async def test_ingest_trade_fill_idempotency_key_deduplicates_requests() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    client_id = uuid.uuid4()
    async with session_maker() as db:
        db.add(
            Client(
                id=client_id,
                email="fills-c@example.com",
                hashed_password=hash_password("secret"),
                broker_type="ibkr",
                encrypted_creds="enc",
                risk_params={},
                mode="confirmation",
                tier="basic",
                is_active=True,
            )
        )
        db.add(
            Trade(
                client_id=client_id,
                action="BUY",
                symbol="ES",
                instrument="FOP",
                qty=1,
                fill_price=None,
                order_id="OID-FILLS-IDEMP",
                agent_reasoning="test",
                mode="confirmation",
                status="submitted",
                pnl=0.0,
            )
        )
        await db.commit()

    app = FastAPI()
    app.include_router(trades_api.router)

    async def override_current_client() -> SimpleNamespace:
        return SimpleNamespace(id=client_id)

    async def override_db_session():
        async with session_maker() as db:
            yield db

    app.dependency_overrides[get_current_client] = override_current_client
    app.dependency_overrides[get_db_session] = override_db_session

    payload = {
        "status": "filled",
        "qty": 1,
        "fill_price": 10.0,
        "expected_price": 10.0,
        "fees": 0.25,
        "broker_fill_id": "FILL-IDEMP-1",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        first = await http.post(
            f"/clients/{client_id}/trades/1/fills",
            headers={"Idempotency-Key": "idem-key-1"},
            json=payload,
        )
        second = await http.post(
            f"/clients/{client_id}/trades/1/fills",
            headers={"Idempotency-Key": "idem-key-1"},
            json={**payload, "fill_price": 9.5},
        )

    assert first.status_code == 200
    assert second.status_code == 200
    first_payload = first.json()
    second_payload = second.json()
    assert first_payload["id"] == second_payload["id"]
    assert first_payload["fill_price"] == pytest.approx(10.0)
    assert second_payload["fill_price"] == pytest.approx(10.0)
    assert second_payload["ingest_idempotency_key"] == "idem-key-1"

    async with session_maker() as db:
        fill_rows = await db.execute(select(TradeFill).where(TradeFill.client_id == client_id))
        fills = fill_rows.scalars().all()
        assert len(fills) == 1

    await engine.dispose()


@pytest.mark.asyncio
async def test_ingest_trade_fill_broker_fill_id_deduplicates_requests() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    client_id = uuid.uuid4()
    async with session_maker() as db:
        db.add(
            Client(
                id=client_id,
                email="fills-d@example.com",
                hashed_password=hash_password("secret"),
                broker_type="ibkr",
                encrypted_creds="enc",
                risk_params={},
                mode="confirmation",
                tier="basic",
                is_active=True,
            )
        )
        db.add(
            Trade(
                client_id=client_id,
                action="SELL",
                symbol="NQ",
                instrument="FOP",
                qty=1,
                fill_price=None,
                order_id="OID-FILLS-BROKER-ID",
                agent_reasoning="test",
                mode="confirmation",
                status="submitted",
                pnl=0.0,
            )
        )
        await db.commit()

    app = FastAPI()
    app.include_router(trades_api.router)

    async def override_current_client() -> SimpleNamespace:
        return SimpleNamespace(id=client_id)

    async def override_db_session():
        async with session_maker() as db:
            yield db

    app.dependency_overrides[get_current_client] = override_current_client
    app.dependency_overrides[get_db_session] = override_db_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        first = await http.post(
            f"/clients/{client_id}/trades/1/fills",
            json={
                "status": "filled",
                "qty": 1,
                "fill_price": 20.0,
                "expected_price": 19.8,
                "fees": 0.5,
                "broker_fill_id": "BROKER-FILL-1",
            },
        )
        second = await http.post(
            f"/clients/{client_id}/trades/1/fills",
            json={
                "status": "filled",
                "qty": 1,
                "fill_price": 20.5,
                "expected_price": 19.8,
                "fees": 0.5,
                "broker_fill_id": "BROKER-FILL-1",
            },
        )

    assert first.status_code == 200
    assert second.status_code == 200
    first_payload = first.json()
    second_payload = second.json()
    assert first_payload["id"] == second_payload["id"]
    assert second_payload["fill_price"] == pytest.approx(20.0)

    async with session_maker() as db:
        fill_rows = await db.execute(select(TradeFill).where(TradeFill.client_id == client_id))
        fills = fill_rows.scalars().all()
        assert len(fills) == 1

    await engine.dispose()
