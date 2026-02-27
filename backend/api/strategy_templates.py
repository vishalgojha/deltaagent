from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_client
from backend.api.error_utils import broker_http_exception
from backend.auth.vault import CredentialVault
from backend.brokers.base import BrokerError
from backend.db.models import Client
from backend.db.session import get_db_session
from backend.schemas import (
    StrategyExecutionOut,
    StrategyPreviewOut,
    StrategyTemplateCreateRequest,
    StrategyTemplateUpdateRequest,
    StrategyTemplateOut,
)
from backend.strategy_templates.service import StrategyTemplateService


router = APIRouter(prefix="/strategy-template", tags=["strategy-template"])
vault = CredentialVault()


def _decrypt_creds(current_client: Client) -> dict:
    try:
        return vault.decrypt(current_client.encrypted_creds)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Credential decrypt failed: {exc}") from exc


@router.post("", response_model=StrategyTemplateOut)
async def create_template(
    payload: StrategyTemplateCreateRequest,
    current_client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db_session),
) -> StrategyTemplateOut:
    service = StrategyTemplateService(db)
    try:
        template = await service.create_template(current_client.id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StrategyTemplateOut.model_validate(template)


@router.get("", response_model=list[StrategyTemplateOut])
async def list_templates(
    current_client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db_session),
) -> list[StrategyTemplateOut]:
    service = StrategyTemplateService(db)
    rows = await service.list_templates(current_client.id)
    return [StrategyTemplateOut.model_validate(row) for row in rows]


@router.get("/{template_id}", response_model=StrategyTemplateOut)
async def get_template(
    template_id: int,
    current_client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db_session),
) -> StrategyTemplateOut:
    service = StrategyTemplateService(db)
    try:
        template = await service.get_template(current_client.id, template_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return StrategyTemplateOut.model_validate(template)


@router.put("/{template_id}", response_model=StrategyTemplateOut)
async def update_template(
    template_id: int,
    payload: StrategyTemplateUpdateRequest,
    current_client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db_session),
) -> StrategyTemplateOut:
    service = StrategyTemplateService(db)
    try:
        template = await service.update_template(current_client.id, template_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StrategyTemplateOut.model_validate(template)


@router.delete("/{template_id}", status_code=204)
async def delete_template(
    template_id: int,
    current_client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db_session),
) -> None:
    service = StrategyTemplateService(db)
    try:
        await service.delete_template(current_client.id, template_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{template_id}/resolve", response_model=StrategyPreviewOut)
async def resolve_template(
    template_id: int,
    request: Request,
    current_client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db_session),
) -> StrategyPreviewOut:
    service = StrategyTemplateService(db)
    creds = _decrypt_creds(current_client)
    manager = request.app.state.agent_manager
    try:
        agent = await manager.get_agent(current_client.id, current_client.broker_type, creds, db)
        resolved = await service.resolve_strategy_template(current_client.id, template_id, agent.broker)
    except BrokerError as exc:
        raise broker_http_exception(exc, operation="resolve", broker=current_client.broker_type) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StrategyPreviewOut(**resolved.to_payload())


@router.post("/{template_id}/execute", response_model=StrategyExecutionOut)
async def execute_template(
    template_id: int,
    request: Request,
    current_client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db_session),
) -> StrategyExecutionOut:
    service = StrategyTemplateService(db)
    creds = _decrypt_creds(current_client)
    manager = request.app.state.agent_manager
    try:
        agent = await manager.get_agent(current_client.id, current_client.broker_type, creds, db)
        execution = await service.execute_strategy_template(
            current_client.id,
            template_id,
            agent.broker,
            emergency_halt=getattr(request.app.state, "emergency_halt", None),
        )
    except BrokerError as exc:
        raise broker_http_exception(exc, operation="execute", broker=current_client.broker_type) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StrategyExecutionOut(
        id=execution.id,
        template_id=execution.template_id,
        order_id=execution.order_id,
        status=execution.status,
        avg_fill_price=execution.avg_fill_price,
        execution_timestamp=execution.execution_timestamp,
        payload=execution.payload,
    )
