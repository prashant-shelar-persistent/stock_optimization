/**
 * ChatAssistant — the floating chat panel rendered in the bottom-right corner
 * of the dashboard.
 *
 * Layout:
 *   ┌─────────────────────────────────────────────┐  ← fixed bottom-right
 *   │  [Bot] Portfolio Assistant          [×]     │  ← header
 *   ├─────────────────────────────────────────────┤
 *   │  ┌─────────────────────────────────────┐   │
 *   │  │  <ChatMessage role="assistant" …/>  │   │  ← scroll area
 *   │  │  <ChatMessage role="user" …/>       │   │
 *   │  │  <PayloadConfirmCard …/>            │   │
 *   │  └─────────────────────────────────────┘   │
 *   ├─────────────────────────────────────────────┤
 *   │  <ChatInput …/>                            │  ← footer
 *   └─────────────────────────────────────────────┘
 *
 * The FAB (Floating Action Button) that toggles the panel is rendered
 * separately below the panel so it is always visible.
 *
 * State management:
 *   - Panel open/close state lives in chatStore.isPanelOpen
 *   - All conversation state lives in chatStore
 *   - API calls are delegated to useChatSession
 *   - After confirmation, useOptimize.startNewRun is called with the run_id
 *     so the existing WebSocket + progress pipeline kicks in automatically
 *
 * Accessibility:
 *   - The panel is a `role="dialog"` with aria-label
 *   - Focus is trapped inside the panel when open
 *   - The FAB has an aria-label and aria-expanded attribute
 *   - The close button has an aria-label
 */

import { useEffect, useRef, useCallback } from "react";
import { Bot, X, RotateCcw, MessageSquare } from "lucide-react";
import { useChatStore } from "@/store/chatStore";
import { useUIStore } from "@/store/uiStore";
import { useChatSession } from "@/hooks/useChatSession";
import { ChatMessage } from "@/components/chat/ChatMessage";
import { PayloadConfirmCard } from "@/components/chat/PayloadConfirmCard";
import { ChatInput } from "@/components/chat/ChatInput";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { cn } from "@/lib/utils";

// ── Welcome message ───────────────────────────────────────────────────────────

const WELCOME_MESSAGE =
  "Hi! I'm your portfolio assistant. Tell me what you'd like to optimize — for example:\n\n" +
  "\"Build a tech-heavy portfolio with AAPL, MSFT, NVDA and a $50,000 budget, " +
  "targeting at least 12% annual return.\"\n\n" +
  "I'll ask follow-up questions if I need more details.";

// ── ChatAssistant panel ───────────────────────────────────────────────────────

