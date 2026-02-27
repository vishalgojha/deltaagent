import uuid

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent.core import TradingAgent
from backend.agent.memory import AgentMemoryStore
from backend.agent.risk import RiskGovernor
from backend.brokers.base import BrokerBase
from backend.brokers.factory import build_broker
from backend.config import get_settings
from backend.safety.emergency_halt import EmergencyHaltController


class AgentManager:
    def __init__(
        self,
        emergency_halt: EmergencyHaltController | None = None,
        redis_client: Redis | None = None,
    ) -> None:
        self.memory_store = AgentMemoryStore()
        self.risk_governor = RiskGovernor()
        self._brokers: dict[uuid.UUID, BrokerBase] = {}
        self.emergency_halt = emergency_halt
        self.redis_client = redis_client

    async def get_agent(
        self,
        client_id: uuid.UUID,
        broker_type: str,
        broker_credentials: dict | None,
        db: AsyncSession,
        force_recreate_broker: bool = False,
    ) -> TradingAgent:
        existing = self._brokers.get(client_id)
        if force_recreate_broker and existing is not None:
            await self._disconnect_broker(existing)
            self._brokers.pop(client_id, None)

        broker = self._brokers.get(client_id)
        if broker is None:
            broker = build_broker(
                broker_type=broker_type,
                use_mock=get_settings().use_mock_broker,
                credentials=broker_credentials,
            )
            await broker.connect()
            self._brokers[client_id] = broker
        return TradingAgent(
            broker=broker,
            db=db,
            memory_store=self.memory_store,
            risk_governor=self.risk_governor,
            emergency_halt=self.emergency_halt,
            redis_client=self.redis_client,
        )

    async def shutdown(self) -> None:
        for broker in list(self._brokers.values()):
            await self._disconnect_broker(broker)
        self._brokers.clear()

    @staticmethod
    async def _disconnect_broker(broker: BrokerBase) -> None:
        try:
            await broker.disconnect()
        except Exception:  # noqa: BLE001
            pass
