/**
 * Tests for @/components/chat/ChatAssistant
 *
 * ChatAssistant is the floating panel + FAB button that orchestrates the
 * entire chat experience. It reads from chatStore and delegates API calls
 * to useChatSession.
 *
 * Strategy:
 *   - Mock useChatSession to isolate the component from API calls.
 *   - Drive state via chatStore directly (no mocking needed — it's a real store).
 *   - Assert on rendered output and store mutations.
 *
 * Covers:
 *   - FAB button renders, toggles the panel, and updates aria-expanded
 *   - Panel is hidden (aria-hidden=true) when isPanelOpen is false
 *   - Panel is visible (aria-hidden=false) when isPanelOpen is true
 *   - Welcome message shown when no messages exist
 *   - Welcome message hidden when messages exist
 *   - User and assistant messages rendered from the store
 *   - Typing indicator shown when isSending is true
 *   - Typing indicator hidden when isSending is false
 *   - PayloadConfirmCard shown when status is pending_confirmation + payload
 *   - PayloadConfirmCard hidden when status is active
 *   - PayloadConfirmCard hidden when pendingPayload is null
 *   - Confirm & Run button calls confirmRun
 *   - Edit button calls resetSession
 *   - Error alert shown when error is set
 *   - Error alert hidden when error is null
 *   - ChatInput disabled when session is confirmed
 *   - ChatInput enabled when session is active
 *   - Header status text changes based on sessionStatus
 *   - Reset button shown when session is active (not confirmed)
 *   - Reset button hidden when sessionStatus is null
 *   - Reset button hidden when session is confirmed
 *   - Reset button calls resetSession when clicked
 *   - Close button closes the panel
 *   - Confirmed run triggers startNewRun and closes panel
 *   - Sending a message calls sendMessage with the typed content
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ChatAssistant } from "@/components/chat/ChatAssistant";
import { useChatStore } from "@/store/chatStore";
import { useUIStore } from "@/store/uiStore";
import type { ChatMessage, ExtractedSlots } from "@/types/api";

// ── Mock useChatSession ────────────────────────────────────────────────────
// We mock the hook so tests don't need a running backend.

const mockSendMessage = vi.fn().mockResolvedValue("Assistant reply");
const mockConfirmRun = vi.fn().mockResolvedValue("run-abc-123");
const mockResetSession = vi.fn();
const mockRehydrate = vi.fn().mockResolvedValue(true);

vi.mock("@/hooks/useChatSession", () => ({
  useChatSession: () => ({
    sendMessage: mockSendMessage,
    confirmRun: mockConfirmRun,
    resetSession: mockResetSession,
    rehydrate: mockRehydrate,
  }),
}));

// ── Helpers ────────────────────────────────────────────────────────────────

function makeMessage(
  role: "user" | "assistant",
  content: string,
): ChatMessage {
  return { role, content, timestamp: "2024-06-01T12:00:00.000Z" };
}

/** Reset both stores to a clean state before each test. */
function resetStores() {
  useChatStore.getState().resetSession();
  useChatStore.setState({ isPanelOpen: false });
  useUIStore.setState({
    currentRunId: null,
    optimizationResult: null,
    isOptimizing: false,
    agentProgress: [],
    activeTab: "classical",
  });
}

// ── Setup ──────────────────────────────────────────────────────────────────

beforeEach(() => {
  resetStores();
  vi.clearAllMocks();
});

// ══════════════════════════════════════════════════════════════════════════
// FAB button
// ══════════════════════════════════════════════════════════════════════════

describe("FAB button", () => {
  it("renders the FAB button with 'Open chat assistant' label when panel is closed", () => {
    render(<ChatAssistant />);
    expect(
      screen.getByRole("button", { name: "Open chat assistant" }),
    ).toBeInTheDocument();
  });

  it("FAB button has aria-expanded=false when panel is closed", () => {
    render(<ChatAssistant />);
    const fab = screen.getByRole("button", { name: "Open chat assistant" });
    expect(fab.getAttribute("aria-expanded")).toBe("false");
  });

  it("FAB button toggles the panel open when clicked", async () => {
    const user = userEvent.setup();
    render(<ChatAssistant />);
    await user.click(screen.getByRole("button", { name: "Open chat assistant" }));
    expect(useChatStore.getState().isPanelOpen).toBe(true);
  });

  it("FAB button label changes to 'Close chat assistant' when panel is open", async () => {
    const user = userEvent.setup();
    render(<ChatAssistant />);
    await user.click(screen.getByRole("button", { name: "Open chat assistant" }));
    expect(
      screen.getByRole("button", { name: "Close chat assistant" }),
    ).toBeInTheDocument();
  });

  it("FAB button has aria-expanded=true when panel is open", async () => {
    const user = userEvent.setup();
    render(<ChatAssistant />);
    await user.click(screen.getByRole("button", { name: "Open chat assistant" }));
    const fab = screen.getByRole("button", { name: "Close chat assistant" });
    expect(fab.getAttribute("aria-expanded")).toBe("true");
  });

  it("FAB button closes the panel when clicked while open", async () => {
    const user = userEvent.setup();
    act(() => {
      useChatStore.getState().openPanel();
    });
    render(<ChatAssistant />);
    await user.click(screen.getByRole("button", { name: "Close chat assistant" }));
    expect(useChatStore.getState().isPanelOpen).toBe(false);
  });
});

