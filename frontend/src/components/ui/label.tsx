/**
 * Label component — shadcn/ui implementation using Radix UI Label.
 *
 * Provides an accessible form label that is associated with its control
 * via the `htmlFor` prop. Automatically styles as disabled when the
 * associated control is disabled.
 *
 * Usage:
 *   <Label htmlFor="budget">Investment Budget (USD)</Label>
 *   <Input id="budget" type="number" />
 */

import * as React from "react";
import * as LabelPrimitive from "@radix-ui/react-label";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const labelVariants = cva(
  "text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70",
);

const Label = React.forwardRef<
  React.ElementRef<typeof LabelPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof LabelPrimitive.Root> &
    VariantProps<typeof labelVariants>
>(({ className, ...props }, ref) => (
  <LabelPrimitive.Root
    ref={ref}
    className={cn(labelVariants(), className)}
    {...props}
  />
));
Label.displayName = LabelPrimitive.Root.displayName;

export { Label };
