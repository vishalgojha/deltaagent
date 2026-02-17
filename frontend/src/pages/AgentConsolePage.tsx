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

export function AgentConsolePage({ clientId, token }: Props) {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState("");
  const [mode, setModeUi] = useState<"confirmation" | "autonomous">("confirmation");
  const [runs, setRuns] = useState<TimelineRun[]>([]);
  const [expandedToolItems, setExpandedToolItems] = useState<Record<string, boolean>>({});
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

  useEffect(() => {
    setRuns([]);
    setResolvedProposals({});
    setExpandedToolItems({});
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

  function asTimelineFromChat(response: Record<string, unknown>): TimelineItem[] {
    const createdAt = nowIso();
    const items: TimelineItem[] = [];

    if (typeof response.message === "string" && response.message.trim()) {
      items.push({ id: crypto.randomUUID(), kind: "assistant", text: response.message, createdAt });
    }

    const toolCalls = Array.isArray(response.tool_calls) ? response.tool_calls : [];
    for (const call of toolCalls) {
      if (isRecord(call)) {
        items.push({
          id: crypto.randomUUID(),
          kind: "tool_call",
          text: String(call.name ?? "tool_call"),
          payload: call,
          createdAt
        });
      }
    }

    const toolResults = Array.isArray(response.tool_results) ? response.tool_results : [];
    for (const result of toolResults) {
      if (isRecord(result)) {
        items.push({
          id: crypto.randomUUID(),
          kind: "tool_result",
          text: "tool_result",
          payload: result,
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
