import uuid
from datetime import datetime, timezone
from statistics import mean, median
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import assert_client_scope, get_current_client
from backend.db.models import AuditLog, Client, Trade, TradeFill
from backend.db.session import get_db_session
from backend.execution.fills import compute_slippage_bps
from backend.risk_defaults import AUTO_REMEDIATION_ACTIONS, CONSERVATIVE_RISK_PRESET, merge_risk_parameters
from backend.schemas import (
    AutoRemediationStatusOut,
    ExecutionQualityOut,
    IncidentNoteCreateRequest,
    IncidentNoteOut,
    TradeFillIngestRequest,
    TradeFillOut,
    TradeOut,
)


router = APIRouter(prefix="/clients", tags=["trades"])
FILLED_STATUSES = {"filled", "partially_filled", "completed"}
ALERT_SEVERITY_SCORE = {"warning": 1, "critical": 2}


@router.get("/{id}/trades", response_model=list[TradeOut])
async def get_trades(
    id: uuid.UUID,
    limit: int = 100,
    current_client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db_session),
) -> list[TradeOut]:
    assert_client_scope(id, current_client)
    rows = await db.execute(
        select(Trade).where(Trade.client_id == id).order_by(desc(Trade.timestamp)).limit(limit)
    )
    return [TradeOut.model_validate(row) for row in rows.scalars().all()]


@router.post("/{id}/trades/{trade_id}/fills", response_model=TradeFillOut)
async def ingest_trade_fill(
    id: uuid.UUID,
    trade_id: int,
    payload: TradeFillIngestRequest,
    idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key"),
    current_client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db_session),
) -> TradeFillOut:
    assert_client_scope(id, current_client)
    trade = await db.get(Trade, trade_id)
    if trade is None or trade.client_id != id:
        raise HTTPException(status_code=404, detail="Trade not found")

    normalized_idempotency_key = _normalize_optional_text(idempotency_key_header or payload.idempotency_key)
    normalized_broker_fill_id = _normalize_optional_text(payload.broker_fill_id)
    existing_fill = await _find_existing_fill(
        db,
        client_id=id,
        trade_id=trade_id,
        idempotency_key=normalized_idempotency_key,
        broker_fill_id=normalized_broker_fill_id,
    )
    if existing_fill is not None:
        return TradeFillOut.model_validate(existing_fill)

    existing_rows = await db.execute(
        select(TradeFill.qty, TradeFill.fill_price).where(
            TradeFill.client_id == id,
            TradeFill.trade_id == trade_id,
        )
    )
    existing_fills = list(existing_rows.all())

    expected_price = payload.expected_price if payload.expected_price is not None else trade.fill_price
    slippage_bps = compute_slippage_bps(trade.action, payload.fill_price, expected_price)
    fill_timestamp = payload.fill_timestamp or datetime.now(timezone.utc)

    fill = TradeFill(
        client_id=id,
        trade_id=trade_id,
        order_id=trade.order_id,
        broker_fill_id=normalized_broker_fill_id,
        ingest_idempotency_key=normalized_idempotency_key,
        status=payload.status,
        qty=payload.qty,
        fill_price=payload.fill_price,
        expected_price=expected_price,
        slippage_bps=slippage_bps,
        fees=float(payload.fees),
        realized_pnl=payload.realized_pnl,
        fill_timestamp=fill_timestamp,
        raw_payload=payload.raw_payload,
    )
    db.add(fill)

    trade.status = payload.status
    total_qty = int(payload.qty) + sum(int(row.qty) for row in existing_fills)
    total_notional = (float(payload.fill_price) * int(payload.qty)) + sum(
        float(row.fill_price) * int(row.qty) for row in existing_fills
    )
    trade.fill_price = (total_notional / total_qty) if total_qty > 0 else payload.fill_price
    if payload.realized_pnl is not None:
        trade.pnl = payload.realized_pnl

    db.add(
        AuditLog(
            client_id=id,
            event_type="trade_fill_ingested",
            details={
                "trade_id": trade_id,
                "order_id": trade.order_id,
                "status": payload.status,
                "qty": payload.qty,
                "fill_price": payload.fill_price,
                "slippage_bps": slippage_bps,
                "broker_fill_id": normalized_broker_fill_id,
                "idempotency_key": normalized_idempotency_key,
            },
        )
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing_fill = await _find_existing_fill(
            db,
            client_id=id,
            trade_id=trade_id,
            idempotency_key=normalized_idempotency_key,
            broker_fill_id=normalized_broker_fill_id,
        )
        if existing_fill is not None:
            return TradeFillOut.model_validate(existing_fill)
        raise HTTPException(status_code=409, detail="Duplicate fill ingest conflict")

    await db.refresh(fill)
    return TradeFillOut.model_validate(fill)


@router.get("/{id}/trades/{trade_id}/fills", response_model=list[TradeFillOut])
async def get_trade_fills(
    id: uuid.UUID,
    trade_id: int,
    limit: int = Query(default=200, ge=1, le=1000),
    current_client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db_session),
) -> list[TradeFillOut]:
    assert_client_scope(id, current_client)
    trade = await db.get(Trade, trade_id)
    if trade is None or trade.client_id != id:
        raise HTTPException(status_code=404, detail="Trade not found")

    rows = await db.execute(
        select(TradeFill)
        .where(TradeFill.client_id == id, TradeFill.trade_id == trade_id)
        .order_by(desc(TradeFill.fill_timestamp), desc(TradeFill.id))
        .limit(limit)
    )
    return [TradeFillOut.model_validate(item) for item in rows.scalars().all()]


