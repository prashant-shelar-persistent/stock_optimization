/**
 * ComparisonDashboard — Side-by-side comparison of Classical vs Quantum results.
 *
 * Layout:
 *   ┌─────────────────────────────────────────────────────────────┐
 *   │  Sharpe Ratio Comparison (horizontal bar chart)             │
 *   ├─────────────────────────────────────────────────────────────┤
 *   │  Tabs: Classical | QAOA | VQE                               │
 *   │  ┌──────────────────────┬──────────────────────────────┐    │
 *   │  │  Allocation Pie      │  Metrics Cards               │    │
 *   │  │  Chart               │  (Return, Volatility, Sharpe)│    │
 *   │  ├──────────────────────┴──────────────────────────────┤    │
 *   │  │  Weights Table                                       │    │
 *   │  └──────────────────────────────────────────────────────┘    │
 *   ├─────────────────────────────────────────────────────────────┤
 *   │  Full Metrics Comparison Bar Chart (all strategies)         │
 *   ├─────────────────────────────────────────────────────────────┤
 *   │  Comparison Summary (improvement deltas)                    │
 *   ├─────────────────────────────────────────────────────────────┤
 *   │  LLM Explanation Panel                                      │
 *   └─────────────────────────────────────────────────────────────┘
 *
 * Props:
 *   result — OptimizationRunDetail from the completed optimization
 */

import { useUIStore, selectActiveTab } from "@/store/uiStore";
import type { ComparisonTab } from "@/store/uiStore";
import type { OptimizationRunDetail } from "@/types/api";
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
import { Separator } from "@/components/ui/separator";
import { AllocationPieChart } from "@/components/charts/AllocationPieChart";
import { MetricsComparisonBar } from "@/components/charts/MetricsComparisonBar";
import { SharpeComparisonChart } from "@/components/charts/SharpeComparisonChart";
import { WeightsTable } from "@/components/charts/WeightsTable";
import { MetricsCard } from "@/components/charts/MetricsCard";
import { QuantumCircuitInfo } from "@/components/charts/QuantumCircuitInfo";
import { LLMExplanationPanel } from "@/components/dashboard/LLMExplanationPanel";
import {
  TrendingUp,
  TrendingDown,
  Award,
  AlertTriangle,
} from "lucide-react";
import { formatPercent, formatNumber, cn } from "@/lib/utils";

// ── Types ─────────────────────────────────────────────────────────────────────

interface ComparisonDashboardProps {
  result: OptimizationRunDetail;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function getSolverStatusBadge(status: string) {
  const isOk = status === "optimal" || status === "optimal_inaccurate";
  return (
    <Badge variant={isOk ? "success" : "warning"} className="text-xs">
      {status}
    </Badge>
  );
}

function formatSolveTime(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

// ── Recommendation banner ─────────────────────────────────────────────────────

function RecommendationBanner({ recommendation }: { recommendation: string }) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-primary/30 bg-primary/5 px-4 py-3">
      <Award className="mt-0.5 h-4 w-4 flex-shrink-0 text-primary" />
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-primary">
          Recommendation
        </p>
        <p className="mt-0.5 text-sm text-foreground/90">{recommendation}</p>
      </div>
    </div>
  );
}

