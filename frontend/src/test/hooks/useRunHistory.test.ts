/**
 * Tests for @/hooks/useRunHistory
 *
 * Uses TanStack Query's QueryClientProvider and mocks the listRuns API
 * function to test the hook's behaviour in different states:
 *   - Loading state (isLoading = true, runs = [])
 *   - Success state (runs populated, total set)
 *   - Error state (error set, runs = [])
 *   - Pagination (setPage changes the query key)
 *   - Default page is 1
 *   - PAGE_SIZE is 20 (passed to listRuns)
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";
import { useRunHistory } from "@/hooks/useRunHistory";
import { makeRunSummary, RUN_SUMMARY_LIST } from "@/test/fixtures";
import type { OptimizationRunSummary } from "@/types/api";

// ── Mock listRuns ─────────────────────────────────────────────────────────────

const mockListRuns = vi.fn();

vi.mock("@/lib/api", () => ({
  listRuns: (...args: unknown[]) => mockListRuns(...args),
}));

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Create a fresh QueryClient for each test to prevent cache pollution.
 */
function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // Disable retries so errors surface immediately in tests
        retry: false,
        // Disable stale time so queries always refetch
        staleTime: 0,
      },
    },
  });
}

/**
 * Wrapper that provides a fresh QueryClient for each renderHook call.
 */
function createWrapper() {
  const queryClient = createTestQueryClient();
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return createElement(
      QueryClientProvider,
      { client: queryClient },
      children,
    );
  };
}

/**
 * Build a paginated list response.
 */
function makeListResponse(
  items: OptimizationRunSummary[],
  total: number,
  page = 1,
  pageSize = 20,
) {
  return { items, total, page, page_size: pageSize };
}

// ── Setup ─────────────────────────────────────────────────────────────────────

