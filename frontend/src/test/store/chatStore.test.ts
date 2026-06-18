/**
 * Tests for @/store/chatStore
 *
 * The chatStore is a Zustand slice that manages all chat assistant UI state.
 * These tests exercise every action and derived selector to ensure the store
 * behaves correctly in isolation (no React rendering needed).
 *
 * Covers:
 *   - Initial state shape
 *   - Panel visibility: openPanel / closePanel / togglePanel
 *   - Session lifecycle: setSessionId (resets conversation state)
 *   - setSessionStatus
 *   - Message management: appendMessage / setMessages
 *   - Slot management: mergeExtractedSlots / setExtractedSlots
 *   - Payload preview: setPendingPayload
 *   - Loading flags: setIsSending / setIsConfirming
 *   - Error handling: setError
 *   - Confirmation: setConfirmedRunId (also updates status + clears payload)
 *   - applyAssistantReply (atomic convenience action)
 *   - resetSession (full reset, panel stays open)
 *   - Selector helpers: selectCanSendMessage / selectShowConfirmCard
 */

import { describe, it, expect, beforeEach } from "vitest";
import {
  useChatStore,
  selectIsPanelOpen,
  selectSessionId,
  selectMessages,
  selectExtractedSlots,
  selectSessionStatus,
  selectPendingPayload,
  selectIsSending,
  selectIsConfirming,
  selectError,
  selectConfirmedRunId,
  selectCanSendMessage,
  selectShowConfirmCard,
} from "@/store/chatStore";
import type { ChatMessage, ExtractedSlots } from "@/types/api";

// ── Helpers ────────────────────────────────────────────────────────────────

function getState() {
  return useChatStore.getState();
}

function makeMessage(
  role: "user" | "assistant",
  content: string,
  timestamp?: string,
): ChatMessage {
  return { role, content, timestamp };
}

// ── Reset store before each test ───────────────────────────────────────────

beforeEach(() => {
  useChatStore.getState().resetSession();
  useChatStore.setState({ isPanelOpen: false });
});

// ── Initial state ──────────────────────────────────────────────────────────

describe("initial state", () => {
  it("isPanelOpen is false", () => {
    expect(getState().isPanelOpen).toBe(false);
  });

  it("sessionId is null", () => {
    expect(getState().sessionId).toBeNull();
  });

  it("messages is an empty array", () => {
    expect(getState().messages).toEqual([]);
  });

  it("extractedSlots is an empty object", () => {
    expect(getState().extractedSlots).toEqual({});
  });

  it("sessionStatus is null", () => {
    expect(getState().sessionStatus).toBeNull();
  });

  it("pendingPayload is null", () => {
    expect(getState().pendingPayload).toBeNull();
  });

  it("isSending is false", () => {
    expect(getState().isSending).toBe(false);
  });

  it("isConfirming is false", () => {
    expect(getState().isConfirming).toBe(false);
  });

  it("error is null", () => {
    expect(getState().error).toBeNull();
  });

  it("confirmedRunId is null", () => {
    expect(getState().confirmedRunId).toBeNull();
  });
});

// ── Panel visibility ───────────────────────────────────────────────────────

describe("panel visibility", () => {
  it("openPanel sets isPanelOpen to true", () => {
    getState().openPanel();
    expect(getState().isPanelOpen).toBe(true);
  });

  it("closePanel sets isPanelOpen to false", () => {
    getState().openPanel();
    getState().closePanel();
    expect(getState().isPanelOpen).toBe(false);
  });

  it("togglePanel flips isPanelOpen from false to true", () => {
    expect(getState().isPanelOpen).toBe(false);
    getState().togglePanel();
    expect(getState().isPanelOpen).toBe(true);
  });

  it("togglePanel flips isPanelOpen from true to false", () => {
    getState().openPanel();
    getState().togglePanel();
    expect(getState().isPanelOpen).toBe(false);
  });

  it("calling openPanel twice keeps isPanelOpen true", () => {
    getState().openPanel();
    getState().openPanel();
    expect(getState().isPanelOpen).toBe(true);
  });
});

// ── Session lifecycle ──────────────────────────────────────────────────────

