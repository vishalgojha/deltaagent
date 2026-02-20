import uuid
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.jwt import decode_access_token, decode_admin_token
from backend.config import get_settings
from backend.db.models import Client
from backend.db.session import get_db_session


async def get_current_client(
    authorization: str = Header(default=""),
    db: AsyncSession = Depends(get_db_session),
) -> Client:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization.replace("Bearer ", "", 1).strip()
    try:
        client_id = decode_access_token(token)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    client = await db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Client not found")
    await _set_db_security_context(db, client_id=str(client.id), is_admin=False)
    return client


def assert_client_scope(path_client_id: uuid.UUID, current_client: Client) -> None:
    if path_client_id != current_client.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-tenant access denied")


def require_admin_access(
    authorization: str = Header(default=""),
    x_admin_key: str = Header(default="", alias="X-Admin-Key"),
) -> str:
    auth_value = authorization if isinstance(authorization, str) else ""
    if auth_value.startswith("Bearer "):
        token = auth_value.replace("Bearer ", "", 1).strip()
        try:
            actor = decode_admin_token(token)
            return actor
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token") from exc

    settings = get_settings()
    if not settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API key is not configured",
        )
    header_admin_key = x_admin_key if isinstance(x_admin_key, str) else ""
    if header_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin key")
    return "admin"


async def set_admin_db_context(
    db: AsyncSession = Depends(get_db_session),
    _: str = Depends(require_admin_access),
) -> str:
    await _set_db_security_context(db, client_id="", is_admin=True)
    return "admin"


async def _set_db_security_context(db: AsyncSession, client_id: str, is_admin: bool) -> None:
    bind = db.get_bind()
    if bind is None or bind.dialect.name != "postgresql":
        return
    await db.execute(
        text("SELECT set_config('app.current_client_id', :client_id, false)"),
        {"client_id": client_id},
    )
    await db.execute(
        text("SELECT set_config('app.is_admin', :is_admin, false)"),
        {"is_admin": "true" if is_admin else "false"},
    )