@router.get("/{id}/metrics/execution-quality", response_model=ExecutionQualityOut)
async def get_execution_quality(
    id: uuid.UUID,
    from_ts: datetime | None = Query(default=None, alias="from"),
    to_ts: datetime | None = Query(default=None, alias="to"),
    backfill_missing: bool = Query(default=True),
    current_client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db_session),
) -> ExecutionQualityOut:
    assert_client_scope(id, current_client)
    now = datetime.now(timezone.utc)
    target_client = current_client if isinstance(current_client, Client) else await db.get(Client, id)
    raw_risk_params = dict(getattr(target_client, "risk_params", None) or getattr(current_client, "risk_params", {}) or {})
    current_mode = str(getattr(target_client, "mode", None) or getattr(current_client, "mode", None) or "confirmation")
    merged_risk_params = merge_risk_parameters(raw_risk_params)

    stmt = select(Trade).where(Trade.client_id == id)
    if from_ts is not None:
        stmt = stmt.where(Trade.timestamp >= from_ts)
    if to_ts is not None:
        stmt = stmt.where(Trade.timestamp <= to_ts)
    trade_rows = await db.execute(stmt.order_by(desc(Trade.timestamp)).limit(5000))
    trades = list(trade_rows.scalars().all())
    fills: list[TradeFill] = []
    backfilled_trade_ids: set[int] = set()
    avg_slippage: float | None = None
    median_slippage: float | None = None
    avg_first_fill_latency_ms: float | None = None
    trades_with_fills = 0

    if trades:
        trade_ids = [trade.id for trade in trades]
        fills_stmt = select(TradeFill).where(TradeFill.client_id == id, TradeFill.trade_id.in_(trade_ids))
        if from_ts is not None:
            fills_stmt = fills_stmt.where(TradeFill.fill_timestamp >= from_ts)
        if to_ts is not None:
            fills_stmt = fills_stmt.where(TradeFill.fill_timestamp <= to_ts)
        fill_rows = await db.execute(fills_stmt.order_by(TradeFill.fill_timestamp.asc(), TradeFill.id.asc()))
        fills = list(fill_rows.scalars().all())

        if backfill_missing:
            filled_trade_ids = {fill.trade_id for fill in fills}
            for trade in trades:
                if trade.id in filled_trade_ids:
                    continue
                if str(trade.status).lower() not in FILLED_STATUSES:
                    continue
                if trade.fill_price is None:
                    continue
                if int(trade.qty) <= 0:
                    continue
                backfilled_trade_ids.add(trade.id)

        slippages = [float(fill.slippage_bps) for fill in fills if fill.slippage_bps is not None]
        if backfilled_trade_ids:
            # Backfilled trades represent known executions from legacy data with no fill event rows.
            slippages.extend([0.0] * len(backfilled_trade_ids))
        avg_slippage = float(mean(slippages)) if slippages else None
        median_slippage = float(median(slippages)) if slippages else None

        trade_by_id = {trade.id: trade for trade in trades}
        first_fill_latency_ms: list[float] = []
        seen_trades: set[int] = set()
        for fill in fills:
            if fill.trade_id in seen_trades:
                continue
            trade = trade_by_id.get(fill.trade_id)
            if trade is None:
                continue
            fill_ts = _as_utc(fill.fill_timestamp)
            trade_ts = _as_utc(trade.timestamp)
            latency_ms = max((fill_ts - trade_ts).total_seconds() * 1000.0, 0.0)
            first_fill_latency_ms.append(latency_ms)
            seen_trades.add(fill.trade_id)

        if backfilled_trade_ids:
            first_fill_latency_ms.extend([0.0] * len(backfilled_trade_ids))

        avg_first_fill_latency_ms = float(mean(first_fill_latency_ms)) if first_fill_latency_ms else None
        trades_with_fills = len({fill.trade_id for fill in fills}.union(backfilled_trade_ids))

    execution_alerts = _build_execution_alerts(
        trades_total=len(trades),
        trades_with_fills=trades_with_fills,
        avg_slippage_bps=avg_slippage,
        avg_first_fill_latency_ms=avg_first_fill_latency_ms,
        risk_parameters=merged_risk_params,
    )
    auto_remediation, next_mode, next_risk_params, audit_details = _evaluate_auto_remediation_policy(
        current_mode=current_mode,
        raw_risk_params=raw_risk_params,
        merged_risk_params=merged_risk_params,
        alerts=execution_alerts,
        now=now,
    )
    if target_client is not None and (next_mode != current_mode or next_risk_params != raw_risk_params):
        target_client.mode = next_mode
        target_client.risk_params = next_risk_params
        db.add(target_client)
        if audit_details is not None:
            db.add(
                AuditLog(
                    client_id=id,
                    event_type="execution_auto_remediation_executed",
                    risk_rule_triggered=str(audit_details.get("alert_id") or "unknown"),
                    details=audit_details,
                )
            )
        await db.commit()

    return ExecutionQualityOut(
        client_id=id,
        window_start=from_ts,
        window_end=to_ts,
        trades_total=len(trades),
        trades_with_fills=trades_with_fills,
        fill_events=len(fills) + len(backfilled_trade_ids),
        backfilled_trades=len(backfilled_trade_ids),
        backfilled_fill_events=len(backfilled_trade_ids),
        avg_slippage_bps=avg_slippage,
        median_slippage_bps=median_slippage,
        avg_first_fill_latency_ms=avg_first_fill_latency_ms,
        auto_remediation=auto_remediation,
        generated_at=now,
    )


