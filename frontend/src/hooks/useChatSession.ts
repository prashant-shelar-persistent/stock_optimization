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
 * React 19 design principles:
 *   - Uses `useTransition` for non-urgent state updates (message appending,
 *     slot merging) so the input field stays responsive during API calls.
 *   - Uses `useOptimistic` for the optimistic user-message append, giving
 *     instant feedback while the network request is in flight.
 *   - All async logic lives here; chatStore only holds synchronous UI state.
 *   - Error handling: API errors are caught, formatted, and stored in
 *     chatStore.error so the ChatAssistant panel can surface them.
 *     AbortError is silently swallowed — it is not a user-facing error.
 *   - Abort safety: each sendMessage / confirmRun call creates its own
 *     AbortController. The latest controller is stored on a ref so the
 *     cleanup effect can cancel any in-flight request when the component
 *     unmounts or the panel closes.
 *   - The hook is stable across renders (all callbacks are memoised with
 *     useCallback and have minimal dependency arrays).
 *
 * Returns:
 *   - sendMessage(content)   — send a user message; returns the assistant reply
 *   - confirmRun(overrides?) — confirm the pending payload; returns run_id
 *   - resetSession()         — abandon the current session and start fresh
 *   - rehydrate(sessionId)   — reload full session state from the backend
 *   - isPending              — true while a React transition is in progress
 */

import { useCallback, useEffect, useOptimistic, useRef, useTransition } from "react";
import {
  createChatSession,
  sendChatMessage,
  confirmChatRun,
  getChatSession,
} from "@/lib/api";
import { useChatStore } from "@/store/chatStore";
import type { ChatMessage, ExtractedSlots } from "@/types/api";

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

  /**
   * True while a React transition (non-urgent state update) is in progress.
   * Can be used to show a subtle loading indicator without blocking the input.
   */
  isPending: boolean;

  /**
   * The optimistic message list — includes the user's latest message
   * immediately (before the API responds). Use this in the UI instead of
   * the store's `messages` array so the user sees instant feedback.
   * Automatically rolls back if the API call fails.
   */
  optimisticMessages: ChatMessage[];
}

// ── Hook ───────────────────────────────────────────────────────────────────────