// ── Improvement row helper ────────────────────────────────────────────────────

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
    <div className="flex items-center justify-between text-sm">
      <span className="text-muted-foreground">{label}</span>
      <div className="flex items-center gap-1">
        {isGood ? (
          <TrendingUp className="h-3.5 w-3.5 text-green-500" />
        ) : (
          <TrendingDown className="h-3.5 w-3.5 text-red-500" />
        )}
        <span
          className={cn(
            "font-medium tabular-nums",
            isGood ? "text-green-600 dark:text-green-400" : "text-red-500",
          )}
        >
          {formattedDelta}
        </span>
      </div>
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
      {/* Metrics cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MetricsCard
          label="Expected Return"
          value={metrics.expected_return}
          format="percent"
          description="Annualised expected portfolio return"
        />
        <MetricsCard
          label="Volatility"
          value={metrics.volatility}
          format="percent"
          description="Annualised portfolio volatility (standard deviation)"
        />
        <MetricsCard
          label="Sharpe Ratio"
          value={metrics.sharpe_ratio}
          format="ratio"
          description="Risk-adjusted return: (return − risk-free rate) / volatility"
          highlight
        />
        <MetricsCard
          label="Assets"
          value={metrics.num_assets}
          format="ratio"
          description="Number of assets with non-zero weight"
        />
      </div>

      {/* Max drawdown if available */}
      {metrics.max_drawdown !== undefined && (
        <div className="flex items-center gap-2 rounded-md border bg-muted/30 px-3 py-2">
          <TrendingDown className="h-4 w-4 text-red-500" />
          <span className="text-sm text-muted-foreground">Max Drawdown:</span>
          <span className="text-sm font-semibold text-red-500">
            {formatPercent(metrics.max_drawdown)}
          </span>
        </div>
      )}

      {/* Solver info */}
      <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
        <span>Solver: CVXPY (Markowitz MVO)</span>
        <span>•</span>
        {getSolverStatusBadge(solver_status)}
        <span>•</span>
        <span>Solved in {formatSolveTime(solve_time_ms)}</span>
      </div>

      <Separator />

      {/* Allocation chart + weights table */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div>
          <p className="mb-2 text-sm font-medium">Portfolio Allocation</p>
          <AllocationPieChart
            weights={weights}
            budget={result.budget}
            colorSet="classical"
          />
        </div>
        <div>
          <p className="mb-2 text-sm font-medium">Asset Weights</p>
          <WeightsTable
            weights={weights}
            budget={result.budget}
            colorScheme="classical"
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

  const classicalSharpe = classical?.metrics.sharpe_ratio;

  return (
    <div className="space-y-4">
      {/* Metrics cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MetricsCard
          label="Expected Return"
          value={qaoa.metrics.expected_return}
          format="percent"
          delta={
            classical
              ? qaoa.metrics.expected_return - classical.metrics.expected_return
              : undefined
          }
          description="Annualised expected portfolio return"
        />
        <MetricsCard
          label="Volatility"
          value={qaoa.metrics.volatility}
          format="percent"
          delta={
            classical
              ? qaoa.metrics.volatility - classical.metrics.volatility
              : undefined
          }
          description="Annualised portfolio volatility"
        />
        <MetricsCard
          label="Sharpe Ratio"
          value={qaoa.metrics.sharpe_ratio}
          format="ratio"
          delta={
            classicalSharpe !== undefined
              ? qaoa.metrics.sharpe_ratio - classicalSharpe
              : undefined
          }
          description="Risk-adjusted return"
          highlight
        />
        <MetricsCard
          label="Assets"
          value={qaoa.metrics.num_assets}
          format="ratio"
          description="Number of selected assets"
        />
      </div>

      {/* Circuit info */}
      <QuantumCircuitInfo
        type="qaoa"
        numQubits={qaoa.num_qubits}
        circuitDepth={qaoa.circuit_depth}
        solveTimeMs={qaoa.solve_time_ms}
        selectedAssets={qaoa.selected_assets}
      />

      <Separator />

      {/* Allocation chart + weights table */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div>
          <p className="mb-2 text-sm font-medium">Portfolio Allocation</p>
          <AllocationPieChart
            weights={qaoa.weights}
            budget={result.budget}
            colorSet="quantum"
          />
        </div>
        <div>
          <p className="mb-2 text-sm font-medium">Asset Weights</p>
          <WeightsTable
            weights={qaoa.weights}
            budget={result.budget}
            colorScheme="quantum"
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

  const classicalSharpe = classical?.metrics.sharpe_ratio;

  return (
    <div className="space-y-4">
      {/* Metrics cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MetricsCard
          label="Expected Return"
          value={vqe.metrics.expected_return}
          format="percent"
          delta={
            classical
              ? vqe.metrics.expected_return - classical.metrics.expected_return
              : undefined
          }
          description="Annualised expected portfolio return"
        />
        <MetricsCard
          label="Volatility"
          value={vqe.metrics.volatility}
          format="percent"
          delta={
            classical
              ? vqe.metrics.volatility - classical.metrics.volatility
              : undefined
          }
          description="Annualised portfolio volatility"
        />
        <MetricsCard
          label="Sharpe Ratio"
          value={vqe.metrics.sharpe_ratio}
          format="ratio"
          delta={
            classicalSharpe !== undefined
              ? vqe.metrics.sharpe_ratio - classicalSharpe
              : undefined
          }
          description="Risk-adjusted return"
          highlight
        />
        <MetricsCard
          label="Assets"
          value={vqe.metrics.num_assets}
          format="ratio"
          description="Number of selected assets"
        />
      </div>

      {/* Circuit info */}
      <QuantumCircuitInfo
        type="vqe"
        numQubits={vqe.num_qubits}
        solveTimeMs={vqe.solve_time_ms}
        selectedAssets={vqe.selected_assets}
      />

      <Separator />

      {/* Allocation chart + weights table */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div>
          <p className="mb-2 text-sm font-medium">Portfolio Allocation</p>
          <AllocationPieChart
            weights={vqe.weights}
            budget={result.budget}
            colorSet="quantum"
          />
        </div>
        <div>
          <p className="mb-2 text-sm font-medium">Asset Weights</p>
          <WeightsTable
            weights={vqe.weights}
            budget={result.budget}
            colorScheme="quantum"
          />
        </div>
      </div>
    </div>
  );
}

// ── Comparison summary section ────────────────────────────────────────────────

function ComparisonSummarySection({ result }: { result: OptimizationRunDetail }) {
  const { classical_result, quantum_result, comparison } = result;

  if (!classical_result) return null;

  const classicalMetrics = classical_result.metrics;
  const qaoaMetrics = quantum_result?.qaoa?.metrics;
  const vqeMetrics = quantum_result?.vqe?.metrics;
  const hasQuantum = qaoaMetrics !== undefined || vqeMetrics !== undefined;

  if (!hasQuantum) {
    return (
      <div className="flex items-center gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 dark:border-amber-800 dark:bg-amber-900/20">
        <AlertTriangle className="h-4 w-4 text-amber-500 flex-shrink-0" />
        <p className="text-sm text-amber-700 dark:text-amber-400">
          Quantum optimization was not run. Enable it in the constraint form to
          compare classical vs quantum strategies.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Recommendation */}
      {comparison?.recommendation && (
        <RecommendationBanner recommendation={comparison.recommendation} />
      )}

      {/* Sharpe comparison */}
      <div>
        <p className="mb-3 text-sm font-medium">Sharpe Ratio Comparison</p>
        <SharpeComparisonChart
          classicalSharpe={classicalMetrics.sharpe_ratio}
          qaoaSharpe={qaoaMetrics?.sharpe_ratio}
          vqeSharpe={vqeMetrics?.sharpe_ratio}
        />
      </div>

      <Separator />

      {/* Full metrics comparison bar */}
      <div>
        <p className="mb-3 text-sm font-medium">
          Metrics Comparison (Return / Volatility / Sharpe)
        </p>
        <MetricsComparisonBar
          classical={classicalMetrics}
          qaoa={qaoaMetrics}
          vqe={vqeMetrics}
        />
      </div>

      {/* Improvement summary */}
      {comparison && (
        <>
          <Separator />
          <div>
            <p className="mb-3 text-sm font-medium">Improvement vs Classical</p>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {/* QAOA improvements */}
              {qaoaMetrics && (
                <div className="rounded-lg border bg-muted/30 p-4 space-y-2">
                  <div className="flex items-center gap-2">
                    <Badge variant="quantum" className="text-xs">
                      QAOA
                    </Badge>
                    <span className="text-sm font-medium">vs Classical</span>
                  </div>
                  <ImprovementRow
                    label="Sharpe"
                    delta={comparison.sharpe_improvement_qaoa}
                    higherIsBetter
                  />
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
                </div>
              )}

              {/* VQE improvements */}
              {vqeMetrics && (
                <div className="rounded-lg border bg-muted/30 p-4 space-y-2">
                  <div className="flex items-center gap-2">
                    <Badge variant="quantum" className="text-xs">
                      VQE
                    </Badge>
                    <span className="text-sm font-medium">vs Classical</span>
                  </div>
                  <ImprovementRow
                    label="Sharpe"
                    delta={comparison.sharpe_improvement_vqe}
                    higherIsBetter
                  />
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
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function ComparisonDashboard({ result }: ComparisonDashboardProps) {
  const activeTab = useUIStore(selectActiveTab);
  const setActiveTab = useUIStore((s) => s.setActiveTab);

  const hasQuantum =
    result.quantum_result?.qaoa !== undefined ||
    result.quantum_result?.vqe !== undefined;

  const classicalSharpe = result.classical_result?.metrics.sharpe_ratio;
  const qaoaSharpe = result.quantum_result?.qaoa?.metrics.sharpe_ratio;
  const vqeSharpe = result.quantum_result?.vqe?.metrics.sharpe_ratio;

  // Determine if LLM explanation node is still running
  const isExplanationLoading =
    result.status === "running" && !result.llm_explanation;

  return (
    <div className="space-y-6">
      {/* ── Top: Sharpe ratio overview ── */}
      {classicalSharpe !== undefined && hasQuantum && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Sharpe Ratio Overview</CardTitle>
            <CardDescription>
              Risk-adjusted return comparison across all strategies
            </CardDescription>
          </CardHeader>
          <CardContent>
            <SharpeComparisonChart
              classicalSharpe={classicalSharpe}
              qaoaSharpe={qaoaSharpe}
              vqeSharpe={vqeSharpe}
            />
          </CardContent>
        </Card>
      )}

      {/* ── Tabs: Classical | QAOA | VQE ── */}
      <Card>
        <CardContent className="pt-4">
          <Tabs
            value={activeTab}
            onValueChange={(v) => setActiveTab(v as ComparisonTab)}
          >
            <TabsList className="mb-4">
              <TabsTrigger value="classical">
                <span className="flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-blue-500" />
                  Classical
                </span>
              </TabsTrigger>
              {result.quantum_result?.qaoa && (
                <TabsTrigger value="qaoa">
                  <span className="flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-full bg-violet-500" />
                    QAOA
                  </span>
                </TabsTrigger>
              )}
              {result.quantum_result?.vqe && (
                <TabsTrigger value="vqe">
                  <span className="flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-full bg-purple-500" />
                    VQE
                  </span>
                </TabsTrigger>
              )}
            </TabsList>

            <TabsContent value="classical">
              <ClassicalTabContent result={result} />
            </TabsContent>

            {result.quantum_result?.qaoa && (
              <TabsContent value="qaoa">
                <QAOATabContent result={result} />
              </TabsContent>
            )}

            {result.quantum_result?.vqe && (
              <TabsContent value="vqe">
                <VQETabContent result={result} />
              </TabsContent>
            )}
          </Tabs>
        </CardContent>
      </Card>

      {/* ── Full metrics comparison bar (only when quantum results exist) ── */}
      {hasQuantum && result.classical_result && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Full Metrics Comparison</CardTitle>
            <CardDescription>
              Return, volatility, and Sharpe ratio across all strategies
            </CardDescription>
          </CardHeader>
          <CardContent>
            <MetricsComparisonBar
              classical={result.classical_result.metrics}
              qaoa={result.quantum_result?.qaoa?.metrics}
              vqe={result.quantum_result?.vqe?.metrics}
            />
          </CardContent>
        </Card>
      )}

      {/* ── Comparison summary ── */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Strategy Comparison</CardTitle>
          <CardDescription>
            Performance deltas and recommendation
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ComparisonSummarySection result={result} />
        </CardContent>
      </Card>

      {/* ── LLM Explanation ── */}
      <LLMExplanationPanel
        explanation={result.llm_explanation}
        isLoading={isExplanationLoading}
      />
    </div>
  );
}
