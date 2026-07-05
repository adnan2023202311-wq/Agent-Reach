import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const dotVariants = cva("relative inline-flex rounded-full", {
  variants: {
    tone: {
      success: "bg-success",
      warning: "bg-warning",
      destructive: "bg-destructive",
      info: "bg-info",
      accent: "bg-accent",
      neutral: "bg-muted-foreground",
    },
    size: {
      sm: "size-1.5",
      md: "size-2",
      lg: "size-2.5",
    },
  },
  defaultVariants: { tone: "neutral", size: "md" },
});

export interface StatusIndicatorProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof dotVariants> {
  /** Adds a subtle animated pulse ring — for "live" states. */
  pulse?: boolean;
  /** Optional label rendered next to the dot. */
  label?: string;
}

export const StatusIndicator = React.forwardRef<HTMLSpanElement, StatusIndicatorProps>(
  ({ tone, size, pulse, label, className, ...props }, ref) => {
    return (
      <span
        ref={ref}
        className={cn("inline-flex items-center gap-2 text-xs text-muted-foreground", className)}
        {...props}
      >
        <span className="relative inline-flex items-center justify-center">
          {pulse && (
            <span
              className={cn(
                dotVariants({ tone, size: "lg" }),
                "absolute opacity-60 animate-ping",
              )}
              aria-hidden
            />
          )}
          <span className={cn(dotVariants({ tone, size }))} aria-hidden />
        </span>
        {label && <span className="text-foreground/80">{label}</span>}
      </span>
    );
  },
);
StatusIndicator.displayName = "StatusIndicator";
