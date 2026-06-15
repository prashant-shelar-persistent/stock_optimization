/**
 * ComparisonDashboard — Full results comparison panel for the Portfolio Optimizer.
 *
 * Displays the complete optimization results side-by-side across Classical,
 * QAOA, and VQE strategies. This is the primary results view shown after an
 * optimization run completes.
 *
 * Layout:
 *   ┌──────────────────────────────────────────────────────────────┐
 *   │  Comparison Summary (recommendation + Sharpe deltas)         │
 *   ├──────────────────────────────────────────────────────────────┤
 *   │  Tabs: Classical | QAOA | VQE                                │
 *   │  ┌──────────────────────┬──────────────────────────────────┐ │
 *   │  │  AllocationChart     │  Metrics Table                   │ │
 *   │  │  (pie chart)         │  (Return, Volatility, Sharpe,    │ │
 *   │  │                      │   Assets, Solve Time)            │ │
 *   │  └──────────────────────┴──────────────────────────────────┘ │
 *   ├──────────────────────────────────────────────────────────────┤
 *   │  MetricsChart (all strategies side-by-side bar charts)       │
 *   ├──────────────────────────────────────────────────────────────┤
 *   │  LLM Explanation (collapsible, GPT-4o generated)             │
 *   └──────────────────────────────────────────────────────────────┘
 *
 * Props:
 *   result — OptimizationRunDetail from the completed optimization run
 *
 * Usage:
 *   <ComparisonDashboard result={optimizationResult} />
 */

