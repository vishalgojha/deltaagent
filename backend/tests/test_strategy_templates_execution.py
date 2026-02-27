import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.auth.jwt import hash_password
from backend.brokers.mock import MockBroker
from backend.db.models import AuditLog, Base, Client, StrategyTemplate, Trade, TradeFill
from backend.safety.emergency_halt import EmergencyHaltController
from backend.strategy_templates.service import ResolvedStrategy, StrategyTemplateService


@pytest.mark.asyncio
async def test_strategy_template_execution_blocked_by_emergency_halt() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as db:
        client_id = uuid.uuid4()
        db.add(
            Client(
                id=client_id,
                email="halt-template@example.com",
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

        broker = MockBroker()
        await broker.connect()
        controller = EmergencyHaltController()
        await controller.set(halted=True, reason="ops halt", updated_by="admin")
        service = StrategyTemplateService(db)

        with pytest.raises(ValueError, match="globally halted"):
            await service.execute_strategy_template(
                client_id=client_id,
                template_id=999,
                broker=broker,
                emergency_halt=controller,
            )

        rows = await db.execute(
            select(AuditLog).where(
                AuditLog.client_id == client_id,
                AuditLog.event_type == "emergency_halt_blocked",
            )
        )
        assert rows.scalar_one_or_none() is not None
    await engine.dispose()


@pytest.mark.asyncio
async def test_strategy_template_execution_persists_trade_fill(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as db:
        client_id = uuid.uuid4()
        db.add(
            Client(
                id=client_id,
                email="template-fill@example.com",
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
            StrategyTemplate(
                id=1,
                client_id=client_id,
                name="ES Call Fly",
                strategy_type="call_butterfly",
                underlying_symbol="ES",
                dte_min=1,
                dte_max=30,
                center_delta_target=0.5,
                wing_width=50.0,
                max_risk_per_trade=2000.0,
                sizing_method="risk_based",
                max_contracts=3,
                hedge_enabled=False,
                auto_execute=False,
            )
        )
        await db.commit()

        async def _resolve(*_args, **_kwargs) -> ResolvedStrategy:
            return ResolvedStrategy(
                template_id=1,
                strategy_type="call_butterfly",
                expiry="20260320",
                dte=20,
                center_strike=5000.0,
                estimated_net_premium=3.2,
                estimated_max_risk=1800.0,
                estimated_net_delta=0.02,
                contracts=1,
                greeks={"delta": 0.02, "gamma": 0.01, "theta": -0.03, "vega": 0.04},
                pnl_curve=[],
                legs=[
                    {
                        "action": "BUY",
                        "ratio": 1,
                        "symbol": "ES",
                        "instrument": "FOP",
                        "expiry": "20260320",
                        "strike": 4950.0,
                        "right": "C",
                    },
                    {
                        "action": "SELL",
                        "ratio": 2,
                        "symbol": "ES",
                        "instrument": "FOP",
                        "expiry": "20260320",
                        "strike": 5000.0,
                        "right": "C",
                    },
                    {
                        "action": "BUY",
                        "ratio": 1,
                        "symbol": "ES",
                        "instrument": "FOP",
                        "expiry": "20260320",
                        "strike": 5050.0,
                        "right": "C",
                    },
                ],
            )

        monkeypatch.setattr(StrategyTemplateService, "resolve_strategy_template", _resolve)
        monkeypatch.setattr(
            "backend.strategy_templates.service.RiskGovernor._is_market_hours",
            staticmethod(lambda _time: True),
        )

        broker = MockBroker()
        await broker.connect()
        service = StrategyTemplateService(db)
        execution = await service.execute_strategy_template(client_id=client_id, template_id=1, broker=broker)

        assert execution.status == "filled"
        assert execution.order_id is not None

        trade_rows = await db.execute(select(Trade).where(Trade.client_id == client_id))
        trade = trade_rows.scalar_one_or_none()
        assert trade is not None
        assert trade.order_id == execution.order_id
        assert trade.status == "filled"
        assert trade.fill_price == pytest.approx(3.2)

        fill_rows = await db.execute(
            select(TradeFill).where(TradeFill.client_id == client_id, TradeFill.trade_id == trade.id)
        )
        fill = fill_rows.scalar_one_or_none()
        assert fill is not None
        assert fill.order_id == execution.order_id
        assert fill.status == "filled"
        assert fill.fill_price == pytest.approx(3.2)
        assert fill.expected_price == pytest.approx(3.2)
    await engine.dispose()
