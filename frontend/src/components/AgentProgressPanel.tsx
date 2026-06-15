/**
 * AgentProgressPanel — Real-time progress tracker for optimization runs.
 *
 * Displays the live status of each LangGraph agent node as the optimization
 * pipeline executes. Progress events are streamed via WebSocket and stored
 * in the Zustand UI store.
 *
 * Features:
 *   - Ordered list of agent pipeline steps with status icons
 *   - Animated progress bar showing overall pipeline completion
 *   - Per-step timestamps and descriptive messages
 *   - WebSocket connection state indicator (connecting / open / closed / error)
 *   - Graceful empty/idle state when no run is active
 *   - Auto-scrolls to the latest event
 *
 * Props:
 *   runId           — The active run ID (null when idle)
 *   connectionState — Current WebSocket connection state from useWebSocket
 */

import { useEffect, useRef, type ComponentType } from "react";
import {
  CheckCircle2,
  XCircle,
  Loader2,
  Circle,
  Wifi,
  WifiOff,
  AlertTriangle,
  Activity,
  Database,
  ShieldCheck,
  TrendingUp,
  Atom,
  GitCompare,
  MessageSquare,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { useUIStore, selectAgentProgress } from "@/store/uiStore";
import type { AgentNodeName, AgentProgressMessage } from "@/types/api";
import type { ConnectionState } from "@/hooks/useWebSocket";

// ── Agent node metadata ────────────────────────────────────────────────────────

/**
 * Ordered list of all agent pipeline nodes.
 * The order here defines the visual sequence in the progress tracker.
 */
const PIPELINE_NODES: {
  name: AgentNodeName;
  label: string;
  description: string;
  Icon: ComponentType<{ className?: string }>;
}[] = [
  {
    name: "data_fetch",
    label: "Data Fetch",
    description: "Fetching live market prices via yfinance",
    Icon: Database,
  },
  {
    name: "constraint_validation",
    label: "Constraint Validation",
    description: "Validating portfolio constraints and parameters",
    Icon: ShieldCheck,
  },
  {
    name: "classical_optimization",
    label: "Classical Optimization",
    description: "Running Markowitz Mean-Variance via CVXPY",
    Icon: TrendingUp,
  },
  {
    name: "quantum_dispatch",
    label: "Quantum Optimization",
    description: "Running QAOA (Qiskit) and VQE (PennyLane) solvers",
    Icon: Atom,
  },
  {
    name: "comparison",
    label: "Comparison",
    description: "Comparing classical vs quantum portfolio metrics",
    Icon: GitCompare,
  },
  {
    name: "llm_explanation",
    label: "LLM Explanation",
    description: "Generating natural-language explanation via GPT-4o",
    Icon: MessageSquare,
  },
];

const TOTAL_STEPS = PIPELINE_NODES.length;

// ── Helper utilities ───────────────────────────────────────────────────────────

/**
 * Compute the overall pipeline progress percentage (0–100) from the list of
 * received progress events.
 *
 * Each node contributes equally. A "completed" event for a node counts as a
 * full step; a "started" event counts as half a step.
 */
function computeProgress(events: AgentProgressMessage[]): number {
  if (events.length === 0) return 0;

  // Build a map of node → best status seen so far
  const nodeStatus = new Map<AgentNodeName, "started" | "completed" | "failed">();
  for (const event of events) {
    const current = nodeStatus.get(event.node);
    // "completed" > "failed" > "started" in terms of progress weight
    if (!current || event.status === "completed") {
      nodeStatus.set(event.node, event.status);
    } else if (event.status === "failed" && current === "started") {
      nodeStatus.set(event.node, event.status);
    }
  }

  let score = 0;
  for (const status of nodeStatus.values()) {
    if (status === "completed") score += 1;
    else if (status === "started") score += 0.5;
    // "failed" counts as 0 additional progress beyond what was started
  }

  return Math.min(100, Math.round((score / TOTAL_STEPS) * 100));
}

/**
 * Determine the display status of a pipeline node given the received events.
 */
function getNodeStatus(
  nodeName: AgentNodeName,
  events: AgentProgressMessage[],
): "idle" | "running" | "completed" | "failed" {
  const nodeEvents = events.filter((e) => e.node === nodeName);
  if (nodeEvents.length === 0) return "idle";

  // Check for terminal states first
  if (nodeEvents.some((e) => e.status === "failed")) return "failed";
  if (nodeEvents.some((e) => e.status === "completed")) return "completed";
  return "running";
}

/**
 * Get the most recent message for a given node.
 */
function getLatestMessage(
  nodeName: AgentNodeName,
  events: AgentProgressMessage[],
): AgentProgressMessage | undefined {
  const nodeEvents = events.filter((e) => e.node === nodeName);
  return nodeEvents[nodeEvents.length - 1];
}

/**
 * Format an ISO timestamp to a human-readable time string.
 */
function formatTimestamp(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

// ── Sub-components ─────────────────────────────────────────────────────────────

interface ConnectionIndicatorProps {
  state: ConnectionState;
}

function ConnectionIndicator({ state }: ConnectionIndicatorProps) {
  const config = {
    connecting: {
      icon: <Loader2 className="h-3.5 w-3.5 animate-spin" />,
      label: "Connecting…",
      className: "text-yellow-600 dark:text-yellow-400",
    },
    open: {
      icon: <Wifi className="h-3.5 w-3.5" />,
      label: "Live",
      className: "text-green-600 dark:text-green-400",
    },
    closed: {
      icon: <WifiOff className="h-3.5 w-3.5" />,
      label: "Disconnected",
      className: "text-muted-foreground",
    },
    error: {
      icon: <AlertTriangle className="h-3.5 w-3.5" />,
      label: "Connection error",
      className: "text-destructive",
    },
  } as const;

  const { icon, label, className } = config[state];

  return (
    <span className={cn("flex items-center gap-1 text-xs font-medium", className)}>
      {icon}
      {label}
    </span>
  );
}

// ── Step row ───────────────────────────────────────────────────────────────────

interface StepRowProps {
  nodeName: AgentNodeName;
  label: string;
  description: string;
  Icon: ComponentType<{ className?: string }>;
  status: "idle" | "running" | "completed" | "failed";
  latestEvent?: AgentProgressMessage;
  isLast: boolean;
}

function StepRow({
  label,
  description,
  Icon,
  status,
  latestEvent,
  isLast,
}: StepRowProps) {
  const statusConfig = {
    idle: {
      icon: <Circle className="h-5 w-5 text-muted-foreground/40" />,
      rowClass: "opacity-50",
      badgeVariant: "outline" as const,
      badgeLabel: "Pending",
    },
    running: {
      icon: (
        <Loader2 className="h-5 w-5 animate-spin text-primary" />
      ),
      rowClass: "",
      badgeVariant: "default" as const,
      badgeLabel: "Running",
    },
    completed: {
      icon: <CheckCircle2 className="h-5 w-5 text-green-500 dark:text-green-400" />,
      rowClass: "",
      badgeVariant: "success" as const,
      badgeLabel: "Done",
    },
    failed: {
      icon: <XCircle className="h-5 w-5 text-destructive" />,
      rowClass: "",
      badgeVariant: "destructive" as const,
      badgeLabel: "Failed",
    },
  };

  const { icon, rowClass, badgeVariant, badgeLabel } = statusConfig[status];

  return (
    <div className={cn("flex gap-3", rowClass)}>
      {/* Left: connector line + status icon */}
      <div className="flex flex-col items-center">
        <div className="mt-0.5 flex-shrink-0">{icon}</div>
        {!isLast && (
          <div
            className={cn(
              "mt-1 w-px flex-1",
              status === "completed"
                ? "bg-green-500/40 dark:bg-green-400/30"
                : "bg-border",
            )}
            style={{ minHeight: "1.5rem" }}
          />
        )}
      </div>

      {/* Right: content */}
      <div className="min-w-0 flex-1 pb-4">
        <div className="flex flex-wrap items-center gap-2">
          <Icon
            className={cn(
              "h-4 w-4 flex-shrink-0",
              status === "idle"
                ? "text-muted-foreground/40"
                : status === "running"
                  ? "text-primary"
                  : status === "completed"
                    ? "text-green-500 dark:text-green-400"
                    : "text-destructive",
            )}
          />
          <span
            className={cn(
              "text-sm font-medium",
              status === "idle" && "text-muted-foreground",
            )}
          >
            {label}
          </span>
          <Badge variant={badgeVariant} className="text-[10px] px-1.5 py-0">
            {badgeLabel}
          </Badge>
          {latestEvent && (
            <span className="ml-auto text-[10px] text-muted-foreground tabular-nums">
              {formatTimestamp(latestEvent.timestamp)}
            </span>
          )}
        </div>

        {/* Message from the latest event, or default description */}
        <p
          className={cn(
            "mt-0.5 text-xs leading-relaxed",
            status === "idle"
              ? "text-muted-foreground/50"
              : "text-muted-foreground",
          )}
        >
          {latestEvent?.message ?? description}
        </p>
      </div>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export interface AgentProgressPanelProps {
  /** The active optimization run ID. Null when no run is in progress. */
  runId: string | null;
  /** Current WebSocket connection state. */
  connectionState: ConnectionState;
  /** Optional additional CSS classes. */
  className?: string;
}

export function AgentProgressPanel({
  runId,
  connectionState,
  className,
}: AgentProgressPanelProps) {
  const agentProgress = useUIStore(selectAgentProgress);
  const isOptimizing = useUIStore((s) => s.isOptimizing);

  const scrollBottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to the latest event whenever new progress arrives
  useEffect(() => {
    if (scrollBottomRef.current) {
      scrollBottomRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [agentProgress.length]);

  const progress = computeProgress(agentProgress);

  // Count completed steps for the subtitle
  const completedCount = PIPELINE_NODES.filter(
    (n) => getNodeStatus(n.name, agentProgress) === "completed",
  ).length;

  const hasAnyProgress = agentProgress.length > 0;
  const isIdle = !runId && !hasAnyProgress;

  return (
    <Card className={cn("flex flex-col", className)}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Activity className="h-5 w-5 text-primary" />
            <CardTitle className="text-base">Agent Pipeline</CardTitle>
          </div>
          {runId && (
            <ConnectionIndicator state={connectionState} />
          )}
        </div>

        {/* Run ID badge */}
        {runId && (
          <p className="text-xs text-muted-foreground">
            Run{" "}
            <span className="font-mono font-medium text-foreground">
              {runId.slice(0, 8)}…
            </span>
          </p>
        )}

        {/* Progress bar */}
        {(isOptimizing || hasAnyProgress) && (
          <div className="mt-2 space-y-1">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>
                {completedCount} / {TOTAL_STEPS} steps completed
              </span>
              <span className="tabular-nums font-medium">{progress}%</span>
            </div>
            <Progress
              value={progress}
              className={cn(
                "h-1.5",
                progress === 100
                  ? "[&>div]:bg-green-500"
                  : isOptimizing
                    ? "[&>div]:bg-primary"
                    : "[&>div]:bg-muted-foreground",
              )}
            />
          </div>
        )}
      </CardHeader>

      <Separator />

      <CardContent className="flex-1 p-0">
        {isIdle ? (
          /* ── Idle / empty state ── */
          <div className="flex flex-col items-center justify-center gap-3 px-6 py-10 text-center">
            <div className="rounded-full bg-muted p-3">
              <Activity className="h-6 w-6 text-muted-foreground" />
            </div>
            <div>
              <p className="text-sm font-medium text-muted-foreground">
                No active run
              </p>
              <p className="mt-0.5 text-xs text-muted-foreground/70">
                Submit an optimization to see live agent progress here.
              </p>
            </div>
          </div>
        ) : (
          /* ── Pipeline steps ── */
          <ScrollArea className="h-full max-h-[480px]">
            <div className="px-6 py-4">
              {PIPELINE_NODES.map((node, index) => {
                const status = getNodeStatus(node.name, agentProgress);
                const latestEvent = getLatestMessage(node.name, agentProgress);
                return (
                  <StepRow
                    key={node.name}
                    nodeName={node.name}
                    label={node.label}
                    description={node.description}
                    Icon={node.Icon}
                    status={status}
                    latestEvent={latestEvent}
                    isLast={index === PIPELINE_NODES.length - 1}
                  />
                );
              })}
              {/* Sentinel element for auto-scroll */}
              <div ref={scrollBottomRef} />
            </div>
          </ScrollArea>
        )}
      </CardContent>

      {/* Footer: completion summary */}
      {!isIdle && !isOptimizing && hasAnyProgress && (
        <>
          <Separator />
          <div className="px-6 py-3">
            {agentProgress.some((e) => e.status === "failed") ? (
              <div className="flex items-center gap-2 text-xs text-destructive">
                <XCircle className="h-4 w-4 flex-shrink-0" />
                <span>
                  Pipeline encountered an error. Check the toast notification for
                  details.
                </span>
              </div>
            ) : progress === 100 ? (
              <div className="flex items-center gap-2 text-xs text-green-600 dark:text-green-400">
                <CheckCircle2 className="h-4 w-4 flex-shrink-0" />
                <span>All steps completed successfully.</span>
              </div>
            ) : (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Circle className="h-4 w-4 flex-shrink-0" />
                <span>Pipeline stopped at {completedCount} of {TOTAL_STEPS} steps.</span>
              </div>
            )}
          </div>
        </>
      )}
    </Card>
  );
}

export default AgentProgressPanel;
