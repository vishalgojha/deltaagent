import uuid
from fastapi import APIRouter, Depends
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import assert_client_scope, get_current_client
from backend.db.models import Client, Trade
from backend.db.session import get_db_session
from backend.schemas import TradeOut


router = APIRouter(prefix="/clients", tags=["trades"])


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
