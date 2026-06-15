/**
 * useAssetSearch — custom hook for the asset search combobox.
 *
 * Debounces the query string by 300 ms, then uses TanStack Query to call
 * searchAssets() when the debounced query is at least 1 character long.
 *
 * Returns: { results, isLoading }
 */

import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { searchAssets } from "@/lib/api";
import type { AssetSearchResult } from "@/types/api";

const DEBOUNCE_MS = 300;
const MIN_QUERY_LENGTH = 1;

interface UseAssetSearchReturn {
  /** The list of matching assets (empty array while loading or query is too short). */
  results: AssetSearchResult[];

  /** True while the search query is in flight. */
  isLoading: boolean;
}

export function useAssetSearch(query: string): UseAssetSearchReturn {
  const [debouncedQuery, setDebouncedQuery] = useState(query);

  // Debounce: update debouncedQuery 300 ms after the last keystroke
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedQuery(query);
    }, DEBOUNCE_MS);

    return () => {
      clearTimeout(timer);
    };
  }, [query]);

  const isQueryLongEnough = debouncedQuery.length >= MIN_QUERY_LENGTH;

  const { data, isLoading } = useQuery({
    queryKey: ["assets", debouncedQuery] as const,
    queryFn: () => searchAssets(debouncedQuery),
    enabled: isQueryLongEnough,
    staleTime: 60_000, // asset metadata rarely changes — cache for 1 minute
  });

  return {
    results: data ?? [],
    // Only report loading when the query is long enough to trigger a fetch
    isLoading: isQueryLongEnough && isLoading,
  };
}
