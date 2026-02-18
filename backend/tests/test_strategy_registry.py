import pytest

from backend.agent.risk import RiskViolation
from backend.agent.strategy_registry import StrategyRegistry


def test_registry_accepts_default_single_leg_rebalance() -> None:
    registry = StrategyRegistry()
    spec = registry.validate_trade_payload(
        {
            "action": "BUY",
            "symbol": "ES",
            "instrument": "FOP",
            "qty": 1,
            "order_type": "MKT",
        }
    )
    assert spec.strategy_id == "delta_rebalance_single"


def test_registry_blocks_disallowed_symbol() -> None:
    registry = StrategyRegistry()
    with pytest.raises(RiskViolation) as exc:
        registry.validate_trade_payload(
            {
                "strategy_id": "delta_rebalance_single",
                "action": "BUY",
                "symbol": "AAPL",
                "instrument": "FOP",
                "qty": 1,
                "order_type": "MKT",
            }
        )
    assert exc.value.rule == "STRATEGY_POLICY"


def test_registry_requires_defined_risk_for_vertical() -> None:
    registry = StrategyRegistry()
    with pytest.raises(RiskViolation):
        registry.validate_trade_payload(
            {
                "strategy_id": "vertical_spread",
                "action": "SELL",
                "symbol": "ES",
                "instrument": "FOP",
                "qty": 1,
                "order_type": "MKT",
            }
        )

    spec = registry.validate_trade_payload(
        {
            "strategy_id": "vertical_spread",
            "symbol": "ES",
            "legs": [
                {"action": "BUY", "symbol": "ES", "instrument": "FOP", "qty": 1},
                {"action": "SELL", "symbol": "ES", "instrument": "FOP", "qty": 1},
            ],
        }
    )
    assert spec.strategy_id == "vertical_spread"


def test_registry_profile_validation_enforces_tier_allowlist() -> None:
    registry = StrategyRegistry()
    profile = {
        "strategy_id": "condor_profile",
        "name": "Condor Profile",
        "allowed_symbols": ["ES", "NQ"],
        "allowed_asset_classes": ["fop"],
        "max_legs": 4,
        "require_defined_risk": True,
        "tier_allowlist": ["enterprise"],
    }
    trade = {
        "strategy_id": "condor_profile",
        "symbol": "ES",
        "legs": [
            {"action": "SELL", "symbol": "ES", "instrument": "FOP"},
            {"action": "BUY", "symbol": "ES", "instrument": "FOP"},
        ],
    }

    with pytest.raises(RiskViolation):
        registry.validate_trade_payload_with_profile(trade, profile, client_tier="basic")

    spec = registry.validate_trade_payload_with_profile(trade, profile, client_tier="enterprise")
    assert spec.strategy_id == "condor_profile"