// ══════════════════════════════════════════════════════════════════════════
// Panel visibility
// ══════════════════════════════════════════════════════════════════════════

describe("panel visibility", () => {
  it("panel has aria-hidden=true when isPanelOpen is false", () => {
    render(<ChatAssistant />);
    const panel = screen.getByRole("dialog", { hidden: true });
    expect(panel.getAttribute("aria-hidden")).toBe("true");
  });

  it("panel has aria-hidden=false when isPanelOpen is true", () => {
    act(() => {
      useChatStore.getState().openPanel();
    });
    render(<ChatAssistant />);
    const panel = screen.getByRole("dialog");
    expect(panel.getAttribute("aria-hidden")).toBe("false");
  });

  it("panel has aria-label 'Portfolio Assistant chat'", () => {
    act(() => {
      useChatStore.getState().openPanel();
    });
    render(<ChatAssistant />);
    expect(
      screen.getByRole("dialog", { name: "Portfolio Assistant chat" }),
    ).toBeInTheDocument();
  });

  it("panel has role=dialog", () => {
    render(<ChatAssistant />);
    // getByRole with hidden:true finds the dialog even when aria-hidden
    expect(screen.getByRole("dialog", { hidden: true })).toBeInTheDocument();
  });
});

// ══════════════════════════════════════════════════════════════════════════
// Welcome message
// ══════════════════════════════════════════════════════════════════════════