describe("setSessionId", () => {
  it("sets the sessionId", () => {
    getState().setSessionId("session-abc");
    expect(getState().sessionId).toBe("session-abc");
  });

  it("resets messages to empty array", () => {
    getState().appendMessage(makeMessage("user", "hello"));
    getState().setSessionId("session-new");
    expect(getState().messages).toEqual([]);
  });

  it("resets extractedSlots to empty object", () => {
    getState().setExtractedSlots({ tickers: ["AAPL"] });
    getState().setSessionId("session-new");
    expect(getState().extractedSlots).toEqual({});
  });

  it("sets sessionStatus to 'collecting'", () => {
    getState().setSessionId("session-new");
    expect(getState().sessionStatus).toBe("collecting");
  });

  it("clears pendingPayload", () => {
    getState().setPendingPayload({ tickers: ["AAPL"], budget: 10000 });
    getState().setSessionId("session-new");
    expect(getState().pendingPayload).toBeNull();
  });

  it("clears isSending flag", () => {
    getState().setIsSending(true);
    getState().setSessionId("session-new");
    expect(getState().isSending).toBe(false);
  });

  it("clears isConfirming flag", () => {
    getState().setIsConfirming(true);
    getState().setSessionId("session-new");
    expect(getState().isConfirming).toBe(false);
  });

  it("clears error", () => {
    getState().setError("some error");
    getState().setSessionId("session-new");
    expect(getState().error).toBeNull();
  });

  it("clears confirmedRunId", () => {
    // Manually set confirmedRunId via setState
    useChatStore.setState({ confirmedRunId: "run-old" });
    getState().setSessionId("session-new");
    expect(getState().confirmedRunId).toBeNull();
  });
});

describe("setSessionStatus", () => {
  it("updates sessionStatus to 'active'", () => {
    getState().setSessionStatus("active");
    expect(getState().sessionStatus).toBe("active");
  });

  it("updates sessionStatus to 'pending_confirmation'", () => {
    getState().setSessionStatus("pending_confirmation");
    expect(getState().sessionStatus).toBe("pending_confirmation");
  });

  it("updates sessionStatus to 'confirmed'", () => {
    getState().setSessionStatus("confirmed");
    expect(getState().sessionStatus).toBe("confirmed");
  });

  it("updates sessionStatus to 'abandoned'", () => {
    getState().setSessionStatus("abandoned");
    expect(getState().sessionStatus).toBe("abandoned");
  });
});

// ── Message management ─────────────────────────────────────────────────────

describe("appendMessage", () => {
  it("appends a user message to an empty list", () => {
    const msg = makeMessage("user", "Hello");
    getState().appendMessage(msg);
    expect(getState().messages).toHaveLength(1);
    expect(getState().messages[0]).toEqual(msg);
  });

  it("appends an assistant message after a user message", () => {
    getState().appendMessage(makeMessage("user", "Hello"));
    getState().appendMessage(makeMessage("assistant", "Hi there!"));
    expect(getState().messages).toHaveLength(2);
    expect(getState().messages[1].role).toBe("assistant");
    expect(getState().messages[1].content).toBe("Hi there!");
  });

  it("preserves existing messages when appending", () => {
    getState().appendMessage(makeMessage("user", "msg1"));
    getState().appendMessage(makeMessage("user", "msg2"));
    getState().appendMessage(makeMessage("assistant", "reply"));
    expect(getState().messages).toHaveLength(3);
  });

  it("preserves the timestamp field", () => {
    const ts = "2024-01-01T00:00:00.000Z";
    getState().appendMessage(makeMessage("user", "Hello", ts));
    expect(getState().messages[0].timestamp).toBe(ts);
  });
});

describe("setMessages", () => {
  it("replaces the entire messages array", () => {
    getState().appendMessage(makeMessage("user", "old"));
    const newMessages: ChatMessage[] = [
      makeMessage("user", "new1"),
      makeMessage("assistant", "new2"),
    ];
    getState().setMessages(newMessages);
    expect(getState().messages).toHaveLength(2);
    expect(getState().messages[0].content).toBe("new1");
    expect(getState().messages[1].content).toBe("new2");
  });

  it("can set messages to an empty array", () => {
    getState().appendMessage(makeMessage("user", "hello"));
    getState().setMessages([]);
    expect(getState().messages).toEqual([]);
  });
});

// ── Slot management ────────────────────────────────────────────────────────

