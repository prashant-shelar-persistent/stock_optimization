/**
 * RunDetailPage — Full detail view for a single optimization run.
 *
 * Route: /run/:runId
 *
 * Layout:
 *   ┌──────────────────────────────────────────────────────┐
 *   │  Header (logo + nav)                                 │
 *   ├──────────────────────────────────────────────────────┤
 *   │  ← Back to History                                   │
 *   │  Run Metadata Card (ID, status, tickers, budget, ts) │
 *   ├──────────────────────────────────────────────────────┤
 *   │  [pending/running]  AgentProgressPanel               │
 *   │  [completed]        ComparisonDashboard              │
 *   │  [failed]           Error card                       │
 *   │  [loading]          Skeleton placeholders            │
 *   └──────────────────────────────────────────────────────┘
 *
 * State:
 *   - runId from useParams()
 *   - run data from useRunDetail(runId) — polls while pending/running
 */

import { useParams, Link } from "react-router-dom";
import {
  ArrowLeft,
  BarChart3,
  History,
  AlertTriangle,
  Clock,
  CheckCircle2,
  Loader2,
  XCircle,
  Calendar,
  DollarSign,
  Hash,
} from "lucide-react";
import { useRunDetail } from "@/hooks/useRunDetail";
import { AgentProgressPanel } from "@/components/dashboard/AgentProgressPanel";
import { ComparisonDashboard } from "@/components/dashboard/ComparisonDashboard";
import { FrontierReportViewer } from "@/components/dashboard/FrontierReportViewer";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { formatCurrency, truncate } from "@/lib/utils";
import type { OptimizationRunDetail, OptimizationStatus } from "@/types/api";

// ── Status badge ───────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: OptimizationStatus }) {
  switch (status) {
    case "completed":
      return (
        <Badge variant="success" className="gap-1.5">
          <CheckCircle2 className="h-3 w-3" />
          Completed
        </Badge>
      );
    case "running":
      return (
        <Badge variant="default" className="gap-1.5">
          <Loader2 className="h-3 w-3 animate-spin" />
          Running
        </Badge>
      );
    case "pending":
      return (
        <Badge variant="secondary" className="gap-1.5">
          <Clock className="h-3 w-3" />
          Pending
        </Badge>
      );
    case "failed":
      return (
        <Badge variant="destructive" className="gap-1.5">
          <XCircle className="h-3 w-3" />
          Failed
        </Badge>
      );
    default:
      return <Badge variant="outline">{status}</Badge>;
  }
}

// ── Metadata card ──────────────────────────────────────────────────────────────

function MetadataCard({ run }: { run: OptimizationRunDetail }) {
  const createdAt = new Date(run.created_at).toLocaleString([], {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

  const completedAt = run.completed_at
    ? new Date(run.completed_at).toLocaleString([], {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : null;

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">Run Details</CardTitle>
          <StatusBadge status={run.status} />
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {/* Run ID */}
          <div className="flex items-start gap-2">
            <Hash className="mt-0.5 h-4 w-4 flex-shrink-0 text-muted-foreground" />
            <div className="min-w-0">
              <p className="text-xs text-muted-foreground">Run ID</p>
              <p className="font-mono text-sm font-medium" title={run.run_id}>
                {truncate(run.run_id, 16)}
              </p>
            </div>
          </div>

          {/* Budget */}
          <div className="flex items-start gap-2">
            <DollarSign className="mt-0.5 h-4 w-4 flex-shrink-0 text-muted-foreground" />
            <div>
              <p className="text-xs text-muted-foreground">Budget</p>
              <p className="text-sm font-medium">{formatCurrency(run.budget)}</p>
            </div>
          </div>

          {/* Created at */}
          <div className="flex items-start gap-2">
            <Calendar className="mt-0.5 h-4 w-4 flex-shrink-0 text-muted-foreground" />
            <div>
              <p className="text-xs text-muted-foreground">Created</p>
              <p className="text-sm">{createdAt}</p>
            </div>
          </div>

          {/* Completed at */}
          {completedAt && (
            <div className="flex items-start gap-2">
              <CheckCircle2 className="mt-0.5 h-4 w-4 flex-shrink-0 text-green-500" />
              <div>
                <p className="text-xs text-muted-foreground">Completed</p>
                <p className="text-sm">{completedAt}</p>
              </div>
            </div>
          )}
        </div>

        {/* Tickers */}
        <Separator className="my-4" />
        <div>
          <p className="mb-2 text-xs text-muted-foreground">Assets</p>
          <div className="flex flex-wrap gap-1.5">
            {run.tickers.map((ticker) => (
              <Badge
                key={ticker}
                variant="outline"
                className="font-mono text-xs"
              >
                {ticker}
              </Badge>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ── Metadata skeleton ──────────────────────────────────────────────────────────

function MetadataSkeleton() {
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <Skeleton className="h-5 w-24" />
          <Skeleton className="h-5 w-20 rounded-full" />
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="space-y-1.5">
              <Skeleton className="h-3 w-16" />
              <Skeleton className="h-4 w-28" />
            </div>
          ))}
        </div>
        <Separator className="my-4" />
        <div className="flex gap-1.5">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-5 w-12 rounded-full" />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

// ── Results skeleton ───────────────────────────────────────────────────────────

function ResultsSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-8 w-48" />
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-20 rounded-lg" />
        ))}
      </div>
      <Skeleton className="h-64 rounded-lg" />
    </div>
  );
}

// ── In-progress panel ──────────────────────────────────────────────────────────

/**
 * Shown while the run is pending or running.
 * Uses a static empty progress array since we're viewing a historical run
 * (not connected to a live WebSocket). The polling via useRunDetail will
 * refresh the page when the run completes.
 */
function InProgressPanel({ run }: { run: OptimizationRunDetail }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Agent Pipeline Progress</CardTitle>
        <p className="text-xs text-muted-foreground">
          {run.status === "pending"
            ? "Run is queued and will start shortly…"
            : "Optimization is running — this page will update automatically."}
        </p>
      </CardHeader>
      <CardContent>
        <AgentProgressPanel progress={[]} isRunning={run.status === "running"} />
      </CardContent>
    </Card>
  );
}

