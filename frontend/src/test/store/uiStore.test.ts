/**
 * Tests for @/store/uiStore
 *
 * This file mirrors the existing src/test/uiStore.test.ts but lives in the
 * new subdirectory layout (src/test/store/). It extends coverage with
 * additional edge-case scenarios and integration with the fixtures module.
 *
 * Covers:
 *   - Initial state verification
 *   - All action creators (setCurrentRunId, setOptimizationResult,
 *     setIsOptimizing, addAgentProgress, resetProgress, setActiveTab,
 *     startNewRun)
 *   - Deduplication logic in addAgentProgress
 *   - Selector helpers (selectCurrentRunId, selectOptimizationResult,
 *     selectIsOptimizing, selectAgentProgress, selectActiveTab)
 *   - State isolation between tests (beforeEach reset)
 */

import { describe, it, expect, beforeEach } from "vitest";
import {
  useUIStore,
  selectCurrentRunId,
  selectOptimizationResult,
  selectIsOptimizing,
  selectAgentProgress,
  selectActiveTab,
} from "@/store/uiStore";
import type { OptimizationRunDetail } from "@/types/api";
import {
  makeProgressMessage,
  COMPLETED_RUN_DETAIL,
  FULL_PIPELINE_PROGRESS,
} from "@/test/fixtures";

// ── Helpers ──────────────────────────────────────────────────────────────────

/** Access the raw Zustand store state without React hooks. */
function getStore() {
  return useUIStore.getState();
}

/** Reset the store to its initial state before each test. */
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
  it("currentRunId is null", () => {
    expect(getStore().currentRunId).toBeNull();
  });

  it("optimizationResult is null", () => {
    expect(getStore().optimizationResult).toBeNull();
  });

  it("isOptimizing is false", () => {
    expect(getStore().isOptimizing).toBe(false);
  });

  it("agentProgress is an empty array", () => {
    expect(getStore().agentProgress).toEqual([]);
    expect(getStore().agentProgress).toHaveLength(0);
  });

  it("activeTab defaults to 'classical'", () => {
    expect(getStore().activeTab).toBe("classical");
  });
});

// ── setCurrentRunId ───────────────────────────────────────────────────────────

describe("setCurrentRunId", () => {
  it("sets a string run ID", () => {
    getStore().setCurrentRunId("run-abc-123");
    expect(getStore().currentRunId).toBe("run-abc-123");
  });

  it("overwrites an existing run ID", () => {
    getStore().setCurrentRunId("run-old");
    getStore().setCurrentRunId("run-new");
    expect(getStore().currentRunId).toBe("run-new");
  });

  it("clears the run ID when passed null", () => {
    getStore().setCurrentRunId("run-abc-123");
    getStore().setCurrentRunId(null);
    expect(getStore().currentRunId).toBeNull();
  });

  it("does not affect other state fields", () => {
    getStore().setIsOptimizing(true);
    getStore().setCurrentRunId("run-xyz");
    expect(getStore().isOptimizing).toBe(true);
  });
});

// ── setOptimizationResult ─────────────────────────────────────────────────────

