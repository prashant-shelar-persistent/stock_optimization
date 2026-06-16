/**
 * Chat assistant state store powered by Zustand.
 *
 * Manages the floating ChatAssistant panel lifecycle:
 *   - isPanelOpen        — whether the chat panel is visible
 *   - sessionId          — the active backend session ID (null when no session)
 *   - messages           — ordered list of chat messages (user + assistant)
 *   - extractedSlots     — partial OptimizationRequest extracted by the LLM
 *   - sessionStatus      — mirrors the backend ChatSessionStatus
 *   - pendingPayload     — the payload preview awaiting user confirmation
 *   - isSending          — true while a message is in-flight to the backend
 *   - isConfirming       — true while the confirm request is in-flight
 *   - error              — last error message (null when no error)
 *   - confirmedRunId     — the run_id returned after a successful confirmation
 *
 * The store is intentionally kept free of async logic — all API calls live
 * in the `useChatSession` hook.  The store only holds derived UI state and
 * provides synchronous actions that the hook calls after each API response.
 */

import { create } from "zustand";
import type {
  ChatMessage,
  ChatSessionStatus,
  ExtractedSlots,
} from "@/types/api";

// ── State shape ────────────────────────────────────────────────────────────────

interface ChatState {
  /**
   * Whether the floating chat panel is currently visible.
   * Toggled by the FAB button in the bottom-right corner.
   */
  isPanelOpen: boolean;

  /**
   * The backend session ID for the active conversation.
   * Null when no session has been created yet (or after a reset).
   */
  sessionId: string | null;

  /**
   * Ordered list of chat messages rendered in the conversation thread.
   * Each message has a `role` ("user" | "assistant") and `content`.
   */
  messages: ChatMessage[];

  /**
   * Partial OptimizationRequest slots extracted by the LLM across turns.
   * Updated after every assistant reply that includes new slot data.
   */
  extractedSlots: ExtractedSlots;

  /**
   * Mirrors the backend `ChatSessionStatus`.
   * - "active"               — conversation in progress, more turns expected
   * - "pending_confirmation" — LLM has enough data; payload preview is ready
   * - "confirmed"            — user confirmed; optimization run dispatched
   * - "abandoned"            — session was abandoned / reset
   * - null                   — no session exists yet
   */
  sessionStatus: ChatSessionStatus | null;

  /**
   * The extracted-slots payload preview shown to the user before they
   * confirm the optimization run.  Non-null only when
   * `sessionStatus === "pending_confirmation"`.
   */
  pendingPayload: ExtractedSlots | null;

  /**
   * True while a `sendChatMessage` API call is in-flight.
   * Used to disable the input field and show a loading indicator.
   */
  isSending: boolean;

  /**
   * True while a `confirmChatRun` API call is in-flight.
   * Used to disable the confirm button and show a spinner.
   */
  isConfirming: boolean;

  /**
   * The last error message surfaced to the user (null when no error).
   * Cleared automatically when a new message is sent or the session resets.
   */
  error: string | null;

  /**
   * The `run_id` returned by the backend after a successful confirmation.
   * Non-null only after `sessionStatus === "confirmed"`.
   * The ChatAssistant component passes this to `useOptimize` to start
   * tracking the new run.
   */
  confirmedRunId: string | null;
}

// ── Actions ────────────────────────────────────────────────────────────────────

interface ChatActions {
  // ── Panel visibility ──────────────────────────────────────────────────────

  /** Open the chat panel. */
  openPanel: () => void;

  /** Close the chat panel. */
  closePanel: () => void;

  /** Toggle the chat panel open/closed. */
  togglePanel: () => void;

  // ── Session lifecycle ─────────────────────────────────────────────────────

  /**
   * Record the newly created session ID returned by `createChatSession`.
   * Resets all conversation state (messages, slots, errors) for a fresh start.
   */
  setSessionId: (sessionId: string) => void;

  /**
   * Update the session status.  Called after every API response that
   * includes a new `status` field.
   */
  setSessionStatus: (status: ChatSessionStatus) => void;

  // ── Message management ────────────────────────────────────────────────────

  /**
   * Append a single message to the conversation thread.
   * Used to optimistically add the user's message before the API responds,
   * and to append the assistant's reply after the response arrives.
   */
  appendMessage: (message: ChatMessage) => void;

