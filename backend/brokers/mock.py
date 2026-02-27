import asyncio
import random
from collections.abc import Callable
from typing import Any

from backend.brokers.base import BrokerBase, BrokerOrderResult


class MockBroker(BrokerBase):
    def __init__(self, credentials: dict | None = None) -> None:
        self._credentials = credentials or {}
        self._connected = False
        raw_positions = self._credentials.get("mock_positions", [])
        self._positions: list[dict[str, Any]] = list(raw_positions) if isinstance(raw_positions, list) else []
        self._next_order = 1000

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def get_positions(self) -> list[dict[str, Any]]:
        return list(self._positions)

    async def get_greeks(self, contract: dict[str, Any]) -> dict[str, float]:
        strike = float(contract.get("strike", 0))
        return {
            "delta": max(min((strike - 5000) / 1000.0, 1), -1),
            "gamma": 0.01,
            "theta": -0.05,
            "vega": 0.15,
        }

    async def get_options_chain(self, symbol: str, expiry: str | None = None) -> list[dict[str, Any]]:
        base = 5000 if symbol == "ES" else 18000
        chain = []
        for offset in range(-4, 5):
            strike = base + offset * 50
            chain.append(
                {
                    "symbol": symbol,
                    "expiry": expiry or "2026-03-20",
                    "strike": strike,
                    "call_delta": round(0.5 - offset * 0.05, 3),
                    "put_delta": round(-0.5 - offset * 0.05, 3),
                    "gamma": 0.01,
                    "theta": -0.06,
                    "vega": 0.12,
                }
            )
        return chain

    async def get_market_data(self, symbol: str) -> dict[str, float]:
        underlying = 5000.0 if symbol == "ES" else 18000.0
        return {
            "underlying_price": underlying + random.uniform(-10, 10),
            "iv_rank": 45.0,
            "iv_percentile": 58.0,
            "bid": 10.0,
            "ask": 10.5,
        }

    async def submit_order(
        self,
        contract: dict[str, Any],
        action: str,
        qty: int,
        order_type: str,
        limit_price: float | None = None,
    ) -> BrokerOrderResult:
        self._next_order += 1
        fill_price = limit_price or 10.25
        expected_price = limit_price if limit_price is not None else 10.20
        position = {
            "symbol": contract.get("symbol", "ES"),
            "instrument_type": contract.get("instrument", "FOP"),
            "strike": contract.get("strike"),
            "expiry": contract.get("expiry"),
            "qty": qty if action.upper() == "BUY" else -qty,
            "delta": contract.get("delta", 0.0),
            "gamma": contract.get("gamma", 0.0),
            "theta": contract.get("theta", 0.0),
            "vega": contract.get("vega", 0.0),
            "avg_price": fill_price,
        }
        self._positions.append(position)
        return BrokerOrderResult(
            order_id=str(self._next_order),
            status="filled",
            fill_price=fill_price,
            broker_fill_id=f"mock-fill-{self._next_order}",
            expected_price=expected_price,
            fees=0.0,
            realized_pnl=0.0,
            raw_payload={"broker": "mock", "position": position},
        )

    async def stream_greeks(self, callback: Callable[[dict[str, Any]], Any]) -> None:
        while self._connected:
            await callback(
                {
                    "symbol": "ES",
                    "delta": random.uniform(-0.2, 0.2),
                    "gamma": random.uniform(0.01, 0.03),
                    "theta": random.uniform(-0.1, -0.02),
                    "vega": random.uniform(0.1, 0.3),
                }
            )
            await asyncio.sleep(1.0)

    async def submit_combo_order(
        self,
        symbol: str,
        legs: list[dict[str, Any]],
        qty: int,
        order_type: str,
        limit_price: float | None = None,
        action: str = "BUY",
    ) -> dict[str, Any]:
        self._next_order += 1
        return {
            "order_id": str(self._next_order),
            "status": "filled",
            "fill_price": limit_price or 0.0,
            "expected_price": limit_price or 0.0,
            "broker_fill_id": f"mock-combo-fill-{self._next_order}",
            "timestamp": asyncio.get_event_loop().time(),
            "symbol": symbol,
            "legs": legs,
            "qty": qty,
            "action": action,
            "order_type": order_type,
        }
