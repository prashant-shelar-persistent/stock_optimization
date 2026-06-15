/**
 * Shared test fixtures for the Portfolio Optimizer frontend tests.
 *
 * Provides factory functions and pre-built objects that are reused across
 * multiple test files. Keeping fixtures centralised ensures consistency and
 * makes it easy to update when the API schema changes.
 */

import type {
  AgentProgressMessage,
  AgentNodeName,
  AssetWeight,
  ClassicalResult,
  ComparisonSummary,
  OptimizationRequest,
  OptimizationRunDetail,
  OptimizationRunSummary,
  PortfolioMetrics,
  QuantumResult,
} from "@/types/api";

// ── Agent progress messages ──────────────────────────────────────────────────

/**
 * Build a single AgentProgressMessage.
 */
export function makeProgressMessage(
  node: AgentNodeName,
  status: AgentProgressMessage["status"],
  overrides: Partial<AgentProgressMessage> = {},
): AgentProgressMessage {
  return {
    type: "progress",
    run_id: "run-fixture-001",
    node,
    status,
    message: `${node} ${status}`,
    timestamp: "2024-06-01T12:00:00.000Z",
    ...overrides,
  };
}

/** A full pipeline of progress messages (all 6 nodes, started + completed). */
export const FULL_PIPELINE_PROGRESS: AgentProgressMessage[] = [
  "data_fetch",
  "constraint_validation",
  "classical_optimization",
  "quantum_dispatch",
  "comparison",
  "llm_explanation",
].flatMap((node) => [
  makeProgressMessage(node as AgentNodeName, "started", {
    message: `${node} started`,
    timestamp: "2024-06-01T12:00:00.000Z",
  }),
  makeProgressMessage(node as AgentNodeName, "completed", {
    message: `${node} completed`,
    timestamp: "2024-06-01T12:00:01.000Z",
  }),
]);

/** Progress messages for the first two nodes only (partial pipeline). */
export const PARTIAL_PIPELINE_PROGRESS: AgentProgressMessage[] = [
  makeProgressMessage("data_fetch", "started", {
    message: "Fetching AAPL, MSFT, GOOGL data",
  }),
  makeProgressMessage("data_fetch", "completed", {
    message: "Fetched 3 assets (252 trading days)",
  }),
  makeProgressMessage("constraint_validation", "started", {
    message: "Validating portfolio constraints",
  }),
];

// ── Portfolio metrics ────────────────────────────────────────────────────────

export const CLASSICAL_METRICS: PortfolioMetrics = {
  expected_return: 0.142,
  volatility: 0.187,
  sharpe_ratio: 1.45,
  max_drawdown: 0.23,
  num_assets: 3,
};

export const QAOA_METRICS: PortfolioMetrics = {
  expected_return: 0.158,
  volatility: 0.192,
  sharpe_ratio: 1.62,
  num_assets: 3,
};

export const VQE_METRICS: PortfolioMetrics = {
  expected_return: 0.151,
  volatility: 0.189,
  sharpe_ratio: 1.55,
  num_assets: 3,
};

// ── Asset weights ────────────────────────────────────────────────────────────

export const CLASSICAL_WEIGHTS: AssetWeight[] = [
  { ticker: "AAPL", weight: 0.45, allocation: 4500, sector: "Technology" },
  { ticker: "MSFT", weight: 0.35, allocation: 3500, sector: "Technology" },
  { ticker: "GOOGL", weight: 0.20, allocation: 2000, sector: "Communication Services" },
];

export const QAOA_WEIGHTS: AssetWeight[] = [
  { ticker: "AAPL", weight: 0.50, allocation: 5000, sector: "Technology" },
  { ticker: "MSFT", weight: 0.30, allocation: 3000, sector: "Technology" },
  { ticker: "GOOGL", weight: 0.20, allocation: 2000, sector: "Communication Services" },
];

export const VQE_WEIGHTS: AssetWeight[] = [
  { ticker: "AAPL", weight: 0.40, allocation: 4000, sector: "Technology" },
  { ticker: "MSFT", weight: 0.40, allocation: 4000, sector: "Technology" },
  { ticker: "GOOGL", weight: 0.20, allocation: 2000, sector: "Communication Services" },
];

// ── Classical result ─────────────────────────────────────────────────────────

export const CLASSICAL_RESULT: ClassicalResult = {
  weights: CLASSICAL_WEIGHTS,
  metrics: CLASSICAL_METRICS,
  solver_status: "optimal",
  solve_time_ms: 42,
};

// ── Quantum result ───────────────────────────────────────────────────────────

export const QUANTUM_RESULT: QuantumResult = {
  qaoa: {
    selected_assets: ["AAPL", "MSFT", "GOOGL"],
    weights: QAOA_WEIGHTS,
    metrics: QAOA_METRICS,
    circuit_depth: 12,
    num_qubits: 3,
    solve_time_ms: 1240,
  },
  vqe: {
    selected_assets: ["AAPL", "MSFT", "GOOGL"],
    weights: VQE_WEIGHTS,
    metrics: VQE_METRICS,
    num_qubits: 3,
    solve_time_ms: 980,
  },
};

