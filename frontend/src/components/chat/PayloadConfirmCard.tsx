/**
 * PayloadConfirmCard — displays the extracted optimization parameters for
 * user review before the run is dispatched.
 *
 * Shown when `sessionStatus === "pending_confirmation"` and
 * `pendingPayload` is non-null.
 *
 * Layout:
 *   ┌─────────────────────────────────────────────────┐
 *   │  ✓ Ready to optimize                        │
 *   │  Review the parameters below, then confirm. │
 *   ├─────────────────────────────────────────────────┤
 *   │  Tickers    AAPL · MSFT · GOOGL             │
 *   │  Budget     $100,000                        │
 *   │  Min Return 8%                              │
 *   │  Max Vol    15%                             │
 *   │  …                                          │
 *   ├─────────────────────────────────────────────────┤
 *   │  [Cancel]              [Confirm & Run →]    │
 *   └─────────────────────────────────────────────────┘
 *
 * Props:
 *   - payload       — the ExtractedSlots to display
 *   - isConfirming  — true while the confirm API call is in-flight
 *   - onConfirm()   — called when the user clicks "Confirm & Run"
 *   - onCancel()    — called when the user clicks "Cancel"
 *
 * React 19: Uses `import * as React` for consistent namespace access.
 * No forwardRef needed — refs are plain props in React 19.
 */

