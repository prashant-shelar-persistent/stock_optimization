/**
 * Separator component — shadcn/ui implementation using Radix UI Separator.
 *
 * Provides a visual divider between sections. Supports both horizontal
 * (default) and vertical orientations.
 *
 * Usage:
 *   <Separator />
 *   <Separator orientation="vertical" className="h-6" />
 */

import * as React from "react";
import * as SeparatorPrimitive from "@radix-ui/react-separator";
import { cn } from "@/lib/utils";

function Separator({
  className,
  orientation = "horizontal",
  decorative = true,
  ...props
}: React.ComponentProps<typeof SeparatorPrimitive.Root>) {
  return (
    <SeparatorPrimitive.Root
      decorative={decorative}
      orientation={orientation}
      className={cn(
        "shrink-0 bg-border",
        orientation === "horizontal" ? "h-[1px] w-full" : "h-full w-[1px]",
        className,
      )}
      {...props}
    />
  );
}

export { Separator };
