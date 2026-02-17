import asyncio
import logging
from collections.abc import Callable
from typing import Any

from backend.brokers.base import BrokerBase, BrokerConnectionError, BrokerOrderError, BrokerOrderResult
from backend.config import get_settings


logger = logging.getLogger(__name__)


class IBKRBroker(BrokerBase):
    _INSTRUMENT_ALIASES = {
        "OPT": "FOP",
        "OPTION": "FOP",
        "FUTOPT": "FOP",
        "FUTURE": "FUT",
    }
    _DEFAULT_EXCHANGE_BY_SYMBOL = {
        "ES": "CME",
        "NQ": "CME",
        "RTY": "CME",
        "YM": "CBOT",
        "ZN": "CBOT",
        "ZB": "CBOT",
        "CL": "NYMEX",
        "GC": "COMEX",
    }

    def __init__(self, credentials: dict | None = None) -> None:
        self._ib = None
        self._connected = False
        self._credentials = credentials or {}
        self._stream_enabled = False

    async def connect(self) -> None:
        try:
            from ib_insync import IB  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise BrokerConnectionError("ib_insync not available", retryable=False) from exc
        cfg = get_settings()
        host = self._credentials.get("host", cfg.ibkr_gateway_host)
        port = int(self._credentials.get("port", cfg.ibkr_gateway_port))
        client_id = int(self._credentials.get("client_id", 1))
        self._ib = IB()
        retries = int(self._credentials.get("connect_retries", 3))
        base_backoff = float(self._credentials.get("connect_backoff_seconds", 0.5))
        ok = False
        last_error: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                ok = await self._ib.connectAsync(host, port, clientId=client_id)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                ok = False
            if ok:
                break
            if attempt < retries:
                delay = base_backoff * (2 ** (attempt - 1))
                logger.warning(
                    "IBKR connect attempt failed",
                    extra={"attempt": attempt, "retries": retries, "host": host, "port": port},
                )
                await asyncio.sleep(delay)
        if not ok:
            raise BrokerConnectionError(
                "Failed to connect to IBKR gateway",
                retryable=True,
                context={
                    "host": host,
                    "port": port,
                    "client_id": client_id,
                    "retries": retries,
                    "last_error": str(last_error) if last_error else None,
                },
            )
        self._connected = True

    async def get_positions(self) -> list[dict[str, Any]]:
        if not self._ib:
            return []
        items = self._ib.positions()
        positions: list[dict[str, Any]] = []
        for item in items:
            contract = item.contract
            greeks = await self.get_greeks(
                {
                    "symbol": contract.symbol,
                    "instrument": contract.secType,
                    "expiry": getattr(contract, "lastTradeDateOrContractMonth", None),
                    "strike": getattr(contract, "strike", None),
                    "right": getattr(contract, "right", "C"),
                    "exchange": getattr(contract, "exchange", "CME"),
                    "currency": getattr(contract, "currency", "USD"),
                    "multiplier": getattr(contract, "multiplier", None),
                }
            )
            positions.append(
                {
                    "symbol": contract.symbol,
                    "instrument_type": contract.secType,
                    "strike": getattr(contract, "strike", None),
                    "expiry": getattr(contract, "lastTradeDateOrContractMonth", None),
                    "qty": int(item.position),
                    "delta": greeks["delta"],
                    "gamma": greeks["gamma"],
                    "theta": greeks["theta"],
                    "vega": greeks["vega"],
                    "avg_price": float(item.avgCost) if item.avgCost else 0.0,
                }
            )
        return positions

    async def get_greeks(self, contract: dict[str, Any]) -> dict[str, float]:
        self._require_connected()
        ib_contract = self._build_contract(contract)
        tickers = await self._ib.reqTickersAsync(ib_contract)
        if not tickers:
            return {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
        return self._extract_greeks(tickers[0])

    async def get_options_chain(self, symbol: str, expiry: str | None = None) -> list[dict[str, Any]]:
        self._require_connected()
        try:
            params = await self._ib.reqSecDefOptParamsAsync(symbol, "", "FUT", 0)
        except Exception as exc:  # noqa: BLE001
            raise BrokerOrderError(
                f"Unable to fetch chain params for {symbol}",
                retryable=True,
                context={"symbol": symbol},
            ) from exc
        if not params:
            return []
        chain = params[0]
        expirations = sorted(list(chain.expirations))
        target_expiry = expiry or (expirations[0] if expirations else None)
        if not target_expiry:
            return []
        strikes = sorted([float(s) for s in chain.strikes])
        max_quotes = int(self._credentials.get("max_chain_quotes", 20))
        sample_strikes = strikes[:max_quotes]
        rows: list[dict[str, Any]] = []
        for strike in sample_strikes:
            call_contract = self._build_contract(
                {
                    "symbol": symbol,
                    "instrument": "FOP",
                    "expiry": target_expiry,
                    "strike": strike,
                    "right": "C",
                    "exchange": chain.exchange or "CME",
                    "currency": "USD",
                }
            )
            put_contract = self._build_contract(
                {
                    "symbol": symbol,
                    "instrument": "FOP",
                    "expiry": target_expiry,
                    "strike": strike,
                    "right": "P",
                    "exchange": chain.exchange or "CME",
                    "currency": "USD",
                }
            )
            call_ticker, put_ticker = await self._ib.reqTickersAsync(call_contract, put_contract)
            call_g = self._extract_greeks(call_ticker)
            put_g = self._extract_greeks(put_ticker)
            rows.append(
                {
                    "symbol": symbol,
                    "expiry": target_expiry,
                    "strike": strike,
                    "call_delta": call_g["delta"],
                    "put_delta": put_g["delta"],
                    "gamma": call_g["gamma"],
                    "theta": call_g["theta"],
                    "vega": call_g["vega"],
                }
            )
        return rows

    async def get_market_data(self, symbol: str) -> dict[str, float]:
        self._require_connected()
        under_instrument = self._credentials.get("underlying_instrument", "IND")
        contract = self._build_contract(
            {
                "symbol": symbol,
                "instrument": under_instrument,
                "expiry": self._credentials.get("underlying_expiry"),
                "exchange": self._credentials.get("exchange", "CME"),
                "currency": self._credentials.get("currency", "USD"),
            }
        )
        ticker_list = await self._ib.reqTickersAsync(contract)
        if not ticker_list:
            return {"underlying_price": 0.0, "iv_rank": 0.0, "iv_percentile": 0.0, "bid": 0.0, "ask": 0.0}
        ticker = ticker_list[0]
        last = self._safe_float(getattr(ticker, "marketPrice", lambda: 0.0)())
        if last == 0.0:
            last = self._safe_float(getattr(ticker, "last", 0.0))
        bid = self._safe_float(getattr(ticker, "bid", 0.0))
        ask = self._safe_float(getattr(ticker, "ask", 0.0))
        # IV rank/percentile should come from persisted historical IV; set sentinel until history service is added.
        return {"underlying_price": last, "iv_rank": 0.0, "iv_percentile": 0.0, "bid": bid, "ask": ask}

    async def submit_order(
        self,
        contract: dict[str, Any],
        action: str,
        qty: int,
        order_type: str,
        limit_price: float | None = None,
    ) -> BrokerOrderResult:
        self._require_connected()
        ib_contract = self._build_contract(contract)
        order = self._build_order(action=action, qty=qty, order_type=order_type, limit_price=limit_price)
        try:
            trade = self._ib.placeOrder(ib_contract, order)
        except Exception as exc:  # noqa: BLE001
            raise BrokerOrderError(
                f"IBKR order placement failed: {exc}",
                retryable=True,
                context={
                    "symbol": contract.get("symbol"),
                    "instrument": contract.get("instrument"),
                    "order_type": order_type,
                },
            ) from exc
        status = getattr(trade.orderStatus, "status", "submitted")
        order_id = str(getattr(trade.order, "orderId", ""))
        fill_price = self._safe_float(getattr(trade.orderStatus, "avgFillPrice", 0.0))
        return BrokerOrderResult(
            order_id=order_id or "ibkr-submitted",
            status=status,
            fill_price=fill_price if fill_price > 0 else limit_price,
        )

    async def stream_greeks(self, callback: Callable[[dict[str, Any]], Any]) -> None:
        self._require_connected()
        self._stream_enabled = True
        await callback({"event": "stream_started", "broker": "ibkr"})
        while self._stream_enabled:
            positions = await self.get_positions()
            for position in positions:
                await callback(
                    {
                        "symbol": position["symbol"],
                        "delta": position["delta"],
                        "gamma": position["gamma"],
                        "theta": position["theta"],
                        "vega": position["vega"],
                        "qty": position["qty"],
                    }
                )
            await asyncio.sleep(1.0)

    def stop_stream(self) -> None:
        self._stream_enabled = False

    def _require_connected(self) -> None:
        if not self._ib or not self._connected:
            raise BrokerConnectionError("IBKR not connected")

    def _build_contract(self, payload: dict[str, Any]) -> Any:
        try:
            from ib_insync import Future, FuturesOption, Index, Stock  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise BrokerConnectionError("ib_insync contract classes unavailable", retryable=False) from exc
        normalized = self._normalize_contract_payload(payload)
        instrument = normalized["instrument"]
        symbol = normalized["symbol"]
        exchange = normalized["exchange"]
        currency = normalized["currency"]
        if instrument == "FOP":
            expiry = normalized.get("expiry")
            strike = normalized.get("strike")
            right = normalized.get("right", "C")
            if not expiry or strike is None:
                raise BrokerOrderError("FOP order requires expiry and strike")
            kwargs: dict[str, Any] = {
                "symbol": symbol,
                "lastTradeDateOrContractMonth": str(expiry),
                "strike": float(strike),
                "right": right,
                "exchange": exchange,
                "currency": currency,
            }
            if normalized.get("multiplier"):
                kwargs["multiplier"] = str(normalized["multiplier"])
            if normalized.get("trading_class"):
                kwargs["tradingClass"] = str(normalized["trading_class"])
            return FuturesOption(
                **kwargs,
            )
        if instrument == "IND":
            return Index(symbol=symbol, exchange=exchange, currency=currency)
        if instrument == "STK":
            return Stock(symbol=symbol, exchange=exchange, currency=currency)
        expiry = normalized.get("expiry")
        if not expiry:
            raise BrokerOrderError("FUT contract requires expiry in payload or credentials")
        return Future(
            symbol=symbol,
            lastTradeDateOrContractMonth=str(expiry),
            exchange=exchange,
            currency=currency,
        )

    def _normalize_contract_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        symbol = str(payload.get("symbol", "")).upper()
        if not symbol:
            raise BrokerOrderError("Contract symbol is required")
        raw_instrument = str(payload.get("instrument", "FOP")).upper()
        instrument = self._INSTRUMENT_ALIASES.get(raw_instrument, raw_instrument)
        exchange_overrides = self._credentials.get("exchange_overrides", {}) or {}
        exchange = payload.get("exchange") or exchange_overrides.get(symbol)
        if not exchange:
            exchange = self._DEFAULT_EXCHANGE_BY_SYMBOL.get(symbol, self._credentials.get("exchange", "CME"))
        currency = payload.get("currency", self._credentials.get("currency", "USD"))
        expiry = payload.get("expiry") or self._credentials.get("underlying_expiry")
        right = str(payload.get("right", "C")).upper()
        if right in {"CALL", "C"}:
            right = "C"
        elif right in {"PUT", "P"}:
            right = "P"
        return {
            "symbol": symbol,
            "instrument": instrument,
            "exchange": str(exchange),
            "currency": str(currency),
            "expiry": expiry,
            "strike": payload.get("strike"),
            "right": right,
            "multiplier": payload.get("multiplier", self._credentials.get("multiplier")),
            "trading_class": payload.get("trading_class", self._credentials.get("trading_class")),
        }

    def _build_order(self, action: str, qty: int, order_type: str, limit_price: float | None) -> Any:
        try:
            from ib_insync import LimitOrder, MarketOrder  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise BrokerConnectionError("ib_insync order classes unavailable") from exc
        order_type = order_type.upper()
        if order_type == "LMT":
            if limit_price is None:
                raise BrokerOrderError("Limit order requires limit_price")
            return LimitOrder(action.upper(), qty, float(limit_price))
        return MarketOrder(action.upper(), qty)

    @staticmethod
    def _extract_greeks(ticker: Any) -> dict[str, float]:
        model = getattr(ticker, "modelGreeks", None)
        if model is None:
            return {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
        return {
            "delta": IBKRBroker._safe_float(getattr(model, "delta", 0.0)),
            "gamma": IBKRBroker._safe_float(getattr(model, "gamma", 0.0)),
            "theta": IBKRBroker._safe_float(getattr(model, "theta", 0.0)),
            "vega": IBKRBroker._safe_float(getattr(model, "vega", 0.0)),
        }

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            if value is None:
                return 0.0
            return float(value)
        except Exception:  # noqa: BLE001
            return 0.0
