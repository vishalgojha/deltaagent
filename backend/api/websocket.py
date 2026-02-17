import asyncio
import uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent.manager import AgentManager
from backend.auth.jwt import decode_access_token
from backend.auth.vault import CredentialVault
from backend.db.models import Client


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
            while True:
                status_payload = await agent.status(id)
                await websocket.send_json({"type": "agent_status", "data": status_payload})
                await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        return
