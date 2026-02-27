import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.api import agent as agent_api
from backend.api.deps import get_current_client


@pytest.mark.asyncio
async def test_get_parameters_merges_defaults_for_legacy_clients() -> None:
    client_id = uuid.uuid4()
    app = FastAPI()
    app.include_router(agent_api.router)

    async def override_current_client() -> SimpleNamespace:
        return SimpleNamespace(
            id=client_id,
            risk_params={
                "delta_threshold": 0.4,
                "max_size": 7,
            },
        )

    app.dependency_overrides[get_current_client] = override_current_client

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        response = await http.get(f"/clients/{client_id}/agent/parameters")

    assert response.status_code == 200
    payload = response.json()
    risk = payload["risk_parameters"]

    assert risk["delta_threshold"] == pytest.approx(0.4)
    assert risk["max_size"] == 7
    assert risk["max_loss"] == pytest.approx(5000.0)
    assert risk["max_open_positions"] == 20
    assert risk["execution_alert_slippage_warn_bps"] == pytest.approx(15.0)
    assert risk["execution_alert_slippage_critical_bps"] == pytest.approx(30.0)
    assert risk["execution_alert_latency_warn_ms"] == 3000
    assert risk["execution_alert_latency_critical_ms"] == 8000
    assert risk["execution_alert_fill_coverage_warn_pct"] == pytest.approx(75.0)
    assert risk["execution_alert_fill_coverage_critical_pct"] == pytest.approx(50.0)
