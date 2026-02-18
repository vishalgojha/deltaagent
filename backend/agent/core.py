import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Any

import httpx
from redis.asyncio import Redis
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent.memory import AgentMemoryStore
from backend.agent.prompts import AUTONOMOUS_PROMPT, CONFIRMATION_PROMPT
from backend.agent.risk import RiskGovernor, RiskParameters, RiskViolation
from backend.agent.strategy_registry import StrategyRegistry
from backend.agent.tools import AgentTools
from backend.brokers.base import BrokerBase
from backend.config import get_settings
from backend.db.models import AgentMemory, AuditLog, Client, Instrument, Proposal, StrategyProfile, Trade
from backend.safety.emergency_halt import EmergencyHaltController
from backend.strategies.delta_neutral import detect_rebalance_need


logger = logging.getLogger(__name__)


class TradingAgent:
    def __init__(
        self,
        broker: BrokerBase,
        db: AsyncSession,
        memory_store: AgentMemoryStore,
        risk_governor: RiskGovernor,
        emergency_halt: EmergencyHaltController | None = None,
        redis_client: Redis | None = None,
    ) -> None:
        self.broker = broker
        self.db = db
        self.memory_store = memory_store
        self.risk_governor = risk_governor
        self.emergency_halt = emergency_halt
        self.redis_client = redis_client
        self.tools = AgentTools(broker=broker, db=db)
        self.settings = get_settings()
        self.strategy_registry = StrategyRegistry()

    async def chat(self, client_id: uuid.UUID, message: str) -> dict[str, Any]:
        context = self.memory_store.get_or_create(client_id)
        if context.mode == "autonomous" and not self.settings.autonomous_enabled:
            metadata = self._empty_tool_metadata()
            await self._audit(
                client_id,
                "autonomous_blocked",
                {"reason": "AUTONOMOUS_ENABLED=false", "message": message},
            )
            return {
                "mode": context.mode,
                "message": "Autonomous mode is globally disabled by system policy.",
                "executed": False,
                **metadata,
            }
        context.message_history.append({"role": "user", "content": message})
        await self._save_memory(client_id, "user", message)

        portfolio = await self.tools.get_portfolio_greeks()
        context.positions = portfolio["positions"]
        context.net_greeks = portfolio["net_greeks"]
        await self._cache_portfolio_state(client_id, portfolio)
        mode = context.mode
        params = RiskParameters.from_dict(context.parameters)

        llm_decision = await self._decide(mode=mode, message=message, context=context, params=params)
        reasoning = llm_decision["reasoning"]
        proposed_trade = llm_decision.get("trade")
        tool_metadata = {
            "tool_trace_id": llm_decision.get("tool_trace_id", str(uuid.uuid4())),
            "planned_tools": llm_decision.get("planned_tools", []),
            "tool_calls": llm_decision.get("tool_calls", []),
            "tool_results": llm_decision.get("tool_results", []),
        }

        if mode == "confirmation":
            if proposed_trade:
                proposal = await self._create_proposal(client_id, proposed_trade, reasoning)
                context.last_action = f"proposal:{proposal.id}"
                await self._audit(client_id, "agent_proposal_created", {"proposal_id": proposal.id, "reasoning": reasoning})
                response = {
                    "mode": mode,
                    "message": reasoning,
                    "proposal_id": proposal.id,
                    "proposal": proposal.trade_payload,
                    **tool_metadata,
                }
            else:
                await self._audit(client_id, "agent_decision_no_trade", {"reasoning": reasoning})
                response = {"mode": mode, "message": reasoning, "executed": False, **tool_metadata}
        else:
            if not proposed_trade:
                await self._audit(client_id, "agent_decision_no_trade", {"reasoning": reasoning})
                response = {"mode": mode, "message": reasoning, "executed": False, **tool_metadata}
            else:
                execution = await self._execute_trade(client_id, proposed_trade, reasoning, params)
                context.last_action = f"trade:{execution.get('trade_id')}"
                response = {"mode": mode, "message": reasoning, "execution": execution, "executed": True, **tool_metadata}

        context.message_history.append({"role": "assistant", "content": response["message"]})
        self.memory_store.update(context)
        await self._save_memory(client_id, "assistant", response["message"])
        await self._publish_stream_event(
            client_id,
            "agent_message",
            {"role": "assistant", "content": response["message"], "mode": mode},
        )
        return response

    async def approve_proposal(self, client_id: uuid.UUID, proposal_id: int) -> dict[str, Any]:
        proposal = await self.db.get(Proposal, proposal_id)
        if not proposal or proposal.client_id != client_id:
            raise ValueError("Proposal not found")
        if proposal.status != "pending":
            raise ValueError("Proposal already resolved")

        client = await self.db.get(Client, client_id)
        params = RiskParameters.from_dict(client.risk_params if client else {})
        execution = await self._execute_trade(client_id, proposal.trade_payload, proposal.agent_reasoning, params)
        proposal.status = "approved"
        proposal.resolved_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self._audit(client_id, "proposal_approved", {"proposal_id": proposal_id, "execution": execution})
        return execution

    async def reject_proposal(self, client_id: uuid.UUID, proposal_id: int) -> dict[str, Any]:
        proposal = await self.db.get(Proposal, proposal_id)
        if not proposal or proposal.client_id != client_id:
            raise ValueError("Proposal not found")
        proposal.status = "rejected"
        proposal.resolved_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self._audit(client_id, "proposal_rejected", {"proposal_id": proposal_id})
        return {"proposal_id": proposal_id, "status": "rejected"}

    async def status(self, client_id: uuid.UUID) -> dict[str, Any]:
        context = self.memory_store.get_or_create(client_id)
        payload = {
            "client_id": client_id,
            "mode": context.mode,
            "last_action": context.last_action,
            "healthy": context.healthy,
            "net_greeks": context.net_greeks,
        }
        await self._publish_stream_event(client_id, "agent_status", payload)
        return payload

    async def set_mode(self, client_id: uuid.UUID, mode: str) -> None:
        if mode == "autonomous" and not self.settings.autonomous_enabled:
            await self._audit(
                client_id,
                "autonomous_blocked",
                {"reason": "AUTONOMOUS_ENABLED=false", "requested_mode": mode},
            )
            raise ValueError("Autonomous mode is globally disabled")
        context = self.memory_store.get_or_create(client_id)
        context.mode = mode
        self.memory_store.update(context)
        client = await self.db.get(Client, client_id)
        if client:
            client.mode = mode
            await self.db.commit()
        await self._audit(client_id, "mode_changed", {"mode": mode})
        await self._publish_stream_event(client_id, "mode_changed", {"mode": mode})

    async def set_parameters(self, client_id: uuid.UUID, params: dict[str, Any]) -> None:
        context = self.memory_store.get_or_create(client_id)
        merged_params = dict(context.parameters or {})
        merged_params.update(params or {})
        context.parameters = merged_params
        self.memory_store.update(context)
        client = await self.db.get(Client, client_id)
        if client:
            stored = dict(client.risk_params or {})
            stored.update(params or {})
            client.risk_params = stored
            await self.db.commit()
        await self._audit(client_id, "risk_params_updated", {"risk_params": merged_params})
        await self._publish_stream_event(client_id, "risk_params_updated", {"risk_params": merged_params})

    async def _execute_trade(
        self,
        client_id: uuid.UUID,
        trade_payload: dict[str, Any],
        reasoning: str,
        params: RiskParameters,
    ) -> dict[str, Any]:
        if self.emergency_halt is not None:
            state = await self.emergency_halt.get()
            if state.halted:
                await self._audit(
                    client_id,
                    "emergency_halt_blocked",
                    {"reason": state.reason, "order": trade_payload},
                )
                raise ValueError("Trading is globally halted by emergency control")
        portfolio = await self.tools.get_portfolio_greeks()
        await self._cache_portfolio_state(client_id, portfolio)
        strategy = None
        strategy_id = str(trade_payload.get("strategy_id") or "delta_rebalance_single")
        profile_row = await self.db.execute(
            select(StrategyProfile).where(StrategyProfile.strategy_id == strategy_id, StrategyProfile.is_active.is_(True))
        )
        profile = profile_row.scalar_one_or_none()
        client = await self.db.get(Client, client_id)
        market = await self.tools.get_market_data(trade_payload["symbol"])
        net_delta = float(portfolio["net_greeks"]["delta"])
        order_delta_est = float(trade_payload.get("delta_estimate", 0.5))
        direction = 1 if trade_payload["action"].upper() == "BUY" else -1
        projected_delta = net_delta + direction * int(trade_payload["qty"]) * order_delta_est
        recent = await self._recent_trades(client_id, 30)
        daily_pnl = sum(t.pnl for t in recent)
        open_legs = sum(abs(int(p.get("qty", 0))) for p in portfolio["positions"])
        try:
            if profile is not None:
                strategy = self.strategy_registry.validate_trade_payload_with_profile(
                    trade_payload,
                    {
                        "strategy_id": profile.strategy_id,
                        "name": profile.name,
                        "allowed_symbols": profile.allowed_symbols,
                        "allowed_asset_classes": profile.allowed_asset_classes,
                        "max_legs": profile.max_legs,
                        "require_defined_risk": profile.require_defined_risk,
                        "tier_allowlist": profile.tier_allowlist,
                    },
                    client_tier=client.tier if client else None,
                )
            else:
                strategy = self.strategy_registry.validate_trade_payload(trade_payload)
            self.risk_governor.validate_order(
                client_id=str(client_id),
                order=trade_payload,
                net_delta=net_delta,
                projected_delta=projected_delta,
                daily_pnl=daily_pnl,
                open_legs=open_legs,
                bid=market.get("bid", 0),
                ask=market.get("ask", 0),
                params=params,
            )
        except RiskViolation as exc:
            await self._audit(
                client_id,
                "risk_violation",
                {"reason": exc.reason, "order": trade_payload},
                risk_rule=exc.rule,
            )
            raise

        order = await self.tools.submit_order(
            action=trade_payload["action"],
            symbol=trade_payload["symbol"],
            instrument=trade_payload.get("instrument", "FOP"),
            qty=int(trade_payload["qty"]),
            order_type=trade_payload.get("order_type", "MKT"),
            limit_price=trade_payload.get("limit_price"),
            strike=trade_payload.get("strike"),
            expiry=trade_payload.get("expiry"),
        )
        trade = Trade(
            client_id=client_id,
            action=trade_payload["action"],
            symbol=trade_payload["symbol"],
            instrument=trade_payload.get("instrument", "FOP"),
            qty=int(trade_payload["qty"]),
            fill_price=order.get("fill_price"),
            order_id=order["order_id"],
            agent_reasoning=reasoning,
            mode=self.memory_store.get_or_create(client_id).mode,
            status=order.get("status", "submitted"),
            pnl=0.0,
        )
        self.db.add(trade)
        await self.db.commit()
        await self.db.refresh(trade)
        assert strategy is not None
        await self._audit(
            client_id,
            "order_executed",
            {
                "trade_id": trade.id,
                "order": order,
                "reasoning": reasoning,
                "strategy_id": strategy.strategy_id,
            },
        )
        await self._publish_stream_event(
            client_id,
            "order_executed",
            {"trade_id": trade.id, "order_id": order["order_id"], "status": order.get("status", "submitted")},
        )
        return {"trade_id": trade.id, "order": order}

    async def _decide(
        self,
        mode: str,
        message: str,
        context: Any,
        params: RiskParameters,
    ) -> dict[str, Any]:
        delta_query = await self._build_market_delta_query_response(message)
        if delta_query is not None:
            return delta_query

        rebalance = detect_rebalance_need(context.positions, params.delta_threshold)
        default_trade = None
        if rebalance["needs_rebalance"]:
            action = "SELL" if rebalance["net_delta"] > 0 else "BUY"
            default_trade = {
                "action": action,
                "symbol": "ES",
                "instrument": "FOP",
                "qty": 1,
                "order_type": "MKT",
                "limit_price": None,
                "strategy_id": "delta_rebalance_single",
            }
        default_reasoning = (
            f"Detected net delta {rebalance['net_delta']:.4f}, threshold {params.delta_threshold:.4f}. "
            f"{'Proposing hedge.' if default_trade else 'No trade needed.'}"
        )

        llm = await self._call_llm(mode, message, context, default_reasoning, default_trade)
        return llm

    async def _build_market_delta_query_response(self, message: str) -> dict[str, Any] | None:
        request = await self._parse_delta_query(message)
        if request is None:
            return None

        symbol = str(request["symbol"])
        target_delta = float(request["target_delta"])
        expiry_hint = request.get("expiry_hint")

        try:
            chain = await self.tools.get_options_chain(symbol=symbol, expiry=expiry_hint)
            if not chain and expiry_hint:
                chain = await self.tools.get_options_chain(symbol=symbol, expiry=None)
            market_data = await self.tools.get_market_data(symbol)
        except Exception as exc:  # noqa: BLE001
            return {
                "reasoning": f"Could not fetch {symbol} option data right now: {exc}",
                "trade": None,
                **self._empty_tool_metadata(),
            }
        if not chain:
            return {
                "reasoning": f"No options chain data returned for {symbol}.",
                "trade": None,
                **self._empty_tool_metadata(),
            }
        has_signal = any(
            (
                abs(float(row.get("call_delta", 0.0))) > 0.01
                or abs(float(row.get("put_delta", 0.0))) > 0.01
                or self._safe_float(row.get("call_mid")) > 0
                or self._safe_float(row.get("put_mid")) > 0
                or self._safe_float(row.get("call_last")) > 0
                or self._safe_float(row.get("put_last")) > 0
            )
            for row in chain
        )
        if not has_signal:
            return {
                "reasoning": (
                    f"{symbol} chain returned but Greeks/quotes are unavailable. "
                    "Check IBKR futures-options market data permissions and live quote subscription."
                ),
                "trade": None,
                **self._empty_tool_metadata(),
            }

        primary_call = min(chain, key=lambda row: abs(float(row.get("call_delta", 0.0)) - target_delta))
        primary_put = min(chain, key=lambda row: abs(float(row.get("put_delta", 0.0)) + target_delta))

        call_price = self._format_option_price(primary_call, side="call")
        put_price = self._format_option_price(primary_put, side="put")
        underlying = float(market_data.get("underlying_price", 0.0))
        chosen_expiry = primary_call.get("expiry") or primary_put.get("expiry") or "n/a"

        primary_sell_lots = int(request.get("primary_sell_lots", 1))
        secondary_buy_lots = int(request.get("secondary_buy_lots", 0))
        secondary_delta = float(request.get("secondary_delta", 0.30))
        secondary_side = str(request.get("secondary_side", "call"))

        lines = [
            f"{symbol} underlying {underlying:.2f}, expiry {chosen_expiry}.",
            f"Nearest +{target_delta:.2f} call: strike {primary_call.get('strike')} (delta {float(primary_call.get('call_delta', 0.0)):.3f}, price {call_price}).",
            f"Nearest -{target_delta:.2f} put: strike {primary_put.get('strike')} (delta {float(primary_put.get('put_delta', 0.0)):.3f}, price {put_price}).",
        ]
        if primary_sell_lots > 0:
            lines.append(
                f"Plan (not executed): SELL {primary_sell_lots} lots each of call {primary_call.get('strike')} and put {primary_put.get('strike')}."
            )
        if secondary_buy_lots > 0:
            if secondary_side == "put":
                secondary_row = min(chain, key=lambda row: abs(abs(float(row.get("put_delta", 0.0))) - secondary_delta))
                secondary_delta_value = float(secondary_row.get("put_delta", 0.0))
                secondary_price = self._format_option_price(secondary_row, side="put")
            else:
                secondary_row = min(chain, key=lambda row: abs(abs(float(row.get("call_delta", 0.0))) - secondary_delta))
                secondary_delta_value = float(secondary_row.get("call_delta", 0.0))
                secondary_price = self._format_option_price(secondary_row, side="call")
            lines.append(
                f"Plan (not executed): BUY {secondary_buy_lots} lots of {secondary_side.upper()} near |delta| {secondary_delta:.2f} -> strike {secondary_row.get('strike')} (delta {secondary_delta_value:.3f}, price {secondary_price})."
            )

        return {"reasoning": " ".join(lines), "trade": None, **self._empty_tool_metadata()}

    async def _parse_delta_query(self, message: str) -> dict[str, Any] | None:
        text = message.lower()
        if "delta" not in text:
            return None
        if not any(key in text for key in ("up", "down", "call", "put")):
            return None

        symbol = await self._resolve_symbol_from_catalog(text)
        if symbol is None:
            return None

        match = re.search(r"delta\s*([0-9]*\.?[0-9]+)", text)
        if not match:
            value = 0.50
        else:
            try:
                value = abs(float(match.group(1)))
            except ValueError:
                value = 0.50
        if value > 1.0:
            value = value / 100.0
        value = min(max(value, 0.05), 0.95)

        days_match = re.search(r"(\d+)\s*days?\s*(?:from\s*now|out)?", text)
        expiry_hint = None
        if days_match:
            days_out = int(days_match.group(1))
            expiry_hint = (datetime.now(timezone.utc).date() + timedelta(days=days_out)).strftime("%Y%m%d")

        sell_match = re.search(r"sell\s+(\d+)\s+lots?", text)
        buy_match = re.search(r"buy\s+(\d+)\s+lots?", text)
        secondary_delta_match = re.search(r"buy\s+\d+\s+lots?.*?delta\s*([0-9]*\.?[0-9]+)", text)
        primary_sell_lots = int(sell_match.group(1)) if sell_match else 1
        secondary_buy_lots = 0
        secondary_delta = 0.30
        if buy_match and secondary_delta_match:
            secondary_buy_lots = int(buy_match.group(1))
            try:
                secondary_delta = abs(float(secondary_delta_match.group(1)))
            except ValueError:
                secondary_delta = 0.30
            if secondary_delta > 1.0:
                secondary_delta = secondary_delta / 100.0
            secondary_delta = min(max(secondary_delta, 0.05), 0.95)
        secondary_side = "put" if ("buy" in text and "put" in text) else "call"

        return {
            "symbol": symbol,
            "target_delta": value,
            "expiry_hint": expiry_hint,
            "primary_sell_lots": primary_sell_lots,
            "secondary_buy_lots": secondary_buy_lots,
            "secondary_delta": secondary_delta,
            "secondary_side": secondary_side,
        }

    async def _resolve_symbol_from_catalog(self, lower_message: str) -> str | None:
        rows = await self.db.execute(
            select(Instrument.symbol, Instrument.aliases).where(Instrument.is_active.is_(True))
        )
        scored: list[tuple[int, str]] = []
        for symbol, aliases in rows.all():
            symbol_norm = str(symbol).upper()
            if self._contains_term(lower_message, symbol_norm.lower()):
                scored.append((len(symbol_norm), symbol_norm))
            if isinstance(aliases, list):
                for alias in aliases:
                    alias_norm = str(alias).strip().lower()
                    if alias_norm and self._contains_term(lower_message, alias_norm):
                        scored.append((len(alias_norm), symbol_norm))

        if scored:
            scored.sort(reverse=True)
            return scored[0][1]

        # Fallback when catalog is not seeded yet: only explicit symbol mentions.
        for explicit in ("ES", "NQ", "SI", "GC", "CL", "RTY", "YM"):
            if self._contains_term(lower_message, explicit.lower()):
                return explicit
        return None

    @staticmethod
    def _contains_term(text: str, term: str) -> bool:
        if not term:
            return False
        if re.search(r"[^a-z0-9]", term):
            return term in text
        return re.search(rf"\b{re.escape(term)}\b", text) is not None

    def _format_option_price(self, row: dict[str, Any], side: str) -> str:
        side_prefix = "call" if side == "call" else "put"
        bid = self._safe_float(row.get(f"{side_prefix}_bid"))
        ask = self._safe_float(row.get(f"{side_prefix}_ask"))
        mid = self._safe_float(row.get(f"{side_prefix}_mid"))
        last = self._safe_float(row.get(f"{side_prefix}_last"))
        if mid > 0:
            return f"{mid:.2f} mid"
        if bid > 0 and ask > 0:
            return f"{((bid + ask) / 2):.2f} est"
        if last > 0:
            return f"{last:.2f} last"
        return "n/a"

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            if value is None:
                return 0.0
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    async def _call_llm(
        self,
        mode: str,
        message: str,
        context: Any,
        fallback_reasoning: str,
        fallback_trade: dict[str, Any] | None,
    ) -> dict[str, Any]:
        tool_trace_id = str(uuid.uuid4())
        planned_tools: list[dict[str, Any]] = []
        tool_calls: list[dict[str, Any]] = []
        tool_results: list[dict[str, Any]] = []

        backend_choice = self._resolve_decision_backend(context.parameters)
        if backend_choice == "deterministic":
            return {
                "reasoning": fallback_reasoning,
                "trade": fallback_trade,
                "tool_trace_id": tool_trace_id,
                "planned_tools": planned_tools,
                "tool_calls": tool_calls,
                "tool_results": tool_results,
            }

        if backend_choice == "ollama":
            ollama_response = await self._call_ollama(
                mode=mode,
                message=message,
                context=context,
                fallback_reasoning=fallback_reasoning,
                fallback_trade=fallback_trade,
                tool_trace_id=tool_trace_id,
            )
            if ollama_response is not None:
                return ollama_response

        if not self.settings.anthropic_api_key:
            return {
                "reasoning": fallback_reasoning,
                "trade": fallback_trade,
                "tool_trace_id": tool_trace_id,
                "planned_tools": planned_tools,
                "tool_calls": tool_calls,
                "tool_results": tool_results,
            }
        try:
            from anthropic import AsyncAnthropic  # type: ignore

            client = AsyncAnthropic(api_key=self.settings.anthropic_api_key)
            prompt = CONFIRMATION_PROMPT if mode == "confirmation" else AUTONOMOUS_PROMPT
            messages: list[dict[str, Any]] = [
                {
                    "role": "user",
                    "content": (
                        f"{prompt}\n\n"
                        f"User message: {message}\n"
                        f"Client mode: {mode}\n"
                        f"Context net greeks: {json.dumps(context.net_greeks)}\n"
                        "Use tools when needed. Return compact JSON with keys reasoning and optional trade."
                    ),
                }
            ]
            tools = self._tool_definitions()
            for _ in range(3):
                response = await client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=700,
                    messages=messages,
                    tools=tools,
                )
                tool_uses = [part for part in response.content if getattr(part, "type", "") == "tool_use"]
                text_chunks = [part.text for part in response.content if getattr(part, "type", "") == "text"]
                if not tool_uses:
                    text = "\n".join(text_chunks).strip()
                    parsed = json.loads(text) if text.startswith("{") else {}
                    parsed_trade = parsed.get("trade") if "trade" in parsed else fallback_trade
                    if parsed_trade is None and fallback_trade is not None:
                        parsed_trade = fallback_trade
                    return {
                        "reasoning": parsed.get("reasoning", fallback_reasoning),
                        "trade": parsed_trade,
                        "tool_trace_id": tool_trace_id,
                        "planned_tools": planned_tools,
                        "tool_calls": tool_calls,
                        "tool_results": tool_results,
                    }

                messages.append({"role": "assistant", "content": response.content})
                llm_tool_results = []
                for tool_use in tool_uses:
                    name = tool_use.name
                    tool_input = tool_use.input
                    started_at = datetime.now(timezone.utc)
                    started_tick = perf_counter()
                    planned_tools.append({"name": name, "input": tool_input})
                    if mode == "confirmation" and name == "submit_order":
                        result = {"error": "submit_order blocked in confirmation mode"}
                    else:
                        try:
                            result = await self._run_tool(context.client_id, name, tool_input)
                        except Exception as exc:  # noqa: BLE001
                            result = {"error": str(exc)}
                    completed_at = datetime.now(timezone.utc)
                    duration_ms = int((perf_counter() - started_tick) * 1000)
                    output_payload = result if isinstance(result, dict) else {"value": result}
                    success = not (isinstance(output_payload.get("error"), str) and output_payload.get("error"))

                    tool_calls.append(
                        {
                            "tool_use_id": tool_use.id,
                            "name": name,
                            "input": tool_input,
                            "started_at": started_at,
                            "completed_at": completed_at,
                            "duration_ms": duration_ms,
                        }
                    )
                    tool_results.append(
                        {
                            "tool_use_id": tool_use.id,
                            "name": name,
                            "output": output_payload,
                            "success": success,
                            "error": output_payload.get("error") if not success else None,
                            "started_at": started_at,
                            "completed_at": completed_at,
                            "duration_ms": duration_ms,
                        }
                    )
                    llm_tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use.id,
                            "content": json.dumps(output_payload, default=str),
                        }
                    )
                messages.append({"role": "user", "content": llm_tool_results})
            return {
                "reasoning": fallback_reasoning,
                "trade": fallback_trade,
                "tool_trace_id": tool_trace_id,
                "planned_tools": planned_tools,
                "tool_calls": tool_calls,
                "tool_results": tool_results,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM call failed, using fallback", extra={"error": str(exc)})
            return {
                "reasoning": fallback_reasoning,
                "trade": fallback_trade,
                "tool_trace_id": tool_trace_id,
                "planned_tools": planned_tools,
                "tool_calls": tool_calls,
                "tool_results": tool_results,
            }

    def _resolve_decision_backend(self, parameters: dict[str, Any] | None) -> str:
        chosen = str((parameters or {}).get("decision_backend", self.settings.decision_backend_default)).strip().lower()
        if chosen in {"deterministic", "ollama", "anthropic"}:
            return chosen
        return self.settings.decision_backend_default

    async def _call_ollama(
        self,
        mode: str,
        message: str,
        context: Any,
        fallback_reasoning: str,
        fallback_trade: dict[str, Any] | None,
        tool_trace_id: str,
    ) -> dict[str, Any] | None:
        prompt = CONFIRMATION_PROMPT if mode == "confirmation" else AUTONOMOUS_PROMPT
        system = (
            f"{prompt}\n\n"
            "Respond with strict JSON only with keys: reasoning (string), trade (object|null).\n"
            "If no trade, set trade to null."
        )
        user = (
            f"User message: {message}\n"
            f"Client mode: {mode}\n"
            f"Context net greeks: {json.dumps(context.net_greeks)}"
        )
        body = {
            "model": self.settings.ollama_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "format": "json",
        }
        try:
            timeout = httpx.Timeout(25.0, connect=3.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                res = await client.post(f"{self.settings.ollama_base_url}/api/chat", json=body)
                res.raise_for_status()
                payload = res.json()
            content = (
                payload.get("message", {}).get("content")
                if isinstance(payload, dict)
                else None
            )
            if not isinstance(content, str) or not content.strip():
                return None
            parsed = json.loads(content)
            parsed_trade = parsed.get("trade") if "trade" in parsed else fallback_trade
            if parsed_trade is None and fallback_trade is not None:
                parsed_trade = fallback_trade
            return {
                "reasoning": parsed.get("reasoning", fallback_reasoning),
                "trade": parsed_trade,
                "tool_trace_id": tool_trace_id,
                "planned_tools": [],
                "tool_calls": [],
                "tool_results": [],
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ollama call failed, falling back", extra={"error": str(exc)})
            return None

    def _empty_tool_metadata(self) -> dict[str, Any]:
        return {
            "tool_trace_id": str(uuid.uuid4()),
            "planned_tools": [],
            "tool_calls": [],
            "tool_results": [],
        }

    def _tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "get_portfolio_greeks",
                "description": "Return net portfolio greeks and position list",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "get_options_chain",
                "description": "Fetch options chain with greeks",
                "input_schema": {
                    "type": "object",
                    "properties": {"symbol": {"type": "string"}, "expiry": {"type": "string"}},
                    "required": ["symbol"],
                },
            },
            {
                "name": "submit_order",
                "description": "Submit broker order",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string"},
                        "symbol": {"type": "string"},
                        "instrument": {"type": "string"},
                        "qty": {"type": "integer"},
                        "order_type": {"type": "string"},
                        "limit_price": {"type": "number"},
                        "strike": {"type": "number"},
                        "expiry": {"type": "string"},
                    },
                    "required": ["action", "symbol", "instrument", "qty", "order_type"],
                },
            },
            {
                "name": "get_market_data",
                "description": "Fetch market data and IV stats",
                "input_schema": {
                    "type": "object",
                    "properties": {"symbol": {"type": "string"}},
                    "required": ["symbol"],
                },
            },
            {
                "name": "calculate_hedge",
                "description": "Calculate hedge recommendation",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "target_delta": {"type": "number"},
                        "current_delta": {"type": "number"},
                    },
                    "required": ["target_delta", "current_delta"],
                },
            },
            {
                "name": "get_trade_history",
                "description": "Return recent trades",
                "input_schema": {
                    "type": "object",
                    "properties": {"limit": {"type": "integer"}},
                    "required": ["limit"],
                },
            },
        ]

    async def _run_tool(self, client_id: uuid.UUID, name: str, args: dict[str, Any]) -> Any:
        if name == "get_portfolio_greeks":
            return await self.tools.get_portfolio_greeks()
        if name == "get_options_chain":
            return await self.tools.get_options_chain(args["symbol"], args.get("expiry"))
        if name == "submit_order":
            return await self.tools.submit_order(
                action=args["action"],
                symbol=args["symbol"],
                instrument=args["instrument"],
                qty=int(args["qty"]),
                order_type=args["order_type"],
                limit_price=args.get("limit_price"),
                strike=args.get("strike"),
                expiry=args.get("expiry"),
            )
        if name == "get_market_data":
            return await self.tools.get_market_data(args["symbol"])
        if name == "calculate_hedge":
            return await self.tools.calculate_hedge(
                target_delta=float(args["target_delta"]),
                current_delta=float(args["current_delta"]),
            )
        if name == "get_trade_history":
            rows = await self.tools.get_trade_history(client_id, int(args.get("limit", 20)))
            return [
                {
                    "id": row.id,
                    "timestamp": row.timestamp.isoformat(),
                    "symbol": row.symbol,
                    "action": row.action,
                    "qty": row.qty,
                    "status": row.status,
                }
                for row in rows
            ]
        return {"error": f"unknown_tool:{name}"}

    async def _create_proposal(self, client_id: uuid.UUID, trade_payload: dict[str, Any] | None, reasoning: str) -> Proposal:
        proposal = Proposal(
            client_id=client_id,
            trade_payload=trade_payload or {},
            agent_reasoning=reasoning,
            status="pending",
        )
        self.db.add(proposal)
        await self.db.commit()
        await self.db.refresh(proposal)
        return proposal

    async def _save_memory(self, client_id: uuid.UUID, role: str, content: str) -> None:
        self.db.add(AgentMemory(client_id=client_id, message_role=role, content=content))
        await self.db.commit()

    async def _audit(
        self,
        client_id: uuid.UUID,
        event_type: str,
        details: dict[str, Any],
        risk_rule: str | None = None,
    ) -> None:
        self.db.add(
            AuditLog(
                client_id=client_id,
                event_type=event_type,
                details=details,
                risk_rule_triggered=risk_rule,
            )
        )
        await self.db.commit()
        await self._publish_stream_event(
            client_id,
            "audit",
            {"event_type": event_type, "details": details, "risk_rule": risk_rule},
        )

    async def _recent_trades(self, client_id: uuid.UUID, limit: int) -> list[Trade]:
        result = await self.db.execute(
            select(Trade).where(Trade.client_id == client_id).order_by(desc(Trade.timestamp)).limit(limit)
        )
        return list(result.scalars().all())

    async def _cache_portfolio_state(self, client_id: uuid.UUID, portfolio: dict[str, Any]) -> None:
        if self.redis_client is None:
            return
        key = f"client:{client_id}:greeks"
        payload = {
            "client_id": str(client_id),
            "net_greeks": portfolio.get("net_greeks", {}),
            "positions": portfolio.get("positions", []),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            await self.redis_client.set(key, json.dumps(payload, default=str), ex=15)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to cache greeks in redis", extra={"client_id": str(client_id), "error": str(exc)})

    async def _publish_stream_event(self, client_id: uuid.UUID, event_type: str, data: dict[str, Any]) -> None:
        if self.redis_client is None:
            return
        channel = f"client:{client_id}:events"
        payload = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        try:
            await self.redis_client.publish(channel, json.dumps(payload, default=str))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to publish stream event", extra={"client_id": str(client_id), "error": str(exc)})
