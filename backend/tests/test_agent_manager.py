import uuid
from typing import Any

import pytest

from backend.agent.manager import AgentManager
from backend.brokers.base import BrokerBase, BrokerOrderResult


class _FakeBroker(BrokerBase):
    def __init__(self) -> None:
        self.connected = False
        self.disconnected = False

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.disconnected = True

    async def get_positions(self) -> list[dict[str, Any]]:
        return []

    async def get_greeks(self, contract: dict[str, Any]) -> dict[str, float]:
        del contract
        return {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}

    async def get_options_chain(self, symbol: str, expiry: str | None = None) -> list[dict[str, Any]]:
        del symbol, expiry
        return []

    async def get_market_data(self, symbol: str) -> dict[str, float]:
        del symbol
        return {"underlying_price": 0.0, "iv_rank": 0.0, "iv_percentile": 0.0, "bid": 0.0, "ask": 0.0}

    async def submit_order(
        self,
        contract: dict[str, Any],
        action: str,
        qty: int,
        order_type: str,
        limit_price: float | None = None,
    ) -> BrokerOrderResult:
        del contract, action, qty, order_type, limit_price
        return BrokerOrderResult(order_id="OID", status="submitted", fill_price=None)

    async def stream_greeks(self, callback):  # noqa: ANN001
        del callback
        return None


@pytest.mark.asyncio
async def test_force_recreate_disconnects_existing_broker(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[_FakeBroker] = []

    def _build_broker(**kwargs: Any) -> _FakeBroker:
        del kwargs
        broker = _FakeBroker()
        created.append(broker)
        return broker

    monkeypatch.setattr("backend.agent.manager.build_broker", _build_broker)
    manager = AgentManager()
    client_id = uuid.uuid4()

    await manager.get_agent(
        client_id=client_id,
        broker_type="ibkr",
        broker_credentials={},
        db=None,  # type: ignore[arg-type]
    )
    await manager.get_agent(
        client_id=client_id,
        broker_type="ibkr",
        broker_credentials={},
        db=None,  # type: ignore[arg-type]
        force_recreate_broker=True,
    )

    assert len(created) == 2
    assert created[0].disconnected is True
    assert created[1].connected is True
