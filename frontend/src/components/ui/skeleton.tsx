/**
 * Skeleton component — shadcn/ui implementation.
 *
 * Provides animated placeholder elements for loading states.
 * Used while fetching optimization results, run history, and asset data.
 *
 * Usage:
 *   <Skeleton className="h-4 w-[250px]" />
 *   <Skeleton className="h-12 w-12 rounded-full" />
 *
 *   // Card skeleton:
 *   <div className="space-y-2">
 *     <Skeleton className="h-4 w-full" />
 *     <Skeleton className="h-4 w-3/4" />
 *     <Skeleton className="h-4 w-1/2" />
 *   </div>
 */

import { cn } from "@/lib/utils";

function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("animate-pulse rounded-md bg-muted", className)}
      {...props}
    />
  );
}

export { Skeleton };