beforeEach(() => {
  mockListRuns.mockReset();
});

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("useRunHistory", () => {
  // ── Initial / loading state ─────────────────────────────────────────────────

  describe("initial state", () => {
    it("starts with isLoading = true before the query resolves", () => {
      // Never resolve the promise so we stay in loading state
      mockListRuns.mockReturnValue(new Promise(() => {}));

      const { result } = renderHook(() => useRunHistory(), {
        wrapper: createWrapper(),
      });

      expect(result.current.isLoading).toBe(true);
    });

    it("starts with an empty runs array", () => {
      mockListRuns.mockReturnValue(new Promise(() => {}));

      const { result } = renderHook(() => useRunHistory(), {
        wrapper: createWrapper(),
      });

      expect(result.current.runs).toEqual([]);
    });

    it("starts with total = 0", () => {
      mockListRuns.mockReturnValue(new Promise(() => {}));

      const { result } = renderHook(() => useRunHistory(), {
        wrapper: createWrapper(),
      });

      expect(result.current.total).toBe(0);
    });

    it("starts on page 1", () => {
      mockListRuns.mockReturnValue(new Promise(() => {}));

      const { result } = renderHook(() => useRunHistory(), {
        wrapper: createWrapper(),
      });

      expect(result.current.page).toBe(1);
    });

    it("starts with error = null", () => {
      mockListRuns.mockReturnValue(new Promise(() => {}));

      const { result } = renderHook(() => useRunHistory(), {
        wrapper: createWrapper(),
      });

      expect(result.current.error).toBeNull();
    });
  });

  // ── Success state ───────────────────────────────────────────────────────────

  describe("success state", () => {
    it("populates runs when the query resolves", async () => {
      mockListRuns.mockResolvedValue(
        makeListResponse(RUN_SUMMARY_LIST, RUN_SUMMARY_LIST.length),
      );

      const { result } = renderHook(() => useRunHistory(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isLoading).toBe(false));

      expect(result.current.runs).toHaveLength(RUN_SUMMARY_LIST.length);
    });

    it("sets total from the API response", async () => {
      mockListRuns.mockResolvedValue(makeListResponse(RUN_SUMMARY_LIST, 42));

      const { result } = renderHook(() => useRunHistory(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isLoading).toBe(false));

      expect(result.current.total).toBe(42);
    });

    it("returns the correct run data", async () => {
      const run = makeRunSummary({ run_id: "run-test-001" });
      mockListRuns.mockResolvedValue(makeListResponse([run], 1));

      const { result } = renderHook(() => useRunHistory(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isLoading).toBe(false));

      expect(result.current.runs[0].run_id).toBe("run-test-001");
      expect(result.current.runs[0].status).toBe("completed");
    });

    it("sets error to null on success", async () => {
      mockListRuns.mockResolvedValue(makeListResponse([], 0));

      const { result } = renderHook(() => useRunHistory(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isLoading).toBe(false));

      expect(result.current.error).toBeNull();
    });

    it("handles an empty list response", async () => {
      mockListRuns.mockResolvedValue(makeListResponse([], 0));

      const { result } = renderHook(() => useRunHistory(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isLoading).toBe(false));

      expect(result.current.runs).toEqual([]);
      expect(result.current.total).toBe(0);
    });
  });

  // ── Error state ─────────────────────────────────────────────────────────────

  describe("error state", () => {
    it("sets error when the query fails", async () => {
      const networkError = new Error("Network request failed");
      mockListRuns.mockRejectedValue(networkError);

      const { result } = renderHook(() => useRunHistory(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.error).not.toBeNull());

      expect(result.current.error).toBeInstanceOf(Error);
      expect(result.current.error?.message).toBe("Network request failed");
    });

    it("returns empty runs array on error", async () => {
      mockListRuns.mockRejectedValue(new Error("Server error"));

      const { result } = renderHook(() => useRunHistory(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.error).not.toBeNull());

      expect(result.current.runs).toEqual([]);
    });

    it("returns total = 0 on error", async () => {
      mockListRuns.mockRejectedValue(new Error("Server error"));

      const { result } = renderHook(() => useRunHistory(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.error).not.toBeNull());

      expect(result.current.total).toBe(0);
    });
  });

  // ── API call parameters ─────────────────────────────────────────────────────

  describe("API call parameters", () => {
    it("calls listRuns with page=1 and page_size=20 by default", async () => {
      mockListRuns.mockResolvedValue(makeListResponse([], 0));

      renderHook(() => useRunHistory(), { wrapper: createWrapper() });

      await waitFor(() => expect(mockListRuns).toHaveBeenCalled());

      expect(mockListRuns).toHaveBeenCalledWith({ page: 1, page_size: 20 });
    });

    it("calls listRuns with the correct page when setPage is called", async () => {
      mockListRuns.mockResolvedValue(makeListResponse([], 0));

      const { result } = renderHook(() => useRunHistory(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isLoading).toBe(false));

      // Navigate to page 2
      result.current.setPage(2);

      await waitFor(() =>
        expect(mockListRuns).toHaveBeenCalledWith({ page: 2, page_size: 20 }),
      );
    });
  });

  // ── Pagination ──────────────────────────────────────────────────────────────

  describe("pagination", () => {
    it("exposes a setPage function", () => {
      mockListRuns.mockReturnValue(new Promise(() => {}));

      const { result } = renderHook(() => useRunHistory(), {
        wrapper: createWrapper(),
      });

      expect(typeof result.current.setPage).toBe("function");
    });

    it("updates the page state when setPage is called", async () => {
      mockListRuns.mockResolvedValue(makeListResponse([], 0));

      const { result } = renderHook(() => useRunHistory(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isLoading).toBe(false));

      result.current.setPage(3);

      await waitFor(() => expect(result.current.page).toBe(3));
    });

    it("fetches new data when page changes", async () => {
      const page1Items = Array.from({ length: 20 }, (_, i) =>
        makeRunSummary({ run_id: `run-p1-${i}` }),
      );
      const page2Items = Array.from({ length: 5 }, (_, i) =>
        makeRunSummary({ run_id: `run-p2-${i}` }),
      );

      mockListRuns
        .mockResolvedValueOnce(makeListResponse(page1Items, 25, 1))
        .mockResolvedValueOnce(makeListResponse(page2Items, 25, 2));

      const { result } = renderHook(() => useRunHistory(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isLoading).toBe(false));
      expect(result.current.runs).toHaveLength(20);

      result.current.setPage(2);

      await waitFor(() =>
        expect(result.current.runs[0]?.run_id).toMatch(/run-p2/),
      );
      expect(result.current.runs).toHaveLength(5);
    });
  });
});
