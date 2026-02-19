import uuid
from datetime import datetime, timezone
import asyncio
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.jwt import hash_password
from backend.auth.vault import CredentialVault
from backend.api.deps import assert_client_scope, get_current_client
from backend.api.error_utils import broker_http_exception
from backend.brokers.base import BrokerError
from backend.db.models import Client
from backend.db.session import get_db_session
from backend.schemas import BrokerConnectRequest, BrokerPreflightCheck, BrokerPreflightResponse, ClientOut, OnboardRequest


router = APIRouter(prefix="/clients", tags=["clients"])
vault = CredentialVault()


@router.post("/onboard", response_model=ClientOut)
async def onboard_client(payload: OnboardRequest, db: AsyncSession = Depends(get_db_session)) -> ClientOut:
    client = Client(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        broker_type=payload.broker_type,
        encrypted_creds=vault.encrypt(payload.broker_credentials),
        risk_params=payload.risk_parameters,
        mode="confirmation",
        tier=payload.subscription_tier,
        is_active=True,
    )
    db.add(client)
    await db.commit()
    await db.refresh(client)
    return ClientOut.model_validate(client)


@router.post("/{id}/connect-broker")
async def connect_broker(
    id: uuid.UUID,
    request: Request,
    payload: BrokerConnectRequest | None = Body(default=None),
    current_client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    assert_client_scope(id, current_client)
    if payload and payload.broker_credentials:
        current_client.encrypted_creds = vault.encrypt(payload.broker_credentials)
        await db.commit()
    try:
        creds = vault.decrypt(current_client.encrypted_creds)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Credential decrypt failed: {exc}") from exc
    manager = request.app.state.agent_manager
    try:
        agent = await manager.get_agent(
            client_id=id,
            broker_type=current_client.broker_type,
            broker_credentials=creds,
            db=db,
            force_recreate_broker=True,
        )
    except BrokerError as exc:
        raise broker_http_exception(exc, operation="connect", broker=current_client.broker_type) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Broker connection failed: {exc}") from exc
    return {"connected": True, "client_id": id, "broker": current_client.broker_type}


@router.post("/{id}/broker/preflight", response_model=BrokerPreflightResponse)
async def preflight_broker(
    id: uuid.UUID,
    request: Request,
    payload: BrokerConnectRequest | None = Body(default=None),
    current_client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db_session),
) -> BrokerPreflightResponse:
    assert_client_scope(id, current_client)
    checks: list[BrokerPreflightCheck] = []
    blocking_issues: list[str] = []
    warnings: list[str] = []
    fix_hints: list[str] = []

    if payload and payload.broker_credentials:
        current_client.encrypted_creds = vault.encrypt(payload.broker_credentials)
        await db.commit()
    try:
        creds = vault.decrypt(current_client.encrypted_creds)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Credential decrypt failed: {exc}") from exc

    if current_client.broker_type == "ibkr":
        _append_ibkr_preflight_checks(checks, blocking_issues, warnings, fix_hints, creds)
        host = str(creds.get("host") or "").strip()
        port = creds.get("port")
        if host and isinstance(port, int) and port > 0:
            tcp_ok = await _check_tcp(host, port)
            if tcp_ok:
                checks.append(
                    BrokerPreflightCheck(
                        key="socket",
                        title="Gateway socket reachability",
                        status="pass",
                        detail=f"TCP reachable at {host}:{port}",
                    )
                )
            else:
                blocking_issues.append(f"Cannot reach IBKR gateway at {host}:{port}.")
                fix_hints.append("Keep IBKR Gateway open, enable API socket access, and verify host/port.")
                checks.append(
                    BrokerPreflightCheck(
                        key="socket",
                        title="Gateway socket reachability",
                        status="fail",
                        detail=f"TCP connection failed at {host}:{port}",
                    )
                )
    else:
        _append_phillip_preflight_checks(checks, blocking_issues, warnings, fix_hints, creds)

    if not any(check.status == "fail" for check in checks):
        manager = request.app.state.agent_manager
        try:
            agent = await manager.get_agent(
                client_id=id,
                broker_type=current_client.broker_type,
                broker_credentials=creds,
                db=db,
                force_recreate_broker=True,
            )
            market = await agent.broker.get_market_data("ES")
            price = float(market.get("underlying_price", 0.0))
            if price > 0:
                checks.append(
                    BrokerPreflightCheck(
                        key="market_data",
                        title="Market data stream",
                        status="pass",
                        detail=f"Received market data (ES={price:.2f})",
                    )
                )
            else:
                warning = "Connected, but market data returned 0.0 for ES"
                warnings.append(warning)
                fix_hints.append("Enable futures/options market data permissions or delayed market data in IBKR.")
                checks.append(
                    BrokerPreflightCheck(
                        key="market_data",
                        title="Market data stream",
                        status="warn",
                        detail=warning,
                    )
                )
        except BrokerError as exc:
            message = str(exc)
            blocking_issues.append(message)
            fix_hints.append("Verify broker credentials, API settings, and ensure the gateway/session is running.")
            checks.append(
                BrokerPreflightCheck(
                    key="broker_connect",
                    title="Broker connection",
                    status="fail",
                    detail=message,
                )
            )

    ok = len(blocking_issues) == 0
    return BrokerPreflightResponse(
        ok=ok,
        broker=current_client.broker_type,
        checks=checks,
        blocking_issues=blocking_issues,
        warnings=warnings,
        fix_hints=fix_hints,
        checked_at=datetime.now(timezone.utc),
    )


