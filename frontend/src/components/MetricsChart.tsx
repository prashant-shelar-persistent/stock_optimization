/**
 * MetricsChart — Side-by-side metrics comparison bar chart.
 *
 * Displays three key portfolio metrics (Expected Return, Volatility, Sharpe
 * Ratio) as individual bar charts, comparing Classical, QAOA, and VQE
 * strategies side-by-side. Each metric is rendered in its own responsive bar
 * chart within a 3-column grid (stacked on mobile). Each bar is individually
 * coloured via Recharts `Cell` components.
 *
 * Features:
 *   - Three bar charts: Return, Volatility, Sharpe Ratio
 *   - Classical (blue), QAOA (violet), VQE (purple) colour coding via Cell
 *   - Null/undefined strategies are omitted — only available solvers shown
 *   - Custom tooltips with formatted values, passed as render functions for
 *     React 19 concurrent-rendering safety (no stale-closure risk)
 *   - Responsive containers (100% width)
 *   - Accessible colour palette consistent with the rest of the dashboard
 *
 * Props:
 *   classical — PortfolioMetrics from the classical optimisation (required)
 *   qaoa      — optional PortfolioMetrics from QAOA
 *   vqe       — optional PortfolioMetrics from VQE
 *
 * Usage:
 *   <MetricsChart
 *     classical={classicalResult.metrics}
 *     qaoa={quantumResult?.qaoa?.metrics}
 *     vqe={quantumResult?.vqe?.metrics}
 *   />
 */

import { useCallback } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import type { PortfolioMetrics } from "@/types/api";
import { formatPercent, formatNumber } from "@/lib/utils";

// ── Colors ────────────────────────────────────────────────────────────────────

const CLASSICAL_COLOR = "#3b82f6"; // blue-500
const QAOA_COLOR = "#8b5cf6";      // violet-500
const VQE_COLOR = "#a855f7";       // purple-500

// ── Types ─────────────────────────────────────────────────────────────────────

export interface MetricsChartProps {
  classical: PortfolioMetrics;
  qaoa?: PortfolioMetrics | null;
  vqe?: PortfolioMetrics | null;
}

/** A single data point for a bar chart. */
interface MetricDataPoint {
  /** Strategy name shown on the X-axis. */
  name: string;
  /** Metric value. */
  value: number;
  /** Fill colour for this bar (applied via Cell). */
  color: string;
}

interface TooltipPayloadEntry {
  name: string;
  value: number;
  color: string;
  payload: MetricDataPoint;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: TooltipPayloadEntry[];
  label?: string;
  /** Whether to format the value as a percentage. */
  isPercent?: boolean;
}

// ── Custom tooltip ────────────────────────────────────────────────────────────

/**
 * Custom Recharts tooltip rendered as a render function (not a pre-instantiated
 * element) so that React 19 concurrent rendering never encounters stale closures
 * from a captured ReactElement snapshot.
 */
function CustomTooltip({
  active,
  payload,
  label,
  isPercent = false,
}: CustomTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;

  return (
    <div className="rounded-lg border bg-popover px-3 py-2 shadow-md text-sm text-popover-foreground">
      <p className="mb-1 font-semibold">{label}</p>
      {payload.map((entry) => (
        <div key={entry.name} className="flex items-center gap-2">
          <span
            className="inline-block h-2.5 w-2.5 flex-shrink-0 rounded-full"
            style={{ backgroundColor: entry.color }}
          />
          <span className="text-muted-foreground">{entry.name}:</span>
          <span className="font-medium tabular-nums">
            {isPercent
              ? formatPercent(entry.value / 100)
              : formatNumber(entry.value, 3)}
          </span>
        </div>
      ))}
    </div>
  );
}

// ── Single metric bar chart ───────────────────────────────────────────────────

interface SingleMetricChartProps {
  /** Chart title shown above the chart. */
  title: string;
  /** Data points for each strategy. */
  data: MetricDataPoint[];
  /** Whether to format Y-axis ticks as percentages. */
  isPercent?: boolean;
  /** Height of the chart in pixels. */
  height?: number;
}

