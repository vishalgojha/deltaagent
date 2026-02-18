import json
import logging
import uuid
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent.memory import AgentMemoryStore
from backend.agent.prompts import AUTONOMOUS_PROMPT, CONFIRMATION_PROMPT
from backend.agent.risk import RiskGovernor, RiskParameters, RiskViolation
from backend.agent.tools import AgentTools
from backend.brokers.base import BrokerBase
from backend.config import get_settings
from backend.db.models import AgentMemory, AuditLog, Client, Proposal, Trade
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
    ) -> None:
        self.broker = broker
        self.db = db
        self.memory_store = memory_store
        self.risk_governor = risk_governor
        self.emergency_halt = emergency_halt
        self.tools = AgentTools(broker=broker, db=db)
        self.settings = get_settings()

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
        return {
            "client_id": client_id,
            "mode": context.mode,
            "last_action": context.last_action,
            "healthy": context.healthy,
            "net_greeks": context.net_greeks,
        }

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

    async def set_parameters(self, client_id: uuid.UUID, params: dict[str, Any]) -> None:
        context = self.memory_store.get_or_create(client_id)
        context.parameters = params
        self.memory_store.update(context)
        client = await self.db.get(Client, client_id)
        if client:
            client.risk_params = params
            await self.db.commit()
        await self._audit(client_id, "risk_params_updated", {"risk_params": params})

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
        market = await self.tools.get_market_data(trade_payload["symbol"])
        net_delta = float(portfolio["net_greeks"]["delta"])
        order_delta_est = float(trade_payload.get("delta_estimate", 0.5))
        direction = 1 if trade_payload["action"].upper() == "BUY" else -1
        projected_delta = net_delta + direction * int(trade_payload["qty"]) * order_delta_est
        recent = await self._recent_trades(client_id, 30)
        daily_pnl = sum(t.pnl for t in recent)
        open_legs = sum(abs(int(p.get("qty", 0))) for p in portfolio["positions"])
        try:
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
        await self._audit(client_id, "order_executed", {"trade_id": trade.id, "order": order, "reasoning": reasoning})
        return {"trade_id": trade.id, "order": order}

    async def _decide(
        self,
        mode: str,
        message: str,
        context: Any,
        params: RiskParameters,
    ) -> dict[str, Any]:
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
            }
        default_reasoning = (
            f"Detected net delta {rebalance['net_delta']:.4f}, threshold {params.delta_threshold:.4f}. "
            f"{'Proposing hedge.' if default_trade else 'No trade needed.'}"
        )

        llm = await self._call_llm(mode, message, context, default_reasoning, default_trade)
        return llm

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
                    return {
                        "reasoning": parsed.get("reasoning", fallback_reasoning),
                        "trade": parsed.get("trade", fallback_trade),
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

    async def _recent_trades(self, client_id: uuid.UUID, limit: int) -> list[Trade]:
        result = await self.db.execute(
            select(Trade).where(Trade.client_id == client_id).order_by(desc(Trade.timestamp)).limit(limit)
        )
        return list(result.scalars().all())
