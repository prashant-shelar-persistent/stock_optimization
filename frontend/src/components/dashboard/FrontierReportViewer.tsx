/**
 * FrontierReportViewer — Renders the efficient-frontier report bundle.
 *
 * Displays:
 *   - Scatter chart: X-measure vs Y-measure for all frontier points
 *   - Highlights: knee point (star), max-Sharpe (diamond), min-risk (circle)
 *   - Summary stats table: num_dominant, num_dominated, solve_time_ms
 *   - Knee portfolio allocation table
 *   - LLM commentary (if present)
 *
 * Uses a pure SVG scatter plot — no external chart library required.
 *
 * React 19 migration notes:
 *   - No forwardRef — refs are plain props in React 19
 *   - Removed React namespace prefix where not needed
 *   - Type-only imports use `import type`
 *   - useMemo dependencies are explicit and minimal
 */

import { useMemo } from "react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  TrendingUp,
  Star,
  Clock,
  MessageSquare,
} from "lucide-react";
import type { FrontierReport, FrontierPoint } from "@/types/api";

// ── Label helpers ─────────────────────────────────────────────────────────────

const MEASURE_LABELS: Record<string, string> = {
  return: "Expected Return",
  volatility: "Volatility",
  sharpe: "Sharpe Ratio",
  diversification_hhi: "Diversification (HHI)",
  sector_concentration: "Sector Concentration",
};

function measureLabel(m: string): string {
  return MEASURE_LABELS[m] ?? m;
}

function fmtVal(v: number, measure: string): string {
  if (
    measure === "return" ||
    measure === "volatility" ||
    measure === "sector_concentration"
  ) {
    return `${(v * 100).toFixed(2)}%`;
  }
  if (measure === "sharpe") return v.toFixed(3);
  if (measure === "diversification_hhi") return v.toFixed(4);
  return v.toFixed(4);
}

// ── SVG scatter chart (no external chart lib needed) ─────────────────────────

interface ScatterChartProps {
  points: FrontierPoint[];
  xMeasure: string;
  yMeasure: string;
  kneeIdx?: number | null;
  maxSharpeIdx?: number | null;
  minRiskIdx?: number | null;
}

