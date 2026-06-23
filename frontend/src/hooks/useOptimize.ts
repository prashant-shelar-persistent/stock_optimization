/**
 * useOptimize — custom hook that wraps the optimization submission flow.
 *
 * Responsibilities:
 *   1. Accepts an OptimizationRequest payload
 *   2. Calls submitOptimization() from @/lib/api
 *   3. Updates uiStore with the new run_id and sets isOptimizing = true
 *   4. Shows success/error toast notifications via useToast
 *
 * Returns: { submit, isSubmitting, error }
 */

import { useState, useCallback } from "react";
import { submitOptimization } from "@/lib/api";
import { useUIStore } from "@/store/uiStore";
import { useToast } from "@/hooks/use-toast";
import type { OptimizationRequest } from "@/types/api";

interface UseOptimizeReturn {
  /**
   * Submit an optimization request.
   * Resolves with the run_id on success, or null on failure.
   */
  submit: (payload: OptimizationRequest) => Promise<string | null>;

  /** True while the HTTP POST is in flight. */
  isSubmitting: boolean;

  /** The last submission error, or null if the last submission succeeded. */
  error: Error | null;
}

export function useOptimize(): UseOptimizeReturn {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const startNewRun = useUIStore((s) => s.startNewRun);
  const { toast } = useToast();

  const submit = useCallback(
    async (payload: OptimizationRequest): Promise<string | null> => {
      setIsSubmitting(true);
      setError(null);

      try {
        const { run_id, ws_token } = await submitOptimization(payload);

        // Transition the global store into "running" state for this run
        // Pass ws_token so the WebSocket can authenticate with the backend
        startNewRun(run_id, ws_token);

        toast({
          title: "Optimization started",
          description: `Run ${run_id.slice(0, 8)}… is now queued.`,
        });

        return run_id;
      } catch (err) {
        const castErr = err instanceof Error ? err : new Error(String(err));
        setError(castErr);

        toast({
          variant: "destructive",
          title: "Submission failed",
          description: castErr.message,
        });

        return null;
      } finally {
        setIsSubmitting(false);
      }
    },
    [startNewRun, toast],
  );

  return { submit, isSubmitting, error };
}
