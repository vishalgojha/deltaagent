import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import assert_client_scope, get_current_client
from backend.api.error_utils import broker_http_exception
from backend.auth.vault import CredentialVault
from backend.brokers.base import BrokerError
from backend.config import get_settings
from backend.db.models import Client, Proposal
from backend.db.session import get_db_session
from backend.schemas import (
    AgentReadinessOut,
    AgentStatusOut,
    ApproveRejectResponse,
    ChatResponse,
    ChatRequest,
    ModeUpdateRequest,
    ParametersUpdateRequest,
    ProposalOut,
)


router = APIRouter(prefix="/clients", tags=["agent"])
vault = CredentialVault()


def _decrypt_creds(current_client: Client) -> dict:
    try:
        return vault.decrypt(current_client.encrypted_creds)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Credential decrypt failed: {exc}") from exc


@router.post("/{id}/agent/mode")
async def set_mode(
    id: uuid.UUID,
    payload: ModeUpdateRequest,
    request: Request,
    current_client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    assert_client_scope(id, current_client)
    creds = _decrypt_creds(current_client)
    manager = request.app.state.agent_manager
    try:
        agent = await manager.get_agent(id, current_client.broker_type, creds, db)
    except BrokerError as exc:
        raise broker_http_exception(exc, operation="get_agent", broker=current_client.broker_type) from exc
    try:
        await agent.set_mode(id, payload.mode)
    except BrokerError as exc:
        raise broker_http_exception(exc, operation="set_mode", broker=current_client.broker_type) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"client_id": id, "mode": payload.mode}


@router.post("/{id}/agent/parameters")
async def update_parameters(
    id: uuid.UUID,
    payload: ParametersUpdateRequest,
    request: Request,
    current_client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    assert_client_scope(id, current_client)
    creds = _decrypt_creds(current_client)
    manager = request.app.state.agent_manager
    try:
        agent = await manager.get_agent(id, current_client.broker_type, creds, db)
    except BrokerError as exc:
        raise broker_http_exception(exc, operation="get_agent", broker=current_client.broker_type) from exc
    await agent.set_parameters(id, payload.risk_parameters)
    return {"client_id": id, "risk_parameters": payload.risk_parameters}


@router.get("/{id}/agent/parameters")
async def get_parameters(
    id: uuid.UUID,
    current_client: Client = Depends(get_current_client),
) -> dict:
    assert_client_scope(id, current_client)
    return {"client_id": id, "risk_parameters": current_client.risk_params or {}}


@router.post("/{id}/agent/chat", response_model=ChatResponse)
async def chat(
    id: uuid.UUID,
    payload: ChatRequest,
    request: Request,
    current_client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db_session),
) -> ChatResponse:
    assert_client_scope(id, current_client)
    creds = _decrypt_creds(current_client)
    manager = request.app.state.agent_manager
    try:
        agent = await manager.get_agent(id, current_client.broker_type, creds, db)
    except BrokerError as exc:
        raise broker_http_exception(exc, operation="get_agent", broker=current_client.broker_type) from exc
    try:
        return ChatResponse.model_validate(await agent.chat(id, payload.message))
    except BrokerError as exc:
        raise broker_http_exception(exc, operation="chat", broker=current_client.broker_type) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{id}/agent/approve/{trade_id}", response_model=ApproveRejectResponse)
async def approve_trade(
    id: uuid.UUID,
    trade_id: int,
    request: Request,
    current_client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db_session),
) -> ApproveRejectResponse:
    assert_client_scope(id, current_client)
    creds = _decrypt_creds(current_client)
    manager = request.app.state.agent_manager
    try:
        agent = await manager.get_agent(id, current_client.broker_type, creds, db)
    except BrokerError as exc:
        raise broker_http_exception(exc, operation="get_agent", broker=current_client.broker_type) from exc
    try:
        await agent.approve_proposal(id, trade_id)
    except BrokerError as exc:
        raise broker_http_exception(exc, operation="approve_proposal", broker=current_client.broker_type) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ApproveRejectResponse(proposal_id=trade_id, status="approved")


