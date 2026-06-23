/**
 * Dashboard page — main entry point for the Portfolio Optimizer.
 *
 * Layout:
 *   ┌──────────────────────────────────────────────────────┐
 *   │  Header (nav + title)                                │
 *   ├──────────────────┬───────────────────────────────────┤
 *   │  Constraint Form │  Results Panel                    │
 *   │  (left sidebar)  │  - AgentProgressPanel (running)   │
 *   │                  │  - ComparisonDashboard (complete)  │
 *   │                  │  - Empty state (idle)              │
 *   └──────────────────┴───────────────────────────────────┘
 *                                          ┌─────────────────┐
 *                                          │  ChatAssistant  │  ← fixed bottom-right
 *                                          │  floating panel │
 *                                          └─────────────────┘
 *                                                    [●]  ← FAB toggle
 *
 * State management:
 *   - currentRunId and optimizationResult come from uiStore
 *   - WebSocket is opened via useWebSocket(currentRunId)
 *   - Agent progress events are accumulated in uiStore.agentProgress
 *   - Chat panel state lives in chatStore (toggled by the FAB in ChatAssistant)
 *   - On chat confirmation, ChatAssistant calls uiStore.startNewRun(runId)
 *     which triggers the WebSocket + progress pipeline automatically
 *
 * React 19.2 notes
 * ────────────────
 * • `<title>` rendered inside the component is hoisted to `<head>` by React 19's
 *   built-in document-metadata support — no external helmet library required.
 * • `useOptimistic` provides an instant "Running" badge update the moment the
 *   user submits a run, before the first WebSocket message arrives. The
 *   optimistic value is automatically replaced by real store data as soon as
 *   `isOptimizing` updates from the WebSocket handler.
 * • `useTransition` wraps the "Run History" navigation so the current page
 *   stays fully interactive while the HistoryPage chunk loads in the background.
 * • No `import React` needed — the automatic JSX transform handles it.
 */

import { useNavigate } from "react-router-dom";
import { useOptimistic, useTransition } from "react";
import { BarChart3, History, Wifi, WifiOff, Loader2, BarChart2 } from "lucide-react";
import { useUIStore } from "@/store/uiStore";
import { useOptimize } from "@/hooks/useOptimize";
import { useWebSocket } from "@/hooks/useWebSocket";
import { ConstraintForm } from "@/components/dashboard/ConstraintForm";
import { AgentProgressPanel } from "@/components/dashboard/AgentProgressPanel";
import { ComparisonDashboard } from "@/components/dashboard/ComparisonDashboard";
import { ChatAssistant } from "@/components/chat/ChatAssistant";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// ── Connection status indicator ────────────────────────────────────────────────

function ConnectionBadge({
  state,
}: {
  state: "connecting" | "open" | "closed" | "error";
}) {
  if (state === "closed") return null;

  return (
    <Badge
      variant="outline"
      className={cn(
        "gap-1.5 text-xs",
        state === "open" && "border-green-500/50 text-green-600",
        state === "connecting" && "border-amber-500/50 text-amber-600",
        state === "error" && "border-destructive/50 text-destructive",
      )}
    >
      {state === "open" && <Wifi className="h-3 w-3" />}
      {state === "connecting" && (
        <Loader2 className="h-3 w-3 animate-spin" />
      )}
      {state === "error" && <WifiOff className="h-3 w-3" />}
      {state === "open" ? "Live" : state === "connecting" ? "Connecting…" : "Disconnected"}
    </Badge>
  );
}

