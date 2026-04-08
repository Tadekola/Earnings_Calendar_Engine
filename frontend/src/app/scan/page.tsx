"use client";

import { useState } from "react";
import { api, ScanRunResponse, ScanResult } from "@/lib/api";

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

export default function ScanResultsPage() {
  const [scanRun, setScanRun] = useState<ScanRunResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filterClass, setFilterClass] = useState<string>("ALL");
  const [sortBy, setSortBy] = useState<"score" | "ticker">("score");
  const [expanded, setExpanded] = useState<string | null>(null);

  async function runScan() {
    setLoading(true);
    setError(null);
    try {
      const result = await api.runScan();
      setScanRun(result);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function filteredResults(): ScanResult[] {
    if (!scanRun) return [];
    let results = [...scanRun.results];
    if (filterClass !== "ALL") {
      results = results.filter((r) => r.classification === filterClass);
    }
    if (sortBy === "score") {
      results.sort((a, b) => (b.overall_score || 0) - (a.overall_score || 0));
    } else if (sortBy === "ticker") {
      results.sort((a, b) => a.ticker.localeCompare(b.ticker));
    }
    return results;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Scan Results</h1>
          <p className="text-sm text-gray-500">
            Run a scan to evaluate the universe for double calendar opportunities
          </p>
        </div>
        <button onClick={runScan} disabled={loading} className="btn-primary">
          {loading ? "Scanning..." : "Run Scan"}
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          {error}
        </div>
      )}

      {scanRun && (
        <>
          {/* Summary bar */}
          <div className="flex flex-wrap items-center gap-6 rounded-lg bg-white p-4 shadow-sm border border-surface-3">
            <div className="text-sm">
              <span className="text-gray-500">Run:</span>{" "}
              <span className="font-mono text-xs">{scanRun.run_id.slice(0, 8)}</span>
            </div>
            <div className="text-sm">
              <span className="text-gray-500">Scanned:</span>{" "}
              <span className="font-semibold">{scanRun.total_scanned}</span>
            </div>
            <div className="text-sm">
              <span className="text-emerald-600 font-semibold">{scanRun.total_recommended}</span>
              <span className="text-gray-500 ml-1">recommend</span>
            </div>
            <div className="text-sm">
              <span className="text-amber-600 font-semibold">{scanRun.total_watchlist}</span>
              <span className="text-gray-500 ml-1">watchlist</span>
            </div>
            <div className="text-sm">
              <span className="text-red-600 font-semibold">{scanRun.total_rejected}</span>
              <span className="text-gray-500 ml-1">rejected</span>
            </div>
            <div className="ml-auto text-xs text-gray-400">
              Mode: {scanRun.operating_mode} | v{scanRun.scoring_version}
            </div>
          </div>

          {/* Filters */}
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <label className="text-xs font-medium text-gray-500">Filter:</label>
              {["ALL", "RECOMMEND", "WATCHLIST", "NO_TRADE"].map((c) => (
                <button
                  key={c}
                  onClick={() => setFilterClass(c)}
                  className={`rounded-full px-3 py-1 text-xs font-medium transition ${
                    filterClass === c
                      ? "bg-brand-700 text-white"
                      : "bg-surface-2 text-gray-600 hover:bg-surface-3"
                  }`}
                >
                  {c.replace("_", " ")}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-2 ml-auto">
              <label className="text-xs font-medium text-gray-500">Sort:</label>
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as "score" | "ticker")}
                className="rounded-md border border-surface-3 bg-white px-2 py-1 text-xs"
              >
                <option value="score">Score</option>
                <option value="ticker">Ticker</option>
              </select>
            </div>
          </div>

          {/* Results */}
          <div className="space-y-2">
            {filteredResults().map((r) => (
              <div key={r.ticker} className="card">
                <div
                  className="flex items-center gap-4 cursor-pointer"
                  onClick={() => setExpanded(expanded === r.ticker ? null : r.ticker)}
                >
                  <div className="w-16">
                    <a
                      href={`/trades?ticker=${r.ticker}`}
                      className="font-semibold text-brand-700 hover:underline"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {r.ticker}
                    </a>
                  </div>
                  <div className="w-16 font-mono text-sm">
                    {r.overall_score !== null ? (
                      <span className={scoreColor(r.overall_score)}>
                        {r.overall_score.toFixed(1)}
                      </span>
                    ) : (
                      "—"
                    )}
                  </div>
                  <div className="w-28 flex flex-col gap-1">
                    <span className={classificationBadge(r.classification)}>
                      {r.classification}
                    </span>
                    {r.strategy_type && (
                      <span className="inline-flex rounded bg-blue-50 px-1.5 py-0.5 text-[10px] font-medium text-blue-700 tracking-wide uppercase w-fit">
                        {r.strategy_type.replace('_', ' ')}
                      </span>
                    )}
                  </div>
                  <div className="flex-1 truncate text-xs text-gray-600">
                    {r.rationale_summary || (r.rejection_reasons || []).join("; ")}
                  </div>
                  <div className="text-xs text-gray-400">
                    {r.processing_time_ms !== null ? `${r.processing_time_ms}ms` : ""}
                  </div>
                  <div className="text-gray-400">
                    {expanded === r.ticker ? "▲" : "▼"}
                  </div>
                </div>

                {expanded === r.ticker && (
                  <div className="mt-4 border-t border-surface-2 pt-4 space-y-4">
                    {/* Score Breakdown */}
                    {r.score_breakdown && r.score_breakdown.length > 0 && (
                      <div>
                        <h4 className="text-xs font-semibold uppercase text-gray-500 mb-2">
                          Score Breakdown
                        </h4>
                        <div className="space-y-2">
                          {r.score_breakdown.map((f) => (
                            <div key={f.factor} className="flex items-center gap-3">
                              <div className="w-44 text-xs text-gray-700">{f.factor}</div>
                              <div className="flex-1">
                                <div className="h-2 rounded-full bg-surface-2">
                                  <div
                                    className={`h-2 rounded-full ${
                                      f.raw_score >= 70
                                        ? "bg-emerald-500"
                                        : f.raw_score >= 40
                                        ? "bg-amber-500"
                                        : "bg-red-400"
                                    }`}
                                    style={{ width: `${f.raw_score}%` }}
                                  />
                                </div>
                              </div>
                              <div className="w-12 text-right font-mono text-xs">
                                {f.raw_score.toFixed(0)}
                              </div>
                              <div className="w-10 text-right font-mono text-xs text-gray-400">
                                w{f.weight.toFixed(0)}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Risk Warnings */}
                    {r.risk_warnings && r.risk_warnings.length > 0 && (
                      <div>
                        <h4 className="text-xs font-semibold uppercase text-gray-500 mb-1">
                          Risk Warnings
                        </h4>
                        <ul className="space-y-1">
                          {r.risk_warnings.map((w, i) => (
                            <li key={i} className="text-xs text-amber-700">
                              ⚠ {w}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Rejection Reasons */}
                    {r.rejection_reasons && r.rejection_reasons.length > 0 && (
                      <div>
                        <h4 className="text-xs font-semibold uppercase text-gray-500 mb-1">
                          Rejection Reasons
                        </h4>
                        <ul className="space-y-1">
                          {r.rejection_reasons.map((reason, i) => (
                            <li key={i} className="text-xs text-red-600">
                              ✕ {reason}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Actions */}
                    <div className="flex gap-2 pt-2">
                      <a
                        href={`/trades?ticker=${r.ticker}`}
                        className="rounded-md bg-brand-50 px-3 py-1.5 text-xs font-medium text-brand-700 hover:bg-brand-100"
                      >
                        View Trade →
                      </a>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      {!scanRun && !loading && (
        <div className="flex h-64 items-center justify-center text-gray-400">
          Run a scan to see results
        </div>
      )}
    </div>
  );
}