@router.post("/{id}/metrics/incidents", response_model=IncidentNoteOut)
async def create_incident_note(
    id: uuid.UUID,
    payload: IncidentNoteCreateRequest,
    current_client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db_session),
) -> IncidentNoteOut:
    assert_client_scope(id, current_client)
    row = AuditLog(
        client_id=id,
        event_type="execution_alert_incident",
        risk_rule_triggered=payload.alert_id,
        details={
            "alert_id": payload.alert_id,
            "severity": payload.severity,
            "label": payload.label,
            "note": payload.note,
            "context": payload.context,
        },
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _to_incident_note_out(row)


@router.get("/{id}/metrics/incidents", response_model=list[IncidentNoteOut])
async def list_incident_notes(
    id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=500),
    current_client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db_session),
) -> list[IncidentNoteOut]:
    assert_client_scope(id, current_client)
    rows = await db.execute(
        select(AuditLog)
        .where(
            AuditLog.client_id == id,
            AuditLog.event_type == "execution_alert_incident",
        )
        .order_by(desc(AuditLog.timestamp), desc(AuditLog.id))
        .limit(limit)
    )
    return [_to_incident_note_out(row) for row in rows.scalars().all()]


def _build_execution_alerts(
    *,
    trades_total: int,
    trades_with_fills: int,
    avg_slippage_bps: float | None,
    avg_first_fill_latency_ms: float | None,
    risk_parameters: dict[str, Any],
) -> list[dict[str, str]]:
    slippage_warn_bps = max(_coerce_float(risk_parameters.get("execution_alert_slippage_warn_bps"), 15.0), 0.1)
    slippage_critical_bps = max(
        _coerce_float(risk_parameters.get("execution_alert_slippage_critical_bps"), 30.0),
        slippage_warn_bps,
    )
    latency_warn_ms = max(_coerce_float(risk_parameters.get("execution_alert_latency_warn_ms"), 3000.0), 1.0)
    latency_critical_ms = max(
        _coerce_float(risk_parameters.get("execution_alert_latency_critical_ms"), 8000.0),
        latency_warn_ms,
    )
    fill_warn_pct = min(max(_coerce_float(risk_parameters.get("execution_alert_fill_coverage_warn_pct"), 75.0), 1.0), 100.0)
    fill_critical_pct = min(
        max(_coerce_float(risk_parameters.get("execution_alert_fill_coverage_critical_pct"), 50.0), 1.0),
        fill_warn_pct,
    )

    alerts: list[dict[str, str]] = []
    avg_slippage_abs = abs(avg_slippage_bps) if avg_slippage_bps is not None else None
    if avg_slippage_abs is not None and avg_slippage_abs >= slippage_warn_bps:
        alerts.append(
            {
                "id": "avg-slippage",
                "severity": "critical" if avg_slippage_abs >= slippage_critical_bps else "warning",
                "label": "Slippage",
            }
        )

    if avg_first_fill_latency_ms is not None and avg_first_fill_latency_ms >= latency_warn_ms:
        alerts.append(
            {
                "id": "first-fill-latency",
                "severity": "critical" if avg_first_fill_latency_ms >= latency_critical_ms else "warning",
                "label": "Latency",
            }
        )

    if trades_total > 0:
        fill_coverage_pct = (float(trades_with_fills) / float(trades_total)) * 100.0
        if fill_coverage_pct < fill_warn_pct:
            alerts.append(
                {
                    "id": "fill-coverage",
                    "severity": "critical" if fill_coverage_pct < fill_critical_pct else "warning",
                    "label": "Fill Coverage",
                }
            )
    return alerts


