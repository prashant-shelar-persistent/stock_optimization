/**
 * MetricsComparisonBar — Recharts BarChart comparing portfolio metrics
 * side-by-side across Classical, QAOA, and VQE strategies.
 *
 * Displays three grouped bars per metric:
 *   - Expected Return (annualised %)
 *   - Volatility (annualised %)
 *   - Sharpe Ratio
 *
 * Props:
 *   classical — PortfolioMetrics from the classical optimization
 *   qaoa      — optional PortfolioMetrics from QAOA
 *   vqe       — optional PortfolioMetrics from VQE
 *
 * React 19.2: Uses function components with typed props (no forwardRef needed).
 * JSX transform is handled automatically via react-jsx in tsconfig.
 */

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  type TooltipProps,
} from "recharts";
import type { PortfolioMetrics } from "@/types/api";
import { formatPercent, formatNumber } from "@/lib/utils";

// ── Colors ────────────────────────────────────────────────────────────────────

const CLASSICAL_COLOR = "#3b82f6"; // blue-500
const QAOA_COLOR = "#8b5cf6";      // violet-500
const VQE_COLOR = "#a855f7";       // purple-500

// ── Types ─────────────────────────────────────────────────────────────────────

interface MetricsComparisonBarProps {
  classical: PortfolioMetrics;
  qaoa?: PortfolioMetrics;
  vqe?: PortfolioMetrics;
}

interface MetricDataPoint {
  metric: string;
  Classical?: number;
  QAOA?: number;
  VQE?: number;
  /** Whether this metric is a percentage (for tooltip formatting) */
  isPercent: boolean;
}

// ── Custom tooltip ────────────────────────────────────────────────────────────

/**
 * Custom tooltip rendered by Recharts on hover.
 * Typed using Recharts' TooltipProps with our MetricDataPoint payload shape.
 */
function CustomTooltip({
  active,
  payload,
  label,
}: TooltipProps<number, string>) {
  if (!active || !payload || payload.length === 0) return null;

  // Determine if this metric is a percentage
  const isPercent = label === "Return" || label === "Volatility";

  return (
    <div className="rounded-lg border bg-popover px-3 py-2 shadow-md text-sm text-popover-foreground">
      <p className="mb-1 font-semibold">{label}</p>
      {payload.map((entry) => (
        <div key={entry.name} className="flex items-center gap-2">
          <span
            className="inline-block h-2.5 w-2.5 rounded-full flex-shrink-0"
            style={{ backgroundColor: entry.color }}
          />
          <span className="text-muted-foreground">{entry.name}:</span>
          <span className="font-medium">
            {isPercent
              ? formatPercent((entry.value as number) / 100)
              : formatNumber(entry.value as number, 3)}
          </span>
        </div>
      ))}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function MetricsComparisonBar({
  classical,
  qaoa,
  vqe,
}: MetricsComparisonBarProps) {
  // Build chart data — multiply by 100 for percentage display
  const data: MetricDataPoint[] = [
    {
      metric: "Return",
      Classical: Math.round(classical.expected_return * 10000) / 100,
      ...(qaoa ? { QAOA: Math.round(qaoa.expected_return * 10000) / 100 } : {}),
      ...(vqe ? { VQE: Math.round(vqe.expected_return * 10000) / 100 } : {}),
      isPercent: true,
    },
    {
      metric: "Volatility",
      Classical: Math.round(classical.volatility * 10000) / 100,
      ...(qaoa ? { QAOA: Math.round(qaoa.volatility * 10000) / 100 } : {}),
      ...(vqe ? { VQE: Math.round(vqe.volatility * 10000) / 100 } : {}),
      isPercent: true,
    },
    {
      metric: "Sharpe",
      Classical: Math.round(classical.sharpe_ratio * 1000) / 1000,
      ...(qaoa ? { QAOA: Math.round(qaoa.sharpe_ratio * 1000) / 1000 } : {}),
      ...(vqe ? { VQE: Math.round(vqe.sharpe_ratio * 1000) / 1000 } : {}),
      isPercent: false,
    },
  ];

  const hasQuantum = qaoa !== undefined || vqe !== undefined;

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart
        data={data}
        margin={{ top: 8, right: 16, left: 0, bottom: 0 }}
        barCategoryGap="25%"
        barGap={4}
      >
        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
        <XAxis
          dataKey="metric"
          tick={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }}
          axisLine={{ stroke: "hsl(var(--border))" }}
          tickLine={false}
        />
        <YAxis
          tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
          axisLine={false}
          tickLine={false}
          width={40}
        />
        <Tooltip content={<CustomTooltip />} />
        {hasQuantum && (
          <Legend
            wrapperStyle={{ fontSize: "12px", paddingTop: "8px" }}
          />
        )}
        <Bar
          dataKey="Classical"
          fill={CLASSICAL_COLOR}
          radius={[3, 3, 0, 0]}
          maxBarSize={48}
        />
        {qaoa && (
          <Bar
            dataKey="QAOA"
            fill={QAOA_COLOR}
            radius={[3, 3, 0, 0]}
            maxBarSize={48}
          />
        )}
        {vqe && (
          <Bar
            dataKey="VQE"
            fill={VQE_COLOR}
            radius={[3, 3, 0, 0]}
            maxBarSize={48}
          />
        )}
      </BarChart>
    </ResponsiveContainer>
  );
}
