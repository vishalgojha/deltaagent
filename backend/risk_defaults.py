from collections.abc import Mapping
from typing import Any


DEFAULT_RISK_PARAMETERS: dict[str, float | int] = {
    "delta_threshold": 0.2,
    "max_size": 10,
    "max_loss": 5000.0,
    "max_open_positions": 20,
    "execution_alert_slippage_warn_bps": 15.0,
    "execution_alert_slippage_critical_bps": 30.0,
    "execution_alert_latency_warn_ms": 3000,
    "execution_alert_latency_critical_ms": 8000,
    "execution_alert_fill_coverage_warn_pct": 75.0,
    "execution_alert_fill_coverage_critical_pct": 50.0,
}


def merge_risk_parameters(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    merged: dict[str, Any] = dict(DEFAULT_RISK_PARAMETERS)
    if raw is None:
        return merged

    int_fields = {
        "max_size",
        "max_open_positions",
        "execution_alert_latency_warn_ms",
        "execution_alert_latency_critical_ms",
    }
    float_fields = {
        "delta_threshold",
        "max_loss",
        "execution_alert_slippage_warn_bps",
        "execution_alert_slippage_critical_bps",
        "execution_alert_fill_coverage_warn_pct",
        "execution_alert_fill_coverage_critical_pct",
    }
    for key, value in raw.items():
        if key in int_fields:
            merged[key] = _coerce_int(value, int(merged[key]))
        elif key in float_fields:
            merged[key] = _coerce_float(value, float(merged[key]))
        else:
            merged[key] = value
    return merged


def _coerce_int(value: object, fallback: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except Exception:  # noqa: BLE001
        return fallback


def _coerce_float(value: object, fallback: float) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except Exception:  # noqa: BLE001
        return fallback