import { useState } from "react";
import {
  TrendingUp,
  TrendingDown,
  Award,
  Clock,
  Layers,
  Cpu,
  ChevronDown,
  ChevronUp,
  Sparkles,
  MessageSquare,
  Zap,
} from "lucide-react";
import {
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from "@/components/ui/tabs";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
  TooltipProvider,
} from "@/components/ui/tooltip";
import { AllocationChart } from "@/components/AllocationChart";
import { MetricsChart } from "@/components/MetricsChart";
import { cn, formatPercent, formatNumber, formatCurrency } from "@/lib/utils";
import type {
  OptimizationRunDetail,
  PortfolioMetrics,
  ComparisonSummary,
} from "@/types/api";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface ComparisonDashboardProps {
  result: OptimizationRunDetail;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Format solve time from milliseconds to a human-readable string. */
function formatSolveTime(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(2)} s`;
  return `${(ms / 60_000).toFixed(1)} min`;
}

/** Format a delta value with sign prefix and color class. */
function getDeltaClass(delta: number, higherIsBetter: boolean): string {
  const isGood = higherIsBetter ? delta > 0 : delta < 0;
  if (delta === 0) return "text-muted-foreground";
  return isGood
    ? "text-green-600 dark:text-green-400"
    : "text-red-500 dark:text-red-400";
}

// ── Comparison Summary Card ───────────────────────────────────────────────────

interface ComparisonSummaryCardProps {
  comparison: ComparisonSummary;
  classicalSharpe: number;
  qaoaSharpe?: number;
  vqeSharpe?: number;
}

function ComparisonSummaryCard({
  comparison,
  classicalSharpe,
  qaoaSharpe,
  vqeSharpe,
}: ComparisonSummaryCardProps) {
  const hasQuantum = qaoaSharpe !== undefined || vqeSharpe !== undefined;

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <Award className="h-4 w-4 text-primary" />
          <CardTitle className="text-base">Optimization Summary</CardTitle>
        </div>
        {hasQuantum && (
          <CardDescription>
            Comparing Classical (Markowitz MVO) vs Quantum (QAOA + VQE)
          </CardDescription>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Recommendation banner */}
        <div className="flex items-start gap-3 rounded-lg border border-primary/30 bg-primary/5 px-4 py-3">
          <Award className="mt-0.5 h-4 w-4 flex-shrink-0 text-primary" />
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-primary">
              Recommendation
            </p>
            <p className="mt-0.5 text-sm text-foreground/90">
              {comparison.recommendation}
            </p>
          </div>
        </div>

        {/* Sharpe ratio comparison */}
        {hasQuantum && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {/* Classical */}
            <div className="rounded-md border bg-muted/30 px-3 py-2.5">
              <div className="flex items-center gap-1.5 mb-1">
                <span className="h-2 w-2 rounded-full bg-blue-500" />
                <p className="text-xs font-medium text-muted-foreground">
                  Classical Sharpe
                </p>
              </div>
              <p className="text-xl font-bold tabular-nums text-blue-600 dark:text-blue-400">
                {formatNumber(classicalSharpe, 3)}
              </p>
            </div>

            {/* QAOA */}
            {qaoaSharpe !== undefined && (
              <div className="rounded-md border bg-muted/30 px-3 py-2.5">
                <div className="flex items-center gap-1.5 mb-1">
                  <span className="h-2 w-2 rounded-full bg-violet-500" />
                  <p className="text-xs font-medium text-muted-foreground">
                    QAOA Sharpe
                  </p>
                </div>
                <div className="flex items-baseline gap-2">
                  <p className="text-xl font-bold tabular-nums text-violet-600 dark:text-violet-400">
                    {formatNumber(qaoaSharpe, 3)}
                  </p>
                  {comparison.sharpe_improvement_qaoa !== undefined && (
                    <span
                      className={cn(
                        "text-xs font-medium tabular-nums",
                        getDeltaClass(comparison.sharpe_improvement_qaoa, true),
                      )}
                    >
                      {comparison.sharpe_improvement_qaoa >= 0 ? "+" : ""}
                      {formatNumber(comparison.sharpe_improvement_qaoa, 3)}
                    </span>
                  )}
                </div>
              </div>
            )}

            {/* VQE */}
            {vqeSharpe !== undefined && (
              <div className="rounded-md border bg-muted/30 px-3 py-2.5">
                <div className="flex items-center gap-1.5 mb-1">
                  <span className="h-2 w-2 rounded-full bg-purple-500" />
                  <p className="text-xs font-medium text-muted-foreground">
                    VQE Sharpe
                  </p>
                </div>
                <div className="flex items-baseline gap-2">
                  <p className="text-xl font-bold tabular-nums text-purple-600 dark:text-purple-400">
                    {formatNumber(vqeSharpe, 3)}
                  </p>
                  {comparison.sharpe_improvement_vqe !== undefined && (
                    <span
                      className={cn(
                        "text-xs font-medium tabular-nums",
                        getDeltaClass(comparison.sharpe_improvement_vqe, true),
                      )}
                    >
                      {comparison.sharpe_improvement_vqe >= 0 ? "+" : ""}
                      {formatNumber(comparison.sharpe_improvement_vqe, 3)}
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Improvement deltas grid */}
        {hasQuantum && (
          <div className="space-y-2">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              vs Classical Baseline
            </p>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {/* QAOA deltas */}
              {qaoaSharpe !== undefined && (
                <div className="space-y-1.5 rounded-md border bg-muted/20 px-3 py-2">
                  <p className="text-xs font-semibold text-violet-600 dark:text-violet-400">
                    QAOA
                  </p>
                  <ImprovementRow
                    label="Return"
                    delta={comparison.return_diff_qaoa}
                    format="percent"
                    higherIsBetter
                  />
                  <ImprovementRow
                    label="Volatility"
                    delta={comparison.volatility_diff_qaoa}
                    format="percent"
                    higherIsBetter={false}
                  />
                  <ImprovementRow
                    label="Sharpe"
                    delta={comparison.sharpe_improvement_qaoa}
                    format="ratio"
                    higherIsBetter
                  />
                </div>
              )}

              {/* VQE deltas */}
              {vqeSharpe !== undefined && (
                <div className="space-y-1.5 rounded-md border bg-muted/20 px-3 py-2">
                  <p className="text-xs font-semibold text-purple-600 dark:text-purple-400">
                    VQE
                  </p>
                  <ImprovementRow
                    label="Return"
                    delta={comparison.return_diff_vqe}
                    format="percent"
                    higherIsBetter
                  />
                  <ImprovementRow
                    label="Volatility"
                    delta={comparison.volatility_diff_vqe}
                    format="percent"
                    higherIsBetter={false}
                  />
                  <ImprovementRow
                    label="Sharpe"
                    delta={comparison.sharpe_improvement_vqe}
                    format="ratio"
                    higherIsBetter
                  />
                </div>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ── Improvement row ───────────────────────────────────────────────────────────

function ImprovementRow({
  label,
  delta,
  format = "ratio",
  higherIsBetter,
}: {
  label: string;
  delta: number | undefined;
  format?: "percent" | "ratio";
  higherIsBetter: boolean;
}) {
  if (delta === undefined) return null;

  const isPositive = delta > 0;
  const isGood = higherIsBetter ? isPositive : !isPositive;
  const formattedDelta =
    format === "percent"
      ? `${delta >= 0 ? "+" : ""}${formatPercent(delta)}`
      : `${delta >= 0 ? "+" : ""}${formatNumber(delta, 3)}`;

  return (
    <div className="flex items-center justify-between text-xs">
      <span className="text-muted-foreground">{label}</span>
      <div className="flex items-center gap-1">
        {isGood ? (
          <TrendingUp className="h-3 w-3 text-green-500" />
        ) : (
          <TrendingDown className="h-3 w-3 text-red-500" />
        )}
        <span
          className={cn(
            "font-medium tabular-nums",
            isGood
              ? "text-green-600 dark:text-green-400"
              : "text-red-500 dark:text-red-400",
          )}
        >
          {formattedDelta}
        </span>
      </div>
    </div>
  );
}

// ── Metrics table ─────────────────────────────────────────────────────────────

interface MetricsTableProps {
  metrics: PortfolioMetrics;
  solveTimeMs?: number;
  classicalMetrics?: PortfolioMetrics;
}

function MetricsTable({
  metrics,
  solveTimeMs,
  classicalMetrics,
}: MetricsTableProps) {
  const rows: Array<{
    label: string;
    value: string;
    delta?: number;
    higherIsBetter?: boolean;
    deltaFormat?: "percent" | "ratio";
  }> = [
    {
      label: "Expected Return",
      value: formatPercent(metrics.expected_return),
      delta: classicalMetrics
        ? metrics.expected_return - classicalMetrics.expected_return
        : undefined,
      higherIsBetter: true,
      deltaFormat: "percent",
    },
    {
      label: "Volatility",
      value: formatPercent(metrics.volatility),
      delta: classicalMetrics
        ? metrics.volatility - classicalMetrics.volatility
        : undefined,
      higherIsBetter: false,
      deltaFormat: "percent",
    },
    {
      label: "Sharpe Ratio",
      value: formatNumber(metrics.sharpe_ratio, 3),
      delta: classicalMetrics
        ? metrics.sharpe_ratio - classicalMetrics.sharpe_ratio
        : undefined,
      higherIsBetter: true,
      deltaFormat: "ratio",
    },
    {
      label: "Assets Selected",
      value: String(metrics.num_assets),
    },
    ...(metrics.max_drawdown !== undefined
      ? [
          {
            label: "Max Drawdown",
            value: formatPercent(metrics.max_drawdown),
            delta: classicalMetrics?.max_drawdown !== undefined
              ? metrics.max_drawdown - classicalMetrics.max_drawdown
              : undefined,
            higherIsBetter: false,
            deltaFormat: "percent" as const,
          },
        ]
      : []),
    ...(solveTimeMs !== undefined
      ? [{ label: "Solve Time", value: formatSolveTime(solveTimeMs) }]
      : []),
  ];

  return (
    <div className="overflow-hidden rounded-md border">
      <table className="w-full text-sm">
        <tbody>
          {rows.map((row, idx) => (
            <tr
              key={row.label}
              className={cn(
                "border-b last:border-b-0",
                idx % 2 === 0 ? "bg-muted/20" : "bg-background",
              )}
            >
              <td className="px-3 py-2 text-muted-foreground">{row.label}</td>
              <td className="px-3 py-2 text-right font-medium tabular-nums">
                {row.value}
              </td>
              {row.delta !== undefined && row.higherIsBetter !== undefined && (
                <td className="px-3 py-2 text-right">
                  <span
                    className={cn(
                      "text-xs font-medium tabular-nums",
                      getDeltaClass(row.delta, row.higherIsBetter),
                    )}
                  >
                    {row.delta >= 0 ? "+" : ""}
                    {row.deltaFormat === "percent"
                      ? formatPercent(row.delta)
                      : formatNumber(row.delta, 3)}
                  </span>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Quantum circuit info ──────────────────────────────────────────────────────

interface QuantumInfoProps {
  type: "qaoa" | "vqe";
  numQubits: number;
  circuitDepth?: number;
  solveTimeMs: number;
  selectedAssets: string[];
}

function QuantumInfo({
  type,
  numQubits,
  circuitDepth,
  solveTimeMs,
  selectedAssets,
}: QuantumInfoProps) {
  const label = type === "qaoa" ? "QAOA" : "VQE";
  const framework = type === "qaoa" ? "Qiskit" : "PennyLane";

  return (
    <div className="rounded-lg border bg-muted/30 p-3 space-y-2.5">
      <div className="flex items-center gap-2">
        <Zap className="h-3.5 w-3.5 text-violet-500" />
        <span className="text-xs font-semibold">{label} Circuit Info</span>
        <Badge variant="outline" className="ml-auto text-xs">
          {framework}
        </Badge>
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <div className="flex items-center gap-1.5">
          <Cpu className="h-3 w-3 text-muted-foreground flex-shrink-0" />
          <div>
            <p className="text-xs text-muted-foreground">Qubits</p>
            <p className="text-sm font-semibold tabular-nums">{numQubits}</p>
          </div>
        </div>

        {circuitDepth !== undefined && (
          <div className="flex items-center gap-1.5">
            <Layers className="h-3 w-3 text-muted-foreground flex-shrink-0" />
            <div>
              <p className="text-xs text-muted-foreground">Depth</p>
              <p className="text-sm font-semibold tabular-nums">{circuitDepth}</p>
            </div>
          </div>
        )}

        <div className="flex items-center gap-1.5">
          <Clock className="h-3 w-3 text-muted-foreground flex-shrink-0" />
          <div>
            <p className="text-xs text-muted-foreground">Solve Time</p>
            <p className="text-sm font-semibold tabular-nums">
              {formatSolveTime(solveTimeMs)}
            </p>
          </div>
        </div>
      </div>

      {selectedAssets.length > 0 && (
        <div>
          <p className="mb-1 text-xs text-muted-foreground">
            Selected Assets ({selectedAssets.length})
          </p>
          <div className="flex flex-wrap gap-1">
            {selectedAssets.map((ticker) => (
              <Badge
                key={ticker}
                variant="outline"
                className="font-mono text-xs"
              >
                {ticker}
              </Badge>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Classical tab content ─────────────────────────────────────────────────────

function ClassicalTabContent({ result }: { result: OptimizationRunDetail }) {
  const { classical_result } = result;
  if (!classical_result) return null;

  const { weights, metrics, solver_status, solve_time_ms } = classical_result;

  return (
    <div className="space-y-4">
      {/* Solver info */}
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span>Solver: CVXPY (Markowitz MVO)</span>
        <span>•</span>
        <Badge
          variant={
            solver_status === "optimal" || solver_status === "optimal_inaccurate"
              ? "success"
              : "warning"
          }
          className="text-xs"
        >
          {solver_status}
        </Badge>
        <span>•</span>
        <span>Solved in {formatSolveTime(solve_time_ms)}</span>
      </div>

      {/* Allocation chart + metrics table */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div>
          <p className="mb-2 text-sm font-medium">Portfolio Allocation</p>
          <AllocationChart
            weights={weights}
            colorScheme="classical"
          />
        </div>
        <div>
          <p className="mb-2 text-sm font-medium">Performance Metrics</p>
          <MetricsTable
            metrics={metrics}
            solveTimeMs={solve_time_ms}
          />
        </div>
      </div>
    </div>
  );
}

// ── QAOA tab content ──────────────────────────────────────────────────────────

function QAOATabContent({ result }: { result: OptimizationRunDetail }) {
  const qaoa = result.quantum_result?.qaoa;
  const classical = result.classical_result;

  if (!qaoa) {
    return (
      <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
        QAOA results not available
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Circuit info */}
      <QuantumInfo
        type="qaoa"
        numQubits={qaoa.num_qubits}
        circuitDepth={qaoa.circuit_depth}
        solveTimeMs={qaoa.solve_time_ms}
        selectedAssets={qaoa.selected_assets}
      />

      {/* Allocation chart + metrics table */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div>
          <p className="mb-2 text-sm font-medium">Portfolio Allocation</p>
          <AllocationChart
            weights={qaoa.weights}
            colorScheme="quantum"
          />
        </div>
        <div>
          <p className="mb-2 text-sm font-medium">Performance Metrics</p>
          <MetricsTable
            metrics={qaoa.metrics}
            solveTimeMs={qaoa.solve_time_ms}
            classicalMetrics={classical?.metrics}
          />
        </div>
      </div>
    </div>
  );
}

// ── VQE tab content ───────────────────────────────────────────────────────────

function VQETabContent({ result }: { result: OptimizationRunDetail }) {
  const vqe = result.quantum_result?.vqe;
  const classical = result.classical_result;

  if (!vqe) {
    return (
      <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
        VQE results not available
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Circuit info */}
      <QuantumInfo
        type="vqe"
        numQubits={vqe.num_qubits}
        solveTimeMs={vqe.solve_time_ms}
        selectedAssets={vqe.selected_assets}
      />

      {/* Allocation chart + metrics table */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div>
          <p className="mb-2 text-sm font-medium">Portfolio Allocation</p>
          <AllocationChart
            weights={vqe.weights}
            colorScheme="quantum"
          />
        </div>
        <div>
          <p className="mb-2 text-sm font-medium">Performance Metrics</p>
          <MetricsTable
            metrics={vqe.metrics}
            solveTimeMs={vqe.solve_time_ms}
            classicalMetrics={classical?.metrics}
          />
        </div>
      </div>
    </div>
  );
}

// ── LLM Explanation Panel ─────────────────────────────────────────────────────

interface LLMPanelProps {
  explanation: string | null | undefined;
  isLoading?: boolean;
}

/**
 * Lightweight markdown-like renderer.
 * Handles: **bold**, *italic*, paragraph breaks, and bullet points.
 */
function renderExplanation(text: string): React.ReactNode {
  const paragraphs = text.split(/\n\n+/);

  return paragraphs.map((para, pIdx) => {
    // Bullet list paragraph
    if (para.trim().startsWith("- ") || para.trim().startsWith("• ")) {
      const items = para
        .split("\n")
        .filter(
          (line) =>
            line.trim().startsWith("- ") || line.trim().startsWith("• "),
        );
      return (
        <ul key={pIdx} className="my-2 ml-4 list-disc space-y-1">
          {items.map((item, iIdx) => (
            <li key={iIdx} className="text-sm leading-relaxed">
              {renderInline(item.replace(/^[-•]\s+/, ""))}
            </li>
          ))}
        </ul>
      );
    }

    return (
      <p key={pIdx} className="text-sm leading-relaxed">
        {renderInline(para)}
      </p>
    );
  });
}

function renderInline(text: string): React.ReactNode {
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g);
  return parts.map((part, idx) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={idx} className="font-semibold text-foreground">
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith("*") && part.endsWith("*")) {
      return (
        <em key={idx} className="italic">
          {part.slice(1, -1)}
        </em>
      );
    }
    return part;
  });
}

function LLMPanel({ explanation, isLoading = false }: LLMPanelProps) {
  const [isExpanded, setIsExpanded] = useState(true);
  const hasContent = Boolean(explanation);

  return (
    <Card>
      <CardHeader className="pb-0">
        <div className="flex items-center gap-2">
          <div className="flex flex-1 items-center gap-2">
            <Sparkles className="h-4 w-4 text-violet-500" />
            <CardTitle className="text-base">AI Portfolio Explanation</CardTitle>
            <span className="rounded-full bg-violet-100 px-2 py-0.5 text-xs font-medium text-violet-700 dark:bg-violet-900/30 dark:text-violet-400">
              GPT-4o
            </span>
          </div>
          {hasContent && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 w-7 p-0"
              onClick={() => setIsExpanded((prev) => !prev)}
              aria-label={isExpanded ? "Collapse explanation" : "Expand explanation"}
            >
              {isExpanded ? (
                <ChevronUp className="h-4 w-4" />
              ) : (
                <ChevronDown className="h-4 w-4" />
              )}
            </Button>
          )}
        </div>
      </CardHeader>

      <Separator className="mt-3" />

      <div
        className={cn(
          "overflow-hidden transition-all duration-300",
          isExpanded ? "max-h-[600px]" : "max-h-0",
        )}
      >
        <CardContent className="pt-4">
          {isLoading && !hasContent && (
            <div className="space-y-2 animate-pulse">
              {[100, 92, 85, 100, 78].map((w, i) => (
                <div
                  key={i}
                  className="h-4 rounded bg-muted"
                  style={{ width: `${w}%` }}
                />
              ))}
            </div>
          )}

          {!isLoading && !hasContent && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <MessageSquare className="h-4 w-4" />
              <span>
                Explanation will appear here once the optimization completes.
              </span>
            </div>
          )}

          {hasContent && (
            <ScrollArea className="max-h-[500px]">
              <div className="prose-sm space-y-3 text-foreground/90 pr-4">
                {renderExplanation(explanation!)}
              </div>
            </ScrollArea>
          )}
        </CardContent>
      </div>
    </Card>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

/**
 * ComparisonDashboard renders the full optimization results comparison view.
 *
 * Shows:
 *   1. Comparison summary with recommendation and Sharpe improvement deltas
 *   2. Tabbed view (Classical | QAOA | VQE) with allocation charts and metrics
 *   3. Side-by-side MetricsChart for all available strategies
 *   4. Collapsible LLM explanation panel
 *
 * QAOA and VQE tabs are disabled with a tooltip when quantum results are absent.
 */
export function ComparisonDashboard({ result }: ComparisonDashboardProps) {
  const [activeTab, setActiveTab] = useState<"classical" | "qaoa" | "vqe">(
    "classical",
  );

  const { classical_result, quantum_result, comparison, llm_explanation } =
    result;

  const hasQaoa = Boolean(quantum_result?.qaoa);
  const hasVqe = Boolean(quantum_result?.vqe);
  const hasQuantum = hasQaoa || hasVqe;

  const classicalSharpe = classical_result?.metrics.sharpe_ratio;
  const qaoaSharpe = quantum_result?.qaoa?.metrics.sharpe_ratio;
  const vqeSharpe = quantum_result?.vqe?.metrics.sharpe_ratio;

  // Determine if the run has any results to show
  if (!classical_result) {
    return (
      <div className="flex h-48 items-center justify-center rounded-lg border border-dashed bg-muted/20 text-sm text-muted-foreground">
        No optimization results available
      </div>
    );
  }

  return (
    <TooltipProvider>
      <div className="space-y-6">
        {/* ── Run metadata ── */}
        <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
          <span>
            Budget:{" "}
            <span className="font-medium text-foreground">
              {formatCurrency(result.budget)}
            </span>
          </span>
          <span>•</span>
          <span>
            Assets:{" "}
            <span className="font-medium text-foreground">
              {result.tickers.join(", ")}
            </span>
          </span>
          {result.completed_at && (
            <>
              <span>•</span>
              <span>
                Completed:{" "}
                <span className="font-medium text-foreground">
                  {new Date(result.completed_at).toLocaleString([], {
                    month: "short",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
              </span>
            </>
          )}
        </div>

        {/* ── Comparison summary ── */}
        {comparison && classicalSharpe !== undefined && (
          <ComparisonSummaryCard
            comparison={comparison}
            classicalSharpe={classicalSharpe}
            qaoaSharpe={qaoaSharpe}
            vqeSharpe={vqeSharpe}
          />
        )}

        {/* ── Strategy tabs ── */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Strategy Details</CardTitle>
            <CardDescription>
              Allocation and performance metrics per optimization strategy
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Tabs
              value={activeTab}
              onValueChange={(v) =>
                setActiveTab(v as "classical" | "qaoa" | "vqe")
              }
            >
              <TabsList className="mb-4">
                {/* Classical tab — always enabled */}
                <TabsTrigger value="classical">
                  <span className="flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-full bg-blue-500" />
                    Classical
                  </span>
                </TabsTrigger>

                {/* QAOA tab — disabled when no quantum results */}
                {hasQaoa ? (
                  <TabsTrigger value="qaoa">
                    <span className="flex items-center gap-1.5">
                      <span className="h-2 w-2 rounded-full bg-violet-500" />
                      QAOA
                    </span>
                  </TabsTrigger>
                ) : (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span>
                        <TabsTrigger value="qaoa" disabled>
                          <span className="flex items-center gap-1.5 opacity-50">
                            <span className="h-2 w-2 rounded-full bg-violet-500" />
                            QAOA
                          </span>
                        </TabsTrigger>
                      </span>
                    </TooltipTrigger>
                    <TooltipContent side="bottom" className="text-xs">
                      Quantum optimization was not run
                    </TooltipContent>
                  </Tooltip>
                )}

                {/* VQE tab — disabled when no quantum results */}
                {hasVqe ? (
                  <TabsTrigger value="vqe">
                    <span className="flex items-center gap-1.5">
                      <span className="h-2 w-2 rounded-full bg-purple-500" />
                      VQE
                    </span>
                  </TabsTrigger>
                ) : (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span>
                        <TabsTrigger value="vqe" disabled>
                          <span className="flex items-center gap-1.5 opacity-50">
                            <span className="h-2 w-2 rounded-full bg-purple-500" />
                            VQE
                          </span>
                        </TabsTrigger>
                      </span>
                    </TooltipTrigger>
                    <TooltipContent side="bottom" className="text-xs">
                      Quantum optimization was not run
                    </TooltipContent>
                  </Tooltip>
                )}
              </TabsList>

              <TabsContent value="classical">
                <ClassicalTabContent result={result} />
              </TabsContent>

              <TabsContent value="qaoa">
                <QAOATabContent result={result} />
              </TabsContent>

              <TabsContent value="vqe">
                <VQETabContent result={result} />
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>

        {/* ── Side-by-side metrics comparison ── */}
        {hasQuantum && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Metrics Comparison</CardTitle>
              <CardDescription>
                All strategies compared across key performance metrics
              </CardDescription>
            </CardHeader>
            <CardContent>
              <MetricsChart
                classical={classical_result.metrics}
                qaoa={quantum_result?.qaoa?.metrics}
                vqe={quantum_result?.vqe?.metrics}
              />
            </CardContent>
          </Card>
        )}

        {/* ── LLM Explanation ── */}
        <LLMPanel explanation={llm_explanation} />
      </div>
    </TooltipProvider>
  );
}
