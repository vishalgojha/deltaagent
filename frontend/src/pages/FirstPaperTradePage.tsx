import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { getReadiness, getTrades } from "../api/endpoints";
import type { Trade } from "../types";

type Props = {
  clientId: string;
  isHalted?: boolean;
  haltReason?: string;
};

const CHECKLIST_STEPS = [
  {
    id: "start_stack",
    label: "Start services with start.bat and verify status.bat shows Backend/Frontend/Postgres/Redis as UP."
  },
  {
    id: "broker_connected",
    label: "Open Broker Settings and confirm paper broker connection is healthy."
  },
  {
    id: "risk_limits",
    label: "Open Dashboard and set conservative limits (example: max_size=1)."
  },
  {
    id: "proposal_only",
    label: "In Agent Console, request one proposal only (confirmation mode, no auto execution)."
  },
  {
    id: "execute_once",
    label: "Review proposal and execute exactly one paper trade through Trade Ticket confirmation."
  },
  {
    id: "verify_status",
    label: "Confirm Latest Trade Status is filled/rejected and capture order_id + fill price."
  }
] as const;

type ChecklistKey = (typeof CHECKLIST_STEPS)[number]["id"];
type ChecklistState = Record<ChecklistKey, boolean>;

function checklistStorageKey(clientId: string): string {
  return `ta_first_paper_trade_checklist_${clientId}`;
}

function defaultChecklistState(): ChecklistState {
  return CHECKLIST_STEPS.reduce((acc, step) => {
    acc[step.id] = false;
    return acc;
  }, {} as ChecklistState);
}

function readChecklistState(clientId: string): ChecklistState {
  const fallback = defaultChecklistState();
  if (typeof window === "undefined") return fallback;
  try {
    const raw = window.localStorage.getItem(checklistStorageKey(clientId));
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Partial<Record<ChecklistKey, unknown>>;
    const next = { ...fallback };
    for (const step of CHECKLIST_STEPS) {
      next[step.id] = parsed[step.id] === true;
    }
    return next;
  } catch {
    return fallback;
  }
}

function formatTradeTimestamp(trade: Trade | null): string {
  if (!trade) return "-";
  return new Date(trade.timestamp).toLocaleString();
}

