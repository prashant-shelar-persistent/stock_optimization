/**
 * AllocationChart — Portfolio allocation pie chart component.
 *
 * Renders a responsive Recharts PieChart showing how a portfolio's budget
 * is distributed across assets. Each slice represents one asset's weight
 * percentage.
 *
 * Features:
 *   - Donut-style pie chart with inner radius for readability
 *   - Custom tooltip showing ticker, weight %, and dollar allocation
 *   - Custom legend with color swatches and weight percentages
 *   - Two color palettes: "classical" (blues/cyans) and "quantum" (violets/purples)
 *   - Responsive container (100% width, configurable height)
 *   - Empty state when weights array is empty or all weights are zero
 *   - Filters out zero-weight assets automatically
 *
 * Props:
 *   weights     — array of AssetWeight objects from the optimization result
 *   title       — optional chart title displayed above the chart
 *   colorScheme — "classical" | "quantum" — controls the color palette
 *                 (default: "classical")
 *
 * Usage:
 *   <AllocationChart
 *     weights={classicalResult.weights}
 *     title="Classical Portfolio Allocation"
 *     colorScheme="classical"
 *   />
 */

import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import type { AssetWeight } from "@/types/api";
import { formatPercent, formatCurrency } from "@/lib/utils";

// ── Color palettes ────────────────────────────────────────────────────────────

/** Blue-dominant palette for classical optimization results. */
const CLASSICAL_COLORS = [
  "#3b82f6", // blue-500
  "#06b6d4", // cyan-500
  "#0ea5e9", // sky-500
  "#10b981", // emerald-500
  "#f59e0b", // amber-500
  "#f97316", // orange-500
  "#6366f1", // indigo-500
  "#14b8a6", // teal-500
  "#ec4899", // pink-500
  "#84cc16", // lime-500
];

/** Violet/purple-dominant palette for quantum optimization results. */
const QUANTUM_COLORS = [
  "#8b5cf6", // violet-500
  "#a855f7", // purple-500
  "#c084fc", // purple-400
  "#e879f9", // fuchsia-400
  "#818cf8", // indigo-400
  "#6366f1", // indigo-500
  "#4f46e5", // indigo-600
  "#7c3aed", // violet-600
  "#9333ea", // purple-600
  "#d946ef", // fuchsia-500
];

// ── Types ─────────────────────────────────────────────────────────────────────

export interface AllocationChartProps {
  weights: AssetWeight[];
  title?: string;
  colorScheme?: "classical" | "quantum";
}

/** Internal shape used by Recharts Pie. */
interface PieSlice {
  name: string;
  ticker: string;
  /** Percentage value (0–100) used as the Recharts dataKey. */
  value: number;
  /** Raw weight fraction (0–1). */
  weight: number;
  /** Dollar allocation. */
  allocation: number;
  sector?: string;
}

// ── Custom tooltip ────────────────────────────────────────────────────────────

interface TooltipPayloadEntry {
  name: string;
  value: number;
  payload: PieSlice;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: TooltipPayloadEntry[];
}

function CustomTooltip({ active, payload }: CustomTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;

  const { ticker, weight, allocation, sector } = payload[0].payload;

  return (
    <div className="rounded-lg border bg-popover px-3 py-2 shadow-md text-sm text-popover-foreground">
      <p className="font-semibold">{ticker}</p>
      {sector && (
        <p className="text-xs text-muted-foreground">{sector}</p>
      )}
      <div className="mt-1 space-y-0.5">
        <p>
          Weight:{" "}
          <span className="font-medium">{formatPercent(weight)}</span>
        </p>
        <p>
          Allocation:{" "}
          <span className="font-medium">{formatCurrency(allocation)}</span>
        </p>
      </div>
    </div>
  );
}

// ── Custom legend ─────────────────────────────────────────────────────────────

interface LegendPayloadEntry {
  value: string;
  color: string;
  payload?: { weight: number };
}

interface CustomLegendProps {
  payload?: LegendPayloadEntry[];
}

function CustomLegend({ payload }: CustomLegendProps) {
  if (!payload || payload.length === 0) return null;

  return (
    <ul className="mt-2 flex flex-wrap justify-center gap-x-4 gap-y-1.5">
      {payload.map((entry) => (
        <li
          key={entry.value}
          className="flex items-center gap-1.5 text-xs text-muted-foreground"
        >
          <span
            className="inline-block h-2.5 w-2.5 flex-shrink-0 rounded-full"
            style={{ backgroundColor: entry.color }}
          />
          <span className="font-medium text-foreground">{entry.value}</span>
          {entry.payload && (
            <span>({formatPercent(entry.payload.weight)})</span>
          )}
        </li>
      ))}
    </ul>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

/**
 * AllocationChart renders a donut pie chart of portfolio asset weights.
 *
 * Zero-weight assets are filtered out automatically. Assets are sorted by
 * weight descending so the largest slice appears first.
 */
export function AllocationChart({
  weights,
  title,
  colorScheme = "classical",
}: AllocationChartProps) {
  const colors = colorScheme === "quantum" ? QUANTUM_COLORS : CLASSICAL_COLORS;

  // Filter zero-weight assets and sort by weight descending
  const chartData: PieSlice[] = weights
    .filter((w) => w.weight > 0.001)
    .sort((a, b) => b.weight - a.weight)
    .map((w) => ({
      name: w.ticker,
      ticker: w.ticker,
      // Recharts uses "value" as the dataKey for pie slices
      value: Math.round(w.weight * 10000) / 100, // percentage (0–100)
      weight: w.weight,
      allocation: w.allocation > 0 ? w.allocation : 0,
      sector: w.sector,
    }));

  // Empty state
  if (chartData.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center rounded-md border border-dashed bg-muted/20 text-sm text-muted-foreground">
        No allocation data available
      </div>
    );
  }

  return (
    <div className="w-full">
      {title && (
        <p className="mb-2 text-center text-sm font-medium text-muted-foreground">
          {title}
        </p>
      )}
      <ResponsiveContainer width="100%" height={280}>
        <PieChart>
          <Pie
            data={chartData}
            cx="50%"
            cy="45%"
            innerRadius={58}
            outerRadius={98}
            paddingAngle={2}
            dataKey="value"
            nameKey="name"
          >
            {chartData.map((entry, index) => (
              <Cell
                key={`cell-${entry.ticker}`}
                fill={colors[index % colors.length]}
                stroke="hsl(var(--background))"
                strokeWidth={2}
              />
            ))}
          </Pie>
          <Tooltip content={<CustomTooltip />} />
          <Legend content={<CustomLegend />} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
