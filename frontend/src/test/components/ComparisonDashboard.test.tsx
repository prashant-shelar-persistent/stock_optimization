/**
 * Tests for @/components/ComparisonDashboard
 *
 * Covers:
 *   - No classical result → "No optimization results available" message
 *   - Classical-only result → Classical tab content rendered
 *   - Full result (classical + quantum) → all tabs available
 *   - Recommendation text displayed in comparison summary
 *   - Sharpe ratio values displayed
 *   - Budget and tickers displayed in run metadata
 *   - LLM explanation panel rendered when explanation is present
 *   - LLM explanation panel shows placeholder when no explanation
 *   - QAOA tab shows "QAOA results not available" when no quantum data
 *   - VQE tab shows "VQE results not available" when no quantum data
 *   - Classical metrics (return, volatility, sharpe) displayed
 *   - Solver status badge displayed
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ComparisonDashboard } from "@/components/ComparisonDashboard";
import type { OptimizationRunDetail } from "@/types/api";
import {
  COMPLETED_RUN_DETAIL,
  CLASSICAL_ONLY_RUN_DETAIL,
  COMPARISON_SUMMARY,
} from "@/test/fixtures";

// ── Mock Recharts ─────────────────────────────────────────────────────────────
// Recharts uses SVG and ResizeObserver; mock it to avoid jsdom issues.

vi.mock("recharts", () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const React = require("react");
  return {
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) =>
      React.createElement("div", { "data-testid": "responsive-container" }, children),
    BarChart: ({ children }: { children: React.ReactNode }) =>
      React.createElement("div", { "data-testid": "bar-chart" }, children),
    Bar: () => null,
    XAxis: () => null,
    YAxis: () => null,
    CartesianGrid: () => null,
    Tooltip: () => null,
    Legend: () => null,
    PieChart: ({ children }: { children: React.ReactNode }) =>
      React.createElement("div", { "data-testid": "pie-chart" }, children),
    Pie: ({ data }: { data: Array<{ name: string }> }) =>
      React.createElement(
        "div",
        { "data-testid": "pie" },
        data?.map((d) =>
          React.createElement("span", { key: d.name, "data-testid": `slice-${d.name}` }, d.name),
        ),
      ),
    Cell: () => null,
  };
});

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeResultWithoutClassical(): OptimizationRunDetail {
  return {
    run_id: "run-no-classical",
    status: "completed",
    tickers: ["AAPL"],
    budget: 1000,
    created_at: "2024-06-01T00:00:00Z",
    // No classical_result
  };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("ComparisonDashboard", () => {
  // ── No results state ────────────────────────────────────────────────────────

  describe("when no classical result is available", () => {
    it("renders 'No optimization results available' message", () => {
      render(<ComparisonDashboard result={makeResultWithoutClassical()} />);
      expect(
        screen.getByText("No optimization results available"),
      ).toBeInTheDocument();
    });

    it("does not render the tabs when no classical result", () => {
      render(<ComparisonDashboard result={makeResultWithoutClassical()} />);
      expect(screen.queryByRole("tab")).not.toBeInTheDocument();
    });
  });

  // ── Run metadata ────────────────────────────────────────────────────────────

  describe("run metadata", () => {
    it("displays the budget in the run metadata", () => {
      render(<ComparisonDashboard result={COMPLETED_RUN_DETAIL} />);
      // Budget: $10,000.00
      expect(screen.getByText("$10,000.00")).toBeInTheDocument();
    });

    it("displays the tickers in the run metadata", () => {
      render(<ComparisonDashboard result={COMPLETED_RUN_DETAIL} />);
      // Tickers are joined: "AAPL, MSFT, GOOGL"
      expect(screen.getByText("AAPL, MSFT, GOOGL")).toBeInTheDocument();
    });
  });

  // ── Comparison summary ──────────────────────────────────────────────────────

  describe("comparison summary", () => {
    it("renders the 'Optimization Summary' heading", () => {
      render(<ComparisonDashboard result={COMPLETED_RUN_DETAIL} />);
      expect(screen.getByText("Optimization Summary")).toBeInTheDocument();
    });

    it("displays the recommendation text", () => {
      render(<ComparisonDashboard result={COMPLETED_RUN_DETAIL} />);
      expect(
        screen.getByText(COMPARISON_SUMMARY.recommendation),
      ).toBeInTheDocument();
    });

    it("displays the 'Recommendation' label", () => {
      render(<ComparisonDashboard result={COMPLETED_RUN_DETAIL} />);
      expect(screen.getByText("Recommendation")).toBeInTheDocument();
    });

    it("displays the Classical Sharpe label when quantum results are present", () => {
      render(<ComparisonDashboard result={COMPLETED_RUN_DETAIL} />);
      expect(screen.getByText("Classical Sharpe")).toBeInTheDocument();
    });

    it("displays the QAOA Sharpe label when QAOA results are present", () => {
      render(<ComparisonDashboard result={COMPLETED_RUN_DETAIL} />);
      expect(screen.getByText("QAOA Sharpe")).toBeInTheDocument();
    });

    it("displays the VQE Sharpe label when VQE results are present", () => {
      render(<ComparisonDashboard result={COMPLETED_RUN_DETAIL} />);
      expect(screen.getByText("VQE Sharpe")).toBeInTheDocument();
    });

    it("shows the 'vs Classical Baseline' section when quantum results are present", () => {
      render(<ComparisonDashboard result={COMPLETED_RUN_DETAIL} />);
      expect(screen.getByText("vs Classical Baseline")).toBeInTheDocument();
    });

    it("does not show quantum comparison when only classical results exist", () => {
      render(<ComparisonDashboard result={CLASSICAL_ONLY_RUN_DETAIL} />);
      expect(screen.queryByText("QAOA Sharpe")).not.toBeInTheDocument();
      expect(screen.queryByText("VQE Sharpe")).not.toBeInTheDocument();
    });
  });

  // ── Strategy tabs ───────────────────────────────────────────────────────────

  describe("strategy tabs", () => {
    it("renders the Classical tab", () => {
      render(<ComparisonDashboard result={COMPLETED_RUN_DETAIL} />);
      expect(screen.getByRole("tab", { name: /classical/i })).toBeInTheDocument();
    });

    it("renders the QAOA tab", () => {
      render(<ComparisonDashboard result={COMPLETED_RUN_DETAIL} />);
      expect(screen.getByRole("tab", { name: /qaoa/i })).toBeInTheDocument();
    });

    it("renders the VQE tab", () => {
      render(<ComparisonDashboard result={COMPLETED_RUN_DETAIL} />);
      expect(screen.getByRole("tab", { name: /vqe/i })).toBeInTheDocument();
    });

    it("shows the Classical tab content by default", () => {
      render(<ComparisonDashboard result={COMPLETED_RUN_DETAIL} />);
      // Classical tab content includes "Portfolio Allocation" and "Performance Metrics"
      expect(screen.getByText("Portfolio Allocation")).toBeInTheDocument();
      expect(screen.getByText("Performance Metrics")).toBeInTheDocument();
    });

    it("shows the solver status badge in the Classical tab", () => {
      render(<ComparisonDashboard result={COMPLETED_RUN_DETAIL} />);
      // CLASSICAL_RESULT has solver_status: "optimal"
      expect(screen.getByText("optimal")).toBeInTheDocument();
    });

    it("shows the CVXPY solver label in the Classical tab", () => {
      render(<ComparisonDashboard result={COMPLETED_RUN_DETAIL} />);
      expect(screen.getByText(/CVXPY/i)).toBeInTheDocument();
    });

    it("shows the solve time in the Classical tab", () => {
      render(<ComparisonDashboard result={COMPLETED_RUN_DETAIL} />);
      // CLASSICAL_RESULT.solve_time_ms = 42 → "42 ms" appears in multiple places
      const elements = screen.getAllByText(/42 ms/i);
      expect(elements.length).toBeGreaterThanOrEqual(1);
    });
  });

  // ── Classical metrics table ─────────────────────────────────────────────────

  describe("classical metrics table", () => {
    it("displays 'Expected Return' row", () => {
      render(<ComparisonDashboard result={COMPLETED_RUN_DETAIL} />);
      expect(screen.getByText("Expected Return")).toBeInTheDocument();
    });

    it("displays 'Volatility' row", () => {
      render(<ComparisonDashboard result={COMPLETED_RUN_DETAIL} />);
      // "Volatility" appears in multiple places (comparison summary + metrics table)
      const elements = screen.getAllByText("Volatility");
      expect(elements.length).toBeGreaterThanOrEqual(1);
    });

    it("displays 'Sharpe Ratio' row", () => {
      render(<ComparisonDashboard result={COMPLETED_RUN_DETAIL} />);
      // "Sharpe Ratio" appears in multiple places (metrics chart + metrics table)
      const elements = screen.getAllByText("Sharpe Ratio");
      expect(elements.length).toBeGreaterThanOrEqual(1);
    });

    it("displays 'Assets Selected' row", () => {
      render(<ComparisonDashboard result={COMPLETED_RUN_DETAIL} />);
      expect(screen.getByText("Assets Selected")).toBeInTheDocument();
    });

    it("displays the formatted expected return value", () => {
      render(<ComparisonDashboard result={COMPLETED_RUN_DETAIL} />);
      // CLASSICAL_METRICS.expected_return = 0.142 → "14.20%"
      expect(screen.getByText("14.20%")).toBeInTheDocument();
    });

    it("displays the formatted volatility value", () => {
      render(<ComparisonDashboard result={COMPLETED_RUN_DETAIL} />);
      // CLASSICAL_METRICS.volatility = 0.187 → "18.70%"
      expect(screen.getByText("18.70%")).toBeInTheDocument();
    });

    it("displays the formatted Sharpe ratio value", () => {
      render(<ComparisonDashboard result={COMPLETED_RUN_DETAIL} />);
      // CLASSICAL_METRICS.sharpe_ratio = 1.45 → "1.450" appears in multiple places
      const elements = screen.getAllByText("1.450");
      expect(elements.length).toBeGreaterThanOrEqual(1);
    });

    it("displays the number of assets", () => {
      render(<ComparisonDashboard result={COMPLETED_RUN_DETAIL} />);
      // CLASSICAL_METRICS.num_assets = 3
      expect(screen.getByText("3")).toBeInTheDocument();
    });
  });

  // ── QAOA tab ────────────────────────────────────────────────────────────────
  // Note: Radix UI Tabs in jsdom does NOT render inactive tab panel content.
  // We test the tab button state and the tab panel accessibility attributes.

  describe("QAOA tab content", () => {
    it("QAOA tab is enabled (not disabled) when quantum results are present", () => {
      render(<ComparisonDashboard result={COMPLETED_RUN_DETAIL} />);
      const qaoaTab = screen.getByRole("tab", { name: /qaoa/i });
      // The tab should not be disabled when QAOA results are available
      expect(qaoaTab).not.toBeDisabled();
    });

    it("QAOA tab is initially not selected (Classical is default)", () => {
      render(<ComparisonDashboard result={COMPLETED_RUN_DETAIL} />);
      const qaoaTab = screen.getByRole("tab", { name: /qaoa/i });
      expect(qaoaTab).toHaveAttribute("aria-selected", "false");
    });

    it("QAOA tab is disabled when no quantum data is available", () => {
      render(<ComparisonDashboard result={CLASSICAL_ONLY_RUN_DETAIL} />);
      const qaoaTab = screen.getByRole("tab", { name: /qaoa/i });
      // When no QAOA results, the tab should be disabled
      expect(qaoaTab).toBeDisabled();
    });
  });

  // ── VQE tab ─────────────────────────────────────────────────────────────────

  describe("VQE tab content", () => {
    it("VQE tab is enabled (not disabled) when quantum results are present", () => {
      render(<ComparisonDashboard result={COMPLETED_RUN_DETAIL} />);
      const vqeTab = screen.getByRole("tab", { name: /vqe/i });
      expect(vqeTab).not.toBeDisabled();
    });

    it("VQE tab is initially not selected (Classical is default)", () => {
      render(<ComparisonDashboard result={COMPLETED_RUN_DETAIL} />);
      const vqeTab = screen.getByRole("tab", { name: /vqe/i });
      expect(vqeTab).toHaveAttribute("aria-selected", "false");
    });

    it("VQE tab is disabled when no quantum data is available", () => {
      render(<ComparisonDashboard result={CLASSICAL_ONLY_RUN_DETAIL} />);
      const vqeTab = screen.getByRole("tab", { name: /vqe/i });
      expect(vqeTab).toBeDisabled();
    });
  });

  // ── LLM explanation panel ───────────────────────────────────────────────────

  describe("LLM explanation panel", () => {
    it("renders the 'AI Portfolio Explanation' heading", () => {
      render(<ComparisonDashboard result={COMPLETED_RUN_DETAIL} />);
      expect(
        screen.getByText("AI Portfolio Explanation"),
      ).toBeInTheDocument();
    });

    it("renders the GPT-4o badge", () => {
      render(<ComparisonDashboard result={COMPLETED_RUN_DETAIL} />);
      expect(screen.getByText("GPT-4o")).toBeInTheDocument();
    });

    it("displays the LLM explanation text when present", () => {
      render(<ComparisonDashboard result={COMPLETED_RUN_DETAIL} />);
      // The explanation contains "optimized portfolio"
      expect(
        screen.getByText(/optimized portfolio/i),
      ).toBeInTheDocument();
    });

    it("shows placeholder text when no explanation is available", () => {
      const resultWithoutExplanation: OptimizationRunDetail = {
        ...COMPLETED_RUN_DETAIL,
        llm_explanation: undefined,
      };
      render(<ComparisonDashboard result={resultWithoutExplanation} />);
      expect(
        screen.getByText(
          /Explanation will appear here once the optimization completes/i,
        ),
      ).toBeInTheDocument();
    });

    it("renders a collapse/expand button when explanation is present", () => {
      render(<ComparisonDashboard result={COMPLETED_RUN_DETAIL} />);
      // The button has aria-label "Collapse explanation" or "Expand explanation"
      const collapseBtn = screen.getByRole("button", {
        name: /collapse explanation/i,
      });
      expect(collapseBtn).toBeInTheDocument();
    });
  });

  // ── Strategy Details card ───────────────────────────────────────────────────

  describe("Strategy Details card", () => {
    it("renders the 'Strategy Details' heading", () => {
      render(<ComparisonDashboard result={COMPLETED_RUN_DETAIL} />);
      expect(screen.getByText("Strategy Details")).toBeInTheDocument();
    });

    it("renders the strategy details description", () => {
      render(<ComparisonDashboard result={COMPLETED_RUN_DETAIL} />);
      expect(
        screen.getByText(
          "Allocation and performance metrics per optimization strategy",
        ),
      ).toBeInTheDocument();
    });
  });

  // ── Classical-only run ──────────────────────────────────────────────────────

  describe("classical-only run", () => {
    it("renders without error when only classical results are present", () => {
      expect(() =>
        render(<ComparisonDashboard result={CLASSICAL_ONLY_RUN_DETAIL} />),
      ).not.toThrow();
    });

    it("shows the classical recommendation", () => {
      render(<ComparisonDashboard result={CLASSICAL_ONLY_RUN_DETAIL} />);
      expect(
        screen.getByText(
          "Classical Markowitz MVO portfolio is optimal for this asset set.",
        ),
      ).toBeInTheDocument();
    });
  });
});
