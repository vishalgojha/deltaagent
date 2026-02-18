import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  approveProposal,
  getStatus,
  getProposals,
  rejectProposal,
  sendChat,
  setMode
} from "../api/endpoints";
import type { ChatResponse } from "../types";
import { useAgentStream } from "../hooks/useAgentStream";

type Props = { clientId: string; token: string };

type TimelineKind = "user" | "assistant" | "tool_call" | "tool_result" | "proposal" | "status" | "system";
type RunStatus = "running" | "completed";

type TimelineItem = {
  id: string;
  kind: TimelineKind;
  text: string;
  payload?: Record<string, unknown>;
  proposalId?: number;
  createdAt: string;
};

type TimelineRun = {
  id: string;
  title: string;
  status: RunStatus;
  items: TimelineItem[];
  createdAt: string;
};

type ToolStepStatus = "queued" | "running" | "completed" | "failed";

type ToolStep = {
  id: string;
  name: string;
  input?: Record<string, unknown>;
  output?: Record<string, unknown>;
  status: ToolStepStatus;
  durationMs?: number;
};

type PersistedTimelineState = {
  version: number;
  runs: TimelineRun[];
  resolvedProposals: Record<number, "approved" | "rejected">;
  proposalRunEntries: Array<[number, string]>;
};

const TIMELINE_STORAGE_VERSION = 1;

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function nowIso(): string {
  return new Date().toISOString();
}

function storageKey(clientId: string): string {
  return `ta_agent_timeline_${clientId}`;
}

function toolResultFailed(payload?: Record<string, unknown>): boolean {
  if (!payload) return false;
  if (payload.success === false) return true;
  return typeof payload.error === "string" && payload.error.length > 0;
}

function summarizeRunTools(run: TimelineRun | null): ToolStep[] {
  if (!run) return [];

  const steps: ToolStep[] = [];
  for (const item of run.items) {
    if (item.kind === "tool_call") {
      steps.push({
        id: item.id,
        name: item.text,
        input: item.payload,
        status: "queued",
        durationMs: typeof item.payload?.duration_ms === "number" ? item.payload.duration_ms : undefined
      });
      continue;
    }

    if (item.kind === "tool_result") {
      const target = steps.find((step) => step.status === "queued" || step.status === "running");
      if (target) {
        target.output = item.payload;
        target.status = toolResultFailed(item.payload) ? "failed" : "completed";
        if (typeof item.payload?.duration_ms === "number") {
          target.durationMs = item.payload.duration_ms;
        }
      } else {
        steps.push({
          id: item.id,
          name: "tool_result",
          output: item.payload,
          status: toolResultFailed(item.payload) ? "failed" : "completed",
          durationMs: typeof item.payload?.duration_ms === "number" ? item.payload.duration_ms : undefined
        });
      }
    }
  }

  if (run.status === "running") {
    const firstQueued = steps.find((step) => step.status === "queued");
    if (firstQueued) firstQueued.status = "running";
  }

  return steps;
}

