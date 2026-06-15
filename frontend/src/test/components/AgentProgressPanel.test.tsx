/**
 * Tests for @/components/dashboard/AgentProgressPanel
 *
 * Covers:
 *   - Idle state: all 6 pipeline steps rendered, 0% progress
 *   - Running state: messages displayed, progress percentage updated
 *   - Completed state: 100% progress, all nodes shown as completed
 *   - Failed state: failed node message displayed
 *   - Progress percentage calculation (1/6 = 17%, 2/6 = 33%, 6/6 = 100%)
 *   - Timestamp formatting
 *   - Multiple nodes in progress simultaneously
 *   - Pending node descriptions shown
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { AgentProgressPanel } from "@/components/dashboard/AgentProgressPanel";
import type { AgentProgressMessage } from "@/types/api";
import {
  makeProgressMessage,
  FULL_PIPELINE_PROGRESS,
  PARTIAL_PIPELINE_PROGRESS,
} from "@/test/fixtures";

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("AgentProgressPanel", () => {
  // ── Idle / empty state ──────────────────────────────────────────────────────

  describe("idle state (no progress events)", () => {
    it("renders all 6 pipeline step labels", () => {
      render(<AgentProgressPanel progress={[]} isRunning={false} />);

      expect(screen.getByText("Data Fetch")).toBeInTheDocument();
      expect(screen.getByText("Constraint Validation")).toBeInTheDocument();
      expect(screen.getByText("Classical Optimization")).toBeInTheDocument();
      expect(screen.getByText("Quantum Optimization")).toBeInTheDocument();
      expect(screen.getByText("Comparison")).toBeInTheDocument();
      expect(screen.getByText("LLM Explanation")).toBeInTheDocument();
    });

    it("shows 0% progress when no events have been received", () => {
      render(<AgentProgressPanel progress={[]} isRunning={false} />);
      expect(screen.getByText("0%")).toBeInTheDocument();
    });

    it("renders the progress bar element", () => {
      render(<AgentProgressPanel progress={[]} isRunning={false} />);
      const progressBar = screen.getByRole("progressbar");
      expect(progressBar).toBeInTheDocument();
    });

    it("renders all 6 pipeline steps as list items", () => {
      render(<AgentProgressPanel progress={[]} isRunning={false} />);
      const listItems = screen.getAllByRole("listitem");
      expect(listItems).toHaveLength(6);
    });

    it("shows the description for the Data Fetch node when pending", () => {
      render(<AgentProgressPanel progress={[]} isRunning={false} />);
      expect(
        screen.getByText("Fetching live market data via yfinance"),
      ).toBeInTheDocument();
    });

    it("shows the description for the Classical Optimization node when pending", () => {
      render(<AgentProgressPanel progress={[]} isRunning={false} />);
      expect(
        screen.getByText("Running Markowitz MVO via CVXPY"),
      ).toBeInTheDocument();
    });

    it("shows the description for the LLM Explanation node when pending", () => {
      render(<AgentProgressPanel progress={[]} isRunning={false} />);
      expect(
        screen.getByText("Generating GPT-4o portfolio explanation"),
      ).toBeInTheDocument();
    });
  });

  // ── Running state ───────────────────────────────────────────────────────────

  describe("running state", () => {
    it("displays the message from a 'started' event", () => {
      const progress = [
        makeProgressMessage("data_fetch", "started", {
          message: "Fetching AAPL, MSFT, GOOGL data",
        }),
      ];
      render(<AgentProgressPanel progress={progress} isRunning={true} />);
      expect(
        screen.getByText("Fetching AAPL, MSFT, GOOGL data"),
      ).toBeInTheDocument();
    });

    it("displays the message from a 'completed' event", () => {
      const progress = [
        makeProgressMessage("data_fetch", "started"),
        makeProgressMessage("data_fetch", "completed", {
          message: "Fetched 3 assets (252 trading days)",
        }),
      ];
      render(<AgentProgressPanel progress={progress} isRunning={true} />);
      expect(
        screen.getByText("Fetched 3 assets (252 trading days)"),
      ).toBeInTheDocument();
    });

    it("displays messages for multiple nodes simultaneously", () => {
      const progress = [
        makeProgressMessage("data_fetch", "completed", {
          message: "Data ready",
        }),
        makeProgressMessage("constraint_validation", "started", {
          message: "Validating constraints",
        }),
      ];
      render(<AgentProgressPanel progress={progress} isRunning={true} />);
      expect(screen.getByText("Data ready")).toBeInTheDocument();
      expect(screen.getByText("Validating constraints")).toBeInTheDocument();
    });

    it("uses the partial pipeline progress fixture correctly", () => {
      render(
        <AgentProgressPanel
          progress={PARTIAL_PIPELINE_PROGRESS}
          isRunning={true}
        />,
      );
      // data_fetch completed, constraint_validation started
      expect(
        screen.getByText("Fetched 3 assets (252 trading days)"),
      ).toBeInTheDocument();
      expect(
        screen.getByText("Validating portfolio constraints"),
      ).toBeInTheDocument();
    });
  });

  // ── Failed state ────────────────────────────────────────────────────────────

  describe("failed state", () => {
    it("displays the message from a 'failed' event", () => {
      const progress = [
        makeProgressMessage("data_fetch", "started"),
        makeProgressMessage("data_fetch", "failed", {
          message: "Network timeout after 30s",
        }),
      ];
      render(<AgentProgressPanel progress={progress} isRunning={false} />);
      expect(
        screen.getByText("Network timeout after 30s"),
      ).toBeInTheDocument();
    });

    it("shows the failed message for a mid-pipeline failure", () => {
      const progress = [
        makeProgressMessage("data_fetch", "started"),
        makeProgressMessage("data_fetch", "completed"),
        makeProgressMessage("constraint_validation", "started"),
        makeProgressMessage("constraint_validation", "failed", {
          message: "Budget constraint infeasible",
        }),
      ];
      render(<AgentProgressPanel progress={progress} isRunning={false} />);
      expect(
        screen.getByText("Budget constraint infeasible"),
      ).toBeInTheDocument();
    });
  });

  // ── Progress percentage ─────────────────────────────────────────────────────

  describe("progress percentage", () => {
    it("shows 17% when 1 of 6 nodes completes", () => {
      const progress = [
        makeProgressMessage("data_fetch", "started"),
        makeProgressMessage("data_fetch", "completed"),
      ];
      render(<AgentProgressPanel progress={progress} isRunning={true} />);
      // 1/6 = 16.67% → rounded to 17%
      expect(screen.getByText("17%")).toBeInTheDocument();
    });

    it("shows 33% when 2 of 6 nodes complete", () => {
      const progress = [
        makeProgressMessage("data_fetch", "started"),
        makeProgressMessage("data_fetch", "completed"),
        makeProgressMessage("constraint_validation", "started"),
        makeProgressMessage("constraint_validation", "completed"),
      ];
      render(<AgentProgressPanel progress={progress} isRunning={true} />);
      // 2/6 = 33.33% → rounded to 33%
      expect(screen.getByText("33%")).toBeInTheDocument();
    });

    it("shows 50% when 3 of 6 nodes complete", () => {
      const progress: AgentProgressMessage[] = [
        makeProgressMessage("data_fetch", "started"),
        makeProgressMessage("data_fetch", "completed"),
        makeProgressMessage("constraint_validation", "started"),
        makeProgressMessage("constraint_validation", "completed"),
        makeProgressMessage("classical_optimization", "started"),
        makeProgressMessage("classical_optimization", "completed"),
      ];
      render(<AgentProgressPanel progress={progress} isRunning={true} />);
      // 3/6 = 50%
      expect(screen.getByText("50%")).toBeInTheDocument();
    });

    it("shows 100% when all 6 nodes complete", () => {
      render(
        <AgentProgressPanel
          progress={FULL_PIPELINE_PROGRESS}
          isRunning={false}
        />,
      );
      expect(screen.getByText("100%")).toBeInTheDocument();
    });

    it("does not count 'started' events toward progress percentage", () => {
      // Only 'started' for data_fetch — no 'completed' yet
      const progress = [makeProgressMessage("data_fetch", "started")];
      render(<AgentProgressPanel progress={progress} isRunning={true} />);
      // 0 completed out of 6 = 0%
      expect(screen.getByText("0%")).toBeInTheDocument();
    });

    it("does not count 'failed' events toward progress percentage", () => {
      // A failed node should not count as completed
      const progress = [
        makeProgressMessage("data_fetch", "started"),
        makeProgressMessage("data_fetch", "failed"),
      ];
      render(<AgentProgressPanel progress={progress} isRunning={false} />);
      expect(screen.getByText("0%")).toBeInTheDocument();
    });
  });

  // ── Timestamp display ───────────────────────────────────────────────────────

  describe("timestamp display", () => {
    it("displays a formatted time string for events with a timestamp", () => {
      const progress = [
        makeProgressMessage("data_fetch", "completed", {
          message: "Done",
          timestamp: "2024-06-01T12:00:00.000Z",
        }),
      ];
      render(<AgentProgressPanel progress={progress} isRunning={false} />);
      // The timestamp should be formatted as HH:MM:SS (locale-dependent)
      const timeElements = screen.getAllByText(/\d{2}:\d{2}:\d{2}/);
      expect(timeElements.length).toBeGreaterThan(0);
    });
  });

  // ── Pipeline header ─────────────────────────────────────────────────────────

  describe("pipeline header", () => {
    it("renders the 'Agent Pipeline Progress' label", () => {
      render(<AgentProgressPanel progress={[]} isRunning={false} />);
      expect(screen.getByText("Agent Pipeline Progress")).toBeInTheDocument();
    });
  });
});
