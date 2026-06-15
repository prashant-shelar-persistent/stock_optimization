/**
 * SharpeComparisonChart — Horizontal bar chart comparing Sharpe ratios
 * across Classical, QAOA, and VQE strategies.
 *
 * Highlights the best-performing strategy with a distinct color.
 * Shows the improvement delta (Δ) relative to the classical baseline.
 *
 * Props:
 *   classicalSharpe — Sharpe ratio from classical optimization
 *   qaoaSharpe      — optional Sharpe ratio from QAOA
 *   vqeSharpe       — optional Sharpe ratio from VQE
 */

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  LabelList,
} from "recharts";
import { formatNumber } from "@/lib/utils";

// ── Colors ────────────────────────────────────────────────────────────────────

const CLASSICAL_COLOR = "#3b82f6"; // blue-500
const QAOA_COLOR = "#8b5cf6";      // violet-500
const VQE_COLOR = "#a855f7";       // purple-500
const BEST_GLOW = "#22c55e";       // green-500 — highlights the winner

// ── Types ─────────────────────────────────────────────────────────────────────

interface SharpeComparisonChartProps {
  classicalSharpe: number;
  qaoaSharpe?: number;
  vqeSharpe?: number;
}

interface SharpeDataPoint {
  name: string;
  sharpe: number;
  delta: number | null;
  color: string;
  isBest: boolean;
}

interface TooltipPayloadEntry {
  value: number;
  payload: SharpeDataPoint;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: TooltipPayloadEntry[];
}

// ── Custom tooltip ────────────────────────────────────────────────────────────

function CustomTooltip({ active, payload }: CustomTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;

  const { name, sharpe, delta, isBest } = payload[0].payload;

  return (
    <div className="rounded-lg border bg-popover px-3 py-2 shadow-md text-sm text-popover-foreground">
      <div className="flex items-center gap-2">
        <p className="font-semibold">{name}</p>
        {isBest && (
          <span className="rounded-full bg-green-100 px-1.5 py-0.5 text-xs font-medium text-green-700 dark:bg-green-900/30 dark:text-green-400">
            Best
          </span>
        )}
      </div>
      <p className="mt-1">
        Sharpe:{" "}
        <span className="font-medium">{formatNumber(sharpe, 3)}</span>
      </p>
      {delta !== null && (
        <p className={delta >= 0 ? "text-green-600 dark:text-green-400" : "text-red-500"}>
          vs Classical:{" "}
          <span className="font-medium">
            {delta >= 0 ? "+" : ""}
            {formatNumber(delta, 3)}
          </span>
        </p>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function SharpeComparisonChart({
  classicalSharpe,
  qaoaSharpe,
  vqeSharpe,
}: SharpeComparisonChartProps) {
  // Determine the best Sharpe ratio
  const allSharpes = [
    classicalSharpe,
    ...(qaoaSharpe !== undefined ? [qaoaSharpe] : []),
    ...(vqeSharpe !== undefined ? [vqeSharpe] : []),
  ];
  const bestSharpe = Math.max(...allSharpes);

  const data: SharpeDataPoint[] = [
    {
      name: "Classical",
      sharpe: classicalSharpe,
      delta: null,
      color: classicalSharpe === bestSharpe ? BEST_GLOW : CLASSICAL_COLOR,
      isBest: classicalSharpe === bestSharpe,
    },
    ...(qaoaSharpe !== undefined
      ? [
          {
            name: "QAOA",
            sharpe: qaoaSharpe,
            delta: qaoaSharpe - classicalSharpe,
            color: qaoaSharpe === bestSharpe ? BEST_GLOW : QAOA_COLOR,
            isBest: qaoaSharpe === bestSharpe,
          },
        ]
      : []),
    ...(vqeSharpe !== undefined
      ? [
          {
            name: "VQE",
            sharpe: vqeSharpe,
            delta: vqeSharpe - classicalSharpe,
            color: vqeSharpe === bestSharpe ? BEST_GLOW : VQE_COLOR,
            isBest: vqeSharpe === bestSharpe,
          },
        ]
      : []),
  ];

  // Compute axis domain with a bit of padding
  const maxSharpe = Math.max(...data.map((d) => d.sharpe));
  const minSharpe = Math.min(...data.map((d) => d.sharpe), 0);
  const padding = (maxSharpe - minSharpe) * 0.15 || 0.1;
  const domainMax = Math.ceil((maxSharpe + padding) * 10) / 10;
  const domainMin = Math.floor((minSharpe - padding) * 10) / 10;

  return (
    <ResponsiveContainer width="100%" height={data.length * 56 + 40}>
      <BarChart
        data={data}
        layout="vertical"
        margin={{ top: 4, right: 64, left: 8, bottom: 4 }}
        barCategoryGap="30%"
      >
        <CartesianGrid
          strokeDasharray="3 3"
          horizontal={false}
          stroke="hsl(var(--border))"
        />
        <XAxis
          type="number"
          domain={[domainMin, domainMax]}
          tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
          axisLine={{ stroke: "hsl(var(--border))" }}
          tickLine={false}
          tickFormatter={(v: number) => formatNumber(v, 2)}
        />
        <YAxis
          type="category"
          dataKey="name"
          tick={{ fontSize: 12, fill: "hsl(var(--foreground))", fontWeight: 500 }}
          axisLine={false}
          tickLine={false}
          width={72}
        />
        <Tooltip content={<CustomTooltip />} cursor={{ fill: "hsl(var(--muted))", opacity: 0.4 }} />
        <Bar dataKey="sharpe" radius={[0, 4, 4, 0]} maxBarSize={32}>
          {data.map((entry) => (
            <Cell
              key={`cell-${entry.name}`}
              fill={entry.color}
              opacity={entry.isBest ? 1 : 0.8}
            />
          ))}
          <LabelList
            dataKey="sharpe"
            position="right"
            formatter={(v: number) => formatNumber(v, 3)}
            style={{
              fontSize: "11px",
              fill: "hsl(var(--foreground))",
              fontWeight: 500,
            }}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
