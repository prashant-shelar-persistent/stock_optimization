/**
 * ChatMessage — renders a single message bubble in the conversation thread.
 *
 * Visual design:
 *   - User messages: right-aligned, primary-coloured bubble
 *   - Assistant messages: left-aligned, muted card-style bubble
 *   - Timestamps are shown below each bubble in a subtle muted style
 *   - A small avatar/icon differentiates user vs. assistant
 *
 * Props:
 *   - role      — "user" | "assistant"
 *   - content   — the message text (may contain newlines)
 *   - timestamp — optional ISO-8601 string; rendered as a relative or
 *                 absolute time label
 *   - isLoading — when true, renders an animated typing indicator instead
 *                 of content (used for the "assistant is thinking" state)
 *
 * React 19: Uses `import * as React` for consistent namespace access.
 * No forwardRef needed — refs are plain props in React 19.
 */

import { Bot, User } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ChatRole } from "@/types/api";

// ── Typing indicator ───────────────────────────────────────────────────────────

function TypingIndicator() {
  return (
    <span
      className="inline-flex items-center gap-1"
      aria-label="Assistant is typing"
    >
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 rounded-full bg-current opacity-60 animate-bounce"
          style={{ animationDelay: `${i * 150}ms`, animationDuration: "900ms" }}
        />
      ))}
    </span>
  );
}
TypingIndicator.displayName = "TypingIndicator";

// ── Timestamp formatter ────────────────────────────────────────────────────────

function formatTimestamp(iso: string): string {
  try {
    const date = new Date(iso);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffSec = Math.floor(diffMs / 1000);

    if (diffSec < 5) return "just now";
    if (diffSec < 60) return `${diffSec}s ago`;
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;

    return date.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

// ── Props ──────────────────────────────────────────────────────────────────────

export interface ChatMessageProps {
  /** Who sent this message. */
  role: ChatRole;
  /** The message text. Newlines are preserved. */
  content: string;
  /** Optional ISO-8601 timestamp for display. */
  timestamp?: string;
  /**
   * When true, renders an animated typing indicator instead of content.
   * Used for the "assistant is thinking" placeholder while the API call
   * is in-flight.
   */
  isLoading?: boolean;
}

// ── Component ──────────────────────────────────────────────────────────────────

/**
 * ChatMessage renders a single message row with avatar, bubble, and timestamp.
 *
 * React 19: function component with no forwardRef — refs are plain props.
 */
function ChatMessage({
  role,
  content,
  timestamp,
  isLoading = false,
}: ChatMessageProps) {
  const isUser = role === "user";

  return (
    <div
      className={cn(
        "flex w-full gap-2.5",
        isUser ? "flex-row-reverse" : "flex-row",
      )}
    >
      {/* Avatar icon */}
      <div
        className={cn(
          "mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full",
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-muted-foreground",
        )}
        aria-hidden="true"
      >
        {isUser ? (
          <User className="h-3.5 w-3.5" />
        ) : (
          <Bot className="h-3.5 w-3.5" />
        )}
      </div>

      {/* Bubble + timestamp */}
      <div
        className={cn(
          "flex max-w-[80%] flex-col gap-1",
          isUser ? "items-end" : "items-start",
        )}
      >
        <div
          className={cn(
            "rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed",
            isUser
              ? "rounded-tr-sm bg-primary text-primary-foreground"
              : "rounded-tl-sm bg-muted text-foreground",
          )}
        >
          {isLoading ? (
            <TypingIndicator />
          ) : (
            // Preserve newlines in the message content
            <span className="whitespace-pre-wrap break-words">{content}</span>
          )}
        </div>

        {/* Timestamp */}
        {timestamp && !isLoading && (
          <time
            dateTime={timestamp}
            className="px-1 text-[10px] text-muted-foreground/60"
          >
            {formatTimestamp(timestamp)}
          </time>
        )}
      </div>
    </div>
  );
}
ChatMessage.displayName = "ChatMessage";

export { ChatMessage };