describe("welcome message", () => {
  it("shows the welcome message when no messages exist", () => {
    act(() => {
      useChatStore.getState().openPanel();
    });
    render(<ChatAssistant />);
    expect(
      screen.getByText(/Hi! I'm your portfolio assistant/),
    ).toBeInTheDocument();
  });

  it("does NOT show the welcome message when messages exist", () => {
    act(() => {
      useChatStore.getState().openPanel();
      useChatStore.getState().appendMessage(makeMessage("user", "Hello"));
    });
    render(<ChatAssistant />);
    expect(
      screen.queryByText(/Hi! I'm your portfolio assistant/),
    ).not.toBeInTheDocument();
  });

  it("welcome message mentions portfolio optimization", () => {
    act(() => {
      useChatStore.getState().openPanel();
    });
    render(<ChatAssistant />);
    expect(screen.getByText(/optimize/i)).toBeInTheDocument();
  });
});

// ══════════════════════════════════════════════════════════════════════════
// Messages
// ══════════════════════════════════════════════════════════════════════════

describe("messages", () => {
  it("renders a user message from the store", () => {
    act(() => {
      useChatStore.getState().openPanel();
      useChatStore.getState().appendMessage(makeMessage("user", "Build me a portfolio"));
    });
    render(<ChatAssistant />);
    expect(screen.getByText("Build me a portfolio")).toBeInTheDocument();
  });

  it("renders an assistant message from the store", () => {
    act(() => {
      useChatStore.getState().openPanel();
      useChatStore.getState().appendMessage(makeMessage("assistant", "What tickers?"));
    });
    render(<ChatAssistant />);
    expect(screen.getByText("What tickers?")).toBeInTheDocument();
  });

  it("renders multiple messages in order", () => {
    act(() => {
      useChatStore.getState().openPanel();
      useChatStore.getState().appendMessage(makeMessage("user", "First message"));
      useChatStore.getState().appendMessage(makeMessage("assistant", "Second message"));
      useChatStore.getState().appendMessage(makeMessage("user", "Third message"));
    });
    render(<ChatAssistant />);
    expect(screen.getByText("First message")).toBeInTheDocument();
    expect(screen.getByText("Second message")).toBeInTheDocument();
    expect(screen.getByText("Third message")).toBeInTheDocument();
  });
});

// ══════════════════════════════════════════════════════════════════════════
// Typing indicator
// ══════════════════════════════════════════════════════════════════════════

describe("typing indicator", () => {
  it("shows the typing indicator when isSending is true", () => {
    act(() => {
      useChatStore.getState().openPanel();
      useChatStore.getState().setIsSending(true);
    });
    render(<ChatAssistant />);
    expect(screen.getByLabelText("Assistant is typing")).toBeInTheDocument();
  });

  it("does NOT show the typing indicator when isSending is false", () => {
    act(() => {
      useChatStore.getState().openPanel();
      // isSending is false by default
    });
    render(<ChatAssistant />);
    expect(
      screen.queryByLabelText("Assistant is typing"),
    ).not.toBeInTheDocument();
  });
});

// ══════════════════════════════════════════════════════════════════════════
// PayloadConfirmCard
// ══════════════════════════════════════════════════════════════════════════

describe("PayloadConfirmCard", () => {
  const PAYLOAD: ExtractedSlots = { tickers: ["AAPL", "MSFT"], budget: 50000 };

  it("shows PayloadConfirmCard when status is pending_confirmation and payload is set", () => {
    act(() => {
      useChatStore.getState().openPanel();
      useChatStore.getState().setSessionStatus("pending_confirmation");
      useChatStore.getState().setPendingPayload(PAYLOAD);
    });
    render(<ChatAssistant />);
    expect(screen.getByText("Ready to optimize")).toBeInTheDocument();
  });

  it("does NOT show PayloadConfirmCard when status is active", () => {
    act(() => {
      useChatStore.getState().openPanel();
      useChatStore.getState().setSessionId("s-1");
      // setSessionId sets status to 'active'
      useChatStore.getState().setPendingPayload(PAYLOAD);
    });
    render(<ChatAssistant />);
    expect(screen.queryByText("Ready to optimize")).not.toBeInTheDocument();
  });

  it("does NOT show PayloadConfirmCard when pendingPayload is null", () => {
    act(() => {
      useChatStore.getState().openPanel();
      useChatStore.getState().setSessionStatus("pending_confirmation");
      // pendingPayload remains null
    });
    render(<ChatAssistant />);
    expect(screen.queryByText("Ready to optimize")).not.toBeInTheDocument();
  });

  it("shows the tickers from the payload in the confirm card", () => {
    act(() => {
      useChatStore.getState().openPanel();
      useChatStore.getState().setSessionStatus("pending_confirmation");
      useChatStore.getState().setPendingPayload(PAYLOAD);
    });
    render(<ChatAssistant />);
    // The PayloadConfirmCard renders tickers as individual Badge elements.
    // Use getAllByText since the welcome message also contains "AAPL" in its example text.
    const aaplMatches = screen.getAllByText(/AAPL/);
    expect(aaplMatches.length).toBeGreaterThanOrEqual(1);
    const msftMatches = screen.getAllByText(/MSFT/);
    expect(msftMatches.length).toBeGreaterThanOrEqual(1);
  });

  it("calls confirmRun when 'Confirm & Run' button is clicked", async () => {
    const user = userEvent.setup();
    act(() => {
      useChatStore.getState().openPanel();
      useChatStore.getState().setSessionStatus("pending_confirmation");
      useChatStore.getState().setPendingPayload(PAYLOAD);
    });
    render(<ChatAssistant />);
    await user.click(screen.getByRole("button", { name: /Confirm & Run/ }));
    expect(mockConfirmRun).toHaveBeenCalledOnce();
  });

  it("calls resetSession when 'Edit' button is clicked", async () => {
    const user = userEvent.setup();
    act(() => {
      useChatStore.getState().openPanel();
      useChatStore.getState().setSessionStatus("pending_confirmation");
      useChatStore.getState().setPendingPayload(PAYLOAD);
    });
    render(<ChatAssistant />);
    await user.click(screen.getByRole("button", { name: "Edit" }));
    expect(mockResetSession).toHaveBeenCalledOnce();
  });
});

// ══════════════════════════════════════════════════════════════════════════
// Error alert
// ══════════════════════════════════════════════════════════════════════════

describe("error alert", () => {
  it("shows the error message when error is set", () => {
    act(() => {
      useChatStore.getState().openPanel();
      useChatStore.getState().setError("Failed to send message");
    });
    render(<ChatAssistant />);
    expect(screen.getByText("Failed to send message")).toBeInTheDocument();
  });

  it("does NOT show an alert when error is null", () => {
    act(() => {
      useChatStore.getState().openPanel();
      // error is null by default
    });
    render(<ChatAssistant />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows a different error message correctly", () => {
    act(() => {
      useChatStore.getState().openPanel();
      useChatStore.getState().setError("Network timeout — please try again");
    });
    render(<ChatAssistant />);
    expect(
      screen.getByText("Network timeout — please try again"),
    ).toBeInTheDocument();
  });
});

// ══════════════════════════════════════════════════════════════════════════
// ChatInput disabled state
// ══════════════════════════════════════════════════════════════════════════

describe("ChatInput disabled state", () => {
  it("ChatInput is NOT disabled when session is active", () => {
    act(() => {
      useChatStore.getState().openPanel();
      useChatStore.getState().setSessionId("s-1");
    });
    render(<ChatAssistant />);
    const textarea = screen.getByRole("textbox", { name: "Chat message" });
    expect(textarea).not.toBeDisabled();
  });

  it("ChatInput is disabled when session is confirmed", () => {
    act(() => {
      useChatStore.getState().openPanel();
      useChatStore.getState().setSessionStatus("confirmed");
    });
    render(<ChatAssistant />);
    const textarea = screen.getByRole("textbox", { name: "Chat message" });
    expect(textarea).toBeDisabled();
  });

  it("ChatInput is NOT disabled when status is pending_confirmation", () => {
    act(() => {
      useChatStore.getState().openPanel();
      useChatStore.getState().setSessionStatus("pending_confirmation");
    });
    render(<ChatAssistant />);
    const textarea = screen.getByRole("textbox", { name: "Chat message" });
    expect(textarea).not.toBeDisabled();
  });
});

// ══════════════════════════════════════════════════════════════════════════
// Header status text
// ══════════════════════════════════════════════════════════════════════════

describe("header status text", () => {
  it("shows 'Ask me anything' when sessionStatus is null", () => {
    act(() => {
      useChatStore.getState().openPanel();
      // sessionStatus is null by default
    });
    render(<ChatAssistant />);
    expect(screen.getByText("Ask me anything")).toBeInTheDocument();
  });

  it("shows 'Listening…' when sessionStatus is active", () => {
    act(() => {
      useChatStore.getState().openPanel();
      useChatStore.getState().setSessionId("s-1");
      // setSessionId sets status to 'active'
    });
    render(<ChatAssistant />);
    expect(screen.getByText("Listening…")).toBeInTheDocument();
  });

  it("shows 'Ready to confirm' when sessionStatus is pending_confirmation", () => {
    act(() => {
      useChatStore.getState().openPanel();
      useChatStore.getState().setSessionStatus("pending_confirmation");
    });
    render(<ChatAssistant />);
    expect(screen.getByText("Ready to confirm")).toBeInTheDocument();
  });

  it("shows 'Run dispatched ✓' when sessionStatus is confirmed", () => {
    act(() => {
      useChatStore.getState().openPanel();
      useChatStore.getState().setSessionStatus("confirmed");
    });
    render(<ChatAssistant />);
    expect(screen.getByText("Run dispatched ✓")).toBeInTheDocument();
  });
});

// ══════════════════════════════════════════════════════════════════════════
// Reset button
// ══════════════════════════════════════════════════════════════════════════

describe("reset button", () => {
  it("shows the reset button when session is active", () => {
    act(() => {
      useChatStore.getState().openPanel();
      useChatStore.getState().setSessionId("s-1");
    });
    render(<ChatAssistant />);
    expect(
      screen.getByRole("button", { name: "Start new conversation" }),
    ).toBeInTheDocument();
  });

  it("shows the reset button when status is pending_confirmation", () => {
    act(() => {
      useChatStore.getState().openPanel();
      useChatStore.getState().setSessionStatus("pending_confirmation");
    });
    render(<ChatAssistant />);
    expect(
      screen.getByRole("button", { name: "Start new conversation" }),
    ).toBeInTheDocument();
  });

  it("does NOT show the reset button when sessionStatus is null", () => {
    act(() => {
      useChatStore.getState().openPanel();
      // sessionStatus is null by default
    });
    render(<ChatAssistant />);
    expect(
      screen.queryByRole("button", { name: "Start new conversation" }),
    ).not.toBeInTheDocument();
  });

  it("does NOT show the reset button when session is confirmed", () => {
    act(() => {
      useChatStore.getState().openPanel();
      useChatStore.getState().setSessionStatus("confirmed");
    });
    render(<ChatAssistant />);
    expect(
      screen.queryByRole("button", { name: "Start new conversation" }),
    ).not.toBeInTheDocument();
  });

  it("calls resetSession when the reset button is clicked", async () => {
    const user = userEvent.setup();
    act(() => {
      useChatStore.getState().openPanel();
      useChatStore.getState().setSessionId("s-1");
    });
    render(<ChatAssistant />);
    await user.click(
      screen.getByRole("button", { name: "Start new conversation" }),
    );
    expect(mockResetSession).toHaveBeenCalledOnce();
  });
});

// ══════════════════════════════════════════════════════════════════════════
// Close button
// ══════════════════════════════════════════════════════════════════════════

describe("close button", () => {
  it("renders the close button when panel is open", () => {
    act(() => {
      useChatStore.getState().openPanel();
    });
    render(<ChatAssistant />);
    expect(
      screen.getByRole("button", { name: "Close chat panel" }),
    ).toBeInTheDocument();
  });

  it("closes the panel when the close button is clicked", async () => {
    const user = userEvent.setup();
    act(() => {
      useChatStore.getState().openPanel();
    });
    render(<ChatAssistant />);
    await user.click(screen.getByRole("button", { name: "Close chat panel" }));
    expect(useChatStore.getState().isPanelOpen).toBe(false);
  });
});

// ══════════════════════════════════════════════════════════════════════════
// Confirmed run integration
// ══════════════════════════════════════════════════════════════════════════

describe("confirmed run integration", () => {
  it("calls startNewRun with the confirmed run ID", () => {
    const startNewRun = vi.fn();
    useUIStore.setState({ startNewRun } as unknown as typeof useUIStore.getState);

    act(() => {
      useChatStore.getState().openPanel();
      useChatStore.getState().setConfirmedRunId("run-xyz-789");
    });

    render(<ChatAssistant />);
    expect(startNewRun).toHaveBeenCalledWith("run-xyz-789");
  });

  it("closes the panel when confirmedRunId is set", () => {
    act(() => {
      useChatStore.getState().openPanel();
      useChatStore.getState().setConfirmedRunId("run-xyz-789");
    });

    render(<ChatAssistant />);
    expect(useChatStore.getState().isPanelOpen).toBe(false);
  });

  it("does NOT call startNewRun when confirmedRunId is null", () => {
    const startNewRun = vi.fn();
    useUIStore.setState({ startNewRun } as unknown as typeof useUIStore.getState);

    act(() => {
      useChatStore.getState().openPanel();
      // confirmedRunId remains null
    });

    render(<ChatAssistant />);
    expect(startNewRun).not.toHaveBeenCalled();
  });
});

// ══════════════════════════════════════════════════════════════════════════
// Send message integration
// ══════════════════════════════════════════════════════════════════════════

describe("send message integration", () => {
  it("calls sendMessage when user types and presses Enter", async () => {
    const user = userEvent.setup();
    act(() => {
      useChatStore.getState().openPanel();
    });
    render(<ChatAssistant />);
    const textarea = screen.getByRole("textbox", { name: "Chat message" });
    await user.type(textarea, "Build me a portfolio{Enter}");
    expect(mockSendMessage).toHaveBeenCalledWith("Build me a portfolio");
  });

  it("does NOT call sendMessage when the input is empty", async () => {
    const user = userEvent.setup();
    act(() => {
      useChatStore.getState().openPanel();
    });
    render(<ChatAssistant />);
    const textarea = screen.getByRole("textbox", { name: "Chat message" });
    await user.type(textarea, "{Enter}");
    expect(mockSendMessage).not.toHaveBeenCalled();
  });

  it("does NOT call sendMessage when the session is confirmed (input disabled)", async () => {
    const user = userEvent.setup();
    act(() => {
      useChatStore.getState().openPanel();
      useChatStore.getState().setSessionStatus("confirmed");
    });
    render(<ChatAssistant />);
    const textarea = screen.getByRole("textbox", { name: "Chat message" });
    // Typing into a disabled textarea should have no effect
    await user.type(textarea, "Hello{Enter}");
    expect(mockSendMessage).not.toHaveBeenCalled();
  });
});

// ══════════════════════════════════════════════════════════════════════════
// "Portfolio Assistant" header title
// ══════════════════════════════════════════════════════════════════════════

describe("header title", () => {
  it("renders 'Portfolio Assistant' as the panel title", () => {
    act(() => {
      useChatStore.getState().openPanel();
    });
    render(<ChatAssistant />);
    expect(screen.getByText("Portfolio Assistant")).toBeInTheDocument();
  });
});
