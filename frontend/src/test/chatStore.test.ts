/**
 * Tests for @/store/chatStore
 *
 * Comprehensive unit tests for the chatStore Zustand slice.
 * Exercises every action, selector, and derived state in isolation —
 * no React rendering required.
 *
 * Covers:
 *   - Initial state shape (all fields at their zero values)
 *   - Panel visibility: openPanel / closePanel / togglePanel
 *   - Session lifecycle: setSessionId (resets conversation state)
 *   - setSessionStatus for all four status values
 *   - Message management: appendMessage / setMessages
 *   - Slot management: mergeExtractedSlots / setExtractedSlots
 *   - Payload preview: setPendingPayload
 *   - Loading flags: setIsSending / setIsConfirming
 *   - Error handling: setError
 *   - Confirmation: setConfirmedRunId (also updates status + clears payload)
 *   - applyAssistantReply (atomic convenience action)
 *   - resetSession (full reset, panel stays open)
 *   - Selector helpers: all exported selectors
 *   - selectCanSendMessage derived logic
 *   - selectShowConfirmCard derived logic
 *   - Multi-turn slot accumulation across several applyAssistantReply calls
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

/** Shorthand to get the current store state. */
function getState() {
  return useChatStore.getState();
}

/** Build a ChatMessage fixture. */
function makeMsg(
  role: "user" | "assistant",
  content: string,
  timestamp?: string,
): ChatMessage {
  return { role, content, timestamp };
}

// ── Reset store before each test ───────────────────────────────────────────

beforeEach(() => {
  // resetSession does not touch isPanelOpen, so we reset it explicitly.
  useChatStore.getState().resetSession();
  useChatStore.setState({ isPanelOpen: false });
});

// ══════════════════════════════════════════════════════════════════════════
// Initial state
// ══════════════════════════════════════════════════════════════════════════

describe("initial state", () => {
  it("isPanelOpen starts as false", () => {
    expect(getState().isPanelOpen).toBe(false);
  });

  it("sessionId starts as null", () => {
    expect(getState().sessionId).toBeNull();
  });

  it("messages starts as an empty array", () => {
    expect(getState().messages).toEqual([]);
  });

  it("extractedSlots starts as an empty object", () => {
    expect(getState().extractedSlots).toEqual({});
  });

  it("sessionStatus starts as null", () => {
    expect(getState().sessionStatus).toBeNull();
  });

  it("pendingPayload starts as null", () => {
    expect(getState().pendingPayload).toBeNull();
  });

  it("isSending starts as false", () => {
    expect(getState().isSending).toBe(false);
  });

  it("isConfirming starts as false", () => {
    expect(getState().isConfirming).toBe(false);
  });

  it("error starts as null", () => {
    expect(getState().error).toBeNull();
  });

  it("confirmedRunId starts as null", () => {
    expect(getState().confirmedRunId).toBeNull();
  });
});

// ══════════════════════════════════════════════════════════════════════════
// Panel visibility
// ══════════════════════════════════════════════════════════════════════════

describe("openPanel", () => {
  it("sets isPanelOpen to true", () => {
    getState().openPanel();
    expect(getState().isPanelOpen).toBe(true);
  });

  it("is idempotent — calling twice keeps isPanelOpen true", () => {
    getState().openPanel();
    getState().openPanel();
    expect(getState().isPanelOpen).toBe(true);
  });
});

describe("closePanel", () => {
  it("sets isPanelOpen to false", () => {
    getState().openPanel();
    getState().closePanel();
    expect(getState().isPanelOpen).toBe(false);
  });

  it("is idempotent — calling twice keeps isPanelOpen false", () => {
    getState().closePanel();
    getState().closePanel();
    expect(getState().isPanelOpen).toBe(false);
  });
});

