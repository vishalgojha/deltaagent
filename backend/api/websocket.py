import asyncio
import json
import uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent.manager import AgentManager
from backend.auth.jwt import decode_access_token
from backend.auth.vault import CredentialVault
from backend.db.models import AgentMemory, Client


router = APIRouter(tags=["websocket"])
vault = CredentialVault()


@router.websocket("/clients/{id}/stream")
async def stream_client(websocket: WebSocket, id: uuid.UUID) -> None:
    await websocket.accept()
    token = websocket.query_params.get("token", "")
    try:
        token_client = decode_access_token(token)
        if token_client != id:
            await websocket.send_json({"error": "forbidden"})
            await websocket.close()
            return
    except Exception:  # noqa: BLE001
        await websocket.send_json({"error": "unauthorized"})
        await websocket.close()
        return
    app = websocket.app
    db_maker = app.state.db_sessionmaker
    manager: AgentManager = app.state.agent_manager
    try:
        async with db_maker() as db:  # type: AsyncSession
            client = await db.get(Client, id)
            if not client:
                await websocket.send_json({"error": "client_not_found"})
                await websocket.close()
                return
            try:
                creds = vault.decrypt(client.encrypted_creds)
            except Exception:
                await websocket.send_json({"error": "credential_decrypt_failed"})
                await websocket.close()
                return
            agent = await manager.get_agent(id, client.broker_type, creds, db)
            last_memory_id = 0
            while True:
                status_payload = await agent.status(id)
                await websocket.send_json({"type": "agent_status", "data": status_payload})

                greeks_payload = await _load_greeks_cache(websocket, id)
                if greeks_payload is not None:
                    await websocket.send_json({"type": "greeks", "data": greeks_payload})

                messages_stmt = (
                    select(AgentMemory)
                    .where(AgentMemory.client_id == id, AgentMemory.id > last_memory_id)
                    .order_by(AgentMemory.id.asc())
                    .limit(25)
                )
                rows = await db.execute(messages_stmt)
                for row in rows.scalars().all():
                    last_memory_id = max(last_memory_id, row.id)
                    await websocket.send_json(
                        {
                            "type": "agent_message",
                            "data": {
                                "role": row.message_role,
                                "content": row.content,
                                "timestamp": row.timestamp.isoformat(),
                            },
                        }
                    )
                await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        return


async def _load_greeks_cache(websocket: WebSocket, client_id: uuid.UUID) -> dict | None:
    redis_client = getattr(websocket.app.state, "redis", None)
    if redis_client is None:
        return None
    key = f"client:{client_id}:greeks"
    try:
        raw = await redis_client.get(key)
        if not raw:
            return None
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else None
    except Exception:  # noqa: BLE001
        return None
