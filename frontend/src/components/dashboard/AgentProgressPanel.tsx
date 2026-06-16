/**
 * AgentProgressPanel — Real-time display of LangGraph agent node execution.
 *
 * Shows the ordered pipeline of agent nodes with their status:
 *   data_fetch → constraint_validation → classical_optimization →
 *   quantum_dispatch → comparison → frontier_computation → llm_explanation
 *
 * Each node shows:
 *   - Icon + label
 *   - Status indicator (pending / running / completed / failed)
 *   - Progress message from the WebSocket
 *   - Timestamp
 *
 * Props:
 *   progress — ordered list of AgentProgressMessage from uiStore
 *   isRunning — whether the optimization is still in progress
 */

import { cn } from "@/lib/utils";
import { Progress } from "@/components/ui/progress";
import {
  CheckCircle2,
  XCircle,
  Loader2,
  Circle,
  Database,
  ShieldCheck,
  BarChart2,
  Atom,
  GitCompare,
  MessageSquare,
  TrendingUp,
} from "lucide-react";
import type { AgentProgressMessage, AgentNodeName } from "@/types/api";

// ── Node metadata ─────────────────────────────────────────────────────────────

interface NodeMeta {
  label: string;
  description: string;
  Icon: React.ComponentType<{ className?: string }>;
}

const NODE_META: Record<AgentNodeName, NodeMeta> = {
  data_fetch: {
    label: "Data Fetch",
    description: "Fetching live market data via yfinance",
    Icon: Database,
  },
  constraint_validation: {
    label: "Constraint Validation",
    description: "Validating portfolio constraints",
    Icon: ShieldCheck,
  },
  classical_optimization: {
    label: "Classical Optimization",
    description: "Running Markowitz MVO via CVXPY",
    Icon: BarChart2,
  },
  quantum_dispatch: {
    label: "Quantum Optimization",
    description: "Running QAOA (Qiskit) + VQE (PennyLane)",
    Icon: Atom,
  },
  comparison: {
    label: "Comparison",
    description: "Comparing classical vs quantum results",
    Icon: GitCompare,
  },
  frontier_computation: {
    label: "Frontier Computation",
    description: "Computing efficient frontier sweep",
    Icon: TrendingUp,
  },
  llm_explanation: {
    label: "LLM Explanation",
    description: "Generating GPT-4o portfolio explanation",
    Icon: MessageSquare,
  },
};

/** Ordered pipeline steps */
const PIPELINE_ORDER: AgentNodeName[] = [
  "data_fetch",
  "constraint_validation",
  "classical_optimization",
  "quantum_dispatch",
  "comparison",
  "frontier_computation",
  "llm_explanation",
];

// ── Types ─────────────────────────────────────────────────────────────────────

interface AgentProgressPanelProps {
  progress: AgentProgressMessage[];
  isRunning: boolean;
}

type NodeStatus = "pending" | "running" | "completed" | "failed";

