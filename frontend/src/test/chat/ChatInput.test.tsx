/**
 * Tests for @/components/chat/ChatInput
 *
 * ChatInput is the message composition area at the bottom of the chat panel.
 * It features an auto-growing textarea, Enter-to-send, and a send button.
 *
 * Covers:
 *   - Renders textarea with correct placeholder
 *   - Renders send button
 *   - Typing into the textarea updates the value
 *   - Clicking send button calls onSend with trimmed content
 *   - Pressing Enter calls onSend
 *   - Pressing Shift+Enter does NOT call onSend (inserts newline)
 *   - Empty input does NOT call onSend
 *   - Whitespace-only input does NOT call onSend
 *   - Input is cleared after send
 *   - isSending=true disables the textarea and send button
 *   - disabled=true disables the entire input
 *   - disabled=true shows "Session complete." placeholder
 *   - Character count warning shown when approaching limit
 *   - Keyboard hint shown when not disabled
 *   - Keyboard hint hidden when disabled
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ChatInput } from "@/components/chat/ChatInput";

// ── Rendering ──────────────────────────────────────────────────────────────

describe("rendering", () => {
  it("renders the textarea with default placeholder", () => {
    render(<ChatInput onSend={vi.fn()} />);
    expect(
      screen.getByPlaceholderText("Ask me to build a portfolio…"),
    ).toBeInTheDocument();
  });

  it("renders the textarea with custom placeholder", () => {
    render(
      <ChatInput onSend={vi.fn()} placeholder="Type your message here…" />,
    );
    expect(
      screen.getByPlaceholderText("Type your message here…"),
    ).toBeInTheDocument();
  });

  it("renders the send button", () => {
    render(<ChatInput onSend={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Send message" })).toBeInTheDocument();
  });

  it("renders the keyboard hint when not disabled", () => {
    render(<ChatInput onSend={vi.fn()} />);
    expect(screen.getByText(/Enter to send/)).toBeInTheDocument();
  });

  it("does NOT render the keyboard hint when disabled", () => {
    render(<ChatInput onSend={vi.fn()} disabled />);
    expect(screen.queryByText(/Enter to send/)).not.toBeInTheDocument();
  });
});

// ── Typing ─────────────────────────────────────────────────────────────────

describe("typing", () => {
  it("updates the textarea value as the user types", async () => {
    const user = userEvent.setup();
    render(<ChatInput onSend={vi.fn()} />);
    const textarea = screen.getByRole("textbox", { name: "Chat message" });
    await user.type(textarea, "Hello world");
    expect(textarea).toHaveValue("Hello world");
  });
});

// ── Send via button click ──────────────────────────────────────────────────

describe("send via button click", () => {
  it("calls onSend with the trimmed content when send button is clicked", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<ChatInput onSend={onSend} />);
    const textarea = screen.getByRole("textbox", { name: "Chat message" });
    await user.type(textarea, "Build me a portfolio");
    await user.click(screen.getByRole("button", { name: "Send message" }));
    expect(onSend).toHaveBeenCalledOnce();
    expect(onSend).toHaveBeenCalledWith("Build me a portfolio");
  });

  it("clears the textarea after sending", async () => {
    const user = userEvent.setup();
    render(<ChatInput onSend={vi.fn()} />);
    const textarea = screen.getByRole("textbox", { name: "Chat message" });
    await user.type(textarea, "Hello");
    await user.click(screen.getByRole("button", { name: "Send message" }));
    expect(textarea).toHaveValue("");
  });

  it("trims leading/trailing whitespace before calling onSend", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<ChatInput onSend={onSend} />);
    const textarea = screen.getByRole("textbox", { name: "Chat message" });
    await user.type(textarea, "  hello  ");
    await user.click(screen.getByRole("button", { name: "Send message" }));
    expect(onSend).toHaveBeenCalledWith("hello");
  });

  it("does NOT call onSend when the input is empty", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<ChatInput onSend={onSend} />);
    await user.click(screen.getByRole("button", { name: "Send message" }));
    expect(onSend).not.toHaveBeenCalled();
  });

  it("does NOT call onSend when the input is whitespace only", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<ChatInput onSend={onSend} />);
    const textarea = screen.getByRole("textbox", { name: "Chat message" });
    await user.type(textarea, "   ");
    await user.click(screen.getByRole("button", { name: "Send message" }));
    expect(onSend).not.toHaveBeenCalled();
  });
});

// ── Send via Enter key ─────────────────────────────────────────────────────

describe("send via Enter key", () => {
  it("calls onSend when Enter is pressed", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<ChatInput onSend={onSend} />);
    const textarea = screen.getByRole("textbox", { name: "Chat message" });
    await user.type(textarea, "Hello{Enter}");
    expect(onSend).toHaveBeenCalledOnce();
    expect(onSend).toHaveBeenCalledWith("Hello");
  });

  it("does NOT call onSend when Shift+Enter is pressed", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<ChatInput onSend={onSend} />);
    const textarea = screen.getByRole("textbox", { name: "Chat message" });
    await user.type(textarea, "Hello");
    // Shift+Enter should insert a newline, not submit
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: true });
    expect(onSend).not.toHaveBeenCalled();
  });
});

// ── isSending state ────────────────────────────────────────────────────────

describe("isSending state", () => {
  it("disables the textarea when isSending is true", () => {
    render(<ChatInput onSend={vi.fn()} isSending />);
    const textarea = screen.getByRole("textbox", { name: "Chat message" });
    expect(textarea).toBeDisabled();
  });

  it("disables the send button when isSending is true", () => {
    render(<ChatInput onSend={vi.fn()} isSending />);
    const button = screen.getByRole("button", { name: "Send message" });
    expect(button).toBeDisabled();
  });

  it("sets aria-busy on the send button when isSending is true", () => {
    render(<ChatInput onSend={vi.fn()} isSending />);
    const button = screen.getByRole("button", { name: "Send message" });
    expect(button.getAttribute("aria-busy")).toBe("true");
  });
});

// ── disabled state ─────────────────────────────────────────────────────────

describe("disabled state", () => {
  it("disables the textarea when disabled is true", () => {
    render(<ChatInput onSend={vi.fn()} disabled />);
    const textarea = screen.getByRole("textbox", { name: "Chat message" });
    expect(textarea).toBeDisabled();
  });

  it("shows 'Session complete.' placeholder when disabled", () => {
    render(<ChatInput onSend={vi.fn()} disabled />);
    expect(
      screen.getByPlaceholderText("Session complete."),
    ).toBeInTheDocument();
  });

  it("does NOT call onSend when disabled and Enter is pressed", async () => {
    const onSend = vi.fn();
    render(<ChatInput onSend={onSend} disabled />);
    const textarea = screen.getByRole("textbox", { name: "Chat message" });
    // Textarea is disabled so typing won't work, but we verify the guard
    fireEvent.keyDown(textarea, { key: "Enter" });
    expect(onSend).not.toHaveBeenCalled();
  });
});

// ── Character count warning ────────────────────────────────────────────────

describe("character count warning", () => {
  it("does NOT show character count when below warning threshold", async () => {
    const user = userEvent.setup();
    render(<ChatInput onSend={vi.fn()} />);
    const textarea = screen.getByRole("textbox", { name: "Chat message" });
    await user.type(textarea, "Short message");
    // Should not show character count for short messages
    expect(screen.queryByText(/\/2000/)).not.toBeInTheDocument();
  });

  it("shows character count when approaching the limit (>= 1800 chars)", async () => {
    const user = userEvent.setup();
    render(<ChatInput onSend={vi.fn()} />);
    const textarea = screen.getByRole("textbox", { name: "Chat message" });
    // Type 1800 characters to trigger the warning
    const longText = "A".repeat(1800);
    await user.type(textarea, longText);
    expect(screen.getByText(/\/2000/)).toBeInTheDocument();
  });
});
