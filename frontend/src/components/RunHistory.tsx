/**
 * RunHistory — Paginated table of past optimization runs.
 *
 * Reads data from the `useRunHistory` hook (TanStack Query + pagination).
 *
 * Columns:
 *   Status | Assets | Budget | Classical Sharpe | Quantum Sharpe | Date | Actions
 *
 * Features:
 *   - Colored status badges (pending=gray, running=blue+spinner, completed=green, failed=red)
 *   - Tickers: first 3 as badges, "+N more" if > 3
 *   - Budget: formatted as USD
 *   - Sharpe: 2 decimal places, "—" if null
 *   - Date: relative time (e.g., "2 hours ago") via Intl.RelativeTimeFormat
 *   - Actions: "View Details" link to /run/:runId
 *   - Pagination: Previous / Next + "Page X of Y"
 *   - Loading: 5 Skeleton rows
 *   - Empty state: prompt to start a run
 *   - Error state: message + retry button
 *
 * React 19: uses named imports — no `import * as React` needed.
 */

import { Link } from "react-router-dom";
import {
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Loader2,
  RefreshCw,
} from "lucide-react";
import { useRunHistory } from "@/hooks/useRunHistory";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatCurrency, formatNumber } from "@/lib/utils";
import type { OptimizationRunSummary, OptimizationStatus } from "@/types/api";

// ── Constants ──────────────────────────────────────────────────────────────────

const PAGE_SIZE = 20;

// ── Relative time formatter ────────────────────────────────────────────────────

/**
 * Format a date string as a human-readable relative time.
 * e.g. "2 hours ago", "3 days ago", "just now"
 */
function formatRelativeTime(dateStr: string): string {
  try {
    const date = new Date(dateStr);
    const now = Date.now();
    const diffMs = now - date.getTime();
    const diffSec = Math.floor(diffMs / 1000);

    if (diffSec < 60) return "just now";

    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) {
      const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
      return rtf.format(-diffMin, "minute");
    }

    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) {
      const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
      return rtf.format(-diffHr, "hour");
    }

    const diffDay = Math.floor(diffHr / 24);
    if (diffDay < 30) {
      const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
      return rtf.format(-diffDay, "day");
    }

    // Fall back to locale date string for older dates
    return date.toLocaleDateString([], {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return dateStr;
  }
}

// ── Status badge ───────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: OptimizationStatus }) {
  switch (status) {
    case "completed":
      return <Badge variant="success">Completed</Badge>;
    case "running":
      return (
        <Badge variant="default" className="gap-1">
          <Loader2 className="h-3 w-3 animate-spin" />
          Running
        </Badge>
      );
    case "pending":
      return <Badge variant="secondary">Pending</Badge>;
    case "failed":
      return <Badge variant="destructive">Failed</Badge>;
    default:
      return <Badge variant="outline">{status}</Badge>;
  }
}

// ── Table skeleton ─────────────────────────────────────────────────────────────

function TableSkeleton() {
  return (
    <>
      {Array.from({ length: 5 }).map((_, i) => (
        <TableRow key={i}>
          <TableCell>
            <Skeleton className="h-5 w-20 rounded-full" />
          </TableCell>
          <TableCell>
            <div className="flex gap-1">
              <Skeleton className="h-5 w-12 rounded-full" />
              <Skeleton className="h-5 w-12 rounded-full" />
              <Skeleton className="h-5 w-12 rounded-full" />
            </div>
          </TableCell>
          <TableCell>
            <Skeleton className="h-4 w-20" />
          </TableCell>
          <TableCell>
            <Skeleton className="h-4 w-12" />
          </TableCell>
          <TableCell>
            <Skeleton className="h-4 w-12" />
          </TableCell>
          <TableCell>
            <Skeleton className="h-4 w-24" />
          </TableCell>
          <TableCell>
            <Skeleton className="h-4 w-16" />
          </TableCell>
        </TableRow>
      ))}
    </>
  );
}

// ── Run row ────────────────────────────────────────────────────────────────────

