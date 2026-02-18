from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.api.deps import _set_db_security_context
from backend.db.session import reset_connection_security_context


class _FakeCursor:
    def __init__(self) -> None:
        self.executed: list[str] = []
        self.closed = False

    def execute(self, sql: str) -> None:
        self.executed.append(sql)

    def close(self) -> None:
        self.closed = True


class _FakeConnection:
    def __init__(self) -> None:
        self.cursor_obj = _FakeCursor()

    def cursor(self) -> _FakeCursor:
        return self.cursor_obj


@pytest.mark.asyncio
async def test_set_db_security_context_sets_postgres_session_vars() -> None:
    db = SimpleNamespace(
        get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name="postgresql")),
        execute=AsyncMock(),
    )

    await _set_db_security_context(db, client_id="client-1", is_admin=True)  # type: ignore[arg-type]

    assert db.execute.await_count == 2
    first_stmt, first_params = db.execute.await_args_list[0].args
    second_stmt, second_params = db.execute.await_args_list[1].args
    assert "app.current_client_id" in str(first_stmt)
    assert first_params == {"client_id": "client-1"}
    assert "app.is_admin" in str(second_stmt)
    assert second_params == {"is_admin": "true"}


@pytest.mark.asyncio
async def test_set_db_security_context_noop_for_non_postgres() -> None:
    db = SimpleNamespace(
        get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name="sqlite")),
        execute=AsyncMock(),
    )

    await _set_db_security_context(db, client_id="client-1", is_admin=False)  # type: ignore[arg-type]
    assert db.execute.await_count == 0


def test_reset_connection_security_context_resets_postgres_values() -> None:
    conn = _FakeConnection()

    reset_connection_security_context(conn, "postgresql")

    assert conn.cursor_obj.executed == [
        "SELECT set_config('app.current_client_id', '', false)",
        "SELECT set_config('app.is_admin', 'false', false)",
    ]
    assert conn.cursor_obj.closed is True


def test_reset_connection_security_context_noop_for_non_postgres() -> None:
    conn = _FakeConnection()

    reset_connection_security_context(conn, "sqlite")

    assert conn.cursor_obj.executed == []
    assert conn.cursor_obj.closed is False
