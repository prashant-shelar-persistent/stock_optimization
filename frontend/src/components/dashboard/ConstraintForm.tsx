/**
 * ConstraintForm — Portfolio optimization constraint input form.
 *
 * Sections:
 *   1. Assets (ticker multi-select)
 *   2. Budget (USD)
 *   3. Business Objectives matrix (multi-objective weights + thresholds)
 *   4. Efficient Frontier config (axis pair + num_points)
 *   5. Risk / Return legacy constraints (min_return, max_volatility)
 *   6. Weight constraints
 *   7. Lookback period
 *   8. Quantum toggle
 */

import {
  useState,
  useCallback,
  type KeyboardEvent,
  type ChangeEvent,
} from "react";
import { useOptimize } from "@/hooks/useOptimize";
import { useAssetSearch } from "@/hooks/useAssetSearch";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
  TooltipProvider,
} from "@/components/ui/tooltip";
import {
  X,
  Plus,
  Search,
  Info,
  Loader2,
  Zap,
  BarChart2,
  Target,
  TrendingUp,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type {
  OptimizationRequest,
  BusinessObjective,
  FrontierConfig,
  ObjectiveName,
  FrontierMeasureName,
  ObjectiveDirection,
} from "@/types/api";

// ── Default values ────────────────────────────────────────────────────────────

const DEFAULT_TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"];
const DEFAULT_BUDGET = 100_000;
const DEFAULT_BUDGET_DISPLAY = "100,000";
const DEFAULT_LOOKBACK = 252;
const DEFAULT_MAX_WEIGHT = 0.4;
const DEFAULT_NUM_ASSETS = 5;

// ── Objective catalogue ───────────────────────────────────────────────────────

interface ObjectiveMeta {
  name: ObjectiveName;
  label: string;
  defaultDirection: ObjectiveDirection;
  tooltip: string;
  isFrontierAxis: boolean;
}

const OBJECTIVE_CATALOGUE: ObjectiveMeta[] = [
  {
    name: "return",
    label: "Expected Return",
    defaultDirection: "maximize",
    tooltip: "Annualised expected portfolio return",
    isFrontierAxis: true,
  },
  {
    name: "volatility",
    label: "Volatility",
    defaultDirection: "minimize",
    tooltip: "Annualised portfolio volatility (standard deviation)",
    isFrontierAxis: true,
  },
  {
    name: "sharpe",
    label: "Sharpe Ratio",
    defaultDirection: "maximize",
    tooltip: "Risk-adjusted return (return / volatility)",
    isFrontierAxis: true,
  },
  {
    name: "diversification_hhi",
    label: "Diversification (HHI)",
    defaultDirection: "minimize",
    tooltip:
      "Herfindahl-Hirschman Index of weight concentration — lower is more diversified",
    isFrontierAxis: true,
  },
  {
    name: "sector_concentration",
    label: "Sector Concentration",
    defaultDirection: "minimize",
    tooltip: "Maximum single-sector weight — lower means less sector risk",
    isFrontierAxis: true,
  },
  {
    name: "max_drawdown",
    label: "Max Drawdown",
    defaultDirection: "minimize",
    tooltip:
      "Largest peak-to-trough decline (informational — not a frontier axis)",
    isFrontierAxis: false,
  },
  {
    name: "esg_score",
    label: "ESG Score",
    defaultDirection: "maximize",
    tooltip:
      "Environmental, Social & Governance composite score (informational — not a frontier axis)",
    isFrontierAxis: false,
  },
];

const FRONTIER_MEASURES: { value: FrontierMeasureName; label: string }[] = [
  { value: "volatility", label: "Volatility" },
  { value: "return", label: "Expected Return" },
  { value: "sharpe", label: "Sharpe Ratio" },
  { value: "diversification_hhi", label: "Diversification (HHI)" },
  { value: "sector_concentration", label: "Sector Concentration" },
];

// ── Types ─────────────────────────────────────────────────────────────────────

interface ConstraintFormProps {
  onRunStarted?: (runId: string) => void;
}

// ── Ticker input with search ──────────────────────────────────────────────────

interface TickerInputProps {
  tickers: string[];
  onAdd: (ticker: string) => void;
  onRemove: (ticker: string) => void;
}

function TickerInput({ tickers, onAdd, onRemove }: TickerInputProps) {
  const [query, setQuery] = useState("");
  const [showDropdown, setShowDropdown] = useState(false);
  const { results, isLoading } = useAssetSearch(query);

  const handleAdd = useCallback(
    (ticker: string) => {
      const upper = ticker.toUpperCase().trim();
      if (upper && !tickers.includes(upper)) {
        onAdd(upper);
      }
      setQuery("");
      setShowDropdown(false);
    },
    [tickers, onAdd],
  );

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && query.trim()) {
      e.preventDefault();
      handleAdd(query.trim());
    }
    if (e.key === "Escape") setShowDropdown(false);
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5 min-h-[32px]">
        {tickers.map((ticker) => (
          <Badge key={ticker} variant="secondary" className="gap-1 font-mono text-xs">
            {ticker}
            <button
              type="button"
              onClick={() => onRemove(ticker)}
              className="ml-0.5 rounded-full hover:bg-muted-foreground/20 p-0.5"
              aria-label={`Remove ${ticker}`}
            >
              <X className="h-2.5 w-2.5" />
            </button>
          </Badge>
        ))}
        {tickers.length === 0 && (
          <span className="text-xs text-muted-foreground">No tickers selected</span>
        )}
      </div>

      <div className="relative">
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => { setQuery(e.target.value); setShowDropdown(true); }}
            onKeyDown={handleKeyDown}
            onFocus={() => setShowDropdown(true)}
            onBlur={() => setTimeout(() => setShowDropdown(false), 150)}
            placeholder="Search ticker (e.g. AAPL)…"
            className="pl-8 pr-8 h-9 text-sm"
          />
          {isLoading && (
            <Loader2 className="absolute right-2.5 top-2.5 h-3.5 w-3.5 animate-spin text-muted-foreground" />
          )}
          {!isLoading && query && (
            <button
              type="button"
              onClick={() => { setQuery(""); setShowDropdown(false); }}
              className="absolute right-2.5 top-2.5"
            >
              <X className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground" />
            </button>
          )}
        </div>

        {showDropdown && (results.length > 0 || query.trim()) && (
          <div className="absolute z-50 mt-1 w-full rounded-md border bg-popover shadow-md">
            {results.length > 0 ? (
              <ul className="max-h-48 overflow-auto py-1">
                {results.map((asset) => (
                  <li key={asset.ticker}>
                    <button
                      type="button"
                      className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-accent"
                      onMouseDown={() => handleAdd(asset.ticker)}
                    >
                      <span className="font-mono font-semibold">{asset.ticker}</span>
                      <span className="truncate text-muted-foreground">{asset.name}</span>
                      {asset.sector && (
                        <Badge variant="outline" className="ml-auto text-xs flex-shrink-0">
                          {asset.sector}
                        </Badge>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              query.trim() && (
                <div className="px-3 py-2">
                  <button
                    type="button"
                    className="flex w-full items-center gap-2 text-sm hover:text-primary"
                    onMouseDown={() => handleAdd(query.trim())}
                  >
                    <Plus className="h-3.5 w-3.5" />
                    Add "{query.toUpperCase()}"
                  </button>
                </div>
              )
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Field label with tooltip ──────────────────────────────────────────────────

function FieldLabel({
  htmlFor,
  label,
  tooltip,
}: {
  htmlFor?: string;
  label: string;
  tooltip?: string;
}) {
  return (
    <div className="flex items-center gap-1.5">
      <Label htmlFor={htmlFor} className="text-sm font-medium">
        {label}
      </Label>
      {tooltip && (
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Info className="h-3 w-3 cursor-help text-muted-foreground/60 hover:text-muted-foreground" />
            </TooltipTrigger>
            <TooltipContent side="right" className="max-w-[220px] text-xs">
              {tooltip}
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      )}
    </div>
  );
}

// ── Objectives matrix row ─────────────────────────────────────────────────────

interface ObjectiveRowProps {
  obj: BusinessObjective & { _meta: ObjectiveMeta };
  onChange: (updated: Partial<BusinessObjective>) => void;
}

function ObjectiveRow({ obj, onChange }: ObjectiveRowProps) {
  const [thresholdInput, setThresholdInput] = useState(
    obj.threshold != null ? String(obj.threshold) : "",
  );

  const handleThresholdBlur = () => {
    const v = parseFloat(thresholdInput);
    onChange({ threshold: isNaN(v) ? null : v });
  };

  return (
    <div
      className={cn(
        "rounded-md border p-3 space-y-2 transition-colors",
        obj.enabled ? "border-border bg-card" : "border-dashed border-muted bg-muted/30 opacity-60",
      )}
    >
      {/* Row header: enable toggle + name + direction */}
      <div className="flex items-center gap-2">
        <Switch
          checked={obj.enabled}
          onCheckedChange={(v) => onChange({ enabled: v })}
          aria-label={`Enable ${obj._meta.label}`}
          className="scale-75"
        />
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="flex-1 text-xs font-medium cursor-default truncate">
                {obj._meta.label}
              </span>
            </TooltipTrigger>
            <TooltipContent side="right" className="max-w-[200px] text-xs">
              {obj._meta.tooltip}
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
        <Select
          value={obj.direction}
          onValueChange={(v) => onChange({ direction: v as ObjectiveDirection })}
          disabled={!obj.enabled}
        >
          <SelectTrigger className="h-6 w-[90px] text-xs px-2">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="maximize" className="text-xs">Maximize</SelectItem>
            <SelectItem value="minimize" className="text-xs">Minimize</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Weight slider */}
      {obj.enabled && (
        <div className="space-y-1">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">Weight</span>
            <span className="text-xs tabular-nums font-medium">
              {(obj.weight * 100).toFixed(0)}%
            </span>
          </div>
          <Slider
            min={1}
            max={100}
            step={1}
            value={[Math.round(obj.weight * 100)]}
            onValueChange={([v]) => onChange({ weight: v / 100 })}
            className="w-full"
          />
        </div>
      )}

      {/* Optional threshold */}
      {obj.enabled && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground w-16 flex-shrink-0">
            Threshold
          </span>
          <Input
            type="number"
            step="any"
            placeholder="optional"
            value={thresholdInput}
            onChange={(e) => setThresholdInput(e.target.value)}
            onBlur={handleThresholdBlur}
            className="h-6 text-xs px-2 flex-1"
          />
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Info className="h-3 w-3 text-muted-foreground/60 flex-shrink-0" />
              </TooltipTrigger>
              <TooltipContent side="left" className="max-w-[200px] text-xs">
                Hard constraint: for maximize objectives the solver enforces
                measure ≥ threshold; for minimize, measure ≤ threshold.
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function ConstraintForm({ onRunStarted }: ConstraintFormProps) {
  const { submit, isSubmitting } = useOptimize();

  // ── Core state ──
  const [tickers, setTickers] = useState<string[]>(DEFAULT_TICKERS);
  const [budget, setBudget] = useState(DEFAULT_BUDGET);
  const [budgetInput, setBudgetInput] = useState(DEFAULT_BUDGET_DISPLAY);
  const [budgetTouched, setBudgetTouched] = useState(false);

  // ── Objectives matrix ──
  const [objectives, setObjectives] = useState<
    (BusinessObjective & { _meta: ObjectiveMeta })[]
  >(
    OBJECTIVE_CATALOGUE.map((meta) => ({
      name: meta.name,
      label: meta.label,
      direction: meta.defaultDirection,
      weight: 0.5,
      enabled: meta.name === "return" || meta.name === "volatility",
      threshold: null,
      _meta: meta,
    })),
  );

  // ── Frontier config ──
  const [frontierEnabled, setFrontierEnabled] = useState(false);
  const [frontierX, setFrontierX] = useState<FrontierMeasureName>("volatility");
  const [frontierY, setFrontierY] = useState<FrontierMeasureName>("return");
  const [frontierPoints, setFrontierPoints] = useState(20);

  // ── Legacy constraints ──
  const [minReturn, setMinReturn] = useState<number | undefined>(undefined);
  const [maxVolatility, setMaxVolatility] = useState<number | undefined>(undefined);
  const [maxWeightPerAsset, setMaxWeightPerAsset] = useState(DEFAULT_MAX_WEIGHT);
  const [numAssetsToSelect, setNumAssetsToSelect] = useState(DEFAULT_NUM_ASSETS);
  const [lookbackDays, setLookbackDays] = useState(DEFAULT_LOOKBACK);
  const [runQuantum, setRunQuantum] = useState(false);

  // ── Validation errors ──
  const [errors, setErrors] = useState<Record<string, string>>({});

  // ── Budget helpers ──────────────────────────────────────────────────────────

  function validateBudgetInput(raw: string): string | undefined {
    const trimmed = raw.trim();
    if (trimmed === "") return "Budget is required.";
    const stripped = trimmed.replace(/,/g, "");
    if (!/^\d+(\.\d+)?$/.test(stripped))
      return "Budget must be a valid positive number (e.g. 50000 or 50,000).";
    const numeric = parseFloat(stripped);
    if (isNaN(numeric) || numeric <= 0) return "Budget must be greater than $0.";
    if (numeric < 1) return "Budget must be at least $1.";
    if (numeric > 1_000_000_000) return "Budget cannot exceed $1,000,000,000.";
    return undefined;
  }

  function parseBudget(raw: string): number {
    return parseFloat(raw.trim().replace(/,/g, ""));
  }

  function handleBudgetChange(e: ChangeEvent<HTMLInputElement>) {
    const raw = e.target.value;
    setBudgetInput(raw);
    const numeric = parseBudget(raw);
    if (!isNaN(numeric) && numeric > 0) setBudget(numeric);
    if (budgetTouched) {
      const errMsg = validateBudgetInput(raw);
      setErrors((prev) => {
        const next = { ...prev };
        if (errMsg) next.budget = errMsg;
        else delete next.budget;
        return next;
      });
    } else if (raw.trim() !== "") {
      setErrors((prev) => { const next = { ...prev }; delete next.budget; return next; });
    }
  }

  function handleBudgetBlur() {
    setBudgetTouched(true);
    const errMsg = validateBudgetInput(budgetInput);
    if (errMsg) {
      setErrors((prev) => ({ ...prev, budget: errMsg }));
    } else {
      const numeric = parseBudget(budgetInput);
      setBudget(numeric);
      setBudgetInput(numeric.toLocaleString("en-US", { maximumFractionDigits: 2 }));
      setErrors((prev) => { const next = { ...prev }; delete next.budget; return next; });
    }
  }

  // ── Objectives helpers ──────────────────────────────────────────────────────

  function updateObjective(
    name: ObjectiveName,
    patch: Partial<BusinessObjective>,
  ) {
    setObjectives((prev) =>
      prev.map((o) => (o.name === name ? { ...o, ...patch } : o)),
    );
  }

  // ── Frontier helpers ────────────────────────────────────────────────────────

  const frontierXOptions = FRONTIER_MEASURES.filter((m) => m.value !== frontierY);
  const frontierYOptions = FRONTIER_MEASURES.filter((m) => m.value !== frontierX);

  // ── Validation ──────────────────────────────────────────────────────────────

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (tickers.length < 2) newErrors.tickers = "Select at least 2 tickers.";

    const budgetErr = validateBudgetInput(budgetInput);
    if (budgetErr) newErrors.budget = budgetErr;

    if (minReturn !== undefined && (minReturn < 0 || minReturn > 1))
      newErrors.minReturn = "Min return must be between 0% and 100%.";

    if (maxVolatility !== undefined && (maxVolatility < 0 || maxVolatility > 1))
      newErrors.maxVolatility = "Max volatility must be between 0% and 100%.";

    if (runQuantum && numAssetsToSelect > tickers.length)
      newErrors.numAssetsToSelect = `Cannot select more assets than the ${tickers.length} tickers provided.`;

    if (frontierEnabled && frontierX === frontierY)
      newErrors.frontier = "X and Y axes must be different measures.";

    const enabledObjs = objectives.filter((o) => o.enabled);
    if (enabledObjs.length > 0) {
      const totalWeight = enabledObjs.reduce((s, o) => s + o.weight, 0);
      if (totalWeight <= 0)
        newErrors.objectives = "At least one enabled objective must have a positive weight.";
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  // ── Submit ──────────────────────────────────────────────────────────────────

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

    const finalBudget = parseBudget(budgetInput);

    // Build objectives array — only include enabled rows
    const enabledObjectives = objectives
      .filter((o) => o.enabled)
      .map(({ _meta: _m, ...rest }) => rest as BusinessObjective);

    // Build frontier config
    const frontierConfig: FrontierConfig | undefined = frontierEnabled
      ? {
          enabled: true,
          x_measure: frontierX,
          y_measure: frontierY,
          num_points: frontierPoints,
        }
      : undefined;

    const payload: OptimizationRequest = {
      tickers,
      budget: finalBudget,
      ...(enabledObjectives.length > 0 ? { objectives: enabledObjectives } : {}),
      ...(frontierConfig ? { frontier: frontierConfig } : {}),
      ...(minReturn !== undefined ? { min_return: minReturn } : {}),
      ...(maxVolatility !== undefined ? { max_volatility: maxVolatility } : {}),
      max_weight_per_asset: maxWeightPerAsset,
      ...(runQuantum ? { num_assets_to_select: numAssetsToSelect } : {}),
      lookback_days: lookbackDays,
      run_quantum: runQuantum,
    };

    const runId = await submit(payload);
    if (runId && onRunStarted) onRunStarted(runId);
  };

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <form id="constraint-form" onSubmit={handleSubmit} className="space-y-5">

      {/* ── Assets ── */}
      <div className="space-y-2">
        <FieldLabel label="Assets" tooltip="Search and select assets to include in the portfolio" />
        <TickerInput
          tickers={tickers}
          onAdd={(t) => setTickers((prev) => [...prev, t])}
          onRemove={(t) => setTickers((prev) => prev.filter((x) => x !== t))}
        />
        {errors.tickers && <p className="text-xs text-destructive">{errors.tickers}</p>}
      </div>

      <Separator />

      {/* ── Budget ── */}
      <div className="space-y-2">
        <FieldLabel
          htmlFor="budget"
          label="Budget (USD)"
          tooltip="Total investment budget in US dollars."
        />
        <div className="relative">
          <span className="absolute left-3 top-2 text-sm text-muted-foreground select-none">$</span>
          <Input
            id="budget"
            type="text"
            inputMode="decimal"
            value={budgetInput}
            onChange={handleBudgetChange}
            onBlur={handleBudgetBlur}
            placeholder="e.g. 100,000"
            aria-describedby={errors.budget ? "budget-error" : "budget-hint"}
            aria-invalid={!!errors.budget}
            className={cn(
              "pl-6 h-9 text-sm",
              errors.budget && "border-destructive focus-visible:ring-destructive",
            )}
          />
        </div>
        {errors.budget ? (
          <p id="budget-error" className="text-xs text-destructive" role="alert">
            {errors.budget}
          </p>
        ) : (
          <p id="budget-hint" className="text-xs text-muted-foreground">
            Enter a positive dollar amount (e.g. 50,000 or 1,000,000)
          </p>
        )}
      </div>

      <Separator />

      {/* ── Business Objectives Matrix ── */}
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <Target className="h-4 w-4 text-primary" />
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Business Objectives
          </p>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Info className="h-3 w-3 cursor-help text-muted-foreground/60" />
              </TooltipTrigger>
              <TooltipContent side="right" className="max-w-[240px] text-xs">
                Enable objectives and set relative weights. The solver builds a
                weighted scalarised objective from all enabled rows. Optionally
                set a hard threshold to enforce a minimum/maximum constraint.
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>

        <div className="space-y-2">
          {objectives.map((obj) => (
            <ObjectiveRow
              key={obj.name}
              obj={obj}
              onChange={(patch) => updateObjective(obj.name, patch)}
            />
          ))}
        </div>
        {errors.objectives && (
          <p className="text-xs text-destructive">{errors.objectives}</p>
        )}
      </div>

      <Separator />

      {/* ── Efficient Frontier ── */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-emerald-500" />
            <FieldLabel
              label="Efficient Frontier"
              tooltip="Trace the Pareto frontier between two selected measures using an epsilon-constraint sweep."
            />
          </div>
          <Switch
            checked={frontierEnabled}
            onCheckedChange={setFrontierEnabled}
            aria-label="Enable efficient frontier computation"
          />
        </div>

        {frontierEnabled && (
          <div className="ml-6 space-y-3 rounded-md border border-dashed p-3">
            {/* Axis selectors */}
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">X Axis</Label>
                <Select
                  value={frontierX}
                  onValueChange={(v) => setFrontierX(v as FrontierMeasureName)}
                >
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {frontierXOptions.map((m) => (
                      <SelectItem key={m.value} value={m.value} className="text-xs">
                        {m.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Y Axis</Label>
                <Select
                  value={frontierY}
                  onValueChange={(v) => setFrontierY(v as FrontierMeasureName)}
                >
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {frontierYOptions.map((m) => (
                      <SelectItem key={m.value} value={m.value} className="text-xs">
                        {m.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {errors.frontier && (
              <p className="text-xs text-destructive">{errors.frontier}</p>
            )}

            {/* Number of points */}
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <FieldLabel
                  htmlFor="frontier-points"
                  label="Frontier Points"
                  tooltip="Number of parametric solves used to trace the frontier (5–100). More points = smoother curve but slower."
                />
                <span className="text-xs tabular-nums text-muted-foreground">
                  {frontierPoints}
                </span>
              </div>
              <Slider
                id="frontier-points"
                min={5}
                max={50}
                step={5}
                value={[frontierPoints]}
                onValueChange={([v]) => setFrontierPoints(v)}
                className="w-full"
              />
            </div>

            <p className="text-xs text-muted-foreground">
              The frontier report will appear in the run detail view after completion.
            </p>
          </div>
        )}
      </div>

      <Separator />

      {/* ── Risk / Return legacy constraints ── */}
      <div className="space-y-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Risk / Return Constraints
        </p>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <FieldLabel
              htmlFor="min-return"
              label="Min Return"
              tooltip="Minimum acceptable annualised portfolio return (0–50%)"
            />
            <span className="text-xs tabular-nums text-muted-foreground">
              {minReturn !== undefined ? `${(minReturn * 100).toFixed(0)}%` : "None"}
            </span>
          </div>
          <Slider
            id="min-return"
            min={0}
            max={50}
            step={1}
            value={[minReturn !== undefined ? minReturn * 100 : 0]}
            onValueChange={([v]) => setMinReturn(v > 0 ? v / 100 : undefined)}
            className="w-full"
          />
          {errors.minReturn && <p className="text-xs text-destructive">{errors.minReturn}</p>}
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <FieldLabel
              htmlFor="max-vol"
              label="Max Volatility"
              tooltip="Maximum acceptable annualised portfolio volatility (0–80%)"
            />
            <span className="text-xs tabular-nums text-muted-foreground">
              {maxVolatility !== undefined ? `${(maxVolatility * 100).toFixed(0)}%` : "None"}
            </span>
          </div>
          <Slider
            id="max-vol"
            min={0}
            max={80}
            step={1}
            value={[maxVolatility !== undefined ? maxVolatility * 100 : 0]}
            onValueChange={([v]) => setMaxVolatility(v > 0 ? v / 100 : undefined)}
            className="w-full"
          />
          {errors.maxVolatility && (
            <p className="text-xs text-destructive">{errors.maxVolatility}</p>
          )}
        </div>
      </div>

      <Separator />

      {/* ── Weight constraints ── */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <FieldLabel
            htmlFor="max-weight"
            label="Max Weight per Asset"
            tooltip="Maximum allocation fraction for any single asset (5–100%)"
          />
          <span className="text-xs tabular-nums text-muted-foreground">
            {(maxWeightPerAsset * 100).toFixed(0)}%
          </span>
        </div>
        <Slider
          id="max-weight"
          min={5}
          max={100}
          step={5}
          value={[maxWeightPerAsset * 100]}
          onValueChange={([v]) => setMaxWeightPerAsset(v / 100)}
          className="w-full"
        />
      </div>

      <Separator />

      {/* ── Lookback period ── */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <FieldLabel
            htmlFor="lookback"
            label="Lookback Period"
            tooltip="Number of trading days of historical data to use"
          />
          <span className="text-xs tabular-nums text-muted-foreground">{lookbackDays}d</span>
        </div>
        <Slider
          id="lookback"
          min={60}
          max={756}
          step={21}
          value={[lookbackDays]}
          onValueChange={([v]) => setLookbackDays(v)}
          className="w-full"
        />
      </div>

      <Separator />

      {/* ── Quantum toggle ── */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Zap className="h-4 w-4 text-violet-500" />
            <FieldLabel
              label="Run Quantum Optimization"
              tooltip="Also run QAOA (Qiskit) and VQE (PennyLane) for comparison. Significantly slower."
            />
          </div>
          <Switch
            checked={runQuantum}
            onCheckedChange={setRunQuantum}
            aria-label="Enable quantum optimization"
          />
        </div>

        {runQuantum && (
          <div className="ml-6 space-y-2">
            <div className="flex items-center justify-between">
              <FieldLabel
                htmlFor="num-assets"
                label="Assets to Select (QUBO)"
                tooltip="Number of assets the quantum algorithm will select from the universe"
              />
              <span className="text-xs tabular-nums text-muted-foreground">
                {numAssetsToSelect}
              </span>
            </div>
            <Slider
              id="num-assets"
              min={2}
              max={Math.min(tickers.length, 10)}
              step={1}
              value={[numAssetsToSelect]}
              onValueChange={([v]) => setNumAssetsToSelect(v)}
              className="w-full"
            />
            {errors.numAssetsToSelect && (
              <p className="text-xs text-destructive">{errors.numAssetsToSelect}</p>
            )}
            <p className="text-xs text-muted-foreground">
              Quantum simulation is slow for &gt;8 assets
            </p>
          </div>
        )}
      </div>

      <Separator />

      {/* ── Submit ── */}
      <Button
        type="submit"
        disabled={isSubmitting}
        className="w-full gap-2"
        size="default"
      >
        {isSubmitting ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            Running Optimization…
          </>
        ) : (
          <>
            <BarChart2 className="h-4 w-4" />
            Run Optimization
          </>
        )}
      </Button>
    </form>
  );
}