function ScatterChart({
  points,
  xMeasure,
  yMeasure,
  kneeIdx,
  maxSharpeIdx,
  minRiskIdx,
}: ScatterChartProps) {
  const W = 480;
  const H = 300;
  const PAD = { top: 20, right: 20, bottom: 48, left: 56 };

  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const yMin = Math.min(...ys);
  const yMax = Math.max(...ys);

  const xRange = xMax - xMin || 1;
  const yRange = yMax - yMin || 1;

  const toSvgX = (v: number) =>
    PAD.left + ((v - xMin) / xRange) * (W - PAD.left - PAD.right);
  const toSvgY = (v: number) =>
    H - PAD.bottom - ((v - yMin) / yRange) * (H - PAD.top - PAD.bottom);

  // Axis tick helpers
  const xTicks = useMemo(() => {
    const n = 5;
    return Array.from({ length: n }, (_, i) => xMin + (xRange * i) / (n - 1));
  }, [xMin, xRange]);

  const yTicks = useMemo(() => {
    const n = 5;
    return Array.from({ length: n }, (_, i) => yMin + (yRange * i) / (n - 1));
  }, [yMin, yRange]);

  // Pre-compute dominant points path for the frontier line
  const frontierPath = useMemo(() => {
    const dominant = points
      .filter((p) => p.is_dominant)
      .sort((a, b) => a.x - b.x);
    if (dominant.length < 2) return null;
    return dominant
      .map((p, i) => `${i === 0 ? "M" : "L"}${toSvgX(p.x)},${toSvgY(p.y)}`)
      .join(" ");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [points, xMin, xRange, yMin, yRange]);

  return (
    <div className="w-full overflow-x-auto">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full max-w-[480px] mx-auto"
        aria-label={`Efficient frontier: ${measureLabel(xMeasure)} vs ${measureLabel(yMeasure)}`}
        role="img"
      >
        {/* Grid lines */}
        {yTicks.map((t, i) => (
          <line
            key={`ygrid-${i}`}
            x1={PAD.left}
            x2={W - PAD.right}
            y1={toSvgY(t)}
            y2={toSvgY(t)}
            stroke="currentColor"
            strokeOpacity={0.08}
            strokeWidth={1}
            aria-hidden="true"
          />
        ))}
        {xTicks.map((t, i) => (
          <line
            key={`xgrid-${i}`}
            x1={toSvgX(t)}
            x2={toSvgX(t)}
            y1={PAD.top}
            y2={H - PAD.bottom}
            stroke="currentColor"
            strokeOpacity={0.08}
            strokeWidth={1}
            aria-hidden="true"
          />
        ))}

        {/* Frontier line (dominant points only, sorted by x) */}
        {frontierPath && (
          <path
            d={frontierPath}
            fill="none"
            stroke="hsl(var(--primary))"
            strokeWidth={2}
            strokeOpacity={0.6}
            aria-label="Efficient frontier curve"
          />
        )}

        {/* All points */}
        {points.map((p, i) => {
          const cx = toSvgX(p.x);
          const cy = toSvgY(p.y);
          const isKnee = i === kneeIdx;
          const isMaxSharpe = i === maxSharpeIdx;
          const isMinRisk = i === minRiskIdx;

          if (isKnee) {
            // Star shape for knee
            return (
              <g key={`pt-${i}`} aria-label={`Knee point: ${fmtVal(p.x, xMeasure)}, ${fmtVal(p.y, yMeasure)}`}>
                <circle
                  cx={cx}
                  cy={cy}
                  r={10}
                  fill="hsl(var(--primary))"
                  fillOpacity={0.15}
                />
                <text
                  x={cx}
                  y={cy + 5}
                  textAnchor="middle"
                  fontSize={12}
                  fill="hsl(var(--primary))"
                  aria-hidden="true"
                >
                  ★
                </text>
              </g>
            );
          }
          if (isMaxSharpe) {
            return (
              <g key={`pt-${i}`} aria-label={`Max Sharpe point: ${fmtVal(p.x, xMeasure)}, ${fmtVal(p.y, yMeasure)}`}>
                <circle
                  cx={cx}
                  cy={cy}
                  r={8}
                  fill="hsl(142 76% 36%)"
                  fillOpacity={0.2}
                />
                <circle cx={cx} cy={cy} r={4} fill="hsl(142 76% 36%)" />
              </g>
            );
          }
          if (isMinRisk) {
            return (
              <g key={`pt-${i}`} aria-label={`Min risk point: ${fmtVal(p.x, xMeasure)}, ${fmtVal(p.y, yMeasure)}`}>
                <circle
                  cx={cx}
                  cy={cy}
                  r={8}
                  fill="hsl(217 91% 60%)"
                  fillOpacity={0.2}
                />
                <circle cx={cx} cy={cy} r={4} fill="hsl(217 91% 60%)" />
              </g>
            );
          }

          return (
            <circle
              key={`pt-${i}`}
              cx={cx}
              cy={cy}
              r={p.is_dominant ? 4 : 3}
              fill={
                p.is_dominant
                  ? "hsl(var(--primary))"
                  : "hsl(var(--muted-foreground))"
              }
              fillOpacity={p.is_dominant ? 0.8 : 0.35}
              aria-hidden="true"
            />
          );
        })}

        {/* X axis ticks + labels */}
        {xTicks.map((t, i) => (
          <g key={`xtick-${i}`} aria-hidden="true">
            <line
              x1={toSvgX(t)}
              x2={toSvgX(t)}
              y1={H - PAD.bottom}
              y2={H - PAD.bottom + 4}
              stroke="currentColor"
              strokeOpacity={0.4}
            />
            <text
              x={toSvgX(t)}
              y={H - PAD.bottom + 14}
              textAnchor="middle"
              fontSize={9}
              fill="currentColor"
              fillOpacity={0.6}
            >
              {fmtVal(t, xMeasure)}
            </text>
          </g>
        ))}

        {/* Y axis ticks + labels */}
        {yTicks.map((t, i) => (
          <g key={`ytick-${i}`} aria-hidden="true">
            <line
              x1={PAD.left - 4}
              x2={PAD.left}
              y1={toSvgY(t)}
              y2={toSvgY(t)}
              stroke="currentColor"
              strokeOpacity={0.4}
            />
            <text
              x={PAD.left - 6}
              y={toSvgY(t) + 3}
              textAnchor="end"
              fontSize={9}
              fill="currentColor"
              fillOpacity={0.6}
            >
              {fmtVal(t, yMeasure)}
            </text>
          </g>
        ))}

        {/* Axis labels */}
        <text
          x={(PAD.left + W - PAD.right) / 2}
          y={H - 4}
          textAnchor="middle"
          fontSize={10}
          fill="currentColor"
          fillOpacity={0.7}
          aria-hidden="true"
        >
          {measureLabel(xMeasure)}
        </text>
        <text
          x={12}
          y={(PAD.top + H - PAD.bottom) / 2}
          textAnchor="middle"
          fontSize={10}
          fill="currentColor"
          fillOpacity={0.7}
          transform={`rotate(-90, 12, ${(PAD.top + H - PAD.bottom) / 2})`}
          aria-hidden="true"
        >
          {measureLabel(yMeasure)}
        </text>
      </svg>

      {/* Legend */}
      <div
        className="flex flex-wrap items-center justify-center gap-4 mt-2 text-xs text-muted-foreground"
        aria-label="Chart legend"
      >
        <span className="flex items-center gap-1">
          <span className="text-primary text-sm" aria-hidden="true">★</span>
          Knee (recommended)
        </span>
        <span className="flex items-center gap-1">
          <span
            className="inline-block w-3 h-3 rounded-full bg-emerald-500 opacity-80"
            aria-hidden="true"
          />
          Max Sharpe
        </span>
        <span className="flex items-center gap-1">
          <span
            className="inline-block w-3 h-3 rounded-full bg-blue-500 opacity-80"
            aria-hidden="true"
          />
          Min Risk
        </span>
        <span className="flex items-center gap-1">
          <span
            className="inline-block w-3 h-3 rounded-full bg-primary opacity-80"
            aria-hidden="true"
          />
          Dominant
        </span>
        <span className="flex items-center gap-1">
          <span
            className="inline-block w-3 h-3 rounded-full bg-muted-foreground opacity-40"
            aria-hidden="true"
          />
          Dominated
        </span>
      </div>
    </div>
  );
}

// ── Knee portfolio allocation table ──────────────────────────────────────────

function KneePortfolioTable({
  point,
  xMeasure,
  yMeasure,
}: {
  point: FrontierPoint;
  xMeasure: string;
  yMeasure: string;
}) {
  const sorted = [...point.weights].sort((a, b) => b.weight - a.weight);
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-3 text-center">
        <div className="rounded-md bg-muted/40 p-2">
          <p className="text-xs text-muted-foreground">{measureLabel(xMeasure)}</p>
          <p className="text-sm font-semibold tabular-nums">
            {fmtVal(point.x, xMeasure)}
          </p>
        </div>
        <div className="rounded-md bg-muted/40 p-2">
          <p className="text-xs text-muted-foreground">{measureLabel(yMeasure)}</p>
          <p className="text-sm font-semibold tabular-nums">
            {fmtVal(point.y, yMeasure)}
          </p>
        </div>
        <div className="rounded-md bg-muted/40 p-2">
          <p className="text-xs text-muted-foreground">Sharpe</p>
          <p className="text-sm font-semibold tabular-nums">
            {point.sharpe.toFixed(3)}
          </p>
        </div>
      </div>

      <table className="w-full text-xs" aria-label="Knee portfolio asset weights">
        <thead>
          <tr className="border-b text-muted-foreground">
            <th className="py-1 text-left font-medium" scope="col">Ticker</th>
            <th className="py-1 text-right font-medium" scope="col">Weight</th>
            <th className="py-1 text-right font-medium" scope="col">Allocation</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((w) => (
            <tr key={w.ticker} className="border-b border-muted/40">
              <td className="py-1 font-mono font-semibold">{w.ticker}</td>
              <td className="py-1 text-right tabular-nums">
                {(w.weight * 100).toFixed(1)}%
              </td>
              <td className="py-1 text-right tabular-nums text-muted-foreground">
                ${w.allocation.toLocaleString("en-US", { maximumFractionDigits: 0 })}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

interface FrontierReportViewerProps {
  report: FrontierReport;
}

export function FrontierReportViewer({ report }: FrontierReportViewerProps) {
  const kneePoint =
    report.knee_point_index != null
      ? report.points[report.knee_point_index]
      : null;

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <TrendingUp className="h-5 w-5 text-emerald-500" aria-hidden="true" />
          <CardTitle className="text-base">Efficient Frontier</CardTitle>
        </div>
        <CardDescription>
          {measureLabel(report.x_measure)} vs {measureLabel(report.y_measure)} —{" "}
          {report.num_dominant} Pareto-dominant portfolios traced
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-5">
        {/* Scatter chart */}
        <ScatterChart
          points={report.points}
          xMeasure={report.x_measure}
          yMeasure={report.y_measure}
          kneeIdx={report.knee_point_index}
          maxSharpeIdx={report.max_sharpe_index}
          minRiskIdx={report.min_risk_index}
        />

        <Separator />

        {/* Summary stats */}
        <div
          className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center"
          aria-label="Frontier summary statistics"
        >
          <div className="rounded-md bg-muted/40 p-2">
            <p className="text-xs text-muted-foreground">Total Points</p>
            <p className="text-sm font-semibold">{report.points.length}</p>
          </div>
          <div className="rounded-md bg-muted/40 p-2">
            <p className="text-xs text-muted-foreground">Dominant</p>
            <p className="text-sm font-semibold text-emerald-600">
              {report.num_dominant}
            </p>
          </div>
          <div className="rounded-md bg-muted/40 p-2">
            <p className="text-xs text-muted-foreground">Dominated</p>
            <p className="text-sm font-semibold text-muted-foreground">
              {report.num_dominated}
            </p>
          </div>
          <div className="rounded-md bg-muted/40 p-2 flex items-center justify-center gap-1">
            <Clock className="h-3 w-3 text-muted-foreground" aria-hidden="true" />
            <p className="text-sm font-semibold tabular-nums">
              {(report.solve_time_ms / 1000).toFixed(1)}s
            </p>
          </div>
        </div>

        {/* Knee portfolio */}
        {kneePoint && (
          <>
            <Separator />
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Star className="h-4 w-4 text-primary" aria-hidden="true" />
                <h4 className="text-sm font-semibold">
                  Recommended Portfolio (Knee Point)
                </h4>
                <Badge variant="outline" className="text-xs">
                  {report.x_direction === "minimize" ? "Low Risk" : "High Return"}
                </Badge>
              </div>
              <KneePortfolioTable
                point={kneePoint}
                xMeasure={report.x_measure}
                yMeasure={report.y_measure}
              />
            </div>
          </>
        )}

        {/* LLM commentary */}
        {report.commentary && (
          <>
            <Separator />
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <MessageSquare className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                <h4 className="text-sm font-semibold">AI Commentary</h4>
              </div>
              <p className="text-sm text-muted-foreground leading-relaxed whitespace-pre-wrap">
                {report.commentary}
              </p>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
