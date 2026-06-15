/**
 * useRunHistory — custom hook for the run history page.
 *
 * Uses TanStack Query to fetch paginated optimization run summaries.
 *
 * Returns: { runs, total, page, setPage, isLoading, error }
 */

import { useState } from "react";
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

  /** Navigate to a specific page. */
  setPage: (page: number) => void;

  /** True while the query is fetching. */
  isLoading: boolean;

  /** The query error, or null if no error. */
  error: Error | null;
}

export function useRunHistory(): UseRunHistoryReturn {
  const [page, setPage] = useState(1);

  const { data, isLoading, error } = useQuery({
    queryKey: ["runs", page] as const,
    queryFn: () => listRuns({ page, page_size: PAGE_SIZE }),
    staleTime: 30_000, // 30 seconds
    placeholderData: (previousData) => previousData, // keep previous page visible while fetching
  });

  return {
    runs: data?.items ?? [],
    total: data?.total ?? 0,
    page,
    setPage,
    isLoading,
    error: error as Error | null,
  };
}