@router.post("/{id}/agent/reject/{trade_id}", response_model=ApproveRejectResponse)
async def reject_trade(
    id: uuid.UUID,
    trade_id: int,
    request: Request,
    current_client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db_session),
) -> ApproveRejectResponse:
    assert_client_scope(id, current_client)
    creds = _decrypt_creds(current_client)
    manager = request.app.state.agent_manager
    try:
        agent = await manager.get_agent(id, current_client.broker_type, creds, db)
    except BrokerError as exc:
        raise broker_http_exception(exc, operation="get_agent", broker=current_client.broker_type) from exc
    try:
        await agent.reject_proposal(id, trade_id)
    except BrokerError as exc:
        raise broker_http_exception(exc, operation="reject_proposal", broker=current_client.broker_type) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ApproveRejectResponse(proposal_id=trade_id, status="rejected")


@router.get("/{id}/agent/status", response_model=AgentStatusOut)
async def status(
    id: uuid.UUID,
    request: Request,
    current_client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db_session),
) -> AgentStatusOut:
    assert_client_scope(id, current_client)
    creds = _decrypt_creds(current_client)
    manager = request.app.state.agent_manager
    try:
        agent = await manager.get_agent(id, current_client.broker_type, creds, db)
    except BrokerError as exc:
        raise broker_http_exception(exc, operation="get_agent", broker=current_client.broker_type) from exc
    payload = await agent.status(id)
    return AgentStatusOut(**payload)


@router.get("/{id}/agent/readiness", response_model=AgentReadinessOut)
async def readiness(
    id: uuid.UUID,
    request: Request,
    current_client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db_session),
) -> AgentReadinessOut:
    assert_client_scope(id, current_client)
    settings = get_settings()
    connected = False
    market_data_ok = False
    last_error: str | None = None
    mode = current_client.mode or "confirmation"
    risk_blocked = False

    emergency_halt = getattr(request.app.state, "emergency_halt", None)
    if emergency_halt is not None:
        state = await emergency_halt.get()
        if state.halted:
            risk_blocked = True
            last_error = state.reason or "Emergency trading halt is active"

    if mode == "autonomous" and not settings.autonomous_enabled:
        risk_blocked = True
        if not last_error:
            last_error = "Autonomous mode disabled by system policy"

    creds = _decrypt_creds(current_client)
    manager = request.app.state.agent_manager
    try:
        agent = await manager.get_agent(id, current_client.broker_type, creds, db)
        connected = True
    except BrokerError as exc:
        connected = False
        last_error = str(exc)
        ready = False
        return AgentReadinessOut(
            client_id=id,
            ready=ready,
            connected=connected,
            market_data_ok=market_data_ok,
            mode=mode,
            risk_blocked=risk_blocked,
            last_error=last_error,
            updated_at=datetime.now(timezone.utc),
        )

    try:
        market = await agent.tools.get_market_data("ES")
        underlying = float(market.get("underlying_price", 0.0))
        bid = float(market.get("bid", 0.0))
        ask = float(market.get("ask", 0.0))
        market_data_ok = underlying > 0 or (bid > 0 and ask > 0)
        if not market_data_ok and not last_error:
            last_error = "Market data unavailable"
    except BrokerError as exc:
        market_data_ok = False
        if not last_error:
            last_error = str(exc)
    except Exception as exc:  # noqa: BLE001
        market_data_ok = False
        if not last_error:
            last_error = str(exc)

    ready = connected and market_data_ok and not risk_blocked
    return AgentReadinessOut(
        client_id=id,
        ready=ready,
        connected=connected,
        market_data_ok=market_data_ok,
        mode=mode,
        risk_blocked=risk_blocked,
        last_error=last_error,
        updated_at=datetime.now(timezone.utc),
    )


@router.get("/{id}/agent/proposals", response_model=list[ProposalOut])
async def list_proposals(
    id: uuid.UUID,
    current_client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db_session),
) -> list[ProposalOut]:
    assert_client_scope(id, current_client)
    rows = await db.execute(
        select(Proposal).where(Proposal.client_id == id).order_by(desc(Proposal.timestamp)).limit(100)
    )
    return [ProposalOut.model_validate(row) for row in rows.scalars().all()]
