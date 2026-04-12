"use client";

import { useState } from "react";
import { api, ScanRunResponse, ScanResult } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, classificationVariant } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CardSkeleton, KPICardSkeleton } from "@/components/ui/skeleton";
import ScoreDistribution from "@/components/charts/ScoreDistribution";
import {
  Play,
  Loader2,
  ChevronDown,
  ChevronUp,
  ArrowRight,
  Search,
  AlertTriangle,
  XCircle,
  BarChart3,
} from "lucide-react";

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
          <h1 className="text-2xl font-bold tracking-tight text-gray-900 dark:text-gray-100">Scan Results</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Evaluate the universe for options trade opportunities
          </p>
        </div>
        <Button onClick={runScan} disabled={loading}>
          {loading ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Scanning...
            </>
          ) : (
            <>
              <Play className="h-4 w-4" />
              Run Scan
            </>
          )}
        </Button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
          {error}
        </div>
      )}

      {loading && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            {[1, 2, 3, 4].map((i) => <KPICardSkeleton key={i} />)}
          </div>
          {[1, 2, 3].map((i) => <CardSkeleton key={i} />)}
        </div>
      )}

      {scanRun && !loading && (
        <>
          {/* Summary bar */}
          <Card>
            <CardContent className="flex flex-wrap items-center gap-6 p-4">
              <div className="text-sm">
                <span className="text-gray-500 dark:text-gray-400">Run:</span>{" "}
                <span className="font-mono text-xs text-gray-900 dark:text-gray-100">{scanRun.run_id.slice(0, 8)}</span>
              </div>
              <div className="text-sm">
                <span className="text-gray-500 dark:text-gray-400">Scanned:</span>{" "}
                <span className="font-semibold text-gray-900 dark:text-gray-100">{scanRun.total_scanned}</span>
              </div>
              <div className="text-sm">
                <span className="font-semibold text-emerald-600">{scanRun.total_recommended}</span>
                <span className="text-gray-500 dark:text-gray-400 ml-1">recommend</span>
              </div>
              <div className="text-sm">
                <span className="font-semibold text-amber-600">{scanRun.total_watchlist}</span>
                <span className="text-gray-500 dark:text-gray-400 ml-1">watchlist</span>
              </div>
              <div className="text-sm">
                <span className="font-semibold text-red-500">{scanRun.total_rejected}</span>
                <span className="text-gray-500 dark:text-gray-400 ml-1">rejected</span>
              </div>
              <div className="ml-auto text-xs text-gray-400">
                Mode: {scanRun.operating_mode} | v{scanRun.scoring_version}
              </div>
            </CardContent>
          </Card>

          {/* Score Distribution Chart */}
          {scanRun.results.filter((r) => r.overall_score != null).length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <div className="flex items-center gap-2">
                  <BarChart3 className="h-4 w-4 text-brand-600" />
                  <CardTitle>Score Distribution</CardTitle>
                </div>
              </CardHeader>
              <CardContent>
                <ScoreDistribution results={scanRun.results} height={200} />
              </CardContent>
            </Card>
          )}

          {/* Filters */}
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <label className="text-xs font-medium text-gray-500 dark:text-gray-400">Filter:</label>
              {["ALL", "RECOMMEND", "WATCHLIST", "NO_TRADE"].map((c) => (
                <button
                  key={c}
                  onClick={() => setFilterClass(c)}
                  className={`rounded-full px-3 py-1 text-xs font-medium transition ${
                    filterClass === c
                      ? "bg-brand-700 text-white"
                      : "bg-surface-2 text-gray-600 hover:bg-surface-3 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600"
                  }`}
                >
                  {c.replace("_", " ")}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-2 ml-auto">
              <label className="text-xs font-medium text-gray-500 dark:text-gray-400">Sort:</label>
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as "score" | "ticker")}
                className="rounded-md border border-surface-3 bg-white px-2 py-1 text-xs dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
              >
                <option value="score">Score</option>
                <option value="ticker">Ticker</option>
              </select>
            </div>
          </div>

          {/* Results */}
          <div className="space-y-2">
            {filteredResults().map((r) => (
              <Card key={r.ticker}>
                <CardContent className="p-4">
                  <div
                    className="flex items-center gap-4 cursor-pointer"
                    onClick={() => setExpanded(expanded === r.ticker ? null : r.ticker)}
                  >
                    <div className="w-16">
                      <a
                        href={`/trades?ticker=${r.ticker}`}
                        className="font-semibold text-brand-700 hover:underline dark:text-brand-400"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {r.ticker}
                      </a>
                    </div>
                    <div className="w-16 font-mono text-sm">
                      {r.overall_score !== null ? (
                        <span className={`font-bold ${scoreColor(r.overall_score)}`}>
                          {r.overall_score.toFixed(1)}
                        </span>
                      ) : (
                        <span className="text-gray-400">—</span>
                      )}
                    </div>
                    <div className="w-28 flex flex-col gap-1">
                      <Badge variant={classificationVariant(r.classification)}>{r.classification}</Badge>
                      {r.strategy_type && (
                        <Badge variant="strategy">{r.strategy_type.replace('_', ' ')}</Badge>
                      )}
                      {r.layer_id && (
                        <div className="flex gap-1 mt-1">
                          <Badge variant="layer">{r.layer_id}</Badge>
                          <Badge variant="account">{r.account_id || "SHENIDO"}</Badge>
                        </div>
                      )}
                    </div>
                    <div className="flex-1 truncate text-xs text-gray-600 dark:text-gray-400">
                      {r.rationale_summary || (r.rejection_reasons || []).join("; ")}
                    </div>
                    <div className="text-xs font-mono text-gray-400">
                      {r.processing_time_ms !== null ? `${r.processing_time_ms}ms` : ""}
                    </div>
                    <div className="text-gray-400">
                      {expanded === r.ticker ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                    </div>
                  </div>

                  {expanded === r.ticker && (
                    <div className="mt-4 border-t border-surface-2 pt-4 space-y-4 dark:border-gray-700">
                      {/* Score Breakdown */}
                      {r.score_breakdown && r.score_breakdown.length > 0 && (
                        <div>
                          <h4 className="text-[10px] font-semibold uppercase tracking-wider text-gray-400 mb-2">
                            Score Breakdown
                          </h4>
                          <div className="space-y-2">
                            {r.score_breakdown.map((f) => (
                              <div key={f.factor} className="flex items-center gap-3">
                                <div className="w-44 text-xs text-gray-700 dark:text-gray-300">{f.factor}</div>
                                <div className="flex-1">
                                  <div className="h-2 rounded-full bg-surface-2 dark:bg-gray-700">
                                    <div
                                      className={`h-2 rounded-full transition-all ${
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
                                <div className="w-12 text-right font-mono text-xs text-gray-700 dark:text-gray-300">
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
                          <h4 className="text-[10px] font-semibold uppercase tracking-wider text-gray-400 mb-1">
                            Risk Warnings
                          </h4>
                          <ul className="space-y-1">
                            {r.risk_warnings.map((w, i) => (
                              <li key={i} className="flex items-center gap-1.5 text-xs text-amber-700 dark:text-amber-400">
                                <AlertTriangle className="h-3 w-3 flex-shrink-0" /> {w}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {/* Rejection Reasons */}
                      {r.rejection_reasons && r.rejection_reasons.length > 0 && (
                        <div>
                          <h4 className="text-[10px] font-semibold uppercase tracking-wider text-gray-400 mb-1">
                            Rejection Reasons
                          </h4>
                          <ul className="space-y-1">
                            {r.rejection_reasons.map((reason, i) => (
                              <li key={i} className="flex items-center gap-1.5 text-xs text-red-600 dark:text-red-400">
                                <XCircle className="h-3 w-3 flex-shrink-0" /> {reason}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {/* Actions */}
                      <div className="flex gap-2 pt-2">
                        <Button variant="ghost" size="sm" asChild>
                          <a href={`/trades?ticker=${r.ticker}`}>
                            View Trade <ArrowRight className="h-3 w-3" />
                          </a>
                        </Button>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        </>
      )}

      {!scanRun && !loading && (
        <div className="flex h-64 flex-col items-center justify-center text-gray-400 dark:text-gray-500">
          <Search className="mb-3 h-10 w-10 text-gray-300 dark:text-gray-600" />
          <p className="text-sm">Run a scan to see results</p>
        </div>
      )}
    </div>
  );
}
