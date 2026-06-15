/**
 * MetricsCard — Displays a single portfolio metric in a compact card format.
 *
 * Used to show Expected Return, Volatility, Sharpe Ratio, and Max Drawdown
 * for each optimization strategy (Classical, QAOA, VQE).
 *
 * Props:
 *   label       — metric name (e.g. "Sharpe Ratio")
 *   value       — numeric value
 *   format      — "percent" | "ratio" | "currency" — controls display format
 *   delta       — optional delta vs baseline (shown with +/- color)
 *   description — optional tooltip/description text
 *   highlight   — if true, renders with a highlighted border
 */

import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
  TooltipProvider,
} from "@/components/ui/tooltip";
import { Info } from "lucide-react";
import { cn, formatPercent, formatNumber, formatCurrency } from "@/lib/utils";

// ── Types ─────────────────────────────────────────────────────────────────────

type MetricFormat = "percent" | "ratio" | "currency";

interface MetricsCardProps {
  label: string;
  value: number;
  format?: MetricFormat;
  delta?: number;
  description?: string;
  highlight?: boolean;
  className?: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatValue(value: number, format: MetricFormat): string {
  switch (format) {
    case "percent":
      return formatPercent(value);
    case "currency":
      return formatCurrency(value);
    case "ratio":
    default:
      return formatNumber(value, 3);
  }
}

function formatDelta(delta: number, format: MetricFormat): string {
  const sign = delta >= 0 ? "+" : "";
  switch (format) {
    case "percent":
      return `${sign}${formatPercent(delta)}`;
    case "currency":
      return `${sign}${formatCurrency(delta)}`;
    case "ratio":
    default:
      return `${sign}${formatNumber(delta, 3)}`;
  }
}

// ── Main component ────────────────────────────────────────────────────────────

export function MetricsCard({
  label,
  value,
  format = "ratio",
  delta,
  description,
  highlight = false,
  className,
}: MetricsCardProps) {
  const deltaPositive = delta !== undefined && delta > 0;
  const deltaNegative = delta !== undefined && delta < 0;

  return (
    <div
      className={cn(
        "rounded-lg border bg-card p-4 transition-colors",
        highlight && "border-primary/50 bg-primary/5",
        className,
      )}
    >
      {/* Label row */}
      <div className="flex items-center gap-1.5">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {label}
        </p>
        {description && (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Info className="h-3 w-3 cursor-help text-muted-foreground/60 hover:text-muted-foreground" />
              </TooltipTrigger>
              <TooltipContent side="top" className="max-w-[200px] text-xs">
                {description}
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}
      </div>

      {/* Value */}
      <p
        className={cn(
          "mt-1 text-2xl font-bold tabular-nums",
          highlight && "text-primary",
        )}
      >
        {formatValue(value, format)}
      </p>

      {/* Delta vs baseline */}
      {delta !== undefined && (
        <p
          className={cn(
            "mt-0.5 text-xs font-medium tabular-nums",
            deltaPositive && "text-green-600 dark:text-green-400",
            deltaNegative && "text-red-500 dark:text-red-400",
            !deltaPositive && !deltaNegative && "text-muted-foreground",
          )}
        >
          {formatDelta(delta, format)} vs Classical
        </p>
      )}
    </div>
  );
}
