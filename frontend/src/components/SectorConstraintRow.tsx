/**
 * SectorConstraintRow — a single row in the sector constraints table.
 *
 * Displays a sector name with a max-weight slider and numeric input.
 * The slider and input are kept in sync — editing either updates both.
 *
 * React 19: uses named imports — no `import * as React` needed.
 *
 * Usage:
 *   <SectorConstraintRow
 *     sector="Technology"
 *     maxWeight={0.4}
 *     onChange={(sector, maxWeight) => updateSectorConstraint(sector, maxWeight)}
 *     onRemove={(sector) => removeSectorConstraint(sector)}
 *     disabled={isOptimizing}
 *   />
 */

import {
  useState,
  useEffect,
  type ChangeEvent,
  type KeyboardEvent,
} from "react";
import { Trash2 } from "lucide-react";
import { Slider } from "@/components/ui/slider";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface SectorConstraintRowProps {
  /** The sector name (e.g. "Technology"). */
  sector: string;
  /** Current max weight value (0.0–1.0). */
  maxWeight: number;
  /** Called when the max weight changes. */
  onChange: (sector: string, maxWeight: number) => void;
  /** Called when the user removes this sector constraint. */
  onRemove: (sector: string) => void;
  /** When true, all controls are disabled. */
  disabled?: boolean;
  /** Additional class names for the row container. */
  className?: string;
}

/** Formats a weight (0.0–1.0) as a whole-number percentage string. */
function formatWeight(w: number): string {
  return (w * 100).toFixed(0);
}

/** Clamps a weight value to the valid range [0.01, 1.0]. */
function clamp(value: number): number {
  return Math.min(1, Math.max(0.01, value));
}

export function SectorConstraintRow({
  sector,
  maxWeight,
  onChange,
  onRemove,
  disabled = false,
  className,
}: SectorConstraintRowProps) {
  // Local input string state so the user can type freely without clamping mid-edit
  const [inputValue, setInputValue] = useState(
    formatWeight(maxWeight),
  );

  // Keep local input in sync when maxWeight changes externally
  useEffect(() => {
    setInputValue(formatWeight(maxWeight));
  }, [maxWeight]);

  function handleSliderChange(values: number[]) {
    const newWeight = values[0];
    onChange(sector, newWeight);
    setInputValue(formatWeight(newWeight));
  }

  function handleInputChange(e: ChangeEvent<HTMLInputElement>) {
    setInputValue(e.target.value);
  }

  function handleInputBlur() {
    const parsed = parseFloat(inputValue);
    if (!isNaN(parsed)) {
      const clamped = clamp(parsed / 100);
      onChange(sector, clamped);
      setInputValue(formatWeight(clamped));
    } else {
      // Reset to current value if invalid
      setInputValue(formatWeight(maxWeight));
    }
  }

  function handleInputKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      (e.target as HTMLInputElement).blur();
    }
  }

  return (
    <div
      className={cn(
        "flex items-center gap-3 rounded-md border border-border bg-card px-3 py-2",
        disabled && "opacity-60",
        className,
      )}
    >
      {/* Sector name */}
      <span className="w-28 shrink-0 truncate text-sm font-medium">
        {sector}
      </span>

      {/* Slider */}
      <div className="flex-1">
        <Slider
          min={0.01}
          max={1}
          step={0.01}
          value={[maxWeight]}
          onValueChange={handleSliderChange}
          disabled={disabled}
          aria-label={`Max weight for ${sector}`}
        />
      </div>

      {/* Numeric input (percentage) */}
      <div className="relative w-20 shrink-0">
        <Input
          type="number"
          min={1}
          max={100}
          step={1}
          value={inputValue}
          onChange={handleInputChange}
          onBlur={handleInputBlur}
          onKeyDown={handleInputKeyDown}
          disabled={disabled}
          className="pr-6 text-right text-sm"
          aria-label={`Max weight percentage for ${sector}`}
        />
        <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-xs text-muted-foreground">
          %
        </span>
      </div>

      {/* Remove button */}
      <Button
        type="button"
        variant="ghost"
        size="icon"
        onClick={() => onRemove(sector)}
        disabled={disabled}
        aria-label={`Remove ${sector} constraint`}
        className="h-8 w-8 shrink-0 text-muted-foreground hover:text-destructive"
      >
        <Trash2 className="h-4 w-4" />
      </Button>
    </div>
  );
}
