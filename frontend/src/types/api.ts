/**
 * TypeScript types mirroring the Pydantic schemas defined in the backend.
 *
 * Keep these in sync with backend/app/schemas/*.py.
 */

// ── Enums ─────────────────────────────────────────────────────────────────────

export type OptimizationStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed";

export type AgentNodeName =
  | "data_fetch"
  | "constraint_validation"
  | "classical_optimization"
  | "quantum_dispatch"
  | "comparison"
  | "frontier_computation"
  | "llm_explanation";

// ── Multi-objective & frontier shared enums ─────────────────────────────────

/**
 * All measure names accepted in the `objectives` matrix.
 *
 * The first five are also valid frontier axes (the convex measures the
 * solver understands). `max_drawdown` and `esg_score` are accepted in
 * the matrix but currently surface only in LLM commentary — they are
 * NOT valid frontier axes.
 */
export type ObjectiveName =
  | "return"
  | "volatility"
  | "sharpe"
  | "diversification_hhi"
  | "sector_concentration"
  | "max_drawdown"
  | "esg_score";

export type FrontierMeasureName =
  | "return"
  | "volatility"
  | "sharpe"
  | "diversification_hhi"
  | "sector_concentration";

export type ObjectiveDirection = "maximize" | "minimize";

// ── Request types ─────────────────────────────────────────────────────────────

export interface SectorConstraint {
  /** Sector name (e.g. "Technology", "Healthcare") */
  sector: string;
  /** Maximum allocation fraction for this sector (0.0–1.0) */
  max_weight: number;
}

/**
 * A single row in the multi-objective matrix.
 *
 * Each enabled row contributes `weight × sign(direction) × normalised(measure)`
 * to the scalarised CVXPY objective.  When `threshold` is provided it
 * becomes a hard constraint (≥ for maximise, ≤ for minimise).
 *
 * Mirrors `BusinessObjective` in backend/app/schemas/requests.py.
 */
export interface BusinessObjective {
  /** Measure name — one of the supported objectives */
  name: ObjectiveName;
  /** Whether this measure is maximised or minimised */
  direction: ObjectiveDirection;
  /** Weight in the scalarised objective (0.0–1.0; rows renormalised at solve time) */
  weight: number;
  /** Whether this row participates in the solve */
  enabled: boolean;
  /**
   * Optional hard threshold. For maximise objectives the solver enforces
   * `measure(w) ≥ threshold`; for minimise objectives `measure(w) ≤ threshold`.
   */
  threshold?: number | null;
  /** Free-form label for the UI / LLM commentary */
  label?: string | null;
}

/**
 * Configuration for the efficient-frontier sweep.
 *
 * When `enabled` is true the backend traces the Pareto frontier between
 * `x_measure` and `y_measure` via an epsilon-constraint sweep across
 * `num_points` levels.
 *
 * Mirrors `FrontierConfig` in backend/app/schemas/requests.py.
 */
export interface FrontierConfig {
  /** Whether to compute and return an efficient frontier */
  enabled: boolean;
  /** Measure plotted on the X-axis (default: volatility) */
  x_measure: FrontierMeasureName;
  /** Measure plotted on the Y-axis (default: return) */
  y_measure: FrontierMeasureName;
  /** Number of parametric solves used to trace the frontier (5–100) */
  num_points: number;
}

export interface OptimizationRequest {
  /** List of ticker symbols (e.g. ["AAPL", "MSFT", "GOOGL"]) */
  tickers: string[];
  /** Total investment budget in USD */
  budget: number;
  /**
   * Multi-objective matrix.  When provided (and non-empty) the solver
   * builds a weighted scalarised objective from the enabled rows and
   * the legacy `min_return` / `max_volatility` fields are ignored
   * except as fallbacks for very old clients.
   */
  objectives?: BusinessObjective[];
  /** Efficient-frontier sweep configuration */
  frontier?: FrontierConfig;
  /**
   * DEPRECATED — kept for backward compatibility with old clients.
   * Prefer adding a `return` row to `objectives` with a threshold.
   */
  min_return?: number;
  /**
   * DEPRECATED — kept for backward compatibility with old clients.
   * Prefer adding a `volatility` row to `objectives` with a threshold.
   */
  max_volatility?: number;
  /** Maximum weight for any single asset (0.0–1.0) */
  max_weight_per_asset?: number;
  /** Minimum weight for any included asset (0.0–1.0) */
  min_weight_per_asset?: number;
  /** Sector-level allocation constraints */
  sector_constraints?: SectorConstraint[];
  /** Number of assets to select (for quantum QUBO formulation) */
  num_assets_to_select?: number;
  /** Historical data lookback period in days */
  lookback_days?: number;
  /** Whether to run quantum optimization (QAOA + VQE) */
  run_quantum?: boolean;
}

// ── Portfolio result types ────────────────────────────────────────────────────

export interface AssetWeight {
  ticker: string;
  weight: number;
  /** Dollar amount allocated */
  allocation: number;
  sector?: string;
}

