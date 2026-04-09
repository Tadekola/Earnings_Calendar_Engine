"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, ExplainResponse, RecommendedTrade } from "@/lib/api";

function classificationBadge(c: string) {
  if (c === "RECOMMEND") return "badge-recommend";
  if (c === "WATCHLIST") return "badge-watchlist";
  return "badge-no-trade";
}

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
      <div className="flex h-64 items-center justify-center text-gray-500">
        Loading {ticker}...
      </div>
    );
  }

  if (error && !explain && !trade) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold">{ticker}</h1>
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          {error}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h1 className="text-2xl font-bold">{ticker}</h1>
          {explain && (
            <>
              <span className={classificationBadge(explain.classification)}>
                {explain.classification}
              </span>
              {explain.overall_score !== null && (
                <span className={`text-lg font-mono font-semibold ${scoreColor(explain.overall_score)}`}>
                  {explain.overall_score.toFixed(1)}
                </span>
              )}
            </>
          )}
        </div>
        <div className="flex items-center gap-3">
          <div className="inline-flex rounded-md shadow-sm" role="group">
            <button
              type="button"
              onClick={() => setSelectedStrategy("DOUBLE_CALENDAR")}
              className={`px-4 py-2 text-sm font-medium border border-gray-200 rounded-l-lg hover:bg-gray-100 hover:text-blue-700 focus:z-10 focus:ring-2 focus:ring-blue-700 focus:text-blue-700 ${
                selectedStrategy === "DOUBLE_CALENDAR" ? "bg-blue-50 text-blue-700" : "bg-white text-gray-900"
              }`}
            >
              Double Calendar
            </button>
            <button
              type="button"
              onClick={() => setSelectedStrategy("BUTTERFLY")}
              className={`px-4 py-2 text-sm font-medium border border-gray-200 rounded-r-lg hover:bg-gray-100 hover:text-blue-700 focus:z-10 focus:ring-2 focus:ring-blue-700 focus:text-blue-700 ${
                selectedStrategy === "BUTTERFLY" ? "bg-blue-50 text-blue-700" : "bg-white text-gray-900"
              }`}
            >
              Iron Butterfly
            </button>
          </div>
          <a
            href={`/trades?ticker=${ticker}`}
            className="btn-primary"
          >
            View Trade →
          </a>
        </div>
      </div>

      {/* Recommendation Rationale */}
      {explain?.recommendation_rationale && (
        <div className="card">
          <p className="text-sm text-gray-700 dark:text-gray-200 leading-relaxed font-medium">
            {explain.recommendation_rationale}
          </p>
        </div>
      )}

      {/* Score Breakdown */}
      {explain && explain.factors.length > 0 && (
        <div className="card">
          <h2 className="text-lg font-semibold mb-4">Score Breakdown</h2>
          <div className="space-y-3">
            {explain.factors.map((f) => (
              <div key={f.factor}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-medium text-gray-700">{f.factor}</span>
                  <div className="flex items-center gap-3">
                    <span className={`font-mono text-sm ${scoreColor(f.score)}`}>
                      {f.score.toFixed(0)}
                    </span>
                    <span className="text-xs text-gray-400">w{f.weight.toFixed(0)}</span>
                    <span className="font-mono text-xs text-gray-500">
                      +{f.weighted_contribution.toFixed(1)}
                    </span>
                  </div>
                </div>
                <div className="h-2 rounded-full bg-surface-2">
                  <div
                    className={`h-2 rounded-full transition-all ${
                      f.score >= 70
                        ? "bg-emerald-500"
                        : f.score >= 40
                        ? "bg-amber-500"
                        : "bg-red-400"
                    }`}
                    style={{ width: `${f.score}%` }}
                  />
                </div>
                <p className="mt-1 text-xs text-gray-500">{f.explanation}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Trade Summary */}
      {trade && (
        <div className="card">
          <h2 className="text-lg font-semibold mb-4">Recommended Trade</h2>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div className="rounded-md bg-surface-1 dark:bg-gray-700/50 p-3">
              <p className="text-xs text-gray-500 dark:text-gray-400">Spot Price</p>
              <p className="text-lg font-semibold">${trade.spot_price.toFixed(2)}</p>
            </div>
            <div className="rounded-md bg-surface-1 dark:bg-gray-700/50 p-3">
              <p className="text-xs text-gray-500 dark:text-gray-400">Total Debit</p>
              <p className="text-lg font-semibold">${trade.total_debit_mid.toFixed(2)}</p>
            </div>
            <div className="rounded-md bg-surface-1 dark:bg-gray-700/50 p-3">
              <p className="text-xs text-gray-500 dark:text-gray-400">Max Loss</p>
              <p className="text-lg font-semibold text-red-600 dark:text-red-400">${trade.estimated_max_loss.toFixed(2)}</p>
            </div>
            <div className="rounded-md bg-surface-1 dark:bg-gray-700/50 p-3">
              <p className="text-xs text-gray-500 dark:text-gray-400">Earnings</p>
              <p className="text-lg font-semibold">{trade.earnings_date}</p>
            </div>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div>
              <p className="text-xs text-gray-500 dark:text-gray-400">Lower Strike</p>
              <p className="font-mono font-medium">${trade.lower_strike}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500 dark:text-gray-400">Upper Strike</p>
              <p className="font-mono font-medium">${trade.upper_strike}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500 dark:text-gray-400">Profit Zone</p>
              <p className="font-mono font-medium text-emerald-600 dark:text-emerald-400">
                ${trade.profit_zone_low?.toFixed(1) ?? "0.0"} - ${trade.profit_zone_high?.toFixed(1) ?? "0.0"}
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-500 dark:text-gray-400">Expirations</p>
              <p className="font-mono font-medium">
                {trade.short_expiry} / {trade.long_expiry}
              </p>
            </div>
          </div>

          {/* Legs */}
          <div className="mt-4">
            <h3 className="text-sm font-semibold text-gray-600 mb-2">Legs</h3>
            <div className="overflow-x-auto">
              <table className="min-w-full text-xs">
                <thead>
                  <tr className="border-b border-surface-3 text-left uppercase text-gray-500">
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
                <tbody className="divide-y divide-surface-2">
                  {trade.legs.map((l) => (
                    <tr key={l.leg_number}>
                      <td className="py-2 pr-3 font-mono">{l.leg_number}</td>
                      <td className="py-2 pr-3">{l.option_type}</td>
                      <td className={`py-2 pr-3 font-medium ${l.side === "BUY" ? "text-emerald-600" : "text-red-500"}`}>
                        {l.side}
                      </td>
                      <td className="py-2 pr-3 font-mono">${l.strike}</td>
                      <td className="py-2 pr-3">{l.expiration}</td>
                      <td className="py-2 pr-3 font-mono">{l.bid?.toFixed(2) ?? "—"}</td>
                      <td className="py-2 pr-3 font-mono">{l.ask?.toFixed(2) ?? "—"}</td>
                      <td className="py-2 pr-3 font-mono">{l.mid?.toFixed(2) ?? "—"}</td>
                      <td className="py-2 font-mono">{l.implied_volatility ? (l.implied_volatility * 100).toFixed(1) + "%" : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Risk Warnings */}
      {explain && explain.risk_warnings.length > 0 && (
        <div className="card border-amber-200 bg-amber-50">
          <h2 className="text-sm font-semibold text-amber-800 mb-2">Risk Warnings</h2>
          <ul className="space-y-1">
            {explain.risk_warnings.map((w, i) => (
              <li key={i} className="text-xs text-amber-700">⚠ {w}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Data Quality Notes */}
      {explain && explain.data_quality_notes.length > 0 && (
        <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
          <h2 className="text-sm font-semibold text-blue-800 mb-1">Data Quality</h2>
          <ul className="space-y-1">
            {explain.data_quality_notes.map((n, i) => (
              <li key={i} className="text-xs text-blue-700">{n}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
