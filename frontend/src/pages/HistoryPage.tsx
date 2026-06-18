/**
 * History page — displays past optimization runs in a paginated table.
 *
 * Renders the `RunHistory` component which handles:
 *   - Paginated table of runs (status, tickers, budget, Sharpe ratios, date, actions)
 *   - Loading skeletons, empty state, and error state
 *   - Pagination controls
 *
 * React 19.2 notes
 * ────────────────
 * • `<title>` rendered inside the component is hoisted to `<head>` by React 19's
 *   built-in document-metadata support — no external helmet library required.
 * • `useTransition` wraps the "New Optimization" navigation intent so React 19's
 *   concurrent scheduler can keep the current page interactive while the
 *   DashboardPage chunk loads in the background.
 * • No `import React` needed — the automatic JSX transform handles it.
 */

import { Link, useNavigate } from "react-router-dom";
import { useTransition } from "react";
import { ArrowLeft, BarChart3, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { RunHistory } from "@/components/RunHistory";

// ── Main page ──────────────────────────────────────────────────────────────────

export default function HistoryPage() {
  const navigate = useNavigate();

  /**
   * React 19: useTransition marks the navigation as a non-urgent update so
   * the current page stays fully interactive while the next page's JS chunk
   * is being fetched. `isPending` drives the button's loading indicator.
   */
  const [isPending, startTransition] = useTransition();

  function handleNewOptimization() {
    startTransition(() => {
      navigate("/");
    });
  }

  return (
    <div className="min-h-screen bg-background">
      {/* React 19: <title> hoisted to <head> automatically */}
      <title>Run History | Portfolio Optimizer</title>

      {/* ── Header ── */}
      <header className="border-b bg-card px-6 py-4">
        <div className="mx-auto flex max-w-7xl items-center justify-between">
          <div className="flex items-center gap-3">
            <BarChart3 className="h-7 w-7 text-primary" />
            <div>
              <h1 className="text-xl font-bold leading-none">
                Portfolio Optimizer
              </h1>
              <p className="text-xs text-muted-foreground">
                Classical + Quantum + Agent-First
              </p>
            </div>
          </div>
          <nav>
            <Link
              to="/"
              className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              <ArrowLeft className="h-4 w-4" />
              Back to Dashboard
            </Link>
          </nav>
        </div>
      </header>

      {/* ── Main content ── */}
      <main className="mx-auto max-w-7xl px-6 py-8">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold">Optimization Run History</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              View and compare past optimization runs
            </p>
          </div>

          {/*
           * React 19: The button triggers a transition so the navigation to "/"
           * is treated as a non-urgent update. isPending shows a spinner while
           * the DashboardPage chunk is loading.
           */}
          <Button
            size="sm"
            onClick={handleNewOptimization}
            disabled={isPending}
          >
            {isPending ? (
              <>
                <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
                Loading…
              </>
            ) : (
              "New Optimization"
            )}
          </Button>
        </div>

        {/* Run history table */}
        <RunHistory />
      </main>
    </div>
  );
}