  /**
   * Replace the entire messages array.
   * Used when rehydrating state from a `getChatSession` response (e.g.
   * after a page refresh).
   */
  setMessages: (messages: ChatMessage[]) => void;

  // ── Slot management ───────────────────────────────────────────────────────

  /**
   * Merge new extracted slots into the existing `extractedSlots` object.
   * Only non-null/undefined values from `partial` overwrite existing keys,
   * so earlier slot values are preserved when the LLM returns a sparse update.
   */
  mergeExtractedSlots: (partial: ExtractedSlots) => void;

  /**
   * Replace the entire `extractedSlots` object.
   * Used when rehydrating from a full `ChatSession` response.
   */
  setExtractedSlots: (slots: ExtractedSlots) => void;

  // ── Payload preview ───────────────────────────────────────────────────────

  /**
   * Set the payload preview that the user must confirm before the
   * optimization run is dispatched.  Pass `null` to clear it.
   */
  setPendingPayload: (payload: ExtractedSlots | null) => void;

  // ── Loading flags ─────────────────────────────────────────────────────────

  /** Set the `isSending` flag (true while a message API call is in-flight). */
  setIsSending: (value: boolean) => void;

  /** Set the `isConfirming` flag (true while a confirm API call is in-flight). */
  setIsConfirming: (value: boolean) => void;

  // ── Error handling ────────────────────────────────────────────────────────

  /**
   * Set an error message to display in the chat panel.
   * Pass `null` to clear the current error.
   */
  setError: (message: string | null) => void;

  // ── Confirmation ──────────────────────────────────────────────────────────

  /**
   * Record the `run_id` returned after a successful confirmation.
   * Also updates `sessionStatus` to `"confirmed"` and clears `pendingPayload`.
   */
  setConfirmedRunId: (runId: string) => void;

  // ── Convenience actions ───────────────────────────────────────────────────

  /**
   * Convenience: record the assistant's reply after a `sendChatMessage`
   * response.  Atomically:
   *   1. Appends the assistant message to the thread.
   *   2. Merges any new extracted slots.
   *   3. Sets `pendingPayload` (may be null if slots are incomplete).
   *   4. Updates `sessionStatus`.
   *   5. Clears `isSending` and any previous error.
   */
  applyAssistantReply: (params: {
    content: string;
    extractedSlots: ExtractedSlots | null;
    payloadPreview: ExtractedSlots | null;
    status: ChatSessionStatus;
    timestamp?: string;
  }) => void;

  /**
   * Convenience: fully reset the chat store to its initial state.
   * Called when the user starts a new conversation or navigates away.
   * Does NOT close the panel — call `closePanel` separately if needed.
   */
  resetSession: () => void;
}

// ── Store ──────────────────────────────────────────────────────────────────────

export type ChatStore = ChatState & ChatActions;

/** The initial (empty) state for the chat store. */
const INITIAL_STATE: ChatState = {
  isPanelOpen: false,
  sessionId: null,
  messages: [],
  extractedSlots: {},
  sessionStatus: null,
  pendingPayload: null,
  isSending: false,
  isConfirming: false,
  error: null,
  confirmedRunId: null,
};

