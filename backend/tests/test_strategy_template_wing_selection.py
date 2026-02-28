import pytest

from backend.strategy_templates.service import StrategyTemplateService


def test_select_wing_strikes_uses_adjacent_strikes_when_width_is_tight() -> None:
    strikes = [4900.0, 4950.0, 5000.0, 5050.0, 5100.0]
    lower, upper = StrategyTemplateService._select_wing_strikes(
        strikes=strikes,
        center_strike=5000.0,
        lower_width=5.0,
        upper_width=5.0,
    )
    assert lower == 4950.0
    assert upper == 5050.0


def test_select_wing_strikes_requires_both_sides_of_center() -> None:
    strikes = [5000.0, 5050.0, 5100.0]
    with pytest.raises(ValueError, match="Need strikes both below and above center"):
        StrategyTemplateService._select_wing_strikes(
            strikes=strikes,
            center_strike=5000.0,
            lower_width=50.0,
            upper_width=50.0,
        )
