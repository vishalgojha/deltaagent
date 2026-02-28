import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.agent.core import TradingAgent
from backend.agent.memory import AgentMemoryStore
from backend.agent.risk import RiskGovernor, RiskViolation
from backend.auth.jwt import hash_password
from backend.brokers.mock import MockBroker
from backend.config import get_settings
from backend.db.models import Base, Client, Instrument, Proposal, Trade, TradeFill


class _FakeRedis:
    def __init__(self) -> None:
        self.set_calls: list[tuple[str, str, int | None]] = []
        self.publish_calls: list[tuple[str, str]] = []

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.set_calls.append((key, value, ex))

    async def publish(self, channel: str, payload: str) -> None:
        self.publish_calls.append((channel, payload))


@pytest.mark.asyncio
async def test_confirmation_mode_creates_proposal() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as db:
        client_id = uuid.uuid4()
        client = Client(
            id=client_id,
            email="test@example.com",
            hashed_password=hash_password("secret"),
            broker_type="ibkr",
            encrypted_creds="enc",
            risk_params={"delta_threshold": 0.2},
            mode="confirmation",
            tier="basic",
            is_active=True,
        )
        db.add(client)
        await db.commit()

        broker = MockBroker()
        await broker.connect()
        memory = AgentMemoryStore()
        risk = RiskGovernor()
        risk._is_market_hours = lambda _: True  # type: ignore[attr-defined]
        agent = TradingAgent(broker, db, memory, risk)
        await agent.set_mode(client_id, "confirmation")
        broker._positions = [  # type: ignore[attr-defined]
            {"symbol": "ES", "instrument_type": "FOP", "qty": 1, "delta": 1.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
        ]
        result = await agent.chat(client_id, "Rebalance now")
        assert result["mode"] == "confirmation"
        assert isinstance(result.get("tool_trace_id"), str)
        assert isinstance(result.get("planned_tools"), list)
        assert isinstance(result.get("tool_calls"), list)
        assert isinstance(result.get("tool_results"), list)
        rows = await db.execute(Proposal.__table__.select())
        assert rows.first() is not None


@pytest.mark.asyncio
async def test_confirmation_mode_uses_fallback_when_model_returns_empty_trade() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as db:
        client_id = uuid.uuid4()
        client = Client(
            id=client_id,
            email="fallback@example.com",
            hashed_password=hash_password("secret"),
            broker_type="ibkr",
            encrypted_creds="enc",
            risk_params={"delta_threshold": 0.2},
            mode="confirmation",
            tier="basic",
            is_active=True,
        )
        db.add(client)
        await db.commit()

        broker = MockBroker()
        await broker.connect()
        memory = AgentMemoryStore()
        risk = RiskGovernor()
        risk._is_market_hours = lambda _: True  # type: ignore[attr-defined]
        agent = TradingAgent(broker, db, memory, risk)
        await agent.set_mode(client_id, "confirmation")
        broker._positions = [  # type: ignore[attr-defined]
            {"symbol": "ES", "instrument_type": "FOP", "qty": 1, "delta": 1.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
        ]

        async def _fake_ollama(*_args, **_kwargs):
            return {
                "reasoning": "model returned empty trade",
                "trade": {},
                "tool_trace_id": "trace-fallback",
                "planned_tools": [],
                "tool_calls": [],
                "tool_results": [],
            }

        agent._call_ollama = _fake_ollama  # type: ignore[method-assign]
        result = await agent.chat(client_id, "Rebalance now")
        assert result["mode"] == "confirmation"
        rows = await db.execute(Proposal.__table__.select())
        assert rows.first() is not None


@pytest.mark.asyncio
async def test_approve_executes_trade() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as db:
        client_id = uuid.uuid4()
        db.add(
            Client(
                id=client_id,
                email="approve@example.com",
                hashed_password=hash_password("secret"),
                broker_type="ibkr",
                encrypted_creds="enc",
                risk_params={"delta_threshold": 10.0},
                mode="confirmation",
                tier="basic",
                is_active=True,
            )
        )
        db.add(
            Instrument(
                symbol="ES",
                asset_class="future",
                exchange="CME",
                currency="USD",
                multiplier=50.0,
                tick_size=0.25,
                contract_rules={},
                aliases=["silver"],
                is_active=True,
            )
        )
        db.add(
            Instrument(
                symbol="ES",
                asset_class="future",
                exchange="CME",
                currency="USD",
                multiplier=50.0,
                tick_size=0.25,
                contract_rules={},
                aliases=["silver"],
                is_active=True,
            )
        )
        await db.commit()

        broker = MockBroker()
        await broker.connect()
        memory = AgentMemoryStore()
        risk = RiskGovernor()
        risk._is_market_hours = lambda _: True  # type: ignore[attr-defined]
        agent = TradingAgent(broker, db, memory, risk)
        proposal = Proposal(
            client_id=client_id,
            trade_payload={"action": "BUY", "symbol": "ES", "instrument": "FOP", "qty": 1, "order_type": "MKT"},
            agent_reasoning="test",
            status="pending",
        )
        db.add(proposal)
        await db.commit()
        await db.refresh(proposal)

        execution = await agent.approve_proposal(client_id, proposal.id)
        assert execution["order"]["status"] == "filled"
        trades = await db.execute(Trade.__table__.select())
        assert trades.first() is not None
        fills = await db.execute(TradeFill.__table__.select())
        assert fills.first() is not None


@pytest.mark.asyncio
async def test_approve_blocks_trade_with_unknown_strategy() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as db:
        client_id = uuid.uuid4()
        db.add(
            Client(
                id=client_id,
                email="bad-strategy@example.com",
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

        broker = MockBroker()
        await broker.connect()
        agent = TradingAgent(broker, db, AgentMemoryStore(), RiskGovernor())
        proposal = Proposal(
            client_id=client_id,
            trade_payload={
                "action": "BUY",
                "symbol": "ES",
                "instrument": "FOP",
                "qty": 1,
                "order_type": "MKT",
                "strategy_id": "totally_unknown",
            },
            agent_reasoning="test",
            status="pending",
        )
        db.add(proposal)
        await db.commit()
        await db.refresh(proposal)

        with pytest.raises(RiskViolation) as exc:
            await agent.approve_proposal(client_id, proposal.id)
        assert exc.value.rule == "STRATEGY_POLICY"


@pytest.mark.asyncio
async def test_autonomous_mode_blocked_by_global_switch() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as db:
        client_id = uuid.uuid4()
        db.add(
            Client(
                id=client_id,
                email="blocked@example.com",
                hashed_password=hash_password("secret"),
                broker_type="ibkr",
                encrypted_creds="enc",
                risk_params={"delta_threshold": 0.2},
                mode="confirmation",
                tier="basic",
                is_active=True,
            )
        )
        await db.commit()

        settings = get_settings()
        previous = settings.autonomous_enabled
        settings.autonomous_enabled = False
        try:
            broker = MockBroker()
            await broker.connect()
            agent = TradingAgent(broker, db, AgentMemoryStore(), RiskGovernor())
            with pytest.raises(ValueError):
                await agent.set_mode(client_id, "autonomous")
        finally:
            settings.autonomous_enabled = previous


@pytest.mark.asyncio
async def test_agent_caches_greeks_and_publishes_stream_events() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as db:
        client_id = uuid.uuid4()
        db.add(
            Client(
                id=client_id,
                email="stream@example.com",
                hashed_password=hash_password("secret"),
                broker_type="ibkr",
                encrypted_creds="enc",
                risk_params={"delta_threshold": 0.2},
                mode="confirmation",
                tier="basic",
                is_active=True,
            )
        )
        await db.commit()

        broker = MockBroker()
        await broker.connect()
        fake_redis = _FakeRedis()
        agent = TradingAgent(broker, db, AgentMemoryStore(), RiskGovernor(), redis_client=fake_redis)  # type: ignore[arg-type]
        await agent.set_mode(client_id, "confirmation")
        await agent.chat(client_id, "Analyze and propose hedge")

        assert any(key == f"client:{client_id}:greeks" for key, _, _ in fake_redis.set_calls)
        assert any(channel == f"client:{client_id}:events" for channel, _ in fake_redis.publish_calls)


@pytest.mark.asyncio
async def test_confirmation_mode_no_trade_does_not_create_empty_proposal() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as db:
        client_id = uuid.uuid4()
        db.add(
            Client(
                id=client_id,
                email="no-trade@example.com",
                hashed_password=hash_password("secret"),
                broker_type="ibkr",
                encrypted_creds="enc",
                risk_params={"delta_threshold": 0.2},
                mode="confirmation",
                tier="basic",
                is_active=True,
            )
        )
        await db.commit()

        broker = MockBroker()
        await broker.connect()
        agent = TradingAgent(broker, db, AgentMemoryStore(), RiskGovernor())
        await agent.set_mode(client_id, "confirmation")
        result = await agent.chat(client_id, "Summarize current risk posture for next 30 minutes.")

        assert result["executed"] is False
        assert result.get("proposal_id") is None
        rows = await db.execute(Proposal.__table__.select())
        assert rows.first() is None


@pytest.mark.asyncio
async def test_confirmation_mode_handles_market_delta_query_without_proposal() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as db:
        client_id = uuid.uuid4()
        db.add(
            Client(
                id=client_id,
                email="delta-query@example.com",
                hashed_password=hash_password("secret"),
                broker_type="ibkr",
                encrypted_creds="enc",
                risk_params={"delta_threshold": 0.2},
                mode="confirmation",
                tier="basic",
                is_active=True,
            )
        )
        db.add(
            Instrument(
                symbol="ES",
                asset_class="future",
                exchange="CME",
                currency="USD",
                multiplier=50.0,
                tick_size=0.25,
                contract_rules={},
                aliases=["silver"],
                is_active=True,
            )
        )
        await db.commit()

        broker = MockBroker()
        await broker.connect()
        agent = TradingAgent(broker, db, AgentMemoryStore(), RiskGovernor())
        await agent.set_mode(client_id, "confirmation")
        result = await agent.chat(client_id, "Whats the price of silver delta 0.50 up and down?")

        assert result["executed"] is False
        assert "ES underlying" in result["message"]
        assert result.get("proposal_id") is None


@pytest.mark.asyncio
async def test_confirmation_mode_handles_relative_expiry_and_multileg_preview() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as db:
        client_id = uuid.uuid4()
        db.add(
            Client(
                id=client_id,
                email="multileg@example.com",
                hashed_password=hash_password("secret"),
                broker_type="ibkr",
                encrypted_creds="enc",
                risk_params={"delta_threshold": 0.2},
                mode="confirmation",
                tier="basic",
                is_active=True,
            )
        )
        db.add(
            Instrument(
                symbol="ES",
                asset_class="future",
                exchange="CME",
                currency="USD",
                multiplier=50.0,
                tick_size=0.25,
                contract_rules={},
                aliases=["silver"],
                is_active=True,
            )
        )
        await db.commit()

        broker = MockBroker()
        await broker.connect()
        agent = TradingAgent(broker, db, AgentMemoryStore(), RiskGovernor())
        await agent.set_mode(client_id, "confirmation")
        result = await agent.chat(
            client_id,
            "silver expiry 3 days from now find option with delta 0.50 up/down and sell 5 lots and buy 1 lot with delta 0.30",
        )

        assert result["executed"] is False
        assert "expiry" in result["message"]
        assert "SELL 5 lots" in result["message"]
        assert "BUY 1 lots" in result["message"]
        assert "delta| 0.30" in result["message"]
        assert result.get("proposal_id") is None


@pytest.mark.asyncio
async def test_resolve_decision_backend_accepts_supported_values() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as db:
        broker = MockBroker()
        await broker.connect()
        agent = TradingAgent(broker, db, AgentMemoryStore(), RiskGovernor())
        for backend_name in ("openrouter", "openai", "xai", "anthropic", "ollama", "deterministic"):
            backend = agent._resolve_decision_backend({"decision_backend": backend_name})
            assert backend == backend_name


@pytest.mark.asyncio
async def test_delta_query_parses_esmini_alias() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as db:
        client_id = uuid.uuid4()
        db.add(
            Client(
                id=client_id,
                email="esmini@example.com",
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
        agent = TradingAgent(broker, db, AgentMemoryStore(), RiskGovernor())
        result = await agent.chat(client_id, "Whats the strke for esmini delta 0.25 up and down?")

        assert result["executed"] is False
        assert "Nearest +0.25 call" in result["message"]
        assert "Nearest -0.25 put" in result["message"]
