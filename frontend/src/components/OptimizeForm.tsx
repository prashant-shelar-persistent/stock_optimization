/**
 * OptimizeForm — top-level orchestrator for the portfolio optimization workflow.
 *
 * This component ties together the full optimization lifecycle in a single,
 * self-contained unit:
 *
 *   1. Renders the ConstraintForm (left panel) for user input
 *   2. Tracks the active run_id and opens a WebSocket via useWebSocket
 *   3. Shows the AgentProgressPanel while the run is in progress
 *   4. Shows the ComparisonDashboard when results arrive
 *   5. Shows an empty-state placeholder when no run has been started
 *
 * Layout (responsive):
 *   ┌──────────────────────┬──────────────────────────────────────────┐
 *   │  ConstraintForm      │  Results Panel                           │
 *   │  (sticky sidebar)    │  ┌─────────────────────────────────────┐ │
 *   │                      │  │ AgentProgressPanel (while running)  │ │
 *   │                      │  └─────────────────────────────────────┘ │
 *   │                      │  ┌─────────────────────────────────────┐ │
 *   │                      │  │ ComparisonDashboard (on completion) │ │
 *   │                      │  └─────────────────────────────────────┘ │
 *   └──────────────────────┴──────────────────────────────────────────┘
 *
 * Usage:
 *   <OptimizeForm />
 *
 * The component is intentionally self-contained — it reads all state from
 * uiStore and manages its own run_id lifecycle. No props are required.
 */

import * as React from "react";
import { BarChart3, Wifi, WifiOff, Loader2 } from "lucide-react";

import { ConstraintForm } from "@/components/ConstraintForm";
import { AgentProgressPanel } from "@/components/dashboard/AgentProgressPanel";
import { ComparisonDashboard } from "@/components/dashboard/ComparisonDashboard";

import { useWebSocket } from "@/hooks/useWebSocket";
import { useUIStore } from "@/store/uiStore";
import { cn } from "@/lib/utils";

// ── Connection state badge ────────────────────────────────────────────────────

interface ConnectionBadgeProps {
  state: "connecting" | "open" | "closed" | "error";
}

function ConnectionBadge({ state }: ConnectionBadgeProps) {
  if (state === "closed") return null;

  const config = {
    connecting: {
      icon: <Loader2 className="h-3 w-3 animate-spin" />,
      label: "Connecting…",
      className: "text-muted-foreground",
    },
    open: {
      icon: <Wifi className="h-3 w-3" />,
      label: "Live",
      className: "text-emerald-600 dark:text-emerald-400",
    },
    error: {
      icon: <WifiOff className="h-3 w-3" />,
      label: "Disconnected",
      className: "text-destructive",
    },
  } as const;

  const { icon, label, className } = config[state];

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 text-xs font-medium",
        className,
      )}
      aria-live="polite"
      aria-label={`WebSocket connection: ${label}`}
    >
      {icon}
      {label}
    </span>
  );
}

// ── Empty state ───────────────────────────────────────────────────────────────

function EmptyResultsState() {
  return (
    <div
      className="flex h-64 flex-col items-center justify-center rounded-lg border border-dashed bg-muted/30 px-6 text-center"
      role="status"
      aria-label="No optimization results yet"
    >
      <BarChart3 className="mb-3 h-12 w-12 text-muted-foreground/40" />
      <p className="text-sm font-medium text-muted-foreground">
        Configure constraints and run optimization
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        Classical (Markowitz MVO) + Quantum (QAOA + VQE) results will appear
        here once the agent pipeline completes.
      </p>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export interface OptimizeFormProps {
  /**
   * Additional class names applied to the outer grid container.
   * Useful for overriding max-width or padding from a parent layout.
   */
  className?: string;
}

export function OptimizeForm({ className }: OptimizeFormProps) {
  // ── Run lifecycle state ──────────────────────────────────────────────────

  /**
   * The run_id of the most recently submitted optimization.
   * Passed to useWebSocket so it can open the correct progress socket.
   * Set to null when no run has been started yet.
   */
  const [currentRunId, setCurrentRunId] = React.useState<string | null>(null);

  // ── Global UI state ──────────────────────────────────────────────────────

  const isOptimizing = useUIStore((s) => s.isOptimizing);
  const agentProgress = useUIStore((s) => s.agentProgress);
  const optimizationResult = useUIStore((s) => s.optimizationResult);

  // ── WebSocket ────────────────────────────────────────────────────────────

  /**
   * Opens a WebSocket connection to /ws/runs/{runId}/progress when
   * currentRunId is non-null. Automatically handles reconnection (up to 3
   * retries) and dispatches progress/result/error messages to uiStore.
   */
  const { connectionState } = useWebSocket(currentRunId);

  // ── Callbacks ────────────────────────────────────────────────────────────

  /**
   * Called by ConstraintForm when a new optimization run is successfully
   * submitted. Stores the run_id so useWebSocket can open the socket.
   */
  const handleRunStarted = React.useCallback((runId: string) => {
    setCurrentRunId(runId);
  }, []);

  // ── Derived display flags ────────────────────────────────────────────────

  /** True while a run is in progress (WebSocket open, no result yet). */
  const showProgress = isOptimizing || connectionState === "connecting";

  /** True once a completed result is available. */
  const showResults = !isOptimizing && optimizationResult !== null;

  /** True when neither progress nor results are available. */
  const showEmptyState = !showProgress && !showResults;

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <div
      className={cn(
        "grid grid-cols-1 gap-8 lg:grid-cols-[420px_1fr]",
        className,
      )}
    >
      {/* ── Left: Constraint form (sticky on large screens) ── */}
      <aside className="lg:sticky lg:top-8 lg:self-start">
        <ConstraintForm onRunStarted={handleRunStarted} />
      </aside>

      {/* ── Right: Results panel ── */}
      <section aria-label="Optimization results" className="min-w-0 space-y-6">
        {/* Connection status indicator (only visible while a run is active) */}
        {currentRunId && (
          <div className="flex items-center justify-end">
            <ConnectionBadge state={connectionState} />
          </div>
        )}

        {/* Empty state — shown before any run is submitted */}
        {showEmptyState && <EmptyResultsState />}

        {/* Agent progress panel — shown while the run is in progress */}
        {showProgress && (
          <AgentProgressPanel
            progress={agentProgress}
            isRunning={isOptimizing}
          />
        )}

        {/* Comparison dashboard — shown once the run completes */}
        {showResults && optimizationResult && (
          <ComparisonDashboard result={optimizationResult} />
        )}
      </section>
    </div>
  );
}
