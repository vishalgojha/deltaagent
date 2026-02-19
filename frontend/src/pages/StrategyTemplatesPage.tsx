import { FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createStrategyTemplate,
  deleteStrategyTemplate,
  executeStrategyTemplate,
  listStrategyTemplates,
  resolveStrategyTemplate,
  updateStrategyTemplate
} from "../api/endpoints";
import type { StrategyPreview, StrategyTemplate } from "../types";

type StrategyTemplateForm = {
  name: string;
  strategy_type: "butterfly" | "iron_fly" | "broken_wing_butterfly";
  underlying_symbol: string;
  dte_min: string;
  dte_max: string;
  center_delta_target: string;
  wing_width: string;
  max_risk_per_trade: string;
  sizing_method: "fixed_contracts" | "risk_based";
  max_contracts: string;
  hedge_enabled: boolean;
  auto_execute: boolean;
};

const initialForm: StrategyTemplateForm = {
  name: "ES Delta Butterfly",
  strategy_type: "butterfly",
  underlying_symbol: "ES",
  dte_min: "3",
  dte_max: "10",
  center_delta_target: "0.30",
  wing_width: "50",
  max_risk_per_trade: "1000",
  sizing_method: "risk_based",
  max_contracts: "5",
  hedge_enabled: false,
  auto_execute: false
};

function toForm(template: StrategyTemplate): StrategyTemplateForm {
  return {
    name: template.name,
    strategy_type: template.strategy_type,
    underlying_symbol: template.underlying_symbol,
    dte_min: String(template.dte_min),
    dte_max: String(template.dte_max),
    center_delta_target: String(template.center_delta_target),
    wing_width: String(template.wing_width),
    max_risk_per_trade: String(template.max_risk_per_trade),
    sizing_method: template.sizing_method,
    max_contracts: String(template.max_contracts),
    hedge_enabled: template.hedge_enabled,
    auto_execute: template.auto_execute
  };
}

function PnlCurveChart({ points }: { points: Array<{ underlying: number; pnl: number }> }) {
  if (!points.length) return null;
  const width = 520;
  const height = 180;
  const pad = 22;
  const xs = points.map((p) => p.underlying);
  const ys = points.map((p) => p.pnl);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const x = (v: number) => pad + ((v - minX) / Math.max(maxX - minX, 1)) * (width - 2 * pad);
  const y = (v: number) => height - pad - ((v - minY) / Math.max(maxY - minY, 1)) * (height - 2 * pad);
  const polyline = points.map((p) => `${x(p.underlying)},${y(p.pnl)}`).join(" ");
  const zeroY = y(0);
  return (
    <svg viewBox={`0 0 ${width} ${height}`} style={{ width: "100%", height: 180, border: "1px solid #e2e8f0", borderRadius: 8 }}>
      <line x1={pad} y1={zeroY} x2={width - pad} y2={zeroY} stroke="#94a3b8" strokeDasharray="4 4" />
      <polyline points={polyline} fill="none" stroke="#0b3b8f" strokeWidth={2.5} />
      {points.map((p) => (
        <circle key={`${p.underlying}`} cx={x(p.underlying)} cy={y(p.pnl)} r={3} fill="#0b3b8f" />
      ))}
    </svg>
  );
}

type Props = {
  isHalted?: boolean;
  haltReason?: string;
};

