from datetime import UTC, datetime, timedelta

import pytest

from backend.strategy_templates.service import StrategyTemplateService


def test_select_expiry_parses_month_only_expiry() -> None:
    now = datetime.now(UTC).date()
    target_month_date = now + timedelta(days=45)
    month_token = f"{target_month_date.year:04d}{target_month_date.month:02d}"
    chain_rows = [{"expiry": month_token}, {"expiry": month_token}]

    selected_expiry, selected_dte = StrategyTemplateService._select_expiry(chain_rows, dte_min=1, dte_max=365)

    assert selected_expiry == month_token
    assert selected_dte >= 1


def test_select_expiry_error_lists_available_expiries() -> None:
    now = datetime.now(UTC).date()
    exp_1 = (now + timedelta(days=20)).strftime("%Y%m%d")
    exp_2 = (now + timedelta(days=35)).strftime("%Y%m%d")

    with pytest.raises(ValueError, match="Available expiries") as exc:
        StrategyTemplateService._select_expiry(
            [{"expiry": exp_1}, {"expiry": exp_2}],
            dte_min=1,
            dte_max=5,
        )

    message = str(exc.value)
    assert "configured DTE range 1-5" in message
    assert exp_1 in message
    assert exp_2 in message
