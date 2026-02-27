import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from redis.asyncio import Redis


@dataclass
class EmergencyHaltState:
    halted: bool = False
    reason: str = ""
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_by: str = "system"


class EmergencyHaltController:
    def __init__(self, redis_client: Redis | None = None, storage_key: str = "global:emergency_halt") -> None:
        self._lock = asyncio.Lock()
        self._state = EmergencyHaltState()
        self._redis = redis_client
        self._storage_key = storage_key
        self._logger = logging.getLogger(__name__)

    async def get(self) -> EmergencyHaltState:
        async with self._lock:
            await self._refresh_from_store()
            return EmergencyHaltState(
                halted=self._state.halted,
                reason=self._state.reason,
                updated_at=self._state.updated_at,
                updated_by=self._state.updated_by,
            )

    async def set(self, halted: bool, reason: str, updated_by: str) -> EmergencyHaltState:
        async with self._lock:
            self._state = EmergencyHaltState(
                halted=halted,
                reason=reason,
                updated_at=datetime.now(timezone.utc),
                updated_by=updated_by,
            )
            await self._persist_to_store()
            return EmergencyHaltState(
                halted=self._state.halted,
                reason=self._state.reason,
                updated_at=self._state.updated_at,
                updated_by=self._state.updated_by,
            )

    async def _refresh_from_store(self) -> None:
        if self._redis is None:
            return
        try:
            raw = await self._redis.get(self._storage_key)
            if not raw:
                return
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                return
            updated_at_raw = payload.get("updated_at")
            updated_at = self._state.updated_at
            if isinstance(updated_at_raw, str):
                try:
                    updated_at = datetime.fromisoformat(updated_at_raw)
                except ValueError:
                    updated_at = self._state.updated_at
            self._state = EmergencyHaltState(
                halted=bool(payload.get("halted", False)),
                reason=str(payload.get("reason", "")),
                updated_at=updated_at,
                updated_by=str(payload.get("updated_by", "system")),
            )
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("Failed to load emergency halt state from redis", extra={"error": str(exc)})

    async def _persist_to_store(self) -> None:
        if self._redis is None:
            return
        payload = {
            "halted": self._state.halted,
            "reason": self._state.reason,
            "updated_at": self._state.updated_at.isoformat(),
            "updated_by": self._state.updated_by,
        }
        try:
            await self._redis.set(self._storage_key, json.dumps(payload, default=str))
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("Failed to persist emergency halt state to redis", extra={"error": str(exc)})