export function useChatSession(): UseChatSessionReturn {
  // ── Store selectors (stable references) ──────────────────────────────────

  const setSessionId = useChatStore((s) => s.setSessionId);
  const setSessionStatus = useChatStore((s) => s.setSessionStatus);
  const setMessages = useChatStore((s) => s.setMessages);
  const setExtractedSlots = useChatStore((s) => s.setExtractedSlots);
  const applyAssistantReply = useChatStore((s) => s.applyAssistantReply);
  const setPendingPayload = useChatStore((s) => s.setPendingPayload);
  const setIsSending = useChatStore((s) => s.setIsSending);
  const setIsConfirming = useChatStore((s) => s.setIsConfirming);
  const setError = useChatStore((s) => s.setError);
  const setConfirmedRunId = useChatStore((s) => s.setConfirmedRunId);
  const resetSessionStore = useChatStore((s) => s.resetSession);

  // Read current messages for the optimistic hook (must be a stable selector)
  const messages = useChatStore((s) => s.messages);

  // ── React 19: useTransition for non-urgent state updates ─────────────────
  // isPending is true while the transition's async work is scheduled but not
  // yet committed. We expose it so the UI can show a subtle loading state.
  const [isPending, startTransition] = useTransition();

  // ── React 19: useOptimistic for instant user-message feedback ────────────
  // optimisticMessages mirrors the store's messages array but with the
  // user's latest message appended immediately (before the API responds).
  // The optimistic value is automatically rolled back if the action throws.
  const [optimisticMessages, addOptimisticMessage] = useOptimistic(
    messages,
    (current: ChatMessage[], newMessage: ChatMessage) => [
      ...current,
      newMessage,
    ],
  );

  // ── Read current session ID without subscribing to re-renders ────────────
  // We use getState() inside callbacks to always get the latest value without
  // adding sessionId to every useCallback dependency array.
  const getSessionId = useCallback(
    () => useChatStore.getState().sessionId,
    [],
  );

  // ── Abort controller ref ──────────────────────────────────────────────────
  // Track the latest in-flight AbortController so we can cancel it on unmount.
  const abortControllerRef = useRef<AbortController | null>(null);

  // Cancel any in-flight request when the component unmounts.
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  // ── sendMessage ────────────────────────────────────────────────────────────

  const sendMessage = useCallback(
    async (content: string): Promise<string | null> => {
      const trimmed = content.trim();
      if (!trimmed) return null;

      // Cancel any previous in-flight request before starting a new one
      abortControllerRef.current?.abort();
      const controller = new AbortController();
      abortControllerRef.current = controller;
      const { signal } = controller;

      // Clear any previous error and set the sending flag
      setError(null);
      setIsSending(true);

      // Build the optimistic user message with a stable client-side ID
      const userMessage: ChatMessage = {
        role: "user",
        content: trimmed,
        timestamp: new Date().toISOString(),
        id: crypto.randomUUID(),
      };

      // React 19: wrap non-urgent state updates in a transition so the input
      // field stays responsive. The optimistic append happens synchronously
      // inside the transition callback.
      let replyContent: string | null = null;

      await new Promise<void>((resolve) => {
        startTransition(async () => {
          // Optimistically append the user message for instant UI feedback
          addOptimisticMessage(userMessage);

          try {
            // Resolve or create the session ID
            let sessionId = getSessionId();

            if (!sessionId) {
              // First message — create a new session seeded with this message
              const session = await createChatSession(
                { initial_message: trimmed },
                signal,
              );

              // Record the session ID (this also resets conversation state)
              setSessionId(session.session_id);
              sessionId = session.session_id;

              // The backend already processed the initial message and returned
              // the full session including the assistant's first reply.
              // Reconstruct the message list from the session response.
              setMessages(session.messages);
              setExtractedSlots(session.extracted_slots ?? {});
              setSessionStatus(session.status);

              if (session.status === "pending_confirmation") {
                setPendingPayload(session.extracted_slots);
              }

              // The assistant reply is the last message in the session
              const lastMsg = session.messages[session.messages.length - 1];
              replyContent =
                lastMsg?.role === "assistant" ? lastMsg.content : "";
            } else {
              // Subsequent message — send to the existing session
              const response = await sendChatMessage(sessionId, trimmed, signal);

              // Apply the assistant reply atomically to the store
              applyAssistantReply({
                content: response.reply,
                extractedSlots: response.session.extracted_slots ?? null,
                payloadPreview: response.payload_preview,
                status: response.session.status,
                timestamp: new Date().toISOString(),
              });

              replyContent = response.reply;
            }
          } catch (err) {
            // Silently swallow AbortError — it is not a user-facing error
            if (!(err instanceof DOMException && err.name === "AbortError")) {
              const message =
                err instanceof Error ? err.message : "Failed to send message";
              setError(message);
            }
          } finally {
            setIsSending(false);
            resolve();
          }
        });
      });

      return replyContent;
    },
    [
      addOptimisticMessage,
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

  // ── confirmRun ─────────────────────────────────────────────────────────────

  const confirmRun = useCallback(
    async (
      overrides?: Record<string, unknown>,
    ): Promise<string | null> => {
      const sessionId = getSessionId();
      if (!sessionId) {
        setError("No active session to confirm.");
        return null;
      }

      // Cancel any previous in-flight request before starting a new one
      abortControllerRef.current?.abort();
      const controller = new AbortController();
      abortControllerRef.current = controller;
      const { signal } = controller;

      setError(null);
      setIsConfirming(true);

      try {
        const response = await confirmChatRun(
          sessionId,
          { slot_overrides: overrides ?? null },
          signal,
        );

        // Record the confirmed run ID and ws_token (also updates status + clears payload)
        setConfirmedRunId(response.run_id, response.ws_token);

        setIsConfirming(false);
        return response.run_id;
      } catch (err) {
        // Silently swallow AbortError — it is not a user-facing error
        if (err instanceof DOMException && err.name === "AbortError") {
          setIsConfirming(false);
          return null;
        }
        const message =
          err instanceof Error ? err.message : "Failed to confirm run";
        setError(message);
        setIsConfirming(false);
        return null;
      }
    },
    [getSessionId, setConfirmedRunId, setError, setIsConfirming],
  );

  // ── resetSession ───────────────────────────────────────────────────────────

  const resetSession = useCallback(() => {
    // Cancel any in-flight request when resetting
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    resetSessionStore();
  }, [resetSessionStore]);

  // ── rehydrate ──────────────────────────────────────────────────────────────

  const rehydrate = useCallback(
    async (sessionId: string): Promise<boolean> => {
      setError(null);

      // Cancel any previous in-flight request
      abortControllerRef.current?.abort();
      const controller = new AbortController();
      abortControllerRef.current = controller;
      const { signal } = controller;

      try {
        const session = await getChatSession(sessionId, signal);

        // Restore session ID (resets conversation state first)
        setSessionId(session.session_id);

        // Then restore the full message history and slots
        setMessages(session.messages);
        setExtractedSlots(session.extracted_slots ?? {});
        setSessionStatus(session.status);

        if (session.status === "pending_confirmation") {
          setPendingPayload(session.extracted_slots);
        }

        return true;
      } catch (err) {
        // Silently swallow AbortError — it is not a user-facing error
        if (err instanceof DOMException && err.name === "AbortError") {
          return false;
        }
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

  return { sendMessage, confirmRun, resetSession, rehydrate, isPending, optimisticMessages };
}