def _append_ibkr_preflight_checks(
    checks: list[BrokerPreflightCheck],
    blocking_issues: list[str],
    warnings: list[str],
    fix_hints: list[str],
    creds: dict,
) -> None:
    host = str(creds.get("host") or "").strip()
    port = creds.get("port")
    client_id = creds.get("client_id")
    if not host:
        blocking_issues.append("IBKR host is missing.")
        fix_hints.append("Set IBKR host, e.g. localhost for local backend or host.docker.internal in Docker.")
        checks.append(BrokerPreflightCheck(key="host", title="IBKR host", status="fail", detail="Missing host"))
    else:
        checks.append(BrokerPreflightCheck(key="host", title="IBKR host", status="pass", detail=f"Host={host}"))

    if not isinstance(port, int) or port <= 0:
        blocking_issues.append("IBKR port is invalid.")
        fix_hints.append("Use a valid numeric IBKR API port (typically 4002 for paper gateway).")
        checks.append(BrokerPreflightCheck(key="port", title="IBKR port", status="fail", detail=f"Invalid port={port}"))
    else:
        checks.append(BrokerPreflightCheck(key="port", title="IBKR port", status="pass", detail=f"Port={port}"))

    if not isinstance(client_id, int) or client_id < 0:
        blocking_issues.append("IBKR client_id must be a non-negative integer.")
        fix_hints.append("Use a unique client_id (for example 11, 12, 13) to avoid error 326.")
        checks.append(
            BrokerPreflightCheck(
                key="client_id",
                title="Client ID format",
                status="fail",
                detail=f"Invalid client_id={client_id}",
            )
        )
    else:
        detail = f"client_id={client_id}"
        status = "pass"
        if client_id in {0, 1}:
            status = "warn"
            warning = f"client_id={client_id} may collide with other running API sessions."
            warnings.append(warning)
            fix_hints.append("Pick a dedicated client_id per app session to avoid collisions.")
            detail = warning
        checks.append(BrokerPreflightCheck(key="client_id", title="Client ID format", status=status, detail=detail))

    under = str(creds.get("underlying_instrument") or "IND").upper()
    if under not in {"IND", "FUT", "STK"}:
        warnings.append(f"Underlying instrument '{under}' is unusual for this setup.")
        fix_hints.append("Use IND for index market data, or FUT with explicit underlying_expiry when needed.")
        checks.append(
            BrokerPreflightCheck(
                key="underlying_instrument",
                title="Underlying instrument",
                status="warn",
                detail=f"Configured instrument={under}",
            )
        )
    else:
        checks.append(
            BrokerPreflightCheck(
                key="underlying_instrument",
                title="Underlying instrument",
                status="pass",
                detail=f"Configured instrument={under}",
            )
        )


def _append_phillip_preflight_checks(
    checks: list[BrokerPreflightCheck],
    blocking_issues: list[str],
    warnings: list[str],
    fix_hints: list[str],
    creds: dict,
) -> None:
    client_id = str(creds.get("client_id") or "").strip()
    client_secret = str(creds.get("client_secret") or "").strip()
    if not client_id:
        blocking_issues.append("Phillip client_id is missing.")
        fix_hints.append("Provide Phillip API client_id.")
        checks.append(BrokerPreflightCheck(key="client_id", title="Phillip client ID", status="fail", detail="Missing client_id"))
    else:
        checks.append(BrokerPreflightCheck(key="client_id", title="Phillip client ID", status="pass", detail="Configured"))

    if not client_secret:
        blocking_issues.append("Phillip client_secret is missing.")
        fix_hints.append("Provide Phillip API client_secret.")
        checks.append(
            BrokerPreflightCheck(
                key="client_secret",
                title="Phillip client secret",
                status="fail",
                detail="Missing client_secret",
            )
        )
    else:
        checks.append(
            BrokerPreflightCheck(
                key="client_secret",
                title="Phillip client secret",
                status="pass",
                detail="Configured",
            )
        )
    if not blocking_issues:
        checks.append(
            BrokerPreflightCheck(
                key="oauth",
                title="OAuth credentials format",
                status="warn",
                detail="Format looks valid; token validation runs in broker connection step.",
            )
        )
        warnings.append("OAuth access token validity is checked during connect/market data probe.")


async def _check_tcp(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
        writer.close()
        await writer.wait_closed()
        del reader
        return True
    except Exception:  # noqa: BLE001
        return False
