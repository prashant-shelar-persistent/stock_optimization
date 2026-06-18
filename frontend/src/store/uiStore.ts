/**
 * Global UI state store powered by Zustand.
 *
 * Manages the active optimization run lifecycle:
 *   - currentRunId      — the run currently being tracked
 *   - optimizationResult — the completed result (set when WebSocket delivers "result")
 *   - isOptimizing      — true while a run is in progress
 *   - agentProgress     — ordered list of progress events from WebSocket
 *   - activeTab         — which comparison tab is selected in the dashboard
 *
 * React 19 notes
 * ──────────────
 * • Uses `devtools` middleware so every action is visible in Redux DevTools,
 *   which now integrates with the React 19 DevTools timeline.
 * • Uses `subscribeWithSelector` middleware so WebSocket handlers can
 *   subscribe to individual slices without triggering full-store re-renders.
 * • `useShallow` is re-exported here for consumers that select multiple
 *   fields at once; React 19's improved batching makes this even more
 *   effective at eliminating redundant renders.
 * • `uiStoreApi` is exported for use outside React components (e.g. in
 *   WebSocket event handlers) — the preferred React 19 pattern over
 *   accessing the store via a hook in a non-component context.
 */

import { create } from "zustand";
import { devtools, subscribeWithSelector } from "zustand/middleware";
import { useShallow } from "zustand/react/shallow";
import type {
  AgentProgressMessage,
  OptimizationRunDetail,
} from "@/types/api";

// ── Re-export useShallow for consumers ────────────────────────────────────────
export { useShallow };

// ── State shape ───────────────────────────────────────────────────────────────

export type ComparisonTab = "classical" | "qaoa" | "vqe";

interface UIState {
  /** The run ID currently being tracked (null when idle). */
  currentRunId: string | null;

  /** The completed optimization result (null until a run finishes). */
  optimizationResult: OptimizationRunDetail | null;

  /** True while an optimization run is in progress. */
  isOptimizing: boolean;

  /**
   * Ordered list of agent progress events received via WebSocket.
   * Appended to as the agent graph executes each node.
   */
  agentProgress: AgentProgressMessage[];

  /** Which comparison tab is currently selected in the dashboard. */
  activeTab: ComparisonTab;
}

// ── Actions ───────────────────────────────────────────────────────────────────

interface UIActions {
  /** Set the active run ID (called immediately after submitting an optimization). */
  setCurrentRunId: (runId: string | null) => void;

  /** Store the completed optimization result (called when WebSocket delivers "result"). */
  setOptimizationResult: (result: OptimizationRunDetail | null) => void;

  /** Toggle the in-progress flag. */
  setIsOptimizing: (value: boolean) => void;

  /**
   * Append a single agent progress event to the ordered list.
   * Duplicate events (same node + status) are silently ignored.
   */
  addAgentProgress: (message: AgentProgressMessage) => void;

  /** Clear all progress events (called when starting a new run). */
  resetProgress: () => void;

  /** Switch the active comparison tab. */
  setActiveTab: (tab: ComparisonTab) => void;

  /**
   * Convenience action: reset all run-related state and start tracking a new run.
   * Equivalent to calling resetProgress + setCurrentRunId + setIsOptimizing(true)
   * + setOptimizationResult(null) in sequence.
   */
  startNewRun: (runId: string) => void;
}

// ── Store ─────────────────────────────────────────────────────────────────────

export type UIStore = UIState & UIActions;

/**
 * The Zustand store instance.
 *
 * Middleware stack (innermost → outermost):
 *   1. `subscribeWithSelector` — enables `store.subscribe(selector, listener)`
 *      for WebSocket handlers that need to react to specific state slices.
 *   2. `devtools` — integrates with Redux DevTools Extension and the React 19
 *      DevTools timeline; each action is labelled for easy tracing.
 */
export const useUIStore = create<UIStore>()(
  devtools(
    subscribeWithSelector((set) => ({
      // ── Initial state ──────────────────────────────────────────────────────

      currentRunId: null,
      optimizationResult: null,
      isOptimizing: false,
      agentProgress: [],
      activeTab: "classical",

      // ── Actions ────────────────────────────────────────────────────────────

      setCurrentRunId: (runId) =>
        set({ currentRunId: runId }, false, "ui/setCurrentRunId"),

      setOptimizationResult: (result) =>
        set({ optimizationResult: result }, false, "ui/setOptimizationResult"),

      setIsOptimizing: (value) =>
        set({ isOptimizing: value }, false, "ui/setIsOptimizing"),

      addAgentProgress: (message) =>
        set(
          (state) => {
            // Deduplicate: skip if an identical node+status event already exists
            const isDuplicate = state.agentProgress.some(
              (p) => p.node === message.node && p.status === message.status,
            );
            if (isDuplicate) return state;
            return { agentProgress: [...state.agentProgress, message] };
          },
          false,
          "ui/addAgentProgress",
        ),

      resetProgress: () =>
        set({ agentProgress: [] }, false, "ui/resetProgress"),

      setActiveTab: (tab) =>
        set({ activeTab: tab }, false, "ui/setActiveTab"),

      startNewRun: (runId) =>
        set(
          {
            currentRunId: runId,
            isOptimizing: true,
            optimizationResult: null,
            agentProgress: [],
            activeTab: "classical",
          },
          false,
          "ui/startNewRun",
        ),
    })),
    {
      name: "UIStore",
      // Only enable devtools in development to avoid overhead in production
      enabled: !import.meta.env.PROD,
    },
  ),
);

/**
 * The raw Zustand store API — use this outside React components (e.g. in
 * WebSocket event handlers) to read or mutate state without hooks.
 *
 * @example
 * ```ts
 * // In a WebSocket handler (not a React component):
 * uiStoreApi.getState().addAgentProgress(message);
 * ```
 */
export const uiStoreApi = useUIStore;

// ── Selector helpers (stable references, avoids unnecessary re-renders) ───────

/** Select only the current run ID. */
export const selectCurrentRunId = (s: UIStore) => s.currentRunId;

/** Select only the optimization result. */
export const selectOptimizationResult = (s: UIStore) => s.optimizationResult;

/** Select only the isOptimizing flag. */
export const selectIsOptimizing = (s: UIStore) => s.isOptimizing;

/** Select only the agent progress list. */
export const selectAgentProgress = (s: UIStore) => s.agentProgress;

/** Select only the active comparison tab. */
export const selectActiveTab = (s: UIStore) => s.activeTab;
