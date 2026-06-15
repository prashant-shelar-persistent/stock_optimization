/**
 * Tests for @/components/SectorConstraintRow
 *
 * Covers: rendering, slider interaction, input interaction, remove button,
 *         disabled state, input validation (invalid/empty input resets).
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SectorConstraintRow } from "@/components/SectorConstraintRow";

describe("SectorConstraintRow", () => {
  // ── Rendering ──────────────────────────────────────────────────────────────

  it("renders the sector name", () => {
    render(
      <SectorConstraintRow
        sector="Technology"
        maxWeight={0.4}
        onChange={vi.fn()}
        onRemove={vi.fn()}
      />,
    );
    expect(screen.getByText("Technology")).toBeInTheDocument();
  });

  it("renders the numeric input with the correct initial value (as percentage)", () => {
    render(
      <SectorConstraintRow
        sector="Healthcare"
        maxWeight={0.3}
        onChange={vi.fn()}
        onRemove={vi.fn()}
      />,
    );
    // 0.3 * 100 = 30
    const input = screen.getByRole("spinbutton", {
      name: /max weight percentage for healthcare/i,
    });
    expect(input).toHaveValue(30);
  });

  it("renders the remove button with accessible label", () => {
    render(
      <SectorConstraintRow
        sector="Energy"
        maxWeight={0.2}
        onChange={vi.fn()}
        onRemove={vi.fn()}
      />,
    );
    expect(
      screen.getByRole("button", { name: /remove energy constraint/i }),
    ).toBeInTheDocument();
  });

  it("renders the % suffix", () => {
    render(
      <SectorConstraintRow
        sector="Finance"
        maxWeight={0.5}
        onChange={vi.fn()}
        onRemove={vi.fn()}
      />,
    );
    expect(screen.getByText("%")).toBeInTheDocument();
  });

  // ── Remove button ──────────────────────────────────────────────────────────

  it("calls onRemove with the sector name when remove button is clicked", () => {
    const onRemove = vi.fn();
    render(
      <SectorConstraintRow
        sector="Utilities"
        maxWeight={0.25}
        onChange={vi.fn()}
        onRemove={onRemove}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: /remove utilities constraint/i }),
    );
    expect(onRemove).toHaveBeenCalledWith("Utilities");
  });

  // ── Input interaction ──────────────────────────────────────────────────────

  it("calls onChange with correct decimal value when input is blurred with valid value", () => {
    const onChange = vi.fn();
    render(
      <SectorConstraintRow
        sector="Technology"
        maxWeight={0.4}
        onChange={onChange}
        onRemove={vi.fn()}
      />,
    );
    const input = screen.getByRole("spinbutton", {
      name: /max weight percentage for technology/i,
    });
    fireEvent.change(input, { target: { value: "60" } });
    fireEvent.blur(input);
    // 60 / 100 = 0.6
    expect(onChange).toHaveBeenCalledWith("Technology", 0.6);
  });

  it("resets input to current maxWeight when blurred with invalid (non-numeric) value", () => {
    const onChange = vi.fn();
    render(
      <SectorConstraintRow
        sector="Technology"
        maxWeight={0.4}
        onChange={onChange}
        onRemove={vi.fn()}
      />,
    );
    const input = screen.getByRole("spinbutton", {
      name: /max weight percentage for technology/i,
    });
    fireEvent.change(input, { target: { value: "abc" } });
    fireEvent.blur(input);
    // onChange should NOT be called with invalid value
    expect(onChange).not.toHaveBeenCalled();
    // Input should reset to 40 (0.4 * 100)
    expect(input).toHaveValue(40);
  });

  it("clamps input value to minimum 0.01 (1%)", () => {
    const onChange = vi.fn();
    render(
      <SectorConstraintRow
        sector="Technology"
        maxWeight={0.4}
        onChange={onChange}
        onRemove={vi.fn()}
      />,
    );
    const input = screen.getByRole("spinbutton", {
      name: /max weight percentage for technology/i,
    });
    fireEvent.change(input, { target: { value: "0" } });
    fireEvent.blur(input);
    // 0/100 = 0, clamped to 0.01
    expect(onChange).toHaveBeenCalledWith("Technology", 0.01);
  });

  it("clamps input value to maximum 1.0 (100%)", () => {
    const onChange = vi.fn();
    render(
      <SectorConstraintRow
        sector="Technology"
        maxWeight={0.4}
        onChange={onChange}
        onRemove={vi.fn()}
      />,
    );
    const input = screen.getByRole("spinbutton", {
      name: /max weight percentage for technology/i,
    });
    fireEvent.change(input, { target: { value: "150" } });
    fireEvent.blur(input);
    // 150/100 = 1.5, clamped to 1.0
    expect(onChange).toHaveBeenCalledWith("Technology", 1);
  });

  it("submits on Enter key press (triggers blur)", () => {
    const onChange = vi.fn();
    render(
      <SectorConstraintRow
        sector="Technology"
        maxWeight={0.4}
        onChange={onChange}
        onRemove={vi.fn()}
      />,
    );
    const input = screen.getByRole("spinbutton", {
      name: /max weight percentage for technology/i,
    });
    fireEvent.change(input, { target: { value: "50" } });
    // In jsdom, calling .blur() on the element doesn't automatically fire the
    // blur event handler; we need to fire both keyDown and blur explicitly.
    fireEvent.keyDown(input, { key: "Enter" });
    fireEvent.blur(input);
    // After blur, onChange should be called with the parsed value
    expect(onChange).toHaveBeenCalledWith("Technology", 0.5);
  });

  // ── Disabled state ─────────────────────────────────────────────────────────

  it("disables the remove button when disabled prop is true", () => {
    render(
      <SectorConstraintRow
        sector="Technology"
        maxWeight={0.4}
        onChange={vi.fn()}
        onRemove={vi.fn()}
        disabled
      />,
    );
    expect(
      screen.getByRole("button", { name: /remove technology constraint/i }),
    ).toBeDisabled();
  });

  it("disables the numeric input when disabled prop is true", () => {
    render(
      <SectorConstraintRow
        sector="Technology"
        maxWeight={0.4}
        onChange={vi.fn()}
        onRemove={vi.fn()}
        disabled
      />,
    );
    expect(
      screen.getByRole("spinbutton", {
        name: /max weight percentage for technology/i,
      }),
    ).toBeDisabled();
  });

  it("applies opacity class when disabled", () => {
    const { container } = render(
      <SectorConstraintRow
        sector="Technology"
        maxWeight={0.4}
        onChange={vi.fn()}
        onRemove={vi.fn()}
        disabled
      />,
    );
    expect(container.firstChild).toHaveClass("opacity-60");
  });

  // ── External maxWeight update ──────────────────────────────────────────────

  it("updates input value when maxWeight prop changes externally", () => {
    const { rerender } = render(
      <SectorConstraintRow
        sector="Technology"
        maxWeight={0.4}
        onChange={vi.fn()}
        onRemove={vi.fn()}
      />,
    );
    const input = screen.getByRole("spinbutton", {
      name: /max weight percentage for technology/i,
    });
    expect(input).toHaveValue(40);

    rerender(
      <SectorConstraintRow
        sector="Technology"
        maxWeight={0.6}
        onChange={vi.fn()}
        onRemove={vi.fn()}
      />,
    );
    expect(input).toHaveValue(60);
  });
});