function RunRow({ run }: { run: OptimizationRunSummary }) {
  const relativeDate = formatRelativeTime(run.created_at);

  return (
    <TableRow className="group">
      {/* Status */}
      <TableCell>
        <StatusBadge status={run.status} />
      </TableCell>

      {/* Tickers */}
      <TableCell>
        <div className="flex flex-wrap gap-1">
          {run.tickers.slice(0, 3).map((t) => (
            <Badge key={t} variant="outline" className="font-mono text-xs">
              {t}
            </Badge>
          ))}
          {run.tickers.length > 3 && (
            <Badge variant="outline" className="text-xs text-muted-foreground">
              +{run.tickers.length - 3}
            </Badge>
          )}
        </div>
      </TableCell>

      {/* Budget */}
      <TableCell className="tabular-nums text-sm">
        {formatCurrency(run.budget)}
      </TableCell>

      {/* Classical Sharpe */}
      <TableCell className="tabular-nums text-sm">
        {run.classical_sharpe !== undefined && run.classical_sharpe !== null ? (
          <span className="font-medium text-blue-600 dark:text-blue-400">
            {formatNumber(run.classical_sharpe, 2)}
          </span>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </TableCell>

      {/* Quantum Sharpe */}
      <TableCell className="tabular-nums text-sm">
        {run.quantum_sharpe !== undefined && run.quantum_sharpe !== null ? (
          <span className="font-medium text-violet-600 dark:text-violet-400">
            {formatNumber(run.quantum_sharpe, 2)}
          </span>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </TableCell>

      {/* Date */}
      <TableCell
        className="text-xs text-muted-foreground"
        title={new Date(run.created_at).toLocaleString()}
      >
        {relativeDate}
      </TableCell>

      {/* Actions */}
      <TableCell>
        <Link
          to={`/run/${run.run_id}`}
          className="flex items-center gap-1 text-xs text-primary hover:underline"
        >
          View Details
          <ExternalLink className="h-3 w-3" />
        </Link>
      </TableCell>
    </TableRow>
  );
}

// ── Empty state ────────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <TableRow>
      <TableCell
        colSpan={7}
        className="h-40 text-center text-sm text-muted-foreground"
      >
        <div className="flex flex-col items-center gap-2">
          <p>No optimization runs yet.</p>
          <Link
            to="/"
            className="text-primary hover:underline font-medium"
          >
            Start one from the Dashboard →
          </Link>
        </div>
      </TableCell>
    </TableRow>
  );
}

// ── Error state ────────────────────────────────────────────────────────────────

function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <TableRow>
      <TableCell
        colSpan={7}
        className="h-40 text-center"
      >
        <div className="flex flex-col items-center gap-3">
          <p className="text-sm text-destructive">{message}</p>
          <Button
            variant="outline"
            size="sm"
            onClick={onRetry}
            className="gap-1.5"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Retry
          </Button>
        </div>
      </TableCell>
    </TableRow>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export function RunHistory() {
  const { runs, total, page, setPage, isLoading, error } = useRunHistory();

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const startItem = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const endItem = Math.min(page * PAGE_SIZE, total);

  // Derive a retry function by going back to page 1
  const handleRetry = () => setPage(1);

  return (
    <div className="space-y-4">
      {/* Table */}
      <div className="rounded-lg border bg-card">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/40 hover:bg-muted/40">
              <TableHead className="w-[120px]">Status</TableHead>
              <TableHead>Assets</TableHead>
              <TableHead className="w-[120px]">Budget</TableHead>
              <TableHead className="w-[110px]">
                <span className="flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-blue-500 flex-shrink-0" />
                  Classical
                </span>
              </TableHead>
              <TableHead className="w-[110px]">
                <span className="flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-violet-500 flex-shrink-0" />
                  Quantum
                </span>
              </TableHead>
              <TableHead className="w-[130px]">Date</TableHead>
              <TableHead className="w-[110px]">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableSkeleton />
            ) : error ? (
              <ErrorState
                message={`Failed to load run history: ${error.message}`}
                onRetry={handleRetry}
              />
            ) : runs.length === 0 ? (
              <EmptyState />
            ) : (
              runs.map((run) => <RunRow key={run.run_id} run={run} />)
            )}
          </TableBody>
        </Table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>
            {total > 0
              ? `Showing ${startItem}–${endItem} of ${total} run${total !== 1 ? "s" : ""}`
              : "No runs"}
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage(page - 1)}
              disabled={page <= 1 || isLoading}
              className="gap-1"
            >
              <ChevronLeft className="h-4 w-4" />
              Previous
            </Button>
            <span className="tabular-nums px-1">
              Page {page} of {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage(page + 1)}
              disabled={page >= totalPages || isLoading}
              className="gap-1"
            >
              Next
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
