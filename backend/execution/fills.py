import uuid
from datetime import datetime, timezone
from typing import Any

from backend.db.models import TradeFill


def compute_slippage_bps(action: str, fill_price: float, expected_price: float | None) -> float | None:
    if expected_price is None or expected_price <= 0:
        return None
    try:
        raw_bps = ((float(fill_price) - float(expected_price)) / float(expected_price)) * 10000.0
    except Exception:  # noqa: BLE001
        return None
    if str(action).upper() == "SELL":
        return -raw_bps
    return raw_bps


def estimate_expected_price(
    action: str,
    *,
    bid: float,
    ask: float,
    limit_price: float | None,
    fallback_price: Any = None,
) -> float | None:
    if limit_price is not None and float(limit_price) > 0:
        return float(limit_price)
    if bid > 0 and ask > 0:
        return (bid + ask) / 2.0
    if str(action).upper() == "BUY" and ask > 0:
        return ask
    if str(action).upper() == "SELL" and bid > 0:
        return bid
    fallback = _safe_float(fallback_price)
    return fallback if fallback > 0 else None


def build_trade_fill_from_order(
    *,
    client_id: uuid.UUID,
    trade_id: int,
    order_id: str | None,
    action: str,
    qty: int,
    order_payload: dict[str, Any],
    expected_price: float | None = None,
) -> TradeFill | None:
    fill_price_raw = order_payload.get("fill_price")
    fill_price = _safe_float(fill_price_raw)
    if fill_price <= 0:
        return None

    if expected_price is None:
        expected_price = _safe_float(order_payload.get("expected_price")) or None
    slippage_bps = compute_slippage_bps(action, fill_price, expected_price)

    broker_fill_id = order_payload.get("broker_fill_id")
    broker_fill_id_value = str(broker_fill_id) if broker_fill_id is not None else None

    raw_payload = order_payload.get("raw_payload")
    if not isinstance(raw_payload, dict):
        raw_payload = order_payload if isinstance(order_payload, dict) else {"value": str(order_payload)}

    realized_pnl_raw = order_payload.get("realized_pnl", order_payload.get("pnl"))
    realized_pnl = _safe_float(realized_pnl_raw) if realized_pnl_raw is not None else None
    fees = _safe_float(order_payload.get("fees", 0.0))
    fill_timestamp = _coerce_timestamp(order_payload.get("fill_timestamp"))
    status = str(order_payload.get("status", "filled"))

    return TradeFill(
        client_id=client_id,
        trade_id=trade_id,
        order_id=order_id,
        broker_fill_id=broker_fill_id_value,
        status=status,
        qty=max(abs(int(qty)), 1),
        fill_price=fill_price,
        expected_price=expected_price,
        slippage_bps=slippage_bps,
        fees=fees,
        realized_pnl=realized_pnl,
        fill_timestamp=fill_timestamp,
        raw_payload=raw_payload,
    )


def _coerce_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except Exception:  # noqa: BLE001
        return 0.0
