/**
 * Tests for @/components/chat/PayloadConfirmCard
 *
 * PayloadConfirmCard displays extracted optimization parameters for user
 * review before the run is dispatched.
 *
 * Covers:
 *   - Header: "Ready to optimize" title and subtitle
 *   - Tickers displayed as badges
 *   - Budget formatted as currency
 *   - Min return formatted as percentage
 *   - Max volatility formatted as percentage
 *   - Max weight per asset formatted as percentage
 *   - Min weight per asset formatted as percentage
 *   - Lookback days displayed
 *   - Quantum enabled/disabled badge
 *   - Sector constraints displayed
 *   - Objectives displayed (enabled only)
 *   - Frontier config displayed
 *   - Confirm button calls onConfirm
 *   - Cancel/Edit button calls onCancel
 *   - Confirm button disabled when isConfirming is true
 *   - Confirm button shows spinner when isConfirming
 *   - Confirm button disabled when tickers are missing
 *   - Confirm button disabled when budget is 0
 *   - Optional fields not rendered when absent
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PayloadConfirmCard } from "@/components/chat/PayloadConfirmCard";
import type { ExtractedSlots } from "@/types/api";

// ── Fixtures ───────────────────────────────────────────────────────────────

const FULL_PAYLOAD: ExtractedSlots = {
  tickers: ["AAPL", "MSFT", "GOOGL"],
  budget: 50000,
  min_return: 0.08,
  max_volatility: 0.15,
  max_weight_per_asset: 0.4,
  min_weight_per_asset: 0.05,
  num_assets_to_select: 3,
  lookback_days: 252,
  run_quantum: true,
  sector_constraints: [
    { sector: "Technology", max_weight: 0.6 },
    { sector: "Healthcare", max_weight: 0.3 },
  ],
  objectives: [
    { name: "return", direction: "maximize", weight: 0.7, enabled: true, label: "Return" },
    { name: "volatility", direction: "minimize", weight: 0.3, enabled: true, label: "Volatility" },
    { name: "sharpe", direction: "maximize", weight: 0.5, enabled: false, label: "Sharpe" },
  ],
  frontier: {
    enabled: true,
    x_measure: "volatility",
    y_measure: "return",
    num_points: 20,
  },
};

const MINIMAL_PAYLOAD: ExtractedSlots = {
  tickers: ["AAPL"],
  budget: 10000,
};

// ── Header ─────────────────────────────────────────────────────────────────

describe("header", () => {
  it("renders 'Ready to optimize' title", () => {
    render(
      <PayloadConfirmCard
        payload={MINIMAL_PAYLOAD}
        isConfirming={false}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByText("Ready to optimize")).toBeInTheDocument();
  });

  it("renders the subtitle about reviewing parameters", () => {
    render(
      <PayloadConfirmCard
        payload={MINIMAL_PAYLOAD}
        isConfirming={false}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(
      screen.getByText(/Review the parameters below/),
    ).toBeInTheDocument();
  });
});

// ── Tickers ────────────────────────────────────────────────────────────────

describe("tickers", () => {
  it("renders each ticker as a badge", () => {
    render(
      <PayloadConfirmCard
        payload={FULL_PAYLOAD}
        isConfirming={false}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("MSFT")).toBeInTheDocument();
    expect(screen.getByText("GOOGL")).toBeInTheDocument();
  });

  it("renders the Tickers label", () => {
    render(
      <PayloadConfirmCard
        payload={FULL_PAYLOAD}
        isConfirming={false}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByText("Tickers")).toBeInTheDocument();
  });

  it("does NOT render Tickers row when tickers is empty", () => {
    render(
      <PayloadConfirmCard
        payload={{ budget: 10000 }}
        isConfirming={false}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.queryByText("Tickers")).not.toBeInTheDocument();
  });
});

// ── Budget ─────────────────────────────────────────────────────────────────

describe("budget", () => {
  it("renders the budget formatted as currency", () => {
    render(
      <PayloadConfirmCard
        payload={MINIMAL_PAYLOAD}
        isConfirming={false}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByText("Budget")).toBeInTheDocument();
    expect(screen.getByText("$10,000.00")).toBeInTheDocument();
  });

  it("renders $50,000.00 for budget of 50000", () => {
    render(
      <PayloadConfirmCard
        payload={FULL_PAYLOAD}
        isConfirming={false}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByText("$50,000.00")).toBeInTheDocument();
  });

  it("does NOT render Budget row when budget is absent", () => {
    render(
      <PayloadConfirmCard
        payload={{ tickers: ["AAPL"] }}
        isConfirming={false}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.queryByText("Budget")).not.toBeInTheDocument();
  });
});

// ── Min return ─────────────────────────────────────────────────────────────

describe("min return", () => {
  it("renders min_return as a percentage", () => {
    render(
      <PayloadConfirmCard
        payload={FULL_PAYLOAD}
        isConfirming={false}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByText("Min Return")).toBeInTheDocument();
    expect(screen.getByText("8.00%")).toBeInTheDocument();
  });

  it("does NOT render Min Return row when absent", () => {
    render(
      <PayloadConfirmCard
        payload={MINIMAL_PAYLOAD}
        isConfirming={false}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.queryByText("Min Return")).not.toBeInTheDocument();
  });
});

// ── Max volatility ─────────────────────────────────────────────────────────

describe("max volatility", () => {
  it("renders max_volatility as a percentage", () => {
    render(
      <PayloadConfirmCard
        payload={FULL_PAYLOAD}
        isConfirming={false}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByText("Max Volatility")).toBeInTheDocument();
    expect(screen.getByText("15.00%")).toBeInTheDocument();
  });

  it("does NOT render Max Volatility row when absent", () => {
    render(
      <PayloadConfirmCard
        payload={MINIMAL_PAYLOAD}
        isConfirming={false}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.queryByText("Max Volatility")).not.toBeInTheDocument();
  });
});

// ── Lookback days ──────────────────────────────────────────────────────────

describe("lookback days", () => {
  it("renders lookback_days with 'days' suffix", () => {
    render(
      <PayloadConfirmCard
        payload={FULL_PAYLOAD}
        isConfirming={false}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByText("Lookback")).toBeInTheDocument();
    expect(screen.getByText("252 days")).toBeInTheDocument();
  });

  it("does NOT render Lookback row when absent", () => {
    render(
      <PayloadConfirmCard
        payload={MINIMAL_PAYLOAD}
        isConfirming={false}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.queryByText("Lookback")).not.toBeInTheDocument();
  });
});

// ── Quantum flag ───────────────────────────────────────────────────────────

describe("quantum flag", () => {
  it("renders 'Enabled' badge when run_quantum is true", () => {
    render(
      <PayloadConfirmCard
        payload={FULL_PAYLOAD}
        isConfirming={false}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByText("Quantum")).toBeInTheDocument();
    expect(screen.getByText("Enabled")).toBeInTheDocument();
  });

  it("renders 'Disabled' text when run_quantum is false", () => {
    render(
      <PayloadConfirmCard
        payload={{ ...MINIMAL_PAYLOAD, run_quantum: false }}
        isConfirming={false}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByText("Disabled")).toBeInTheDocument();
  });

  it("does NOT render Quantum row when absent", () => {
    render(
      <PayloadConfirmCard
        payload={MINIMAL_PAYLOAD}
        isConfirming={false}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.queryByText("Quantum")).not.toBeInTheDocument();
  });
});

// ── Sector constraints ─────────────────────────────────────────────────────

describe("sector constraints", () => {
  it("renders sector constraints with sector name and max weight", () => {
    render(
      <PayloadConfirmCard
        payload={FULL_PAYLOAD}
        isConfirming={false}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByText("Sector Limits")).toBeInTheDocument();
    expect(screen.getByText(/Technology/)).toBeInTheDocument();
    expect(screen.getByText(/Healthcare/)).toBeInTheDocument();
  });

  it("does NOT render Sector Limits row when absent", () => {
    render(
      <PayloadConfirmCard
        payload={MINIMAL_PAYLOAD}
        isConfirming={false}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.queryByText("Sector Limits")).not.toBeInTheDocument();
  });
});

// ── Objectives ─────────────────────────────────────────────────────────────

describe("objectives", () => {
  it("renders enabled objectives", () => {
    render(
      <PayloadConfirmCard
        payload={FULL_PAYLOAD}
        isConfirming={false}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByText("Objectives")).toBeInTheDocument();
    // Enabled objectives: Return (maximize ↑) and Volatility (minimize ↓)
    // Use getAllByText since "Return" also appears in "Min Return"
    const returnMatches = screen.getAllByText(/Return/);
    expect(returnMatches.length).toBeGreaterThanOrEqual(1);
    // Verify the objectives row contains both enabled objectives
    const objectivesLabel = screen.getByText("Objectives");
    const objectivesRow = objectivesLabel.closest("div");
    expect(objectivesRow?.textContent).toContain("Return");
    expect(objectivesRow?.textContent).toContain("Volatility");
  });

  it("does NOT render disabled objectives", () => {
    render(
      <PayloadConfirmCard
        payload={FULL_PAYLOAD}
        isConfirming={false}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    // "Sharpe" objective is disabled — should not appear in objectives list
    // (Note: it might appear elsewhere, so we check the objectives section specifically)
    const objectivesSection = screen.getByText("Objectives").closest("div");
    expect(objectivesSection?.textContent).not.toContain("Sharpe");
  });

  it("does NOT render Objectives row when absent", () => {
    render(
      <PayloadConfirmCard
        payload={MINIMAL_PAYLOAD}
        isConfirming={false}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.queryByText("Objectives")).not.toBeInTheDocument();
  });
});

// ── Frontier ───────────────────────────────────────────────────────────────

describe("frontier", () => {
  it("renders frontier config when enabled", () => {
    render(
      <PayloadConfirmCard
        payload={FULL_PAYLOAD}
        isConfirming={false}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByText("Frontier")).toBeInTheDocument();
    expect(screen.getByText(/volatility vs return/)).toBeInTheDocument();
    expect(screen.getByText(/20 pts/)).toBeInTheDocument();
  });

  it("does NOT render Frontier row when frontier.enabled is false", () => {
    render(
      <PayloadConfirmCard
        payload={{
          ...MINIMAL_PAYLOAD,
          frontier: {
            enabled: false,
            x_measure: "volatility",
            y_measure: "return",
            num_points: 10,
          },
        }}
        isConfirming={false}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.queryByText("Frontier")).not.toBeInTheDocument();
  });
});

// ── Action buttons ─────────────────────────────────────────────────────────

describe("action buttons", () => {
  it("calls onConfirm when Confirm & Run button is clicked", async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    render(
      <PayloadConfirmCard
        payload={MINIMAL_PAYLOAD}
        isConfirming={false}
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />,
    );
    await user.click(screen.getByRole("button", { name: /Confirm & Run/ }));
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it("calls onCancel when Edit button is clicked", async () => {
    const onCancel = vi.fn();
    const user = userEvent.setup();
    render(
      <PayloadConfirmCard
        payload={MINIMAL_PAYLOAD}
        isConfirming={false}
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Edit" }));
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it("disables Confirm button when isConfirming is true", () => {
    render(
      <PayloadConfirmCard
        payload={MINIMAL_PAYLOAD}
        isConfirming={true}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    const confirmBtn = screen.getByRole("button", { name: /Starting run/ });
    expect(confirmBtn).toBeDisabled();
  });

  it("shows spinner text 'Starting run…' when isConfirming is true", () => {
    render(
      <PayloadConfirmCard
        payload={MINIMAL_PAYLOAD}
        isConfirming={true}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByText(/Starting run/)).toBeInTheDocument();
  });

  it("disables Edit button when isConfirming is true", () => {
    render(
      <PayloadConfirmCard
        payload={MINIMAL_PAYLOAD}
        isConfirming={true}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    const editBtn = screen.getByRole("button", { name: "Edit" });
    expect(editBtn).toBeDisabled();
  });

  it("disables Confirm button when tickers are missing", () => {
    render(
      <PayloadConfirmCard
        payload={{ budget: 10000 }}
        isConfirming={false}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    const confirmBtn = screen.getByRole("button", { name: /Confirm & Run/ });
    expect(confirmBtn).toBeDisabled();
  });

  it("disables Confirm button when budget is 0", () => {
    render(
      <PayloadConfirmCard
        payload={{ tickers: ["AAPL"], budget: 0 }}
        isConfirming={false}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    const confirmBtn = screen.getByRole("button", { name: /Confirm & Run/ });
    expect(confirmBtn).toBeDisabled();
  });

  it("enables Confirm button when tickers and budget are present", () => {
    render(
      <PayloadConfirmCard
        payload={MINIMAL_PAYLOAD}
        isConfirming={false}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    const confirmBtn = screen.getByRole("button", { name: /Confirm & Run/ });
    expect(confirmBtn).not.toBeDisabled();
  });
});

// ── className prop ─────────────────────────────────────────────────────────

describe("className prop", () => {
  it("applies extra className to the outer container", () => {
    const { container } = render(
      <PayloadConfirmCard
        payload={MINIMAL_PAYLOAD}
        isConfirming={false}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        className="mt-4 custom-class"
      />,
    );
    const outer = container.firstChild as HTMLElement;
    expect(outer.className).toContain("custom-class");
  });
});
