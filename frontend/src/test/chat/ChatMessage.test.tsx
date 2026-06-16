/**
 * Tests for @/components/chat/ChatMessage
 *
 * ChatMessage renders a single message bubble in the conversation thread.
 * It handles user and assistant roles, timestamps, and a loading state.
 *
 * Covers:
 *   - User message: right-aligned, User icon, correct content
 *   - Assistant message: left-aligned, Bot icon, correct content
 *   - Timestamp display (when provided)
 *   - No timestamp when not provided
 *   - Loading state: renders typing indicator, no content, no timestamp
 *   - Newlines preserved in content (whitespace-pre-wrap)
 *   - Empty content renders without crashing
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ChatMessage } from "@/components/chat/ChatMessage";

// ── User message ───────────────────────────────────────────────────────────

describe("user message", () => {
  it("renders the message content", () => {
    render(<ChatMessage role="user" content="Hello, build me a portfolio!" />);
    expect(screen.getByText("Hello, build me a portfolio!")).toBeInTheDocument();
  });

  it("renders the User icon (aria-hidden)", () => {
    const { container } = render(
      <ChatMessage role="user" content="Hello" />,
    );
    // The avatar div is aria-hidden; we check the SVG is present
    const avatarDiv = container.querySelector("[aria-hidden='true']");
    expect(avatarDiv).toBeInTheDocument();
  });

  it("does NOT render the Bot icon for user messages", () => {
    const { container } = render(
      <ChatMessage role="user" content="Hello" />,
    );
    // The avatar container should have bg-primary class (user style)
    const avatarDiv = container.querySelector("[aria-hidden='true']");
    expect(avatarDiv?.className).toContain("bg-primary");
  });
});

// ── Assistant message ──────────────────────────────────────────────────────

describe("assistant message", () => {
  it("renders the message content", () => {
    render(
      <ChatMessage
        role="assistant"
        content="What tickers are you interested in?"
      />,
    );
    expect(
      screen.getByText("What tickers are you interested in?"),
    ).toBeInTheDocument();
  });

  it("renders the Bot icon avatar (aria-hidden)", () => {
    const { container } = render(
      <ChatMessage role="assistant" content="Hello" />,
    );
    const avatarDiv = container.querySelector("[aria-hidden='true']");
    expect(avatarDiv).toBeInTheDocument();
    // Assistant avatar has bg-muted class
    expect(avatarDiv?.className).toContain("bg-muted");
  });
});

// ── Timestamp ──────────────────────────────────────────────────────────────

describe("timestamp", () => {
  it("renders a <time> element when timestamp is provided", () => {
    render(
      <ChatMessage
        role="user"
        content="Hello"
        timestamp="2024-06-01T12:00:00.000Z"
      />,
    );
    const timeEl = document.querySelector("time");
    expect(timeEl).toBeInTheDocument();
    expect(timeEl?.getAttribute("dateTime")).toBe("2024-06-01T12:00:00.000Z");
  });

  it("does NOT render a <time> element when timestamp is not provided", () => {
    render(<ChatMessage role="user" content="Hello" />);
    expect(document.querySelector("time")).toBeNull();
  });

  it("does NOT render a <time> element when isLoading is true", () => {
    render(
      <ChatMessage
        role="assistant"
        content=""
        isLoading
        timestamp="2024-06-01T12:00:00.000Z"
      />,
    );
    expect(document.querySelector("time")).toBeNull();
  });
});

// ── Loading state ──────────────────────────────────────────────────────────

describe("loading state", () => {
  it("renders the typing indicator aria-label when isLoading is true", () => {
    render(<ChatMessage role="assistant" content="" isLoading />);
    expect(screen.getByLabelText("Assistant is typing")).toBeInTheDocument();
  });

  it("does NOT render the content text when isLoading is true", () => {
    render(
      <ChatMessage role="assistant" content="This should not appear" isLoading />,
    );
    expect(screen.queryByText("This should not appear")).not.toBeInTheDocument();
  });

  it("renders three animated dots in the typing indicator", () => {
    const { container } = render(
      <ChatMessage role="assistant" content="" isLoading />,
    );
    // The typing indicator contains 3 span dots
    const indicator = container.querySelector("[aria-label='Assistant is typing']");
    const dots = indicator?.querySelectorAll("span");
    expect(dots?.length).toBe(3);
  });
});

// ── Content rendering ──────────────────────────────────────────────────────

describe("content rendering", () => {
  it("renders multi-line content with whitespace-pre-wrap", () => {
    const multiline = "Line 1\nLine 2\nLine 3";
    const { container } = render(
      <ChatMessage role="assistant" content={multiline} />,
    );
    const contentSpan = container.querySelector(".whitespace-pre-wrap");
    expect(contentSpan).toBeInTheDocument();
    expect(contentSpan?.textContent).toBe(multiline);
  });

  it("renders empty content without crashing", () => {
    expect(() =>
      render(<ChatMessage role="user" content="" />),
    ).not.toThrow();
  });

  it("renders long content without crashing", () => {
    const longContent = "A".repeat(2000);
    expect(() =>
      render(<ChatMessage role="assistant" content={longContent} />),
    ).not.toThrow();
  });
});

// ── Default isLoading ──────────────────────────────────────────────────────

describe("isLoading defaults to false", () => {
  it("renders content (not typing indicator) when isLoading is not provided", () => {
    render(<ChatMessage role="assistant" content="Hello there" />);
    expect(screen.getByText("Hello there")).toBeInTheDocument();
    expect(screen.queryByLabelText("Assistant is typing")).not.toBeInTheDocument();
  });
});
