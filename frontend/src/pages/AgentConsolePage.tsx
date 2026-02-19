import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  approveProposal,
  getHealth,
  getReadiness,
  getRiskParameters,
  getTrades,
  getStatus,
  getProposals,
  rejectProposal,
  sendChat,
  setMode,
  updateAgentParameters
} from "../api/endpoints";
import { getApiBaseUrl } from "../api/client";
import type { ChatResponse, Trade } from "../types";
import { useAgentStream } from "../hooks/useAgentStream";

type Props = { clientId: string; token: string; isHalted?: boolean; haltReason?: string };

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

type LiveAgentStatus = {
  mode?: string;
  last_action?: string | null;
  healthy?: boolean;
  net_greeks?: Record<string, number>;
};

type LiveGreeks = {
  net_greeks?: Record<string, number>;
  positions?: Array<Record<string, unknown>>;
  updated_at?: string;
};

type ExecutionPhase = "idle" | "preflight_blocked" | "ready" | "executing" | "executed" | "failed";

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

export function AgentConsolePage({ clientId, token, isHalted = false, haltReason = "" }: Props) {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState("");
  const [mode, setModeUi] = useState<"confirmation" | "autonomous">("confirmation");
  const [decisionBackend, setDecisionBackendUi] = useState<"ollama" | "deterministic">("ollama");
  const [runs, setRuns] = useState<TimelineRun[]>([]);
  const [expandedToolItems, setExpandedToolItems] = useState<Record<string, boolean>>({});
  const [expandedWorkflowSteps, setExpandedWorkflowSteps] = useState<Record<string, boolean>>({});
  const [expandedTimelineItems, setExpandedTimelineItems] = useState<Record<string, boolean>>({});
  const [error, setError] = useState("");
  const [selectedProposalId, setSelectedProposalId] = useState<number | null>(null);
  const [executionPhase, setExecutionPhase] = useState<ExecutionPhase>("idle");
  const [executionMessage, setExecutionMessage] = useState("");
  const [lastExecutionTrade, setLastExecutionTrade] = useState<Trade | null>(null);
  const [executionSentAt, setExecutionSentAt] = useState<string | null>(null);
  const [executionResolvedAt, setExecutionResolvedAt] = useState<string | null>(null);
  const [executeConfirmed, setExecuteConfirmed] = useState(false);
  const [showExecuteModal, setShowExecuteModal] = useState(false);
  const [showDebugStream, setShowDebugStream] = useState(false);
  const [activeTab, setActiveTab] = useState<"operate" | "timeline" | "debug">("operate");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [timelineQuery, setTimelineQuery] = useState("");
  const [timelineStatusFilter, setTimelineStatusFilter] = useState<"all" | "running" | "completed">("all");
  const [liveStatus, setLiveStatus] = useState<LiveAgentStatus | null>(null);
  const [liveGreeks, setLiveGreeks] = useState<LiveGreeks | null>(null);
  const [debugEvents, setDebugEvents] = useState<Array<{ id: string; text: string; payload?: Record<string, unknown>; createdAt: string }>>(
    []
  );
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

  const readinessQuery = useQuery({
    queryKey: ["agent-readiness", clientId],
    queryFn: () => getReadiness(clientId),
    refetchInterval: 10000
  });

  const tradesQuery = useQuery({
    queryKey: ["trades", clientId],
    queryFn: () => getTrades(clientId),
    refetchInterval: executionPhase === "executing" ? 3000 : false
  });

  const healthQuery = useQuery({
    queryKey: ["api-health"],
    queryFn: getHealth,
    refetchInterval: 15000
  });

  const parametersQuery = useQuery({
    queryKey: ["agent-parameters", clientId],
    queryFn: () => getRiskParameters(clientId)
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
  const executionBlocked = !!readinessQuery.data && !readinessQuery.data.ready;
  const haltBlocked = isHalted;
  const effectiveBlocked = executionBlocked || haltBlocked;
  const executeGuardMessage =
    haltBlocked
      ? (haltReason || "Trading is globally halted.")
      : executionBlocked
      ? (readinessQuery.data?.last_error || "Execution blocked by readiness checks.")
      : mode === "confirmation" && !executeConfirmed
      ? "Confirm execution checkbox to continue."
      : "";
  const executeBlockedByGuard =
    haltBlocked ||
    executionBlocked ||
    (mode === "confirmation" && !executeConfirmed);
  const pendingProposals = proposalsQuery.data ?? [];
  const selectedProposal = useMemo(
    () => pendingProposals.find((proposal) => proposal.id === selectedProposalId) ?? null,
    [pendingProposals, selectedProposalId]
  );
  const assistantFeed = useMemo(() => {
    const events = runs
      .slice()
      .reverse()
      .flatMap((run) => run.items)
      .filter((item) => item.kind === "user" || item.kind === "assistant" || item.kind === "proposal" || item.kind === "system");
    return events.slice(-18);
  }, [runs]);
  const filteredRuns = useMemo(() => {
    const query = timelineQuery.trim().toLowerCase();
    return runs.filter((run) => {
      if (timelineStatusFilter !== "all" && run.status !== timelineStatusFilter) return false;
      if (!query) return true;
      if (run.title.toLowerCase().includes(query)) return true;
      return run.items.some((item) => item.text.toLowerCase().includes(query) || String(item.proposalId ?? "").includes(query));
    });
  }, [runs, timelineQuery, timelineStatusFilter]);

  useEffect(() => {
    setRuns([]);
    setResolvedProposals({});
    setLiveStatus(null);
    setLiveGreeks(null);
    setDebugEvents([]);
    setExpandedToolItems({});
    setExpandedWorkflowSteps({});
    setExpandedTimelineItems({});
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

  useEffect(() => {
    const backendRaw = (parametersQuery.data?.risk_parameters as Record<string, unknown> | undefined)?.decision_backend;
    if (backendRaw === "deterministic" || backendRaw === "ollama") {
      setDecisionBackendUi(backendRaw);
      return;
    }
    setDecisionBackendUi("ollama");
  }, [parametersQuery.data?.risk_parameters]);

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

  const decisionBackendMutation = useMutation({
    mutationFn: (nextBackend: "ollama" | "deterministic") =>
      updateAgentParameters(clientId, { decision_backend: nextBackend }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["agent-parameters", clientId] });
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

    if (eventType === "agent_status" && isRecord(lastEvent.data)) {
      const eventPayload: Record<string, unknown> = lastEvent.data;
      setLiveStatus(eventPayload);
      if (showDebugStream) {
        setDebugEvents((prev) =>
          [{ id: crypto.randomUUID(), text: eventType, payload: eventPayload, createdAt: nowIso() }, ...prev].slice(0, 50)
        );
      }
      return;
    }
    if (eventType === "greeks" && isRecord(lastEvent.data)) {
      const eventPayload: Record<string, unknown> = lastEvent.data;
      setLiveGreeks(eventPayload);
      if (showDebugStream) {
        setDebugEvents((prev) =>
          [{ id: crypto.randomUUID(), text: eventType, payload: eventPayload, createdAt: nowIso() }, ...prev].slice(0, 50)
        );
      }
      return;
    }

    if (showDebugStream) {
      setDebugEvents((prev) =>
        [{ id: crypto.randomUUID(), text: eventType, payload: isRecord(lastEvent.data) ? lastEvent.data : undefined, createdAt: nowIso() }, ...prev].slice(0, 50)
      );
    }

    appendSystemOutsideRun({
      id: crypto.randomUUID(),
      kind: "status",
      text: eventType,
      payload: isRecord(lastEvent.data) ? lastEvent.data : undefined,
      createdAt: nowIso()
    });
  }, [lastEvent, showDebugStream]);

  useEffect(() => {
    if (!tradesQuery.data || tradesQuery.data.length === 0) return;
    setLastExecutionTrade(tradesQuery.data[0]);
    if (executionPhase === "executing") {
      setExecutionPhase("executed");
      setExecutionResolvedAt(tradesQuery.data[0].timestamp ?? nowIso());
    }
  }, [tradesQuery.data, executionPhase]);

  useEffect(() => {
    if (pendingProposals.length === 0) {
      setSelectedProposalId(null);
      return;
    }
    if (!selectedProposalId || !pendingProposals.some((proposal) => proposal.id === selectedProposalId)) {
      setSelectedProposalId(pendingProposals[0].id);
    }
  }, [pendingProposals, selectedProposalId]);

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
    if (haltBlocked) {
      setError(haltReason || "Trading is globally halted");
      return;
    }
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

  async function onDecisionBackendChange(nextBackend: "ollama" | "deterministic") {
    setError("");
    try {
      await decisionBackendMutation.mutateAsync(nextBackend);
      setDecisionBackendUi(nextBackend);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Engine update failed");
    }
  }

  async function onApprove(id: number) {
    if (effectiveBlocked) {
      setError(haltReason || readinessQuery.data?.last_error || "Execution blocked: readiness checks are failing");
      return;
    }
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

  async function onExecuteSelectedProposal() {
    if (!selectedProposalId) {
      setExecutionPhase("idle");
      setExecutionMessage("No pending proposal selected.");
      return;
    }

    if (mode === "confirmation" && !executeConfirmed) {
      setExecutionPhase("preflight_blocked");
      setExecutionMessage("Confirm execution checkbox to continue.");
      return;
    }

    setExecutionPhase("idle");
    setExecutionMessage("Running preflight checks...");
    setLastExecutionTrade(null);
    setExecutionSentAt(null);
    setExecutionResolvedAt(null);

    const readinessResult = await readinessQuery.refetch();
    const readiness = readinessResult.data;
    if (haltBlocked || !readiness?.ready) {
      setExecutionPhase("preflight_blocked");
      setExecutionMessage(haltReason || readiness?.last_error || "Execution blocked by readiness checks.");
      return;
    }

    try {
      setExecutionPhase("executing");
      setExecutionSentAt(nowIso());
      setExecutionMessage(`Sending Proposal #${selectedProposalId} to broker...`);
      await onApprove(selectedProposalId);

      const trades = await tradesQuery.refetch();
      const latestTrade = trades.data?.[0] ?? null;
      setLastExecutionTrade(latestTrade);
      setExecutionResolvedAt(latestTrade?.timestamp ?? nowIso());
      setExecutionPhase("executed");
      setExecutionMessage(
        latestTrade
          ? `Order sent. Latest status: ${latestTrade.status}${latestTrade.order_id ? ` (Order ${latestTrade.order_id})` : ""}`
          : "Order approval completed. Waiting for broker fill update."
      );
    } catch (err) {
      setExecutionPhase("failed");
      setExecutionMessage(err instanceof Error ? err.message : "Execution failed");
    }
  }

  function openExecuteModal() {
    if (executeBlockedByGuard || !selectedProposalId) return;
    setShowExecuteModal(true);
  }

  async function confirmExecuteFromModal() {
    if (executeBlockedByGuard || approveMutation.isPending || executionPhase === "executing") return;
    setShowExecuteModal(false);
    await onExecuteSelectedProposal();
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

  function formatTs(ts?: string | null): string {
    if (!ts) return "-";
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return ts;
    return d.toLocaleString();
  }

  function mapFillStatus(status?: string | null): "pending" | "partially_filled" | "filled" | "rejected" {
    const raw = String(status ?? "").toLowerCase();
    if (raw.includes("reject") || raw.includes("cancel")) return "rejected";
    if (raw.includes("partial")) return "partially_filled";
    if (raw.includes("fill")) return "filled";
    return "pending";
  }

  function getStepDurationLabel(step: ToolStep): string | null {
    if (typeof step.durationMs === "number") return `${step.durationMs} ms`;
    if (step.input && typeof step.input.duration_ms === "number") return `${step.input.duration_ms} ms`;
    if (step.output && typeof step.output.duration_ms === "number") return `${step.output.duration_ms} ms`;
    return null;
  }

  function summarizeProposalPayload(payload?: Record<string, unknown>): string {
    if (!payload) return "No trade payload";
    const action = payload.action ? String(payload.action) : "-";
    const symbol = payload.symbol ? String(payload.symbol) : "-";
    const qty = payload.qty ?? "-";
    const instrument = payload.instrument ? String(payload.instrument) : "-";
    const orderType = payload.order_type ? String(payload.order_type) : "-";
    return `${action} ${symbol} x${qty} (${instrument}, ${orderType})`;
  }

  useEffect(() => {
    if (!showExecuteModal) return;

    function onModalKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        setShowExecuteModal(false);
        return;
      }
      if (event.key === "Enter") {
        event.preventDefault();
        void confirmExecuteFromModal();
      }
    }

    window.addEventListener("keydown", onModalKeyDown);
    return () => window.removeEventListener("keydown", onModalKeyDown);
  }, [showExecuteModal, executeBlockedByGuard, approveMutation.isPending, executionPhase, selectedProposalId]);

  return (
    <div className="grid">
      <section className="card console-statebar">
        <div className="metric-grid">
          <article className="metric-card">
            <p className="metric-label">Execution</p>
            <p className="metric-value">{effectiveBlocked ? "blocked" : "ready"}</p>
          </article>
          <article className="metric-card">
            <p className="metric-label">Mode</p>
            <p className="metric-value">{liveStatus?.mode ?? statusQuery.data?.mode ?? mode}</p>
          </article>
          <article className="metric-card">
            <p className="metric-label">Engine</p>
            <p className="metric-value">{decisionBackend}</p>
          </article>
          <article className="metric-card">
            <p className="metric-label">WebSocket</p>
            <p className="metric-value">{connected ? "connected" : "disconnected"}</p>
          </article>
        </div>
      </section>

      <section className="card">
        <div className="row">
          <button type="button" className="secondary" onClick={() => setShowAdvanced((prev) => !prev)}>
            {showAdvanced ? "Hide Advanced" : "Show Advanced"}
          </button>
          {showAdvanced && (
            <>
              <button type="button" className={activeTab === "operate" ? "" : "secondary"} onClick={() => setActiveTab("operate")}>
                Operate
              </button>
              <button type="button" className={activeTab === "timeline" ? "" : "secondary"} onClick={() => setActiveTab("timeline")}>
                Timeline
              </button>
              <button
                type="button"
                className={activeTab === "debug" ? "" : "secondary"}
                onClick={() => {
                  setShowDebugStream(true);
                  setActiveTab("debug");
                }}
              >
                Debug
              </button>
            </>
          )}
        </div>
      </section>

      {(activeTab === "operate" || !showAdvanced) && (
        <div className="grid grid-2">
          <section className="card">
        <h3>Trade Assistant</h3>
        <p className="muted">Describe what you want. The system will analyze, propose, and execute only within your safety limits.</p>

        <div className="assistant-chat" style={{ marginTop: 10 }}>
          {assistantFeed.length === 0 && <p className="muted">No conversation yet. Start with a simple request like "Hedge delta to neutral".</p>}
          {assistantFeed.map((item) => (
            <div key={item.id} className={`assistant-bubble ${item.kind}`}>
              <p className="assistant-role">
                {item.kind === "user" ? "You" : item.kind === "assistant" ? "Agent" : item.kind === "proposal" ? "Proposal" : "System"}
              </p>
              <p>{item.kind === "proposal" && item.payload ? summarizeProposalPayload(item.payload) : item.text}</p>
            </div>
          ))}
        </div>

        {pendingProposals.length > 0 && (
          <div className="grid" style={{ marginTop: 12 }}>
            <div className="proposal-quick-card">
              <p style={{ margin: 0, fontWeight: 700 }}>Execute Trade</p>
              <p className="muted" style={{ marginTop: 6 }}>
                Flow: Select proposal, run preflight, execute, then track broker status.
              </p>
              <div className="row" style={{ marginTop: 8 }}>
                <label>
                  Proposal
                  <select
                    style={{ marginLeft: 8 }}
                    value={selectedProposalId ?? ""}
                    onChange={(event) => setSelectedProposalId(Number(event.target.value))}
                  >
                    {pendingProposals.map((proposal) => (
                      <option key={proposal.id} value={proposal.id}>
                        #{proposal.id} {summarizeProposalPayload(proposal.trade_payload)}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  type="button"
                  className="secondary"
                  disabled={haltBlocked}
                  onClick={async () => {
                    const readiness = await readinessQuery.refetch();
                    if (!readiness.data?.ready || haltBlocked) {
                      setExecutionPhase("preflight_blocked");
                      setExecutionMessage(haltReason || readiness.data?.last_error || "Execution blocked by readiness checks.");
                      return;
                    }
                    setExecutionPhase("ready");
                    setExecutionMessage("Preflight passed. Ready to execute.");
                  }}
                >
                  Run Preflight
                </button>
                <button
                  type="button"
                  disabled={
                    executeBlockedByGuard ||
                    !selectedProposalId ||
                    approveMutation.isPending ||
                    executionPhase === "executing"
                  }
                  onClick={openExecuteModal}
                >
                  {executionPhase === "executing" ? "Executing..." : "Execute Trade"}
                </button>
              </div>
              {mode === "confirmation" && (
                <label className="row" style={{ marginTop: 4 }}>
                  <input
                    type="checkbox"
                    checked={executeConfirmed}
                    onChange={(event) => setExecuteConfirmed(event.target.checked)}
                  />
                  <span className="muted">I confirm this trade execution</span>
                </label>
              )}
              <div className="row" style={{ marginTop: 8 }}>
                <span className="muted">Preflight: {executionBlocked ? "blocked" : "pass"}</span>
                <span className="muted">Broker: {String(readinessQuery.data?.connected ?? "-")}</span>
                <span className="muted">Market Data: {String(readinessQuery.data?.market_data_ok ?? "-")}</span>
                <span className="muted">Risk: {readinessQuery.data?.risk_blocked ? "blocked" : "pass"}</span>
              </div>
              {executeGuardMessage && (
                <p style={{ color: "#991b1b", marginTop: 4 }}>{executeGuardMessage}</p>
              )}
              {executionMessage && <p className="muted" style={{ marginTop: 8 }}>{executionMessage}</p>}
              <div className="row" style={{ marginTop: 4 }}>
                {(() => {
                  const fillStatus = mapFillStatus(lastExecutionTrade?.status);
                  const pendingActive = executionPhase === "idle" || executionPhase === "ready" || executionPhase === "preflight_blocked";
                  const sentActive = executionPhase === "executing" || executionPhase === "executed";
                  const partialActive = fillStatus === "partially_filled";
                  const filledActive = fillStatus === "filled";
                  const rejectedActive = executionPhase === "failed" || fillStatus === "rejected";
                  return (
                    <div className="grid" style={{ width: "100%" }}>
                      <div className="row">
                        <span className="muted">Lifecycle:</span>
                        <span className={`lifecycle-chip ${pendingActive ? "active pending" : ""}`}>Pending</span>
                        <span className={`lifecycle-chip ${sentActive ? "active sent" : ""}`}>Sent to broker</span>
                        <span className={`lifecycle-chip ${partialActive ? "active partial" : ""}`}>Partially filled</span>
                        <span className={`lifecycle-chip ${filledActive ? "active filled" : ""}`}>Filled</span>
                        <span className={`lifecycle-chip ${rejectedActive ? "active rejected" : ""}`}>Rejected</span>
                      </div>
                      <div className="row">
                        <span className="muted">Sent At: {formatTs(executionSentAt)}</span>
                        <span className="muted">Resolved At: {formatTs(executionResolvedAt)}</span>
                        <span className="muted">Status: {lastExecutionTrade?.status ?? "-"}</span>
                        {lastExecutionTrade?.order_id && <span className="muted">Order: {lastExecutionTrade.order_id}</span>}
                        {lastExecutionTrade?.fill_price !== null && lastExecutionTrade?.fill_price !== undefined && (
                          <span className="muted">Avg Fill: {lastExecutionTrade.fill_price}</span>
                        )}
                      </div>
                    </div>
                  );
                })()}
              </div>
            </div>
            <p style={{ margin: 0, fontWeight: 700 }}>Pending Decisions</p>
            {pendingProposals.map((proposal) => (
              <div key={proposal.id} className="proposal-quick-card">
                <p style={{ margin: 0, fontWeight: 700 }}>Proposal #{proposal.id}</p>
                <p className="muted">{summarizeProposalPayload(proposal.trade_payload)}</p>
                <div className="row">
                  <button disabled={effectiveBlocked} onClick={() => onApprove(proposal.id)}>
                    Approve Proposal
                  </button>
                  <button className="danger" onClick={() => onReject(proposal.id)}>
                    Reject Proposal
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="row" style={{ marginTop: 12 }}>
          <button type="submit" form="simple-trade-form" disabled={haltBlocked || sendChatMutation.isPending}>
            {sendChatMutation.isPending ? "Running..." : "Send"}
          </button>
          <span className="muted">
            {mode === "confirmation"
              ? "Confirmation mode: proposal will require Approve."
              : "Autonomous mode: agent may execute directly if allowed."}
          </span>
        </div>

        <form id="simple-trade-form" onSubmit={onSend} className="grid" style={{ marginTop: 10 }}>
          <textarea
            rows={3}
            placeholder="Ask the agent..."
            value={message}
            onChange={(e) => setMessage(e.target.value)}
          />
        </form>

        {showAdvanced && (
        <div style={{ marginTop: 14, borderTop: "1px solid rgba(148,163,184,0.25)", paddingTop: 12 }}>
        <h3>Agent Controls</h3>
        <div className="row">
          <button className="secondary" onClick={() => onModeChange("confirmation")}>
            Confirmation
          </button>
          <button onClick={() => onModeChange("autonomous")}>Autonomous</button>
          <span className="muted">Current: {mode}</span>
          <label>
            Engine
            <select
              style={{ marginLeft: 8 }}
              value={decisionBackend}
              onChange={(e) => onDecisionBackendChange(e.target.value as "ollama" | "deterministic")}
            >
              <option value="ollama">Ollama (Default)</option>
              <option value="deterministic">Deterministic Logic</option>
            </select>
          </label>
          <span className="muted">WS: {connected ? "connected" : "disconnected"}</span>
          <label className="row" style={{ marginLeft: "auto" }}>
            <input type="checkbox" checked={showDebugStream} onChange={(e) => setShowDebugStream(e.target.checked)} />
            Debug stream
          </label>
        </div>
        <div className="card" style={{ marginTop: 10, marginBottom: 0 }}>
          <p style={{ margin: "0 0 6px 0", fontWeight: 700 }}>System Health</p>
          <div className="row">
            <span className="muted">API: {getApiBaseUrl()}</span>
            <span className="muted">Backend: {healthQuery.isError ? "unreachable" : (healthQuery.data?.status ?? "checking...")}</span>
            <span className="muted">Agent healthy: {String(liveStatus?.healthy ?? statusQuery.data?.healthy ?? "-")}</span>
            <span className="muted">Mode: {liveStatus?.mode ?? statusQuery.data?.mode ?? mode}</span>
            <span className="muted">WS: {connected ? "connected" : "disconnected"}</span>
          </div>
        </div>
        <div className="card" style={{ marginTop: 10, marginBottom: 0 }}>
          <p style={{ margin: "0 0 6px 0", fontWeight: 700 }}>Execution Readiness</p>
          <div className="row">
            <span className="muted">
              Ready:{" "}
              {readinessQuery.isLoading
                ? "checking..."
                : readinessQuery.isError
                  ? "unavailable"
                  : readinessQuery.data?.ready
                    ? "yes"
                    : "no"}
            </span>
            <span className="muted">Broker: {String(readinessQuery.data?.connected ?? "-")}</span>
            <span className="muted">Market Data: {String(readinessQuery.data?.market_data_ok ?? "-")}</span>
            <span className="muted">Risk Blocked: {String(readinessQuery.data?.risk_blocked ?? "-")}</span>
          </div>
          {(effectiveBlocked || readinessQuery.isError) && (
            <p style={{ color: "#991b1b", margin: "6px 0 0 0" }}>
              {haltBlocked
                ? (haltReason || "Trading is globally halted.")
                : readinessQuery.isError
                ? "Execution checks unavailable. Fix readiness before approving trades."
                : (readinessQuery.data?.last_error || "Execution blocked by readiness checks.")}
            </p>
          )}
        </div>
        <p className="muted" style={{ marginTop: 8, marginBottom: 0 }}>
          Tip: For higher-quality reasoning, OpenAI or Anthropic models usually perform better than local models.
        </p>
        <div className="card" style={{ marginTop: 10, marginBottom: 0 }}>
          <p style={{ margin: "0 0 6px 0", fontWeight: 700 }}>Live Status</p>
          <div className="row">
            <span className="muted">Mode: {liveStatus?.mode ?? mode}</span>
            <span className="muted">Healthy: {String(liveStatus?.healthy ?? statusQuery.data?.healthy ?? "-")}</span>
            <span className="muted">Last Action: {String(liveStatus?.last_action ?? statusQuery.data?.last_action ?? "none")}</span>
          </div>
          <p className="muted" style={{ margin: "6px 0 0 0" }}>
            Net Greeks: {JSON.stringify(liveGreeks?.net_greeks ?? liveStatus?.net_greeks ?? statusQuery.data?.net_greeks ?? {})}
          </p>
        </div>
        <div className="row" style={{ marginTop: 8 }}>
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
              <div key={item.id} className="card" style={{ minWidth: 0, flex: "1 1 220px", margin: 0 }}>
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
        </div>
        )}
        {!showAdvanced && error && <p style={{ color: "#991b1b", marginTop: 8 }}>{error}</p>}
      </section>

      {showAdvanced && (
      <section className="card">
        <h3>Recent Timeline</h3>
        <p className="muted">Most recent runs. Open Timeline tab for full history and filters.</p>
        {proposalsQuery.isLoading && <p className="muted">Loading proposals...</p>}
        {proposalsQuery.error && (
          <p style={{ color: "#991b1b" }}>
            {proposalsQuery.error instanceof Error ? proposalsQuery.error.message : "Failed to load proposals"}
          </p>
        )}
        <div className="grid" style={{ maxHeight: 560, overflow: "auto", marginTop: 8 }}>
          {runs.length === 0 && <p className="muted">No timeline entries yet.</p>}
          {runs.slice(0, 5).map((run) => (
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
                      {item.kind === "proposal" && item.payload && (
                        <p className="muted" style={{ marginBottom: 6 }}>
                          {summarizeProposalPayload(item.payload)}
                        </p>
                      )}
                      {item.payload && (
                        <>
                          <button
                            type="button"
                            className="secondary"
                            onClick={() =>
                              setExpandedTimelineItems((prev) => ({
                                ...prev,
                                [item.id]: !prev[item.id]
                              }))
                            }
                          >
                            {expandedTimelineItems[item.id] ? "Hide payload" : "Show payload"}
                          </button>
                          {expandedTimelineItems[item.id] && <pre style={{ marginTop: 8 }}>{JSON.stringify(item.payload, null, 2)}</pre>}
                        </>
                      )}
                      {isProposalPending && item.proposalId !== undefined && (
                        <div className="row">
                          <button disabled={effectiveBlocked} onClick={() => onApprove(item.proposalId!)}>
                            Approve
                          </button>
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
      )}
        </div>
      )}

      {showAdvanced && activeTab === "timeline" && (
        <section className="card">
          <h3>Agent Timeline</h3>
          <div className="row" style={{ marginBottom: 8 }}>
            <input
              placeholder="Search run/proposal text"
              value={timelineQuery}
              onChange={(e) => setTimelineQuery(e.target.value)}
              style={{ maxWidth: 280 }}
            />
            <select
              value={timelineStatusFilter}
              onChange={(e) => setTimelineStatusFilter(e.target.value as "all" | "running" | "completed")}
              style={{ maxWidth: 160 }}
            >
              <option value="all">All statuses</option>
              <option value="running">Running</option>
              <option value="completed">Completed</option>
            </select>
          </div>
          <div className="grid" style={{ maxHeight: 700, overflow: "auto" }}>
            {filteredRuns.length === 0 && <p className="muted">No timeline entries yet.</p>}
            {filteredRuns.map((run) => (
              <div key={run.id} className="card" style={{ marginBottom: 4 }}>
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <p style={{ margin: 0, fontWeight: 700 }}>Run: {run.title}</p>
                  <p className="muted" style={{ margin: 0 }}>{run.status}</p>
                </div>
                <div className="grid" style={{ marginTop: 8 }}>
                  {run.items.map((item) => (
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
                      {item.kind === "proposal" && item.payload && (
                        <p className="muted" style={{ marginBottom: 6 }}>
                          {summarizeProposalPayload(item.payload)}
                        </p>
                      )}
                      {item.payload && (
                        <>
                          <button
                            type="button"
                            className="secondary"
                            onClick={() =>
                              setExpandedTimelineItems((prev) => ({
                                ...prev,
                                [item.id]: !prev[item.id]
                              }))
                            }
                          >
                            {expandedTimelineItems[item.id] ? "Hide payload" : "Show payload"}
                          </button>
                          {expandedTimelineItems[item.id] && <pre style={{ marginTop: 8 }}>{JSON.stringify(item.payload, null, 2)}</pre>}
                        </>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {showAdvanced && activeTab === "debug" && (
        <section className="card">
          <h3>Debug Stream Events</h3>
          <p className="muted">Tool traces and websocket payloads for diagnostics.</p>
          <div style={{ marginTop: 12 }}>
            <p style={{ margin: "0 0 6px 0", fontWeight: 700 }}>Tool Execution</p>
            {toolStripItems.length === 0 && <p className="muted" style={{ margin: 0 }}>No tool calls in current run.</p>}
            <div className="row" style={{ alignItems: "flex-start" }}>
              {toolStripItems.map((item) => (
                <div key={item.id} className="card" style={{ minWidth: 0, flex: "1 1 220px", margin: 0 }}>
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
          <div className="grid" style={{ maxHeight: 420, overflow: "auto", marginTop: 10 }}>
            {debugEvents.length === 0 && <p className="muted">No stream events captured yet.</p>}
            {debugEvents.map((event) => (
              <div key={event.id} className="card" style={{ marginBottom: 2 }}>
                <p style={{ margin: "0 0 6px 0", fontWeight: 700 }}>{event.text}</p>
                {event.payload && <pre>{JSON.stringify(event.payload, null, 2)}</pre>}
              </div>
            ))}
          </div>
        </section>
      )}

      {showExecuteModal && selectedProposal && (
        <div className="modal-overlay" role="dialog" aria-modal="true" aria-label="Trade Ticket Confirmation">
          <section className="modal-card">
            <h3 style={{ marginBottom: 8 }}>Trade Ticket</h3>
            <p className="muted">Review once before sending to broker.</p>
            <div className="grid" style={{ marginTop: 10 }}>
              <p><strong>Proposal:</strong> #{selectedProposal.id}</p>
              <p><strong>Trade:</strong> {summarizeProposalPayload(selectedProposal.trade_payload)}</p>
              <p><strong>Mode:</strong> {mode}</p>
              <p><strong>Readiness:</strong> {readinessQuery.data?.ready ? "PASS" : "BLOCKED"}</p>
              <p><strong>Broker:</strong> {String(readinessQuery.data?.connected ?? "-")}</p>
              <p><strong>Market Data:</strong> {String(readinessQuery.data?.market_data_ok ?? "-")}</p>
            </div>
            {executeGuardMessage && <p style={{ color: "#991b1b", marginTop: 10 }}>{executeGuardMessage}</p>}
            <div className="row" style={{ marginTop: 12, justifyContent: "flex-end" }}>
              <button type="button" className="secondary" onClick={() => setShowExecuteModal(false)}>
                Cancel
              </button>
              <button
                type="button"
                disabled={executeBlockedByGuard || approveMutation.isPending || executionPhase === "executing"}
                onClick={confirmExecuteFromModal}
              >
                Confirm Execute
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