// ── Comparison summary ───────────────────────────────────────────────────────

export const COMPARISON_SUMMARY: ComparisonSummary = {
  sharpe_improvement_qaoa: 0.17,
  sharpe_improvement_vqe: 0.10,
  return_diff_qaoa: 0.016,
  return_diff_vqe: 0.009,
  volatility_diff_qaoa: 0.005,
  volatility_diff_vqe: 0.002,
  recommendation:
    "QAOA outperforms the classical baseline with a higher Sharpe ratio. Consider the quantum portfolio for better risk-adjusted returns.",
};

// ── Optimization run detail ──────────────────────────────────────────────────

/**
 * A fully completed optimization run with classical + quantum results.
 */
export const COMPLETED_RUN_DETAIL: OptimizationRunDetail = {
  run_id: "run-fixture-001",
  status: "completed",
  tickers: ["AAPL", "MSFT", "GOOGL"],
  budget: 10000,
  created_at: "2024-06-01T12:00:00.000Z",
  completed_at: "2024-06-01T12:01:30.000Z",
  classical_sharpe: 1.45,
  quantum_sharpe: 1.62,
  classical_result: CLASSICAL_RESULT,
  quantum_result: QUANTUM_RESULT,
  comparison: COMPARISON_SUMMARY,
  llm_explanation:
    "The optimized portfolio allocates 45% to AAPL, 35% to MSFT, and 20% to GOOGL. " +
    "The quantum QAOA approach achieves a higher Sharpe ratio of 1.62 compared to the " +
    "classical Markowitz MVO result of 1.45, representing an 11.7% improvement in " +
    "risk-adjusted returns.",
};

/**
 * A run with only classical results (quantum was not run).
 */
export const CLASSICAL_ONLY_RUN_DETAIL: OptimizationRunDetail = {
  run_id: "run-fixture-002",
  status: "completed",
  tickers: ["AAPL", "MSFT", "GOOGL"],
  budget: 10000,
  created_at: "2024-06-01T11:00:00.000Z",
  completed_at: "2024-06-01T11:00:05.000Z",
  classical_sharpe: 1.45,
  classical_result: CLASSICAL_RESULT,
  comparison: {
    recommendation: "Classical Markowitz MVO portfolio is optimal for this asset set.",
  },
};

/**
 * A run that is still in progress.
 */
export const RUNNING_RUN_DETAIL: OptimizationRunDetail = {
  run_id: "run-fixture-003",
  status: "running",
  tickers: ["AAPL", "MSFT"],
  budget: 5000,
  created_at: "2024-06-01T13:00:00.000Z",
};

/**
 * A failed run.
 */
export const FAILED_RUN_DETAIL: OptimizationRunDetail = {
  run_id: "run-fixture-004",
  status: "failed",
  tickers: ["AAPL"],
  budget: 1000,
  created_at: "2024-06-01T14:00:00.000Z",
  error_message: "Insufficient historical data for the requested lookback period.",
};

// ── Run summaries ────────────────────────────────────────────────────────────

/**
 * Build an OptimizationRunSummary with optional overrides.
 */
export function makeRunSummary(
  overrides: Partial<OptimizationRunSummary> = {},
): OptimizationRunSummary {
  return {
    run_id: "run-summary-001",
    status: "completed",
    tickers: ["AAPL", "MSFT", "GOOGL"],
    budget: 10000,
    created_at: new Date(Date.now() - 3_600_000).toISOString(), // 1 hour ago
    completed_at: new Date(Date.now() - 3_500_000).toISOString(),
    classical_sharpe: 1.45,
    quantum_sharpe: 1.62,
    ...overrides,
  };
}

/** A list of 3 completed run summaries for pagination tests. */
export const RUN_SUMMARY_LIST: OptimizationRunSummary[] = [
  makeRunSummary({ run_id: "run-001", tickers: ["AAPL", "MSFT"] }),
  makeRunSummary({
    run_id: "run-002",
    status: "running",
    tickers: ["GOOGL", "AMZN", "TSLA"],
    quantum_sharpe: undefined,
  }),
  makeRunSummary({
    run_id: "run-003",
    status: "failed",
    tickers: ["NVDA"],
    classical_sharpe: undefined,
    quantum_sharpe: undefined,
  }),
];

// ── Optimization request ─────────────────────────────────────────────────────

export const SAMPLE_OPTIMIZATION_REQUEST: OptimizationRequest = {
  tickers: ["AAPL", "MSFT", "GOOGL"],
  budget: 10000,
  min_return: 0.08,
  max_volatility: 0.25,
  max_weight_per_asset: 0.5,
  min_weight_per_asset: 0.05,
  sector_constraints: [{ sector: "Technology", max_weight: 0.6 }],
  num_assets_to_select: 3,
  lookback_days: 252,
  run_quantum: true,
};
