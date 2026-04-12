import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold transition-colors",
  {
    variants: {
      variant: {
        default: "bg-brand-100 text-brand-800 dark:bg-brand-900/30 dark:text-brand-300",
        recommend: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300",
        watchlist: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300",
        notrade: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300",
        healthy: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300",
        degraded: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300",
        critical: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300",
        outline: "border border-surface-4 text-gray-700 dark:border-gray-600 dark:text-gray-300",
        strategy: "rounded bg-blue-50 px-1.5 py-0.5 text-[10px] font-medium text-blue-700 tracking-wide uppercase dark:bg-blue-900/30 dark:text-blue-300",
        layer: "rounded bg-purple-50 px-1.5 py-0.5 text-[10px] font-bold text-purple-700 uppercase tracking-wider dark:bg-purple-900/30 dark:text-purple-300",
        account: "rounded bg-gray-100 px-1.5 py-0.5 text-[10px] font-medium text-gray-600 uppercase tracking-wider dark:bg-gray-700 dark:text-gray-300",
        confirmed: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300",
        estimated: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

function classificationVariant(c: string): BadgeProps["variant"] {
  if (c === "RECOMMEND") return "recommend";
  if (c === "WATCHLIST") return "watchlist";
  return "notrade";
}

function severityVariant(s: string): BadgeProps["variant"] {
  if (s === "HEALTHY") return "healthy";
  if (s === "DEGRADED") return "degraded";
  return "critical";
}

function confidenceVariant(c: string): BadgeProps["variant"] {
  if (c === "CONFIRMED") return "confirmed";
  return "estimated";
}

export { Badge, badgeVariants, classificationVariant, severityVariant, confidenceVariant };
