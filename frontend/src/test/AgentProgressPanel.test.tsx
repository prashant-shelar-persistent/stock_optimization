/**
 * Tests for @/components/dashboard/AgentProgressPanel
 *
 * Covers: idle state, progress rendering, node status display,
 *         progress bar percentage, failed state, completed state.
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { AgentProgressPanel } from "@/components/dashboard/AgentProgressPanel";
import type { AgentProgressMessage } from "@/types/api";

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeMsg(
  node: AgentProgressMessage["node"],
  status: AgentProgressMessage["status"],
  message = `${node} ${status}`,
): AgentProgressMessage {
  return {
    type: "progress",
    run_id: "run-test",
    node,
    status,
    message,
    timestamp: "2024-01-01T12:00:00.000Z",
  };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("AgentProgressPanel", () => {
  // ── Idle / empty state ────────────────────────────────────────────────────

  it("renders all 7 pipeline steps in idle state", () => {
    render(<AgentProgressPanel progress={[]} isRunning={false} />);
    expect(screen.getByText("Data Fetch")).toBeInTheDocument();
    expect(screen.getByText("Constraint Validation")).toBeInTheDocument();
    expect(screen.getByText("Classical Optimization")).toBeInTheDocument();
    expect(screen.getByText("Quantum Optimization")).toBeInTheDocument();
    expect(screen.getByText("Comparison")).toBeInTheDocument();
    expect(screen.getByText("Frontier Computation")).toBeInTheDocument();
    expect(screen.getByText("LLM Explanation")).toBeInTheDocument();
  });

  it("shows 0% progress when no events received", () => {
    render(<AgentProgressPanel progress={[]} isRunning={false} />);
    expect(screen.getByText("0%")).toBeInTheDocument();
  });

  it("shows descriptions for pending nodes", () => {
    render(<AgentProgressPanel progress={[]} isRunning={false} />);
    expect(
      screen.getByText("Fetching live market data via yfinance"),
    ).toBeInTheDocument();
  });

  // ── Running state ─────────────────────────────────────────────────────────

  it("shows the message from a started event", () => {
    const progress = [makeMsg("data_fetch", "started", "Fetching AAPL data...")];
    render(<AgentProgressPanel progress={progress} isRunning={true} />);
    expect(screen.getByText("Fetching AAPL data...")).toBeInTheDocument();
  });

  it("shows the message from a completed event", () => {
    const progress = [
      makeMsg("data_fetch", "started"),
      makeMsg("data_fetch", "completed", "Fetched 5 assets"),
    ];
    render(<AgentProgressPanel progress={progress} isRunning={true} />);
    expect(screen.getByText("Fetched 5 assets")).toBeInTheDocument();
  });

  it("shows the message from a failed event", () => {
    const progress = [
      makeMsg("data_fetch", "started"),
      makeMsg("data_fetch", "failed", "Network timeout"),
    ];
    render(<AgentProgressPanel progress={progress} isRunning={false} />);
    expect(screen.getByText("Network timeout")).toBeInTheDocument();
  });

  // ── Progress percentage ───────────────────────────────────────────────────

  it("shows correct progress percentage when one node completes", () => {
    // 1 completed out of 7 = ~14%
    const progress = [
      makeMsg("data_fetch", "started"),
      makeMsg("data_fetch", "completed"),
    ];
    render(<AgentProgressPanel progress={progress} isRunning={true} />);
    // 1/7 = 14.28% → rounded to 14%
    expect(screen.getByText("14%")).toBeInTheDocument();
  });

  it("shows 100% progress when all nodes complete", () => {
    const progress: AgentProgressMessage[] = [
      "data_fetch",
      "constraint_validation",
      "classical_optimization",
      "quantum_dispatch",
      "comparison",
      "frontier_computation",
      "llm_explanation",
    ].flatMap((node) => [
      makeMsg(node as AgentProgressMessage["node"], "started"),
      makeMsg(node as AgentProgressMessage["node"], "completed"),
    ]);
    render(<AgentProgressPanel progress={progress} isRunning={false} />);
    expect(screen.getByText("100%")).toBeInTheDocument();
  });

  it("shows 29% when 2 of 7 nodes complete", () => {
    const progress: AgentProgressMessage[] = [
      makeMsg("data_fetch", "started"),
      makeMsg("data_fetch", "completed"),
      makeMsg("constraint_validation", "started"),
      makeMsg("constraint_validation", "completed"),
    ];
    render(<AgentProgressPanel progress={progress} isRunning={true} />);
    // 2/7 = 28.57% → rounded to 29%
    expect(screen.getByText("29%")).toBeInTheDocument();
  });

  // ── Node status visual states ─────────────────────────────────────────────

  it("renders the progress bar element", () => {
    render(<AgentProgressPanel progress={[]} isRunning={false} />);
    // The Progress component renders a div with role="progressbar"
    const progressBar = screen.getByRole("progressbar");
    expect(progressBar).toBeInTheDocument();
  });

  it("renders all pipeline steps as list items", () => {
    render(<AgentProgressPanel progress={[]} isRunning={false} />);
    const listItems = screen.getAllByRole("listitem");
    expect(listItems).toHaveLength(7);
  });

  // ── Multiple nodes in progress ────────────────────────────────────────────

  it("shows messages for multiple nodes simultaneously", () => {
    const progress: AgentProgressMessage[] = [
      makeMsg("data_fetch", "completed", "Data ready"),
      makeMsg("constraint_validation", "started", "Validating constraints"),
    ];
    render(<AgentProgressPanel progress={progress} isRunning={true} />);
    expect(screen.getByText("Data ready")).toBeInTheDocument();
    expect(screen.getByText("Validating constraints")).toBeInTheDocument();
  });

  // ── Timestamp display ─────────────────────────────────────────────────────

  it("displays a formatted timestamp for events that have one", () => {
    const progress = [
      makeMsg("data_fetch", "completed", "Done"),
    ];
    render(<AgentProgressPanel progress={progress} isRunning={false} />);
    // The timestamp "2024-01-01T12:00:00.000Z" should be formatted as a time string
    // We just verify some time-like text is present (locale-dependent)
    const timeElements = screen.getAllByText(/\d{2}:\d{2}:\d{2}/);
    expect(timeElements.length).toBeGreaterThan(0);
  });
});