import * as React from "react";
import { CheckCircle2, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { formatCurrency, formatPercent } from "@/lib/utils";
import type { ExtractedSlots } from "@/types/api";

// ── Helper: row renderer ───────────────────────────────────────────────────────

interface RowProps {
  label: string;
  value: React.ReactNode;
}

function Row({ label, value }: RowProps) {
  return (
    <div className="flex items-start justify-between gap-4 py-1.5">
      <span className="shrink-0 text-xs font-medium text-muted-foreground">
        {label}
      </span>
      <span className="text-right text-xs text-foreground">{value}</span>
    </div>
  );
}
Row.displayName = "Row";

// ── Props ──────────────────────────────────────────────────────────────────────

export interface PayloadConfirmCardProps {
  /** The extracted optimization parameters to display. */
  payload: ExtractedSlots;
  /** True while the confirm API call is in-flight. */
  isConfirming: boolean;
  /** Called when the user clicks "Confirm & Run". */
  onConfirm: () => void;
  /** Called when the user clicks "Cancel" / "Edit". */
  onCancel: () => void;
  /** Optional extra className for the outer container. */
  className?: string;
}

// ── Component ──────────────────────────────────────────────────────────────────

/**
 * PayloadConfirmCard renders the extracted optimization parameters for review.
 *
 * React 19: function component with no forwardRef — refs are plain props.
 */
function PayloadConfirmCard({
  payload,
  isConfirming,
  onConfirm,
  onCancel,
  className,
}: PayloadConfirmCardProps) {
  const {
    tickers,
    budget,
    min_return,
    max_volatility,
    max_weight_per_asset,
    min_weight_per_asset,
    num_assets_to_select,
    lookback_days,
    run_quantum,
    sector_constraints,
    objectives,
    frontier,
  } = payload;

  // Determine if we have enough data to actually run
  const hasMinimumData =
    tickers && tickers.length > 0 && budget != null && budget > 0;

  return (
    <div
      className={cn(
        "rounded-xl border border-green-500/30 bg-green-50/50 dark:bg-green-950/20",
        className,
      )}
    >
      {/* Header */}
      <div className="flex items-start gap-2.5 px-4 pt-4 pb-3">
        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-green-600 dark:text-green-400" />
        <div>
          <p className="text-sm font-semibold text-green-800 dark:text-green-300">
            Ready to optimize
          </p>
          <p className="mt-0.5 text-xs text-green-700/70 dark:text-green-400/70">
            Review the parameters below, then confirm to start the run.
          </p>
        </div>
      </div>

      <Separator className="bg-green-500/20" />

      {/* Parameter rows */}
      <div className="px-4 py-2">
        {/* Tickers */}
        {tickers && tickers.length > 0 && (
          <Row
            label="Tickers"
            value={
              <div className="flex flex-wrap justify-end gap-1">
                {tickers.map((t) => (
                  <Badge
                    key={t}
                    variant="secondary"
                    className="px-1.5 py-0 text-[10px] font-mono"
                  >
                    {t}
                  </Badge>
                ))}
              </div>
            }
          />
        )}

        {/* Budget */}
        {budget != null && (
          <Row label="Budget" value={formatCurrency(budget)} />
        )}

        {/* Min return */}
        {min_return != null && (
          <Row label="Min Return" value={formatPercent(min_return)} />
        )}

        {/* Max volatility */}
        {max_volatility != null && (
          <Row label="Max Volatility" value={formatPercent(max_volatility)} />
        )}

        {/* Max weight per asset */}
        {max_weight_per_asset != null && (
          <Row
            label="Max Weight / Asset"
            value={formatPercent(max_weight_per_asset)}
          />
        )}

        {/* Min weight per asset */}
        {min_weight_per_asset != null && (
          <Row
            label="Min Weight / Asset"
            value={formatPercent(min_weight_per_asset)}
          />
        )}

        {/* Number of assets to select */}
        {num_assets_to_select != null && (
          <Row label="Assets to Select" value={String(num_assets_to_select)} />
        )}

        {/* Lookback days */}
        {lookback_days != null && (
          <Row label="Lookback" value={`${lookback_days} days`} />
        )}

        {/* Quantum flag */}
        {run_quantum != null && (
          <Row
            label="Quantum"
            value={
              run_quantum ? (
                <Badge variant="secondary" className="text-[10px]">
                  Enabled
                </Badge>
              ) : (
                <span className="text-muted-foreground">Disabled</span>
              )
            }
          />
        )}

        {/* Sector constraints */}
        {sector_constraints && sector_constraints.length > 0 && (
          <Row
            label="Sector Limits"
            value={
              <div className="flex flex-col items-end gap-0.5">
                {sector_constraints.map((sc) => (
                  <span key={sc.sector} className="text-xs">
                    {sc.sector}: ≤{formatPercent(sc.max_weight)}
                  </span>
                ))}
              </div>
            }
          />
        )}

        {/* Objectives summary */}
        {objectives && objectives.length > 0 && (
          <Row
            label="Objectives"
            value={
              <div className="flex flex-col items-end gap-0.5">
                {objectives
                  .filter((o) => o.enabled)
                  .map((o) => (
                    <span key={o.name} className="text-xs capitalize">
                      {o.direction === "maximize" ? "↑" : "↓"}{" "}
                      {o.label ?? o.name}
                    </span>
                  ))}
              </div>
            }
          />
        )}

        {/* Frontier */}
        {frontier?.enabled && (
          <Row
            label="Frontier"
            value={`${frontier.x_measure} vs ${frontier.y_measure} (${frontier.num_points} pts)`}
          />
        )}
      </div>

      <Separator className="bg-green-500/20" />

      {/* Action buttons */}
      <div className="flex items-center justify-between gap-2 px-4 py-3">
        <Button
          variant="ghost"
          size="sm"
          onClick={onCancel}
          disabled={isConfirming}
          className="text-xs text-muted-foreground hover:text-foreground"
        >
          Edit
        </Button>

        <Button
          size="sm"
          onClick={onConfirm}
          disabled={isConfirming || !hasMinimumData}
          className="gap-1.5 text-xs"
        >
          {isConfirming ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Starting run…
            </>
          ) : (
            "Confirm & Run →"
          )}
        </Button>
      </div>
    </div>
  );
}
PayloadConfirmCard.displayName = "PayloadConfirmCard";

export { PayloadConfirmCard };