// ── Error panel ────────────────────────────────────────────────────────────────

function ErrorPanel({ run }: { run: OptimizationRunDetail }) {
  return (
    <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-5">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-destructive" />
        <div>
          <p className="font-semibold text-destructive">Optimization Failed</p>
          {run.error_message ? (
            <p className="mt-1 text-sm text-destructive/80">
              {run.error_message}
            </p>
          ) : (
            <p className="mt-1 text-sm text-muted-foreground">
              An unexpected error occurred. Please try again from the Dashboard.
            </p>
          )}
          <div className="mt-3">
            <Link
              to="/"
              className="text-sm font-medium text-primary hover:underline"
            >
              ← Back to Dashboard
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Page-level error ───────────────────────────────────────────────────────────

function PageError({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-5">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-destructive" />
        <div>
          <p className="font-semibold text-destructive">Failed to load run</p>
          <p className="mt-1 text-sm text-destructive/80">{message}</p>
          <div className="mt-3">
            <Link
              to="/history"
              className="text-sm font-medium text-primary hover:underline"
            >
              ← Back to History
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const { run, isLoading, error } = useRunDetail(runId ?? "");

  return (
    <div className="flex min-h-screen flex-col bg-background">
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

          <nav className="flex items-center gap-4">
            <Link
              to="/"
              className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              <BarChart3 className="h-4 w-4" />
              Dashboard
            </Link>
            <Link
              to="/history"
              className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              <History className="h-4 w-4" />
              History
            </Link>
          </nav>
        </div>
      </header>

      {/* ── Main content ── */}
      <main className="flex-1 mx-auto w-full max-w-7xl px-6 py-6">
        {/* Back link */}
        <div className="mb-5">
          <Link
            to="/history"
            className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors w-fit"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to History
          </Link>
        </div>

        {/* Page title */}
        <div className="mb-6">
          <h2 className="text-2xl font-bold">Run Detail</h2>
          {runId && (
            <p className="mt-1 font-mono text-sm text-muted-foreground">
              {runId}
            </p>
          )}
        </div>

        {/* Content */}
        <div className="space-y-6">
          {/* Loading state */}
          {isLoading && !run && (
            <>
              <MetadataSkeleton />
              <ResultsSkeleton />
            </>
          )}

          {/* Error state */}
          {error && !run && (
            <PageError message={error.message} />
          )}

          {/* Run loaded */}
          {run && (
            <>
              {/* Metadata card */}
              <MetadataCard run={run} />

              {/* Results area */}
              {(run.status === "pending" || run.status === "running") && (
                <InProgressPanel run={run} />
              )}

              {run.status === "failed" && <ErrorPanel run={run} />}

              {run.status === "completed" && run.classical_result && (
                <>
                  <ComparisonDashboard result={run} />
                  {run.frontier_report && (
                    <FrontierReportViewer report={run.frontier_report} />
                  )}
                </>
              )}

              {run.status === "completed" && !run.classical_result && (
                <div className="rounded-lg border bg-muted/20 p-6 text-center text-sm text-muted-foreground">
                  Results are not available for this run.
                </div>
              )}
            </>
          )}
        </div>
      </main>
    </div>
  );
}
