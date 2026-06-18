/**
 * Progress component — shadcn/ui implementation using Radix UI Progress.
 *
 * Displays a progress bar for optimization run progress, loading states,
 * and agent pipeline completion percentage.
 *
 * Usage:
 *   <Progress value={60} />
 *   <Progress value={progress} className="h-2" />
 *
 * @param value - Progress percentage (0–100). Null/undefined shows indeterminate state.
 */

import * as React from "react";
import * as ProgressPrimitive from "@radix-ui/react-progress";
import { cn } from "@/lib/utils";

function Progress({
  className,
  value,
  ...props
}: React.ComponentProps<typeof ProgressPrimitive.Root>) {
  return (
    <ProgressPrimitive.Root
      className={cn(
        "relative h-4 w-full overflow-hidden rounded-full bg-secondary",
        className,
      )}
      {...props}
    >
      <ProgressPrimitive.Indicator
        className="h-full w-full flex-1 bg-primary transition-all"
        style={{ transform: `translateX(-${100 - (value ?? 0)}%)` }}
      />
    </ProgressPrimitive.Root>
  );
}

export { Progress };
