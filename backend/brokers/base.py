from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


class BrokerError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str = "BROKER_ERROR",
        retryable: bool = False,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.context = context or {}


class BrokerConnectionError(BrokerError):
    def __init__(self, message: str, *, retryable: bool = True, context: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="BROKER_CONNECTION_ERROR", retryable=retryable, context=context)


class BrokerAuthError(BrokerError):
    def __init__(self, message: str, *, retryable: bool = False, context: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="BROKER_AUTH_ERROR", retryable=retryable, context=context)


class BrokerOrderError(BrokerError):
    def __init__(self, message: str, *, retryable: bool = False, context: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="BROKER_ORDER_ERROR", retryable=retryable, context=context)


@dataclass
class BrokerOrderResult:
    order_id: str
    status: str
    fill_price: float | None = None


class BrokerBase(ABC):
    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def get_positions(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def get_greeks(self, contract: dict[str, Any]) -> dict[str, float]: ...

    @abstractmethod
    async def get_options_chain(self, symbol: str, expiry: str | None = None) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def get_market_data(self, symbol: str) -> dict[str, float]: ...

    @abstractmethod
    async def submit_order(
        self,
        contract: dict[str, Any],
        action: str,
        qty: int,
        order_type: str,
        limit_price: float | None = None,
    ) -> BrokerOrderResult: ...

    @abstractmethod
    async def stream_greeks(self, callback: Callable[[dict[str, Any]], Any]) -> None: ...
