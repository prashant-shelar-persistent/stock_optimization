/**
 * useRunDetail — custom hook for the run detail page.
 *
 * Uses TanStack Query to fetch a single optimization run by ID.
 * Polls every 3 seconds while the run is in a non-terminal state
 * (status === "pending" | "running"), and stops polling once the run
 * reaches a terminal state (status === "completed" | "failed").
 *
 * Returns: { run, isLoading, error }
 */

import { useQuery } from "@tanstack/react-query";
import { getOptimizationRun } from "@/lib/api";
import type { OptimizationRunDetail } from "@/types/api";

const POLL_INTERVAL_MS = 3000;

/** Terminal statuses — polling stops when the run reaches one of these. */
const TERMINAL_STATUSES = new Set(["completed", "failed"]);

interface UseRunDetailReturn {
  /** The run detail, or undefined while loading. */
  run: OptimizationRunDetail | undefined;

  /** True while the initial fetch is in flight. */
  isLoading: boolean;

  /** The query error, or null if no error. */
  error: Error | null;
}

export function useRunDetail(runId: string): UseRunDetailReturn {
  const { data, isLoading, error } = useQuery({
    queryKey: ["run", runId] as const,
    queryFn: () => getOptimizationRun(runId),
    // Poll every 3 s while the run is still in progress; stop once terminal
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (!status || TERMINAL_STATUSES.has(status)) {
        return false; // stop polling
      }
      return POLL_INTERVAL_MS;
    },
    // Keep stale data visible while re-fetching
    staleTime: 0,
  });

  return {
    run: data,
    isLoading,
    error: error as Error | null,
  };
}