describe("togglePanel", () => {
  it("flips isPanelOpen from false to true", () => {
    expect(getState().isPanelOpen).toBe(false);
    getState().togglePanel();
    expect(getState().isPanelOpen).toBe(true);
  });

  it("flips isPanelOpen from true to false", () => {
    getState().openPanel();
    getState().togglePanel();
    expect(getState().isPanelOpen).toBe(false);
  });

  it("two toggles return to the original state", () => {
    getState().togglePanel();
    getState().togglePanel();
    expect(getState().isPanelOpen).toBe(false);
  });
});

// ══════════════════════════════════════════════════════════════════════════
// Session lifecycle
// ══════════════════════════════════════════════════════════════════════════

describe("setSessionId", () => {
  it("stores the provided session ID", () => {
    getState().setSessionId("sess-001");
    expect(getState().sessionId).toBe("sess-001");
  });

  it("replaces a previous session ID", () => {
    getState().setSessionId("sess-001");
    getState().setSessionId("sess-002");
    expect(getState().sessionId).toBe("sess-002");
  });

  it("resets messages to an empty array", () => {
    getState().appendMessage(makeMsg("user", "hello"));
    getState().setSessionId("sess-new");
    expect(getState().messages).toEqual([]);
  });

  it("resets extractedSlots to an empty object", () => {
    getState().setExtractedSlots({ tickers: ["AAPL"], budget: 5000 });
    getState().setSessionId("sess-new");
    expect(getState().extractedSlots).toEqual({});
  });

  it("sets sessionStatus to 'collecting'", () => {
    getState().setSessionId("sess-new");
    expect(getState().sessionStatus).toBe("collecting");
  });

  it("clears pendingPayload", () => {
    getState().setPendingPayload({ tickers: ["AAPL"], budget: 10000 });
    getState().setSessionId("sess-new");
    expect(getState().pendingPayload).toBeNull();
  });

  it("clears isSending", () => {
    getState().setIsSending(true);
    getState().setSessionId("sess-new");
    expect(getState().isSending).toBe(false);
  });

  it("clears isConfirming", () => {
    getState().setIsConfirming(true);
    getState().setSessionId("sess-new");
    expect(getState().isConfirming).toBe(false);
  });

  it("clears error", () => {
    getState().setError("previous error");
    getState().setSessionId("sess-new");
    expect(getState().error).toBeNull();
  });

  it("clears confirmedRunId", () => {
    useChatStore.setState({ confirmedRunId: "run-old" });
    getState().setSessionId("sess-new");
    expect(getState().confirmedRunId).toBeNull();
  });
});

describe("setSessionStatus", () => {
  it("sets status to 'active'", () => {
    getState().setSessionStatus("active");
    expect(getState().sessionStatus).toBe("active");
  });

  it("sets status to 'pending_confirmation'", () => {
    getState().setSessionStatus("pending_confirmation");
    expect(getState().sessionStatus).toBe("pending_confirmation");
  });

  it("sets status to 'confirmed'", () => {
    getState().setSessionStatus("confirmed");
    expect(getState().sessionStatus).toBe("confirmed");
  });

  it("sets status to 'abandoned'", () => {
    getState().setSessionStatus("abandoned");
    expect(getState().sessionStatus).toBe("abandoned");
  });

  it("does not affect other state fields", () => {
    getState().appendMessage(makeMsg("user", "hi"));
    getState().setSessionStatus("active");
    expect(getState().messages).toHaveLength(1);
  });
});

// ══════════════════════════════════════════════════════════════════════════
// Message management
// ══════════════════════════════════════════════════════════════════════════

