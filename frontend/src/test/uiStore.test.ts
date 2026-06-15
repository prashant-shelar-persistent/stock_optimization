/**
 * Tests for @/store/uiStore
 *
 * Covers all actions and selectors:
 *   setCurrentRunId, setOptimizationResult, setIsOptimizing,
 *   addAgentProgress (with deduplication), resetProgress,
 *   setActiveTab, startNewRun, and all selector helpers.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { useUIStore } from "@/store/uiStore";
import {
  selectCurrentRunId,
  selectOptimizationResult,
  selectIsOptimizing,
  selectAgentProgress,
  selectActiveTab,
} from "@/store/uiStore";
import type { AgentProgressMessage, OptimizationRunDetail } from "@/types/api";

// Helper to get the raw store state (bypasses React hooks)
function getStore() {
  return useUIStore.getState();
}

// Reset store to initial state before each test
beforeEach(() => {
  useUIStore.setState({
    currentRunId: null,
    optimizationResult: null,
    isOptimizing: false,
    agentProgress: [],
    activeTab: "classical",
  });
});

// ── Initial state ─────────────────────────────────────────────────────────────

describe("initial state", () => {
  it("has null currentRunId", () => {
    expect(getStore().currentRunId).toBeNull();
  });

  it("has null optimizationResult", () => {
    expect(getStore().optimizationResult).toBeNull();
  });

  it("has isOptimizing = false", () => {
    expect(getStore().isOptimizing).toBe(false);
  });

  it("has empty agentProgress array", () => {
    expect(getStore().agentProgress).toEqual([]);
  });

  it("has activeTab = 'classical'", () => {
    expect(getStore().activeTab).toBe("classical");
  });
});

// ── setCurrentRunId ───────────────────────────────────────────────────────────

describe("setCurrentRunId", () => {
  it("sets a run ID", () => {
    getStore().setCurrentRunId("run-abc-123");
    expect(getStore().currentRunId).toBe("run-abc-123");
  });

  it("clears the run ID when passed null", () => {
    getStore().setCurrentRunId("run-abc-123");
    getStore().setCurrentRunId(null);
    expect(getStore().currentRunId).toBeNull();
  });
});

// ── setOptimizationResult ─────────────────────────────────────────────────────

describe("setOptimizationResult", () => {
  const mockResult: OptimizationRunDetail = {
    run_id: "run-xyz",
    status: "completed",
    tickers: ["AAPL", "MSFT"],
    budget: 10000,
    created_at: "2024-01-01T00:00:00Z",
  };

  it("stores the result", () => {
    getStore().setOptimizationResult(mockResult);
    expect(getStore().optimizationResult).toEqual(mockResult);
  });

  it("clears the result when passed null", () => {
    getStore().setOptimizationResult(mockResult);
    getStore().setOptimizationResult(null);
    expect(getStore().optimizationResult).toBeNull();
  });
});

// ── setIsOptimizing ───────────────────────────────────────────────────────────

describe("setIsOptimizing", () => {
  it("sets to true", () => {
    getStore().setIsOptimizing(true);
    expect(getStore().isOptimizing).toBe(true);
  });

  it("sets to false", () => {
    getStore().setIsOptimizing(true);
    getStore().setIsOptimizing(false);
    expect(getStore().isOptimizing).toBe(false);
  });
});

// ── addAgentProgress ──────────────────────────────────────────────────────────

describe("addAgentProgress", () => {
  const makeMsg = (
    node: AgentProgressMessage["node"],
    status: AgentProgressMessage["status"],
    message = "test",
  ): AgentProgressMessage => ({
    type: "progress",
    run_id: "run-1",
    node,
    status,
    message,
    timestamp: new Date().toISOString(),
  });

  it("appends a progress message", () => {
    const msg = makeMsg("data_fetch", "started");
    getStore().addAgentProgress(msg);
    expect(getStore().agentProgress).toHaveLength(1);
    expect(getStore().agentProgress[0]).toEqual(msg);
  });

  it("appends multiple distinct messages", () => {
    getStore().addAgentProgress(makeMsg("data_fetch", "started"));
    getStore().addAgentProgress(makeMsg("data_fetch", "completed"));
    expect(getStore().agentProgress).toHaveLength(2);
  });

  it("deduplicates: ignores a message with the same node+status", () => {
    const msg = makeMsg("data_fetch", "started");
    getStore().addAgentProgress(msg);
    getStore().addAgentProgress(msg); // duplicate
    expect(getStore().agentProgress).toHaveLength(1);
  });

  it("allows same node with different status (started then completed)", () => {
    getStore().addAgentProgress(makeMsg("data_fetch", "started"));
    getStore().addAgentProgress(makeMsg("data_fetch", "completed"));
    expect(getStore().agentProgress).toHaveLength(2);
    expect(getStore().agentProgress[0].status).toBe("started");
    expect(getStore().agentProgress[1].status).toBe("completed");
  });

  it("allows different nodes with same status", () => {
    getStore().addAgentProgress(makeMsg("data_fetch", "started"));
    getStore().addAgentProgress(makeMsg("constraint_validation", "started"));
    expect(getStore().agentProgress).toHaveLength(2);
  });
});

// ── resetProgress ─────────────────────────────────────────────────────────────

describe("resetProgress", () => {
  it("clears all progress events", () => {
    getStore().addAgentProgress({
      type: "progress",
      run_id: "r1",
      node: "data_fetch",
      status: "started",
      message: "fetching",
      timestamp: new Date().toISOString(),
    });
    expect(getStore().agentProgress).toHaveLength(1);

    getStore().resetProgress();
    expect(getStore().agentProgress).toEqual([]);
  });

  it("is a no-op when progress is already empty", () => {
    getStore().resetProgress();
    expect(getStore().agentProgress).toEqual([]);
  });
});

// ── setActiveTab ──────────────────────────────────────────────────────────────

describe("setActiveTab", () => {
  it("switches to qaoa tab", () => {
    getStore().setActiveTab("qaoa");
    expect(getStore().activeTab).toBe("qaoa");
  });

  it("switches to vqe tab", () => {
    getStore().setActiveTab("vqe");
    expect(getStore().activeTab).toBe("vqe");
  });

  it("switches back to classical tab", () => {
    getStore().setActiveTab("qaoa");
    getStore().setActiveTab("classical");
    expect(getStore().activeTab).toBe("classical");
  });
});

// ── startNewRun ───────────────────────────────────────────────────────────────

describe("startNewRun", () => {
  it("sets currentRunId", () => {
    getStore().startNewRun("run-new-1");
    expect(getStore().currentRunId).toBe("run-new-1");
  });

  it("sets isOptimizing to true", () => {
    getStore().startNewRun("run-new-1");
    expect(getStore().isOptimizing).toBe(true);
  });

  it("clears optimizationResult", () => {
    getStore().setOptimizationResult({
      run_id: "old",
      status: "completed",
      tickers: [],
      budget: 0,
      created_at: "",
    });
    getStore().startNewRun("run-new-1");
    expect(getStore().optimizationResult).toBeNull();
  });

  it("clears agentProgress", () => {
    getStore().addAgentProgress({
      type: "progress",
      run_id: "old",
      node: "data_fetch",
      status: "started",
      message: "old",
      timestamp: new Date().toISOString(),
    });
    getStore().startNewRun("run-new-1");
    expect(getStore().agentProgress).toEqual([]);
  });

  it("resets activeTab to 'classical'", () => {
    getStore().setActiveTab("vqe");
    getStore().startNewRun("run-new-1");
    expect(getStore().activeTab).toBe("classical");
  });
});

// ── Selector helpers ──────────────────────────────────────────────────────────

describe("selector helpers", () => {
  it("selectCurrentRunId returns currentRunId", () => {
    getStore().setCurrentRunId("sel-run");
    const state = getStore();
    expect(selectCurrentRunId(state)).toBe("sel-run");
  });

  it("selectOptimizationResult returns optimizationResult", () => {
    const result: OptimizationRunDetail = {
      run_id: "r",
      status: "completed",
      tickers: [],
      budget: 0,
      created_at: "",
    };
    getStore().setOptimizationResult(result);
    const state = getStore();
    expect(selectOptimizationResult(state)).toEqual(result);
  });

  it("selectIsOptimizing returns isOptimizing", () => {
    getStore().setIsOptimizing(true);
    const state = getStore();
    expect(selectIsOptimizing(state)).toBe(true);
  });

  it("selectAgentProgress returns agentProgress", () => {
    const state = getStore();
    expect(selectAgentProgress(state)).toEqual([]);
  });

  it("selectActiveTab returns activeTab", () => {
    getStore().setActiveTab("qaoa");
    const state = getStore();
    expect(selectActiveTab(state)).toBe("qaoa");
  });
});