def _evaluate_auto_remediation_policy(
    *,
    current_mode: str,
    raw_risk_params: dict[str, Any],
    merged_risk_params: dict[str, Any],
    alerts: list[dict[str, str]],
    now: datetime,
) -> tuple[AutoRemediationStatusOut, str, dict[str, Any], dict[str, Any] | None]:
    updated_risk_params = dict(raw_risk_params)
    next_mode = current_mode
    audit_details: dict[str, Any] | None = None

    enabled = bool(merged_risk_params.get("auto_remediation_enabled", False))
    cooldown_minutes = max(_coerce_int(merged_risk_params.get("auto_remediation_cooldown_minutes"), 20), 0)
    max_actions_per_hour = max(_coerce_int(merged_risk_params.get("auto_remediation_max_actions_per_hour"), 2), 1)
    actions_last_hour = max(_coerce_int(merged_risk_params.get("auto_remediation_actions_last_hour"), 0), 0)
    window_started_at = _parse_timestamp(merged_risk_params.get("auto_remediation_window_started_at"))
    if window_started_at is None or (now - window_started_at).total_seconds() >= 3600.0:
        actions_last_hour = 0
        window_started_at = now

    last_action = _normalize_action(merged_risk_params.get("auto_remediation_last_action"))
    last_action_at = _parse_timestamp(merged_risk_params.get("auto_remediation_last_action_at"))
    cooldown_remaining_seconds = _cooldown_remaining_seconds(last_action_at, now, cooldown_minutes)

    alert = _pick_primary_alert(alerts)
    active_alert_id = alert["id"] if alert is not None else None
    active_alert_severity = alert["severity"] if alert is not None else None

    if alert is None:
        planned_action = "none"
        outcome = "no_alert"
        message = "No active execution alerts."
    else:
        policy_key = "auto_remediation_critical_action" if alert["severity"] == "critical" else "auto_remediation_warning_action"
        planned_action = _normalize_action(merged_risk_params.get(policy_key))
        if not enabled:
            outcome = "disabled"
            message = "Auto-remediation is disabled."
        elif planned_action == "none":
            outcome = "no_action"
            message = f"Alert {alert['id']} has no configured remediation action."
        elif actions_last_hour >= max_actions_per_hour:
            outcome = "rate_limited"
            message = f"Suppressed by hourly guardrail ({actions_last_hour}/{max_actions_per_hour})."
        elif cooldown_remaining_seconds > 0:
            outcome = "cooldown"
            message = f"Suppressed by cooldown ({cooldown_remaining_seconds}s remaining)."
        else:
            if planned_action == "pause_autonomous":
                if current_mode == "autonomous":
                    next_mode = "confirmation"
                    outcome = "executed"
                    message = f"Paused autonomous mode after {alert['id']} alert."
                else:
                    outcome = "noop"
                    message = "Autonomous mode is already paused."
            elif planned_action == "apply_conservative":
                changed = False
                for key, value in CONSERVATIVE_RISK_PRESET.items():
                    if updated_risk_params.get(key) != value:
                        changed = True
                    updated_risk_params[key] = value
                if changed:
                    outcome = "executed"
                    message = f"Applied conservative preset after {alert['id']} alert."
                else:
                    outcome = "noop"
                    message = "Conservative preset is already active."
            else:
                outcome = "no_action"
                message = f"Unsupported remediation action '{planned_action}' configured."

            if outcome == "executed":
                actions_last_hour += 1
                last_action = planned_action
                last_action_at = now
                cooldown_remaining_seconds = _cooldown_remaining_seconds(last_action_at, now, cooldown_minutes)
                audit_details = {
                    "alert_id": active_alert_id,
                    "severity": active_alert_severity,
                    "action": planned_action,
                    "message": message,
                    "mode_before": current_mode,
                    "mode_after": next_mode,
                    "actions_last_hour": actions_last_hour,
                    "max_actions_per_hour": max_actions_per_hour,
                    "cooldown_minutes": cooldown_minutes,
                    "evaluated_at": now.isoformat(),
                }

    persisted_last_action = last_action if last_action != "none" else None

    updated_risk_params["auto_remediation_actions_last_hour"] = actions_last_hour
    updated_risk_params["auto_remediation_window_started_at"] = _to_iso_or_none(window_started_at)
    updated_risk_params["auto_remediation_last_action"] = persisted_last_action
    updated_risk_params["auto_remediation_last_action_at"] = _to_iso_or_none(last_action_at)
    updated_risk_params["auto_remediation_last_alert_id"] = active_alert_id
    updated_risk_params["auto_remediation_last_alert_severity"] = active_alert_severity
    updated_risk_params["auto_remediation_last_outcome"] = outcome
    updated_risk_params["auto_remediation_last_reason"] = message

    return (
        AutoRemediationStatusOut(
            enabled=enabled,
            active_alert_id=active_alert_id,
            active_alert_severity=active_alert_severity if active_alert_severity in ALERT_SEVERITY_SCORE else None,
            planned_action=planned_action,
            outcome=outcome,
            message=message,
            cooldown_minutes=cooldown_minutes,
            cooldown_remaining_seconds=cooldown_remaining_seconds,
            actions_last_hour=actions_last_hour,
            max_actions_per_hour=max_actions_per_hour,
            last_action=persisted_last_action,
            last_action_at=last_action_at,
        ),
        next_mode,
        updated_risk_params,
        audit_details,
    )


