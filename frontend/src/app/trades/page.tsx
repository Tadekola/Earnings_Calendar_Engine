"use client";

import { useEffect, useState } from "react";
import { api, RecommendedTrade } from "@/lib/api";

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
    } catch (err: any) {
      setError(err.message);
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
        <h1 className="text-2xl font-bold">Trade Builder</h1>
        <p className="text-sm text-gray-500">
          View recommended double calendar structure and adjust parameters
        </p>
      </div>

      <form onSubmit={handleSubmit} className="flex items-center gap-3">
        <input
          type="text"
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          placeholder="Enter ticker (e.g. AAPL)"
          className="rounded-lg border border-surface-3 bg-white px-4 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        />
        <button type="submit" disabled={loading || !ticker} className="btn-primary">
          {loading ? "Loading..." : "Build Trade"}
        </button>
      </form>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          {error}
        </div>
      )}

      {trade && (
        <div className="space-y-6">
          {/* Trade Header */}
          <div className="card">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-xl font-bold">{trade.ticker} Double Calendar</h2>
                <p className="text-sm text-gray-500">
                  Spot: ${trade.spot_price.toFixed(2)} | Earnings: {trade.earnings_date} ({trade.earnings_confidence})
                </p>
              </div>
              <span
                className={`rounded-full px-3 py-1 text-xs font-semibold ${
                  trade.classification === "RECOMMEND"
                    ? "bg-emerald-100 text-emerald-800"
                    : trade.classification === "WATCHLIST"
                    ? "bg-amber-100 text-amber-800"
                    : "bg-red-100 text-red-800"
                }`}
              >
                {trade.classification} — {trade.overall_score.toFixed(1)}
              </span>
            </div>
          </div>

          {/* Trade Structure */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div className="card">
              <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">Trade Dates</h3>
              <div className="mt-3 space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-500">Entry Window</span>
                  <span>{trade.entry_date_start} → {trade.entry_date_end}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Planned Exit</span>
                  <span className="font-medium text-brand-700">{trade.planned_exit_date}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Short Expiry</span>
                  <span>{trade.short_expiry}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Long Expiry</span>
                  <span>{trade.long_expiry}</span>
                </div>
              </div>
            </div>

            <div className="card">
              <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">Pricing</h3>
              <div className="mt-3 space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-500">Lower Strike</span>
                  <span className="font-mono">${trade.lower_strike.toFixed(2)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Upper Strike</span>
                  <span className="font-mono">${trade.upper_strike.toFixed(2)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Total Debit (mid)</span>
                  <span className="font-mono font-semibold">${trade.total_debit_mid.toFixed(2)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Debit (pessimistic)</span>
                  <span className="font-mono text-warning">
                    ${trade.total_debit_pessimistic?.toFixed(2) || "N/A"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Max Loss</span>
                  <span className="font-mono text-danger">${trade.estimated_max_loss.toFixed(2)}</span>
                </div>
                {trade.profit_zone_low && trade.profit_zone_high && (
                  <div className="flex justify-between">
                    <span className="text-gray-500">Profit Zone</span>
                    <span className="font-mono text-success">
                      ${trade.profit_zone_low.toFixed(2)} — ${trade.profit_zone_high.toFixed(2)}
                    </span>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Legs Table */}
          <div className="card">
            <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">Trade Legs</h3>
            <div className="mt-3 overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="border-b border-surface-3 text-left text-xs font-medium uppercase text-gray-500">
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
                <tbody className="divide-y divide-surface-2">
                  {trade.legs.map((leg) => (
                    <tr key={leg.leg_number} className="hover:bg-surface-1">
                      <td className="py-2 pr-3 font-mono">{leg.leg_number}</td>
                      <td className="py-2 pr-3">
                        <span className={leg.option_type === "CALL" ? "text-blue-600" : "text-purple-600"}>
                          {leg.option_type}
                        </span>
                      </td>
                      <td className="py-2 pr-3">
                        <span className={leg.side === "BUY" ? "text-emerald-600 font-medium" : "text-red-600 font-medium"}>
                          {leg.side}
                        </span>
                      </td>
                      <td className="py-2 pr-3 font-mono">${leg.strike.toFixed(2)}</td>
                      <td className="py-2 pr-3 text-xs">{leg.expiration}</td>
                      <td className="py-2 pr-3 font-mono">{leg.bid?.toFixed(2) ?? "—"}</td>
                      <td className="py-2 pr-3 font-mono">{leg.ask?.toFixed(2) ?? "—"}</td>
                      <td className="py-2 pr-3 font-mono font-medium">{leg.mid?.toFixed(2) ?? "—"}</td>
                      <td className="py-2 pr-3 font-mono">{leg.implied_volatility ? (leg.implied_volatility * 100).toFixed(1) + "%" : "—"}</td>
                      <td className="py-2 pr-3 font-mono">{leg.delta?.toFixed(3) ?? "—"}</td>
                      <td className="py-2 pr-3 font-mono">{leg.open_interest ?? "—"}</td>
                      <td className="py-2 font-mono">{leg.spread_to_mid ? (leg.spread_to_mid * 100).toFixed(1) + "%" : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Rationale & Risks */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div className="card">
              <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">Rationale</h3>
              <p className="mt-3 text-sm text-gray-700 leading-relaxed">
                {trade.rationale_summary}
              </p>
            </div>
            <div className="card">
              <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">Key Risks</h3>
              <ul className="mt-3 space-y-1">
                {trade.key_risks.map((risk, i) => (
                  <li key={i} className="text-sm text-gray-600">
                    <span className="text-warning mr-1">⚠</span> {risk}
                  </li>
                ))}
              </ul>
            </div>
          </div>

          {/* Risk Disclaimer */}
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
            <p className="text-xs text-amber-800 leading-relaxed">{trade.risk_disclaimer}</p>
          </div>
        </div>
      )}

      {!trade && !loading && !error && (
        <div className="flex h-64 items-center justify-center text-gray-400">
          Enter a ticker to build a double calendar trade
        </div>
      )}
    </div>
  );
}