describe("setOptimizationResult", () => {
  it("stores a complete OptimizationRunDetail", () => {
    getStore().setOptimizationResult(COMPLETED_RUN_DETAIL);
    expect(getStore().optimizationResult).toEqual(COMPLETED_RUN_DETAIL);
  });

  it("stores the run_id correctly", () => {
    getStore().setOptimizationResult(COMPLETED_RUN_DETAIL);
    expect(getStore().optimizationResult?.run_id).toBe("run-fixture-001");
  });

  it("stores the status correctly", () => {
    getStore().setOptimizationResult(COMPLETED_RUN_DETAIL);
    expect(getStore().optimizationResult?.status).toBe("completed");
  });

  it("clears the result when passed null", () => {
    getStore().setOptimizationResult(COMPLETED_RUN_DETAIL);
    getStore().setOptimizationResult(null);
    expect(getStore().optimizationResult).toBeNull();
  });

  it("overwrites a previous result", () => {
    const first: OptimizationRunDetail = {
      run_id: "run-first",
      status: "completed",
      tickers: ["AAPL"],
      budget: 1000,
      created_at: "2024-01-01T00:00:00Z",
    };
    const second: OptimizationRunDetail = {
      run_id: "run-second",
      status: "completed",
      tickers: ["MSFT"],
      budget: 2000,
      created_at: "2024-01-02T00:00:00Z",
    };
    getStore().setOptimizationResult(first);
    getStore().setOptimizationResult(second);
    expect(getStore().optimizationResult?.run_id).toBe("run-second");
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

  it("is idempotent when already false", () => {
    getStore().setIsOptimizing(false);
    expect(getStore().isOptimizing).toBe(false);
  });

  it("is idempotent when already true", () => {
    getStore().setIsOptimizing(true);
    getStore().setIsOptimizing(true);
    expect(getStore().isOptimizing).toBe(true);
  });
});

// ── addAgentProgress ──────────────────────────────────────────────────────────

describe("addAgentProgress", () => {
  it("appends a single progress message", () => {
    const msg = makeProgressMessage("data_fetch", "started");
    getStore().addAgentProgress(msg);
    expect(getStore().agentProgress).toHaveLength(1);
    expect(getStore().agentProgress[0]).toEqual(msg);
  });

  it("appends multiple distinct messages in order", () => {
    const msg1 = makeProgressMessage("data_fetch", "started");
    const msg2 = makeProgressMessage("data_fetch", "completed");
    const msg3 = makeProgressMessage("constraint_validation", "started");
    getStore().addAgentProgress(msg1);
    getStore().addAgentProgress(msg2);
    getStore().addAgentProgress(msg3);
    expect(getStore().agentProgress).toHaveLength(3);
    expect(getStore().agentProgress[0].node).toBe("data_fetch");
    expect(getStore().agentProgress[0].status).toBe("started");
    expect(getStore().agentProgress[1].status).toBe("completed");
    expect(getStore().agentProgress[2].node).toBe("constraint_validation");
  });

  it("deduplicates: ignores a message with the same node+status", () => {
    const msg = makeProgressMessage("data_fetch", "started");
    getStore().addAgentProgress(msg);
    getStore().addAgentProgress(msg); // exact duplicate
    expect(getStore().agentProgress).toHaveLength(1);
  });

  it("deduplicates: ignores a different message object with same node+status", () => {
    const msg1 = makeProgressMessage("data_fetch", "started", {
      message: "First message",
    });
    const msg2 = makeProgressMessage("data_fetch", "started", {
      message: "Second message (different text, same node+status)",
    });
    getStore().addAgentProgress(msg1);
    getStore().addAgentProgress(msg2);
    // Only the first should be kept
    expect(getStore().agentProgress).toHaveLength(1);
    expect(getStore().agentProgress[0].message).toBe("First message");
  });

  it("allows same node with different statuses (started → completed)", () => {
    getStore().addAgentProgress(makeProgressMessage("data_fetch", "started"));
    getStore().addAgentProgress(makeProgressMessage("data_fetch", "completed"));
    expect(getStore().agentProgress).toHaveLength(2);
    expect(getStore().agentProgress[0].status).toBe("started");
    expect(getStore().agentProgress[1].status).toBe("completed");
  });

  it("allows same node with failed status after started", () => {
    getStore().addAgentProgress(makeProgressMessage("data_fetch", "started"));
    getStore().addAgentProgress(makeProgressMessage("data_fetch", "failed"));
    expect(getStore().agentProgress).toHaveLength(2);
    expect(getStore().agentProgress[1].status).toBe("failed");
  });

  it("allows different nodes with the same status", () => {
    getStore().addAgentProgress(makeProgressMessage("data_fetch", "started"));
    getStore().addAgentProgress(
      makeProgressMessage("constraint_validation", "started"),
    );
    expect(getStore().agentProgress).toHaveLength(2);
  });

  it("handles a full pipeline of 12 messages (6 nodes × 2 statuses)", () => {
    FULL_PIPELINE_PROGRESS.forEach((msg) => getStore().addAgentProgress(msg));
    expect(getStore().agentProgress).toHaveLength(12);
  });
});

// ── resetProgress ─────────────────────────────────────────────────────────────

describe("resetProgress", () => {
  it("clears all progress events", () => {
    getStore().addAgentProgress(makeProgressMessage("data_fetch", "started"));
    getStore().addAgentProgress(makeProgressMessage("data_fetch", "completed"));
    expect(getStore().agentProgress).toHaveLength(2);

    getStore().resetProgress();
    expect(getStore().agentProgress).toEqual([]);
  });

  it("is a no-op when progress is already empty", () => {
    getStore().resetProgress();
    expect(getStore().agentProgress).toEqual([]);
  });

  it("does not affect other state fields", () => {
    getStore().setCurrentRunId("run-xyz");
    getStore().setIsOptimizing(true);
    getStore().addAgentProgress(makeProgressMessage("data_fetch", "started"));

    getStore().resetProgress();

    expect(getStore().currentRunId).toBe("run-xyz");
    expect(getStore().isOptimizing).toBe(true);
  });
});

// ── setActiveTab ──────────────────────────────────────────────────────────────

describe("setActiveTab", () => {
  it("switches to 'qaoa' tab", () => {
    getStore().setActiveTab("qaoa");
    expect(getStore().activeTab).toBe("qaoa");
  });

  it("switches to 'vqe' tab", () => {
    getStore().setActiveTab("vqe");
    expect(getStore().activeTab).toBe("vqe");
  });

  it("switches back to 'classical' tab", () => {
    getStore().setActiveTab("qaoa");
    getStore().setActiveTab("classical");
    expect(getStore().activeTab).toBe("classical");
  });

  it("is idempotent when already on the same tab", () => {
    getStore().setActiveTab("qaoa");
    getStore().setActiveTab("qaoa");
    expect(getStore().activeTab).toBe("qaoa");
  });
});

// ── startNewRun ───────────────────────────────────────────────────────────────

describe("startNewRun", () => {
  it("sets currentRunId to the provided run ID", () => {
    getStore().startNewRun("run-new-001");
    expect(getStore().currentRunId).toBe("run-new-001");
  });

  it("sets isOptimizing to true", () => {
    getStore().startNewRun("run-new-001");
    expect(getStore().isOptimizing).toBe(true);
  });

  it("clears optimizationResult", () => {
    getStore().setOptimizationResult(COMPLETED_RUN_DETAIL);
    getStore().startNewRun("run-new-001");
    expect(getStore().optimizationResult).toBeNull();
  });

  it("clears agentProgress", () => {
    getStore().addAgentProgress(makeProgressMessage("data_fetch", "started"));
    getStore().startNewRun("run-new-001");
    expect(getStore().agentProgress).toEqual([]);
  });

  it("resets activeTab to 'classical'", () => {
    getStore().setActiveTab("vqe");
    getStore().startNewRun("run-new-001");
    expect(getStore().activeTab).toBe("classical");
  });

  it("atomically updates all fields in a single state transition", () => {
    // Set up a dirty state
    getStore().setCurrentRunId("run-old");
    getStore().setIsOptimizing(false);
    getStore().setOptimizationResult(COMPLETED_RUN_DETAIL);
    getStore().addAgentProgress(makeProgressMessage("data_fetch", "started"));
    getStore().setActiveTab("qaoa");

    // startNewRun should reset everything atomically
    getStore().startNewRun("run-brand-new");

    const state = getStore();
    expect(state.currentRunId).toBe("run-brand-new");
    expect(state.isOptimizing).toBe(true);
    expect(state.optimizationResult).toBeNull();
    expect(state.agentProgress).toEqual([]);
    expect(state.activeTab).toBe("classical");
  });
});

// ── Selector helpers ──────────────────────────────────────────────────────────

describe("selector helpers", () => {
  it("selectCurrentRunId returns currentRunId", () => {
    getStore().setCurrentRunId("sel-run-001");
    const state = getStore();
    expect(selectCurrentRunId(state)).toBe("sel-run-001");
  });

  it("selectCurrentRunId returns null when no run is active", () => {
    const state = getStore();
    expect(selectCurrentRunId(state)).toBeNull();
  });

  it("selectOptimizationResult returns the stored result", () => {
    getStore().setOptimizationResult(COMPLETED_RUN_DETAIL);
    const state = getStore();
    expect(selectOptimizationResult(state)).toEqual(COMPLETED_RUN_DETAIL);
  });

  it("selectOptimizationResult returns null when no result is stored", () => {
    const state = getStore();
    expect(selectOptimizationResult(state)).toBeNull();
  });

  it("selectIsOptimizing returns true when optimizing", () => {
    getStore().setIsOptimizing(true);
    const state = getStore();
    expect(selectIsOptimizing(state)).toBe(true);
  });

  it("selectIsOptimizing returns false when not optimizing", () => {
    const state = getStore();
    expect(selectIsOptimizing(state)).toBe(false);
  });

  it("selectAgentProgress returns the progress array", () => {
    const msg = makeProgressMessage("data_fetch", "started");
    getStore().addAgentProgress(msg);
    const state = getStore();
    expect(selectAgentProgress(state)).toHaveLength(1);
    expect(selectAgentProgress(state)[0]).toEqual(msg);
  });

  it("selectAgentProgress returns empty array initially", () => {
    const state = getStore();
    expect(selectAgentProgress(state)).toEqual([]);
  });

  it("selectActiveTab returns the current tab", () => {
    getStore().setActiveTab("qaoa");
    const state = getStore();
    expect(selectActiveTab(state)).toBe("qaoa");
  });

  it("selectActiveTab returns 'classical' by default", () => {
    const state = getStore();
    expect(selectActiveTab(state)).toBe("classical");
  });
});

// ── State isolation ───────────────────────────────────────────────────────────

describe("state isolation between tests", () => {
  it("each test starts with a clean slate (currentRunId is null)", () => {
    // This test verifies that the beforeEach reset works correctly.
    // If state leaked from a previous test, this would fail.
    expect(getStore().currentRunId).toBeNull();
  });

  it("each test starts with a clean slate (agentProgress is empty)", () => {
    expect(getStore().agentProgress).toHaveLength(0);
  });

  it("each test starts with a clean slate (isOptimizing is false)", () => {
    expect(getStore().isOptimizing).toBe(false);
  });
});