export function AgentConsolePage({ clientId, token }: Props) {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState("");
  const [mode, setModeUi] = useState<"confirmation" | "autonomous">("confirmation");
  const [runs, setRuns] = useState<TimelineRun[]>([]);
  const [expandedToolItems, setExpandedToolItems] = useState<Record<string, boolean>>({});
  const [expandedWorkflowSteps, setExpandedWorkflowSteps] = useState<Record<string, boolean>>({});
  const [error, setError] = useState("");
  const [resolvedProposals, setResolvedProposals] = useState<Record<number, "approved" | "rejected">>({});
  const proposalIdsSeen = useRef<Set<number>>(new Set());
  const proposalRunMap = useRef<Map<number, string>>(new Map());
  const latestStatusRef = useRef("");
  const activeRunIdRef = useRef<string | null>(null);
  const { connected, lastEvent } = useAgentStream(clientId, token);

  const proposalsQuery = useQuery({
    queryKey: ["proposals", clientId],
    queryFn: async () => {
      const rows = await getProposals(clientId);
      return rows.filter((p) => p.status === "pending");
    }
  });

  const statusQuery = useQuery({
    queryKey: ["agent-status", clientId],
    queryFn: () => getStatus(clientId)
  });

  const pendingProposalIds = useMemo(
    () => new Set((proposalsQuery.data ?? []).map((proposal) => proposal.id)),
    [proposalsQuery.data]
  );

  const currentRun = runs[0] ?? null;
  const toolStripItems = useMemo(
    () => (currentRun?.items ?? []).filter((item) => item.kind === "tool_call" || item.kind === "tool_result").slice(-8),
    [currentRun]
  );
  const currentRunToolSteps = useMemo(() => summarizeRunTools(currentRun), [currentRun]);
  const currentRunHasProposal = useMemo(
    () => (currentRun?.items ?? []).some((item) => item.kind === "proposal"),
    [currentRun]
  );
  const currentRunHasAssistantText = useMemo(
    () => (currentRun?.items ?? []).some((item) => item.kind === "assistant"),
    [currentRun]
  );

  useEffect(() => {
    setRuns([]);
    setResolvedProposals({});
    setExpandedToolItems({});
    setExpandedWorkflowSteps({});
    proposalIdsSeen.current = new Set();
    proposalRunMap.current = new Map();
    activeRunIdRef.current = null;
    latestStatusRef.current = "";
    try {
      const raw = localStorage.getItem(storageKey(clientId));
      if (!raw) return;
      const parsed = JSON.parse(raw) as PersistedTimelineState;
      if (parsed.version !== TIMELINE_STORAGE_VERSION || !Array.isArray(parsed.runs)) return;
      const restoredRuns = parsed.runs.slice(0, 20);
      setRuns(restoredRuns);
      setResolvedProposals(parsed.resolvedProposals ?? {});
      proposalRunMap.current = new Map(parsed.proposalRunEntries ?? []);
      for (const run of restoredRuns) {
        for (const item of run.items) {
          if (item.kind === "proposal" && typeof item.proposalId === "number") {
            proposalIdsSeen.current.add(item.proposalId);
          }
        }
      }
      const inProgress = restoredRuns.find((run) => run.status === "running");
      activeRunIdRef.current = inProgress?.id ?? null;
    } catch {
      // ignore malformed saved timeline state
    }
  }, [clientId]);

  useEffect(() => {
    const payload: PersistedTimelineState = {
      version: TIMELINE_STORAGE_VERSION,
      runs: runs.slice(0, 20),
      resolvedProposals,
      proposalRunEntries: Array.from(proposalRunMap.current.entries())
    };
    try {
      localStorage.setItem(storageKey(clientId), JSON.stringify(payload));
    } catch {
      // ignore storage write failures
    }
  }, [clientId, runs, resolvedProposals]);

  useEffect(() => {
    if (statusQuery.data?.mode) {
      setModeUi(statusQuery.data.mode);
    }
  }, [statusQuery.data?.mode]);

  const sendChatMutation = useMutation({
    mutationFn: (chatMessage: string) => sendChat(clientId, chatMessage)
  });

  const setModeMutation = useMutation({
    mutationFn: (nextMode: "confirmation" | "autonomous") => setMode(clientId, nextMode),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["agent-status", clientId] });
    }
  });

  const approveMutation = useMutation({
    mutationFn: (id: number) => approveProposal(clientId, id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["proposals", clientId] });
    }
  });

  const rejectMutation = useMutation({
    mutationFn: (id: number) => rejectProposal(clientId, id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["proposals", clientId] });
    }
  });

  function startRun(prompt: string): string {
    const runId = crypto.randomUUID();
    const createdAt = nowIso();
    const run: TimelineRun = {
      id: runId,
      title: prompt.slice(0, 72),
      status: "running",
      createdAt,
      items: [{ id: crypto.randomUUID(), kind: "user", text: prompt, createdAt }]
    };
    setRuns((prev) => [run, ...prev].slice(0, 20));
    activeRunIdRef.current = runId;
    return runId;
  }

  function appendToRun(runId: string, items: TimelineItem[]) {
    if (items.length === 0) return;
    setRuns((prev) =>
      prev.map((run) => (run.id === runId ? { ...run, items: [...run.items, ...items].slice(-120) } : run))
    );
  }

  function appendSystemOutsideRun(item: TimelineItem) {
    const runId = activeRunIdRef.current;
    if (runId) {
      appendToRun(runId, [item]);
      return;
    }
    const fallbackId = crypto.randomUUID();
    setRuns((prev) => [
      {
        id: fallbackId,
        title: "Agent event",
        status: "completed",
        createdAt: item.createdAt,
        items: [item]
      },
      ...prev
    ]);
  }

  function completeRun(runId: string) {
    setRuns((prev) => prev.map((run) => (run.id === runId ? { ...run, status: "completed" } : run)));
    if (activeRunIdRef.current === runId) {
      activeRunIdRef.current = null;
    }
  }

  function asTimelineFromChat(response: ChatResponse): TimelineItem[] {
    const createdAt = nowIso();
    const items: TimelineItem[] = [];

    if (response.tool_trace_id) {
      items.push({
        id: crypto.randomUUID(),
        kind: "status",
        text: `tool_trace:${response.tool_trace_id}`,
        createdAt
      });
    }

    if (typeof response.message === "string" && response.message.trim()) {
      items.push({ id: crypto.randomUUID(), kind: "assistant", text: response.message, createdAt });
    }

    const toolCalls = Array.isArray(response.tool_calls) ? response.tool_calls : [];
    for (const call of toolCalls) {
      items.push({
        id: call.tool_use_id || crypto.randomUUID(),
        kind: "tool_call",
        text: call.name || "tool_call",
        payload: {
          tool_use_id: call.tool_use_id,
          input: call.input,
          started_at: call.started_at,
          completed_at: call.completed_at,
          duration_ms: call.duration_ms
        },
        createdAt
      });
    }

    const toolResults = Array.isArray(response.tool_results) ? response.tool_results : [];
    for (const result of toolResults) {
      items.push({
        id: crypto.randomUUID(),
        kind: "tool_result",
        text: result.name || "tool_result",
        payload: {
          tool_use_id: result.tool_use_id,
          output: result.output,
          success: result.success,
          error: result.error,
          started_at: result.started_at,
          completed_at: result.completed_at,
          duration_ms: result.duration_ms
        },
        createdAt
      });
    }

    if (toolCalls.length === 0 && Array.isArray(response.planned_tools)) {
      for (const planned of response.planned_tools) {
        if (!isRecord(planned)) continue;
        items.push({
          id: crypto.randomUUID(),
          kind: "tool_call",
          text: String(planned.name ?? "planned_tool"),
          payload: planned,
          createdAt
        });
      }
    }

    if (typeof response.proposal_id === "number") {
      items.push({
        id: `proposal-${response.proposal_id}`,
        kind: "proposal",
        text: "New proposal generated",
        payload: isRecord(response.proposal) ? response.proposal : undefined,
        proposalId: response.proposal_id,
        createdAt
      });
      proposalIdsSeen.current.add(response.proposal_id);
      if (activeRunIdRef.current) {
        proposalRunMap.current.set(response.proposal_id, activeRunIdRef.current);
      }
    }

    return items;
  }

  useEffect(() => {
    if (!lastEvent) return;
    const serialized = JSON.stringify(lastEvent);
    if (serialized === latestStatusRef.current) return;
    latestStatusRef.current = serialized;
    const eventType = typeof lastEvent.type === "string" ? lastEvent.type : "event";
    appendSystemOutsideRun({
      id: crypto.randomUUID(),
      kind: "status",
      text: eventType,
      payload: isRecord(lastEvent.data) ? lastEvent.data : lastEvent,
      createdAt: nowIso()
    });
  }, [lastEvent]);

  useEffect(() => {
    for (const proposal of proposalsQuery.data ?? []) {
      if (proposalIdsSeen.current.has(proposal.id)) continue;
      proposalIdsSeen.current.add(proposal.id);
      const proposalItem: TimelineItem = {
        id: `proposal-${proposal.id}`,
        kind: "proposal",
        text: proposal.agent_reasoning || "Pending proposal",
        payload: proposal.trade_payload,
        proposalId: proposal.id,
        createdAt: nowIso()
      };
      const runId = activeRunIdRef.current;
      if (runId) {
        proposalRunMap.current.set(proposal.id, runId);
        appendToRun(runId, [proposalItem]);
      } else {
        const standaloneRunId = crypto.randomUUID();
        proposalRunMap.current.set(proposal.id, standaloneRunId);
        setRuns((prev) => [
          {
            id: standaloneRunId,
            title: `Proposal #${proposal.id}`,
            status: "completed",
            createdAt: proposalItem.createdAt,
            items: [proposalItem]
          },
          ...prev
        ]);
      }
    }
  }, [proposalsQuery.data]);

  async function onSend(event: FormEvent) {
    event.preventDefault();
    setError("");
    const trimmed = message.trim();
    if (!trimmed) return;

    const runId = startRun(trimmed);
    try {
      const response = await sendChatMutation.mutateAsync(trimmed);
      setMessage("");
      appendToRun(runId, asTimelineFromChat(response));
      completeRun(runId);
      await queryClient.invalidateQueries({ queryKey: ["proposals", clientId] });
    } catch (err) {
      appendToRun(runId, [
        {
          id: crypto.randomUUID(),
          kind: "system",
          text: err instanceof Error ? err.message : "Chat failed",
          createdAt: nowIso()
        }
      ]);
      completeRun(runId);
      setError(err instanceof Error ? err.message : "Chat failed");
    }
  }

  async function onModeChange(nextMode: "confirmation" | "autonomous") {
    setError("");
    try {
      await setModeMutation.mutateAsync(nextMode);
      setModeUi(nextMode);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Mode update failed");
    }
  }

  async function onApprove(id: number) {
    await approveMutation.mutateAsync(id);
    setResolvedProposals((prev) => ({ ...prev, [id]: "approved" }));
    const runId = proposalRunMap.current.get(id) ?? activeRunIdRef.current;
    const item: TimelineItem = {
      id: crypto.randomUUID(),
      kind: "system",
      text: `Proposal #${id} approved.`,
      createdAt: nowIso()
    };
    if (runId) appendToRun(runId, [item]);
    else appendSystemOutsideRun(item);
  }

  async function onReject(id: number) {
    await rejectMutation.mutateAsync(id);
    setResolvedProposals((prev) => ({ ...prev, [id]: "rejected" }));
    const runId = proposalRunMap.current.get(id) ?? activeRunIdRef.current;
    const item: TimelineItem = {
      id: crypto.randomUUID(),
      kind: "system",
      text: `Proposal #${id} rejected.`,
      createdAt: nowIso()
    };
    if (runId) appendToRun(runId, [item]);
    else appendSystemOutsideRun(item);
  }

  function injectPrompt(prompt: string) {
    setMessage(prompt);
  }

  function getStepDurationLabel(step: ToolStep): string | null {
    if (typeof step.durationMs === "number") return `${step.durationMs} ms`;
    if (step.input && typeof step.input.duration_ms === "number") return `${step.input.duration_ms} ms`;
    if (step.output && typeof step.output.duration_ms === "number") return `${step.output.duration_ms} ms`;
    return null;
  }

  return (
    <div className="grid grid-2">
      <section className="card">
        <h3>Agent Controls</h3>
        <div className="row">
          <button className="secondary" onClick={() => onModeChange("confirmation")}>
            Confirmation
          </button>
          <button onClick={() => onModeChange("autonomous")}>Autonomous</button>
          <span className="muted">Current: {mode}</span>
          <span className="muted">WS: {connected ? "connected" : "disconnected"}</span>
        </div>
        <form onSubmit={onSend} className="grid" style={{ marginTop: 12 }}>
          <textarea
            rows={4}
            placeholder="Ask the agent..."
            value={message}
            onChange={(e) => setMessage(e.target.value)}
          />
          <button type="submit">Send</button>
        </form>
        <div className="row" style={{ marginTop: 6 }}>
          <button
            type="button"
            className="secondary"
            onClick={() => injectPrompt("Hedge portfolio delta to near neutral with minimum slippage.")}
          >
            Delta Hedge
          </button>
          <button
            type="button"
            className="secondary"
            onClick={() => injectPrompt("Check exposure and propose a low-risk rebalance for open positions.")}
          >
            Rebalance
          </button>
          <button
            type="button"
            className="secondary"
            onClick={() => injectPrompt("Summarize current risk posture and recommend actions for next 30 minutes.")}
          >
            Risk Summary
          </button>
        </div>

        <div className="agent-flow" style={{ marginTop: 14 }}>
          <div className="agent-flow-head">
            <p className="agent-flow-title">Tool Calling Workflow</p>
            <p className="muted" style={{ margin: 0 }}>
              {currentRun ? `Current Run: ${currentRun.title}` : "No active run"}
            </p>
          </div>
          <div className="agent-stage-row">
            <span className={`agent-stage ${currentRun ? "active" : ""}`}>Intent</span>
            <span className={`agent-stage ${currentRunHasAssistantText ? "active" : ""}`}>Plan</span>
            <span className={`agent-stage ${currentRunToolSteps.length > 0 ? "active" : ""}`}>Tool Calls</span>
            <span className={`agent-stage ${currentRunHasProposal ? "active" : ""}`}>Decision</span>
            <span className={`agent-stage ${currentRun?.status === "completed" ? "active" : ""}`}>Complete</span>
          </div>
          {currentRunToolSteps.length > 0 ? (
            <div className="grid" style={{ marginTop: 8 }}>
              {currentRunToolSteps.map((step, index) => (
                <div key={step.id} className="tool-step-card">
                  <div className="row" style={{ justifyContent: "space-between" }}>
                    <p style={{ margin: 0, fontWeight: 700 }}>
                      Step {index + 1}: {step.name}
                    </p>
                    <div className="row">
                      {getStepDurationLabel(step) && <span className="tool-step-duration">{getStepDurationLabel(step)}</span>}
                      <span className={`tool-step-status ${step.status}`}>{step.status}</span>
                      <button
                        type="button"
                        className="secondary tool-step-toggle"
                        onClick={() =>
                          setExpandedWorkflowSteps((prev) => ({
                            ...prev,
                            [step.id]: !prev[step.id]
                          }))
                        }
                      >
                        {expandedWorkflowSteps[step.id] ? "Hide" : "Details"}
                      </button>
                    </div>
                  </div>
                  {expandedWorkflowSteps[step.id] && (
                    <div className="tool-step-details">
                      {step.input && <pre style={{ marginTop: 8 }}>{JSON.stringify(step.input, null, 2)}</pre>}
                      {step.output && <pre style={{ marginTop: 8 }}>{JSON.stringify(step.output, null, 2)}</pre>}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="muted" style={{ marginTop: 8 }}>
              Start a request to see planned and executed tool steps.
            </p>
          )}
        </div>

        <div style={{ marginTop: 12 }}>
          <p style={{ margin: "0 0 6px 0", fontWeight: 700 }}>Tool Execution</p>
          {toolStripItems.length === 0 && <p className="muted" style={{ margin: 0 }}>No tool calls in current run.</p>}
          <div className="row" style={{ alignItems: "flex-start" }}>
            {toolStripItems.map((item) => (
              <div key={item.id} className="card" style={{ minWidth: 180, margin: 0 }}>
                <button
                  className="secondary"
                  type="button"
                  onClick={() =>
                    setExpandedToolItems((prev) => ({
                      ...prev,
                      [item.id]: !prev[item.id]
                    }))
                  }
                >
                  {item.kind === "tool_call" ? "Call" : "Result"}: {item.text}
                </button>
                {expandedToolItems[item.id] && item.payload && (
                  <pre style={{ marginTop: 8 }}>{JSON.stringify(item.payload, null, 2)}</pre>
                )}
              </div>
            ))}
          </div>
        </div>
        {error && <p style={{ color: "#991b1b" }}>{error}</p>}
      </section>

      <section className="card">
        <h3>Agent Timeline</h3>
        {proposalsQuery.isLoading && <p className="muted">Loading proposals...</p>}
        {proposalsQuery.error && (
          <p style={{ color: "#991b1b" }}>
            {proposalsQuery.error instanceof Error ? proposalsQuery.error.message : "Failed to load proposals"}
          </p>
        )}
        <div className="grid" style={{ maxHeight: 560, overflow: "auto" }}>
          {runs.length === 0 && <p className="muted">No timeline entries yet.</p>}
          {runs.map((run) => (
            <div key={run.id} className="card" style={{ marginBottom: 4 }}>
              <div className="row" style={{ justifyContent: "space-between" }}>
                <p style={{ margin: 0, fontWeight: 700 }}>Run: {run.title}</p>
                <p className="muted" style={{ margin: 0 }}>{run.status}</p>
              </div>
              <div className="grid" style={{ marginTop: 8 }}>
                {run.items.map((item) => {
                  const isProposalPending =
                    item.proposalId !== undefined &&
                    pendingProposalIds.has(item.proposalId) &&
                    !resolvedProposals[item.proposalId];
                  const resolved = item.proposalId ? resolvedProposals[item.proposalId] : undefined;

                  return (
                    <div key={item.id} className="card" style={{ marginBottom: 2 }}>
                      <p style={{ margin: "0 0 6px 0", fontWeight: 700 }}>
                        {item.kind === "user" && "You"}
                        {item.kind === "assistant" && "Agent"}
                        {item.kind === "tool_call" && "Tool Call"}
                        {item.kind === "tool_result" && "Tool Result"}
                        {item.kind === "proposal" && `Proposal #${item.proposalId ?? "-"}`}
                        {item.kind === "status" && "Status"}
                        {item.kind === "system" && "System"}
                      </p>
                      <p style={{ margin: "0 0 6px 0" }}>{item.text}</p>
                      {item.payload && <pre>{JSON.stringify(item.payload, null, 2)}</pre>}
                      {isProposalPending && item.proposalId !== undefined && (
                        <div className="row">
                          <button onClick={() => onApprove(item.proposalId!)}>Approve</button>
                          <button className="danger" onClick={() => onReject(item.proposalId!)}>
                            Reject
                          </button>
                        </div>
                      )}
                      {resolved && (
                        <p className="muted" style={{ marginBottom: 0 }}>
                          {resolved === "approved" ? "Approved" : "Rejected"}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
