/**
 * Tests for @/hooks/useWebSocket
 *
 * Uses a mock WebSocket class to test connection lifecycle and message handling.
 *
 * React 18 strict mode double-invokes effects, creating multiple WebSocket
 * instances. We work around this by:
 *   1. Capturing the socket reference INSIDE the act() callback (after effects flush)
 *   2. Testing store-level effects (Zustand state) rather than hook-local state
 *      for message handling tests
 *   3. Testing connectionState via the Zustand store where possible
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useUIStore } from "@/store/uiStore";

// ── Mock WebSocket ────────────────────────────────────────────────────────────

class MockWebSocket {
  url: string;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  readyState = 0; // CONNECTING
  closedWith: { code?: number; reason?: string } | null = null;

  static instances: MockWebSocket[] = [];

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  static get last(): MockWebSocket {
    return MockWebSocket.instances[MockWebSocket.instances.length - 1];
  }

  close(code?: number, reason?: string) {
    this.closedWith = { code, reason };
    this.readyState = 3;
    if (this.onclose) {
      this.onclose({ code: code ?? 1000, reason: reason ?? "" } as CloseEvent);
    }
  }

  simulateMessage(data: unknown) {
    if (this.onmessage) {
      this.onmessage({ data: JSON.stringify(data) } as MessageEvent);
    }
  }

  simulateOpen() {
    this.readyState = 1;
    if (this.onopen) {
      this.onopen({} as Event);
    }
  }

  simulateError() {
    if (this.onerror) {
      this.onerror({} as Event);
    }
  }

  simulateClose(code = 1006) {
    this.readyState = 3;
    if (this.onclose) {
      this.onclose({ code } as CloseEvent);
    }
  }
}

// ── Mock API ──────────────────────────────────────────────────────────────────

vi.mock("@/lib/api", () => ({
  openProgressSocket: (runId: string) =>
    new MockWebSocket(`ws://test/${runId}`),
}));

const mockToast = vi.fn();
vi.mock("@/hooks/use-toast", () => ({
  useToast: () => ({ toast: mockToast }),
}));

// ── Setup / teardown ──────────────────────────────────────────────────────────

beforeEach(() => {
  MockWebSocket.instances = [];
  mockToast.mockClear();
  useUIStore.setState({
    currentRunId: null,
    optimizationResult: null,
    isOptimizing: false,
    agentProgress: [],
    activeTab: "classical",
  });
});

afterEach(() => {
  vi.clearAllMocks();
});

// ── Helper: get the active socket after effects have flushed ──────────────────
// React 18 strict mode creates multiple sockets; the last one is always active.
function getActiveSocket(): MockWebSocket {
  return MockWebSocket.last;
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("useWebSocket", () => {
  // ── Null runId ─────────────────────────────────────────────────────────────

  it("returns 'closed' state when runId is null", () => {
    const { result } = renderHook(() => useWebSocket(null));
    expect(result.current.connectionState).toBe("closed");
  });

  it("does not create a WebSocket when runId is null", () => {
    renderHook(() => useWebSocket(null));
    expect(MockWebSocket.instances).toHaveLength(0);
  });

  // ── Connection lifecycle ───────────────────────────────────────────────────

  it("creates at least one WebSocket when runId is provided", () => {
    renderHook(() => useWebSocket("run-123"));
    expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(1);
    // All created sockets should have the correct run ID in the URL
    expect(MockWebSocket.last.url).toContain("run-123");
  });

  it("returns 'connecting' state immediately after runId is set", () => {
    const { result } = renderHook(() => useWebSocket("run-123"));
    expect(result.current.connectionState).toBe("connecting");
  });

  // ── Message handling (tests Zustand store state, not hook-local state) ─────

  it("calls addAgentProgress on 'progress' message", () => {
    renderHook(() => useWebSocket("run-123"));

    // Get the active socket after all effects have flushed
    const ws = getActiveSocket();

    act(() => {
      ws.simulateMessage({
        type: "progress",
        run_id: "run-123",
        node: "data_fetch",
        status: "started",
        message: "Fetching data",
        timestamp: "2024-01-01T12:00:00Z",
      });
    });

    const { agentProgress } = useUIStore.getState();
    expect(agentProgress).toHaveLength(1);
    expect(agentProgress[0].node).toBe("data_fetch");
    expect(agentProgress[0].status).toBe("started");
    expect(agentProgress[0].message).toBe("Fetching data");
  });

  it("accumulates multiple progress messages", () => {
    renderHook(() => useWebSocket("run-123"));
    const ws = getActiveSocket();

    act(() => {
      ws.simulateMessage({
        type: "progress",
        run_id: "run-123",
        node: "data_fetch",
        status: "started",
        message: "Starting",
        timestamp: "2024-01-01T12:00:00Z",
      });
      ws.simulateMessage({
        type: "progress",
        run_id: "run-123",
        node: "data_fetch",
        status: "completed",
        message: "Done",
        timestamp: "2024-01-01T12:00:01Z",
      });
    });

    const { agentProgress } = useUIStore.getState();
    expect(agentProgress).toHaveLength(2);
    expect(agentProgress[0].status).toBe("started");
    expect(agentProgress[1].status).toBe("completed");
  });

  it("calls setOptimizationResult and setIsOptimizing(false) on 'result' message", () => {
    useUIStore.setState({ isOptimizing: true });

    renderHook(() => useWebSocket("run-123"));
    const ws = getActiveSocket();

    const mockResult = {
      run_id: "run-123",
      status: "completed",
      tickers: ["AAPL"],
      budget: 5000,
      created_at: "2024-01-01T00:00:00Z",
    };

    act(() => {
      ws.simulateMessage({
        type: "result",
        run_id: "run-123",
        result: mockResult,
      });
    });

    const state = useUIStore.getState();
    expect(state.optimizationResult).toEqual(mockResult);
    expect(state.isOptimizing).toBe(false);
  });

  it("sets isOptimizing(false) on 'error' message", () => {
    useUIStore.setState({ isOptimizing: true });

    renderHook(() => useWebSocket("run-123"));
    const ws = getActiveSocket();

    act(() => {
      ws.simulateMessage({
        type: "error",
        run_id: "run-123",
        error_code: "OPTIMIZATION_FAILED",
        message: "Solver failed",
      });
    });

    expect(useUIStore.getState().isOptimizing).toBe(false);
  });

  it("ignores malformed (non-JSON) messages gracefully", () => {
    renderHook(() => useWebSocket("run-123"));
    const ws = getActiveSocket();

    act(() => {
      if (ws.onmessage) {
        ws.onmessage({ data: "not valid json {{{" } as MessageEvent);
      }
    });

    // No crash, store unchanged
    expect(useUIStore.getState().agentProgress).toHaveLength(0);
  });

  // ── Cleanup ────────────────────────────────────────────────────────────────

  it("closes the WebSocket when runId changes to null", () => {
    const { rerender } = renderHook(
      ({ runId }: { runId: string | null }) => useWebSocket(runId),
      { initialProps: { runId: "run-123" as string | null } },
    );

    // Capture the active socket before rerender
    const activeWs = getActiveSocket();

    act(() => {
      rerender({ runId: null });
    });

    // The previously active WebSocket should have been closed
    expect(activeWs.closedWith).not.toBeNull();
  });

  it("creates a new WebSocket when runId changes to a different value", () => {
    const { rerender } = renderHook(
      ({ runId }: { runId: string }) => useWebSocket(runId),
      { initialProps: { runId: "run-old" } },
    );

    // All sockets so far should be for run-old
    const oldInstances = MockWebSocket.instances.length;
    expect(MockWebSocket.last.url).toContain("run-old");

    act(() => {
      rerender({ runId: "run-new" });
    });

    // More sockets should have been created, and the last one is for run-new
    expect(MockWebSocket.instances.length).toBeGreaterThan(oldInstances);
    expect(MockWebSocket.last.url).toContain("run-new");
  });

  // ── Reconnection ───────────────────────────────────────────────────────────

  it("attempts reconnection on unexpected close (non-1000 code)", () => {
    vi.useFakeTimers();

    try {
      renderHook(() => useWebSocket("run-123"));
      const ws = getActiveSocket();
      const countBefore = MockWebSocket.instances.length;

      // Simulate unexpected close
      act(() => {
        ws.simulateClose(1006);
      });

      // Advance timer to trigger reconnect (2000ms * 1 = 2000ms)
      act(() => {
        vi.advanceTimersByTime(2100);
      });

      // A new WebSocket should have been created
      expect(MockWebSocket.instances.length).toBeGreaterThan(countBefore);
    } finally {
      vi.useRealTimers();
    }
  });

  it("does not retry after normal close (code 1000)", () => {
    vi.useFakeTimers();

    try {
      renderHook(() => useWebSocket("run-123"));
      const ws = getActiveSocket();
      const countBefore = MockWebSocket.instances.length;

      act(() => {
        ws.close(1000);
      });

      // Advance timers well past retry delay — no retry should fire
      act(() => {
        vi.advanceTimersByTime(10000);
      });

      // No new WebSocket should have been created after a normal close
      expect(MockWebSocket.instances.length).toBe(countBefore);
    } finally {
      vi.useRealTimers();
    }
  });
});