export function StrategyTemplatesPage({ isHalted = false, haltReason = "" }: Props) {
  const qc = useQueryClient();
  const [form, setForm] = useState<StrategyTemplateForm>(initialForm);
  const [selectedTemplate, setSelectedTemplate] = useState<number | null>(null);
  const [preview, setPreview] = useState<StrategyPreview | null>(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const templatesQuery = useQuery({
    queryKey: ["strategy-templates"],
    queryFn: listStrategyTemplates
  });

  function normalizePayload() {
    return {
      name: form.name.trim(),
      strategy_type: form.strategy_type,
      underlying_symbol: form.underlying_symbol.trim().toUpperCase(),
      dte_min: Number(form.dte_min),
      dte_max: Number(form.dte_max),
      center_delta_target: Number(form.center_delta_target),
      wing_width: Number(form.wing_width),
      max_risk_per_trade: Number(form.max_risk_per_trade),
      sizing_method: form.sizing_method,
      max_contracts: Number(form.max_contracts),
      hedge_enabled: form.hedge_enabled,
      auto_execute: form.auto_execute
    };
  }

  const createMutation = useMutation({
    mutationFn: createStrategyTemplate,
    onSuccess: (created) => {
      setSuccess(`Template created: #${created.id}`);
      setError("");
      setSelectedTemplate(created.id);
      qc.invalidateQueries({ queryKey: ["strategy-templates"] });
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : "Failed to create template");
      setSuccess("");
    }
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: ReturnType<typeof normalizePayload> }) =>
      updateStrategyTemplate(id, payload),
    onSuccess: (updated) => {
      setSuccess(`Template updated: #${updated.id}`);
      setError("");
      qc.invalidateQueries({ queryKey: ["strategy-templates"] });
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : "Failed to update template");
      setSuccess("");
    }
  });

  const resolveMutation = useMutation({
    mutationFn: resolveStrategyTemplate,
    onSuccess: (data) => {
      setPreview(data);
      setError("");
      setSuccess(`Preview loaded for template #${data.template_id}`);
    },
    onError: (err) => {
      setPreview(null);
      setError(err instanceof Error ? err.message : "Failed to resolve template");
      setSuccess("");
    }
  });

  const executeMutation = useMutation({
    mutationFn: executeStrategyTemplate,
    onSuccess: (data) => {
      setSuccess(`Order submitted: ${data.order_id ?? "pending id"} (${data.status})`);
      setError("");
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : "Failed to execute template");
      setSuccess("");
    }
  });

  const deleteMutation = useMutation({
    mutationFn: deleteStrategyTemplate,
    onSuccess: () => {
      setSuccess("Template deleted");
      setError("");
      setSelectedTemplate(null);
      setPreview(null);
      setForm(initialForm);
      qc.invalidateQueries({ queryKey: ["strategy-templates"] });
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : "Failed to delete template");
      setSuccess("");
    }
  });

  const templates = templatesQuery.data ?? [];
  const selected = useMemo(
    () => templates.find((row) => row.id === selectedTemplate) ?? null,
    [templates, selectedTemplate]
  );

  async function onCreate(event: FormEvent) {
    event.preventDefault();
    setError("");
    setSuccess("");
    const payload = normalizePayload();
    if (!payload.name || !payload.underlying_symbol) {
      setError("Name and underlying symbol are required");
      return;
    }
    if (payload.dte_max < payload.dte_min) {
      setError("DTE max must be greater than or equal to DTE min");
      return;
    }
    await createMutation.mutateAsync(payload);
  }

  async function onUpdate() {
    if (!selectedTemplate) {
      setError("Select a template first");
      return;
    }
    const payload = normalizePayload();
    if (!payload.name || !payload.underlying_symbol) {
      setError("Name and underlying symbol are required");
      return;
    }
    if (payload.dte_max < payload.dte_min) {
      setError("DTE max must be greater than or equal to DTE min");
      return;
    }
    await updateMutation.mutateAsync({ id: selectedTemplate, payload });
  }

  async function onPreview() {
    if (!selectedTemplate) {
      setError("Select a template first");
      return;
    }
    await resolveMutation.mutateAsync(selectedTemplate);
  }

  async function onExecute() {
    if (isHalted) {
      setError(haltReason || "Trading is globally halted");
      return;
    }
    if (!selectedTemplate) {
      setError("Select a template first");
      return;
    }
    await executeMutation.mutateAsync(selectedTemplate);
  }

  async function onDelete() {
    if (!selectedTemplate) {
      setError("Select a template first");
      return;
    }
    if (!window.confirm(`Delete template #${selectedTemplate}?`)) return;
    await deleteMutation.mutateAsync(selectedTemplate);
  }

  return (
    <div className="grid grid-2">
      <section className="card">
        <h3>Create Strategy Template</h3>
        <form className="grid" onSubmit={onCreate}>
          <label className="grid">
            Name
            <input value={form.name} onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))} />
          </label>
          <div className="grid grid-2">
            <label className="grid">
              Strategy Type
              <select
                value={form.strategy_type}
                onChange={(e) =>
                  setForm((p) => ({ ...p, strategy_type: e.target.value as StrategyTemplate["strategy_type"] }))
                }
              >
                <option value="butterfly">butterfly</option>
                <option value="iron_fly">iron_fly</option>
                <option value="broken_wing_butterfly">broken_wing_butterfly</option>
              </select>
            </label>
            <label className="grid">
              Underlying
              <input
                value={form.underlying_symbol}
                onChange={(e) => setForm((p) => ({ ...p, underlying_symbol: e.target.value }))}
              />
            </label>
          </div>

          <div className="grid grid-2">
            <label className="grid">
              DTE Min
              <input value={form.dte_min} onChange={(e) => setForm((p) => ({ ...p, dte_min: e.target.value }))} />
            </label>
            <label className="grid">
              DTE Max
              <input value={form.dte_max} onChange={(e) => setForm((p) => ({ ...p, dte_max: e.target.value }))} />
            </label>
          </div>

          <div className="grid grid-2">
            <label className="grid">
              Center Delta Target
              <input
                value={form.center_delta_target}
                onChange={(e) => setForm((p) => ({ ...p, center_delta_target: e.target.value }))}
              />
            </label>
            <label className="grid">
              Wing Width (points)
              <input value={form.wing_width} onChange={(e) => setForm((p) => ({ ...p, wing_width: e.target.value }))} />
            </label>
          </div>

          <div className="grid grid-2">
            <label className="grid">
              Max Risk Per Trade
              <input
                value={form.max_risk_per_trade}
                onChange={(e) => setForm((p) => ({ ...p, max_risk_per_trade: e.target.value }))}
              />
            </label>
            <label className="grid">
              Max Contracts
              <input
                value={form.max_contracts}
                onChange={(e) => setForm((p) => ({ ...p, max_contracts: e.target.value }))}
              />
            </label>
          </div>

          <label className="grid">
            Sizing Method
            <select
              value={form.sizing_method}
              onChange={(e) => setForm((p) => ({ ...p, sizing_method: e.target.value as "fixed_contracts" | "risk_based" }))}
            >
              <option value="risk_based">risk_based</option>
              <option value="fixed_contracts">fixed_contracts</option>
            </select>
          </label>

          <div className="row">
            <label className="row">
              <input
                type="checkbox"
                checked={form.hedge_enabled}
                onChange={(e) => setForm((p) => ({ ...p, hedge_enabled: e.target.checked }))}
              />
              Hedge Enabled
            </label>
            <label className="row">
              <input
                type="checkbox"
                checked={form.auto_execute}
                onChange={(e) => setForm((p) => ({ ...p, auto_execute: e.target.checked }))}
              />
              Auto Execute
            </label>
          </div>

          <button type="submit" disabled={createMutation.isPending}>
            {createMutation.isPending ? "Creating..." : "Create Template"}
          </button>
          <div className="row">
            <button type="button" className="secondary" disabled={!selectedTemplate || updateMutation.isPending} onClick={onUpdate}>
              {updateMutation.isPending ? "Updating..." : "Update Selected"}
            </button>
            <button type="button" className="danger" disabled={!selectedTemplate || deleteMutation.isPending} onClick={onDelete}>
              {deleteMutation.isPending ? "Deleting..." : "Delete Selected"}
            </button>
          </div>
        </form>
      </section>

      <section className="card">
        <h3>Template Preview</h3>
        <div className="grid">
          <label className="grid">
            Select Template
            <select
              value={selectedTemplate ?? ""}
              onChange={(e) => {
                const id = e.target.value ? Number(e.target.value) : null;
                setSelectedTemplate(id);
                const row = templates.find((t) => t.id === id);
                if (row) setForm(toForm(row));
              }}
            >
              <option value="">Choose...</option>
              {templates.map((row) => (
                <option key={row.id} value={row.id}>
                  #{row.id} {row.name}
                </option>
              ))}
            </select>
          </label>

          <div className="row">
            <button className="secondary" onClick={onPreview} disabled={!selectedTemplate || resolveMutation.isPending}>
              {resolveMutation.isPending ? "Loading..." : "Load + Preview"}
            </button>
            <button onClick={onExecute} disabled={isHalted || !selectedTemplate || executeMutation.isPending}>
              {executeMutation.isPending ? "Executing..." : "Execute"}
            </button>
          </div>
          {isHalted && <p style={{ color: "#991b1b", margin: 0 }}>{haltReason || "Trading is globally halted."}</p>}
          {selected && <p className="muted">Underlying {selected.underlying_symbol}, type {selected.strategy_type}</p>}
        </div>

        {preview ? (
          <div className="grid strategy-preview">
            <p>Expiry: {preview.expiry} (DTE {preview.dte})</p>
            <p>Center Strike: {preview.center_strike}</p>
            <p>Contracts: {preview.contracts}</p>
            <p>Estimated Risk: {preview.estimated_max_risk}</p>
            <p>Estimated Net Delta: {preview.estimated_net_delta}</p>
            <p className="muted">Greeks: {JSON.stringify(preview.greeks)}</p>

            <h4>Legs</h4>
            <table className="table-scroll">
              <thead>
                <tr>
                  <th>Action</th>
                  <th>Ratio</th>
                  <th>Strike</th>
                  <th>Delta</th>
                  <th>Mid</th>
                </tr>
              </thead>
              <tbody>
                {preview.legs.map((leg, idx) => (
                  <tr key={`${leg.strike}-${idx}`}>
                    <td>{leg.action}</td>
                    <td>{leg.ratio}</td>
                    <td>{leg.strike}</td>
                    <td>{leg.delta ?? "-"}</td>
                    <td>{leg.mid_price ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <h4>Estimated PnL Curve</h4>
            <PnlCurveChart points={preview.pnl_curve} />
            <table className="table-scroll">
              <thead>
                <tr>
                  <th>Underlying</th>
                  <th>PnL</th>
                </tr>
              </thead>
              <tbody>
                {preview.pnl_curve.map((p) => (
                  <tr key={`${p.underlying}`}>
                    <td>{p.underlying}</td>
                    <td>{p.pnl}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="muted">No preview loaded</p>
        )}

        {error && <p style={{ color: "#991b1b", marginTop: 8 }}>{error}</p>}
        {success && <p style={{ color: "#166534", marginTop: 8 }}>{success}</p>}
      </section>
    </div>
  );
}
