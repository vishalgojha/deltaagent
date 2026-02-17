import uuid
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.brokers.base import BrokerBase
from backend.db.models import Trade
from backend.strategies.greeks import aggregate_portfolio_greeks
from backend.strategies.rebalancer import calculate_delta_hedge


class AgentTools:
    def __init__(self, broker: BrokerBase, db: AsyncSession) -> None:
        self._broker = broker
        self._db = db

    async def get_portfolio_greeks(self) -> dict[str, Any]:
        positions = await self._broker.get_positions()
        greeks = aggregate_portfolio_greeks(positions)
        return {"positions": positions, "net_greeks": greeks}

    async def get_options_chain(self, symbol: str, expiry: str | None) -> list[dict[str, Any]]:
        return await self._broker.get_options_chain(symbol=symbol, expiry=expiry)

    async def submit_order(
        self,
        action: str,
        symbol: str,
        instrument: str,
        qty: int,
        order_type: str,
        limit_price: float | None,
        strike: float | None = None,
        expiry: str | None = None,
    ) -> dict[str, Any]:
        result = await self._broker.submit_order(
            contract={
                "symbol": symbol,
                "instrument": instrument,
                "strike": strike,
                "expiry": expiry,
            },
            action=action,
            qty=qty,
            order_type=order_type,
            limit_price=limit_price,
        )
        return {
            "order_id": result.order_id,
            "status": result.status,
            "fill_price": result.fill_price,
        }

    async def get_market_data(self, symbol: str) -> dict[str, float]:
        return await self._broker.get_market_data(symbol)

    async def calculate_hedge(self, target_delta: float, current_delta: float) -> dict:
        return calculate_delta_hedge(target_delta=target_delta, current_delta=current_delta)

    async def get_trade_history(self, client_id: uuid.UUID, limit: int) -> list[Trade]:
        query = (
            select(Trade)
            .where(Trade.client_id == client_id)
            .order_by(desc(Trade.timestamp))
            .limit(limit)
        )
        result = await self._db.execute(query)
        return list(result.scalars().all())
