from collections.abc import Mapping
from typing import Any


AUTO_REMEDIATION_ACTIONS = {"none", "apply_conservative", "pause_autonomous"}

CONSERVATIVE_RISK_PRESET: dict[str, float | int] = {
    "delta_threshold": 0.1,
    "max_size": 5,
    "max_loss": 2500.0,
    "max_open_positions": 10,
    "execution_alert_slippage_warn_bps": 10.0,
    "execution_alert_slippage_critical_bps": 20.0,
    "execution_alert_latency_warn_ms": 2000,
    "execution_alert_latency_critical_ms": 5000,
    "execution_alert_fill_coverage_warn_pct": 85.0,
    "execution_alert_fill_coverage_critical_pct": 70.0,
}

DEFAULT_RISK_PARAMETERS: dict[str, Any] = {
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
    "auto_remediation_enabled": False,
    "auto_remediation_warning_action": "none",
    "auto_remediation_critical_action": "pause_autonomous",
    "auto_remediation_cooldown_minutes": 20,
    "auto_remediation_max_actions_per_hour": 2,
    "auto_remediation_last_outcome": "idle",
    "auto_remediation_last_reason": "",
    "auto_remediation_last_action": None,
    "auto_remediation_last_action_at": None,
    "auto_remediation_actions_last_hour": 0,
    "auto_remediation_window_started_at": None,
    "auto_remediation_last_alert_id": None,
    "auto_remediation_last_alert_severity": None,
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
        "auto_remediation_cooldown_minutes",
        "auto_remediation_max_actions_per_hour",
        "auto_remediation_actions_last_hour",
    }
    float_fields = {
        "delta_threshold",
        "max_loss",
        "execution_alert_slippage_warn_bps",
        "execution_alert_slippage_critical_bps",
        "execution_alert_fill_coverage_warn_pct",
        "execution_alert_fill_coverage_critical_pct",
    }
    bool_fields = {
        "auto_remediation_enabled",
    }
    action_fields = {
        "auto_remediation_warning_action",
        "auto_remediation_critical_action",
        "auto_remediation_last_action",
    }
    text_fields = {
        "auto_remediation_last_outcome",
        "auto_remediation_last_reason",
        "auto_remediation_last_action_at",
        "auto_remediation_window_started_at",
        "auto_remediation_last_alert_id",
        "auto_remediation_last_alert_severity",
    }
    for key, value in raw.items():
        if key in int_fields:
            merged[key] = _coerce_int(value, int(merged[key]))
        elif key in float_fields:
            merged[key] = _coerce_float(value, float(merged[key]))
        elif key in bool_fields:
            merged[key] = _coerce_bool(value, bool(merged[key]))
        elif key in action_fields:
            merged[key] = _coerce_action(value, str(merged[key]) if merged[key] is not None else "none")
        elif key in text_fields:
            merged[key] = _normalize_optional_text(value)
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


def _coerce_bool(value: object, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return fallback


def _coerce_action(value: object, fallback: str) -> str:
    normalized = _normalize_optional_text(value)
    if normalized is None:
        return fallback
    if normalized in AUTO_REMEDIATION_ACTIONS:
        return normalized
    return fallback


def _normalize_optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized if normalized else None
