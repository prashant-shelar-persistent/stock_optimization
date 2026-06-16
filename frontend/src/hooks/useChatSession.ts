/**
 * useChatSession — custom hook that orchestrates the chat assistant lifecycle.
 *
 * Responsibilities:
 *   1. Create a new chat session via `createChatSession` (lazy — on first message)
 *   2. Send user messages via `sendChatMessage` and update chatStore
 *   3. Confirm a pending payload via `confirmChatRun` and return the run_id
 *   4. Rehydrate session state from the backend via `getChatSession`
 *   5. Reset the session (start a new conversation)
 *
 * Design principles:
 *   - All async logic lives here; chatStore only holds synchronous UI state.
 *   - Optimistic UI: the user's message is appended to the store immediately
 *     before the API call resolves, so the UI feels instant.
 *   - Error handling: API errors are caught, formatted, and stored in
 *     chatStore.error so the ChatAssistant panel can surface them.
 *   - The hook is stable across renders (all callbacks are memoised with
 *     useCallback and have minimal dependency arrays).
 *
 * Returns:
 *   - sendMessage(content)   — send a user message; returns the assistant reply
 *   - confirmRun(overrides?) — confirm the pending payload; returns run_id
 *   - resetSession()         — abandon the current session and start fresh
 *   - rehydrate(sessionId)   — reload full session state from the backend
 */

import { useCallback } from "react";
import {
  createChatSession,
  sendChatMessage,
  confirmChatRun,
  getChatSession,
} from "@/lib/api";
import { useChatStore } from "@/store/chatStore";
import type { ExtractedSlots } from "@/types/api";

// ── Return type ────────────────────────────────────────────────────────────────

export interface UseChatSessionReturn {
  /**
   * Send a user message to the active (or newly created) session.
   *
   * Workflow:
   *   1. Optimistically appends the user message to the store.
   *   2. Creates a new session if none exists yet.
   *   3. Calls `sendChatMessage` and appends the assistant reply.
   *   4. Updates extracted slots and session status in the store.
   *
   * @returns The assistant reply string, or null if the call failed.
   */
  sendMessage: (content: string) => Promise<string | null>;

  /**
   * Confirm the pending payload and dispatch the optimization run.
   *
   * Only callable when `sessionStatus === "pending_confirmation"`.
   *
   * @param overrides - Optional slot overrides to apply before confirming.
   * @returns The new `run_id`, or null if the call failed.
   */
  confirmRun: (
    overrides?: Record<string, unknown>,
  ) => Promise<string | null>;

  /**
   * Reset the chat session to its initial state.
   * Clears all messages, slots, and errors. Does NOT close the panel.
   */
  resetSession: () => void;

  /**
   * Rehydrate the store from a full `ChatSession` fetched from the backend.
   * Useful after a page refresh when a session_id is persisted in localStorage.
   *
   * @param sessionId - The session to reload.
   * @returns True on success, false on failure.
   */
  rehydrate: (sessionId: string) => Promise<boolean>;
}

// ── Hook ───────────────────────────────────────────────────────────────────────