describe("appendMessage", () => {
  it("appends a user message to an empty list", () => {
    const msg = makeMsg("user", "Hello");
    getState().appendMessage(msg);
    expect(getState().messages).toHaveLength(1);
    expect(getState().messages[0]).toEqual(msg);
  });

  it("appends an assistant message after a user message", () => {
    getState().appendMessage(makeMsg("user", "Hello"));
    getState().appendMessage(makeMsg("assistant", "Hi there!"));
    expect(getState().messages).toHaveLength(2);
    expect(getState().messages[1].role).toBe("assistant");
    expect(getState().messages[1].content).toBe("Hi there!");
  });

  it("preserves all existing messages when appending", () => {
    getState().appendMessage(makeMsg("user", "msg1"));
    getState().appendMessage(makeMsg("assistant", "reply1"));
    getState().appendMessage(makeMsg("user", "msg2"));
    expect(getState().messages).toHaveLength(3);
    expect(getState().messages[0].content).toBe("msg1");
    expect(getState().messages[1].content).toBe("reply1");
    expect(getState().messages[2].content).toBe("msg2");
  });

  it("preserves the timestamp field", () => {
    const ts = "2024-06-01T12:00:00.000Z";
    getState().appendMessage(makeMsg("user", "Hello", ts));
    expect(getState().messages[0].timestamp).toBe(ts);
  });

  it("preserves messages without a timestamp", () => {
    getState().appendMessage(makeMsg("user", "No timestamp"));
    expect(getState().messages[0].timestamp).toBeUndefined();
  });
});

describe("setMessages", () => {
  it("replaces the entire messages array", () => {
    getState().appendMessage(makeMsg("user", "old"));
    const newMessages: ChatMessage[] = [
      makeMsg("user", "new1"),
      makeMsg("assistant", "new2"),
    ];
    getState().setMessages(newMessages);
    expect(getState().messages).toHaveLength(2);
    expect(getState().messages[0].content).toBe("new1");
    expect(getState().messages[1].content).toBe("new2");
  });

  it("can set messages to an empty array", () => {
    getState().appendMessage(makeMsg("user", "hello"));
    getState().setMessages([]);
    expect(getState().messages).toEqual([]);
  });

  it("does not affect other state fields", () => {
    getState().setError("some error");
    getState().setMessages([makeMsg("user", "hi")]);
    expect(getState().error).toBe("some error");
  });
});

// ══════════════════════════════════════════════════════════════════════════
// Slot management
// ══════════════════════════════════════════════════════════════════════════

describe("mergeExtractedSlots", () => {
  it("merges new slots into an empty object", () => {
    getState().mergeExtractedSlots({ tickers: ["AAPL", "MSFT"] });
    expect(getState().extractedSlots.tickers).toEqual(["AAPL", "MSFT"]);
  });

  it("adds new keys without overwriting existing ones", () => {
    getState().setExtractedSlots({ tickers: ["AAPL"], budget: 10000 });
    getState().mergeExtractedSlots({ min_return: 0.08 });
    const slots = getState().extractedSlots;
    expect(slots.tickers).toEqual(["AAPL"]);
    expect(slots.budget).toBe(10000);
    expect(slots.min_return).toBe(0.08);
  });

  it("overwrites an existing key with a new non-null value", () => {
    getState().setExtractedSlots({ budget: 5000 });
    getState().mergeExtractedSlots({ budget: 20000 });
    expect(getState().extractedSlots.budget).toBe(20000);
  });

  it("does NOT overwrite an existing value with null", () => {
    getState().setExtractedSlots({ budget: 10000 });
    getState().mergeExtractedSlots({ budget: null as unknown as number });
    expect(getState().extractedSlots.budget).toBe(10000);
  });

  it("does NOT overwrite an existing value with undefined", () => {
    getState().setExtractedSlots({ budget: 10000 });
    getState().mergeExtractedSlots({ budget: undefined });
    expect(getState().extractedSlots.budget).toBe(10000);
  });

  it("accumulates slots across multiple calls (multi-turn scenario)", () => {
    getState().mergeExtractedSlots({ tickers: ["AAPL"] });
    getState().mergeExtractedSlots({ budget: 50000 });
    getState().mergeExtractedSlots({ min_return: 0.1 });
    const slots = getState().extractedSlots;
    expect(slots.tickers).toEqual(["AAPL"]);
    expect(slots.budget).toBe(50000);
    expect(slots.min_return).toBe(0.1);
  });
});

