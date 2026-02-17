from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import set_admin_db_context
from backend.db.models import AuditLog, Client
from backend.db.session import get_db_session
from backend.schemas import EmergencyHaltRequest, EmergencyHaltResponse


router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/emergency-halt", response_model=EmergencyHaltResponse)
async def get_emergency_halt(
    request: Request,
    _: str = Depends(set_admin_db_context),
) -> EmergencyHaltResponse:
    state = await request.app.state.emergency_halt.get()
    return EmergencyHaltResponse(
        halted=state.halted,
        reason=state.reason,
        updated_at=state.updated_at,
        updated_by=state.updated_by,
    )


@router.post("/emergency-halt", response_model=EmergencyHaltResponse)
async def set_emergency_halt(
    payload: EmergencyHaltRequest,
    request: Request,
    admin_actor: str = Depends(set_admin_db_context),
    db: AsyncSession = Depends(get_db_session),
) -> EmergencyHaltResponse:
    state = await request.app.state.emergency_halt.set(
        halted=payload.halted,
        reason=payload.reason.strip(),
        updated_by=admin_actor,
    )

    rows = await db.execute(select(Client.id))
    client_ids = list(rows.scalars().all())
    for client_id in client_ids:
        db.add(
            AuditLog(
                client_id=client_id,
                event_type="emergency_halt_updated",
                details={
                    "halted": state.halted,
                    "reason": state.reason,
                    "updated_by": state.updated_by,
                    "updated_at": state.updated_at.isoformat(),
                },
            )
        )
    if client_ids:
        await db.commit()

    return EmergencyHaltResponse(
        halted=state.halted,
        reason=state.reason,
        updated_at=state.updated_at,
        updated_by=state.updated_by,
    )
