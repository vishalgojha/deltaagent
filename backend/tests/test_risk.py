import pytest

from backend.agent.risk import RiskGovernor, RiskParameters, RiskViolation


def base_order() -> dict:
    return {"action": "BUY", "symbol": "ES", "qty": 1, "order_type": "MKT"}


def test_risk_allows_valid_order() -> None:
    gov = RiskGovernor()
    gov._is_market_hours = lambda _: True  # type: ignore[attr-defined]
    gov.validate_order(
        client_id="c1",
        order=base_order(),
        net_delta=0.1,
        projected_delta=0.15,
        daily_pnl=0.0,
        recent_trade_pnls=None,
        open_legs=1,
        bid=10.0,
        ask=10.2,
        params=RiskParameters(),
    )


def test_risk_blocks_size() -> None:
    gov = RiskGovernor()
    gov._is_market_hours = lambda _: True  # type: ignore[attr-defined]
    with pytest.raises(RiskViolation) as exc:
        gov.validate_order(
            client_id="c1",
            order={**base_order(), "qty": 11},
            net_delta=0.0,
            projected_delta=0.1,
            daily_pnl=0.0,
            recent_trade_pnls=None,
            open_legs=1,
            bid=10.0,
            ask=10.2,
            params=RiskParameters(),
        )
    assert exc.value.rule == "MAX_SINGLE_ORDER_SIZE"


def test_risk_circuit_breaker_from_recent_trade_pnls() -> None:
    gov = RiskGovernor()
    gov._is_market_hours = lambda _: True  # type: ignore[attr-defined]
    with pytest.raises(RiskViolation) as exc:
        gov.validate_order(
            client_id="c1",
            order=base_order(),
            net_delta=0.0,
            projected_delta=0.1,
            daily_pnl=0.0,
            recent_trade_pnls=[-700.0, -650.0, -800.0],
            open_legs=1,
            bid=10.0,
            ask=10.2,
            params=RiskParameters(),
        )
    assert exc.value.rule == "CIRCUIT_BREAKER"
