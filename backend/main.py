import asyncio
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import from_url as redis_from_url
from sqlalchemy import text

from backend.agent.manager import AgentManager
from backend.api import admin, agent, auth, clients, positions, reference, strategy_templates, trades, websocket
from backend.config import get_settings
from backend.db.models import Base
from backend.db.session import SessionLocal, engine
from backend.logging import configure_logging
from backend.safety.emergency_halt import EmergencyHaltController


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = get_settings()
    if settings.auto_create_tables:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    try:
        app.state.redis = redis_from_url(settings.redis_url, decode_responses=True)
        await app.state.redis.ping()
    except Exception:  # noqa: BLE001
        app.state.redis = None
    app.state.emergency_halt = EmergencyHaltController(redis_client=app.state.redis)
    app.state.agent_manager = AgentManager(
        emergency_halt=app.state.emergency_halt,
        redis_client=app.state.redis,
    )
    app.state.db_sessionmaker = SessionLocal
    yield
    await app.state.agent_manager.shutdown()
    if app.state.redis is not None:
        await app.state.redis.close()


app = FastAPI(title="Trading Agent", lifespan=lifespan)
settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(clients.router)
app.include_router(positions.router)
app.include_router(trades.router)
app.include_router(agent.router)
app.include_router(strategy_templates.router)
app.include_router(reference.router)
app.include_router(websocket.router)


@app.get("/")
async def root() -> dict:
    return {"status": "ok", "service": "trading-agent"}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/health/ready")
async def readiness() -> dict:
    settings = get_settings()
    checks: dict[str, dict] = {}

    db_ok = False
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        db_ok = True
        checks["database"] = {"ok": True}
    except Exception as exc:  # noqa: BLE001
        checks["database"] = {"ok": False, "error": str(exc)}

    redis_ok = False
    if app.state.redis is None:
        checks["redis"] = {"ok": False, "error": "redis client not initialized"}
    else:
        try:
            await app.state.redis.ping()
            redis_ok = True
            checks["redis"] = {"ok": True}
        except Exception as exc:  # noqa: BLE001
            checks["redis"] = {"ok": False, "error": str(exc)}

    broker_ok = True
    broker_details: dict[str, dict] = {}
    if settings.use_mock_broker:
        broker_details["mode"] = {"ok": True, "detail": "mock broker enabled"}
    else:
        ib_ok = await _tcp_check(settings.ibkr_gateway_host, settings.ibkr_gateway_port)
        broker_details["ibkr_gateway"] = {"ok": ib_ok, "host": settings.ibkr_gateway_host, "port": settings.ibkr_gateway_port}
        ph = urlparse(settings.phillip_api_base)
        ph_host = ph.hostname or "api.phillipcapital.com.au"
        ph_port = ph.port or (443 if ph.scheme == "https" else 80)
        ph_ok = await _tcp_check(ph_host, ph_port)
        broker_details["phillip_api"] = {"ok": ph_ok, "host": ph_host, "port": ph_port}
        broker_ok = ib_ok and ph_ok
    checks["broker_reachability"] = broker_details

    ready = db_ok and redis_ok and broker_ok
    payload = {"ready": ready, "checks": checks}
    if not ready:
        raise HTTPException(status_code=503, detail=payload)
    return payload


async def _tcp_check(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        conn = asyncio.open_connection(host, port)
        reader, writer = await asyncio.wait_for(conn, timeout=timeout)
        writer.close()
        await writer.wait_closed()
        del reader
        return True
    except Exception:  # noqa: BLE001
        return False
