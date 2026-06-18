/**
 * ChatInput — the message composition area at the bottom of the chat panel.
 *
 * Features:
 *   - Auto-growing textarea (up to ~4 lines) that resets after send
 *   - Send on Enter (Shift+Enter inserts a newline)
 *   - Send button with loading spinner while a message is in-flight
 *   - Disabled when `disabled` prop is true (e.g. session is confirmed)
 *   - Character count hint when approaching the limit
 *   - Accessible: labelled textarea, aria-busy on the send button
 *
 * Props:
 *   - onSend(content)  — called with the trimmed message text
 *   - isSending        — true while the API call is in-flight
 *   - disabled         — true to fully disable the input (e.g. after confirm)
 *   - placeholder      — optional placeholder text
 */

import { useRef, useState, useCallback, useEffect } from "react";
import { SendHorizonal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// ── Constants ─────────────────────────────────────────────────────────────────

const MAX_CHARS = 2000;
const WARN_THRESHOLD = 1800;

// ── Props ─────────────────────────────────────────────────────────────────────

export interface ChatInputProps {
  /**
   * Called with the trimmed message text when the user submits.
   * The input is cleared immediately after this is called.
   */
  onSend: (content: string) => void;
  /** True while the previous message is still being processed. */
  isSending?: boolean;
  /** When true, the entire input is disabled (e.g. session confirmed). */
  disabled?: boolean;
  /** Placeholder text shown when the textarea is empty. */
  placeholder?: string;
  /** Optional extra className for the outer container. */
  className?: string;
  /**
   * Called whenever the textarea value changes (on every keystroke).
   * Used by ChatAssistant to clear the error banner when the user starts typing.
   */
  onChange?: (value: string) => void;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function ChatInput({
  onSend,
  isSending = false,
  disabled = false,
  placeholder = "Ask me to build a portfolio…",
  className,
  onChange,
}: ChatInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize the textarea as the user types
  const autoResize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    // Cap at ~4 lines (approx 96px)
    el.style.height = `${Math.min(el.scrollHeight, 96)}px`;
  }, []);

  useEffect(() => {
    autoResize();
  }, [value, autoResize]);

  // ── Submit handler ──────────────────────────────────────────────────────────

  const handleSubmit = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || isSending || disabled) return;
    onSend(trimmed);
    setValue("");
    // Reset height after clearing
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [value, isSending, disabled, onSend]);

  // ── Keyboard handler ────────────────────────────────────────────────────────

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  // ── Derived state ───────────────────────────────────────────────────────────

  const charCount = value.length;
  const isOverLimit = charCount > MAX_CHARS;
  const showCharCount = charCount >= WARN_THRESHOLD;
  const canSend = value.trim().length > 0 && !isSending && !disabled && !isOverLimit;

  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <div
        className={cn(
          "flex items-end gap-2 rounded-xl border bg-background px-3 py-2 transition-colors",
          "focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-1",
          disabled && "opacity-60 cursor-not-allowed",
          isOverLimit && "border-destructive focus-within:ring-destructive",
        )}
      >
        {/* Textarea */}
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            onChange?.(e.target.value);
          }}
          onKeyDown={handleKeyDown}
          placeholder={disabled ? "Session complete." : placeholder}
          disabled={disabled || isSending}
          rows={1}
          maxLength={MAX_CHARS + 100} // allow slight overage so user sees the warning
          aria-label="Chat message"
          aria-multiline="true"
          className={cn(
            "flex-1 resize-none bg-transparent text-sm leading-relaxed",
            "placeholder:text-muted-foreground/60",
            "focus:outline-none",
            "disabled:cursor-not-allowed",
            "min-h-[24px]",
          )}
        />

        {/* Send button */}
        <Button
          type="button"
          size="icon"
          variant={canSend ? "default" : "ghost"}
          onClick={handleSubmit}
          disabled={!canSend}
          aria-label="Send message"
          aria-busy={isSending}
          aria-disabled={!canSend}
          className={cn(
            "h-8 w-8 shrink-0 transition-all",
            canSend ? "opacity-100" : "opacity-40",
          )}
        >
          <SendHorizonal className="h-4 w-4" />
        </Button>
      </div>

      {/* Character count warning */}
      {showCharCount && (
        <p
          className={cn(
            "self-end pr-1 text-[10px]",
            isOverLimit ? "text-destructive" : "text-muted-foreground/60",
          )}
        >
          {charCount}/{MAX_CHARS}
        </p>
      )}

      {/* Keyboard hint */}
      {!disabled && (
        <p className="self-start pl-1 text-[10px] text-muted-foreground/40">
          Enter to send · Shift+Enter for newline
        </p>
      )}
    </div>
  );
}
