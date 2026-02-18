from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.config import get_settings


settings = get_settings()
engine = create_async_engine(settings.database_url, future=True, echo=False)
SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


def reset_connection_security_context(dbapi_connection: Any, dialect_name: str) -> None:
    if dialect_name != "postgresql":
        return

    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("SELECT set_config('app.current_client_id', '', false)")
        cursor.execute("SELECT set_config('app.is_admin', 'false', false)")
    finally:
        cursor.close()


@event.listens_for(engine.sync_engine, "checkout")
def _on_checkout_reset_security_context(dbapi_connection, connection_record, connection_proxy) -> None:  # noqa: ANN001
    reset_connection_security_context(dbapi_connection, engine.sync_engine.dialect.name)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