export function useChatSession(): UseChatSessionReturn {
  // Pull only the actions we need from the store (stable references)
  const setSessionId = useChatStore((s) => s.setSessionId);
  const setSessionStatus = useChatStore((s) => s.setSessionStatus);
  const appendMessage = useChatStore((s) => s.appendMessage);
  const setMessages = useChatStore((s) => s.setMessages);
  const setExtractedSlots = useChatStore((s) => s.setExtractedSlots);
  const applyAssistantReply = useChatStore((s) => s.applyAssistantReply);
  const setPendingPayload = useChatStore((s) => s.setPendingPayload);
  const setIsSending = useChatStore((s) => s.setIsSending);
  const setIsConfirming = useChatStore((s) => s.setIsConfirming);
  const setError = useChatStore((s) => s.setError);
  const setConfirmedRunId = useChatStore((s) => s.setConfirmedRunId);
  const resetSessionStore = useChatStore((s) => s.resetSession);

  // Read current session ID without subscribing to re-renders on every change.
  // We use getState() inside callbacks to always get the latest value.
  const getSessionId = useCallback(
    () => useChatStore.getState().sessionId,
    [],
  );

  // ── sendMessage ─────────────────────────────────────────────────────────────

  const sendMessage = useCallback(
    async (content: string): Promise<string | null> => {
      const trimmed = content.trim();
      if (!trimmed) return null;

      // Clear any previous error and set the sending flag
      setError(null);
      setIsSending(true);

      // Optimistically append the user message with a client-side timestamp
      const userTimestamp = new Date().toISOString();
      appendMessage({ role: "user", content: trimmed, timestamp: userTimestamp });

      try {
        // Resolve or create the session ID
        let sessionId = getSessionId();

        if (!sessionId) {
          // First message — create a new session seeded with this message
          const session = await createChatSession({
            initial_message: trimmed,
          });

          // Record the session ID (this also resets conversation state)
          setSessionId(session.session_id);
          sessionId = session.session_id;

          // The backend already processed the initial message and returned
          // the full session including the assistant's first reply.
          // Reconstruct the message list from the session response.
          setMessages(session.messages);
          setExtractedSlots(session.extracted_slots);
          setSessionStatus(session.status);

          if (session.status === "pending_confirmation") {
            setPendingPayload(session.extracted_slots);
          }

          // The assistant reply is the last message in the session
          const lastMsg = session.messages[session.messages.length - 1];
          const replyContent =
            lastMsg?.role === "assistant" ? lastMsg.content : "";

          setIsSending(false);
          return replyContent;
        }

        // Subsequent message — send to the existing session
        const response = await sendChatMessage(sessionId, trimmed);

        // Apply the assistant reply atomically to the store
        applyAssistantReply({
          content: response.reply,
          extractedSlots: response.payload_preview ?? null,
          payloadPreview: response.payload_preview,
          status: response.status,
          timestamp: new Date().toISOString(),
        });

        setIsSending(false);
        return response.reply;
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Failed to send message";
        setError(message);
        setIsSending(false);
        return null;
      }
    },
    [
      appendMessage,
      applyAssistantReply,
      getSessionId,
      setError,
      setExtractedSlots,
      setIsSending,
      setMessages,
      setPendingPayload,
      setSessionId,
      setSessionStatus,
    ],
  );

  // ── confirmRun ──────────────────────────────────────────────────────────────

  const confirmRun = useCallback(
    async (
      overrides?: Record<string, unknown>,
    ): Promise<string | null> => {
      const sessionId = getSessionId();
      if (!sessionId) {
        setError("No active session to confirm.");
        return null;
      }

      setError(null);
      setIsConfirming(true);

      try {
        const response = await confirmChatRun(sessionId, {
          slot_overrides: overrides ?? null,
        });

        // Record the confirmed run ID (also updates status + clears payload)
        setConfirmedRunId(response.run_id);

        setIsConfirming(false);
        return response.run_id;
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Failed to confirm run";
        setError(message);
        setIsConfirming(false);
        return null;
      }
    },
    [getSessionId, setConfirmedRunId, setError, setIsConfirming],
  );

  // ── resetSession ────────────────────────────────────────────────────────────

  const resetSession = useCallback(() => {
    resetSessionStore();
  }, [resetSessionStore]);

  // ── rehydrate ───────────────────────────────────────────────────────────────

  const rehydrate = useCallback(
    async (sessionId: string): Promise<boolean> => {
      setError(null);

      try {
        const session = await getChatSession(sessionId);

        // Restore session ID (resets conversation state first)
        setSessionId(session.session_id);

        // Then restore the full message history and slots
        setMessages(session.messages);
        setExtractedSlots(session.extracted_slots);
        setSessionStatus(session.status);

        if (session.status === "pending_confirmation") {
          setPendingPayload(session.extracted_slots as ExtractedSlots);
        }

        return true;
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Failed to reload session";
        setError(message);
        return false;
      }
    },
    [
      setError,
      setExtractedSlots,
      setMessages,
      setPendingPayload,
      setSessionId,
      setSessionStatus,
    ],
  );

  return { sendMessage, confirmRun, resetSession, rehydrate };
}