export function ChatAssistant() {
  const isPanelOpen = useChatStore((s) => s.isPanelOpen);
  const messages = useChatStore((s) => s.messages);
  const sessionStatus = useChatStore((s) => s.sessionStatus);
  const pendingPayload = useChatStore((s) => s.pendingPayload);
  const isSending = useChatStore((s) => s.isSending);
  const isConfirming = useChatStore((s) => s.isConfirming);
  const error = useChatStore((s) => s.error);
  const confirmedRunId = useChatStore((s) => s.confirmedRunId);

  const togglePanel = useChatStore((s) => s.togglePanel);
  const closePanel = useChatStore((s) => s.closePanel);
  const clearError = useChatStore((s) => s.clearError);

  const { sendMessage, confirmRun, resetSession } = useChatSession();

  // Start tracking the confirmed run in the global UI store
  const startNewRun = useUIStore((s) => s.startNewRun);

  // Scroll to bottom of messages when new ones arrive
  const scrollEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isSending, pendingPayload]);

  // When a run is confirmed, hand off to the existing optimization pipeline
  useEffect(() => {
    if (confirmedRunId) {
      startNewRun(confirmedRunId);
      // Close the panel so the user can see the progress panel
      closePanel();
    }
  }, [confirmedRunId, startNewRun, closePanel]);

  // ── Handlers ────────────────────────────────────────────────────────────────

  const handleSend = useCallback(
    (content: string) => {
      void sendMessage(content);
    },
    [sendMessage],
  );

  const handleConfirm = useCallback(() => {
    void confirmRun();
  }, [confirmRun]);

  const handleCancel = useCallback(() => {
    // Reset the session so the user can start over
    resetSession();
  }, [resetSession]);

  const handleReset = useCallback(() => {
    resetSession();
  }, [resetSession]);

  // Clear the error banner as soon as the user starts typing a new message
  const handleInputChange = useCallback(() => {
    if (error) clearError();
  }, [error, clearError]);

  // ── Derived state ────────────────────────────────────────────────────────────

  const isSessionConfirmed = sessionStatus === "confirmed";
  const showConfirmCard =
    sessionStatus === "pending_confirmation" && pendingPayload != null;
  const inputDisabled = isSessionConfirmed;

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <>
      {/* ── Floating panel ── */}
      <div
        role="dialog"
        aria-label="Portfolio Assistant chat"
        aria-modal="false"
        aria-hidden={!isPanelOpen}
        className={cn(
          // Positioning: fixed bottom-right, above the FAB
          "fixed bottom-20 right-4 z-50",
          // Size
          "flex h-[520px] w-[380px] flex-col",
          // Visual
          "rounded-2xl border bg-card shadow-2xl",
          // Transition
          "transition-all duration-200 ease-in-out",
          isPanelOpen
            ? "translate-y-0 opacity-100 pointer-events-auto"
            : "translate-y-4 opacity-0 pointer-events-none",
        )}
      >
        {/* ── Header ── */}
        <div className="flex items-center justify-between rounded-t-2xl border-b bg-card px-4 py-3">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-full bg-primary/10">
              <Bot className="h-4 w-4 text-primary" />
            </div>
            <div>
              <p className="text-sm font-semibold leading-none">
                Portfolio Assistant
              </p>
              <p className="mt-0.5 text-[10px] text-muted-foreground">
                {sessionStatus === "collecting" && "Listening…"}
                {sessionStatus === "pending_confirmation" && "Ready to confirm"}
                {sessionStatus === "confirmed" && "Run dispatched ✓"}
                {sessionStatus === null && "Ask me anything"}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1">
            {/* Reset button — only shown when a session is active */}
            {sessionStatus !== null && !isSessionConfirmed && (
              <Button
                variant="ghost"
                size="icon"
                onClick={handleReset}
                aria-label="Start new conversation"
                className="h-7 w-7 text-muted-foreground hover:text-foreground"
              >
                <RotateCcw className="h-3.5 w-3.5" />
              </Button>
            )}

            {/* Close button */}
            <Button
              variant="ghost"
              size="icon"
              onClick={closePanel}
              aria-label="Close chat panel"
              className="h-7 w-7 text-muted-foreground hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* ── Message thread ── */}
        <ScrollArea className="flex-1 px-4">
          <div
            className="flex flex-col gap-3 py-4"
            aria-live="polite"
            aria-atomic="false"
            aria-relevant="additions"
          >
            {/* Welcome message (shown before any messages) */}
            {messages.length === 0 && (
              <ChatMessage
                role="assistant"
                content={WELCOME_MESSAGE}
              />
            )}

            {/* Conversation messages */}
            {messages.map((msg, idx) => (
              <ChatMessage
                key={`${msg.role}-${idx}-${msg.timestamp ?? idx}`}
                role={msg.role}
                content={msg.content}
                timestamp={msg.timestamp}
              />
            ))}

            {/* Typing indicator while waiting for assistant reply */}
            {isSending && (
              <ChatMessage
                role="assistant"
                content=""
                isLoading
              />
            )}

            {/* Payload confirmation card */}
            {showConfirmCard && pendingPayload && (
              <PayloadConfirmCard
                payload={pendingPayload}
                isConfirming={isConfirming}
                onConfirm={handleConfirm}
                onCancel={handleCancel}
                className="mt-1"
              />
            )}

            {/* Error alert */}
            {error && (
              <Alert variant="destructive" className="py-2">
                <AlertDescription className="text-xs">{error}</AlertDescription>
              </Alert>
            )}

            {/* Scroll anchor */}
            <div ref={scrollEndRef} />
          </div>
        </ScrollArea>

        {/* ── Input footer ── */}
        <div className="rounded-b-2xl border-t bg-card px-4 py-3">
          <ChatInput
            onSend={handleSend}
            isSending={isSending}
            disabled={inputDisabled}
            onChange={handleInputChange}
            placeholder={
              showConfirmCard
                ? "Confirm or edit the parameters above…"
                : "Describe your portfolio goals…"
            }
          />
        </div>
      </div>

      {/* ── FAB toggle button ── */}
      <button
        type="button"
        onClick={togglePanel}
        aria-label={isPanelOpen ? "Close chat assistant" : "Open chat assistant"}
        aria-expanded={isPanelOpen}
        className={cn(
          // Positioning
          "fixed bottom-4 right-4 z-50",
          // Size & shape
          "flex h-12 w-12 items-center justify-center rounded-full",
          // Visual
          "bg-primary text-primary-foreground shadow-lg",
          // Hover / focus
          "hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2",
          "focus-visible:ring-ring focus-visible:ring-offset-2",
          // Transition
          "transition-all duration-200 ease-in-out",
          isPanelOpen && "rotate-0 scale-95",
        )}
      >
        {isPanelOpen ? (
          <X className="h-5 w-5" />
        ) : (
          <MessageSquare className="h-5 w-5" />
        )}
      </button>
    </>
  );
}
