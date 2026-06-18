/**
 * AllocationPieChart — Recharts PieChart showing portfolio asset allocation.
 *
 * Renders a responsive pie chart with:
 *   - Each slice representing an asset's weight in the portfolio
 *   - Custom tooltip showing ticker, weight %, and dollar allocation
 *   - Legend listing all assets with their weights
 *   - Accessible color palette cycling through a fixed set of colors
 *
 * Props:
 *   weights  — array of AssetWeight objects from the optimization result
 *   budget   — total portfolio budget in USD (used to compute dollar amounts)
 *   title    — optional chart title
 *   colorSet — "classical" | "quantum" — controls the color palette
 *
 * React 19.2: Uses function components with typed props (no forwardRef needed).
 * JSX transform is handled automatically via react-jsx in tsconfig.
 */

import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  ResponsiveContainer,
  type TooltipProps,
} from "recharts";
import type { AssetWeight } from "@/types/api";
import { formatPercent, formatCurrency } from "@/lib/utils";

// ── Color palettes ────────────────────────────────────────────────────────────

const CLASSICAL_COLORS = [
  "#3b82f6", // blue-500
  "#06b6d4", // cyan-500
  "#8b5cf6", // violet-500
  "#ec4899", // pink-500
  "#f59e0b", // amber-500
  "#10b981", // emerald-500
  "#f97316", // orange-500
  "#6366f1", // indigo-500
  "#14b8a6", // teal-500
  "#a855f7", // purple-500
];

const QUANTUM_COLORS = [
  "#8b5cf6", // violet-500
  "#a855f7", // purple-500
  "#c084fc", // purple-400
  "#e879f9", // fuchsia-400
  "#f0abfc", // fuchsia-300
  "#818cf8", // indigo-400
  "#6366f1", // indigo-500
  "#4f46e5", // indigo-600
  "#7c3aed", // violet-600
  "#9333ea", // purple-600
];

// ── Types ─────────────────────────────────────────────────────────────────────

interface AllocationPieChartProps {
  weights: AssetWeight[];
  budget: number;
  title?: string;
  colorSet?: "classical" | "quantum";
}

/** Shape of each data point fed to Recharts Pie. */
interface PieDataPoint {
  ticker: string;
  weight: number;
  allocation: number;
  sector?: string;
  /** Recharts uses "name" for the legend label */
  name: string;
  /** Recharts uses "value" as the numeric slice size */
  value: number;
}

// ── Custom tooltip ────────────────────────────────────────────────────────────

/**
 * Custom tooltip rendered by Recharts on hover.
 * Typed using Recharts' TooltipProps with our PieDataPoint payload shape.
 */
function CustomTooltip({
  active,
  payload,
}: TooltipProps<number, string> & { payload?: Array<{ payload: PieDataPoint }> }) {
  if (!active || !payload || payload.length === 0) return null;

  const entry = payload[0];
  const { ticker, weight, allocation, sector } = entry.payload;

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
    <ul className="mt-2 flex flex-wrap justify-center gap-x-4 gap-y-1">
      {payload.map((entry) => (
        <li
          key={entry.value}
          className="flex items-center gap-1.5 text-xs text-muted-foreground"
        >
          <span
            className="inline-block h-2.5 w-2.5 rounded-full flex-shrink-0"
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

export function AllocationPieChart({
  weights,
  budget,
  title,
  colorSet = "classical",
}: AllocationPieChartProps) {
  const colors = colorSet === "quantum" ? QUANTUM_COLORS : CLASSICAL_COLORS;

  // Filter out zero-weight assets and sort by weight descending
  const chartData: PieDataPoint[] = weights
    .filter((w) => w.weight > 0.001)
    .sort((a, b) => b.weight - a.weight)
    .map((w) => ({
      ticker: w.ticker,
      weight: w.weight,
      // Use provided allocation or compute from budget
      allocation: w.allocation > 0 ? w.allocation : w.weight * budget,
      sector: w.sector,
      // Recharts uses "name" and "value" for pie slices
      name: w.ticker,
      value: Math.round(w.weight * 10000) / 100, // percentage for display
    }));

  if (chartData.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center text-sm text-muted-foreground">
        No allocation data available
      </div>
    );
  }

  return (
    <div className="w-full">
      {title && (
        <p className="mb-2 text-sm font-medium text-muted-foreground text-center">
          {title}
        </p>
      )}
      <ResponsiveContainer width="100%" height={260}>
        <PieChart>
          <Pie
            data={chartData}
            cx="50%"
            cy="45%"
            innerRadius={55}
            outerRadius={95}
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
