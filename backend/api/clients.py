import uuid
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.jwt import hash_password
from backend.auth.vault import CredentialVault
from backend.api.deps import assert_client_scope, get_current_client
from backend.api.error_utils import broker_http_exception
from backend.brokers.base import BrokerError
from backend.db.models import Client
from backend.db.session import get_db_session
from backend.schemas import BrokerConnectRequest, ClientOut, OnboardRequest


router = APIRouter(prefix="/clients", tags=["clients"])
vault = CredentialVault()


@router.post("/onboard", response_model=ClientOut)
async def onboard_client(payload: OnboardRequest, db: AsyncSession = Depends(get_db_session)) -> ClientOut:
    client = Client(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        broker_type=payload.broker_type,
        encrypted_creds=vault.encrypt(payload.broker_credentials),
        risk_params=payload.risk_parameters,
        mode="confirmation",
        tier=payload.subscription_tier,
        is_active=True,
    )
    db.add(client)
    await db.commit()
    await db.refresh(client)
    return ClientOut.model_validate(client)


@router.post("/{id}/connect-broker")
async def connect_broker(
    id: uuid.UUID,
    request: Request,
    payload: BrokerConnectRequest | None = Body(default=None),
    current_client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    assert_client_scope(id, current_client)
    if payload and payload.broker_credentials:
        current_client.encrypted_creds = vault.encrypt(payload.broker_credentials)
        await db.commit()
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
            force_recreate_broker=True,
        )
    except BrokerError as exc:
        raise broker_http_exception(exc, operation="connect", broker=current_client.broker_type) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Broker connection failed: {exc}") from exc
    return {"connected": True, "client_id": id, "broker": current_client.broker_type}
