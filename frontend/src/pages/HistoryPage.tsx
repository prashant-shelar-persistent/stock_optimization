/**
 * History page — displays past optimization runs in a paginated table.
 *
 * Renders the `RunHistory` component which handles:
 *   - Paginated table of runs (status, tickers, budget, Sharpe ratios, date, actions)
 *   - Loading skeletons, empty state, and error state
 *   - Pagination controls
 */

import { Link } from "react-router-dom";
import { ArrowLeft, BarChart3 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { RunHistory } from "@/components/RunHistory";

// ── Main page ──────────────────────────────────────────────────────────────────

export default function HistoryPage() {
  return (
    <div className="min-h-screen bg-background">
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
          <Link to="/">
            <Button size="sm">New Optimization</Button>
          </Link>
        </div>

        {/* Run history table */}
        <RunHistory />
      </main>
    </div>
  );
}
