from dataclasses import dataclass
from datetime import UTC, datetime, time
from typing import Any


class RiskViolation(Exception):
    def __init__(self, rule: str, reason: str) -> None:
        super().__init__(reason)
        self.rule = rule
        self.reason = reason


@dataclass
class RiskParameters:
    delta_threshold: float = 0.20
    max_size: int = 10
    max_loss: float = 5000.0
    max_open_positions: int = 20

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "RiskParameters":
        if not payload:
            return cls()
        return cls(
            delta_threshold=float(payload.get("delta_threshold", 0.20)),
            max_size=int(payload.get("max_size", 10)),
            max_loss=float(payload.get("max_loss", 5000.0)),
            max_open_positions=int(payload.get("max_open_positions", 20)),
        )


class RiskGovernor:
    def __init__(self) -> None:
        self._loss_streak: dict[str, list[float]] = {}

    def validate_order(
        self,
        client_id: str,
        order: dict[str, Any],
        net_delta: float,
        projected_delta: float | None,
        daily_pnl: float,
        open_legs: int,
        bid: float,
        ask: float,
        params: RiskParameters,
    ) -> None:
        effective_delta = projected_delta if projected_delta is not None else net_delta
        if abs(effective_delta) > params.delta_threshold:
            if abs(net_delta) <= params.delta_threshold or abs(effective_delta) >= abs(net_delta):
                raise RiskViolation(
                    "MAX_NET_DELTA",
                    f"net_delta={net_delta} projected_delta={effective_delta} threshold={params.delta_threshold}",
                )

        qty = int(order.get("qty", 0))
        if qty > params.max_size:
            raise RiskViolation("MAX_SINGLE_ORDER_SIZE", f"qty={qty} max={params.max_size}")

        if daily_pnl <= -abs(params.max_loss):
            raise RiskViolation("MAX_DAILY_LOSS", f"daily_pnl={daily_pnl} max_loss={params.max_loss}")

        if open_legs >= params.max_open_positions:
            raise RiskViolation(
                "MAX_OPEN_POSITIONS",
                f"open_legs={open_legs} max={params.max_open_positions}",
            )

        now_utc = datetime.now(UTC).time()
        if not self._is_market_hours(now_utc):
            raise RiskViolation("MARKET_HOURS", "Order attempted outside configured market hours")

        if bid > 0 and ask > 0:
            mid = (bid + ask) / 2
            spread_ratio = (ask - bid) / mid if mid else 1.0
            if spread_ratio > 0.15:
                raise RiskViolation("SPREAD_LIMIT", f"spread_ratio={spread_ratio:.4f} > 0.15")

        losses = self._loss_streak.get(client_id, [])
        if len(losses) >= 3 and all(loss <= -500 for loss in losses[-3:]):
            raise RiskViolation("CIRCUIT_BREAKER", "3 consecutive losses > $500 triggered halt")

    def register_trade_pnl(self, client_id: str, pnl: float) -> None:
        arr = self._loss_streak.setdefault(client_id, [])
        arr.append(pnl)
        if len(arr) > 10:
            del arr[:-10]

    @staticmethod
    def _is_market_hours(now_utc: time) -> bool:
        # Simple UTC windows approximating RTH + ETH for CME index futures options.
        # RTH/ETH detail should be instrument-calendar driven in production.
        return time(22, 0) <= now_utc or now_utc <= time(21, 0)
