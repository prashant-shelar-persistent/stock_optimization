/**
 * Tests for @/hooks/useOptimize
 *
 * Mocks @/lib/api and @/store/uiStore to test the submission flow.
 * Covers: successful submission, error handling, state transitions.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useOptimize } from "@/hooks/useOptimize";
import { useUIStore } from "@/store/uiStore";
import { ApiError } from "@/lib/api";

// ── Mocks ─────────────────────────────────────────────────────────────────────

const mockSubmitOptimization = vi.fn();

vi.mock("@/lib/api", async (importOriginal) => {
  // eslint-disable-next-line @typescript-eslint/consistent-type-imports
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    submitOptimization: (...args: unknown[]) =>
      mockSubmitOptimization(...args),
  };
});

// Mock use-toast to avoid Radix UI toast issues in tests
const mockToast = vi.fn();
vi.mock("@/hooks/use-toast", () => ({
  useToast: () => ({ toast: mockToast }),
}));

// ── Helpers ───────────────────────────────────────────────────────────────────

// Reset Zustand store before each test
beforeEach(() => {
  vi.clearAllMocks();
  useUIStore.setState({
    currentRunId: null,
    optimizationResult: null,
    isOptimizing: false,
    agentProgress: [],
    activeTab: "classical",
  });
});

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("useOptimize", () => {
  // ── Initial state ──────────────────────────────────────────────────────────

  it("starts with isSubmitting=false and error=null", () => {
    const { result } = renderHook(() => useOptimize());
    expect(result.current.isSubmitting).toBe(false);
    expect(result.current.error).toBeNull();
  });

  // ── Successful submission ──────────────────────────────────────────────────

  it("returns the run_id on successful submission", async () => {
    mockSubmitOptimization.mockResolvedValue({ run_id: "run-success-123" });

    const { result } = renderHook(() => useOptimize());

    let returnedRunId: string | null = null;
    await act(async () => {
      returnedRunId = await result.current.submit({
        tickers: ["AAPL", "MSFT"],
        budget: 10000,
      });
    });

    expect(returnedRunId).toBe("run-success-123");
  });

  it("sets isSubmitting=true during submission and false after", async () => {
    let resolveSubmit!: (value: { run_id: string }) => void;
    mockSubmitOptimization.mockReturnValue(
      new Promise<{ run_id: string }>((resolve) => {
        resolveSubmit = resolve;
      }),
    );

    const { result } = renderHook(() => useOptimize());

    // Start submission
    act(() => {
      void result.current.submit({ tickers: ["AAPL"], budget: 5000 });
    });

    // Should be submitting
    expect(result.current.isSubmitting).toBe(true);

    // Resolve the promise
    await act(async () => {
      resolveSubmit({ run_id: "run-123" });
    });

    // Should no longer be submitting
    expect(result.current.isSubmitting).toBe(false);
  });

  it("calls startNewRun on the store with the run_id", async () => {
    mockSubmitOptimization.mockResolvedValue({ run_id: "run-store-test" });

    const { result } = renderHook(() => useOptimize());

    await act(async () => {
      await result.current.submit({ tickers: ["AAPL"], budget: 5000 });
    });

    const storeState = useUIStore.getState();
    expect(storeState.currentRunId).toBe("run-store-test");
    expect(storeState.isOptimizing).toBe(true);
  });

  it("shows a success toast on successful submission", async () => {
    mockSubmitOptimization.mockResolvedValue({ run_id: "run-toast-test" });

    const { result } = renderHook(() => useOptimize());

    await act(async () => {
      await result.current.submit({ tickers: ["AAPL"], budget: 5000 });
    });

    expect(mockToast).toHaveBeenCalledWith(
      expect.objectContaining({
        title: "Optimization started",
      }),
    );
  });

  it("clears error on successful submission after a previous error", async () => {
    // First call fails
    mockSubmitOptimization.mockRejectedValueOnce(new Error("First error"));
    // Second call succeeds
    mockSubmitOptimization.mockResolvedValueOnce({ run_id: "run-ok" });

    const { result } = renderHook(() => useOptimize());

    // First submission (fails)
    await act(async () => {
      await result.current.submit({ tickers: ["AAPL"], budget: 5000 });
    });
    expect(result.current.error).not.toBeNull();

    // Second submission (succeeds)
    await act(async () => {
      await result.current.submit({ tickers: ["AAPL"], budget: 5000 });
    });
    expect(result.current.error).toBeNull();
  });

  // ── Error handling ─────────────────────────────────────────────────────────

  it("returns null on failed submission", async () => {
    mockSubmitOptimization.mockRejectedValue(new Error("Network error"));

    const { result } = renderHook(() => useOptimize());

    let returnedRunId: string | null = "not-null";
    await act(async () => {
      returnedRunId = await result.current.submit({
        tickers: ["AAPL"],
        budget: 5000,
      });
    });

    expect(returnedRunId).toBeNull();
  });

  it("sets error state on failed submission", async () => {
    const testError = new Error("Submission failed");
    mockSubmitOptimization.mockRejectedValue(testError);

    const { result } = renderHook(() => useOptimize());

    await act(async () => {
      await result.current.submit({ tickers: ["AAPL"], budget: 5000 });
    });

    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.error?.message).toBe("Submission failed");
  });

  it("shows a destructive toast on failed submission", async () => {
    mockSubmitOptimization.mockRejectedValue(new Error("API down"));

    const { result } = renderHook(() => useOptimize());

    await act(async () => {
      await result.current.submit({ tickers: ["AAPL"], budget: 5000 });
    });

    expect(mockToast).toHaveBeenCalledWith(
      expect.objectContaining({
        variant: "destructive",
        title: "Submission failed",
        description: "API down",
      }),
    );
  });

  it("handles ApiError correctly", async () => {
    const apiError = new ApiError(422, "VALIDATION_ERROR", "Invalid tickers");
    mockSubmitOptimization.mockRejectedValue(apiError);

    const { result } = renderHook(() => useOptimize());

    await act(async () => {
      await result.current.submit({ tickers: [], budget: 0 });
    });

    expect(result.current.error).toBeInstanceOf(ApiError);
    expect(result.current.error?.message).toBe("Invalid tickers");
  });

  it("does not call startNewRun when submission fails", async () => {
    mockSubmitOptimization.mockRejectedValue(new Error("Failed"));

    const { result } = renderHook(() => useOptimize());

    await act(async () => {
      await result.current.submit({ tickers: ["AAPL"], budget: 5000 });
    });

    const storeState = useUIStore.getState();
    expect(storeState.currentRunId).toBeNull();
    expect(storeState.isOptimizing).toBe(false);
  });

  it("sets isSubmitting=false after failed submission", async () => {
    mockSubmitOptimization.mockRejectedValue(new Error("Failed"));

    const { result } = renderHook(() => useOptimize());

    await act(async () => {
      await result.current.submit({ tickers: ["AAPL"], budget: 5000 });
    });

    await waitFor(() => {
      expect(result.current.isSubmitting).toBe(false);
    });
  });
});