function SingleMetricChart({
  title,
  data,
  isPercent = false,
  height = 200,
}: SingleMetricChartProps) {
  // Compute Y-axis domain with padding
  const values = data.map((d) => d.value);
  const maxVal = Math.max(...values);
  const minVal = Math.min(...values, 0);
  const padding = (maxVal - minVal) * 0.15 || 0.1;
  const domainMax = maxVal + padding;
  const domainMin = Math.min(minVal - padding, 0);

  /**
   * Render function for the Recharts Tooltip `content` prop.
   *
   * Passing a render function (rather than a pre-instantiated ReactElement)
   * is the React 19 concurrent-rendering-safe pattern: Recharts calls this
   * function during its own render cycle, so the `isPercent` closure value
   * is always current and never stale across concurrent renders or Suspense
   * boundaries.
   */
  const renderTooltip = useCallback(
    (props: object) => (
      <CustomTooltip
        {...(props as CustomTooltipProps)}
        isPercent={isPercent}
      />
    ),
    [isPercent],
  );

  return (
    <div className="flex flex-col gap-1">
      <p className="text-center text-xs font-medium text-muted-foreground">
        {title}
      </p>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart
          data={data}
          margin={{ top: 4, right: 8, left: 0, bottom: 4 }}
          barCategoryGap="30%"
        >
          <CartesianGrid
            strokeDasharray="3 3"
            stroke="hsl(var(--border))"
            vertical={false}
          />
          <XAxis
            dataKey="name"
            tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
            axisLine={{ stroke: "hsl(var(--border))" }}
            tickLine={false}
          />
          <YAxis
            domain={[domainMin, domainMax]}
            tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
            axisLine={false}
            tickLine={false}
            width={38}
            tickFormatter={(v: number) =>
              isPercent
                ? `${(v).toFixed(0)}%`
                : formatNumber(v, 2)
            }
          />
          <Tooltip
            content={renderTooltip}
            cursor={{ fill: "hsl(var(--muted))", opacity: 0.4 }}
          />
          <Bar dataKey="value" radius={[3, 3, 0, 0]} maxBarSize={52}>
            {data.map((entry) => (
              <Cell
                key={`cell-${entry.name}`}
                fill={entry.color}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

/**
 * MetricsChart renders three side-by-side bar charts comparing Expected Return,
 * Volatility, and Sharpe Ratio across Classical, QAOA, and VQE strategies.
 *
 * Each chart uses Recharts `Cell` components to apply per-bar colours
 * (blue for Classical, violet for QAOA, purple for VQE). Null/undefined
 * strategies are omitted from all charts automatically.
 */
export function MetricsChart({ classical, qaoa, vqe }: MetricsChartProps) {
  // Build data arrays for each metric
  const returnData: MetricDataPoint[] = [
    {
      name: "Classical",
      value: Math.round(classical.expected_return * 10000) / 100,
      color: CLASSICAL_COLOR,
    },
    ...(qaoa
      ? [
          {
            name: "QAOA",
            value: Math.round(qaoa.expected_return * 10000) / 100,
            color: QAOA_COLOR,
          },
        ]
      : []),
    ...(vqe
      ? [
          {
            name: "VQE",
            value: Math.round(vqe.expected_return * 10000) / 100,
            color: VQE_COLOR,
          },
        ]
      : []),
  ];

  const volatilityData: MetricDataPoint[] = [
    {
      name: "Classical",
      value: Math.round(classical.volatility * 10000) / 100,
      color: CLASSICAL_COLOR,
    },
    ...(qaoa
      ? [
          {
            name: "QAOA",
            value: Math.round(qaoa.volatility * 10000) / 100,
            color: QAOA_COLOR,
          },
        ]
      : []),
    ...(vqe
      ? [
          {
            name: "VQE",
            value: Math.round(vqe.volatility * 10000) / 100,
            color: VQE_COLOR,
          },
        ]
      : []),
  ];

  const sharpeData: MetricDataPoint[] = [
    {
      name: "Classical",
      value: Math.round(classical.sharpe_ratio * 1000) / 1000,
      color: CLASSICAL_COLOR,
    },
    ...(qaoa
      ? [
          {
            name: "QAOA",
            value: Math.round(qaoa.sharpe_ratio * 1000) / 1000,
            color: QAOA_COLOR,
          },
        ]
      : []),
    ...(vqe
      ? [
          {
            name: "VQE",
            value: Math.round(vqe.sharpe_ratio * 1000) / 1000,
            color: VQE_COLOR,
          },
        ]
      : []),
  ];

  const hasQuantum = qaoa !== undefined && qaoa !== null;
  const hasVqe = vqe !== undefined && vqe !== null;

  return (
    <div className="w-full space-y-2">
      {/* Colour legend */}
      <div className="flex flex-wrap justify-center gap-x-5 gap-y-1">
        <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span
            className="inline-block h-2.5 w-2.5 rounded-full"
            style={{ backgroundColor: CLASSICAL_COLOR }}
          />
          <span className="font-medium text-foreground">Classical</span>
        </span>
        {hasQuantum && (
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: QAOA_COLOR }}
            />
            <span className="font-medium text-foreground">QAOA</span>
          </span>
        )}
        {hasVqe && (
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: VQE_COLOR }}
            />
            <span className="font-medium text-foreground">VQE</span>
          </span>
        )}
      </div>

      {/* Three metric charts in a responsive grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <SingleMetricChart
          title="Expected Return (%)"
          data={returnData}
          isPercent
          height={200}
        />
        <SingleMetricChart
          title="Volatility (%)"
          data={volatilityData}
          isPercent
          height={200}
        />
        <SingleMetricChart
          title="Sharpe Ratio"
          data={sharpeData}
          isPercent={false}
          height={200}
        />
      </div>
    </div>
  );
}