export const useChatStore = create<ChatStore>((set) => ({
  // ── Initial state ──────────────────────────────────────────────────────────
  ...INITIAL_STATE,

  // ── Panel visibility ───────────────────────────────────────────────────────

  openPanel: () => set({ isPanelOpen: true }),

  closePanel: () => set({ isPanelOpen: false }),

  togglePanel: () =>
    set((state) => ({ isPanelOpen: !state.isPanelOpen })),

  // ── Session lifecycle ──────────────────────────────────────────────────────

  setSessionId: (sessionId) =>
    set({
      sessionId,
      // Reset conversation state for the new session
      messages: [],
      extractedSlots: {},
      sessionStatus: "active",
      pendingPayload: null,
      isSending: false,
      isConfirming: false,
      error: null,
      confirmedRunId: null,
    }),

  setSessionStatus: (status) => set({ sessionStatus: status }),

  // ── Message management ─────────────────────────────────────────────────────

  appendMessage: (message) =>
    set((state) => ({
      messages: [...state.messages, message],
    })),

  setMessages: (messages) => set({ messages }),

  // ── Slot management ────────────────────────────────────────────────────────

  mergeExtractedSlots: (partial) =>
    set((state) => {
      // Only overwrite keys whose incoming value is not null/undefined,
      // preserving previously extracted values for keys absent in `partial`.
      const merged: ExtractedSlots = { ...state.extractedSlots };
      for (const key of Object.keys(partial) as (keyof ExtractedSlots)[]) {
        const value = partial[key];
        if (value !== null && value !== undefined) {
          // Type-safe assignment: each key maps to its own value type
          (merged as Record<string, unknown>)[key] = value;
        }
      }
      return { extractedSlots: merged };
    }),

  setExtractedSlots: (slots) => set({ extractedSlots: slots }),

  // ── Payload preview ────────────────────────────────────────────────────────

  setPendingPayload: (payload) => set({ pendingPayload: payload }),

  // ── Loading flags ──────────────────────────────────────────────────────────

  setIsSending: (value) => set({ isSending: value }),

  setIsConfirming: (value) => set({ isConfirming: value }),

  // ── Error handling ─────────────────────────────────────────────────────────

  setError: (message) => set({ error: message }),

  // ── Confirmation ───────────────────────────────────────────────────────────

  setConfirmedRunId: (runId) =>
    set({
      confirmedRunId: runId,
      sessionStatus: "confirmed",
      pendingPayload: null,
      isConfirming: false,
    }),

  // ── Convenience actions ────────────────────────────────────────────────────

  applyAssistantReply: ({ content, extractedSlots, payloadPreview, status, timestamp }) =>
    set((state) => {
      // 1. Build the assistant message
      const assistantMessage: ChatMessage = {
        role: "assistant",
        content,
        ...(timestamp ? { timestamp } : {}),
      };

      // 2. Merge new slots (only non-null values)
      const merged: ExtractedSlots = { ...state.extractedSlots };
      if (extractedSlots) {
        for (const key of Object.keys(extractedSlots) as (keyof ExtractedSlots)[]) {
          const value = extractedSlots[key];
          if (value !== null && value !== undefined) {
            (merged as Record<string, unknown>)[key] = value;
          }
        }
      }

      return {
        messages: [...state.messages, assistantMessage],
        extractedSlots: merged,
        pendingPayload: payloadPreview,
        sessionStatus: status,
        isSending: false,
        error: null,
      };
    }),

  resetSession: () =>
    set({
      sessionId: null,
      messages: [],
      extractedSlots: {},
      sessionStatus: null,
      pendingPayload: null,
      isSending: false,
      isConfirming: false,
      error: null,
      confirmedRunId: null,
      // isPanelOpen is intentionally NOT reset — the panel stays open
      // so the user sees the empty state rather than the panel disappearing.
    }),
}));

// ── Selector helpers (stable references, avoids unnecessary re-renders) ────────

/** Select only the panel open/closed flag. */
export const selectIsPanelOpen = (s: ChatStore) => s.isPanelOpen;

/** Select only the session ID. */
export const selectSessionId = (s: ChatStore) => s.sessionId;

/** Select only the messages array. */
export const selectMessages = (s: ChatStore) => s.messages;

/** Select only the extracted slots. */
export const selectExtractedSlots = (s: ChatStore) => s.extractedSlots;

/** Select only the session status. */
export const selectSessionStatus = (s: ChatStore) => s.sessionStatus;

/** Select only the pending payload preview. */
export const selectPendingPayload = (s: ChatStore) => s.pendingPayload;

/** Select only the isSending flag. */
export const selectIsSending = (s: ChatStore) => s.isSending;

/** Select only the isConfirming flag. */
export const selectIsConfirming = (s: ChatStore) => s.isConfirming;

/** Select only the error message. */
export const selectError = (s: ChatStore) => s.error;

/** Select only the confirmed run ID. */
export const selectConfirmedRunId = (s: ChatStore) => s.confirmedRunId;

/**
 * Derived selector: true when the session is in a state where the user
 * can type and send a new message (session exists, not sending, not confirmed).
 */
export const selectCanSendMessage = (s: ChatStore): boolean =>
  s.sessionId !== null &&
  !s.isSending &&
  s.sessionStatus !== "confirmed" &&
  s.sessionStatus !== "abandoned";

/**
 * Derived selector: true when the payload confirmation card should be shown.
 * Requires `pending_confirmation` status AND a non-null payload preview.
 */
export const selectShowConfirmCard = (s: ChatStore): boolean =>
  s.sessionStatus === "pending_confirmation" && s.pendingPayload !== null;
