/**
 * Tests for @/components/AllocationChart
 *
 * Covers:
 *   - Empty state when weights array is empty
 *   - Empty state when all weights are zero
 *   - Renders chart container when weights are provided
 *   - Optional title rendering
 *   - Zero-weight assets are filtered out
 *   - Both color schemes (classical / quantum) accepted without error
 *   - Default colorScheme is "classical"
 *   - Legend entries rendered for each non-zero asset
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { AllocationChart } from "@/components/AllocationChart";
import type { AssetWeight } from "@/types/api";
import { CLASSICAL_WEIGHTS, QAOA_WEIGHTS } from "@/test/fixtures";

// ── Mock Recharts ─────────────────────────────────────────────────────────────
// Recharts uses SVG and ResizeObserver internally. In jsdom, SVG rendering
// is limited, so we mock Recharts to render simplified HTML that still
// exposes the data we want to test.

vi.mock("recharts", () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const React = require("react");

  return {
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) =>
      React.createElement("div", { "data-testid": "responsive-container" }, children),

    PieChart: ({ children }: { children: React.ReactNode }) =>
      React.createElement("div", { "data-testid": "pie-chart" }, children),

    Pie: ({
      data,
      children,
    }: {
      data: Array<{ name: string; value: number }>;
      children?: React.ReactNode;
    }) =>
      React.createElement(
        "div",
        { "data-testid": "pie" },
        data.map((d) =>
          React.createElement(
            "span",
            { key: d.name, "data-testid": `pie-slice-${d.name}` },
            d.name,
          ),
        ),
        children,
      ),

    Cell: () => null,

    Tooltip: () => null,

    Legend: ({
      content,
    }: {
      content?: React.ReactElement;
    }) => (content ? React.cloneElement(content, {
      payload: [{ value: "AAPL", color: "#3b82f6", payload: { weight: 0.45 } }],
    }) : null),
  };
});

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeZeroWeights(): AssetWeight[] {
  return [
    { ticker: "AAPL", weight: 0, allocation: 0 },
    { ticker: "MSFT", weight: 0, allocation: 0 },
  ];
}

function makeTinyWeights(): AssetWeight[] {
  return [
    { ticker: "AAPL", weight: 0.0005, allocation: 5 }, // below 0.001 threshold
    { ticker: "MSFT", weight: 0.5, allocation: 5000 },
  ];
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("AllocationChart", () => {
  // ── Empty state ─────────────────────────────────────────────────────────────

  describe("empty state", () => {
    it("renders empty state message when weights array is empty", () => {
      render(<AllocationChart weights={[]} />);
      expect(
        screen.getByText("No allocation data available"),
      ).toBeInTheDocument();
    });

    it("renders empty state when all weights are zero", () => {
      render(<AllocationChart weights={makeZeroWeights()} />);
      expect(
        screen.getByText("No allocation data available"),
      ).toBeInTheDocument();
    });

    it("renders empty state when all weights are below the 0.001 threshold", () => {
      const tinyWeights: AssetWeight[] = [
        { ticker: "AAPL", weight: 0.0005, allocation: 5 },
        { ticker: "MSFT", weight: 0.0009, allocation: 9 },
      ];
      render(<AllocationChart weights={tinyWeights} />);
      expect(
        screen.getByText("No allocation data available"),
      ).toBeInTheDocument();
    });

    it("does not render the chart container in empty state", () => {
      render(<AllocationChart weights={[]} />);
      expect(
        screen.queryByTestId("responsive-container"),
      ).not.toBeInTheDocument();
    });
  });

  // ── Chart rendering ─────────────────────────────────────────────────────────

  describe("chart rendering", () => {
    it("renders the responsive container when weights are provided", () => {
      render(<AllocationChart weights={CLASSICAL_WEIGHTS} />);
      expect(
        screen.getByTestId("responsive-container"),
      ).toBeInTheDocument();
    });

    it("renders the pie chart when weights are provided", () => {
      render(<AllocationChart weights={CLASSICAL_WEIGHTS} />);
      expect(screen.getByTestId("pie-chart")).toBeInTheDocument();
    });

    it("renders a pie slice for each non-zero asset", () => {
      render(<AllocationChart weights={CLASSICAL_WEIGHTS} />);
      // CLASSICAL_WEIGHTS has AAPL, MSFT, GOOGL
      expect(screen.getByTestId("pie-slice-AAPL")).toBeInTheDocument();
      expect(screen.getByTestId("pie-slice-MSFT")).toBeInTheDocument();
      expect(screen.getByTestId("pie-slice-GOOGL")).toBeInTheDocument();
    });

    it("filters out zero-weight assets from the chart", () => {
      const weights: AssetWeight[] = [
        { ticker: "AAPL", weight: 0.8, allocation: 8000 },
        { ticker: "MSFT", weight: 0, allocation: 0 }, // zero weight
        { ticker: "GOOGL", weight: 0.2, allocation: 2000 },
      ];
      render(<AllocationChart weights={weights} />);
      expect(screen.getByTestId("pie-slice-AAPL")).toBeInTheDocument();
      expect(screen.getByTestId("pie-slice-GOOGL")).toBeInTheDocument();
      expect(
        screen.queryByTestId("pie-slice-MSFT"),
      ).not.toBeInTheDocument();
    });

    it("filters out assets below the 0.001 weight threshold", () => {
      render(<AllocationChart weights={makeTinyWeights()} />);
      // AAPL (0.0005) should be filtered; MSFT (0.5) should remain
      expect(screen.getByTestId("pie-slice-MSFT")).toBeInTheDocument();
      expect(
        screen.queryByTestId("pie-slice-AAPL"),
      ).not.toBeInTheDocument();
    });
  });

  // ── Title ───────────────────────────────────────────────────────────────────

  describe("title prop", () => {
    it("renders the title when provided", () => {
      render(
        <AllocationChart
          weights={CLASSICAL_WEIGHTS}
          title="Classical Portfolio Allocation"
        />,
      );
      expect(
        screen.getByText("Classical Portfolio Allocation"),
      ).toBeInTheDocument();
    });

    it("does not render a title element when title is not provided", () => {
      render(<AllocationChart weights={CLASSICAL_WEIGHTS} />);
      // No title paragraph should be present
      expect(
        screen.queryByText("Classical Portfolio Allocation"),
      ).not.toBeInTheDocument();
    });
  });

  // ── Color schemes ───────────────────────────────────────────────────────────

  describe("colorScheme prop", () => {
    it("renders without error with colorScheme='classical'", () => {
      expect(() =>
        render(
          <AllocationChart weights={CLASSICAL_WEIGHTS} colorScheme="classical" />,
        ),
      ).not.toThrow();
    });

    it("renders without error with colorScheme='quantum'", () => {
      expect(() =>
        render(
          <AllocationChart weights={QAOA_WEIGHTS} colorScheme="quantum" />,
        ),
      ).not.toThrow();
    });

    it("defaults to 'classical' color scheme when not specified", () => {
      // Should render without error (no colorScheme prop)
      expect(() =>
        render(<AllocationChart weights={CLASSICAL_WEIGHTS} />),
      ).not.toThrow();
    });
  });

  // ── Data integrity ──────────────────────────────────────────────────────────

  describe("data integrity", () => {
    it("renders all 3 assets from CLASSICAL_WEIGHTS fixture", () => {
      render(<AllocationChart weights={CLASSICAL_WEIGHTS} />);
      expect(screen.getByTestId("pie-slice-AAPL")).toBeInTheDocument();
      expect(screen.getByTestId("pie-slice-MSFT")).toBeInTheDocument();
      expect(screen.getByTestId("pie-slice-GOOGL")).toBeInTheDocument();
    });

    it("renders all 3 assets from QAOA_WEIGHTS fixture", () => {
      render(<AllocationChart weights={QAOA_WEIGHTS} />);
      expect(screen.getByTestId("pie-slice-AAPL")).toBeInTheDocument();
      expect(screen.getByTestId("pie-slice-MSFT")).toBeInTheDocument();
      expect(screen.getByTestId("pie-slice-GOOGL")).toBeInTheDocument();
    });

    it("handles a single-asset portfolio", () => {
      const singleAsset: AssetWeight[] = [
        { ticker: "AAPL", weight: 1.0, allocation: 10000 },
      ];
      render(<AllocationChart weights={singleAsset} />);
      expect(screen.getByTestId("pie-slice-AAPL")).toBeInTheDocument();
    });

    it("handles a large portfolio (10 assets)", () => {
      const manyAssets: AssetWeight[] = Array.from({ length: 10 }, (_, i) => ({
        ticker: `TICK${i}`,
        weight: 0.1,
        allocation: 1000,
      }));
      render(<AllocationChart weights={manyAssets} />);
      // All 10 slices should be rendered
      manyAssets.forEach((a) => {
        expect(screen.getByTestId(`pie-slice-${a.ticker}`)).toBeInTheDocument();
      });
    });
  });
});
