"use client";

import { TradeLeg } from "@/lib/api";
import { TrendingUp, TrendingDown, Clock, Zap, Activity } from "lucide-react";

interface Props {
  legs: TradeLeg[];
}

interface GreekRow {
  label: string;
  value: number | null;
  icon: React.ReactNode;
  description: string;
  color: string;
}

export default function GreeksSummary({ legs }: Props) {
  const netDelta = legs.reduce((sum, l) => {
    const d = l.delta ?? 0;
    return sum + (l.side === "BUY" ? d : -d);
  }, 0);

  // Gamma, theta, vega are not always available from the API
  // but we'll show what we can compute
  const greeks: GreekRow[] = [
    {
      label: "Net Delta",
      value: netDelta,
      icon: netDelta >= 0 ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />,
      description: "Directional exposure per $1 move",
      color: Math.abs(netDelta) < 0.1 ? "text-emerald-600" : Math.abs(netDelta) < 0.3 ? "text-amber-600" : "text-red-600",
    },
  ];

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {greeks.map((g) => (
        <div
          key={g.label}
          className="flex items-center gap-3 rounded-lg border border-surface-3 bg-surface-1 p-3 dark:border-gray-700 dark:bg-gray-700/50"
        >
          <div className={`flex h-9 w-9 items-center justify-center rounded-lg bg-white shadow-sm dark:bg-gray-800 ${g.color}`}>
            {g.icon}
          </div>
          <div>
            <p className="text-xs text-gray-500 dark:text-gray-400">{g.label}</p>
            <p className={`font-mono text-lg font-semibold ${g.color}`}>
              {g.value !== null ? g.value.toFixed(3) : "—"}
            </p>
          </div>
        </div>
      ))}
      {/* Structural summary */}
      <div className="flex items-center gap-3 rounded-lg border border-surface-3 bg-surface-1 p-3 dark:border-gray-700 dark:bg-gray-700/50">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-white shadow-sm dark:bg-gray-800 text-brand-600">
          <Activity className="h-4 w-4" />
        </div>
        <div>
          <p className="text-xs text-gray-500 dark:text-gray-400">Legs</p>
          <p className="font-mono text-lg font-semibold text-gray-900 dark:text-gray-100">
            {legs.length}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-3 rounded-lg border border-surface-3 bg-surface-1 p-3 dark:border-gray-700 dark:bg-gray-700/50">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-white shadow-sm dark:bg-gray-800 text-emerald-600">
          <TrendingUp className="h-4 w-4" />
        </div>
        <div>
          <p className="text-xs text-gray-500 dark:text-gray-400">Long Legs</p>
          <p className="font-mono text-lg font-semibold text-emerald-600">
            {legs.filter((l) => l.side === "BUY").length}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-3 rounded-lg border border-surface-3 bg-surface-1 p-3 dark:border-gray-700 dark:bg-gray-700/50">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-white shadow-sm dark:bg-gray-800 text-red-600">
          <TrendingDown className="h-4 w-4" />
        </div>
        <div>
          <p className="text-xs text-gray-500 dark:text-gray-400">Short Legs</p>
          <p className="font-mono text-lg font-semibold text-red-600">
            {legs.filter((l) => l.side === "SELL").length}
          </p>
        </div>
      </div>
    </div>
  );
}
