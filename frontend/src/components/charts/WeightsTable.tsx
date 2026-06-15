/**
 * WeightsTable — Sortable table displaying portfolio asset weights.
 *
 * Columns:
 *   - Ticker (with sector badge)
 *   - Weight (% of portfolio)
 *   - Allocation (USD)
 *   - Sector
 *
 * Features:
 *   - Sorted by weight descending by default
 *   - Visual weight bar for quick comparison
 *   - Highlights assets with weight > 20% (concentration warning)
 *
 * Props:
 *   weights — array of AssetWeight objects
 *   budget  — total portfolio budget (used if allocation is missing)
 */

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { formatPercent, formatCurrency } from "@/lib/utils";
import type { AssetWeight } from "@/types/api";

// ── Types ─────────────────────────────────────────────────────────────────────

interface WeightsTableProps {
  weights: AssetWeight[];
  budget: number;
  colorScheme?: "classical" | "quantum";
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Returns a Tailwind color class for the weight bar based on scheme. */
function getBarColor(scheme: "classical" | "quantum"): string {
  return scheme === "quantum"
    ? "bg-violet-500"
    : "bg-blue-500";
}

/** Returns a Tailwind color class for concentration warning. */
function getConcentrationClass(weight: number): string {
  if (weight > 0.3) return "text-red-500 font-semibold";
  if (weight > 0.2) return "text-amber-500 font-medium";
  return "";
}

// ── Main component ────────────────────────────────────────────────────────────

export function WeightsTable({
  weights,
  budget,
  colorScheme = "classical",
}: WeightsTableProps) {
  // Filter zero-weight assets and sort by weight descending
  const sortedWeights = [...weights]
    .filter((w) => w.weight > 0.0001)
    .sort((a, b) => b.weight - a.weight);

  if (sortedWeights.length === 0) {
    return (
      <div className="flex h-24 items-center justify-center text-sm text-muted-foreground">
        No assets in portfolio
      </div>
    );
  }

  const maxWeight = sortedWeights[0].weight;
  const barColor = getBarColor(colorScheme);

  return (
    <div className="overflow-hidden rounded-md border">
      <Table>
        <TableHeader>
          <TableRow className="bg-muted/40 hover:bg-muted/40">
            <TableHead className="w-[100px]">Ticker</TableHead>
            <TableHead>Weight</TableHead>
            <TableHead className="text-right">Allocation</TableHead>
            <TableHead className="hidden sm:table-cell">Sector</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sortedWeights.map((asset) => {
            const allocation =
              asset.allocation > 0 ? asset.allocation : asset.weight * budget;
            const barWidth = maxWeight > 0 ? (asset.weight / maxWeight) * 100 : 0;
            const concentrationClass = getConcentrationClass(asset.weight);

            return (
              <TableRow key={asset.ticker}>
                {/* Ticker */}
                <TableCell className="font-mono font-semibold text-sm">
                  {asset.ticker}
                </TableCell>

                {/* Weight with visual bar */}
                <TableCell>
                  <div className="flex items-center gap-2">
                    <span
                      className={`min-w-[52px] text-sm tabular-nums ${concentrationClass}`}
                    >
                      {formatPercent(asset.weight)}
                    </span>
                    <div className="hidden h-1.5 flex-1 overflow-hidden rounded-full bg-muted sm:block">
                      <div
                        className={`h-full rounded-full ${barColor} transition-all`}
                        style={{ width: `${barWidth}%` }}
                      />
                    </div>
                  </div>
                </TableCell>

                {/* Dollar allocation */}
                <TableCell className="text-right tabular-nums text-sm">
                  {formatCurrency(allocation)}
                </TableCell>

                {/* Sector badge */}
                <TableCell className="hidden sm:table-cell">
                  {asset.sector ? (
                    <Badge variant="outline" className="text-xs font-normal">
                      {asset.sector}
                    </Badge>
                  ) : (
                    <span className="text-xs text-muted-foreground">—</span>
                  )}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