export interface PortfolioMetrics {
  /** Annualised expected return */
  expected_return: number;
  /** Annualised volatility (standard deviation) */
  volatility: number;
  /** Sharpe ratio */
  sharpe_ratio: number;
  /** Maximum drawdown (if computed) */
  max_drawdown?: number;
  /** Number of assets with non-zero weight */
  num_assets: number;
}

export interface ClassicalResult {
  weights: AssetWeight[];
  metrics: PortfolioMetrics;
  solver_status: string;
  solve_time_ms: number;
}

export interface QuantumResult {
  /** QAOA result (Qiskit) */
  qaoa?: {
    selected_assets: string[];
    weights: AssetWeight[];
    metrics: PortfolioMetrics;
    circuit_depth: number;
    num_qubits: number;
    solve_time_ms: number;
  };
  /** VQE-style result (PennyLane) */
  vqe?: {
    selected_assets: string[];
    weights: AssetWeight[];
    metrics: PortfolioMetrics;
    num_qubits: number;
    solve_time_ms: number;
  };
}

export interface ComparisonSummary {
  sharpe_improvement_qaoa?: number;
  sharpe_improvement_vqe?: number;
  return_diff_qaoa?: number;
  return_diff_vqe?: number;
  volatility_diff_qaoa?: number;
  volatility_diff_vqe?: number;
  recommendation: string;
}

// ── Efficient frontier ──────────────────────────────────────────────────────

/**
 * Single sample on the efficient frontier.
 *
 * Mirrors `FrontierPoint` in backend/app/schemas/responses.py.
 */
export interface FrontierPoint {
  /** X-axis measure value */
  x: number;
  /** Y-axis measure value */
  y: number;
  /** Sharpe ratio of this portfolio (always populated for ranking) */
  sharpe: number;
  /** Full asset allocation for this frontier portfolio */
  weights: AssetWeight[];
  /** True when the point is Pareto-efficient given the chosen directions */
  is_dominant: boolean;
  /** True for the algorithmically chosen knee point */
  is_knee: boolean;
  /** CVXPY solver status for this point */
  solver_status: string;
}

/**
 * Full bundle returned by the frontier sweep node.
 *
 * Mirrors `FrontierReport` in backend/app/schemas/responses.py.
 */
export interface FrontierReport {
  /** Canonical name of the X-axis measure */
  x_measure: FrontierMeasureName;
  /** Canonical name of the Y-axis measure */
  y_measure: FrontierMeasureName;
  /** Optimisation direction for the X measure */
  x_direction: ObjectiveDirection;
  /** Optimisation direction for the Y measure */
  y_direction: ObjectiveDirection;
  /** All sampled points (dominant + dominated) */
  points: FrontierPoint[];
  /** Index into `points` of the chosen knee portfolio, if any */
  knee_point_index?: number | null;
  /** Index of the max-Sharpe reference portfolio, if any */
  max_sharpe_index?: number | null;
  /** Index of the minimum-risk reference portfolio, if any */
  min_risk_index?: number | null;
  /** Number of Pareto-dominant points */
  num_dominant: number;
  /** Number of dominated points */
  num_dominated: number;
  /** Total wall-clock time spent sweeping the frontier (ms) */
  solve_time_ms: number;
  /** LLM-generated natural-language summary of the frontier */
  commentary?: string | null;
}

// ── Run types ─────────────────────────────────────────────────────────────────

export interface OptimizationRunSummary {
  run_id: string;
  status: OptimizationStatus;
  tickers: string[];
  budget: number;
  created_at: string;
  completed_at?: string;
  classical_sharpe?: number;
  quantum_sharpe?: number;
}

export interface OptimizationRunDetail extends OptimizationRunSummary {
  classical_result?: ClassicalResult;
  quantum_result?: QuantumResult;
  comparison?: ComparisonSummary;
  llm_explanation?: string;
  error_message?: string;
  /**
   * Efficient-frontier bundle. Populated only when the originating
   * request had `frontier.enabled === true`. Null otherwise.
   */
  frontier_report?: FrontierReport | null;
}

// ── WebSocket message types ───────────────────────────────────────────────────

export interface AgentProgressMessage {
  type: "progress";
  run_id: string;
  node: AgentNodeName;
  status: "started" | "completed" | "failed";
  message: string;
  timestamp: string;
}

export interface AgentResultMessage {
  type: "result";
  run_id: string;
  result: OptimizationRunDetail;
}

export interface AgentErrorMessage {
  type: "error";
  run_id: string;
  error_code: string;
  message: string;
}

export type WebSocketMessage =
  | AgentProgressMessage
  | AgentResultMessage
  | AgentErrorMessage;

// ── Asset search ──────────────────────────────────────────────────────────────

export interface AssetSearchResult {
  ticker: string;
  name: string;
  sector?: string;
  exchange?: string;
}

// ── Health ────────────────────────────────────────────────────────────────────

export interface HealthStatus {
  status: "healthy" | "degraded" | "unhealthy";
  version: string;
  services: {
    database: "up" | "down";
    redis: "up" | "down";
    celery: "up" | "down";
  };
}
