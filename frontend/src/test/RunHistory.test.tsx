/**
 * Tests for @/components/RunHistory
 *
 * Mocks useRunHistory to test rendering in different states:
 *   - Loading skeleton
 *   - Empty state
 *   - Error state
 *   - Populated table with runs
 *   - Pagination controls
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { RunHistory } from "@/components/RunHistory";
import type { OptimizationRunSummary } from "@/types/api";

// ── Mock useRunHistory ────────────────────────────────────────────────────────

const mockUseRunHistory = vi.fn();

vi.mock("@/hooks/useRunHistory", () => ({
  useRunHistory: () => mockUseRunHistory(),
}));

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeRun(
  overrides: Partial<OptimizationRunSummary> = {},
): OptimizationRunSummary {
  return {
    run_id: "run-abc-123",
    status: "completed",
    tickers: ["AAPL", "MSFT", "GOOGL"],
    budget: 10000,
    created_at: new Date(Date.now() - 3600_000).toISOString(), // 1 hour ago
    classical_sharpe: 1.45,
    quantum_sharpe: 1.62,
    ...overrides,
  };
}

function renderRunHistory() {
  return render(
    <MemoryRouter>
      <RunHistory />
    </MemoryRouter>,
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("RunHistory", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ── Loading state ──────────────────────────────────────────────────────────

  it("renders skeleton rows while loading", () => {
    mockUseRunHistory.mockReturnValue({
      runs: [],
      total: 0,
      page: 1,
      setPage: vi.fn(),
      isLoading: true,
      error: null,
    });

    renderRunHistory();

    // Table headers should be present
    expect(screen.getByText("Status")).toBeInTheDocument();
    expect(screen.getByText("Assets")).toBeInTheDocument();
    expect(screen.getByText("Budget")).toBeInTheDocument();
    // Skeleton elements are rendered (no actual data rows)
    expect(screen.queryByText("No optimization runs yet.")).not.toBeInTheDocument();
  });

  // ── Empty state ────────────────────────────────────────────────────────────

  it("renders empty state when no runs exist", () => {
    mockUseRunHistory.mockReturnValue({
      runs: [],
      total: 0,
      page: 1,
      setPage: vi.fn(),
      isLoading: false,
      error: null,
    });

    renderRunHistory();

    expect(screen.getByText("No optimization runs yet.")).toBeInTheDocument();
    expect(
      screen.getByText(/Start one from the Dashboard/i),
    ).toBeInTheDocument();
  });

  // ── Error state ────────────────────────────────────────────────────────────

  it("renders error state with message and retry button", () => {
    mockUseRunHistory.mockReturnValue({
      runs: [],
      total: 0,
      page: 1,
      setPage: vi.fn(),
      isLoading: false,
      error: new Error("Network error"),
    });

    renderRunHistory();

    expect(
      screen.getByText(/Failed to load run history: Network error/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });

  it("calls setPage(1) when retry button is clicked", () => {
    const setPage = vi.fn();
    mockUseRunHistory.mockReturnValue({
      runs: [],
      total: 0,
      page: 3,
      setPage,
      isLoading: false,
      error: new Error("Timeout"),
    });

    renderRunHistory();

    fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(setPage).toHaveBeenCalledWith(1);
  });

  // ── Populated table ────────────────────────────────────────────────────────

  it("renders run rows with correct data", () => {
    const run = makeRun();
    mockUseRunHistory.mockReturnValue({
      runs: [run],
      total: 1,
      page: 1,
      setPage: vi.fn(),
      isLoading: false,
      error: null,
    });

    renderRunHistory();

    // Status badge
    expect(screen.getByText("Completed")).toBeInTheDocument();
    // Tickers
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("MSFT")).toBeInTheDocument();
    expect(screen.getByText("GOOGL")).toBeInTheDocument();
    // Budget
    expect(screen.getByText("$10,000.00")).toBeInTheDocument();
    // Sharpe ratios
    expect(screen.getByText("1.45")).toBeInTheDocument();
    expect(screen.getByText("1.62")).toBeInTheDocument();
  });

  it("shows '+N more' badge when run has more than 3 tickers", () => {
    const run = makeRun({
      tickers: ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"],
    });
    mockUseRunHistory.mockReturnValue({
      runs: [run],
      total: 1,
      page: 1,
      setPage: vi.fn(),
      isLoading: false,
      error: null,
    });

    renderRunHistory();

    // First 3 tickers shown
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("MSFT")).toBeInTheDocument();
    expect(screen.getByText("GOOGL")).toBeInTheDocument();
    // +2 more badge
    expect(screen.getByText("+2")).toBeInTheDocument();
    // 4th and 5th tickers NOT shown
    expect(screen.queryByText("AMZN")).not.toBeInTheDocument();
    expect(screen.queryByText("TSLA")).not.toBeInTheDocument();
  });

  it("shows '—' for null classical_sharpe", () => {
    const run = makeRun({ classical_sharpe: undefined, quantum_sharpe: undefined });
    mockUseRunHistory.mockReturnValue({
      runs: [run],
      total: 1,
      page: 1,
      setPage: vi.fn(),
      isLoading: false,
      error: null,
    });

    renderRunHistory();

    // Should show em-dash for missing sharpe values
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThanOrEqual(2);
  });

  it("renders 'View Details' link pointing to /run/:runId", () => {
    const run = makeRun({ run_id: "run-xyz-999" });
    mockUseRunHistory.mockReturnValue({
      runs: [run],
      total: 1,
      page: 1,
      setPage: vi.fn(),
      isLoading: false,
      error: null,
    });

    renderRunHistory();

    const link = screen.getByRole("link", { name: /view details/i });
    expect(link).toHaveAttribute("href", "/run/run-xyz-999");
  });

  it("renders correct status badge for 'running' status", () => {
    const run = makeRun({ status: "running" });
    mockUseRunHistory.mockReturnValue({
      runs: [run],
      total: 1,
      page: 1,
      setPage: vi.fn(),
      isLoading: false,
      error: null,
    });

    renderRunHistory();

    expect(screen.getByText("Running")).toBeInTheDocument();
  });

  it("renders correct status badge for 'failed' status", () => {
    const run = makeRun({ status: "failed" });
    mockUseRunHistory.mockReturnValue({
      runs: [run],
      total: 1,
      page: 1,
      setPage: vi.fn(),
      isLoading: false,
      error: null,
    });

    renderRunHistory();

    expect(screen.getByText("Failed")).toBeInTheDocument();
  });

  it("renders correct status badge for 'pending' status", () => {
    const run = makeRun({ status: "pending" });
    mockUseRunHistory.mockReturnValue({
      runs: [run],
      total: 1,
      page: 1,
      setPage: vi.fn(),
      isLoading: false,
      error: null,
    });

    renderRunHistory();

    expect(screen.getByText("Pending")).toBeInTheDocument();
  });

  // ── Pagination ─────────────────────────────────────────────────────────────

  it("does not render pagination when total <= PAGE_SIZE (20)", () => {
    mockUseRunHistory.mockReturnValue({
      runs: [makeRun()],
      total: 1,
      page: 1,
      setPage: vi.fn(),
      isLoading: false,
      error: null,
    });

    renderRunHistory();

    expect(
      screen.queryByRole("button", { name: /previous/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /next/i }),
    ).not.toBeInTheDocument();
  });

  it("renders pagination when total > PAGE_SIZE (20)", () => {
    mockUseRunHistory.mockReturnValue({
      runs: Array.from({ length: 20 }, (_, i) =>
        makeRun({ run_id: `run-${i}` }),
      ),
      total: 45,
      page: 1,
      setPage: vi.fn(),
      isLoading: false,
      error: null,
    });

    renderRunHistory();

    expect(
      screen.getByRole("button", { name: /previous/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /next/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/page 1 of 3/i)).toBeInTheDocument();
  });

  it("disables Previous button on first page", () => {
    mockUseRunHistory.mockReturnValue({
      runs: Array.from({ length: 20 }, (_, i) =>
        makeRun({ run_id: `run-${i}` }),
      ),
      total: 45,
      page: 1,
      setPage: vi.fn(),
      isLoading: false,
      error: null,
    });

    renderRunHistory();

    expect(
      screen.getByRole("button", { name: /previous/i }),
    ).toBeDisabled();
  });

  it("disables Next button on last page", () => {
    mockUseRunHistory.mockReturnValue({
      runs: Array.from({ length: 5 }, (_, i) =>
        makeRun({ run_id: `run-${i}` }),
      ),
      total: 45,
      page: 3,
      setPage: vi.fn(),
      isLoading: false,
      error: null,
    });

    renderRunHistory();

    expect(
      screen.getByRole("button", { name: /next/i }),
    ).toBeDisabled();
  });

  it("calls setPage with page+1 when Next is clicked", () => {
    const setPage = vi.fn();
    mockUseRunHistory.mockReturnValue({
      runs: Array.from({ length: 20 }, (_, i) =>
        makeRun({ run_id: `run-${i}` }),
      ),
      total: 45,
      page: 1,
      setPage,
      isLoading: false,
      error: null,
    });

    renderRunHistory();

    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    expect(setPage).toHaveBeenCalledWith(2);
  });

  it("calls setPage with page-1 when Previous is clicked", () => {
    const setPage = vi.fn();
    mockUseRunHistory.mockReturnValue({
      runs: Array.from({ length: 20 }, (_, i) =>
        makeRun({ run_id: `run-${i}` }),
      ),
      total: 45,
      page: 2,
      setPage,
      isLoading: false,
      error: null,
    });

    renderRunHistory();

    fireEvent.click(screen.getByRole("button", { name: /previous/i }));
    expect(setPage).toHaveBeenCalledWith(1);
  });

  it("shows correct item range in pagination footer", () => {
    mockUseRunHistory.mockReturnValue({
      runs: Array.from({ length: 20 }, (_, i) =>
        makeRun({ run_id: `run-${i}` }),
      ),
      total: 45,
      page: 2,
      setPage: vi.fn(),
      isLoading: false,
      error: null,
    });

    renderRunHistory();

    // Page 2: items 21-40 of 45
    expect(screen.getByText(/showing 21.40 of 45 runs/i)).toBeInTheDocument();
  });
});
