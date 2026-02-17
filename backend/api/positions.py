import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import assert_client_scope, get_current_client
from backend.api.error_utils import broker_http_exception
from backend.auth.vault import CredentialVault
from backend.brokers.base import BrokerError
from backend.db.models import Client, Position
from backend.db.session import get_db_session
from backend.schemas import PositionOut


router = APIRouter(prefix="/clients", tags=["positions"])
vault = CredentialVault()


@router.get("/{id}/positions", response_model=list[PositionOut])
async def get_positions(
    id: uuid.UUID,
    request: Request,
    current_client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db_session),
) -> list[PositionOut]:
    assert_client_scope(id, current_client)
    try:
        creds = vault.decrypt(current_client.encrypted_creds)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Credential decrypt failed: {exc}") from exc
    manager = request.app.state.agent_manager
    try:
        agent = await manager.get_agent(
            client_id=id,
            broker_type=current_client.broker_type,
            broker_credentials=creds,
            db=db,
        )
        positions = await agent.broker.get_positions()
    except BrokerError as exc:
        raise broker_http_exception(exc, operation="get_positions", broker=current_client.broker_type) from exc

    await db.execute(delete(Position).where(Position.client_id == id))
    for p in positions:
        db.add(Position(client_id=id, **p))
    await db.commit()

    rows = await db.execute(select(Position).where(Position.client_id == id))
    return [PositionOut.model_validate(item) for item in rows.scalars().all()]
