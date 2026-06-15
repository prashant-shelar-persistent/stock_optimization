/**
 * TickerBadge — a removable pill badge for a selected ticker symbol.
 *
 * Displays the ticker symbol (and optionally the sector) with an ×
 * button to remove it from the selection list.
 *
 * Usage:
 *   <TickerBadge
 *     ticker="AAPL"
 *     sector="Technology"
 *     onRemove={() => removeTicker("AAPL")}
 *     disabled={isOptimizing}
 *   />
 */

import { X } from "lucide-react";
import { cn } from "@/lib/utils";

export interface TickerBadgeProps {
  /** The ticker symbol to display (e.g. "AAPL"). */
  ticker: string;
  /** Optional sector label shown as a subtitle. */
  sector?: string;
  /** Called when the user clicks the remove (×) button. */
  onRemove: () => void;
  /** When true, the remove button is hidden and the badge is non-interactive. */
  disabled?: boolean;
  /** Additional class names for the outer container. */
  className?: string;
}

export function TickerBadge({
  ticker,
  sector,
  onRemove,
  disabled = false,
  className,
}: TickerBadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border border-border bg-secondary px-2.5 py-1 text-xs font-medium text-secondary-foreground",
        disabled && "opacity-60",
        className,
      )}
    >
      <span className="flex flex-col leading-none">
        <span className="font-semibold">{ticker}</span>
        {sector && (
          <span className="mt-0.5 text-[10px] text-muted-foreground">
            {sector}
          </span>
        )}
      </span>
      {!disabled && (
        <button
          type="button"
          aria-label={`Remove ${ticker}`}
          onClick={onRemove}
          className="ml-0.5 rounded-full p-0.5 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <X className="h-3 w-3" />
        </button>
      )}
    </span>
  );
}