interface NodeState {
  status: NodeStatus;
  message: string;
  timestamp: string | null;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function getNodeState(
  node: AgentNodeName,
  progress: AgentProgressMessage[],
): NodeState {
  const events = progress.filter((p) => p.node === node);

  if (events.length === 0) {
    return { status: "pending", message: "", timestamp: null };
  }

  // Check for failure first
  const failedEvent = events.find((e) => e.status === "failed");
  if (failedEvent) {
    return {
      status: "failed",
      message: failedEvent.message,
      timestamp: failedEvent.timestamp,
    };
  }

  // Check for completion
  const completedEvent = events.find((e) => e.status === "completed");
  if (completedEvent) {
    return {
      status: "completed",
      message: completedEvent.message,
      timestamp: completedEvent.timestamp,
    };
  }

  // Started but not yet completed
  const startedEvent = events.find((e) => e.status === "started");
  if (startedEvent) {
    return {
      status: "running",
      message: startedEvent.message,
      timestamp: startedEvent.timestamp,
    };
  }

  return { status: "pending", message: "", timestamp: null };
}

function computeProgress(progress: AgentProgressMessage[]): number {
  const completedCount = PIPELINE_ORDER.filter((node) => {
    const state = getNodeState(node, progress);
    return state.status === "completed";
  }).length;

  return Math.round((completedCount / PIPELINE_ORDER.length) * 100);
}

function formatTimestamp(ts: string): string {
  try {
    return new Date(ts).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return ts;
  }
}

// ── Status icon ───────────────────────────────────────────────────────────────

function StatusIcon({ status }: { status: NodeStatus }) {
  switch (status) {
    case "completed":
      return <CheckCircle2 className="h-4 w-4 text-green-500 flex-shrink-0" />;
    case "failed":
      return <XCircle className="h-4 w-4 text-destructive flex-shrink-0" />;
    case "running":
      return (
        <Loader2 className="h-4 w-4 animate-spin text-primary flex-shrink-0" />
      );
    case "pending":
    default:
      return (
        <Circle className="h-4 w-4 text-muted-foreground/40 flex-shrink-0" />
      );
  }
}

// ── Main component ────────────────────────────────────────────────────────────

export function AgentProgressPanel({
  progress,
  isRunning,
}: AgentProgressPanelProps) {
  const progressPercent = computeProgress(progress);

  return (
    <div className="space-y-4">
      {/* Overall progress bar */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>Agent Pipeline Progress</span>
          <span className="tabular-nums font-medium">{progressPercent}%</span>
        </div>
        <Progress
          value={progressPercent}
          className={cn(
            "h-2",
            isRunning && progressPercent < 100 && "animate-pulse",
          )}
        />
      </div>

      {/* Pipeline steps */}
      <ol className="space-y-2">
        {PIPELINE_ORDER.map((nodeName, index) => {
          const meta = NODE_META[nodeName];
          const state = getNodeState(nodeName, progress);
          const { Icon } = meta;

          return (
            <li
              key={nodeName}
              className={cn(
                "flex items-start gap-3 rounded-md px-3 py-2.5 transition-colors",
                state.status === "running" &&
                  "bg-primary/5 border border-primary/20",
                state.status === "completed" && "opacity-70",
                state.status === "failed" &&
                  "bg-destructive/5 border border-destructive/20",
                state.status === "pending" && "opacity-40",
              )}
            >
              {/* Step number + status icon */}
              <div className="flex flex-col items-center gap-1 pt-0.5">
                <StatusIcon status={state.status} />
                {index < PIPELINE_ORDER.length - 1 && (
                  <div
                    className={cn(
                      "w-px flex-1 min-h-[12px]",
                      state.status === "completed"
                        ? "bg-green-500/30"
                        : "bg-border",
                    )}
                  />
                )}
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <Icon
                    className={cn(
                      "h-3.5 w-3.5 flex-shrink-0",
                      state.status === "running"
                        ? "text-primary"
                        : "text-muted-foreground",
                    )}
                  />
                  <span
                    className={cn(
                      "text-sm font-medium",
                      state.status === "running" && "text-primary",
                      state.status === "failed" && "text-destructive",
                    )}
                  >
                    {meta.label}
                  </span>
                  {state.timestamp && (
                    <span className="ml-auto text-xs text-muted-foreground tabular-nums flex-shrink-0">
                      {formatTimestamp(state.timestamp)}
                    </span>
                  )}
                </div>

                {/* Message */}
                {state.message && (
                  <p
                    className={cn(
                      "mt-0.5 text-xs truncate",
                      state.status === "failed"
                        ? "text-destructive/80"
                        : "text-muted-foreground",
                    )}
                  >
                    {state.message}
                  </p>
                )}

                {/* Description when pending */}
                {state.status === "pending" && (
                  <p className="mt-0.5 text-xs text-muted-foreground/60">
                    {meta.description}
                  </p>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
