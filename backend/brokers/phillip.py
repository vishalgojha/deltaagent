import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import logging
from typing import Any

import httpx

from backend.brokers.base import BrokerAuthError, BrokerBase, BrokerOrderError, BrokerOrderResult
from backend.config import get_settings


logger = logging.getLogger(__name__)


class PhillipBroker(BrokerBase):
    def __init__(self, credentials: dict | None = None) -> None:
        cfg = get_settings()
        creds = credentials or {}
        self._credentials = creds
        self._base_url = cfg.phillip_api_base.rstrip("/")
        self._client_id = creds.get("client_id") or cfg.phillip_client_id
        self._client_secret = creds.get("client_secret") or cfg.phillip_client_secret
        self._token: str | None = None
        self._token_expires_at: datetime | None = None
        self._http = httpx.AsyncClient(timeout=20)
        self._request_retries = int(creds.get("request_retries", 3))
        self._request_backoff_seconds = float(creds.get("request_backoff_seconds", 0.4))

    async def authenticate(self) -> None:
        if not self._client_id or not self._client_secret:
            raise BrokerAuthError(
                "Missing Phillip API credentials",
                retryable=False,
                context={"has_client_id": bool(self._client_id), "has_client_secret": bool(self._client_secret)},
            )
        response = await self._request_with_retry(
            "POST",
            "/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
            require_auth=False,
        )
        payload = response.json()
        self._token = payload["access_token"]
        self._token_expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=int(payload.get("expires_in", 300))
        )

    async def refresh_token(self) -> None:
        if not self._token_expires_at or datetime.now(timezone.utc) >= self._token_expires_at:
            await self.authenticate()

    async def connect(self) -> None:
        await self.authenticate()

    async def _headers(self) -> dict[str, str]:
        await self.refresh_token()
        return {"Authorization": f"Bearer {self._token}"}

    async def get_positions(self) -> list[dict[str, Any]]:
        response = await self._request_with_retry("GET", "/positions")
        positions: list[dict[str, Any]] = []
        for row in response.json().get("positions", []):
            positions.append(
                {
                    "symbol": row.get("symbol"),
                    "instrument_type": row.get("instrumentType", "FOP"),
                    "strike": row.get("strike"),
                    "expiry": row.get("expiry"),
                    "qty": int(row.get("quantity", 0)),
                    "delta": float(row.get("delta", 0)),
                    "gamma": float(row.get("gamma", 0)),
                    "theta": float(row.get("theta", 0)),
                    "vega": float(row.get("vega", 0)),
                    "avg_price": float(row.get("avgPrice", 0)),
                }
            )
        return positions

    async def get_greeks(self, contract: dict[str, Any]) -> dict[str, float]:
        return {
            "delta": float(contract.get("delta", 0)),
            "gamma": float(contract.get("gamma", 0)),
            "theta": float(contract.get("theta", 0)),
            "vega": float(contract.get("vega", 0)),
        }

    async def get_options_chain(self, symbol: str, expiry: str | None = None) -> list[dict[str, Any]]:
        params = {"symbol": symbol}
        if expiry:
            params["expiry"] = expiry
        response = await self._request_with_retry("GET", "/options/chain", params=params)
        return response.json().get("chain", [])

    async def get_market_data(self, symbol: str) -> dict[str, float]:
        response = await self._request_with_retry("GET", f"/market-data/{symbol}")
        payload = response.json()
        return {
            "underlying_price": float(payload.get("last", 0)),
            "iv_rank": float(payload.get("ivRank", 0)),
            "iv_percentile": float(payload.get("ivPercentile", 0)),
            "bid": float(payload.get("bid", 0)),
            "ask": float(payload.get("ask", 0)),
        }

    async def submit_order(
        self,
        contract: dict[str, Any],
        action: str,
        qty: int,
        order_type: str,
        limit_price: float | None = None,
    ) -> BrokerOrderResult:
        payload = self._normalize_order_payload(
            contract=contract,
            action=action,
            qty=qty,
            order_type=order_type,
            limit_price=limit_price,
        )
        response = await self._request_with_retry("POST", "/orders", json=payload)
        body = response.json()
        return BrokerOrderResult(
            order_id=str(body.get("orderId")),
            status=body.get("status", "submitted"),
            fill_price=body.get("fillPrice"),
        )

    async def stream_greeks(self, callback: Callable[[dict[str, Any]], Any]) -> None:
        await callback({"event": "stream_started", "broker": "phillip"})

    def _normalize_order_payload(
        self,
        contract: dict[str, Any],
        action: str,
        qty: int,
        order_type: str,
        limit_price: float | None,
    ) -> dict[str, Any]:
        right = contract.get("right")
        option_type = None
        if right is not None:
            mapped = str(right).upper()
            if mapped in {"C", "CALL"}:
                option_type = "CALL"
            elif mapped in {"P", "PUT"}:
                option_type = "PUT"
        return {
            "symbol": contract.get("symbol"),
            "instrument": str(contract.get("instrument", "FOP")).upper(),
            "exchange": contract.get("exchange", self._credentials.get("exchange", "CME")),
            "currency": contract.get("currency", self._credentials.get("currency", "USD")),
            "action": action.upper(),
            "qty": qty,
            "orderType": order_type.upper(),
            "timeInForce": contract.get("time_in_force", "DAY"),
            "clientOrderId": contract.get("client_order_id"),
            "limitPrice": limit_price,
            "strike": contract.get("strike"),
            "expiry": contract.get("expiry"),
            "optionType": option_type,
        }

    async def _request_with_retry(
        self,
        method: str,
        path: str,
        *,
        require_auth: bool = True,
        **kwargs: Any,
    ) -> httpx.Response:
        retries = max(1, self._request_retries)
        transient_statuses = {408, 425, 429, 500, 502, 503, 504}
        last_error: Exception | None = None
        auth_retry_used = False
        for attempt in range(1, retries + 1):
            try:
                headers = kwargs.pop("headers", {}) or {}
                if require_auth:
                    headers = {**headers, **(await self._headers())}
                response = await self._http.request(
                    method=method.upper(),
                    url=f"{self._base_url}{path}",
                    headers=headers,
                    **kwargs,
                )
                if require_auth and response.status_code == 401 and not auth_retry_used:
                    auth_retry_used = True
                    self._token_expires_at = None
                    await self.refresh_token()
                    continue
                if response.status_code < 400:
                    return response
                if response.status_code in transient_statuses and attempt < retries:
                    delay = self._request_backoff_seconds * (2 ** (attempt - 1))
                    logger.warning(
                        "Phillip transient response; retrying",
                        extra={"method": method, "path": path, "status": response.status_code, "attempt": attempt},
                    )
                    await asyncio.sleep(delay)
                    continue
                if path == "/oauth/token":
                    raise BrokerAuthError(
                        f"Phillip auth failed (status={response.status_code}, endpoint={path}, body={response.text})",
                        retryable=response.status_code in transient_statuses,
                        context={"status": response.status_code, "endpoint": path},
                    )
                raise BrokerOrderError(
                    f"Phillip request failed (method={method.upper()}, endpoint={path}, status={response.status_code}, body={response.text})",
                    retryable=response.status_code in transient_statuses,
                    context={"method": method.upper(), "endpoint": path, "status": response.status_code},
                )
            except (BrokerAuthError, BrokerOrderError):
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt >= retries:
                    break
                delay = self._request_backoff_seconds * (2 ** (attempt - 1))
                logger.warning(
                    "Phillip request error; retrying",
                    extra={"method": method, "path": path, "attempt": attempt, "error": str(exc)},
                )
                await asyncio.sleep(delay)
        if path == "/oauth/token":
            raise BrokerAuthError(
                f"Phillip auth failed after retries: {last_error}",
                retryable=True,
                context={"endpoint": path, "retries": retries},
            )
        raise BrokerOrderError(
            f"Phillip request failed after retries (method={method.upper()}, endpoint={path}): {last_error}",
            retryable=True,
            context={"method": method.upper(), "endpoint": path, "retries": retries},
        )
