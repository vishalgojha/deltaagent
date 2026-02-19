from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_client, set_admin_db_context
from backend.db.models import Client, Instrument, StrategyProfile
from backend.db.session import get_db_session
from backend.reference.seed_data import default_instruments, default_strategy_profiles
from backend.schemas import InstrumentOut, StrategyProfileOut


router = APIRouter(prefix="/reference", tags=["reference"])


@router.get("/instruments", response_model=list[InstrumentOut])
async def list_instruments(
    asset_class: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    is_active: bool = Query(default=True),
    limit: int = Query(default=500, ge=1, le=5000),
    _: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db_session),
) -> list[InstrumentOut]:
    stmt = select(Instrument).where(Instrument.is_active == is_active)
    if asset_class:
        stmt = stmt.where(Instrument.asset_class == asset_class.lower())
    if symbol:
        stmt = stmt.where(Instrument.symbol == symbol.upper())
    stmt = stmt.order_by(Instrument.asset_class, Instrument.symbol).limit(limit)
    rows = await db.execute(stmt)
    return [InstrumentOut.model_validate(item) for item in rows.scalars().all()]


@router.get("/strategies", response_model=list[StrategyProfileOut])
async def list_strategies(
    is_active: bool = Query(default=True),
    limit: int = Query(default=200, ge=1, le=1000),
    _: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db_session),
) -> list[StrategyProfileOut]:
    stmt = select(StrategyProfile).where(StrategyProfile.is_active == is_active).order_by(StrategyProfile.strategy_id).limit(limit)
    rows = await db.execute(stmt)
    return [StrategyProfileOut.model_validate(item) for item in rows.scalars().all()]


@router.post("/seed-defaults")
async def seed_reference_defaults(
    reset: bool = Query(default=False),
    _: str = Depends(set_admin_db_context),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    if reset:
        await db.execute(delete(Instrument))
        await db.execute(delete(StrategyProfile))

    instruments = default_instruments()
    strategies = default_strategy_profiles()

    inserted_instruments = 0
    inserted_strategies = 0

    existing_instruments = await db.execute(
        select(Instrument.symbol, Instrument.asset_class, Instrument.exchange)
    )
    existing_instrument_keys = {(s, a, e) for s, a, e in existing_instruments.all()}
    for payload in instruments:
        key = (payload["symbol"], payload["asset_class"], payload["exchange"])
        if key in existing_instrument_keys:
            continue
        db.add(Instrument(**payload))
        inserted_instruments += 1

    existing_strategies = await db.execute(select(StrategyProfile.strategy_id))
    existing_strategy_ids = {row[0] for row in existing_strategies.all()}
    for payload in strategies:
        if payload["strategy_id"] in existing_strategy_ids:
            continue
        db.add(StrategyProfile(**payload))
        inserted_strategies += 1

    await db.commit()
    return {
        "ok": True,
        "inserted_instruments": inserted_instruments,
        "inserted_strategies": inserted_strategies,
        "total_instruments": len(instruments),
        "total_strategies": len(strategies),
    }
