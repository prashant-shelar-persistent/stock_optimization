/**
 * QuantumCircuitInfo — Displays quantum circuit metadata for QAOA/VQE results.
 *
 * Shows:
 *   - Number of qubits
 *   - Circuit depth (QAOA only)
 *   - Selected assets (binary selection from QUBO)
 *   - Solve time
 *
 * Props:
 *   type         — "qaoa" | "vqe"
 *   numQubits    — number of qubits used
 *   circuitDepth — circuit depth (QAOA only)
 *   solveTimeMs  — solve time in milliseconds
 *   selectedAssets — list of selected ticker symbols
 *
 * React 19.2: Uses function components with typed props (no forwardRef needed).
 * JSX transform is handled automatically via react-jsx in tsconfig.
 */

import { Badge } from "@/components/ui/badge";
import { Cpu, Clock, Layers, Zap } from "lucide-react";

// ── Types ─────────────────────────────────────────────────────────────────────

interface QuantumCircuitInfoProps {
  type: "qaoa" | "vqe";
  numQubits: number;
  circuitDepth?: number;
  solveTimeMs: number;
  selectedAssets: string[];
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatSolveTime(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`;
  return `${(ms / 60_000).toFixed(1)} min`;
}

// ── Main component ────────────────────────────────────────────────────────────

export function QuantumCircuitInfo({
  type,
  numQubits,
  circuitDepth,
  solveTimeMs,
  selectedAssets,
}: QuantumCircuitInfoProps) {
  const label = type === "qaoa" ? "QAOA" : "VQE";
  const framework = type === "qaoa" ? "Qiskit" : "PennyLane";

  return (
    <div className="rounded-lg border bg-muted/30 p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center gap-2">
        <Zap className="h-4 w-4 text-violet-500" />
        <span className="text-sm font-semibold">
          {label} Circuit Info
        </span>
        <Badge variant="outline" className="ml-auto text-xs">
          {framework}
        </Badge>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {/* Qubits */}
        <div className="flex items-center gap-2">
          <Cpu className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
          <div>
            <p className="text-xs text-muted-foreground">Qubits</p>
            <p className="text-sm font-semibold tabular-nums">{numQubits}</p>
          </div>
        </div>

        {/* Circuit depth (QAOA only) */}
        {circuitDepth !== undefined && (
          <div className="flex items-center gap-2">
            <Layers className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
            <div>
              <p className="text-xs text-muted-foreground">Circuit Depth</p>
              <p className="text-sm font-semibold tabular-nums">{circuitDepth}</p>
            </div>
          </div>
        )}

        {/* Solve time */}
        <div className="flex items-center gap-2">
          <Clock className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
          <div>
            <p className="text-xs text-muted-foreground">Solve Time</p>
            <p className="text-sm font-semibold tabular-nums">
              {formatSolveTime(solveTimeMs)}
            </p>
          </div>
        </div>
      </div>

      {/* Selected assets */}
      {selectedAssets.length > 0 && (
        <div>
          <p className="mb-1.5 text-xs text-muted-foreground">
            Selected Assets ({selectedAssets.length})
          </p>
          <div className="flex flex-wrap gap-1.5">
            {selectedAssets.map((ticker) => (
              <Badge
                key={ticker}
                variant="quantum"
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
