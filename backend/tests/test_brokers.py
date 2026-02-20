import pytest
from datetime import datetime, timedelta, timezone

from backend.brokers.factory import build_broker
from backend.brokers.ibkr import IBKRBroker
from backend.brokers.mock import MockBroker
from backend.brokers.base import BrokerOrderError
from backend.brokers.phillip import PhillipBroker


@pytest.mark.asyncio
async def test_factory_returns_mock_when_enabled() -> None:
    broker = build_broker("ibkr", use_mock=True)
    assert isinstance(broker, MockBroker)


@pytest.mark.asyncio
async def test_mock_broker_submit_order() -> None:
    broker = MockBroker()
    await broker.connect()
    result = await broker.submit_order(
        contract={"symbol": "ES", "instrument": "FOP"},
        action="BUY",
        qty=1,
        order_type="MKT",
        limit_price=None,
    )
    assert result.status == "filled"
    assert result.order_id is not None


class _FakeGreeks:
    delta = 0.12
    gamma = 0.03
    theta = -0.08
    vega = 0.20


class _FakeTicker:
    modelGreeks = _FakeGreeks()
    bid = 10.0
    ask = 10.3
    last = 10.2

    @staticmethod
    def marketPrice() -> float:
        return 10.2


class _FakeOrderStatus:
    status = "Filled"
    avgFillPrice = 10.25


class _FakeOrder:
    orderId = 12345


class _FakeTrade:
    orderStatus = _FakeOrderStatus()
    order = _FakeOrder()


class _FakePositionContract:
    symbol = "ES"
    secType = "FOP"
    strike = 5000.0
    lastTradeDateOrContractMonth = "20260320"
    right = "C"
    exchange = "CME"
    currency = "USD"
    multiplier = "50"


class _FakePosition:
    contract = _FakePositionContract()
    position = 1
    avgCost = 10.1


class _FakeChain:
    expirations = {"20260320"}
    strikes = {5000.0, 5050.0}
    exchange = "CME"
    tradingClass = "ES"


class _FakeContractDetails:
    class contract:  # noqa: N801
        conId = 12345
        lastTradeDateOrContractMonth = "202603"


class _FakeIB:
    def __init__(self) -> None:
        self.connected = True
        self.market_data_type: int | None = None

    def isConnected(self) -> bool:  # noqa: N802
        return self.connected

    def positions(self):
        return [_FakePosition()]

    async def reqTickersAsync(self, *args):
        return [_FakeTicker() for _ in args] or [_FakeTicker()]

    async def reqSecDefOptParamsAsync(self, *args):
        return [_FakeChain()]

    async def reqContractDetailsAsync(self, *args):
        return [_FakeContractDetails()]

    def placeOrder(self, contract, order):
        return _FakeTrade()

    def reqMarketDataType(self, market_data_type: int):  # noqa: N802
        self.market_data_type = market_data_type


class _FakeIBClientIdCollision:
    def __init__(self) -> None:
        self.calls: list[int] = []

    async def connectAsync(self, host, port, clientId):  # noqa: N803, ANN001
        self.calls.append(clientId)
        if clientId == 12:
            raise RuntimeError("Error 326: client id is already in use")
        return True


@pytest.mark.asyncio
async def test_ibkr_submit_order_with_fake_ib() -> None:
    broker = IBKRBroker()
    broker._ib = _FakeIB()
    broker._connected = True
    broker._build_contract = lambda payload: payload  # type: ignore[method-assign]
    broker._build_order = lambda action, qty, order_type, limit_price: {  # type: ignore[method-assign]
        "action": action,
        "qty": qty,
        "order_type": order_type,
        "limit_price": limit_price,
    }
    result = await broker.submit_order(
        contract={"symbol": "ES", "instrument": "FOP", "expiry": "20260320", "strike": 5000, "right": "C"},
        action="BUY",
        qty=1,
        order_type="MKT",
    )
    assert result.status == "Filled"
    assert result.order_id == "12345"
    assert result.fill_price == 10.25


@pytest.mark.asyncio
async def test_ibkr_get_positions_enriches_greeks() -> None:
    broker = IBKRBroker()
    broker._ib = _FakeIB()
    broker._connected = True
    broker._build_contract = lambda payload: payload  # type: ignore[method-assign]
    rows = await broker.get_positions()
    assert len(rows) == 1
    assert rows[0]["delta"] == pytest.approx(0.12)


