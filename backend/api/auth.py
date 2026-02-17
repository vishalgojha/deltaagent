from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.jwt import create_access_token, verify_password
from backend.db.models import Client
from backend.db.session import get_db_session
from backend.schemas import LoginRequest, LoginResponse


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db_session)) -> LoginResponse:
    result = await db.execute(select(Client).where(Client.email == payload.email))
    client = result.scalar_one_or_none()
    if not client or not verify_password(payload.password, client.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token(client.id)
    return LoginResponse(access_token=token, client_id=client.id)
