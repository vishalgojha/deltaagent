import uuid
import calendar
from dataclasses import dataclass
from datetime import UTC, date, datetime
import re
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent.risk import RiskGovernor
from backend.brokers.base import BrokerBase, BrokerOrderError
from backend.db.models import AuditLog, Client, Position, StrategyExecution, StrategyTemplate, Trade
from backend.execution.fills import build_trade_fill_from_order, estimate_expected_price
from backend.safety.emergency_halt import EmergencyHaltController
from backend.schemas import StrategyTemplateCreateRequest, StrategyTemplateUpdateRequest


@dataclass
class ResolvedStrategy:
    template_id: int
    strategy_type: str
    expiry: str
    dte: int
    center_strike: float
    estimated_net_premium: float
    estimated_max_risk: float
    estimated_net_delta: float
    contracts: int
    greeks: dict[str, float]
    pnl_curve: list[dict[str, float]]
    legs: list[dict[str, Any]]

    def to_payload(self) -> dict[str, Any]:
        return {
            "template_id": self.template_id,
            "strategy_type": self.strategy_type,
            "expiry": self.expiry,
            "dte": self.dte,
            "center_strike": self.center_strike,
            "estimated_net_premium": self.estimated_net_premium,
            "estimated_max_risk": self.estimated_max_risk,
            "estimated_net_delta": self.estimated_net_delta,
            "contracts": self.contracts,
            "greeks": self.greeks,
            "pnl_curve": self.pnl_curve,
            "legs": self.legs,
        }


