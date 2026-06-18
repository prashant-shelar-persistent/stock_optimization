/**
 * Input component — shadcn/ui implementation.
 *
 * A styled HTML input element with consistent focus, disabled, and
 * placeholder states. Supports all standard HTML input attributes.
 *
 * React 19: ref is passed as a plain prop — no forwardRef wrapper needed.
 *
 * Usage:
 *   <Input type="text" placeholder="Enter ticker symbol..." />
 *   <Input type="number" min={0} max={1} step={0.01} />
 */

import * as React from "react";
import { cn } from "@/lib/utils";

export type InputProps = React.ComponentProps<"input">;

function Input({ className, type, ...props }: InputProps) {
  return (
    <input
      type={type}
      className={cn(
        "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}
Input.displayName = "Input";

export { Input };
