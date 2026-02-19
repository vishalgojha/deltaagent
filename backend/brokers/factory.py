from backend.brokers.base import BrokerBase
from backend.brokers.ibkr import IBKRBroker
from backend.brokers.mock import MockBroker
from backend.brokers.phillip import PhillipBroker


def build_broker(
    broker_type: str,
    use_mock: bool = False,
    credentials: dict | None = None,
) -> BrokerBase:
    if use_mock:
        return MockBroker(credentials=credentials)
    if broker_type == "ibkr":
        return IBKRBroker(credentials=credentials)
    if broker_type == "phillip":
        return PhillipBroker(credentials=credentials)
    raise ValueError(f"Unsupported broker_type={broker_type}")