describe("setExtractedSlots", () => {
  it("replaces the entire extractedSlots object", () => {
    getState().setExtractedSlots({ tickers: ["AAPL"], budget: 5000 });
    getState().setExtractedSlots({ budget: 99000 });
    // tickers should be gone — it was replaced, not merged
    expect(getState().extractedSlots.tickers).toBeUndefined();
    expect(getState().extractedSlots.budget).toBe(99000);
  });

  it("can set extractedSlots to an empty object", () => {
    getState().setExtractedSlots({ tickers: ["AAPL"] });
    getState().setExtractedSlots({});
    expect(getState().extractedSlots).toEqual({});
  });
});

// ══════════════════════════════════════════════════════════════════════════
// Payload preview
// ══════════════════════════════════════════════════════════════════════════

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

  it("replaces a previous payload with a new one", () => {
    getState().setPendingPayload({ tickers: ["AAPL"], budget: 5000 });
    getState().setPendingPayload({ tickers: ["MSFT"], budget: 20000 });
    expect(getState().pendingPayload?.tickers).toEqual(["MSFT"]);
    expect(getState().pendingPayload?.budget).toBe(20000);
  });
});

// ══════════════════════════════════════════════════════════════════════════
// Loading flags
// ══════════════════════════════════════════════════════════════════════════

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

  it("does not affect isConfirming", () => {
    getState().setIsConfirming(true);
    getState().setIsSending(true);
    expect(getState().isConfirming).toBe(true);
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

  it("does not affect isSending", () => {
    getState().setIsSending(true);
    getState().setIsConfirming(true);
    expect(getState().isSending).toBe(true);
  });
});

// ══════════════════════════════════════════════════════════════════════════
// Error handling
// ══════════════════════════════════════════════════════════════════════════

describe("setError", () => {
  it("sets an error message string", () => {
    getState().setError("Something went wrong");
    expect(getState().error).toBe("Something went wrong");
  });

  it("clears the error when passed null", () => {
    getState().setError("error");
    getState().setError(null);
    expect(getState().error).toBeNull();
  });

  it("replaces a previous error with a new one", () => {
    getState().setError("first error");
    getState().setError("second error");
    expect(getState().error).toBe("second error");
  });
});

// ══════════════════════════════════════════════════════════════════════════
// Confirmation
// ══════════════════════════════════════════════════════════════════════════

