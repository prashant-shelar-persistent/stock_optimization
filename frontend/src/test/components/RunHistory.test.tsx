/**
 * Tests for @/components/RunHistory
 *
 * Mocks useRunHistory to test rendering in different states:
 *   - Loading skeleton
 *   - Empty state
 *   - Error state with retry button
 *   - Populated table with runs
 *   - Pagination controls
 *   - Status badges for all statuses
 *   - Ticker truncation (+N more)
 *   - Missing Sharpe values (em-dash)
 *   - View Details link
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { RunHistory } from "@/components/RunHistory";
import type { OptimizationRunSummary } from "@/types/api";
import { makeRunSummary } from "@/test/fixtures";

// ── Mock useRunHistory ────────────────────────────────────────────────────────

const mockUseRunHistory = vi.fn();

vi.mock("@/hooks/useRunHistory", () => ({
  useRunHistory: () => mockUseRunHistory(),
}));

// ── Helpers ───────────────────────────────────────────────────────────────────

function renderRunHistory() {
  return render(
    <MemoryRouter>
      <RunHistory />
    </MemoryRouter>,
  );
}

function makeDefaultReturn(overrides: Partial<{
  runs: OptimizationRunSummary[];
  total: number;
  page: number;
  setPage: ReturnType<typeof vi.fn>;
  isLoading: boolean;
  error: Error | null;
}> = {}) {
  return {
    runs: [],
    total: 0,
    page: 1,
    setPage: vi.fn(),
    isLoading: false,
    error: null,
    ...overrides,
  };
}

// ── Setup ─────────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks();
});

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("RunHistory", () => {
  // ── Table headers ───────────────────────────────────────────────────────────

  describe("table headers", () => {
    it("renders the Status column header", () => {
      mockUseRunHistory.mockReturnValue(makeDefaultReturn({ isLoading: true }));
      renderRunHistory();
      expect(screen.getByText("Status")).toBeInTheDocument();
    });

    it("renders the Assets column header", () => {
      mockUseRunHistory.mockReturnValue(makeDefaultReturn({ isLoading: true }));
      renderRunHistory();
      expect(screen.getByText("Assets")).toBeInTheDocument();
    });

    it("renders the Budget column header", () => {
      mockUseRunHistory.mockReturnValue(makeDefaultReturn({ isLoading: true }));
      renderRunHistory();
      expect(screen.getByText("Budget")).toBeInTheDocument();
    });

    it("renders the Date column header", () => {
      mockUseRunHistory.mockReturnValue(makeDefaultReturn({ isLoading: true }));
      renderRunHistory();
      expect(screen.getByText("Date")).toBeInTheDocument();
    });

    it("renders the Actions column header", () => {
      mockUseRunHistory.mockReturnValue(makeDefaultReturn({ isLoading: true }));
      renderRunHistory();
      expect(screen.getByText("Actions")).toBeInTheDocument();
    });
  });

  // ── Loading state ───────────────────────────────────────────────────────────

  describe("loading state", () => {
    it("renders skeleton rows while loading", () => {
      mockUseRunHistory.mockReturnValue(makeDefaultReturn({ isLoading: true }));
      renderRunHistory();
      // Table headers should be present
      expect(screen.getByText("Status")).toBeInTheDocument();
      // No empty state message
      expect(
        screen.queryByText("No optimization runs yet."),
      ).not.toBeInTheDocument();
    });

    it("does not show empty state while loading", () => {
      mockUseRunHistory.mockReturnValue(makeDefaultReturn({ isLoading: true }));
      renderRunHistory();
      expect(
        screen.queryByText("No optimization runs yet."),
      ).not.toBeInTheDocument();
    });
  });

  // ── Empty state ─────────────────────────────────────────────────────────────

  describe("empty state", () => {
    it("renders empty state message when no runs exist", () => {
      mockUseRunHistory.mockReturnValue(makeDefaultReturn());
      renderRunHistory();
      expect(
        screen.getByText("No optimization runs yet."),
      ).toBeInTheDocument();
    });

    it("renders a link to start a run from the Dashboard", () => {
      mockUseRunHistory.mockReturnValue(makeDefaultReturn());
      renderRunHistory();
      expect(
        screen.getByText(/Start one from the Dashboard/i),
      ).toBeInTheDocument();
    });
  });

  // ── Error state ─────────────────────────────────────────────────────────────

  describe("error state", () => {
    it("renders error message when query fails", () => {
      mockUseRunHistory.mockReturnValue(
        makeDefaultReturn({ error: new Error("Network error") }),
      );
      renderRunHistory();
      expect(
        screen.getByText(/Failed to load run history: Network error/i),
      ).toBeInTheDocument();
    });

    it("renders a Retry button in error state", () => {
      mockUseRunHistory.mockReturnValue(
        makeDefaultReturn({ error: new Error("Timeout") }),
      );
      renderRunHistory();
      expect(
        screen.getByRole("button", { name: /retry/i }),
      ).toBeInTheDocument();
    });

    it("calls setPage(1) when Retry button is clicked", () => {
      const setPage = vi.fn();
      mockUseRunHistory.mockReturnValue(
        makeDefaultReturn({
          error: new Error("Timeout"),
          page: 3,
          setPage,
        }),
      );
      renderRunHistory();
      fireEvent.click(screen.getByRole("button", { name: /retry/i }));
      expect(setPage).toHaveBeenCalledWith(1);
    });
  });

  // ── Populated table ─────────────────────────────────────────────────────────

  describe("populated table", () => {
    it("renders run rows with correct status badge", () => {
      const run = makeRunSummary({ status: "completed" });
      mockUseRunHistory.mockReturnValue(
        makeDefaultReturn({ runs: [run], total: 1 }),
      );
      renderRunHistory();
      expect(screen.getByText("Completed")).toBeInTheDocument();
    });

    it("renders all tickers when 3 or fewer", () => {
      const run = makeRunSummary({ tickers: ["AAPL", "MSFT", "GOOGL"] });
      mockUseRunHistory.mockReturnValue(
        makeDefaultReturn({ runs: [run], total: 1 }),
      );
      renderRunHistory();
      expect(screen.getByText("AAPL")).toBeInTheDocument();
      expect(screen.getByText("MSFT")).toBeInTheDocument();
      expect(screen.getByText("GOOGL")).toBeInTheDocument();
    });

    it("shows first 3 tickers and '+N more' badge when more than 3", () => {
      const run = makeRunSummary({
        tickers: ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"],
      });
      mockUseRunHistory.mockReturnValue(
        makeDefaultReturn({ runs: [run], total: 1 }),
      );
      renderRunHistory();
      expect(screen.getByText("AAPL")).toBeInTheDocument();
      expect(screen.getByText("MSFT")).toBeInTheDocument();
      expect(screen.getByText("GOOGL")).toBeInTheDocument();
      expect(screen.getByText("+2")).toBeInTheDocument();
      expect(screen.queryByText("AMZN")).not.toBeInTheDocument();
      expect(screen.queryByText("TSLA")).not.toBeInTheDocument();
    });

    it("renders the budget formatted as USD", () => {
      const run = makeRunSummary({ budget: 10000 });
      mockUseRunHistory.mockReturnValue(
        makeDefaultReturn({ runs: [run], total: 1 }),
      );
      renderRunHistory();
      expect(screen.getByText("$10,000.00")).toBeInTheDocument();
    });

    it("renders classical Sharpe ratio", () => {
      const run = makeRunSummary({ classical_sharpe: 1.45 });
      mockUseRunHistory.mockReturnValue(
        makeDefaultReturn({ runs: [run], total: 1 }),
      );
      renderRunHistory();
      expect(screen.getByText("1.45")).toBeInTheDocument();
    });

    it("renders quantum Sharpe ratio", () => {
      const run = makeRunSummary({ quantum_sharpe: 1.62 });
      mockUseRunHistory.mockReturnValue(
        makeDefaultReturn({ runs: [run], total: 1 }),
      );
      renderRunHistory();
      expect(screen.getByText("1.62")).toBeInTheDocument();
    });

    it("shows em-dash for missing classical_sharpe", () => {
      const run = makeRunSummary({
        classical_sharpe: undefined,
        quantum_sharpe: undefined,
      });
      mockUseRunHistory.mockReturnValue(
        makeDefaultReturn({ runs: [run], total: 1 }),
      );
      renderRunHistory();
      const dashes = screen.getAllByText("—");
      expect(dashes.length).toBeGreaterThanOrEqual(2);
    });

    it("renders 'View Details' link pointing to /run/:runId", () => {
      const run = makeRunSummary({ run_id: "run-xyz-999" });
      mockUseRunHistory.mockReturnValue(
        makeDefaultReturn({ runs: [run], total: 1 }),
      );
      renderRunHistory();
      const link = screen.getByRole("link", { name: /view details/i });
      expect(link).toHaveAttribute("href", "/run/run-xyz-999");
    });
  });

  // ── Status badges ───────────────────────────────────────────────────────────

  describe("status badges", () => {
    it("renders 'Completed' badge for completed status", () => {
      mockUseRunHistory.mockReturnValue(
        makeDefaultReturn({
          runs: [makeRunSummary({ status: "completed" })],
          total: 1,
        }),
      );
      renderRunHistory();
      expect(screen.getByText("Completed")).toBeInTheDocument();
    });

    it("renders 'Running' badge for running status", () => {
      mockUseRunHistory.mockReturnValue(
        makeDefaultReturn({
          runs: [makeRunSummary({ status: "running" })],
          total: 1,
        }),
      );
      renderRunHistory();
      expect(screen.getByText("Running")).toBeInTheDocument();
    });

    it("renders 'Pending' badge for pending status", () => {
      mockUseRunHistory.mockReturnValue(
        makeDefaultReturn({
          runs: [makeRunSummary({ status: "pending" })],
          total: 1,
        }),
      );
      renderRunHistory();
      expect(screen.getByText("Pending")).toBeInTheDocument();
    });

    it("renders 'Failed' badge for failed status", () => {
      mockUseRunHistory.mockReturnValue(
        makeDefaultReturn({
          runs: [makeRunSummary({ status: "failed" })],
          total: 1,
        }),
      );
      renderRunHistory();
      expect(screen.getByText("Failed")).toBeInTheDocument();
    });
  });

  // ── Pagination ──────────────────────────────────────────────────────────────

  describe("pagination", () => {
    it("does not render pagination when total <= 20", () => {
      mockUseRunHistory.mockReturnValue(
        makeDefaultReturn({ runs: [makeRunSummary()], total: 1 }),
      );
      renderRunHistory();
      expect(
        screen.queryByRole("button", { name: /previous/i }),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: /next/i }),
      ).not.toBeInTheDocument();
    });

    it("renders pagination when total > 20", () => {
      mockUseRunHistory.mockReturnValue(
        makeDefaultReturn({
          runs: Array.from({ length: 20 }, (_, i) =>
            makeRunSummary({ run_id: `run-${i}` }),
          ),
          total: 45,
          page: 1,
        }),
      );
      renderRunHistory();
      expect(
        screen.getByRole("button", { name: /previous/i }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /next/i }),
      ).toBeInTheDocument();
    });

    it("shows 'Page X of Y' text", () => {
      mockUseRunHistory.mockReturnValue(
        makeDefaultReturn({
          runs: Array.from({ length: 20 }, (_, i) =>
            makeRunSummary({ run_id: `run-${i}` }),
          ),
          total: 45,
          page: 1,
        }),
      );
      renderRunHistory();
      expect(screen.getByText(/page 1 of 3/i)).toBeInTheDocument();
    });

    it("disables Previous button on first page", () => {
      mockUseRunHistory.mockReturnValue(
        makeDefaultReturn({
          runs: Array.from({ length: 20 }, (_, i) =>
            makeRunSummary({ run_id: `run-${i}` }),
          ),
          total: 45,
          page: 1,
        }),
      );
      renderRunHistory();
      expect(
        screen.getByRole("button", { name: /previous/i }),
      ).toBeDisabled();
    });

    it("disables Next button on last page", () => {
      mockUseRunHistory.mockReturnValue(
        makeDefaultReturn({
          runs: Array.from({ length: 5 }, (_, i) =>
            makeRunSummary({ run_id: `run-${i}` }),
          ),
          total: 45,
          page: 3,
        }),
      );
      renderRunHistory();
      expect(screen.getByRole("button", { name: /next/i })).toBeDisabled();
    });

    it("calls setPage(page+1) when Next is clicked", () => {
      const setPage = vi.fn();
      mockUseRunHistory.mockReturnValue(
        makeDefaultReturn({
          runs: Array.from({ length: 20 }, (_, i) =>
            makeRunSummary({ run_id: `run-${i}` }),
          ),
          total: 45,
          page: 1,
          setPage,
        }),
      );
      renderRunHistory();
      fireEvent.click(screen.getByRole("button", { name: /next/i }));
      expect(setPage).toHaveBeenCalledWith(2);
    });

    it("calls setPage(page-1) when Previous is clicked", () => {
      const setPage = vi.fn();
      mockUseRunHistory.mockReturnValue(
        makeDefaultReturn({
          runs: Array.from({ length: 20 }, (_, i) =>
            makeRunSummary({ run_id: `run-${i}` }),
          ),
          total: 45,
          page: 2,
          setPage,
        }),
      );
      renderRunHistory();
      fireEvent.click(screen.getByRole("button", { name: /previous/i }));
      expect(setPage).toHaveBeenCalledWith(1);
    });

    it("shows correct item range in pagination footer", () => {
      mockUseRunHistory.mockReturnValue(
        makeDefaultReturn({
          runs: Array.from({ length: 20 }, (_, i) =>
            makeRunSummary({ run_id: `run-${i}` }),
          ),
          total: 45,
          page: 2,
        }),
      );
      renderRunHistory();
      // Page 2: items 21-40 of 45
      expect(screen.getByText(/showing 21.40 of 45 runs/i)).toBeInTheDocument();
    });
  });
});