class StrategyTemplateService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_template(
        self,
        client_id: uuid.UUID,
        payload: StrategyTemplateCreateRequest,
    ) -> StrategyTemplate:
        if payload.dte_max < payload.dte_min:
            raise ValueError("dte_max must be greater than or equal to dte_min")
        template = StrategyTemplate(
            client_id=client_id,
            name=payload.name.strip(),
            strategy_type=payload.strategy_type,
            underlying_symbol=payload.underlying_symbol.strip().upper(),
            dte_min=payload.dte_min,
            dte_max=payload.dte_max,
            center_delta_target=payload.center_delta_target,
            wing_width=payload.wing_width,
            max_risk_per_trade=payload.max_risk_per_trade,
            sizing_method=payload.sizing_method,
            max_contracts=payload.max_contracts,
            hedge_enabled=payload.hedge_enabled,
            auto_execute=payload.auto_execute,
        )
        self.db.add(template)
        await self.db.commit()
        await self.db.refresh(template)
        await self._audit(client_id, "strategy_template_created", {"template_id": template.id, "name": template.name})
        return template

    async def list_templates(self, client_id: uuid.UUID, limit: int = 100) -> list[StrategyTemplate]:
        result = await self.db.execute(
            select(StrategyTemplate)
            .where(StrategyTemplate.client_id == client_id)
            .order_by(desc(StrategyTemplate.updated_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_template(self, client_id: uuid.UUID, template_id: int) -> StrategyTemplate:
        template = await self.db.get(StrategyTemplate, template_id)
        if template is None or template.client_id != client_id:
            raise ValueError("Strategy template not found")
        return template

    async def update_template(
        self,
        client_id: uuid.UUID,
        template_id: int,
        payload: StrategyTemplateUpdateRequest,
    ) -> StrategyTemplate:
        template = await self.get_template(client_id, template_id)
        if payload.dte_max < payload.dte_min:
            raise ValueError("dte_max must be greater than or equal to dte_min")
        template.name = payload.name.strip()
        template.strategy_type = payload.strategy_type
        template.underlying_symbol = payload.underlying_symbol.strip().upper()
        template.dte_min = payload.dte_min
        template.dte_max = payload.dte_max
        template.center_delta_target = payload.center_delta_target
        template.wing_width = payload.wing_width
        template.max_risk_per_trade = payload.max_risk_per_trade
        template.sizing_method = payload.sizing_method
        template.max_contracts = payload.max_contracts
        template.hedge_enabled = payload.hedge_enabled
        template.auto_execute = payload.auto_execute
        await self.db.commit()
        await self.db.refresh(template)
        await self._audit(client_id, "strategy_template_updated", {"template_id": template_id})
        return template

    async def delete_template(self, client_id: uuid.UUID, template_id: int) -> None:
        template = await self.get_template(client_id, template_id)
        await self.db.delete(template)
        await self.db.commit()
        await self._audit(client_id, "strategy_template_deleted", {"template_id": template_id})

    async def resolve_strategy_template(
        self,
        client_id: uuid.UUID,
        template_id: int,
        broker: BrokerBase,
    ) -> ResolvedStrategy:
        template = await self.get_template(client_id, template_id)
        chain = await broker.get_options_chain(template.underlying_symbol, None)
        if not chain:
            raise ValueError(f"No options chain data returned for {template.underlying_symbol}")

        valid_rows = [row for row in chain if row.get("expiry")]
        if not valid_rows:
            raise ValueError("No expiry data in options chain")

        selected_expiry, selected_dte = self._select_expiry(valid_rows, template.dte_min, template.dte_max)
        expiry_rows = [row for row in valid_rows if str(row.get("expiry")) == selected_expiry]
        if not expiry_rows:
            raise ValueError(f"No rows found for selected expiry {selected_expiry}")

        center = min(
            expiry_rows,
            key=lambda row: abs(abs(float(row.get("call_delta", 0.0))) - template.center_delta_target),
        )
        center_strike = float(center["strike"])

        strikes = sorted({float(row["strike"]) for row in expiry_rows if row.get("strike") is not None})
        upper_width = template.wing_width if template.strategy_type != "broken_wing_butterfly" else template.wing_width * 1.5
        lower_strike, upper_strike = self._select_wing_strikes(
            strikes=strikes,
            center_strike=center_strike,
            lower_width=template.wing_width,
            upper_width=upper_width,
        )

        lower_row = self._row_for_strike(expiry_rows, lower_strike)
        upper_row = self._row_for_strike(expiry_rows, upper_strike)
        if not lower_row or not upper_row:
            raise ValueError("Missing required wing contracts in options chain")

        if template.strategy_type == "iron_fly":
            needed = ("call_delta", "put_delta")
        else:
            needed = ("call_delta",)
        for row in (lower_row, center, upper_row):
            for greek_key in needed:
                if row.get(greek_key) is None:
                    raise ValueError("Greeks unavailable for selected contracts")

        pricing_ref = await broker.get_market_data(template.underlying_symbol)
        underlying = float(pricing_ref.get("underlying_price", 0.0))
        if underlying <= 0:
            underlying = center_strike

        lower_call_mid = self._extract_mid(lower_row, "call")
        center_call_mid = self._extract_mid(center, "call")
        upper_call_mid = self._extract_mid(upper_row, "call")
        lower_put_mid = self._extract_mid(lower_row, "put")
        center_put_mid = self._extract_mid(center, "put")

        if template.strategy_type == "iron_fly":
            # Credit structure: sell ATM straddle, buy wings.
            estimated_net_premium = (center_call_mid + center_put_mid) - (lower_put_mid + upper_call_mid)
        else:
            # Debit call butterfly structures.
            estimated_net_premium = (lower_call_mid + upper_call_mid) - (2.0 * center_call_mid)

        contract_multiplier = float(center.get("multiplier") or 50.0)
        if template.strategy_type == "iron_fly":
            max_width = max(center_strike - lower_strike, upper_strike - center_strike)
            max_loss_per_1 = max(max_width - max(estimated_net_premium, 0.0), 0.0) * contract_multiplier
        else:
            max_loss_per_1 = max((center_strike - lower_strike) - max(estimated_net_premium, 0.0), 0.0) * contract_multiplier
        contracts = 1
        if template.sizing_method == "risk_based":
            raw = int(template.max_risk_per_trade // max(max_loss_per_1, 1.0))
            contracts = max(1, raw)
        contracts = min(contracts, template.max_contracts)

        estimated_max_risk = max_loss_per_1 * contracts
        if estimated_max_risk > template.max_risk_per_trade:
            raise ValueError(
                f"Resolved structure risk {estimated_max_risk:.2f} exceeds max_risk_per_trade {template.max_risk_per_trade:.2f}"
            )

        if template.strategy_type == "iron_fly":
            net_delta_1 = (
                -float(center.get("call_delta", 0.0))
                - float(center.get("put_delta", 0.0))
                + float(lower_row.get("put_delta", 0.0))
                + float(upper_row.get("call_delta", 0.0))
            )
            net_gamma = (
                -float(center.get("gamma", 0.0))
                - float(center.get("gamma", 0.0))
                + float(lower_row.get("gamma", 0.0))
                + float(upper_row.get("gamma", 0.0))
            ) * contracts
            net_theta = (
                -float(center.get("theta", 0.0))
                - float(center.get("theta", 0.0))
                + float(lower_row.get("theta", 0.0))
                + float(upper_row.get("theta", 0.0))
            ) * contracts
            net_vega = (
                -float(center.get("vega", 0.0))
                - float(center.get("vega", 0.0))
                + float(lower_row.get("vega", 0.0))
                + float(upper_row.get("vega", 0.0))
            ) * contracts
            legs = [
                self._leg("BUY", 1, template, selected_expiry, lower_strike, lower_row, right="P"),
                self._leg("SELL", 1, template, selected_expiry, center_strike, center, right="P"),
                self._leg("SELL", 1, template, selected_expiry, center_strike, center, right="C"),
                self._leg("BUY", 1, template, selected_expiry, upper_strike, upper_row, right="C"),
            ]
        else:
            net_delta_1 = (
                float(lower_row.get("call_delta", 0.0))
                - (2.0 * float(center.get("call_delta", 0.0)))
                + float(upper_row.get("call_delta", 0.0))
            )
            net_gamma = (
                float(lower_row.get("gamma", 0.0))
                - (2.0 * float(center.get("gamma", 0.0)))
                + float(upper_row.get("gamma", 0.0))
            ) * contracts
            net_theta = (
                float(lower_row.get("theta", 0.0))
                - (2.0 * float(center.get("theta", 0.0)))
                + float(upper_row.get("theta", 0.0))
            ) * contracts
            net_vega = (
                float(lower_row.get("vega", 0.0))
                - (2.0 * float(center.get("vega", 0.0)))
                + float(upper_row.get("vega", 0.0))
            ) * contracts
            legs = [
                self._leg("BUY", 1, template, selected_expiry, lower_strike, lower_row, right="C"),
                self._leg("SELL", 2, template, selected_expiry, center_strike, center, right="C"),
                self._leg("BUY", 1, template, selected_expiry, upper_strike, upper_row, right="C"),
            ]
        net_delta = net_delta_1 * contracts

        curve = self._estimate_pnl_curve(
            underlying=underlying,
            lower=lower_strike,
            center=center_strike,
            upper=upper_strike,
            premium=estimated_net_premium,
            multiplier=contract_multiplier,
            contracts=contracts,
            strategy_type=template.strategy_type,
        )

        return ResolvedStrategy(
            template_id=template.id,
            strategy_type=template.strategy_type,
            expiry=selected_expiry,
            dte=selected_dte,
            center_strike=center_strike,
            estimated_net_premium=round(estimated_net_premium, 4),
            estimated_max_risk=round(estimated_max_risk, 2),
            estimated_net_delta=round(net_delta, 4),
            contracts=contracts,
            greeks={
                "delta": round(net_delta, 4),
                "gamma": round(net_gamma, 4),
                "theta": round(net_theta, 4),
                "vega": round(net_vega, 4),
            },
            pnl_curve=curve,
            legs=legs,
        )

    async def execute_strategy_template(
        self,
        client_id: uuid.UUID,
        template_id: int,
        broker: BrokerBase,
        emergency_halt: EmergencyHaltController | None = None,
    ) -> StrategyExecution:
        await self._enforce_execution_controls(client_id, emergency_halt)
        resolved = await self.resolve_strategy_template(client_id, template_id, broker)
        template = await self.get_template(client_id, template_id)
        client = await self.db.get(Client, client_id)
        if client is None:
            raise ValueError("Client not found")

        await self._enforce_risk(client, template, resolved.contracts)

        if not hasattr(broker, "submit_combo_order"):
            raise BrokerOrderError("Broker does not support combo BAG orders")
        submit_combo = getattr(broker, "submit_combo_order")
        combo_result = await submit_combo(
            symbol=template.underlying_symbol,
            legs=resolved.legs,
            qty=resolved.contracts,
            order_type="LMT",
            limit_price=resolved.estimated_net_premium,
            action="BUY",
        )

        execution = StrategyExecution(
            client_id=client_id,
            template_id=template_id,
            order_id=str(combo_result.get("order_id")) if combo_result.get("order_id") else None,
            status=str(combo_result.get("status", "submitted")),
            avg_fill_price=self._safe_float(combo_result.get("fill_price")),
            payload=resolved.to_payload(),
            execution_timestamp=datetime.now(UTC),
        )
        self.db.add(execution)
        execution_pnl = self._safe_float(combo_result.get("realized_pnl", combo_result.get("pnl", 0.0)))

        trade = Trade(
            client_id=client_id,
            action="BUY",
            symbol=template.underlying_symbol,
            instrument="BAG",
            qty=resolved.contracts,
            fill_price=execution.avg_fill_price,
            order_id=execution.order_id,
            agent_reasoning=f"Strategy template execution: {template.name}",
            mode=client.mode,
            status=execution.status,
            pnl=execution_pnl,
        )
        self.db.add(trade)
        await self.db.flush()

        expected_price = estimate_expected_price(
            trade.action,
            bid=0.0,
            ask=0.0,
            limit_price=resolved.estimated_net_premium,
            fallback_price=combo_result.get("expected_price"),
        )
        fill = build_trade_fill_from_order(
            client_id=client_id,
            trade_id=trade.id,
            order_id=trade.order_id,
            action=trade.action,
            qty=trade.qty,
            order_payload=combo_result,
            expected_price=expected_price,
        )
        if fill is not None:
            self.db.add(fill)

        await self.db.commit()
        await self.db.refresh(execution)

        await self._audit(
            client_id,
            "strategy_template_executed",
            {
                "template_id": template_id,
                "execution_id": execution.id,
                "order_id": execution.order_id,
                "status": execution.status,
            },
        )
        return execution

    async def _enforce_risk(
        self,
        client: Client,
        template: StrategyTemplate,
        resolved_contracts: int,
    ) -> None:
        if not RiskGovernor._is_market_hours(datetime.now(UTC).time()):
            raise ValueError("Order attempted outside configured market hours")

        risk_params = client.risk_params or {}
        max_daily_loss = float(risk_params.get("max_loss", 5000))
        max_open_positions = int(risk_params.get("max_open_positions", 20))
        max_size = int(risk_params.get("max_size", 10))

        start_utc = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        trades_result = await self.db.execute(
            select(Trade)
            .where(Trade.client_id == client.id, Trade.timestamp >= start_utc)
            .order_by(desc(Trade.timestamp))
            .limit(500)
        )
        day_trades = list(trades_result.scalars().all())
        day_pnl = sum(float(t.pnl) for t in day_trades)
        if day_pnl <= -abs(max_daily_loss):
            raise ValueError(f"Daily loss limit breached: {day_pnl:.2f} <= -{max_daily_loss:.2f}")
        consecutive_losses = [float(t.pnl) for t in day_trades[:3]]
        if len(consecutive_losses) >= 3 and all(loss <= -500 for loss in consecutive_losses):
            raise ValueError("Circuit breaker active: 3 consecutive losses > $500")

        pos_result = await self.db.execute(select(Position).where(Position.client_id == client.id))
        open_legs = len(list(pos_result.scalars().all()))
        if open_legs >= max_open_positions:
            raise ValueError(f"Max open positions reached: {open_legs}/{max_open_positions}")

        if resolved_contracts > template.max_contracts:
            raise ValueError(f"Resolved contracts {resolved_contracts} exceed template max {template.max_contracts}")
        if resolved_contracts > max_size:
            raise ValueError(f"Resolved contracts {resolved_contracts} exceed client max_size {max_size}")

    async def _enforce_execution_controls(
        self,
        client_id: uuid.UUID,
        emergency_halt: EmergencyHaltController | None,
    ) -> None:
        if emergency_halt is None:
            return
        state = await emergency_halt.get()
        if not state.halted:
            return
        await self._audit(
            client_id,
            "emergency_halt_blocked",
            {"reason": state.reason, "operation": "strategy_template_execute"},
        )
        raise ValueError("Trading is globally halted by emergency control")

    async def _audit(self, client_id: uuid.UUID, event_type: str, details: dict[str, Any]) -> None:
        self.db.add(AuditLog(client_id=client_id, event_type=event_type, details=details))
        await self.db.commit()

    @staticmethod
    def _row_for_strike(rows: list[dict[str, Any]], strike: float) -> dict[str, Any] | None:
        for row in rows:
            if float(row.get("strike", 0.0)) == strike:
                return row
        return None

    @staticmethod
    def _nearest_strike(strikes: list[float], target: float) -> float:
        return min(strikes, key=lambda x: abs(x - target))

    @staticmethod
    def _select_wing_strikes(
        strikes: list[float],
        center_strike: float,
        lower_width: float,
        upper_width: float,
    ) -> tuple[float, float]:
        lower_candidates = [strike for strike in strikes if strike < center_strike]
        upper_candidates = [strike for strike in strikes if strike > center_strike]
        if not lower_candidates or not upper_candidates:
            low = min(strikes) if strikes else center_strike
            high = max(strikes) if strikes else center_strike
            raise ValueError(
                "Unable to construct butterfly wings from current chain. "
                f"Need strikes both below and above center {center_strike}, available range is {low}-{high}."
            )

        lower_target = center_strike - max(lower_width, 0.0)
        upper_target = center_strike + max(upper_width, 0.0)
        lower_strike = min(lower_candidates, key=lambda x: abs(x - lower_target))
        upper_strike = min(upper_candidates, key=lambda x: abs(x - upper_target))
        return lower_strike, upper_strike

    @staticmethod
    def _select_expiry(chain_rows: list[dict[str, Any]], dte_min: int, dte_max: int) -> tuple[str, int]:
        expiry_map: dict[str, int] = {}
        now = datetime.now(UTC).date()
        for row in chain_rows:
            exp = str(row["expiry"]).strip()
            if exp in expiry_map:
                continue
            exp_date = StrategyTemplateService._parse_expiry_date(exp)
            if exp_date is None:
                continue
            dte = (exp_date - now).days
            expiry_map[exp] = dte
        if not expiry_map:
            raise ValueError("No parseable expiry values in options chain")
        allowed = [(exp, dte) for exp, dte in expiry_map.items() if dte_min <= dte <= dte_max]
        if not allowed:
            available = ", ".join(
                [f"{exp} ({dte}d)" for exp, dte in sorted(expiry_map.items(), key=lambda item: item[1])[:8]]
            )
            raise ValueError(
                f"No expiry matched configured DTE range {dte_min}-{dte_max}. Available expiries: {available}"
            )
        midpoint = (dte_min + dte_max) / 2
        return min(allowed, key=lambda item: abs(item[1] - midpoint))

    @staticmethod
    def _parse_expiry_date(raw_expiry: str) -> date | None:
        raw = raw_expiry.strip()
        if not raw:
            return None

        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                continue

        eight_digit = re.search(r"(\d{8})", raw)
        if eight_digit:
            try:
                return datetime.strptime(eight_digit.group(1), "%Y%m%d").date()
            except ValueError:
                pass

        six_digit = re.search(r"(\d{6})", raw)
        if six_digit:
            token = six_digit.group(1)
            year = int(token[:4])
            month = int(token[4:6])
            if 1 <= month <= 12:
                last_day = calendar.monthrange(year, month)[1]
                return date(year, month, last_day)

        return None

    @staticmethod
    def _extract_mid(row: dict[str, Any], side: str) -> float:
        bid = StrategyTemplateService._safe_float(row.get(f"{side}_bid"))
        ask = StrategyTemplateService._safe_float(row.get(f"{side}_ask"))
        mid = StrategyTemplateService._safe_float(row.get(f"{side}_mid"))
        if mid > 0:
            return mid
        if bid > 0 and ask > 0:
            return (bid + ask) / 2
        return 0.0

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            if value is None:
                return 0.0
            return float(value)
        except Exception:  # noqa: BLE001
            return 0.0

    @staticmethod
    def _leg(
        action: str,
        ratio: int,
        template: StrategyTemplate,
        expiry: str,
        strike: float,
        row: dict[str, Any],
        right: str,
    ) -> dict[str, Any]:
        side = "put" if right.upper() == "P" else "call"
        return {
            "action": action,
            "ratio": ratio,
            "symbol": template.underlying_symbol,
            "instrument": "FOP",
            "expiry": expiry,
            "strike": strike,
            "right": right.upper(),
            "exchange": row.get("exchange", "CME"),
            "trading_class": row.get("trading_class"),
            "multiplier": str(row.get("multiplier")) if row.get("multiplier") else None,
            "delta": StrategyTemplateService._safe_float(row.get(f"{side}_delta")),
            "mid_price": StrategyTemplateService._extract_mid(row, side),
        }

    @staticmethod
    def _estimate_pnl_curve(
        underlying: float,
        lower: float,
        center: float,
        upper: float,
        premium: float,
        multiplier: float,
        contracts: int,
        strategy_type: str,
    ) -> list[dict[str, float]]:
        points = [0.9, 0.95, 1.0, 1.05, 1.1]
        out: list[dict[str, float]] = []
        for factor in points:
            s = underlying * factor
            if strategy_type == "iron_fly":
                # Short straddle + long wings.
                payoff = (
                    max(lower - s, 0.0)
                    - max(center - s, 0.0)
                    - max(s - center, 0.0)
                    + max(s - upper, 0.0)
                )
                pnl = (premium + payoff) * multiplier * contracts
            else:
                payoff = max(s - lower, 0.0) - 2.0 * max(s - center, 0.0) + max(s - upper, 0.0)
                pnl = (payoff - premium) * multiplier * contracts
            out.append({"underlying": round(s, 2), "pnl": round(pnl, 2)})
        return out