// ── Empty state ────────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="flex h-full min-h-[400px] flex-col items-center justify-center rounded-lg border border-dashed bg-muted/20 p-8 text-center">
      <BarChart3 className="mb-4 h-14 w-14 text-muted-foreground/30" />
      <h3 className="text-base font-semibold text-muted-foreground">
        No optimization results yet
      </h3>
      <p className="mt-1.5 max-w-sm text-sm text-muted-foreground/70">
        Configure your portfolio constraints in the form on the left, then click{" "}
        <strong>Run Optimization</strong> to start — or use the{" "}
        <strong>chat assistant</strong> in the bottom-right corner.
      </p>
      <div className="mt-6 flex flex-wrap justify-center gap-3 text-xs text-muted-foreground/60">
        <span className="flex items-center gap-1">
          <span className="h-2 w-2 rounded-full bg-blue-400" />
          Classical (Markowitz MVO)
        </span>
        <span className="flex items-center gap-1">
          <span className="h-2 w-2 rounded-full bg-violet-400" />
          Quantum (QAOA + VQE)
        </span>
        <span className="flex items-center gap-1">
          <span className="h-2 w-2 rounded-full bg-green-400" />
          GPT-4o Explanation
        </span>
      </div>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const navigate = useNavigate();

  // Global state
  const currentRunId = useUIStore((s) => s.currentRunId);
  const wsToken = useUIStore((s) => s.wsToken);
  const isOptimizing = useUIStore((s) => s.isOptimizing);
  const agentProgress = useUIStore((s) => s.agentProgress);
  const optimizationResult = useUIStore((s) => s.optimizationResult);

  // WebSocket — opens when currentRunId is set; wsToken authenticates the connection
  const { connectionState } = useWebSocket(currentRunId, wsToken);

  // Optimize hook — for submit button state
  const { isSubmitting } = useOptimize();

  /**
   * React 19: useTransition wraps the "Run History" navigation so the current
   * page stays fully interactive while the HistoryPage chunk loads.
   * `isNavPending` drives a subtle loading indicator on the nav link.
   */
  const [isNavPending, startNavTransition] = useTransition();

  /**
   * React 19: useOptimistic provides an instant "Running" badge update the
   * moment the user submits a run, before the first WebSocket message arrives.
   *
   * The optimistic value mirrors `isOptimizing` from the store. When the
   * ConstraintForm calls `uiStore.startNewRun(runId)`, the store updates
   * `isOptimizing = true` which React 19 automatically propagates here.
   * The optimistic layer adds a zero-latency visual update for the badge
   * before the store subscription fires.
   */
  const [optimisticIsRunning] = useOptimistic(isOptimizing);

  // Determine what to show in the results panel
  const showProgress =
    optimisticIsRunning || (currentRunId && !optimizationResult);
  const showResults = !optimisticIsRunning && optimizationResult !== null;
  const showEmpty = !showProgress && !showResults;

  function handleNavigateToHistory() {
    startNavTransition(() => {
      navigate("/history");
    });
  }

  return (
    <div className="flex min-h-screen flex-col bg-background">
      {/* React 19: <title> hoisted to <head> automatically */}
      <title>Dashboard | Portfolio Optimizer</title>

      {/* ── Header ── */}
      <header className="sticky top-0 z-40 border-b bg-card/95 px-6 py-3 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between">
          <div className="flex items-center gap-3">
            <BarChart3 className="h-6 w-6 text-primary" />
            <div>
              <h1 className="text-lg font-bold leading-none">
                Portfolio Optimizer
              </h1>
              <p className="text-xs text-muted-foreground">
                Classical + Quantum + Agent-First
              </p>
            </div>
          </div>

          <div className="flex items-center gap-4">
            {/* WebSocket connection status */}
            <ConnectionBadge state={connectionState} />

            <nav>
              {/*
               * React 19: button + startNavTransition keeps the dashboard
               * interactive while the HistoryPage chunk loads in the background.
               */}
              <button
                type="button"
                onClick={handleNavigateToHistory}
                disabled={isNavPending}
                className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors disabled:opacity-60"
              >
                {isNavPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <History className="h-4 w-4" />
                )}
                Run History
              </button>
            </nav>
          </div>
        </div>
      </header>

      {/* ── Main content ── */}
      <main className="flex-1 mx-auto w-full max-w-7xl px-6 py-6">
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[380px_1fr]">
          {/* ── Left: Constraint form ── */}
          <aside className="lg:sticky lg:top-[73px] lg:self-start">
            <div className="rounded-lg border bg-card">
              <div className="border-b px-5 py-4">
                <h2 className="text-base font-semibold">
                  Optimization Constraints
                </h2>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  Configure assets, budget, and risk parameters
                </p>
              </div>
              <ScrollArea className="h-[calc(100vh-230px)]">
                <div className="px-5 py-4">
                  <ConstraintForm />
                </div>
              </ScrollArea>
              {/* ── Sticky submit footer ── */}
              <div className="border-t bg-card px-5 py-3">
                <Button
                  type="submit"
                  form="constraint-form"
                  className="w-full"
                  disabled={isSubmitting || isOptimizing}
                >
                  {isSubmitting ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Submitting…
                    </>
                  ) : isOptimizing ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Running…
                    </>
                  ) : (
                    <>
                      <BarChart2 className="mr-2 h-4 w-4" />
                      Run Optimization
                    </>
                  )}
                </Button>
              </div>
            </div>
          </aside>

          {/* ── Right: Results panel ── */}
          <section className="min-w-0">
            {/* Run ID badge */}
            {currentRunId && (
              <div className="mb-4 flex items-center gap-2">
                <span className="text-xs text-muted-foreground">Run ID:</span>
                <code className="rounded bg-muted px-1.5 py-0.5 text-xs font-mono">
                  {currentRunId}
                </code>
                {/*
                 * React 19: optimisticIsRunning gives an instant "Running" badge
                 * before the first WebSocket event arrives, eliminating the brief
                 * gap between form submit and first progress message.
                 */}
                {optimisticIsRunning && (
                  <Badge variant="outline" className="gap-1 text-xs border-primary/50 text-primary">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    Running
                  </Badge>
                )}
                {!optimisticIsRunning && optimizationResult?.status === "completed" && (
                  <Badge variant="success" className="text-xs">
                    Completed
                  </Badge>
                )}
                {!optimisticIsRunning && optimizationResult?.status === "failed" && (
                  <Badge variant="destructive" className="text-xs">
                    Failed
                  </Badge>
                )}
              </div>
            )}

            {/* Agent progress panel (shown while running) */}
            {showProgress && (
              <div className="mb-6 rounded-lg border bg-card p-5">
                <h3 className="mb-4 text-sm font-semibold">
                  Agent Pipeline Progress
                </h3>
                <AgentProgressPanel
                  progress={agentProgress}
                  isRunning={isOptimizing}
                />
              </div>
            )}

            {/* Error state */}
            {!isOptimizing &&
              optimizationResult?.status === "failed" &&
              optimizationResult.error_message && (
                <div className="mb-6 rounded-lg border border-destructive/30 bg-destructive/5 p-4">
                  <p className="text-sm font-semibold text-destructive">
                    Optimization Failed
                  </p>
                  <p className="mt-1 text-sm text-destructive/80">
                    {optimizationResult.error_message}
                  </p>
                </div>
              )}

            {/* Comparison dashboard (shown when complete) */}
            {showResults && optimizationResult && (
              <ComparisonDashboard result={optimizationResult} />
            )}

            {/* Empty state */}
            {showEmpty && <EmptyState />}
          </section>
        </div>
      </main>

      {/*
       * ── ChatAssistant floating panel ──
       *
       * Rendered outside the main content grid so it can be positioned
       * fixed in the bottom-right corner of the viewport.
       *
       * The ChatAssistant component renders two elements:
       *   1. The sliding chat panel (fixed bottom-20 right-4)
       *   2. The FAB toggle button (fixed bottom-4 right-4)
       *
       * When the user confirms a run via the chat, ChatAssistant calls
       * uiStore.startNewRun(runId) which triggers the WebSocket connection
       * and the AgentProgressPanel above automatically.
       */}
      <ChatAssistant />
    </div>
  );
}