@pytest.mark.asyncio
async def test_ibkr_get_options_chain_returns_greek_rows() -> None:
    broker = IBKRBroker({"max_chain_quotes": 2})
    broker._ib = _FakeIB()
    broker._connected = True
    broker._build_contract = lambda payload: payload  # type: ignore[method-assign]
    chain = await broker.get_options_chain("ES", "20260320")
    assert len(chain) == 2
    assert chain[0]["call_delta"] == pytest.approx(0.12)
    assert chain[0]["call_mid"] == pytest.approx(10.15)
    assert chain[0]["put_mid"] == pytest.approx(10.15)


def test_ibkr_pick_target_expiry_uses_nearest_available() -> None:
    expirations = ["20260320", "20260417", "20260515"]
    picked = IBKRBroker._pick_target_expiry(expirations, "20260322")
    assert picked == "20260320"


class _FakeHTTPResponse:
    def __init__(self, status_code: int, payload: dict, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text or str(payload)

    def json(self) -> dict:
        return self._payload


class _FakeAsyncHTTPClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.transient_positions_failures = 0

    async def request(self, method: str, url: str, data=None, json=None, params=None, headers=None):  # noqa: ANN001
        method = method.upper()
        if method == "POST":
            return await self.post(url, data=data, json=json, headers=headers)
        return await self.get(url, params=params, headers=headers)

    async def post(self, url: str, data=None, json=None, headers=None):  # noqa: ANN001
        self.calls.append(("POST", url))
        if url.endswith("/oauth/token"):
            return _FakeHTTPResponse(200, {"access_token": "token-123", "expires_in": 3600})
        if url.endswith("/orders"):
            return _FakeHTTPResponse(200, {"orderId": "OID-1", "status": "accepted", "fillPrice": 10.5})
        return _FakeHTTPResponse(404, {}, text="not found")

    async def get(self, url: str, params=None, headers=None):  # noqa: ANN001
        self.calls.append(("GET", url))
        if url.endswith("/positions"):
            if self.transient_positions_failures > 0:
                self.transient_positions_failures -= 1
                return _FakeHTTPResponse(503, {"error": "temporary"}, text="temporary")
            return _FakeHTTPResponse(
                200,
                {
                    "positions": [
                        {
                            "symbol": "ES",
                            "instrumentType": "FOP",
                            "strike": 5000,
                            "expiry": "20260320",
                            "quantity": 2,
                            "delta": 0.1,
                            "gamma": 0.02,
                            "theta": -0.04,
                            "vega": 0.2,
                            "avgPrice": 10.0,
                        }
                    ]
                },
            )
        if "/options/chain" in url:
            return _FakeHTTPResponse(200, {"chain": [{"symbol": "ES", "strike": 5000}]})
        if "/market-data/" in url:
            return _FakeHTTPResponse(200, {"last": 5010, "ivRank": 40, "ivPercentile": 55, "bid": 10, "ask": 10.2})
        return _FakeHTTPResponse(404, {}, text="not found")


class _FailingAsyncHTTPClient:
    async def request(self, method: str, url: str, data=None, json=None, params=None, headers=None):  # noqa: ANN001
        raise RuntimeError("network down")


@pytest.mark.asyncio
async def test_phillip_auth_positions_and_order_mapping() -> None:
    broker = PhillipBroker({"client_id": "cid", "client_secret": "secret"})
    broker._http = _FakeAsyncHTTPClient()  # type: ignore[assignment]
    await broker.connect()
    positions = await broker.get_positions()
    assert len(positions) == 1
    assert positions[0]["symbol"] == "ES"
    assert positions[0]["delta"] == pytest.approx(0.1)

    chain = await broker.get_options_chain("ES")
    assert chain[0]["symbol"] == "ES"

    market = await broker.get_market_data("ES")
    assert market["underlying_price"] == pytest.approx(5010.0)

    order = await broker.submit_order(
        contract={
            "symbol": "ES",
            "instrument": "FOP",
            "strike": 5000,
            "expiry": "20260320",
            "exchange": "CME",
            "right": "CALL",
        },
        action="BUY",
        qty=1,
        order_type="MKT",
    )
    assert order.order_id == "OID-1"
    assert order.status == "accepted"


@pytest.mark.asyncio
async def test_phillip_retries_transient_position_errors() -> None:
    broker = PhillipBroker({"client_id": "cid", "client_secret": "secret", "request_retries": 3})
    fake_http = _FakeAsyncHTTPClient()
    fake_http.transient_positions_failures = 1
    broker._http = fake_http  # type: ignore[assignment]
    await broker.connect()
    positions = await broker.get_positions()
    assert len(positions) == 1
    position_gets = [call for call in fake_http.calls if call == ("GET", "https://api.phillipcapital.com.au/positions")]
    assert len(position_gets) >= 2


@pytest.mark.asyncio
async def test_phillip_retry_exhaustion_includes_failure_telemetry() -> None:
    broker = PhillipBroker({"client_id": "cid", "client_secret": "secret", "request_retries": 2})
    broker._http = _FailingAsyncHTTPClient()  # type: ignore[assignment]
    broker._token = "token-123"
    broker._token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    with pytest.raises(BrokerOrderError) as exc:
        await broker.get_positions()

    assert exc.value.retryable is True
    assert exc.value.context["endpoint"] == "/positions"
    assert exc.value.context["retries"] == 2
    assert exc.value.context["last_error_type"] == "RuntimeError"


def test_ibkr_contract_normalization_with_alias_and_exchange_override() -> None:
    broker = IBKRBroker({"exchange_overrides": {"YM": "CBOT"}})
    normalized = broker._normalize_contract_payload(
        {"symbol": "ym", "instrument": "future", "expiry": "202603", "right": "put"}
    )
    assert normalized["symbol"] == "YM"
    assert normalized["instrument"] == "FUT"
    assert normalized["exchange"] == "CBOT"
    assert normalized["right"] == "P"


def test_ibkr_contract_normalization_maps_exchange_alias_and_expiry_digits() -> None:
    broker = IBKRBroker()
    normalized = broker._normalize_contract_payload(
        {"symbol": "es", "instrument": "fop", "expiry": "2026-03-20", "exchange": "globex", "right": "call"}
    )
    assert normalized["exchange"] == "CME"
    assert normalized["expiry"] == "20260320"
    assert normalized["right"] == "C"


class _FakeIBOptionsPartial(_FakeIB):
    async def reqTickersAsync(self, *args):
        if len(args) == 2:
            return [_FakeTicker()]
        return [_FakeTicker()]


@pytest.mark.asyncio
async def test_ibkr_options_chain_handles_partial_ticker_responses() -> None:
    broker = IBKRBroker({"max_chain_quotes": 1})
    broker._ib = _FakeIBOptionsPartial()
    broker._connected = True
    broker._build_contract = lambda payload: payload  # type: ignore[method-assign]

    chain = await broker.get_options_chain("ES", "20260320")

    assert len(chain) == 1
    assert chain[0]["call_delta"] == pytest.approx(0.12)
    assert chain[0]["put_delta"] == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_ibkr_ensure_connected_reconnects_dropped_session() -> None:
    broker = IBKRBroker()
    fake_ib = _FakeIB()
    fake_ib.connected = False
    broker._ib = fake_ib
    broker._connected = True

    called = {"count": 0}

    async def fake_connect_with_retry() -> bool:
        called["count"] += 1
        broker._ib = _FakeIB()
        broker._ib.connected = True
        return True

    broker._connect_with_retry = fake_connect_with_retry  # type: ignore[method-assign]

    await broker._ensure_connected()

    assert called["count"] == 1
    assert broker._connected is True


def test_ibkr_sets_delayed_market_data_type_when_enabled() -> None:
    broker = IBKRBroker({"delayed_market_data": True})
    fake_ib = _FakeIB()
    broker._ib = fake_ib
    broker._configure_market_data_type()
    assert fake_ib.market_data_type == 3


@pytest.mark.asyncio
async def test_ibkr_connect_with_retry_uses_next_client_id_when_collision() -> None:
    broker = IBKRBroker({"client_id": 12, "connect_retries": 1, "client_id_fallback_attempts": 3})
    fake_ib = _FakeIBClientIdCollision()
    broker._ib = fake_ib

    ok = await broker._connect_with_retry()

    assert ok is True
    assert broker._active_client_id == 13
    assert fake_ib.calls == [12, 13]
