/**
 * useRunHistory — custom hook for the run history page.
 *
 * Uses TanStack Query to fetch paginated optimization run summaries.
 *
 * React 19: Uses `useTransition` to wrap page navigation so that the
 * current page's data remains visible while the next page is loading,
 * keeping the UI responsive during pagination.
 *
 * Returns: { runs, total, page, setPage, isLoading, isPending, error }
 */

import { useState, useTransition } from "react";
import { useQuery } from "@tanstack/react-query";
import { listRuns } from "@/lib/api";
import type { OptimizationRunSummary } from "@/types/api";

const PAGE_SIZE = 20;

interface UseRunHistoryReturn {
  /** The current page of run summaries. */
  runs: OptimizationRunSummary[];

  /** Total number of runs across all pages. */
  total: number;

  /** Current 1-based page number. */
  page: number;

  /** Navigate to a specific page. Wrapped in a React transition for smooth UX. */
  setPage: (page: number) => void;

  /** True while the query is fetching. */
  isLoading: boolean;

  /**
   * True while a page-change transition is in progress (React 19 useTransition).
   * The UI can use this to show a subtle loading indicator without blocking
   * the current page's content.
   */
  isPending: boolean;

  /** The query error, or null if no error. */
  error: Error | null;
}

export function useRunHistory(): UseRunHistoryReturn {
  const [page, setPageState] = useState(1);

  // React 19: useTransition wraps page navigation so the current page stays
  // visible while the next page is being fetched. isPending is true during
  // the transition, allowing the UI to show a subtle loading indicator.
  const [isPending, startTransition] = useTransition();

  const { data, isLoading, error } = useQuery({
    queryKey: ["runs", page] as const,
    queryFn: () => listRuns({ page, page_size: PAGE_SIZE }),
    staleTime: 30_000, // 30 seconds
    placeholderData: (previousData) => previousData, // keep previous page visible while fetching
  });

  /**
   * Navigate to a specific page.
   * Wrapped in startTransition so the current page's content stays visible
   * while the new page is loading (non-blocking navigation).
   */
  const setPage = (newPage: number) => {
    startTransition(() => {
      setPageState(newPage);
    });
  };

  return {
    runs: data?.items ?? [],
    total: data?.total ?? 0,
    page,
    setPage,
    isLoading,
    isPending,
    error: error as Error | null,
  };
}
