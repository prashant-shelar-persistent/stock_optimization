/**
 * Tests for @/components/chat/ChatBubble
 *
 * ChatBubble is the low-level styled bubble primitive.
 * It supports three visual variants: "user", "assistant", and "system".
 *
 * Covers:
 *   - User bubble: primary background, rounded-tr-sm corner
 *   - Assistant bubble: muted background, rounded-tl-sm corner
 *   - System bubble: amber background, role="status", aria-live="polite"
 *   - Loading state: typing indicator with aria-label, no children rendered
 *   - Children rendered when not loading
 *   - variant prop overrides role
 *   - Default role is "assistant" when neither role nor variant is provided
 *   - className prop is applied to the outer element
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ChatBubble } from "@/components/chat/ChatBubble";

// ── User bubble ────────────────────────────────────────────────────────────

describe("user bubble", () => {
  it("renders children content", () => {
    render(<ChatBubble role="user">Hello world</ChatBubble>);
    expect(screen.getByText("Hello world")).toBeInTheDocument();
  });

  it("has primary background class", () => {
    const { container } = render(<ChatBubble role="user">Hi</ChatBubble>);
    const bubble = container.firstChild as HTMLElement;
    expect(bubble.className).toContain("bg-primary");
  });

  it("has rounded-tr-sm class (user tail)", () => {
    const { container } = render(<ChatBubble role="user">Hi</ChatBubble>);
    const bubble = container.firstChild as HTMLElement;
    expect(bubble.className).toContain("rounded-tr-sm");
  });

  it("does NOT have rounded-tl-sm class", () => {
    const { container } = render(<ChatBubble role="user">Hi</ChatBubble>);
    const bubble = container.firstChild as HTMLElement;
    expect(bubble.className).not.toContain("rounded-tl-sm");
  });
});

// ── Assistant bubble ───────────────────────────────────────────────────────

describe("assistant bubble", () => {
  it("renders children content", () => {
    render(<ChatBubble role="assistant">What tickers?</ChatBubble>);
    expect(screen.getByText("What tickers?")).toBeInTheDocument();
  });

  it("has muted background class", () => {
    const { container } = render(
      <ChatBubble role="assistant">Hi</ChatBubble>,
    );
    const bubble = container.firstChild as HTMLElement;
    expect(bubble.className).toContain("bg-muted");
  });

  it("has rounded-tl-sm class (assistant tail)", () => {
    const { container } = render(
      <ChatBubble role="assistant">Hi</ChatBubble>,
    );
    const bubble = container.firstChild as HTMLElement;
    expect(bubble.className).toContain("rounded-tl-sm");
  });

  it("does NOT have rounded-tr-sm class", () => {
    const { container } = render(
      <ChatBubble role="assistant">Hi</ChatBubble>,
    );
    const bubble = container.firstChild as HTMLElement;
    expect(bubble.className).not.toContain("rounded-tr-sm");
  });
});

// ── System bubble ──────────────────────────────────────────────────────────

describe("system bubble", () => {
  it("renders children content", () => {
    render(<ChatBubble variant="system">Session reset</ChatBubble>);
    expect(screen.getByText("Session reset")).toBeInTheDocument();
  });

  it("has role='status' for accessibility", () => {
    render(<ChatBubble variant="system">Notice</ChatBubble>);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("has aria-live='polite'", () => {
    render(<ChatBubble variant="system">Notice</ChatBubble>);
    const el = screen.getByRole("status");
    expect(el.getAttribute("aria-live")).toBe("polite");
  });

  it("has amber background class", () => {
    const { container } = render(
      <ChatBubble variant="system">Notice</ChatBubble>,
    );
    const bubble = container.firstChild as HTMLElement;
    expect(bubble.className).toContain("bg-amber-50");
  });

  it("does NOT have primary or muted background", () => {
    const { container } = render(
      <ChatBubble variant="system">Notice</ChatBubble>,
    );
    const bubble = container.firstChild as HTMLElement;
    expect(bubble.className).not.toContain("bg-primary");
    expect(bubble.className).not.toContain("bg-muted");
  });
});

// ── Loading state ──────────────────────────────────────────────────────────

describe("loading state", () => {
  it("renders the typing indicator with aria-label when isLoading is true", () => {
    render(<ChatBubble role="assistant" isLoading />);
    expect(screen.getByLabelText("Assistant is typing")).toBeInTheDocument();
  });

  it("has role='status' on the typing indicator", () => {
    render(<ChatBubble role="assistant" isLoading />);
    // The TypingDots span has role="status"
    const statusEl = screen.getByRole("status");
    expect(statusEl).toBeInTheDocument();
  });

  it("does NOT render children when isLoading is true", () => {
    render(
      <ChatBubble role="assistant" isLoading>
        This should not appear
      </ChatBubble>,
    );
    expect(screen.queryByText("This should not appear")).not.toBeInTheDocument();
  });

  it("renders three aria-hidden dots in the typing indicator", () => {
    const { container } = render(<ChatBubble role="assistant" isLoading />);
    const dots = container.querySelectorAll("[aria-hidden='true']");
    expect(dots.length).toBe(3);
  });
});

// ── variant overrides role ─────────────────────────────────────────────────

describe("variant overrides role", () => {
  it("renders system variant even when role='user' is also provided", () => {
    render(
      <ChatBubble role="user" variant="system">
        System notice
      </ChatBubble>,
    );
    // System variant renders role="status"
    expect(screen.getByRole("status")).toBeInTheDocument();
    // Should NOT have primary background
    const { container } = render(
      <ChatBubble role="user" variant="system">
        System notice
      </ChatBubble>,
    );
    const bubble = container.firstChild as HTMLElement;
    expect(bubble.className).not.toContain("bg-primary");
  });
});

// ── Default role ───────────────────────────────────────────────────────────

describe("default role", () => {
  it("defaults to assistant style when no role or variant is provided", () => {
    const { container } = render(<ChatBubble>Default bubble</ChatBubble>);
    const bubble = container.firstChild as HTMLElement;
    // Default is assistant: bg-muted + rounded-tl-sm
    expect(bubble.className).toContain("bg-muted");
    expect(bubble.className).toContain("rounded-tl-sm");
  });
});

// ── className prop ─────────────────────────────────────────────────────────

describe("className prop", () => {
  it("applies extra className to the outer element", () => {
    const { container } = render(
      <ChatBubble role="user" className="mt-4 custom-class">
        Hi
      </ChatBubble>,
    );
    const bubble = container.firstChild as HTMLElement;
    expect(bubble.className).toContain("custom-class");
  });

  it("applies extra className to system bubble", () => {
    const { container } = render(
      <ChatBubble variant="system" className="my-custom">
        Notice
      </ChatBubble>,
    );
    const bubble = container.firstChild as HTMLElement;
    expect(bubble.className).toContain("my-custom");
  });
});

// ── Content rendering ──────────────────────────────────────────────────────

describe("content rendering", () => {
  it("wraps text in whitespace-pre-wrap span", () => {
    const { container } = render(
      <ChatBubble role="assistant">Line 1\nLine 2</ChatBubble>,
    );
    const span = container.querySelector(".whitespace-pre-wrap");
    expect(span).toBeInTheDocument();
  });

  it("renders React node children (not just strings)", () => {
    render(
      <ChatBubble role="assistant">
        <span data-testid="custom-child">Custom content</span>
      </ChatBubble>,
    );
    expect(screen.getByTestId("custom-child")).toBeInTheDocument();
  });
});