describe("mergeExtractedSlots", () => {
  it("merges new slots into an empty object", () => {
    getState().mergeExtractedSlots({ tickers: ["AAPL", "MSFT"] });
    expect(getState().extractedSlots.tickers).toEqual(["AAPL", "MSFT"]);
  });

  it("merges new slots without overwriting existing ones", () => {
    getState().setExtractedSlots({ tickers: ["AAPL"], budget: 10000 });
    getState().mergeExtractedSlots({ min_return: 0.08 });
    const slots = getState().extractedSlots;
    expect(slots.tickers).toEqual(["AAPL"]);
    expect(slots.budget).toBe(10000);
    expect(slots.min_return).toBe(0.08);
  });

  it("overwrites existing slot values with non-null incoming values", () => {
    getState().setExtractedSlots({ tickers: ["AAPL"], budget: 5000 });
    getState().mergeExtractedSlots({ budget: 20000 });
    expect(getState().extractedSlots.budget).toBe(20000);
  });

  it("does NOT overwrite existing values with null", () => {
    getState().setExtractedSlots({ tickers: ["AAPL"], budget: 10000 });
    // Passing null for budget should preserve the existing value
    getState().mergeExtractedSlots({ budget: null as unknown as number });
    expect(getState().extractedSlots.budget).toBe(10000);
  });

  it("does NOT overwrite existing values with undefined", () => {
    getState().setExtractedSlots({ tickers: ["AAPL"], budget: 10000 });
    getState().mergeExtractedSlots({ budget: undefined });
    expect(getState().extractedSlots.budget).toBe(10000);
  });
});

describe("setExtractedSlots", () => {
  it("replaces the entire extractedSlots object", () => {
    getState().setExtractedSlots({ tickers: ["AAPL"] });
    getState().setExtractedSlots({ budget: 50000 });
    expect(getState().extractedSlots).toEqual({ budget: 50000 });
    expect(getState().extractedSlots.tickers).toBeUndefined();
  });
});

// ── Payload preview ────────────────────────────────────────────────────────

describe("setPendingPayload", () => {
  it("sets a non-null payload", () => {
    const payload: ExtractedSlots = { tickers: ["AAPL"], budget: 10000 };
    getState().setPendingPayload(payload);
    expect(getState().pendingPayload).toEqual(payload);
  });

  it("clears the payload when passed null", () => {
    getState().setPendingPayload({ tickers: ["AAPL"], budget: 10000 });
    getState().setPendingPayload(null);
    expect(getState().pendingPayload).toBeNull();
  });
});

// ── Loading flags ──────────────────────────────────────────────────────────

describe("setIsSending", () => {
  it("sets isSending to true", () => {
    getState().setIsSending(true);
    expect(getState().isSending).toBe(true);
  });

  it("sets isSending to false", () => {
    getState().setIsSending(true);
    getState().setIsSending(false);
    expect(getState().isSending).toBe(false);
  });
});

describe("setIsConfirming", () => {
  it("sets isConfirming to true", () => {
    getState().setIsConfirming(true);
    expect(getState().isConfirming).toBe(true);
  });

  it("sets isConfirming to false", () => {
    getState().setIsConfirming(true);
    getState().setIsConfirming(false);
    expect(getState().isConfirming).toBe(false);
  });
});

// ── Error handling ─────────────────────────────────────────────────────────

describe("setError", () => {
  it("sets an error message", () => {
    getState().setError("Something went wrong");
    expect(getState().error).toBe("Something went wrong");
  });

  it("clears the error when passed null", () => {
    getState().setError("error");
    getState().setError(null);
    expect(getState().error).toBeNull();
  });
});

// ── Confirmation ───────────────────────────────────────────────────────────

describe("setConfirmedRunId", () => {
  it("sets the confirmedRunId", () => {
    getState().setConfirmedRunId("run-xyz-123");
    expect(getState().confirmedRunId).toBe("run-xyz-123");
  });

  it("updates sessionStatus to 'confirmed'", () => {
    getState().setSessionStatus("pending_confirmation");
    getState().setConfirmedRunId("run-xyz-123");
    expect(getState().sessionStatus).toBe("confirmed");
  });

  it("clears pendingPayload", () => {
    getState().setPendingPayload({ tickers: ["AAPL"], budget: 10000 });
    getState().setConfirmedRunId("run-xyz-123");
    expect(getState().pendingPayload).toBeNull();
  });
});

