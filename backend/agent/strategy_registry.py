from dataclasses import dataclass
from typing import Any

from backend.agent.risk import RiskViolation


@dataclass(frozen=True)
class StrategySpec:
    strategy_id: str
    name: str
    max_legs: int
    allowed_instruments: set[str]
    allowed_symbols: set[str]
    require_defined_risk: bool


class StrategyRegistry:
    """Allowlist-based strategy policy for futures options execution."""

    def __init__(self) -> None:
        self._specs: dict[str, StrategySpec] = {
            "delta_rebalance_single": StrategySpec(
                strategy_id="delta_rebalance_single",
                name="Single-leg delta rebalance",
                max_legs=1,
                allowed_instruments={"FOP", "FUT"},
                allowed_symbols={"ES", "NQ", "SI", "GC", "CL"},
                require_defined_risk=False,
            ),
            "vertical_spread": StrategySpec(
                strategy_id="vertical_spread",
                name="Defined-risk vertical spread",
                max_legs=2,
                allowed_instruments={"FOP"},
                allowed_symbols={"ES", "NQ", "SI", "GC", "CL"},
                require_defined_risk=True,
            ),
            "iron_condor": StrategySpec(
                strategy_id="iron_condor",
                name="Defined-risk iron condor",
                max_legs=4,
                allowed_instruments={"FOP"},
                allowed_symbols={"ES", "NQ", "SI", "GC", "CL"},
                require_defined_risk=True,
            ),
            "long_strangle": StrategySpec(
                strategy_id="long_strangle",
                name="Long strangle",
                max_legs=2,
                allowed_instruments={"FOP"},
                allowed_symbols={"ES", "NQ", "SI", "GC", "CL"},
                require_defined_risk=False,
            ),
            "short_strangle_defined": StrategySpec(
                strategy_id="short_strangle_defined",
                name="Short strangle with wings",
                max_legs=4,
                allowed_instruments={"FOP"},
                allowed_symbols={"ES", "NQ", "SI", "GC", "CL"},
                require_defined_risk=True,
            ),
        }

    def validate_trade_payload(self, trade_payload: dict[str, Any]) -> StrategySpec:
        strategy_id = str(trade_payload.get("strategy_id") or "delta_rebalance_single").strip()
        spec = self._specs.get(strategy_id)
        if spec is None:
            raise RiskViolation("STRATEGY_POLICY", f"unknown strategy_id={strategy_id}")

        legs = self._extract_legs(trade_payload)
        if not legs:
            raise RiskViolation("STRATEGY_POLICY", "trade payload has no executable legs")
        if len(legs) > spec.max_legs:
            raise RiskViolation("STRATEGY_POLICY", f"strategy {strategy_id} max_legs={spec.max_legs} got={len(legs)}")

        for leg in legs:
            symbol = str(leg.get("symbol") or trade_payload.get("symbol") or "").upper()
            instrument = str(leg.get("instrument") or trade_payload.get("instrument") or "FOP").upper()
            if symbol not in spec.allowed_symbols:
                raise RiskViolation("STRATEGY_POLICY", f"symbol {symbol} not allowed for {strategy_id}")
            if instrument not in spec.allowed_instruments:
                raise RiskViolation("STRATEGY_POLICY", f"instrument {instrument} not allowed for {strategy_id}")

        if spec.require_defined_risk and not self._is_defined_risk(legs):
            raise RiskViolation("STRATEGY_POLICY", f"strategy {strategy_id} requires defined-risk structure")

        return spec

    def validate_trade_payload_with_profile(
        self,
        trade_payload: dict[str, Any],
        profile: dict[str, Any],
        client_tier: str | None = None,
    ) -> StrategySpec:
        strategy_id = str(profile.get("strategy_id", "")).strip()
        if not strategy_id:
            raise RiskViolation("STRATEGY_POLICY", "strategy profile missing strategy_id")

        allowed_symbols = {str(v).upper() for v in profile.get("allowed_symbols", [])}
        allowed_asset_classes = {str(v).lower() for v in profile.get("allowed_asset_classes", [])}
        tier_allowlist = {str(v).lower() for v in profile.get("tier_allowlist", [])}
        max_legs = int(profile.get("max_legs", 1))
        require_defined_risk = bool(profile.get("require_defined_risk", False))

        spec = StrategySpec(
            strategy_id=strategy_id,
            name=str(profile.get("name", strategy_id)),
            max_legs=max_legs,
            allowed_instruments={"FOP", "FUT", "OPT", "OPTION"},
            allowed_symbols=allowed_symbols or {"ES", "NQ"},
            require_defined_risk=require_defined_risk,
        )

        legs = self._extract_legs(trade_payload)
        if not legs:
            raise RiskViolation("STRATEGY_POLICY", "trade payload has no executable legs")
        if len(legs) > spec.max_legs:
            raise RiskViolation("STRATEGY_POLICY", f"strategy {strategy_id} max_legs={spec.max_legs} got={len(legs)}")

        for leg in legs:
            symbol = str(leg.get("symbol") or trade_payload.get("symbol") or "").upper()
            instrument = str(leg.get("instrument") or trade_payload.get("instrument") or "FOP").upper()
            asset_class = self._instrument_to_asset_class(instrument)
            if symbol not in spec.allowed_symbols:
                raise RiskViolation("STRATEGY_POLICY", f"symbol {symbol} not allowed for {strategy_id}")
            if allowed_asset_classes and asset_class not in allowed_asset_classes:
                raise RiskViolation("STRATEGY_POLICY", f"asset class {asset_class} not allowed for {strategy_id}")

        if tier_allowlist and client_tier and client_tier.lower() not in tier_allowlist:
            raise RiskViolation("STRATEGY_POLICY", f"tier {client_tier} not allowed for {strategy_id}")

        if spec.require_defined_risk and not self._is_defined_risk(legs):
            raise RiskViolation("STRATEGY_POLICY", f"strategy {strategy_id} requires defined-risk structure")

        return spec

    @staticmethod
    def _extract_legs(trade_payload: dict[str, Any]) -> list[dict[str, Any]]:
        raw_legs = trade_payload.get("legs")
        if isinstance(raw_legs, list) and raw_legs:
            return [leg for leg in raw_legs if isinstance(leg, dict)]
        return [trade_payload]

    @staticmethod
    def _is_defined_risk(legs: list[dict[str, Any]]) -> bool:
        # Minimal policy: spread/condor-like structures need at least 2 legs and both buy/sell present.
        if len(legs) < 2:
            return False
        actions = {str(leg.get("action", "")).upper() for leg in legs}
        return "BUY" in actions and "SELL" in actions

    @staticmethod
    def _instrument_to_asset_class(instrument: str) -> str:
        normalized = instrument.upper()
        if normalized in {"FOP", "OPT", "OPTION"}:
            return "fop"
        if normalized in {"FUT", "FUTURE"}:
            return "future"
        return "unknown"