describe("setConfirmedRunId", () => {
  it("stores the run ID", () => {
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

  it("clears isConfirming", () => {
    getState().setIsConfirming(true);
    getState().setConfirmedRunId("run-xyz-123");
    expect(getState().isConfirming).toBe(false);
  });

  it("does not clear messages", () => {
    getState().appendMessage(makeMsg("user", "hello"));
    getState().setConfirmedRunId("run-xyz-123");
    expect(getState().messages).toHaveLength(1);
  });
});

// ══════════════════════════════════════════════════════════════════════════
// applyAssistantReply (atomic convenience action)
// ══════════════════════════════════════════════════════════════════════════

describe("applyAssistantReply", () => {
  it("appends an assistant message to the thread", () => {
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

  it("appends after existing user messages", () => {
    getState().appendMessage(makeMsg("user", "Build me a portfolio"));
    getState().applyAssistantReply({
      content: "What tickers?",
      extractedSlots: null,
      payloadPreview: null,
      status: "active",
    });
    expect(getState().messages).toHaveLength(2);
    expect(getState().messages[1].content).toBe("What tickers?");
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

  it("does not overwrite existing slots with null values in extractedSlots", () => {
    getState().setExtractedSlots({ tickers: ["AAPL"], budget: 10000 });
    getState().applyAssistantReply({
      content: "Updated",
      extractedSlots: { budget: null as unknown as number },
      payloadPreview: null,
      status: "active",
    });
    expect(getState().extractedSlots.budget).toBe(10000);
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

  it("updates sessionStatus to the provided value", () => {
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

  it("omits timestamp when not provided", () => {
    getState().applyAssistantReply({
      content: "Hello",
      extractedSlots: null,
      payloadPreview: null,
      status: "active",
    });
    // timestamp should be absent (not set to undefined explicitly)
    expect(getState().messages[0].timestamp).toBeUndefined();
  });

  it("accumulates slots across multiple calls (multi-turn slot filling)", () => {
    // Turn 1: user says tickers
    getState().applyAssistantReply({
      content: "What budget?",
      extractedSlots: { tickers: ["AAPL", "MSFT"] },
      payloadPreview: null,
      status: "active",
    });
    // Turn 2: user says budget
    getState().applyAssistantReply({
      content: "What return target?",
      extractedSlots: { budget: 50000 },
      payloadPreview: null,
      status: "active",
    });
    // Turn 3: user says min return — now all slots filled
    const preview: ExtractedSlots = {
      tickers: ["AAPL", "MSFT"],
      budget: 50000,
      min_return: 0.1,
    };
    getState().applyAssistantReply({
      content: "Ready to confirm!",
      extractedSlots: { min_return: 0.1 },
      payloadPreview: preview,
      status: "pending_confirmation",
    });

    const slots = getState().extractedSlots;
    expect(slots.tickers).toEqual(["AAPL", "MSFT"]);
    expect(slots.budget).toBe(50000);
    expect(slots.min_return).toBe(0.1);
    expect(getState().sessionStatus).toBe("pending_confirmation");
    expect(getState().pendingPayload).toEqual(preview);
    expect(getState().messages).toHaveLength(3);
  });
});

// ══════════════════════════════════════════════════════════════════════════
// resetSession
// ══════════════════════════════════════════════════════════════════════════

describe("resetSession", () => {
  it("clears sessionId", () => {
    getState().setSessionId("session-abc");
    getState().resetSession();
    expect(getState().sessionId).toBeNull();
  });

  it("clears messages", () => {
    getState().appendMessage(makeMsg("user", "hello"));
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

  it("does NOT change isPanelOpen — panel stays open after reset", () => {
    getState().openPanel();
    getState().resetSession();
    expect(getState().isPanelOpen).toBe(true);
  });

  it("does NOT change isPanelOpen — panel stays closed after reset", () => {
    // panel is already closed (beforeEach sets it to false)
    getState().resetSession();
    expect(getState().isPanelOpen).toBe(false);
  });
});

// ══════════════════════════════════════════════════════════════════════════
// Selector helpers
// ══════════════════════════════════════════════════════════════════════════

describe("selector helpers", () => {
  it("selectIsPanelOpen returns isPanelOpen", () => {
    getState().openPanel();
    expect(selectIsPanelOpen(getState())).toBe(true);
  });

  it("selectSessionId returns sessionId", () => {
    getState().setSessionId("s-123");
    expect(selectSessionId(getState())).toBe("s-123");
  });

  it("selectMessages returns the messages array", () => {
    getState().appendMessage(makeMsg("user", "hi"));
    const msgs = selectMessages(getState());
    expect(msgs).toHaveLength(1);
    expect(msgs[0].content).toBe("hi");
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

// ══════════════════════════════════════════════════════════════════════════
// selectCanSendMessage (derived selector)
// ══════════════════════════════════════════════════════════════════════════

describe("selectCanSendMessage", () => {
  it("returns false when sessionId is null (no session created yet)", () => {
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

  it("returns true when status is 'pending_confirmation' (user can still type)", () => {
    getState().setSessionId("s-1");
    getState().setSessionStatus("pending_confirmation");
    expect(selectCanSendMessage(getState())).toBe(true);
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

  it("returns false when both isSending and status is pending_confirmation", () => {
    getState().setSessionId("s-1");
    getState().setSessionStatus("pending_confirmation");
    getState().setIsSending(true);
    expect(selectCanSendMessage(getState())).toBe(false);
  });
});

// ══════════════════════════════════════════════════════════════════════════
// selectShowConfirmCard (derived selector)
// ══════════════════════════════════════════════════════════════════════════

describe("selectShowConfirmCard", () => {
  it("returns false when sessionStatus is not pending_confirmation (active)", () => {
    getState().setSessionId("s-1");
    getState().setPendingPayload({ tickers: ["AAPL"], budget: 10000 });
    // status is 'active' after setSessionId
    expect(selectShowConfirmCard(getState())).toBe(false);
  });

  it("returns false when pendingPayload is null even if status is pending_confirmation", () => {
    getState().setSessionStatus("pending_confirmation");
    // pendingPayload remains null
    expect(selectShowConfirmCard(getState())).toBe(false);
  });

  it("returns true when status is pending_confirmation AND pendingPayload is non-null", () => {
    getState().setSessionStatus("pending_confirmation");
    getState().setPendingPayload({ tickers: ["AAPL"], budget: 10000 });
    expect(selectShowConfirmCard(getState())).toBe(true);
  });

  it("returns false when status is 'confirmed' even with a payload", () => {
    getState().setSessionStatus("confirmed");
    getState().setPendingPayload({ tickers: ["AAPL"], budget: 10000 });
    expect(selectShowConfirmCard(getState())).toBe(false);
  });

  it("returns false when status is 'abandoned' even with a payload", () => {
    getState().setSessionStatus("abandoned");
    getState().setPendingPayload({ tickers: ["AAPL"], budget: 10000 });
    expect(selectShowConfirmCard(getState())).toBe(false);
  });

  it("returns false after setConfirmedRunId clears pendingPayload", () => {
    getState().setSessionStatus("pending_confirmation");
    getState().setPendingPayload({ tickers: ["AAPL"], budget: 10000 });
    // Confirm the run — this clears pendingPayload and sets status to 'confirmed'
    getState().setConfirmedRunId("run-final");
    expect(selectShowConfirmCard(getState())).toBe(false);
  });
});

// ══════════════════════════════════════════════════════════════════════════════
// Round 4 — new tests: id-based dedup and clearError
// ══════════════════════════════════════════════════════════════════════════════

describe("appendMessage dedups by id, not timestamp", () => {
  it("two messages with identical timestamps but different ids are both appended", () => {
    const ts = "2024-06-01T12:00:00.000Z";
    const msg1: ChatMessage = { role: "user", content: "first", timestamp: ts, id: "id-001" };
    const msg2: ChatMessage = { role: "assistant", content: "second", timestamp: ts, id: "id-002" };
    getState().appendMessage(msg1);
    getState().appendMessage(msg2);
    // Both messages must be present — dedup is by id, not timestamp+role
    expect(getState().messages).toHaveLength(2);
    expect(getState().messages[0].id).toBe("id-001");
    expect(getState().messages[1].id).toBe("id-002");
  });

  it("a message without an id is still appended (id is optional)", () => {
    const msg: ChatMessage = { role: "user", content: "no id" };
    getState().appendMessage(msg);
    expect(getState().messages).toHaveLength(1);
    expect(getState().messages[0].content).toBe("no id");
  });
});

describe("clearError resets only the error field", () => {
  it("sets error to null without touching other state", () => {
    // Set up some state
    getState().setSessionId("sess-123");
    getState().setError("Something went wrong");
    getState().setIsSending(true);
    getState().setExtractedSlots({ tickers: ["AAPL"], budget: 50000 });

    // Clear the error
    getState().clearError();

    // Error is cleared
    expect(getState().error).toBeNull();
    // Other state is untouched
    expect(getState().sessionId).toBe("sess-123");
    expect(getState().isSending).toBe(true);
    expect(getState().extractedSlots.tickers).toEqual(["AAPL"]);
    expect(getState().extractedSlots.budget).toBe(50000);
  });

  it("is a no-op when error is already null", () => {
    expect(getState().error).toBeNull();
    getState().clearError();
    expect(getState().error).toBeNull();
  });
});