// ── applyAssistantReply ────────────────────────────────────────────────────

describe("applyAssistantReply", () => {
  it("appends the assistant message to the thread", () => {
    getState().applyAssistantReply({
      content: "Here is your portfolio!",
      extractedSlots: null,
      payloadPreview: null,
      status: "active",
    });
    const msgs = getState().messages;
    expect(msgs).toHaveLength(1);
    expect(msgs[0].role).toBe("assistant");
    expect(msgs[0].content).toBe("Here is your portfolio!");
  });

  it("merges extractedSlots when provided", () => {
    getState().setExtractedSlots({ tickers: ["AAPL"] });
    getState().applyAssistantReply({
      content: "Got it!",
      extractedSlots: { budget: 50000 },
      payloadPreview: null,
      status: "active",
    });
    expect(getState().extractedSlots.tickers).toEqual(["AAPL"]);
    expect(getState().extractedSlots.budget).toBe(50000);
  });

  it("sets pendingPayload when payloadPreview is provided", () => {
    const preview: ExtractedSlots = { tickers: ["AAPL"], budget: 10000 };
    getState().applyAssistantReply({
      content: "Ready!",
      extractedSlots: preview,
      payloadPreview: preview,
      status: "pending_confirmation",
    });
    expect(getState().pendingPayload).toEqual(preview);
  });

  it("sets pendingPayload to null when payloadPreview is null", () => {
    getState().setPendingPayload({ tickers: ["AAPL"], budget: 10000 });
    getState().applyAssistantReply({
      content: "Still gathering info...",
      extractedSlots: null,
      payloadPreview: null,
      status: "active",
    });
    expect(getState().pendingPayload).toBeNull();
  });

  it("updates sessionStatus", () => {
    getState().applyAssistantReply({
      content: "Ready!",
      extractedSlots: null,
      payloadPreview: null,
      status: "pending_confirmation",
    });
    expect(getState().sessionStatus).toBe("pending_confirmation");
  });

  it("clears isSending flag", () => {
    getState().setIsSending(true);
    getState().applyAssistantReply({
      content: "Done",
      extractedSlots: null,
      payloadPreview: null,
      status: "active",
    });
    expect(getState().isSending).toBe(false);
  });

  it("clears any previous error", () => {
    getState().setError("previous error");
    getState().applyAssistantReply({
      content: "Done",
      extractedSlots: null,
      payloadPreview: null,
      status: "active",
    });
    expect(getState().error).toBeNull();
  });

  it("preserves the timestamp when provided", () => {
    const ts = "2024-06-01T12:00:00.000Z";
    getState().applyAssistantReply({
      content: "Hello",
      extractedSlots: null,
      payloadPreview: null,
      status: "active",
      timestamp: ts,
    });
    expect(getState().messages[0].timestamp).toBe(ts);
  });
});

// ── resetSession ───────────────────────────────────────────────────────────

describe("resetSession", () => {
  it("clears sessionId", () => {
    getState().setSessionId("session-abc");
    getState().resetSession();
    expect(getState().sessionId).toBeNull();
  });

  it("clears messages", () => {
    getState().appendMessage(makeMessage("user", "hello"));
    getState().resetSession();
    expect(getState().messages).toEqual([]);
  });

  it("clears extractedSlots", () => {
    getState().setExtractedSlots({ tickers: ["AAPL"] });
    getState().resetSession();
    expect(getState().extractedSlots).toEqual({});
  });

  it("sets sessionStatus to null", () => {
    getState().setSessionStatus("active");
    getState().resetSession();
    expect(getState().sessionStatus).toBeNull();
  });

  it("clears pendingPayload", () => {
    getState().setPendingPayload({ tickers: ["AAPL"], budget: 10000 });
    getState().resetSession();
    expect(getState().pendingPayload).toBeNull();
  });

  it("clears isSending", () => {
    getState().setIsSending(true);
    getState().resetSession();
    expect(getState().isSending).toBe(false);
  });

  it("clears isConfirming", () => {
    getState().setIsConfirming(true);
    getState().resetSession();
    expect(getState().isConfirming).toBe(false);
  });

  it("clears error", () => {
    getState().setError("some error");
    getState().resetSession();
    expect(getState().error).toBeNull();
  });

  it("clears confirmedRunId", () => {
    useChatStore.setState({ confirmedRunId: "run-old" });
    getState().resetSession();
    expect(getState().confirmedRunId).toBeNull();
  });

  it("does NOT change isPanelOpen (panel stays open)", () => {
    getState().openPanel();
    getState().resetSession();
    expect(getState().isPanelOpen).toBe(true);
  });
});

