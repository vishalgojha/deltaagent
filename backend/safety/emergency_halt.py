from dataclasses import dataclass, field
from datetime import datetime, timezone
import asyncio


@dataclass
class EmergencyHaltState:
    halted: bool = False
    reason: str = ""
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_by: str = "system"


class EmergencyHaltController:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._state = EmergencyHaltState()

    async def get(self) -> EmergencyHaltState:
        async with self._lock:
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
            return EmergencyHaltState(
                halted=self._state.halted,
                reason=self._state.reason,
                updated_at=self._state.updated_at,
                updated_by=self._state.updated_by,
            )
