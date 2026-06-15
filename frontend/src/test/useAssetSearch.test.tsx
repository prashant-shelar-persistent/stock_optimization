/**
 * Tests for @/hooks/useAssetSearch
 *
 * Uses vi.mock to mock @/lib/api and tests debouncing behavior.
 * Covers: minimum query length, debouncing, results shape, loading state.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useAssetSearch } from "@/hooks/useAssetSearch";

// ── Mock the API ──────────────────────────────────────────────────────────────

const mockSearchAssets = vi.fn();

vi.mock("@/lib/api", () => ({
  searchAssets: (...args: unknown[]) => mockSearchAssets(...args),
}));

// ── Test wrapper ──────────────────────────────────────────────────────────────

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
        staleTime: 0,
      },
    },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("useAssetSearch", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  // ── Empty query ────────────────────────────────────────────────────────────

  it("returns empty results and isLoading=false for empty query", async () => {
    const { result } = renderHook(() => useAssetSearch(""), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.results).toEqual([]);
      expect(result.current.isLoading).toBe(false);
    });

    expect(mockSearchAssets).not.toHaveBeenCalled();
  });

  // ── Debounce behavior ──────────────────────────────────────────────────────

  it("calls searchAssets after debounce period with the query", async () => {
    vi.useFakeTimers();
    mockSearchAssets.mockResolvedValue([
      { ticker: "AAPL", name: "Apple Inc.", sector: "Technology" },
    ]);

    const { result } = renderHook(() => useAssetSearch("AAPL"), {
      wrapper: createWrapper(),
    });

    // Advance timers past the 300ms debounce
    act(() => {
      vi.advanceTimersByTime(350);
    });

    vi.useRealTimers();

    await waitFor(() => {
      expect(mockSearchAssets).toHaveBeenCalledWith("AAPL");
    });

    await waitFor(() => {
      expect(result.current.results).toHaveLength(1);
      expect(result.current.results[0].ticker).toBe("AAPL");
      expect(result.current.results[0].name).toBe("Apple Inc.");
    });
  });

  // ── Results shape ──────────────────────────────────────────────────────────

  it("returns results with correct shape including all fields", async () => {
    vi.useFakeTimers();
    const mockResults = [
      {
        ticker: "MSFT",
        name: "Microsoft Corporation",
        sector: "Technology",
        exchange: "NASDAQ",
      },
      {
        ticker: "GOOGL",
        name: "Alphabet Inc.",
        sector: "Technology",
        exchange: "NASDAQ",
      },
    ];
    mockSearchAssets.mockResolvedValue(mockResults);

    const { result } = renderHook(() => useAssetSearch("tech"), {
      wrapper: createWrapper(),
    });

    act(() => {
      vi.advanceTimersByTime(350);
    });

    vi.useRealTimers();

    await waitFor(() => {
      expect(result.current.results).toHaveLength(2);
    });

    expect(result.current.results[0].ticker).toBe("MSFT");
    expect(result.current.results[0].name).toBe("Microsoft Corporation");
    expect(result.current.results[0].sector).toBe("Technology");
    expect(result.current.results[0].exchange).toBe("NASDAQ");
    expect(result.current.results[1].ticker).toBe("GOOGL");
  });

  // ── Empty results ──────────────────────────────────────────────────────────

  it("returns empty array when API returns empty array", async () => {
    vi.useFakeTimers();
    mockSearchAssets.mockResolvedValue([]);

    const { result } = renderHook(() => useAssetSearch("xyz"), {
      wrapper: createWrapper(),
    });

    act(() => {
      vi.advanceTimersByTime(350);
    });

    vi.useRealTimers();

    await waitFor(() => {
      expect(result.current.results).toEqual([]);
      expect(result.current.isLoading).toBe(false);
    });
  });

  // ── Query too short ────────────────────────────────────────────────────────

  it("does not call searchAssets when query is empty string", async () => {
    const { result } = renderHook(() => useAssetSearch(""), {
      wrapper: createWrapper(),
    });

    // Wait a bit to ensure no calls happen
    await new Promise((r) => setTimeout(r, 50));

    expect(mockSearchAssets).not.toHaveBeenCalled();
    expect(result.current.isLoading).toBe(false);
    expect(result.current.results).toEqual([]);
  });

  // ── Multiple results ───────────────────────────────────────────────────────

  it("returns multiple results correctly", async () => {
    vi.useFakeTimers();
    const mockResults = Array.from({ length: 5 }, (_, i) => ({
      ticker: `TICK${i}`,
      name: `Company ${i}`,
      sector: "Finance",
    }));
    mockSearchAssets.mockResolvedValue(mockResults);

    const { result } = renderHook(() => useAssetSearch("TICK"), {
      wrapper: createWrapper(),
    });

    act(() => {
      vi.advanceTimersByTime(350);
    });

    vi.useRealTimers();

    await waitFor(() => {
      expect(result.current.results).toHaveLength(5);
    });

    expect(result.current.results[4].ticker).toBe("TICK4");
  });
});
