/**
 * ChatBubble — the styled bubble container for a single chat message.
 *
 * This is the low-level primitive that renders the rounded rectangle with
 * the role-appropriate background colour.  It is intentionally kept simple
 * so it can be composed into higher-level components (`ChatMessage`) or used
 * standalone for special message types (system notices, inline hints, etc.).
 *
 * Visual variants:
 *   - role="user"      → right-aligned, primary-coloured bubble
 *   - role="assistant" → left-aligned, muted card-style bubble
 *   - variant="system" → full-width, amber-tinted informational bubble
 *
 * Anatomy:
 *   ┌──────────────────────────────────────────────────────┐
 *   │  [children / content]                                │  ← bubble body
 *   └──────────────────────────────────────────────────────┘
 *
 * The bubble does NOT include the avatar icon or timestamp — those are
 * rendered by the parent `ChatMessage` component.
 *
 * Props:
 *   - role      — "user" | "assistant" (controls colour + corner rounding)
 *   - variant   — optional override: "system" renders a full-width notice
 *   - isLoading — when true, renders an animated typing indicator instead
 *                 of children (used for the "assistant is thinking" state)
 *   - children  — the bubble content (text, badges, etc.)
 *   - className — optional extra Tailwind classes for the outer element
 *
 * React 19: Uses `import * as React` for consistent namespace access.
 * No forwardRef needed — refs are plain props in React 19.
 *
 * @example
 * // Basic usage inside ChatMessage
 * <ChatBubble role="user">Hello, build me a portfolio!</ChatBubble>
 *
 * @example
 * // Loading state
 * <ChatBubble role="assistant" isLoading />
 *
 * @example
 * // System notice (full-width)
 * <ChatBubble variant="system">Session reset — starting a new conversation.</ChatBubble>
 */

import * as React from "react";
import { cn } from "@/lib/utils";
import type { ChatRole } from "@/types/api";

// ── Typing indicator ───────────────────────────────────────────────────────────

/**
 * Three animated dots that indicate the assistant is composing a reply.
 * Each dot bounces with a staggered delay to create a wave effect.
 */
function TypingDots() {
  return (
    <span
      className="inline-flex items-center gap-1"
      aria-label="Assistant is typing"
      role="status"
    >
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 rounded-full bg-current opacity-60 animate-bounce"
          style={{ animationDelay: `${i * 150}ms`, animationDuration: "900ms" }}
          aria-hidden="true"
        />
      ))}
    </span>
  );
}
TypingDots.displayName = "TypingDots";

// ── Variant definitions ────────────────────────────────────────────────────────

/**
 * Visual variant for the bubble.
 *
 * - "user"      — primary-coloured, right-aligned tail (rounded-tr-sm)
 * - "assistant" — muted background, left-aligned tail (rounded-tl-sm)
 * - "system"    — full-width amber notice (no directional tail)
 */
export type ChatBubbleVariant = ChatRole | "system";

// ── Props ──────────────────────────────────────────────────────────────────────

export interface ChatBubbleProps {
  /**
   * The role that determines the bubble's visual style.
   * Ignored when `variant="system"` is provided.
   */
  role?: ChatRole;

  /**
   * Explicit variant override.  When set to "system", the bubble renders
   * as a full-width amber informational notice regardless of `role`.
   * Defaults to the value of `role` when omitted.
   */
  variant?: ChatBubbleVariant;

  /**
   * When true, renders an animated typing indicator instead of `children`.
   * Typically used for the assistant's "thinking" placeholder while the
   * API call is in-flight.
   */
  isLoading?: boolean;

  /**
   * The bubble content.  Newlines in plain text are preserved via
   * `whitespace-pre-wrap`.  Pass any React node for richer content.
   */
  children?: React.ReactNode;

  /**
   * Optional extra Tailwind classes applied to the outermost element.
   * Useful for margin/padding overrides from the parent.
   */
  className?: string;
}

// ── Component ──────────────────────────────────────────────────────────────────

/**
 * ChatBubble renders the styled message bubble primitive.
 *
 * It is intentionally stateless and purely presentational — all interaction
 * logic lives in the parent `ChatMessage` or `ChatAssistant` components.
 *
 * React 19: function component with no forwardRef — refs are plain props.
 */
function ChatBubble({
  role = "assistant",
  variant,
  isLoading = false,
  children,
  className,
}: ChatBubbleProps) {
  // Resolve the effective variant (explicit > role fallback)
  const effectiveVariant: ChatBubbleVariant = variant ?? role;

  // ── System notice ──────────────────────────────────────────────────────────
  if (effectiveVariant === "system") {
    return (
      <div
        role="status"
        aria-live="polite"
        className={cn(
          // Full-width, centred text
          "w-full rounded-xl px-3.5 py-2.5 text-center text-xs",
          // Amber tint — works in both light and dark mode
          "bg-amber-50 text-amber-800 dark:bg-amber-950/30 dark:text-amber-300",
          // Subtle border
          "border border-amber-200/60 dark:border-amber-700/40",
          className,
        )}
      >
        {children}
      </div>
    );
  }

  // ── User / assistant bubble ────────────────────────────────────────────────
  const isUser = effectiveVariant === "user";

  return (
    <div
      className={cn(
        // Base bubble shape
        "rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed",
        // Directional tail: shave the corner closest to the avatar
        isUser
          ? "rounded-tr-sm bg-primary text-primary-foreground"
          : "rounded-tl-sm bg-muted text-foreground",
        className,
      )}
    >
      {isLoading ? (
        <TypingDots />
      ) : (
        // Preserve newlines in plain-text message content
        <span className="whitespace-pre-wrap break-words">{children}</span>
      )}
    </div>
  );
}
ChatBubble.displayName = "ChatBubble";

export { ChatBubble };
