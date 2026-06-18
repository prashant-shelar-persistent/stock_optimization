/**
 * Tests for @/components/chat/ChatAssistant
 *
 * ChatAssistant is the floating panel + FAB button that orchestrates the
 * entire chat experience. It reads from chatStore and delegates API calls
 * to useChatSession.
 *
 * We mock useChatSession and the heavy child components to focus on the
 * orchestration logic.
 *
 * Covers:
 *   - FAB button renders and toggles the panel
 *   - Panel is hidden when isPanelOpen is false
 *   - Panel is visible when isPanelOpen is true
 *   - Welcome message shown when no messages exist
 *   - Messages rendered when messages exist
 *   - Typing indicator shown when isSending is true
 *   - PayloadConfirmCard shown when status is pending_confirmation + payload
 *   - Error alert shown when error is set
 *   - ChatInput disabled when session is confirmed
 *   - Header status text changes based on sessionStatus
 *   - Reset button shown when session is active (not confirmed)
 *   - Reset button hidden when session is confirmed
 *   - Close button closes the panel
 *   - Confirmed run triggers startNewRun and closes panel
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ChatAssistant } from "@/components/chat/ChatAssistant";
import { useChatStore } from "@/store/chatStore";
import { useUIStore } from "@/store/uiStore";
import type { ChatMessage, ExtractedSlots } from "@/types/api";

// ── Mock useChatSession ────────────────────────────────────────────────────

const mockSendMessage = vi.fn().mockResolvedValue("Assistant reply");
const mockConfirmRun = vi.fn().mockResolvedValue("run-abc-123");
const mockResetSession = vi.fn();
const mockRehydrate = vi.fn().mockResolvedValue(true);

// Mutable variable so individual tests can override optimisticMessages.
let mockOptimisticMessages: ChatMessage[] = [];

vi.mock("@/hooks/useChatSession", () => ({
  useChatSession: () => ({
    sendMessage: mockSendMessage,
    confirmRun: mockConfirmRun,
    resetSession: mockResetSession,
    rehydrate: mockRehydrate,
    isPending: false,
    get optimisticMessages() {
      return mockOptimisticMessages;
    },
  }),
}));

// ── Helpers ────────────────────────────────────────────────────────────────

function makeMessage(
  role: "user" | "assistant",
  content: string,
): ChatMessage {
  return { role, content, timestamp: "2024-06-01T12:00:00.000Z" };
}

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
  // Reset the optimistic messages mock to empty
  mockOptimisticMessages = [];
}

// ── Setup ──────────────────────────────────────────────────────────────────

beforeEach(() => {
  resetStores();
  vi.clearAllMocks();
});

// ── FAB button ─────────────────────────────────────────────────────────────

describe("FAB button", () => {
  it("renders the FAB button", () => {
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
    const fab = screen.getByRole("button", { name: "Open chat assistant" });
    await user.click(fab);
    expect(useChatStore.getState().isPanelOpen).toBe(true);
  });

  it("FAB button shows 'Close chat assistant' label when panel is open", async () => {
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
});

// ── Panel visibility ───────────────────────────────────────────────────────

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
});

// ── Welcome message ────────────────────────────────────────────────────────

describe("welcome message", () => {
  it("shows welcome message when no messages exist", () => {
    act(() => {
      useChatStore.getState().openPanel();
    });
    render(<ChatAssistant />);
    expect(screen.getByText(/Hi! I'm your portfolio assistant/)).toBeInTheDocument();
  });

  it("does NOT show welcome message when messages exist", () => {
    const msg = makeMessage("user", "Hello");
    act(() => {
      useChatStore.getState().openPanel();
      useChatStore.getState().appendMessage(msg);
      mockOptimisticMessages = [msg];
    });
    render(<ChatAssistant />);
    expect(
      screen.queryByText(/Hi! I'm your portfolio assistant/),
    ).not.toBeInTheDocument();
  });
});

// ── Messages ───────────────────────────────────────────────────────────────

describe("messages", () => {
  it("renders user messages from the store", () => {
    const msg = makeMessage("user", "Build me a portfolio");
    act(() => {
      useChatStore.getState().openPanel();
      useChatStore.getState().appendMessage(msg);
      mockOptimisticMessages = [msg];
    });
    render(<ChatAssistant />);
    expect(screen.getByText("Build me a portfolio")).toBeInTheDocument();
  });

  it("renders assistant messages from the store", () => {
    const msg = makeMessage("assistant", "What tickers?");
    act(() => {
      useChatStore.getState().openPanel();
      useChatStore.getState().appendMessage(msg);
      mockOptimisticMessages = [msg];
    });
    render(<ChatAssistant />);
    expect(screen.getByText("What tickers?")).toBeInTheDocument();
  });

  it("renders multiple messages in order", () => {
    const msgs = [
      makeMessage("user", "First message"),
      makeMessage("assistant", "Second message"),
    ];
    act(() => {
      useChatStore.getState().openPanel();
      msgs.forEach((m) => useChatStore.getState().appendMessage(m));
      mockOptimisticMessages = msgs;
    });
    render(<ChatAssistant />);
    expect(screen.getByText("First message")).toBeInTheDocument();
    expect(screen.getByText("Second message")).toBeInTheDocument();
  });
});

// ── Typing indicator ───────────────────────────────────────────────────────

describe("typing indicator", () => {
  it("shows typing indicator when isSending is true", () => {
    act(() => {
      useChatStore.getState().openPanel();
      useChatStore.getState().setIsSending(true);
    });
    render(<ChatAssistant />);
    expect(screen.getByLabelText("Assistant is typing")).toBeInTheDocument();
  });

  it("does NOT show typing indicator when isSending is false", () => {
    act(() => {
      useChatStore.getState().openPanel();
    });
    render(<ChatAssistant />);
    expect(screen.queryByLabelText("Assistant is typing")).not.toBeInTheDocument();
  });
});

// ── PayloadConfirmCard ─────────────────────────────────────────────────────

describe("PayloadConfirmCard", () => {
  const PAYLOAD: ExtractedSlots = { tickers: ["AAPL"], budget: 10000 };

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

  it("calls confirmRun when Confirm & Run is clicked", async () => {
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

  it("calls resetSession when Edit is clicked", async () => {
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

// ── Error alert ────────────────────────────────────────────────────────────

describe("error alert", () => {
  it("shows error alert when error is set", () => {
    act(() => {
      useChatStore.getState().openPanel();
      useChatStore.getState().setError("Failed to send message");
    });
    render(<ChatAssistant />);
    expect(screen.getByText("Failed to send message")).toBeInTheDocument();
  });

  it("does NOT show error alert when error is null", () => {
    act(() => {
      useChatStore.getState().openPanel();
    });
    render(<ChatAssistant />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

// ── ChatInput disabled state ───────────────────────────────────────────────

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
});

// ── Header status text ─────────────────────────────────────────────────────

describe("header status text", () => {
  it("shows 'Ask me anything' when sessionStatus is null", () => {
    act(() => {
      useChatStore.getState().openPanel();
    });
    render(<ChatAssistant />);
    expect(screen.getByText("Ask me anything")).toBeInTheDocument();
  });

  it("shows 'Listening…' when sessionStatus is active", () => {
    act(() => {
      useChatStore.getState().openPanel();
      useChatStore.getState().setSessionId("s-1");
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

// ── Reset button ───────────────────────────────────────────────────────────

describe("reset button", () => {
  it("shows reset button when session is active", () => {
    act(() => {
      useChatStore.getState().openPanel();
      useChatStore.getState().setSessionId("s-1");
    });
    render(<ChatAssistant />);
    expect(
      screen.getByRole("button", { name: "Start new conversation" }),
    ).toBeInTheDocument();
  });

  it("does NOT show reset button when sessionStatus is null", () => {
    act(() => {
      useChatStore.getState().openPanel();
    });
    render(<ChatAssistant />);
    expect(
      screen.queryByRole("button", { name: "Start new conversation" }),
    ).not.toBeInTheDocument();
  });

  it("does NOT show reset button when session is confirmed", () => {
    act(() => {
      useChatStore.getState().openPanel();
      useChatStore.getState().setSessionStatus("confirmed");
    });
    render(<ChatAssistant />);
    expect(
      screen.queryByRole("button", { name: "Start new conversation" }),
    ).not.toBeInTheDocument();
  });

  it("calls resetSession when reset button is clicked", async () => {
    const user = userEvent.setup();
    act(() => {
      useChatStore.getState().openPanel();
      useChatStore.getState().setSessionId("s-1");
    });
    render(<ChatAssistant />);
    await user.click(screen.getByRole("button", { name: "Start new conversation" }));
    expect(mockResetSession).toHaveBeenCalledOnce();
  });
});

// ── Close button ───────────────────────────────────────────────────────────

describe("close button", () => {
  it("renders the close button", () => {
    act(() => {
      useChatStore.getState().openPanel();
    });
    render(<ChatAssistant />);
    expect(
      screen.getByRole("button", { name: "Close chat panel" }),
    ).toBeInTheDocument();
  });

  it("closes the panel when close button is clicked", async () => {
    const user = userEvent.setup();
    act(() => {
      useChatStore.getState().openPanel();
    });
    render(<ChatAssistant />);
    await user.click(screen.getByRole("button", { name: "Close chat panel" }));
    expect(useChatStore.getState().isPanelOpen).toBe(false);
  });
});

// ── Confirmed run integration ──────────────────────────────────────────────

describe("confirmed run integration", () => {
  it("calls startNewRun when confirmedRunId is set", () => {
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
});

// ── Send message integration ───────────────────────────────────────────────

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
});
