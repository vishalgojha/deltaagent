import uuid
from datetime import datetime, timezone
from statistics import mean, median

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import assert_client_scope, get_current_client
from backend.db.models import AuditLog, Client, Trade, TradeFill
from backend.db.session import get_db_session
from backend.execution.fills import compute_slippage_bps
from backend.schemas import (
    ExecutionQualityOut,
    IncidentNoteCreateRequest,
    IncidentNoteOut,
    TradeFillIngestRequest,
    TradeFillOut,
    TradeOut,
)


router = APIRouter(prefix="/clients", tags=["trades"])
FILLED_STATUSES = {"filled", "partially_filled", "completed"}


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

    stmt = select(Trade).where(Trade.client_id == id)
    if from_ts is not None:
        stmt = stmt.where(Trade.timestamp >= from_ts)
    if to_ts is not None:
        stmt = stmt.where(Trade.timestamp <= to_ts)
    trade_rows = await db.execute(stmt.order_by(desc(Trade.timestamp)).limit(5000))
    trades = list(trade_rows.scalars().all())
    if not trades:
        return ExecutionQualityOut(
            client_id=id,
            window_start=from_ts,
            window_end=to_ts,
            trades_total=0,
            trades_with_fills=0,
            fill_events=0,
            backfilled_trades=0,
            backfilled_fill_events=0,
            avg_slippage_bps=None,
            median_slippage_bps=None,
            avg_first_fill_latency_ms=None,
            generated_at=datetime.now(timezone.utc),
        )

    trade_ids = [trade.id for trade in trades]
    fills_stmt = select(TradeFill).where(TradeFill.client_id == id, TradeFill.trade_id.in_(trade_ids))
    if from_ts is not None:
        fills_stmt = fills_stmt.where(TradeFill.fill_timestamp >= from_ts)
    if to_ts is not None:
        fills_stmt = fills_stmt.where(TradeFill.fill_timestamp <= to_ts)
    fill_rows = await db.execute(fills_stmt.order_by(TradeFill.fill_timestamp.asc(), TradeFill.id.asc()))
    fills = list(fill_rows.scalars().all())

    backfilled_trade_ids: set[int] = set()
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
        generated_at=datetime.now(timezone.utc),
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
