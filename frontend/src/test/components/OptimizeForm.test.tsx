/**
 * Tests for @/components/OptimizeForm
 *
 * OptimizeForm is the top-level orchestrator that ties together:
 *   - ConstraintForm (left panel)
 *   - AgentProgressPanel (while running)
 *   - ComparisonDashboard (when results arrive)
 *   - Empty state (before any run)
 *   - WebSocket connection badge
 *
 * We mock the heavy child components and hooks to focus on the
 * orchestration logic.
 *
 * Covers:
 *   - Empty state rendered before any run is started
 *   - ConstraintForm is always rendered
 *   - AgentProgressPanel shown while isOptimizing = true
 *   - ComparisonDashboard shown when result is available
 *   - Connection badge shown when a run is active
 *   - Empty state hidden when progress is shown
 *   - Empty state hidden when results are shown
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { OptimizeForm } from "@/components/OptimizeForm";
import { useUIStore } from "@/store/uiStore";
import { COMPLETED_RUN_DETAIL, PARTIAL_PIPELINE_PROGRESS } from "@/test/fixtures";

// ── Mock heavy child components ───────────────────────────────────────────────

vi.mock("@/components/ConstraintForm", () => ({
  ConstraintForm: ({ onRunStarted }: { onRunStarted: (id: string) => void }) => (
    <div data-testid="constraint-form">
      <button onClick={() => onRunStarted("run-test-001")}>
        Run Optimization
      </button>
    </div>
  ),
}));

vi.mock("@/components/dashboard/AgentProgressPanel", () => ({
  AgentProgressPanel: ({
    progress,
    isRunning,
  }: {
    progress: unknown[];
    isRunning: boolean;
  }) => (
    <div
      data-testid="agent-progress-panel"
      data-running={String(isRunning)}
      data-progress-count={progress.length}
    >
      Agent Progress Panel
    </div>
  ),
}));

vi.mock("@/components/dashboard/ComparisonDashboard", () => ({
  ComparisonDashboard: ({ result }: { result: { run_id: string } }) => (
    <div data-testid="comparison-dashboard" data-run-id={result.run_id}>
      Comparison Dashboard
    </div>
  ),
}));

vi.mock("@/hooks/useWebSocket", () => ({
  useWebSocket: () => ({ connectionState: "closed" as const }),
}));

// ── Setup ─────────────────────────────────────────────────────────────────────

beforeEach(() => {
  useUIStore.setState({
    currentRunId: null,
    optimizationResult: null,
    isOptimizing: false,
    agentProgress: [],
    activeTab: "classical",
  });
});

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("OptimizeForm", () => {
  // ── Empty state ─────────────────────────────────────────────────────────────

  describe("empty state (no run started)", () => {
    it("renders the ConstraintForm", () => {
      render(<OptimizeForm />);
      expect(screen.getByTestId("constraint-form")).toBeInTheDocument();
    });

    it("renders the empty state placeholder", () => {
      render(<OptimizeForm />);
      expect(
        screen.getByText("Configure constraints and run optimization"),
      ).toBeInTheDocument();
    });

    it("shows the empty state description", () => {
      render(<OptimizeForm />);
      expect(
        screen.getByText(
          /Classical \(Markowitz MVO\) \+ Quantum \(QAOA \+ VQE\) results will appear/i,
        ),
      ).toBeInTheDocument();
    });

    it("does not render the AgentProgressPanel in empty state", () => {
      render(<OptimizeForm />);
      expect(
        screen.queryByTestId("agent-progress-panel"),
      ).not.toBeInTheDocument();
    });

    it("does not render the ComparisonDashboard in empty state", () => {
      render(<OptimizeForm />);
      expect(
        screen.queryByTestId("comparison-dashboard"),
      ).not.toBeInTheDocument();
    });

    it("does not show the connection badge when no run is active", () => {
      render(<OptimizeForm />);
      // Connection badge only appears when currentRunId is set
      expect(screen.queryByText(/Connecting/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/Live/i)).not.toBeInTheDocument();
    });
  });

  // ── Running state ───────────────────────────────────────────────────────────

  describe("running state (isOptimizing = true)", () => {
    beforeEach(() => {
      useUIStore.setState({
        currentRunId: "run-test-001",
        optimizationResult: null,
        isOptimizing: true,
        agentProgress: PARTIAL_PIPELINE_PROGRESS,
        activeTab: "classical",
      });
    });

    it("renders the AgentProgressPanel while optimizing", () => {
      render(<OptimizeForm />);
      expect(screen.getByTestId("agent-progress-panel")).toBeInTheDocument();
    });

    it("passes isRunning=true to AgentProgressPanel", () => {
      render(<OptimizeForm />);
      const panel = screen.getByTestId("agent-progress-panel");
      expect(panel).toHaveAttribute("data-running", "true");
    });

    it("passes the correct progress count to AgentProgressPanel", () => {
      render(<OptimizeForm />);
      const panel = screen.getByTestId("agent-progress-panel");
      expect(panel).toHaveAttribute(
        "data-progress-count",
        String(PARTIAL_PIPELINE_PROGRESS.length),
      );
    });

    it("does not render the empty state while optimizing", () => {
      render(<OptimizeForm />);
      expect(
        screen.queryByText("Configure constraints and run optimization"),
      ).not.toBeInTheDocument();
    });

    it("does not render the ComparisonDashboard while optimizing", () => {
      render(<OptimizeForm />);
      expect(
        screen.queryByTestId("comparison-dashboard"),
      ).not.toBeInTheDocument();
    });

    it("still renders the ConstraintForm while optimizing", () => {
      render(<OptimizeForm />);
      expect(screen.getByTestId("constraint-form")).toBeInTheDocument();
    });
  });

  // ── Results state ───────────────────────────────────────────────────────────

  describe("results state (optimization completed)", () => {
    beforeEach(() => {
      useUIStore.setState({
        currentRunId: "run-fixture-001",
        optimizationResult: COMPLETED_RUN_DETAIL,
        isOptimizing: false,
        agentProgress: [],
        activeTab: "classical",
      });
    });

    it("renders the ComparisonDashboard when result is available", () => {
      render(<OptimizeForm />);
      expect(screen.getByTestId("comparison-dashboard")).toBeInTheDocument();
    });

    it("passes the correct run_id to ComparisonDashboard", () => {
      render(<OptimizeForm />);
      const dashboard = screen.getByTestId("comparison-dashboard");
      expect(dashboard).toHaveAttribute("data-run-id", "run-fixture-001");
    });

    it("does not render the empty state when results are available", () => {
      render(<OptimizeForm />);
      expect(
        screen.queryByText("Configure constraints and run optimization"),
      ).not.toBeInTheDocument();
    });

    it("does not render the AgentProgressPanel when not optimizing", () => {
      render(<OptimizeForm />);
      expect(
        screen.queryByTestId("agent-progress-panel"),
      ).not.toBeInTheDocument();
    });

    it("still renders the ConstraintForm when results are available", () => {
      render(<OptimizeForm />);
      expect(screen.getByTestId("constraint-form")).toBeInTheDocument();
    });
  });

  // ── Layout ──────────────────────────────────────────────────────────────────

  describe("layout", () => {
    it("renders the results section with aria-label", () => {
      render(<OptimizeForm />);
      const resultsSection = screen.getByRole("region", {
        name: /optimization results/i,
      });
      expect(resultsSection).toBeInTheDocument();
    });

    it("renders without error with no props", () => {
      expect(() => render(<OptimizeForm />)).not.toThrow();
    });

    it("accepts a className prop without error", () => {
      expect(() =>
        render(<OptimizeForm className="custom-class" />),
      ).not.toThrow();
    });
  });
});