export function FirstPaperTradePage({ clientId, isHalted = false, haltReason = "" }: Props) {
  const navigate = useNavigate();
  const [checklist, setChecklist] = useState<ChecklistState>(() => readChecklistState(clientId));

  useEffect(() => {
    setChecklist(readChecklistState(clientId));
  }, [clientId]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(checklistStorageKey(clientId), JSON.stringify(checklist));
  }, [clientId, checklist]);

  const readinessQuery = useQuery({
    queryKey: ["first-paper-trade-readiness", clientId],
    queryFn: () => getReadiness(clientId),
    refetchInterval: 10000
  });

  const tradesQuery = useQuery({
    queryKey: ["first-paper-trade-trades", clientId],
    queryFn: () => getTrades(clientId),
    refetchInterval: 10000
  });

  const latestTrade = useMemo(() => (tradesQuery.data ?? [])[0] ?? null, [tradesQuery.data]);
  const completedCount = useMemo(
    () => CHECKLIST_STEPS.filter((step) => checklist[step.id]).length,
    [checklist]
  );
  const readiness = readinessQuery.data;

  function toggleStep(step: ChecklistKey) {
    setChecklist((prev) => ({ ...prev, [step]: !prev[step] }));
  }

  function resetChecklist() {
    setChecklist(defaultChecklistState());
  }

  return (
    <div className="grid paper-trade-page">
      <section className="card">
        <div className="section-head">
          <div>
            <h3>First Paper Trade Flow</h3>
            <p className="muted">One focused path: connect, preflight, propose, execute once, verify.</p>
          </div>
        </div>
        <div className="metric-grid" style={{ marginTop: 12 }}>
          <article className="metric-card">
            <p className="metric-label">Checklist</p>
            <p className="metric-value">
              {completedCount}/{CHECKLIST_STEPS.length}
            </p>
          </article>
          <article className="metric-card">
            <p className="metric-label">Readiness</p>
            <p className="metric-value">
              {readinessQuery.isLoading ? "checking" : readiness?.ready ? "ready" : "blocked"}
            </p>
          </article>
          <article className="metric-card">
            <p className="metric-label">Broker</p>
            <p className="metric-value">
              {readinessQuery.isLoading ? "..." : readiness?.connected ? "connected" : "down"}
            </p>
          </article>
          <article className="metric-card">
            <p className="metric-label">Latest Trade</p>
            <p className="metric-value">{latestTrade?.status ?? "-"}</p>
          </article>
        </div>
        {isHalted && (
          <p style={{ color: "#fca5a5", marginTop: 10 }}>
            Execution blocked: {haltReason || "Global emergency halt is active."}
          </p>
        )}
        {readiness && !readiness.ready && (
          <p style={{ color: "#fca5a5", marginTop: 10 }}>
            Readiness blocked: {readiness.last_error || "Resolve broker/market-data checks first."}
          </p>
        )}
      </section>

      <section className="card">
        <div className="section-head">
          <div>
            <h3>Checklist</h3>
            <p className="muted">Tick each item once completed.</p>
          </div>
          <button type="button" className="secondary" onClick={resetChecklist}>
            Reset
          </button>
        </div>
        <div className="grid" style={{ marginTop: 8 }}>
          {CHECKLIST_STEPS.map((step, index) => (
            <label key={step.id} className="paper-check-item">
              <input
                type="checkbox"
                checked={checklist[step.id]}
                onChange={() => toggleStep(step.id)}
              />
              <span>
                <strong>Step {index + 1}:</strong> {step.label}
              </span>
            </label>
          ))}
        </div>
        <div className="row" style={{ marginTop: 10 }}>
          <button type="button" className="secondary" onClick={() => navigate("/settings/broker")}>
            Open Broker Settings
          </button>
          <button type="button" className="secondary" onClick={() => navigate("/dashboard")}>
            Open Dashboard
          </button>
          <button type="button" onClick={() => navigate("/agent")}>
            Open Agent Console
          </button>
        </div>
      </section>

      <div className="grid grid-2">
        <section className="card">
          <h3>Readiness Snapshot</h3>
          {readinessQuery.isLoading ? (
            <p className="muted">Checking readiness...</p>
          ) : readiness ? (
            <div className="grid">
              <p>Ready: {String(readiness.ready)}</p>
              <p>Broker Connected: {String(readiness.connected)}</p>
              <p>Market Data OK: {String(readiness.market_data_ok)}</p>
              <p>Risk Blocked: {String(readiness.risk_blocked)}</p>
              <p className="muted">Updated: {new Date(readiness.updated_at).toLocaleString()}</p>
              {readiness.last_error && <p style={{ color: "#fca5a5" }}>{readiness.last_error}</p>}
            </div>
          ) : (
            <p className="muted">No readiness data.</p>
          )}
        </section>

        <section className="card">
          <h3>Latest Trade Check</h3>
          {tradesQuery.isLoading ? (
            <p className="muted">Loading trades...</p>
          ) : latestTrade ? (
            <div className="grid">
              <p>Status: {latestTrade.status}</p>
              <p>Order ID: {latestTrade.order_id ?? "-"}</p>
              <p>Fill Price: {latestTrade.fill_price ?? "-"}</p>
              <p>Symbol: {latestTrade.symbol}</p>
              <p>Time: {formatTradeTimestamp(latestTrade)}</p>
            </div>
          ) : (
            <p className="muted">No trades yet. Complete checklist steps 1-5 first.</p>
          )}
        </section>
      </div>
    </div>
  );
}
