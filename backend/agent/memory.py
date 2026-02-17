import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentContext:
    client_id: uuid.UUID
    mode: str = "confirmation"
    parameters: dict[str, Any] = field(default_factory=dict)
    positions: list[dict[str, Any]] = field(default_factory=list)
    net_greeks: dict[str, float] = field(
        default_factory=lambda: {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
    )
    message_history: list[dict[str, str]] = field(default_factory=list)
    last_action: str | None = None
    healthy: bool = True


class AgentMemoryStore:
    def __init__(self) -> None:
        self._contexts: dict[uuid.UUID, AgentContext] = {}

    def get_or_create(self, client_id: uuid.UUID) -> AgentContext:
        if client_id not in self._contexts:
            self._contexts[client_id] = AgentContext(client_id=client_id)
        return self._contexts[client_id]

    def update(self, context: AgentContext) -> None:
        self._contexts[context.client_id] = context
