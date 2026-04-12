"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, ExplainResponse, RecommendedTrade } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, classificationVariant } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CardSkeleton, KPICardSkeleton } from "@/components/ui/skeleton";
import PayoffDiagram from "@/components/charts/PayoffDiagram";
import GreeksSummary from "@/components/GreeksSummary";
import {
  ArrowRight,
  AlertTriangle,
  Info,
  DollarSign,
} from "lucide-react";

function scoreColor(score: number) {
  if (score >= 70) return "text-emerald-600";
  if (score >= 40) return "text-amber-600";
  return "text-red-500";
}

export default function CandidateDetailPage() {
  const params = useParams();
  const ticker = (params.ticker as string)?.toUpperCase() || "";

  const [explain, setExplain] = useState<ExplainResponse | null>(null);
  const [trade, setTrade] = useState<RecommendedTrade | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedStrategy, setSelectedStrategy] = useState<string>("DOUBLE_CALENDAR");

  useEffect(() => {
    if (!ticker) return;
    loadData(selectedStrategy);
  }, [ticker, selectedStrategy]);

  async function loadData(strategy: string) {
    setLoading(true);
    setError(null);
    try {
      const [explainData, tradeData] = await Promise.allSettled([
        api.explain(ticker, strategy),
        api.recommendedTrade(ticker, strategy),
      ]);
      if (explainData.status === "fulfilled") setExplain(explainData.value);
      if (tradeData.status === "fulfilled") setTrade(tradeData.value);
      if (explainData.status === "rejected" && tradeData.status === "rejected") {
        setError(explainData.reason?.message || "Failed to load data");
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="h-8 w-32 rounded bg-surface-3 animate-pulse-subtle" />
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {[1, 2, 3, 4].map((i) => <KPICardSkeleton key={i} />)}
        </div>
        <CardSkeleton />
        <CardSkeleton />
      </div>
    );
  }

  if (error && !explain && !trade) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold tracking-tight text-gray-900 dark:text-gray-100">{ticker}</h1>
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
          {error}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold tracking-tight text-gray-900 dark:text-gray-100">{ticker}</h1>
          {trade && trade.layer_id && <Badge variant="layer">{trade.layer_id}</Badge>}
          {trade && trade.account_id && <Badge variant="account">{trade.account_id}</Badge>}
          {explain && (
            <>
              <Badge variant={classificationVariant(explain.classification)}>{explain.classification}</Badge>
              {explain.overall_score !== null && (
                <span className={`font-mono text-xl font-bold ${scoreColor(explain.overall_score)}`}>
                  {explain.overall_score.toFixed(1)}
                </span>
              )}
            </>
          )}
        </div>
        <div className="flex items-center gap-3">
          <div className="inline-flex rounded-lg border border-surface-3 dark:border-gray-600" role="group">
            <button
              type="button"
              onClick={() => setSelectedStrategy("DOUBLE_CALENDAR")}
              className={`px-4 py-2 text-sm font-medium rounded-l-lg transition ${
                selectedStrategy === "DOUBLE_CALENDAR"
                  ? "bg-brand-50 text-brand-700 dark:bg-brand-900/30 dark:text-brand-300"
                  : "bg-white text-gray-600 hover:bg-surface-1 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700"
              }`}
            >
              Double Calendar
            </button>
            <button
              type="button"
              onClick={() => setSelectedStrategy("BUTTERFLY")}
              className={`px-4 py-2 text-sm font-medium rounded-r-lg transition ${
                selectedStrategy === "BUTTERFLY"
                  ? "bg-brand-50 text-brand-700 dark:bg-brand-900/30 dark:text-brand-300"
                  : "bg-white text-gray-600 hover:bg-surface-1 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700"
              }`}
            >
              Iron Butterfly
            </button>
          </div>
          <Button asChild>
            <a href={`/trades?ticker=${ticker}`}>
              View Trade <ArrowRight className="h-4 w-4" />
            </a>
          </Button>
        </div>
      </div>

      {/* Recommendation Rationale */}
      {explain?.recommendation_rationale && (
        <Card className="border-brand-200 bg-brand-50/50 dark:border-brand-800 dark:bg-brand-900/10">
          <CardContent className="p-5">
            <p className="text-sm leading-relaxed font-medium text-gray-800 dark:text-gray-200">
              {explain.recommendation_rationale}
            </p>
          </CardContent>
        </Card>
      )}

      {/* Score Breakdown */}
      {explain && explain.factors.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Score Breakdown</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {explain.factors.map((f) => (
                <div key={f.factor}>
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-gray-700 dark:text-gray-200">
                      {f.factor}
                    </span>
                    <div className="flex items-center gap-3 text-xs text-gray-500 dark:text-gray-400">
                      <span className={`font-semibold ${scoreColor(f.score)}`}>
                        {Math.round(f.score)}
                      </span>
                      <span className="font-mono">w{f.weight}</span>
                      <span className="font-mono">+{f.weighted_contribution.toFixed(1)}</span>
                    </div>
                  </div>
                  <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-surface-3 dark:bg-gray-700">
                    <div
                      className={`h-full transition-all ${
                        f.score >= 70 ? "bg-emerald-500" : f.score >= 40 ? "bg-amber-500" : "bg-red-400"
                      }`}
                      style={{ width: `${Math.max(0, Math.min(100, f.score))}%` }}
                    />
                  </div>
                  <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{f.explanation}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* P&L Payoff + Greeks */}
      {trade && (
        <>
          <Card>
            <CardContent className="p-6">
              <PayoffDiagram trade={trade} height={280} />
            </CardContent>
          </Card>

          <GreeksSummary legs={trade.legs} />
        </>
      )}

      {/* Trade Summary */}
      {trade && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <DollarSign className="h-4 w-4 text-emerald-600" />
              <CardTitle>Recommended Trade</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <div className="rounded-lg bg-surface-1 p-3 dark:bg-gray-700/50">
                <p className="text-[10px] font-medium uppercase tracking-wider text-gray-400">Spot Price</p>
                <p className="mt-0.5 font-mono text-lg font-semibold text-gray-900 dark:text-gray-100">${trade.spot_price.toFixed(2)}</p>
              </div>
              <div className="rounded-lg bg-surface-1 p-3 dark:bg-gray-700/50">
                <p className="text-[10px] font-medium uppercase tracking-wider text-gray-400">Total Debit</p>
                <p className="mt-0.5 font-mono text-lg font-semibold text-gray-900 dark:text-gray-100">${trade.total_debit_mid.toFixed(2)}</p>
              </div>
              <div className="rounded-lg bg-surface-1 p-3 dark:bg-gray-700/50">
                <p className="text-[10px] font-medium uppercase tracking-wider text-gray-400">Max Loss</p>
                <p className="mt-0.5 font-mono text-lg font-semibold text-red-600 dark:text-red-400">${trade.estimated_max_loss.toFixed(2)}</p>
              </div>
              <div className="rounded-lg bg-surface-1 p-3 dark:bg-gray-700/50">
                <p className="text-[10px] font-medium uppercase tracking-wider text-gray-400">Earnings</p>
                <p className="mt-0.5 font-mono text-lg font-semibold text-gray-900 dark:text-gray-100">{trade.earnings_date}</p>
              </div>
            </div>

            <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
              <div>
                <p className="text-[10px] font-medium uppercase tracking-wider text-gray-400">Lower Strike</p>
                <p className="font-mono font-medium text-gray-900 dark:text-gray-100">${trade.lower_strike}</p>
              </div>
              <div>
                <p className="text-[10px] font-medium uppercase tracking-wider text-gray-400">Upper Strike</p>
                <p className="font-mono font-medium text-gray-900 dark:text-gray-100">${trade.upper_strike}</p>
              </div>
              <div>
                <p className="text-[10px] font-medium uppercase tracking-wider text-gray-400">Profit Zone</p>
                <p className="font-mono font-medium text-emerald-600 dark:text-emerald-400">
                  ${trade.profit_zone_low?.toFixed(1) ?? "0.0"} - ${trade.profit_zone_high?.toFixed(1) ?? "0.0"}
                </p>
              </div>
              <div>
                <p className="text-[10px] font-medium uppercase tracking-wider text-gray-400">Expirations</p>
                <p className="font-mono font-medium text-gray-900 dark:text-gray-100">
                  {trade.short_expiry} / {trade.long_expiry}
                </p>
              </div>
            </div>

            {/* Legs */}
            <div className="mt-6">
              <h3 className="text-[10px] font-semibold uppercase tracking-wider text-gray-400 mb-2">Legs</h3>
              <div className="overflow-x-auto">
                <table className="min-w-full text-xs">
                  <thead>
                    <tr className="border-b border-surface-3 text-left text-[10px] uppercase tracking-wider text-gray-400 dark:border-gray-600">
                      <th className="pb-2 pr-3">#</th>
                      <th className="pb-2 pr-3">Type</th>
                      <th className="pb-2 pr-3">Side</th>
                      <th className="pb-2 pr-3">Strike</th>
                      <th className="pb-2 pr-3">Expiry</th>
                      <th className="pb-2 pr-3">Bid</th>
                      <th className="pb-2 pr-3">Ask</th>
                      <th className="pb-2 pr-3">Mid</th>
                      <th className="pb-2">IV</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-surface-2 dark:divide-gray-700">
                    {trade.legs.map((l) => (
                      <tr key={l.leg_number} className="transition-colors hover:bg-surface-1 dark:hover:bg-gray-700/50">
                        <td className="py-2 pr-3 font-mono text-gray-500">{l.leg_number}</td>
                        <td className="py-2 pr-3">
                          <Badge variant={l.option_type === "CALL" ? "default" : "outline"} className={l.option_type === "CALL" ? "bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300" : "bg-purple-50 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300"}>
                            {l.option_type}
                          </Badge>
                        </td>
                        <td className={`py-2 pr-3 font-semibold ${l.side === "BUY" ? "text-emerald-600" : "text-red-500"}`}>
                          {l.side}
                        </td>
                        <td className="py-2 pr-3 font-mono font-medium text-gray-900 dark:text-gray-100">${l.strike}</td>
                        <td className="py-2 pr-3 font-mono text-gray-600 dark:text-gray-300">{l.expiration}</td>
                        <td className="py-2 pr-3 font-mono text-gray-600 dark:text-gray-300">{l.bid?.toFixed(2) ?? "—"}</td>
                        <td className="py-2 pr-3 font-mono text-gray-600 dark:text-gray-300">{l.ask?.toFixed(2) ?? "—"}</td>
                        <td className="py-2 pr-3 font-mono font-semibold text-gray-900 dark:text-gray-100">{l.mid?.toFixed(2) ?? "—"}</td>
                        <td className="py-2 font-mono text-gray-600 dark:text-gray-300">{l.implied_volatility ? (l.implied_volatility * 100).toFixed(1) + "%" : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Risk Warnings */}
      {explain && explain.risk_warnings.length > 0 && (
        <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-900/20">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600 dark:text-amber-400" />
          <div>
            <h2 className="text-sm font-semibold text-amber-800 dark:text-amber-300 mb-1">Risk Warnings</h2>
            <ul className="space-y-1">
              {explain.risk_warnings.map((w, i) => (
                <li key={i} className="text-xs text-amber-700 dark:text-amber-400">{w}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* Data Quality Notes */}
      {explain && explain.data_quality_notes.length > 0 && (
        <div className="flex items-start gap-3 rounded-lg border border-blue-200 bg-blue-50 p-4 dark:border-blue-800 dark:bg-blue-900/20">
          <Info className="mt-0.5 h-4 w-4 flex-shrink-0 text-blue-600 dark:text-blue-400" />
          <div>
            <h2 className="text-sm font-semibold text-blue-800 dark:text-blue-300 mb-1">Data Quality</h2>
            <ul className="space-y-1">
              {explain.data_quality_notes.map((n, i) => (
                <li key={i} className="text-xs text-blue-700 dark:text-blue-400">{n}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
