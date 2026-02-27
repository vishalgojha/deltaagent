import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.agent.core import TradingAgent
from backend.agent.memory import AgentMemoryStore
from backend.agent.risk import RiskGovernor
from backend.api.deps import require_admin_access
from backend.api.admin import set_emergency_halt
from backend.auth.jwt import create_admin_token, hash_password
from backend.brokers.mock import MockBroker
from backend.config import get_settings
from backend.db.models import AuditLog, Base, Client, Proposal
from backend.schemas import EmergencyHaltRequest
from backend.safety.emergency_halt import EmergencyHaltController


def test_admin_key_required_for_emergency_halt_access() -> None:
    settings = get_settings()
    previous = settings.admin_api_key
    settings.admin_api_key = "expected-admin-key"
    try:
        with pytest.raises(HTTPException) as exc:
            require_admin_access(x_admin_key="wrong-key")
        assert exc.value.status_code == 401

        assert require_admin_access(x_admin_key="expected-admin-key") == "admin"
        assert require_admin_access(authorization=f"Bearer {create_admin_token('admin')}") == "admin"
    finally:
        settings.admin_api_key = previous


def test_admin_session_login_returns_bearer_token() -> None:
    settings = get_settings()
    previous = settings.admin_api_key
    settings.admin_api_key = "expected-admin-key"
    try:
        app = FastAPI()
        from backend.api import admin as admin_api

        app.include_router(admin_api.router)
        with TestClient(app) as client:
            response = client.post("/admin/session/login", json={"admin_key": "expected-admin-key"})
            assert response.status_code == 200
            body = response.json()
            assert body["token_type"] == "bearer"
            assert isinstance(body["access_token"], str)
            assert len(body["access_token"]) > 20
    finally:
        settings.admin_api_key = previous


@pytest.mark.asyncio
async def test_emergency_halt_endpoint_writes_audit_rows() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as db:
        c1 = Client(
            id=uuid.uuid4(),
            email="a@example.com",
            hashed_password=hash_password("secret"),
            broker_type="ibkr",
            encrypted_creds="enc",
            risk_params={},
            mode="confirmation",
            tier="basic",
            is_active=True,
        )
        c2 = Client(
            id=uuid.uuid4(),
            email="b@example.com",
            hashed_password=hash_password("secret"),
            broker_type="ibkr",
            encrypted_creds="enc",
            risk_params={},
            mode="confirmation",
            tier="basic",
            is_active=True,
        )
        db.add_all([c1, c2])
        await db.commit()

        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(emergency_halt=EmergencyHaltController())))
        response = await set_emergency_halt(
            payload=EmergencyHaltRequest(halted=True, reason="manual kill switch"),
            request=request,  # type: ignore[arg-type]
            admin_actor="admin",
            db=db,
        )

        assert response.halted is True
        assert response.reason == "manual kill switch"
        rows = await db.execute(select(AuditLog).where(AuditLog.event_type == "emergency_halt_updated"))
        events = rows.scalars().all()
        assert len(events) == 2
        for event in events:
            assert event.details["halted"] is True
            assert event.details["reason"] == "manual kill switch"
            assert event.details["updated_by"] == "admin"
            assert isinstance(event.details["updated_at"], str)


@pytest.mark.asyncio
async def test_emergency_halt_blocks_proposal_approval_execution() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as db:
        client_id = uuid.uuid4()
        db.add(
            Client(
                id=client_id,
                email="halted@example.com",
                hashed_password=hash_password("secret"),
                broker_type="ibkr",
                encrypted_creds="enc",
                risk_params={"delta_threshold": 10.0},
                mode="confirmation",
                tier="basic",
                is_active=True,
            )
        )
        await db.commit()

        proposal = Proposal(
            client_id=client_id,
            trade_payload={"action": "BUY", "symbol": "ES", "instrument": "FOP", "qty": 1, "order_type": "MKT"},
            agent_reasoning="test",
            status="pending",
        )
        db.add(proposal)
        await db.commit()
        await db.refresh(proposal)

        broker = MockBroker()
        await broker.connect()
        risk = RiskGovernor()
        risk._is_market_hours = lambda _: True  # type: ignore[attr-defined]
        controller = EmergencyHaltController()
        await controller.set(halted=True, reason="ops", updated_by="admin")
        agent = TradingAgent(broker, db, AgentMemoryStore(), risk, emergency_halt=controller)

        with pytest.raises(ValueError, match="globally halted"):
            await agent.approve_proposal(client_id, proposal.id)


class _FakeRedis:
    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._data.get(key)

    async def set(self, key: str, value: str) -> None:
        self._data[key] = value


@pytest.mark.asyncio
async def test_emergency_halt_state_persists_in_shared_store() -> None:
    fake_redis = _FakeRedis()
    writer = EmergencyHaltController(redis_client=fake_redis)  # type: ignore[arg-type]
    reader = EmergencyHaltController(redis_client=fake_redis)  # type: ignore[arg-type]

    await writer.set(halted=True, reason="persisted", updated_by="admin")
    state = await reader.get()

    assert state.halted is True
    assert state.reason == "persisted"
    assert state.updated_by == "admin"
