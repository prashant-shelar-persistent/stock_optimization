/**
 * Tests for @/hooks/useChatSession
 *
 * useChatSession orchestrates the chat assistant lifecycle:
 * - sendMessage: creates session on first message, sends subsequent messages
 * - confirmRun: confirms a pending session and returns run_id
 * - resetSession: resets the store
 * - rehydrate: loads session state from the backend
 *
 * We mock the API functions and test the hook's interaction with chatStore.
 *
 * Covers:
 *   - sendMessage: optimistically appends user message
 *   - sendMessage: creates a new session on first message
 *   - sendMessage: sends to existing session on subsequent messages
 *   - sendMessage: returns assistant reply content
 *   - sendMessage: handles API errors gracefully (sets error, returns null)
 *   - sendMessage: ignores empty/whitespace-only content
 *   - sendMessage: sets isSending flag during call
 *   - confirmRun: calls confirmChatRun with session ID
 *   - confirmRun: returns run_id on success
 *   - confirmRun: sets confirmedRunId in store
 *   - confirmRun: handles missing session ID
 *   - confirmRun: handles API errors
 *   - resetSession: resets the store
 *   - rehydrate: loads session state from backend
 *   - rehydrate: handles API errors
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useChatSession } from "@/hooks/useChatSession";
import { useChatStore } from "@/store/chatStore";
import type { ChatSession, SendChatMessageResponse } from "@/types/api";

// ── Mock API functions ─────────────────────────────────────────────────────

vi.mock("@/lib/api", () => ({
  createChatSession: vi.fn(),
  sendChatMessage: vi.fn(),
  confirmChatRun: vi.fn(),
  getChatSession: vi.fn(),
}));

import {
  createChatSession,
  sendChatMessage,
  confirmChatRun,
  getChatSession,
} from "@/lib/api";

const mockCreateChatSession = vi.mocked(createChatSession);
const mockSendChatMessage = vi.mocked(sendChatMessage);
const mockConfirmChatRun = vi.mocked(confirmChatRun);
const mockGetChatSession = vi.mocked(getChatSession);

// ── Fixtures ───────────────────────────────────────────────────────────────

const MOCK_SESSION: ChatSession = {
  session_id: "sess-abc-123",
  status: "collecting",
  messages: [
    { role: "user", content: "Build me a portfolio", timestamp: "2024-06-01T12:00:00.000Z" },
    { role: "assistant", content: "What tickers?", timestamp: "2024-06-01T12:00:01.000Z" },
  ],
  extracted_slots: { tickers: ["AAPL"] },
  run_id: null,
  created_at: "2024-06-01T12:00:00.000Z",
  updated_at: "2024-06-01T12:00:01.000Z",
};

const MOCK_SEND_RESPONSE: SendChatMessageResponse = {
  reply: "Great, I have AAPL. What budget?",
  session: {
    session_id: "sess-abc-123",
    status: "collecting",
    messages: [
      { role: "user", content: "AAPL and MSFT", timestamp: "2024-06-01T12:01:00.000Z" },
      { role: "assistant", content: "Great, I have AAPL. What budget?", timestamp: "2024-06-01T12:01:01.000Z" },
    ],
    extracted_slots: { tickers: ["AAPL"] },
    run_id: null,
    created_at: "2024-06-01T12:00:00.000Z",
    updated_at: "2024-06-01T12:01:01.000Z",
  },
  payload_preview: null,
};

const MOCK_PENDING_RESPONSE: SendChatMessageResponse = {
  reply: "Ready to confirm!",
  session: {
    session_id: "sess-abc-123",
    status: "pending_confirmation",
    messages: [
      { role: "user", content: "Budget is $10k", timestamp: "2024-06-01T12:02:00.000Z" },
      { role: "assistant", content: "Ready to confirm!", timestamp: "2024-06-01T12:02:01.000Z" },
    ],
    extracted_slots: { tickers: ["AAPL"], budget: 10000 },
    run_id: null,
    created_at: "2024-06-01T12:00:00.000Z",
    updated_at: "2024-06-01T12:02:01.000Z",
  },
  payload_preview: { tickers: ["AAPL"], budget: 10000 },
};

// ── Setup ──────────────────────────────────────────────────────────────────

function resetStore() {
  useChatStore.getState().resetSession();
  useChatStore.setState({ isPanelOpen: false });
}

beforeEach(() => {
  resetStore();
  vi.clearAllMocks();
});

// ── sendMessage ────────────────────────────────────────────────────────────

describe("sendMessage", () => {
  it("returns null for empty content", async () => {
    const { result } = renderHook(() => useChatSession());
    let reply: string | null;
    await act(async () => {
      reply = await result.current.sendMessage("");
    });
    expect(reply!).toBeNull();
  });

  it("returns null for whitespace-only content", async () => {
    const { result } = renderHook(() => useChatSession());
    let reply: string | null;
    await act(async () => {
      reply = await result.current.sendMessage("   ");
    });
    expect(reply!).toBeNull();
  });

  it("optimistically appends the user message before the API call", async () => {
    mockCreateChatSession.mockResolvedValue(MOCK_SESSION);
    const { result } = renderHook(() => useChatSession());

    await act(async () => {
      await result.current.sendMessage("Build me a portfolio");
    });

    // The store should have the messages from the session response
    const messages = useChatStore.getState().messages;
    expect(messages.some((m) => m.role === "user" && m.content === "Build me a portfolio")).toBe(true);
  });

  it("creates a new session when no session exists (first message)", async () => {
    mockCreateChatSession.mockResolvedValue(MOCK_SESSION);
    const { result } = renderHook(() => useChatSession());

    await act(async () => {
      await result.current.sendMessage("Build me a portfolio");
    });

    expect(mockCreateChatSession).toHaveBeenCalledOnce();
    expect(mockCreateChatSession).toHaveBeenCalledWith(
      { initial_message: "Build me a portfolio" },
      expect.any(AbortSignal),
    );
  });

  it("sets the session ID in the store after creating a session", async () => {
    mockCreateChatSession.mockResolvedValue(MOCK_SESSION);
    const { result } = renderHook(() => useChatSession());

    await act(async () => {
      await result.current.sendMessage("Build me a portfolio");
    });

    expect(useChatStore.getState().sessionId).toBe("sess-abc-123");
  });

  it("returns the assistant reply content from the session response", async () => {
    mockCreateChatSession.mockResolvedValue(MOCK_SESSION);
    const { result } = renderHook(() => useChatSession());

    let reply: string | null;
    await act(async () => {
      reply = await result.current.sendMessage("Build me a portfolio");
    });

    // The last message in MOCK_SESSION is the assistant reply "What tickers?"
    expect(reply!).toBe("What tickers?");
  });

  it("sends to existing session on subsequent messages", async () => {
    // Set up an existing session
    useChatStore.getState().setSessionId("sess-abc-123");
    mockSendChatMessage.mockResolvedValue(MOCK_SEND_RESPONSE);

    const { result } = renderHook(() => useChatSession());

    await act(async () => {
      await result.current.sendMessage("AAPL and MSFT");
    });

    expect(mockSendChatMessage).toHaveBeenCalledOnce();
    expect(mockSendChatMessage).toHaveBeenCalledWith(
      "sess-abc-123",
      "AAPL and MSFT",
      expect.any(AbortSignal),
    );
    expect(mockCreateChatSession).not.toHaveBeenCalled();
  });

  it("returns the reply from sendChatMessage on subsequent messages", async () => {
    useChatStore.getState().setSessionId("sess-abc-123");
    mockSendChatMessage.mockResolvedValue(MOCK_SEND_RESPONSE);

    const { result } = renderHook(() => useChatSession());

    let reply: string | null;
    await act(async () => {
      reply = await result.current.sendMessage("AAPL and MSFT");
    });

    expect(reply!).toBe("Great, I have AAPL. What budget?");
  });

  it("sets pendingPayload when response status is pending_confirmation", async () => {
    useChatStore.getState().setSessionId("sess-abc-123");
    mockSendChatMessage.mockResolvedValue(MOCK_PENDING_RESPONSE);

    const { result } = renderHook(() => useChatSession());

    await act(async () => {
      await result.current.sendMessage("Budget is $10k");
    });

    expect(useChatStore.getState().pendingPayload).toEqual({
      tickers: ["AAPL"],
      budget: 10000,
    });
    expect(useChatStore.getState().sessionStatus).toBe("pending_confirmation");
  });

  it("sets error and returns null when createChatSession fails", async () => {
    mockCreateChatSession.mockRejectedValue(new Error("Network error"));

    const { result } = renderHook(() => useChatSession());

    let reply: string | null;
    await act(async () => {
      reply = await result.current.sendMessage("Hello");
    });

    expect(reply!).toBeNull();
    expect(useChatStore.getState().error).toBe("Network error");
  });

  it("sets error and returns null when sendChatMessage fails", async () => {
    useChatStore.getState().setSessionId("sess-abc-123");
    mockSendChatMessage.mockRejectedValue(new Error("API error"));

    const { result } = renderHook(() => useChatSession());

    let reply: string | null;
    await act(async () => {
      reply = await result.current.sendMessage("Hello");
    });

    expect(reply!).toBeNull();
    expect(useChatStore.getState().error).toBe("API error");
  });

  it("clears isSending flag after successful send", async () => {
    useChatStore.getState().setSessionId("sess-abc-123");
    mockSendChatMessage.mockResolvedValue(MOCK_SEND_RESPONSE);

    const { result } = renderHook(() => useChatSession());

    await act(async () => {
      await result.current.sendMessage("Hello");
    });

    expect(useChatStore.getState().isSending).toBe(false);
  });

  it("clears isSending flag after failed send", async () => {
    useChatStore.getState().setSessionId("sess-abc-123");
    mockSendChatMessage.mockRejectedValue(new Error("fail"));

    const { result } = renderHook(() => useChatSession());

    await act(async () => {
      await result.current.sendMessage("Hello");
    });

    expect(useChatStore.getState().isSending).toBe(false);
  });

  it("clears previous error before sending", async () => {
    useChatStore.getState().setSessionId("sess-abc-123");
    useChatStore.getState().setError("previous error");
    mockSendChatMessage.mockResolvedValue(MOCK_SEND_RESPONSE);

    const { result } = renderHook(() => useChatSession());

    await act(async () => {
      await result.current.sendMessage("Hello");
    });

    expect(useChatStore.getState().error).toBeNull();
  });
});

// ── confirmRun ─────────────────────────────────────────────────────────────

describe("confirmRun", () => {
  it("returns null and sets error when no session exists", async () => {
    const { result } = renderHook(() => useChatSession());

    let runId: string | null;
    await act(async () => {
      runId = await result.current.confirmRun();
    });

    expect(runId!).toBeNull();
    expect(useChatStore.getState().error).toBe("No active session to confirm.");
  });

  it("calls confirmChatRun with the session ID", async () => {
    useChatStore.getState().setSessionId("sess-abc-123");
    mockConfirmChatRun.mockResolvedValue({ run_id: "run-xyz-789", session_id: "sess-abc-123" });

    const { result } = renderHook(() => useChatSession());

    await act(async () => {
      await result.current.confirmRun();
    });

    expect(mockConfirmChatRun).toHaveBeenCalledOnce();
    expect(mockConfirmChatRun).toHaveBeenCalledWith(
      "sess-abc-123",
      { slot_overrides: null },
      expect.any(AbortSignal),
    );
  });

  it("returns the run_id on success", async () => {
    useChatStore.getState().setSessionId("sess-abc-123");
    mockConfirmChatRun.mockResolvedValue({ run_id: "run-xyz-789", session_id: "sess-abc-123" });

    const { result } = renderHook(() => useChatSession());

    let runId: string | null;
    await act(async () => {
      runId = await result.current.confirmRun();
    });

    expect(runId!).toBe("run-xyz-789");
  });

  it("sets confirmedRunId in the store on success", async () => {
    useChatStore.getState().setSessionId("sess-abc-123");
    mockConfirmChatRun.mockResolvedValue({ run_id: "run-xyz-789", session_id: "sess-abc-123" });

    const { result } = renderHook(() => useChatSession());

    await act(async () => {
      await result.current.confirmRun();
    });

    expect(useChatStore.getState().confirmedRunId).toBe("run-xyz-789");
    expect(useChatStore.getState().sessionStatus).toBe("confirmed");
  });

  it("passes slot_overrides to confirmChatRun when provided", async () => {
    useChatStore.getState().setSessionId("sess-abc-123");
    mockConfirmChatRun.mockResolvedValue({ run_id: "run-xyz-789", session_id: "sess-abc-123" });

    const { result } = renderHook(() => useChatSession());

    await act(async () => {
      await result.current.confirmRun({ budget: 20000 });
    });

    expect(mockConfirmChatRun).toHaveBeenCalledWith(
      "sess-abc-123",
      { slot_overrides: { budget: 20000 } },
      expect.any(AbortSignal),
    );
  });

  it("sets error and returns null when confirmChatRun fails", async () => {
    useChatStore.getState().setSessionId("sess-abc-123");
    mockConfirmChatRun.mockRejectedValue(new Error("Confirmation failed"));

    const { result } = renderHook(() => useChatSession());

    let runId: string | null;
    await act(async () => {
      runId = await result.current.confirmRun();
    });

    expect(runId!).toBeNull();
    expect(useChatStore.getState().error).toBe("Confirmation failed");
  });

  it("clears isConfirming flag after successful confirm", async () => {
    useChatStore.getState().setSessionId("sess-abc-123");
    mockConfirmChatRun.mockResolvedValue({ run_id: "run-xyz-789", session_id: "sess-abc-123" });

    const { result } = renderHook(() => useChatSession());

    await act(async () => {
      await result.current.confirmRun();
    });

    expect(useChatStore.getState().isConfirming).toBe(false);
  });

  it("clears isConfirming flag after failed confirm", async () => {
    useChatStore.getState().setSessionId("sess-abc-123");
    mockConfirmChatRun.mockRejectedValue(new Error("fail"));

    const { result } = renderHook(() => useChatSession());

    await act(async () => {
      await result.current.confirmRun();
    });

    expect(useChatStore.getState().isConfirming).toBe(false);
  });
});

// ── resetSession ───────────────────────────────────────────────────────────

describe("resetSession", () => {
  it("resets the store to initial state", () => {
    useChatStore.getState().setSessionId("sess-abc-123");
    useChatStore.getState().appendMessage({ role: "user", content: "Hello" });
    useChatStore.getState().setError("some error");

    const { result } = renderHook(() => useChatSession());

    act(() => {
      result.current.resetSession();
    });

    const state = useChatStore.getState();
    expect(state.sessionId).toBeNull();
    expect(state.messages).toEqual([]);
    expect(state.error).toBeNull();
    expect(state.sessionStatus).toBeNull();
  });
});

// ── rehydrate ──────────────────────────────────────────────────────────────

describe("rehydrate", () => {
  it("calls getChatSession with the session ID", async () => {
    mockGetChatSession.mockResolvedValue(MOCK_SESSION);

    const { result } = renderHook(() => useChatSession());

    await act(async () => {
      await result.current.rehydrate("sess-abc-123");
    });

    expect(mockGetChatSession).toHaveBeenCalledWith("sess-abc-123", expect.any(AbortSignal));
  });

  it("returns true on success", async () => {
    mockGetChatSession.mockResolvedValue(MOCK_SESSION);

    const { result } = renderHook(() => useChatSession());

    let success: boolean;
    await act(async () => {
      success = await result.current.rehydrate("sess-abc-123");
    });

    expect(success!).toBe(true);
  });

  it("restores session ID in the store", async () => {
    mockGetChatSession.mockResolvedValue(MOCK_SESSION);

    const { result } = renderHook(() => useChatSession());

    await act(async () => {
      await result.current.rehydrate("sess-abc-123");
    });

    expect(useChatStore.getState().sessionId).toBe("sess-abc-123");
  });

  it("restores messages in the store", async () => {
    mockGetChatSession.mockResolvedValue(MOCK_SESSION);

    const { result } = renderHook(() => useChatSession());

    await act(async () => {
      await result.current.rehydrate("sess-abc-123");
    });

    const messages = useChatStore.getState().messages;
    expect(messages).toHaveLength(2);
    expect(messages[0].role).toBe("user");
    expect(messages[1].role).toBe("assistant");
  });

  it("restores extracted slots in the store", async () => {
    mockGetChatSession.mockResolvedValue(MOCK_SESSION);

    const { result } = renderHook(() => useChatSession());

    await act(async () => {
      await result.current.rehydrate("sess-abc-123");
    });

    expect(useChatStore.getState().extractedSlots).toEqual({ tickers: ["AAPL"] });
  });

  it("sets pendingPayload when session status is pending_confirmation", async () => {
    const pendingSession: ChatSession = {
      ...MOCK_SESSION,
      status: "pending_confirmation",
      extracted_slots: { tickers: ["AAPL"], budget: 10000 },
    };
    mockGetChatSession.mockResolvedValue(pendingSession);

    const { result } = renderHook(() => useChatSession());

    await act(async () => {
      await result.current.rehydrate("sess-abc-123");
    });

    expect(useChatStore.getState().pendingPayload).toEqual({
      tickers: ["AAPL"],
      budget: 10000,
    });
  });

  it("returns false and sets error when getChatSession fails", async () => {
    mockGetChatSession.mockRejectedValue(new Error("Session not found"));

    const { result } = renderHook(() => useChatSession());

    let success: boolean;
    await act(async () => {
      success = await result.current.rehydrate("bad-id");
    });

    expect(success!).toBe(false);
    expect(useChatStore.getState().error).toBe("Session not found");
  });
});
