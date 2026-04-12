"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, RecommendedTrade } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, classificationVariant } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CardSkeleton } from "@/components/ui/skeleton";
import PayoffDiagram from "@/components/charts/PayoffDiagram";
import GreeksSummary from "@/components/GreeksSummary";
import {
  Wrench,
  Loader2,
  CalendarDays,
  DollarSign,
  AlertTriangle,
  FileText,
  ShieldAlert,
  Search,
} from "lucide-react";

export default function TradesPage() {
  const [ticker, setTicker] = useState("");
  const [trade, setTrade] = useState<RecommendedTrade | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const t = params.get("ticker");
    if (t) {
      setTicker(t.toUpperCase());
      loadTrade(t.toUpperCase());
    }
  }, []);

  async function loadTrade(t: string) {
    setLoading(true);
    setError(null);
    try {
      const result = await api.recommendedTrade(t);
      setTrade(result);
      toast.success(`Trade built for ${t} — ${result.strategy_type || "Double Calendar"}`);
    } catch (err: any) {
      setError(err.message);
      toast.error(`Trade build failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (ticker.trim()) loadTrade(ticker.trim().toUpperCase());
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-gray-900 dark:text-gray-100">Trade Builder</h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          View recommended trade structure with P&L analysis
        </p>
      </div>

      <form onSubmit={handleSubmit} className="flex items-center gap-3">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            value={ticker}
            onChange={(e) => setTicker(e.target.value.toUpperCase())}
            placeholder="Enter ticker (e.g. AAPL)"
            className="rounded-lg border border-surface-3 bg-white pl-9 pr-4 py-2.5 text-sm font-medium focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
          />
        </div>
        <Button type="submit" disabled={loading || !ticker}>
          {loading ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Building...
            </>
          ) : (
            <>
              <Wrench className="h-4 w-4" />
              Build Trade
            </>
          )}
        </Button>
      </form>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
          {error}
        </div>
      )}

      {loading && (
        <div className="space-y-6">
          <CardSkeleton />
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <CardSkeleton />
            <CardSkeleton />
          </div>
        </div>
      )}

      {trade && !loading && (
        <div className="space-y-6">
          {/* Trade Header */}
          <Card>
            <CardContent className="p-6">
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-3">
                    <h2 className="text-xl font-bold tracking-tight text-gray-900 dark:text-gray-100">
                      {trade.ticker}
                    </h2>
                    <Badge variant="strategy" className="text-xs">
                      {trade.strategy_type ? trade.strategy_type.replace(/_/g, ' ') : 'Double Calendar'}
                    </Badge>
                  </div>
                  <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                    Spot: <span className="font-mono font-semibold text-gray-700 dark:text-gray-200">${trade.spot_price.toFixed(2)}</span>
                    {" | "}Earnings: <span className="font-mono font-semibold text-gray-700 dark:text-gray-200">{trade.earnings_date}</span>
                    {" ("}
                    <Badge variant={trade.earnings_confidence === "CONFIRMED" ? "confirmed" : "estimated"} className="ml-0.5">
                      {trade.earnings_confidence}
                    </Badge>
                    {")"}
                  </p>
                  {(trade.layer_id || trade.account_id) && (
                    <div className="flex gap-2 mt-2">
                      {trade.layer_id && <Badge variant="layer">{trade.layer_id}</Badge>}
                      {trade.account_id && <Badge variant="account">{trade.account_id}</Badge>}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant={classificationVariant(trade.classification)} className="text-sm px-3 py-1">
                    {trade.classification}
                  </Badge>
                  <span className={`font-mono text-xl font-bold ${
                    trade.overall_score >= 70 ? "text-emerald-600" : trade.overall_score >= 40 ? "text-amber-600" : "text-red-500"
                  }`}>
                    {trade.overall_score.toFixed(1)}
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* P&L Payoff Diagram */}
          <Card>
            <CardContent className="p-6">
              <PayoffDiagram trade={trade} height={300} />
            </CardContent>
          </Card>

          {/* Greeks Summary */}
          <GreeksSummary legs={trade.legs} />

          {/* Trade Structure */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader className="pb-3">
                <div className="flex items-center gap-2">
                  <CalendarDays className="h-4 w-4 text-brand-600" />
                  <CardTitle className="text-sm uppercase tracking-wide">Trade Dates</CardTitle>
                </div>
              </CardHeader>
              <CardContent>
                <div className="space-y-2.5 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-500 dark:text-gray-400">Entry Window</span>
                    <span className="font-mono text-gray-900 dark:text-gray-100">{trade.entry_date_start} → {trade.entry_date_end}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500 dark:text-gray-400">Planned Exit</span>
                    <span className="font-mono font-semibold text-brand-700 dark:text-brand-400">{trade.planned_exit_date}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500 dark:text-gray-400">Short Expiry</span>
                    <span className="font-mono text-gray-900 dark:text-gray-100">{trade.short_expiry}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500 dark:text-gray-400">Long Expiry</span>
                    <span className="font-mono text-gray-900 dark:text-gray-100">{trade.long_expiry}</span>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-3">
                <div className="flex items-center gap-2">
                  <DollarSign className="h-4 w-4 text-emerald-600" />
                  <CardTitle className="text-sm uppercase tracking-wide">Pricing</CardTitle>
                </div>
              </CardHeader>
              <CardContent>
                <div className="space-y-2.5 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-500 dark:text-gray-400">Lower Strike</span>
                    <span className="font-mono text-gray-900 dark:text-gray-100">${trade.lower_strike.toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500 dark:text-gray-400">Upper Strike</span>
                    <span className="font-mono text-gray-900 dark:text-gray-100">${trade.upper_strike.toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between border-t border-surface-3 pt-2 dark:border-gray-600">
                    <span className="text-gray-500 dark:text-gray-400">Total Debit (mid)</span>
                    <span className="font-mono font-semibold text-gray-900 dark:text-gray-100">${trade.total_debit_mid.toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500 dark:text-gray-400">Debit (pessimistic)</span>
                    <span className="font-mono font-semibold text-amber-600">${trade.total_debit_pessimistic?.toFixed(2) || "N/A"}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500 dark:text-gray-400">Max Loss</span>
                    <span className="font-mono font-bold text-red-600">${trade.estimated_max_loss.toFixed(2)}</span>
                  </div>
                  {trade.profit_zone_low && trade.profit_zone_high && (
                    <div className="flex justify-between">
                      <span className="text-gray-500 dark:text-gray-400">Profit Zone</span>
                      <span className="font-mono font-semibold text-emerald-600">
                        ${trade.profit_zone_low.toFixed(2)} — ${trade.profit_zone_high.toFixed(2)}
                      </span>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Legs Table */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm uppercase tracking-wide">Trade Legs</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="border-b border-surface-3 text-left text-[10px] font-medium uppercase tracking-wider text-gray-400 dark:border-gray-600">
                      <th className="pb-2 pr-3">#</th>
                      <th className="pb-2 pr-3">Type</th>
                      <th className="pb-2 pr-3">Side</th>
                      <th className="pb-2 pr-3">Strike</th>
                      <th className="pb-2 pr-3">Expiry</th>
                      <th className="pb-2 pr-3">Bid</th>
                      <th className="pb-2 pr-3">Ask</th>
                      <th className="pb-2 pr-3">Mid</th>
                      <th className="pb-2 pr-3">IV</th>
                      <th className="pb-2 pr-3">Delta</th>
                      <th className="pb-2 pr-3">OI</th>
                      <th className="pb-2">Spread/Mid</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-surface-2 dark:divide-gray-700">
                    {trade.legs.map((leg) => (
                      <tr key={leg.leg_number} className="transition-colors hover:bg-surface-1 dark:hover:bg-gray-700/50">
                        <td className="py-2.5 pr-3 font-mono text-gray-500">{leg.leg_number}</td>
                        <td className="py-2.5 pr-3">
                          <Badge variant={leg.option_type === "CALL" ? "default" : "outline"} className={leg.option_type === "CALL" ? "bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300" : "bg-purple-50 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300"}>
                            {leg.option_type}
                          </Badge>
                        </td>
                        <td className="py-2.5 pr-3">
                          <span className={`font-semibold ${leg.side === "BUY" ? "text-emerald-600" : "text-red-600"}`}>
                            {leg.side}
                          </span>
                        </td>
                        <td className="py-2.5 pr-3 font-mono font-medium text-gray-900 dark:text-gray-100">${leg.strike.toFixed(2)}</td>
                        <td className="py-2.5 pr-3 font-mono text-xs text-gray-600 dark:text-gray-300">{leg.expiration}</td>
                        <td className="py-2.5 pr-3 font-mono text-gray-600 dark:text-gray-300">{leg.bid?.toFixed(2) ?? "—"}</td>
                        <td className="py-2.5 pr-3 font-mono text-gray-600 dark:text-gray-300">{leg.ask?.toFixed(2) ?? "—"}</td>
                        <td className="py-2.5 pr-3 font-mono font-semibold text-gray-900 dark:text-gray-100">{leg.mid?.toFixed(2) ?? "—"}</td>
                        <td className="py-2.5 pr-3 font-mono text-gray-600 dark:text-gray-300">{leg.implied_volatility ? (leg.implied_volatility * 100).toFixed(1) + "%" : "—"}</td>
                        <td className="py-2.5 pr-3 font-mono text-gray-600 dark:text-gray-300">{leg.delta?.toFixed(3) ?? "—"}</td>
                        <td className="py-2.5 pr-3 font-mono text-gray-600 dark:text-gray-300">{leg.open_interest?.toLocaleString() ?? "—"}</td>
                        <td className="py-2.5 font-mono text-gray-600 dark:text-gray-300">{leg.spread_to_mid ? (leg.spread_to_mid * 100).toFixed(1) + "%" : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          {/* Rationale & Risks */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader className="pb-3">
                <div className="flex items-center gap-2">
                  <FileText className="h-4 w-4 text-brand-600" />
                  <CardTitle className="text-sm uppercase tracking-wide">Rationale</CardTitle>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-sm leading-relaxed text-gray-700 dark:text-gray-300">
                  {trade.rationale_summary}
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-3">
                <div className="flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 text-amber-500" />
                  <CardTitle className="text-sm uppercase tracking-wide">Key Risks</CardTitle>
                </div>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2">
                  {trade.key_risks.map((risk, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-gray-600 dark:text-gray-300">
                      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-amber-500" />
                      {risk}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          </div>

          {/* Risk Disclaimer */}
          <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-900/20">
            <ShieldAlert className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600 dark:text-amber-400" />
            <p className="text-xs leading-relaxed text-amber-800 dark:text-amber-300">{trade.risk_disclaimer}</p>
          </div>
        </div>
      )}

      {!trade && !loading && !error && (
        <div className="flex h-64 flex-col items-center justify-center text-gray-400 dark:text-gray-500">
          <Wrench className="mb-3 h-10 w-10 text-gray-300 dark:text-gray-600" />
          <p className="text-sm">Enter a ticker to build a recommended trade</p>
        </div>
      )}
    </div>
  );
}