def _pick_primary_alert(alerts: list[dict[str, str]]) -> dict[str, str] | None:
    selected: dict[str, str] | None = None
    selected_score = -1
    for alert in alerts:
        score = ALERT_SEVERITY_SCORE.get(str(alert.get("severity")), 0)
        if score > selected_score:
            selected = alert
            selected_score = score
    return selected


def _normalize_action(value: object) -> str:
    if value is None:
        return "none"
    normalized = str(value).strip().lower()
    if normalized in AUTO_REMEDIATION_ACTIONS:
        return normalized
    return "none"


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


def _cooldown_remaining_seconds(last_action_at: datetime | None, now: datetime, cooldown_minutes: int) -> int:
    if last_action_at is None or cooldown_minutes <= 0:
        return 0
    elapsed = (now - last_action_at).total_seconds()
    remaining = (cooldown_minutes * 60) - elapsed
    return int(remaining) if remaining > 0 else 0


def _parse_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _as_utc(value)
    raw = str(value).strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        return _as_utc(datetime.fromisoformat(raw))
    except ValueError:
        return None


def _to_iso_or_none(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _as_utc(value).isoformat()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def _find_existing_fill(
    db: AsyncSession,
    *,
    client_id: uuid.UUID,
    trade_id: int,
    idempotency_key: str | None,
    broker_fill_id: str | None,
) -> TradeFill | None:
    if idempotency_key:
        rows = await db.execute(
            select(TradeFill)
            .where(
                TradeFill.client_id == client_id,
                TradeFill.trade_id == trade_id,
                TradeFill.ingest_idempotency_key == idempotency_key,
            )
            .order_by(desc(TradeFill.id))
            .limit(1)
        )
        existing = rows.scalar_one_or_none()
        if existing is not None:
            return existing

    if broker_fill_id:
        rows = await db.execute(
            select(TradeFill)
            .where(
                TradeFill.client_id == client_id,
                TradeFill.trade_id == trade_id,
                TradeFill.broker_fill_id == broker_fill_id,
            )
            .order_by(desc(TradeFill.id))
            .limit(1)
        )
        existing = rows.scalar_one_or_none()
        if existing is not None:
            return existing
    return None


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized if normalized else None


def _to_incident_note_out(row: AuditLog) -> IncidentNoteOut:
    details = row.details if isinstance(row.details, dict) else {}
    context = details.get("context")
    return IncidentNoteOut(
        id=row.id,
        client_id=row.client_id,
        alert_id=str(details.get("alert_id") or row.risk_rule_triggered or "unknown"),
        severity="critical" if str(details.get("severity")).lower() == "critical" else "warning",
        label=str(details.get("label") or "Execution Alert"),
        note=str(details.get("note") or ""),
        context=context if isinstance(context, dict) else {},
        created_at=row.timestamp,
    )
