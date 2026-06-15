/**
 * Tests for @/components/TickerBadge
 *
 * Covers: rendering ticker, optional sector, remove button, disabled state.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { TickerBadge } from "@/components/TickerBadge";

describe("TickerBadge", () => {
  // ── Rendering ──────────────────────────────────────────────────────────────

  it("renders the ticker symbol", () => {
    render(<TickerBadge ticker="AAPL" onRemove={vi.fn()} />);
    expect(screen.getByText("AAPL")).toBeInTheDocument();
  });

  it("renders the sector when provided", () => {
    render(
      <TickerBadge ticker="MSFT" sector="Technology" onRemove={vi.fn()} />,
    );
    expect(screen.getByText("Technology")).toBeInTheDocument();
  });

  it("does not render sector text when sector is not provided", () => {
    render(<TickerBadge ticker="GOOGL" onRemove={vi.fn()} />);
    // Only the ticker should be visible
    expect(screen.getByText("GOOGL")).toBeInTheDocument();
    // No sector element
    expect(screen.queryByText("Technology")).not.toBeInTheDocument();
  });

  // ── Remove button ──────────────────────────────────────────────────────────

  it("renders a remove button with accessible label", () => {
    render(<TickerBadge ticker="TSLA" onRemove={vi.fn()} />);
    const btn = screen.getByRole("button", { name: /remove tsla/i });
    expect(btn).toBeInTheDocument();
  });

  it("calls onRemove when the remove button is clicked", () => {
    const onRemove = vi.fn();
    render(<TickerBadge ticker="NVDA" onRemove={onRemove} />);
    fireEvent.click(screen.getByRole("button", { name: /remove nvda/i }));
    expect(onRemove).toHaveBeenCalledOnce();
  });

  // ── Disabled state ─────────────────────────────────────────────────────────

  it("hides the remove button when disabled", () => {
    render(<TickerBadge ticker="AMZN" onRemove={vi.fn()} disabled />);
    expect(
      screen.queryByRole("button", { name: /remove amzn/i }),
    ).not.toBeInTheDocument();
  });

  it("does not call onRemove when disabled (no button rendered)", () => {
    const onRemove = vi.fn();
    render(<TickerBadge ticker="META" onRemove={onRemove} disabled />);
    // No button to click
    expect(
      screen.queryByRole("button"),
    ).not.toBeInTheDocument();
    expect(onRemove).not.toHaveBeenCalled();
  });

  it("applies opacity class when disabled", () => {
    const { container } = render(
      <TickerBadge ticker="NFLX" onRemove={vi.fn()} disabled />,
    );
    // The outer span should have opacity-60 class
    expect(container.firstChild).toHaveClass("opacity-60");
  });

  // ── Custom className ───────────────────────────────────────────────────────

  it("applies custom className to the outer container", () => {
    const { container } = render(
      <TickerBadge ticker="AAPL" onRemove={vi.fn()} className="my-custom-class" />,
    );
    expect(container.firstChild).toHaveClass("my-custom-class");
  });
});
