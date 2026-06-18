/**
 * ConstraintForm — the primary constraint input form for the Portfolio Optimizer.
 *
 * Sections:
 *   1. Asset Selection   — search + add tickers, display selected as removable badges
 *   2. Budget            — total investment amount (USD)
 *   3. Return & Risk     — min return, max volatility sliders
 *   4. Weight Bounds     — per-asset min/max weight sliders
 *   5. Sector Constraints — add sector + max-weight rows
 *   6. Quantum Settings  — enable/disable quantum, num_assets_to_select, lookback_days
 *   7. Submit            — "Run Optimization" button with loading state
 *
 * The form validates inputs before submission and shows inline error messages.
 * On submit it calls useOptimize().submit() and propagates the run_id upward
 * via the onRunStarted callback.
 *
 * React 19: uses named imports — no `import * as React` needed.
 *
 * Usage:
 *   <ConstraintForm onRunStarted={(runId) => console.log(runId)} />
 */

import {
  useState,
  type ChangeEvent,
  type KeyboardEvent,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  Plus,
  Info,
  Zap,
  TrendingUp,
  DollarSign,
  Settings2,
  ChevronDown,
  ChevronUp,
  Loader2,
  Play,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
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
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

import { AssetSearchCombobox } from "@/components/AssetSearchCombobox";
import { SectorConstraintRow } from "@/components/SectorConstraintRow";
import { TickerBadge } from "@/components/TickerBadge";

import { useOptimize } from "@/hooks/useOptimize";
import { useUIStore } from "@/store/uiStore";
import { formatPercent, formatCurrency } from "@/lib/utils";
import type { OptimizationRequest, SectorConstraint } from "@/types/api";

// ── Constants ──────────────────────────────────────────────────────────────────

const KNOWN_SECTORS = [
  "Technology",
  "Healthcare",
  "Financials",
  "Consumer Discretionary",
  "Consumer Staples",
  "Industrials",
  "Energy",
  "Materials",
  "Real Estate",
  "Utilities",
  "Communication Services",
] as const;

const DEFAULT_BUDGET = 100_000;
const DEFAULT_LOOKBACK_DAYS = 252;
const DEFAULT_NUM_ASSETS = 5;

// ── Types ──────────────────────────────────────────────────────────────────────

interface SelectedAsset {
  ticker: string;
  name: string;
  sector?: string;
}

interface FormErrors {
  tickers?: string;
  budget?: string;
  minReturn?: string;
  maxVolatility?: string;
  maxWeightPerAsset?: string;
  minWeightPerAsset?: string;
  numAssetsToSelect?: string;
  lookbackDays?: string;
  sectorConstraints?: string;
  general?: string;
}

// ── Helper: InfoTooltip ────────────────────────────────────────────────────────

function InfoTooltip({ content }: { content: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          className="ml-1 inline-flex items-center text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label="More information"
        >
          <Info className="h-3.5 w-3.5" />
        </button>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs text-xs">{content}</TooltipContent>
    </Tooltip>
  );
}

// ── Helper: SectionHeader ──────────────────────────────────────────────────────

interface SectionHeaderProps {
  icon: ReactNode;
  title: string;
  description?: string;
  collapsible?: boolean;
  collapsed?: boolean;
  onToggle?: () => void;
}

function SectionHeader({
  icon,
  title,
  description,
  collapsible = false,
  collapsed = false,
  onToggle,
}: SectionHeaderProps) {
  return (
    <div
      className={`flex items-start justify-between ${collapsible ? "cursor-pointer select-none" : ""}`}
      onClick={collapsible ? onToggle : undefined}
      role={collapsible ? "button" : undefined}
      aria-expanded={collapsible ? !collapsed : undefined}
    >
      <div className="flex items-center gap-2">
        <span className="text-primary">{icon}</span>
        <div>
          <h3 className="text-sm font-semibold leading-none">{title}</h3>
          {description && (
            <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
          )}
        </div>
      </div>
      {collapsible && (
        <span className="text-muted-foreground">
          {collapsed ? (
            <ChevronDown className="h-4 w-4" />
          ) : (
            <ChevronUp className="h-4 w-4" />
          )}
        </span>
      )}
    </div>
  );
}

// ── Helper: SliderField ────────────────────────────────────────────────────────

interface SliderFieldProps {
  id: string;
  label: string;
  tooltip?: string;
  value: number | undefined;
  onChange: (value: number | undefined) => void;
  min: number;
  max: number;
  step: number;
  formatValue: (v: number) => string;
  disabled?: boolean;
  optional?: boolean;
  error?: string;
}

function SliderField({
  id,
  label,
  tooltip,
  value,
  onChange,
  min,
  max,
  step,
  formatValue,
  disabled = false,
  optional = false,
  error,
}: SliderFieldProps) {
  const effectiveValue = value ?? min;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <Label htmlFor={id} className="flex items-center">
          {label}
          {optional && (
            <span className="ml-1 text-xs text-muted-foreground">(optional)</span>
          )}
          {tooltip && <InfoTooltip content={tooltip} />}
        </Label>
        <span className="text-sm font-medium tabular-nums text-foreground">
          {value !== undefined ? formatValue(value) : "—"}
        </span>
      </div>
      <Slider
        id={id}
        min={min}
        max={max}
        step={step}
        value={[effectiveValue]}
        onValueChange={([v]) => onChange(v)}
        disabled={disabled}
        aria-label={label}
      />
      {optional && value !== undefined && (
        <button
          type="button"
          onClick={() => onChange(undefined)}
          disabled={disabled}
          className="text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline disabled:pointer-events-none"
        >
          Clear
        </button>
      )}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────────

export interface ConstraintFormProps {
  /**
   * Called when an optimization run is successfully submitted.
   * Receives the new run_id.
   */
  onRunStarted?: (runId: string) => void;
  /** Additional class names for the outer Card. */
  className?: string;
}

export function ConstraintForm({
  onRunStarted,
  className,
}: ConstraintFormProps) {
  // ── Form state ──────────────────────────────────────────────────────────────

  const [selectedAssets, setSelectedAssets] = useState<SelectedAsset[]>([]);
  const [budget, setBudget] = useState<number>(DEFAULT_BUDGET);
  const [budgetInput, setBudgetInput] = useState<string>(
    String(DEFAULT_BUDGET),
  );
  const [minReturn, setMinReturn] = useState<number | undefined>(undefined);
  const [maxVolatility, setMaxVolatility] = useState<number | undefined>(
    undefined,
  );
  const [maxWeightPerAsset, setMaxWeightPerAsset] = useState<
    number | undefined
  >(undefined);
  const [minWeightPerAsset, setMinWeightPerAsset] = useState<
    number | undefined
  >(undefined);
  const [sectorConstraints, setSectorConstraints] = useState<
    SectorConstraint[]
  >([]);
  const [newSector, setNewSector] = useState<string>("");
  const [runQuantum, setRunQuantum] = useState<boolean>(true);
  const [numAssetsToSelect, setNumAssetsToSelect] = useState<number>(
    DEFAULT_NUM_ASSETS,
  );
  const [lookbackDays, setLookbackDays] = useState<number>(
    DEFAULT_LOOKBACK_DAYS,
  );

  // ── Collapsible section state ───────────────────────────────────────────────

  const [advancedCollapsed, setAdvancedCollapsed] = useState(true);
  const [sectorCollapsed, setSectorCollapsed] = useState(true);
  const [quantumCollapsed, setQuantumCollapsed] = useState(false);

  // ── Validation errors ───────────────────────────────────────────────────────

  const [errors, setErrors] = useState<FormErrors>({});

  // ── Hooks ───────────────────────────────────────────────────────────────────

  const { submit, isSubmitting } = useOptimize();
  const isOptimizing = useUIStore((s) => s.isOptimizing);
  const isDisabled = isSubmitting || isOptimizing;

  // ── Asset management ────────────────────────────────────────────────────────

  function handleAssetSelect(
    ticker: string,
    name: string,
    sector?: string,
  ) {
    if (selectedAssets.some((a) => a.ticker === ticker)) return;
    setSelectedAssets((prev) => [...prev, { ticker, name, sector }]);
    // Clear ticker error when user adds an asset
    if (errors.tickers) {
      setErrors((prev) => ({ ...prev, tickers: undefined }));
    }
  }

  function handleAssetRemove(ticker: string) {
    setSelectedAssets((prev) => prev.filter((a) => a.ticker !== ticker));
  }

  // ── Budget management ───────────────────────────────────────────────────────

  function handleBudgetChange(e: ChangeEvent<HTMLInputElement>) {
    setBudgetInput(e.target.value);
  }

  function handleBudgetBlur() {
    const parsed = parseFloat(budgetInput.replace(/,/g, ""));
    if (!isNaN(parsed) && parsed > 0) {
      setBudget(parsed);
      setBudgetInput(String(parsed));
      setErrors((prev) => ({ ...prev, budget: undefined }));
    } else {
      setErrors((prev) => ({
        ...prev,
        budget: "Budget must be a positive number.",
      }));
    }
  }

  function handleBudgetKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") (e.target as HTMLInputElement).blur();
  }

  // ── Sector constraint management ────────────────────────────────────────────

  function handleAddSector() {
    if (!newSector) return;
    if (sectorConstraints.some((sc) => sc.sector === newSector)) {
      setErrors((prev) => ({
        ...prev,
        sectorConstraints: `Sector "${newSector}" is already added.`,
      }));
      return;
    }
    setSectorConstraints((prev) => [
      ...prev,
      { sector: newSector, max_weight: 0.4 },
    ]);
    setNewSector("");
    setErrors((prev) => ({ ...prev, sectorConstraints: undefined }));
    // Auto-expand sector section
    setSectorCollapsed(false);
  }

  function handleSectorChange(sector: string, maxWeight: number) {
    setSectorConstraints((prev) =>
      prev.map((sc) =>
        sc.sector === sector ? { ...sc, max_weight: maxWeight } : sc,
      ),
    );
  }

  function handleSectorRemove(sector: string) {
    setSectorConstraints((prev) => prev.filter((sc) => sc.sector !== sector));
  }

  // ── Validation ──────────────────────────────────────────────────────────────

  function validate(): boolean {
    const newErrors: FormErrors = {};

    if (selectedAssets.length < 2) {
      newErrors.tickers = "Select at least 2 assets to optimize.";
    }

    if (!budget || budget <= 0) {
      newErrors.budget = "Budget must be a positive number.";
    }

    if (
      minReturn !== undefined &&
      maxVolatility !== undefined &&
      minReturn > maxVolatility
    ) {
      newErrors.minReturn =
        "Min return should not exceed max volatility target.";
    }

    if (
      minWeightPerAsset !== undefined &&
      maxWeightPerAsset !== undefined &&
      minWeightPerAsset > maxWeightPerAsset
    ) {
      newErrors.minWeightPerAsset =
        "Min weight per asset cannot exceed max weight per asset.";
    }

    if (runQuantum && numAssetsToSelect > selectedAssets.length) {
      newErrors.numAssetsToSelect = `Cannot select more assets (${numAssetsToSelect}) than available (${selectedAssets.length}).`;
    }

    if (lookbackDays < 30 || lookbackDays > 1825) {
      newErrors.lookbackDays =
        "Lookback period must be between 30 and 1825 days.";
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  }

  // ── Submit ──────────────────────────────────────────────────────────────────

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();

    if (!validate()) return;

    const payload: OptimizationRequest = {
      tickers: selectedAssets.map((a) => a.ticker),
      budget,
      run_quantum: runQuantum,
      lookback_days: lookbackDays,
      ...(minReturn !== undefined && { min_return: minReturn }),
      ...(maxVolatility !== undefined && { max_volatility: maxVolatility }),
      ...(maxWeightPerAsset !== undefined && {
        max_weight_per_asset: maxWeightPerAsset,
      }),
      ...(minWeightPerAsset !== undefined && {
        min_weight_per_asset: minWeightPerAsset,
      }),
      ...(sectorConstraints.length > 0 && {
        sector_constraints: sectorConstraints,
      }),
      ...(runQuantum && { num_assets_to_select: numAssetsToSelect }),
    };

    const runId = await submit(payload);
    if (runId) {
      onRunStarted?.(runId);
    }
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  const selectedTickers = selectedAssets.map((a) => a.ticker);

  return (
    <TooltipProvider delayDuration={300}>
      <Card className={className}>
        <CardHeader className="pb-4">
          <CardTitle className="flex items-center gap-2 text-lg">
            <Settings2 className="h-5 w-5 text-primary" />
            Optimization Constraints
          </CardTitle>
          <CardDescription>
            Configure your portfolio parameters and run classical + quantum
            optimization.
          </CardDescription>
        </CardHeader>

        <CardContent>
          <form onSubmit={handleSubmit} noValidate className="space-y-6">
            {/* ── 1. Asset Selection ─────────────────────────────────────────── */}
            <section aria-labelledby="assets-heading" className="space-y-3">
              <SectionHeader
                icon={<TrendingUp className="h-4 w-4" />}
                title="Asset Selection"
                description="Search and add ticker symbols to your portfolio."
              />

              <AssetSearchCombobox
                selectedTickers={selectedTickers}
                onSelect={handleAssetSelect}
                disabled={isDisabled}
              />

              {/* Selected tickers */}
              {selectedAssets.length > 0 && (
                <div
                  className="flex flex-wrap gap-1.5"
                  role="list"
                  aria-label="Selected assets"
                >
                  {selectedAssets.map((asset) => (
                    <div key={asset.ticker} role="listitem">
                      <TickerBadge
                        ticker={asset.ticker}
                        sector={asset.sector}
                        onRemove={() => handleAssetRemove(asset.ticker)}
                        disabled={isDisabled}
                      />
                    </div>
                  ))}
                </div>
              )}

              {selectedAssets.length === 0 && (
                <p className="text-xs text-muted-foreground">
                  No assets selected. Search above to add tickers.
                </p>
              )}

              {errors.tickers && (
                <p className="text-xs text-destructive" role="alert">
                  {errors.tickers}
                </p>
              )}
            </section>

            <Separator />

            {/* ── 2. Budget ──────────────────────────────────────────────────── */}
            <section aria-labelledby="budget-heading" className="space-y-3">
              <SectionHeader
                icon={<DollarSign className="h-4 w-4" />}
                title="Investment Budget"
                description="Total capital to allocate across the portfolio."
              />

              <div className="space-y-1.5">
                <Label htmlFor="budget" className="flex items-center">
                  Budget (USD)
                  <InfoTooltip content="The total dollar amount to invest. Weights are multiplied by this value to compute per-asset allocations." />
                </Label>
                <div className="relative">
                  <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">
                    $
                  </span>
                  <Input
                    id="budget"
                    type="number"
                    min={1}
                    step={1000}
                    value={budgetInput}
                    onChange={handleBudgetChange}
                    onBlur={handleBudgetBlur}
                    onKeyDown={handleBudgetKeyDown}
                    disabled={isDisabled}
                    className="pl-7"
                    aria-describedby={errors.budget ? "budget-error" : undefined}
                  />
                </div>
                {budget > 0 && (
                  <p className="text-xs text-muted-foreground">
                    {formatCurrency(budget)}
                  </p>
                )}
                {errors.budget && (
                  <p
                    id="budget-error"
                    className="text-xs text-destructive"
                    role="alert"
                  >
                    {errors.budget}
                  </p>
                )}
              </div>
            </section>

            <Separator />

            {/* ── 3. Return & Risk (collapsible) ─────────────────────────────── */}
            <section
              aria-labelledby="risk-return-heading"
              className="space-y-3"
            >
              <SectionHeader
                icon={<TrendingUp className="h-4 w-4" />}
                title="Return & Risk Targets"
                description="Optional annualised constraints."
                collapsible
                collapsed={advancedCollapsed}
                onToggle={() => setAdvancedCollapsed((v) => !v)}
              />

              {!advancedCollapsed && (
                <div className="space-y-5 pt-1">
                  <SliderField
                    id="min-return"
                    label="Minimum Return"
                    tooltip="Minimum acceptable annualised portfolio return. The optimizer will reject solutions below this threshold."
                    value={minReturn}
                    onChange={setMinReturn}
                    min={0}
                    max={0.5}
                    step={0.005}
                    formatValue={(v) => formatPercent(v)}
                    disabled={isDisabled}
                    optional
                    error={errors.minReturn}
                  />

                  <SliderField
                    id="max-volatility"
                    label="Maximum Volatility"
                    tooltip="Maximum acceptable annualised portfolio volatility (standard deviation). Lower values mean a more conservative portfolio."
                    value={maxVolatility}
                    onChange={setMaxVolatility}
                    min={0.01}
                    max={0.8}
                    step={0.005}
                    formatValue={(v) => formatPercent(v)}
                    disabled={isDisabled}
                    optional
                    error={errors.maxVolatility}
                  />

                  <Separator className="my-1" />

                  <SliderField
                    id="max-weight"
                    label="Max Weight per Asset"
                    tooltip="Maximum fraction of the portfolio that can be allocated to any single asset. Prevents over-concentration."
                    value={maxWeightPerAsset}
                    onChange={setMaxWeightPerAsset}
                    min={0.01}
                    max={1}
                    step={0.01}
                    formatValue={(v) => formatPercent(v)}
                    disabled={isDisabled}
                    optional
                    error={errors.maxWeightPerAsset}
                  />

                  <SliderField
                    id="min-weight"
                    label="Min Weight per Asset"
                    tooltip="Minimum fraction allocated to any asset that is included in the portfolio. Prevents negligible positions."
                    value={minWeightPerAsset}
                    onChange={setMinWeightPerAsset}
                    min={0}
                    max={0.5}
                    step={0.005}
                    formatValue={(v) => formatPercent(v)}
                    disabled={isDisabled}
                    optional
                    error={errors.minWeightPerAsset}
                  />
                </div>
              )}
            </section>

            <Separator />

            {/* ── 4. Sector Constraints (collapsible) ────────────────────────── */}
            <section
              aria-labelledby="sector-heading"
              className="space-y-3"
            >
              <SectionHeader
                icon={<Settings2 className="h-4 w-4" />}
                title="Sector Constraints"
                description={
                  sectorConstraints.length > 0
                    ? `${sectorConstraints.length} sector limit${sectorConstraints.length > 1 ? "s" : ""} configured`
                    : "Optional sector-level allocation caps."
                }
                collapsible
                collapsed={sectorCollapsed}
                onToggle={() => setSectorCollapsed((v) => !v)}
              />

              {!sectorCollapsed && (
                <div className="space-y-3 pt-1">
                  {/* Add sector row */}
                  <div className="flex gap-2">
                    <Select
                      value={newSector}
                      onValueChange={setNewSector}
                      disabled={isDisabled}
                    >
                      <SelectTrigger
                        className="flex-1"
                        aria-label="Select sector to add"
                      >
                        <SelectValue placeholder="Select a sector…" />
                      </SelectTrigger>
                      <SelectContent>
                        {KNOWN_SECTORS.filter(
                          (s) =>
                            !sectorConstraints.some((sc) => sc.sector === s),
                        ).map((sector) => (
                          <SelectItem key={sector} value={sector}>
                            {sector}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      onClick={handleAddSector}
                      disabled={isDisabled || !newSector}
                      aria-label="Add sector constraint"
                    >
                      <Plus className="h-4 w-4" />
                    </Button>
                  </div>

                  {errors.sectorConstraints && (
                    <p className="text-xs text-destructive" role="alert">
                      {errors.sectorConstraints}
                    </p>
                  )}

                  {/* Sector constraint rows */}
                  {sectorConstraints.length > 0 ? (
                    <div className="space-y-2">
                      {sectorConstraints.map((sc) => (
                        <SectorConstraintRow
                          key={sc.sector}
                          sector={sc.sector}
                          maxWeight={sc.max_weight}
                          onChange={handleSectorChange}
                          onRemove={handleSectorRemove}
                          disabled={isDisabled}
                        />
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      No sector constraints added. Select a sector above to
                      cap its allocation.
                    </p>
                  )}
                </div>
              )}
            </section>

            <Separator />

            {/* ── 5. Quantum Settings ─────────────────────────────────────────── */}
            <section
              aria-labelledby="quantum-heading"
              className="space-y-3"
            >
              <SectionHeader
                icon={<Zap className="h-4 w-4" />}
                title="Quantum Optimization"
                description="QAOA (Qiskit) + VQE-style (PennyLane) on local simulators."
                collapsible
                collapsed={quantumCollapsed}
                onToggle={() => setQuantumCollapsed((v) => !v)}
              />

              {!quantumCollapsed && (
                <div className="space-y-5 pt-1">
                  {/* Enable quantum toggle */}
                  <div className="flex items-center justify-between rounded-md border border-border bg-card px-3 py-2.5">
                    <div>
                      <Label
                        htmlFor="run-quantum"
                        className="cursor-pointer font-medium"
                      >
                        Enable Quantum Optimization
                      </Label>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        Runs QAOA and VQE alongside classical Markowitz MVO.
                      </p>
                    </div>
                    <Switch
                      id="run-quantum"
                      checked={runQuantum}
                      onCheckedChange={setRunQuantum}
                      disabled={isDisabled}
                      aria-label="Enable quantum optimization"
                    />
                  </div>

                  {runQuantum && (
                    <>
                      {/* Number of assets to select */}
                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <Label
                            htmlFor="num-assets"
                            className="flex items-center"
                          >
                            Assets to Select (QUBO)
                            <InfoTooltip content="The number of assets the quantum QUBO formulation will select from your universe. Fewer assets = fewer qubits = faster simulation." />
                          </Label>
                          <span className="text-sm font-medium tabular-nums">
                            {numAssetsToSelect}
                          </span>
                        </div>
                        <Slider
                          id="num-assets"
                          min={2}
                          max={Math.max(2, selectedAssets.length)}
                          step={1}
                          value={[
                            Math.min(
                              numAssetsToSelect,
                              Math.max(2, selectedAssets.length),
                            ),
                          ]}
                          onValueChange={([v]) => setNumAssetsToSelect(v)}
                          disabled={isDisabled}
                          aria-label="Number of assets to select for quantum optimization"
                        />
                        <p className="text-xs text-muted-foreground">
                          {selectedAssets.length > 0
                            ? `Selecting ${Math.min(numAssetsToSelect, selectedAssets.length)} of ${selectedAssets.length} assets`
                            : "Add assets above to configure this setting"}
                        </p>
                        {errors.numAssetsToSelect && (
                          <p className="text-xs text-destructive" role="alert">
                            {errors.numAssetsToSelect}
                          </p>
                        )}
                      </div>
                    </>
                  )}

                  {/* Lookback period */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label
                        htmlFor="lookback-days"
                        className="flex items-center"
                      >
                        Historical Lookback
                        <InfoTooltip content="Number of trading days of historical price data used to compute returns and covariance. 252 days ≈ 1 trading year." />
                      </Label>
                      <span className="text-sm font-medium tabular-nums">
                        {lookbackDays}d
                      </span>
                    </div>
                    <Slider
                      id="lookback-days"
                      min={30}
                      max={1825}
                      step={30}
                      value={[lookbackDays]}
                      onValueChange={([v]) => setLookbackDays(v)}
                      disabled={isDisabled}
                      aria-label="Historical lookback period in days"
                    />
                    <div className="flex justify-between text-xs text-muted-foreground">
                      <span>30d (1 mo)</span>
                      <span>252d (1 yr)</span>
                      <span>1825d (5 yr)</span>
                    </div>
                    {errors.lookbackDays && (
                      <p className="text-xs text-destructive" role="alert">
                        {errors.lookbackDays}
                      </p>
                    )}
                  </div>
                </div>
              )}
            </section>

            <Separator />

            {/* ── Submit ──────────────────────────────────────────────────────── */}
            <div className="space-y-3">
              {errors.general && (
                <p className="text-xs text-destructive" role="alert">
                  {errors.general}
                </p>
              )}

              {/* Summary line */}
              {selectedAssets.length >= 2 && (
                <div className="rounded-md bg-muted/50 px-3 py-2 text-xs text-muted-foreground">
                  <span className="font-medium text-foreground">
                    {selectedAssets.length} assets
                  </span>{" "}
                  · Budget:{" "}
                  <span className="font-medium text-foreground">
                    {formatCurrency(budget)}
                  </span>
                  {runQuantum && (
                    <>
                      {" "}
                      · Quantum:{" "}
                      <span className="font-medium text-foreground">
                        QAOA + VQE
                      </span>
                    </>
                  )}
                </div>
              )}

              <Button
                type="submit"
                className="w-full"
                disabled={isDisabled || selectedAssets.length < 2}
                aria-label="Run portfolio optimization"
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Submitting…
                  </>
                ) : isOptimizing ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Optimizing…
                  </>
                ) : (
                  <>
                    <Play className="mr-2 h-4 w-4" />
                    Run Optimization
                  </>
                )}
              </Button>

              {isOptimizing && (
                <p className="text-center text-xs text-muted-foreground">
                  Optimization in progress — results will appear on the right.
                </p>
              )}
            </div>
          </form>
        </CardContent>
      </Card>
    </TooltipProvider>
  );
}