// ── Selector helpers ───────────────────────────────────────────────────────

describe("selector helpers", () => {
  it("selectIsPanelOpen returns isPanelOpen", () => {
    getState().openPanel();
    expect(selectIsPanelOpen(getState())).toBe(true);
  });

  it("selectSessionId returns sessionId", () => {
    getState().setSessionId("s-123");
    expect(selectSessionId(getState())).toBe("s-123");
  });

  it("selectMessages returns messages array", () => {
    getState().appendMessage(makeMessage("user", "hi"));
    expect(selectMessages(getState())).toHaveLength(1);
  });

  it("selectExtractedSlots returns extractedSlots", () => {
    getState().setExtractedSlots({ budget: 5000 });
    expect(selectExtractedSlots(getState()).budget).toBe(5000);
  });

  it("selectSessionStatus returns sessionStatus", () => {
    getState().setSessionStatus("active");
    expect(selectSessionStatus(getState())).toBe("active");
  });

  it("selectPendingPayload returns pendingPayload", () => {
    const p: ExtractedSlots = { tickers: ["AAPL"], budget: 10000 };
    getState().setPendingPayload(p);
    expect(selectPendingPayload(getState())).toEqual(p);
  });

  it("selectIsSending returns isSending", () => {
    getState().setIsSending(true);
    expect(selectIsSending(getState())).toBe(true);
  });

  it("selectIsConfirming returns isConfirming", () => {
    getState().setIsConfirming(true);
    expect(selectIsConfirming(getState())).toBe(true);
  });

  it("selectError returns error", () => {
    getState().setError("oops");
    expect(selectError(getState())).toBe("oops");
  });

  it("selectConfirmedRunId returns confirmedRunId", () => {
    getState().setConfirmedRunId("run-abc");
    expect(selectConfirmedRunId(getState())).toBe("run-abc");
  });
});

// ── selectCanSendMessage ───────────────────────────────────────────────────

describe("selectCanSendMessage", () => {
  it("returns false when sessionId is null", () => {
    expect(selectCanSendMessage(getState())).toBe(false);
  });

  it("returns true when session is active and not sending", () => {
    getState().setSessionId("s-1");
    // setSessionId sets status to 'active'
    expect(selectCanSendMessage(getState())).toBe(true);
  });

  it("returns false when isSending is true", () => {
    getState().setSessionId("s-1");
    getState().setIsSending(true);
    expect(selectCanSendMessage(getState())).toBe(false);
  });

  it("returns false when sessionStatus is 'confirmed'", () => {
    getState().setSessionId("s-1");
    getState().setSessionStatus("confirmed");
    expect(selectCanSendMessage(getState())).toBe(false);
  });

  it("returns false when sessionStatus is 'abandoned'", () => {
    getState().setSessionId("s-1");
    getState().setSessionStatus("abandoned");
    expect(selectCanSendMessage(getState())).toBe(false);
  });

  it("returns true when status is 'pending_confirmation' (user can still type)", () => {
    getState().setSessionId("s-1");
    getState().setSessionStatus("pending_confirmation");
    expect(selectCanSendMessage(getState())).toBe(true);
  });
});

// ── selectShowConfirmCard ──────────────────────────────────────────────────

describe("selectShowConfirmCard", () => {
  it("returns false when sessionStatus is not pending_confirmation", () => {
    getState().setSessionId("s-1");
    getState().setPendingPayload({ tickers: ["AAPL"], budget: 10000 });
    // status is 'active' after setSessionId
    expect(selectShowConfirmCard(getState())).toBe(false);
  });

  it("returns false when pendingPayload is null even if status is pending_confirmation", () => {
    getState().setSessionStatus("pending_confirmation");
    expect(selectShowConfirmCard(getState())).toBe(false);
  });

  it("returns true when status is pending_confirmation AND pendingPayload is non-null", () => {
    getState().setSessionStatus("pending_confirmation");
    getState().setPendingPayload({ tickers: ["AAPL"], budget: 10000 });
    expect(selectShowConfirmCard(getState())).toBe(true);
  });
});
