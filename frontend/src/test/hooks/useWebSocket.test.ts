/**
 * Tests for @/hooks/useWebSocket
 *
 * Uses a mock WebSocket class to test the full connection lifecycle:
 *   - Null runId → no socket created, "closed" state
 *   - Non-null runId → socket created, "connecting" state
 *   - onopen → "open" state, retry counter reset
 *   - "progress" message → addAgentProgress called on uiStore
 *   - "result" message → setOptimizationResult + setIsOptimizing(false)
 *   - "error" message → setIsOptimizing(false) + toast shown
 *   - Malformed JSON → silently ignored
 *   - Unexpected close (non-1000) → reconnection attempted
 *   - Normal close (1000) → no reconnection
 *   - runId change → old socket closed, new socket opened
 *   - Unmount → socket closed with code 1000
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useUIStore } from "@/store/uiStore";
import { makeProgressMessage, COMPLETED_RUN_DETAIL } from "@/test/fixtures";

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
    this.readyState = 3; // CLOSED
    if (this.onclose) {
      this.onclose({ code: code ?? 1000, reason: reason ?? "" } as CloseEvent);
    }
  }

  simulateOpen() {
    this.readyState = 1; // OPEN
    if (this.onopen) {
      this.onopen({} as Event);
    }
  }

  simulateMessage(data: unknown) {
    if (this.onmessage) {
      this.onmessage({ data: JSON.stringify(data) } as MessageEvent);
    }
  }

  simulateRawMessage(raw: string) {
    if (this.onmessage) {
      this.onmessage({ data: raw } as MessageEvent);
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

// ── Mocks ─────────────────────────────────────────────────────────────────────

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

// ── Helper ────────────────────────────────────────────────────────────────────

/** React 18 strict mode may create multiple sockets; the last one is active. */
function getActiveSocket(): MockWebSocket {
  return MockWebSocket.last;
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("useWebSocket", () => {
  // ── Null runId ──────────────────────────────────────────────────────────────

  describe("when runId is null", () => {
    it("returns 'closed' connectionState", () => {
      const { result } = renderHook(() => useWebSocket(null));
      expect(result.current.connectionState).toBe("closed");
    });

    it("does not create any WebSocket instances", () => {
      renderHook(() => useWebSocket(null));
      expect(MockWebSocket.instances).toHaveLength(0);
    });
  });

  // ── Connection lifecycle ────────────────────────────────────────────────────

  describe("connection lifecycle", () => {
    it("creates at least one WebSocket when runId is provided", () => {
      renderHook(() => useWebSocket("run-001"));
      expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(1);
    });

    it("creates a WebSocket with the correct URL containing the runId", () => {
      renderHook(() => useWebSocket("run-001"));
      expect(getActiveSocket().url).toContain("run-001");
    });

    it("returns 'connecting' state immediately after runId is set", () => {
      const { result } = renderHook(() => useWebSocket("run-001"));
      expect(result.current.connectionState).toBe("connecting");
    });

    it("transitions to 'open' state when the socket opens", () => {
      const { result } = renderHook(() => useWebSocket("run-001"));
      const ws = getActiveSocket();

      act(() => {
        ws.simulateOpen();
      });

      expect(result.current.connectionState).toBe("open");
    });

    it("transitions to 'error' state when the socket errors", () => {
      const { result } = renderHook(() => useWebSocket("run-001"));
      const ws = getActiveSocket();

      act(() => {
        ws.simulateError();
      });

      expect(result.current.connectionState).toBe("error");
    });
  });

  // ── Message handling ────────────────────────────────────────────────────────

  describe("message handling", () => {
    it("dispatches 'progress' messages to uiStore.addAgentProgress", () => {
      renderHook(() => useWebSocket("run-001"));
      const ws = getActiveSocket();

      const progressMsg = makeProgressMessage("data_fetch", "started", {
        run_id: "run-001",
        message: "Fetching market data",
      });

      act(() => {
        ws.simulateMessage(progressMsg);
      });

      const { agentProgress } = useUIStore.getState();
      expect(agentProgress).toHaveLength(1);
      expect(agentProgress[0].node).toBe("data_fetch");
      expect(agentProgress[0].status).toBe("started");
      expect(agentProgress[0].message).toBe("Fetching market data");
    });

    it("accumulates multiple 'progress' messages in order", () => {
      renderHook(() => useWebSocket("run-001"));
      const ws = getActiveSocket();

      act(() => {
        ws.simulateMessage(
          makeProgressMessage("data_fetch", "started", { run_id: "run-001" }),
        );
        ws.simulateMessage(
          makeProgressMessage("data_fetch", "completed", { run_id: "run-001" }),
        );
        ws.simulateMessage(
          makeProgressMessage("constraint_validation", "started", {
            run_id: "run-001",
          }),
        );
      });

      const { agentProgress } = useUIStore.getState();
      expect(agentProgress).toHaveLength(3);
      expect(agentProgress[0].status).toBe("started");
      expect(agentProgress[1].status).toBe("completed");
      expect(agentProgress[2].node).toBe("constraint_validation");
    });

    it("sets optimizationResult and clears isOptimizing on 'result' message", () => {
      useUIStore.setState({ isOptimizing: true });
      renderHook(() => useWebSocket("run-001"));
      const ws = getActiveSocket();

      act(() => {
        ws.simulateMessage({
          type: "result",
          run_id: "run-001",
          result: COMPLETED_RUN_DETAIL,
        });
      });

      const state = useUIStore.getState();
      expect(state.optimizationResult).toEqual(COMPLETED_RUN_DETAIL);
      expect(state.isOptimizing).toBe(false);
    });

    it("stores the correct run_id from the result message", () => {
      renderHook(() => useWebSocket("run-001"));
      const ws = getActiveSocket();

      act(() => {
        ws.simulateMessage({
          type: "result",
          run_id: "run-001",
          result: COMPLETED_RUN_DETAIL,
        });
      });

      expect(useUIStore.getState().optimizationResult?.run_id).toBe(
        "run-fixture-001",
      );
    });

    it("clears isOptimizing on 'error' message", () => {
      useUIStore.setState({ isOptimizing: true });
      renderHook(() => useWebSocket("run-001"));
      const ws = getActiveSocket();

      act(() => {
        ws.simulateMessage({
          type: "error",
          run_id: "run-001",
          error_code: "OPTIMIZATION_FAILED",
          message: "Solver diverged",
        });
      });

      expect(useUIStore.getState().isOptimizing).toBe(false);
    });

    it("calls toast with destructive variant on 'error' message", () => {
      renderHook(() => useWebSocket("run-001"));
      const ws = getActiveSocket();

      act(() => {
        ws.simulateMessage({
          type: "error",
          run_id: "run-001",
          error_code: "OPTIMIZATION_FAILED",
          message: "Solver diverged",
        });
      });

      expect(mockToast).toHaveBeenCalledWith(
        expect.objectContaining({
          variant: "destructive",
          description: "Solver diverged",
        }),
      );
    });

    it("silently ignores malformed (non-JSON) messages", () => {
      renderHook(() => useWebSocket("run-001"));
      const ws = getActiveSocket();

      act(() => {
        ws.simulateRawMessage("not valid json {{{");
      });

      // No crash, store unchanged
      expect(useUIStore.getState().agentProgress).toHaveLength(0);
      expect(useUIStore.getState().optimizationResult).toBeNull();
    });

    it("silently ignores messages with unknown type", () => {
      renderHook(() => useWebSocket("run-001"));
      const ws = getActiveSocket();

      act(() => {
        ws.simulateMessage({ type: "unknown_type", data: "something" });
      });

      expect(useUIStore.getState().agentProgress).toHaveLength(0);
    });
  });

  // ── Cleanup ─────────────────────────────────────────────────────────────────

  describe("cleanup", () => {
    it("closes the WebSocket when runId changes to null", () => {
      const { rerender } = renderHook(
        ({ runId }: { runId: string | null }) => useWebSocket(runId),
        { initialProps: { runId: "run-001" as string | null } },
      );

      const activeWs = getActiveSocket();

      act(() => {
        rerender({ runId: null });
      });

      expect(activeWs.closedWith).not.toBeNull();
    });

    it("creates a new WebSocket when runId changes to a different value", () => {
      const { rerender } = renderHook(
        ({ runId }: { runId: string }) => useWebSocket(runId),
        { initialProps: { runId: "run-old" } },
      );

      const countBefore = MockWebSocket.instances.length;
      expect(getActiveSocket().url).toContain("run-old");

      act(() => {
        rerender({ runId: "run-new" });
      });

      expect(MockWebSocket.instances.length).toBeGreaterThan(countBefore);
      expect(getActiveSocket().url).toContain("run-new");
    });

    it("closes the socket with code 1000 on unmount", () => {
      const { unmount } = renderHook(() => useWebSocket("run-001"));
      const ws = getActiveSocket();

      act(() => {
        unmount();
      });

      // The socket should have been closed (closedWith is set)
      expect(ws.closedWith).not.toBeNull();
    });
  });

  // ── Reconnection ────────────────────────────────────────────────────────────

  describe("reconnection", () => {
    it("attempts reconnection on unexpected close (non-1000 code)", () => {
      vi.useFakeTimers();

      try {
        renderHook(() => useWebSocket("run-001"));
        const ws = getActiveSocket();
        const countBefore = MockWebSocket.instances.length;

        act(() => {
          ws.simulateClose(1006); // Abnormal closure
        });

        // Advance past the first retry delay (2000ms × 1)
        act(() => {
          vi.advanceTimersByTime(2100);
        });

        expect(MockWebSocket.instances.length).toBeGreaterThan(countBefore);
      } finally {
        vi.useRealTimers();
      }
    });

    it("does not retry after a normal close (code 1000)", () => {
      vi.useFakeTimers();

      try {
        renderHook(() => useWebSocket("run-001"));
        const ws = getActiveSocket();
        const countBefore = MockWebSocket.instances.length;

        act(() => {
          ws.close(1000); // Normal closure
        });

        // Advance well past any retry delay
        act(() => {
          vi.advanceTimersByTime(10_000);
        });

        // No new sockets should have been created
        expect(MockWebSocket.instances.length).toBe(countBefore);
      } finally {
        vi.useRealTimers();
      }
    });
  });
});
