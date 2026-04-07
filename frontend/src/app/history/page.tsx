"use client";

import { useEffect, useState } from "react";
import { api, DashboardSummary } from "@/lib/api";

export default function HistoryPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [scanResults, setScanResults] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadHistory();
  }, []);

  async function loadHistory() {
    setLoading(true);
    setError(null);
    try {
      const [summaryData, resultsData] = await Promise.allSettled([
        api.dashboardSummary(),
        api.scanResults(),
      ]);
      if (summaryData.status === "fulfilled") setSummary(summaryData.value);
      if (resultsData.status === "fulfilled") setScanResults(resultsData.value);
      if (summaryData.status === "rejected" && resultsData.status === "rejected") {
        setError("Failed to load scan history");
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
        Loading scan history...
      </div>
    );
  }

  const maxScanned = Math.max(
    1,
    ...scanResults.map((s) => s.total_scanned || 1)
  );

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Scan History</h1>
          <p className="text-sm text-gray-500">
            Scan-over-scan trends and historical comparison
          </p>
        </div>
        <div className="flex items-center gap-2">
          <a
            href={api.exportScansCSV()}
            className="rounded-md border border-surface-3 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-surface-1"
          >
            Export Scans CSV
          </a>
          <a
            href={api.exportCandidatesCSV()}
            className="rounded-md border border-surface-3 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-surface-1"
          >
            Export Candidates CSV
          </a>
          <a
            href={api.exportScoresCSV()}
            className="rounded-md border border-brand-500 px-3 py-1.5 text-xs font-medium text-brand-600 hover:bg-brand-50"
          >
            Export Scores CSV
          </a>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          {error}
        </div>
      )}

      {/* Lifetime Stats */}
      {summary && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
          <div className="card text-center">
            <p className="text-2xl font-bold text-brand-700">
              {summary.total_scans}
            </p>
            <p className="mt-1 text-xs text-gray-500">Total Scans</p>
          </div>
          <div className="card text-center">
            <p className="text-2xl font-bold text-gray-700">
              {summary.total_candidates_scanned}
            </p>
            <p className="mt-1 text-xs text-gray-500">Tickers Scanned</p>
          </div>
          <div className="card text-center">
            <p className="text-2xl font-bold text-emerald-700">
              {summary.total_recommendations}
            </p>
            <p className="mt-1 text-xs text-gray-500">Recommendations</p>
          </div>
          <div className="card text-center">
            <p className="text-2xl font-bold text-amber-700">
              {summary.total_watchlist}
            </p>
            <p className="mt-1 text-xs text-gray-500">Watchlist</p>
          </div>
          <div className="card text-center">
            <p className="text-2xl font-bold text-gray-700">
              {summary.avg_score != null ? summary.avg_score.toFixed(1) : "—"}
            </p>
            <p className="mt-1 text-xs text-gray-500">Avg Score</p>
          </div>
        </div>
      )}

      {/* Scan Runs Table */}
      <div className="card">
        <h2 className="text-lg font-semibold">All Scan Runs</h2>
        {scanResults.length > 0 ? (
          <div className="mt-4 overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-surface-3 text-left text-xs font-medium uppercase text-gray-500">
                  <th className="pb-3 pr-4">Run ID</th>
                  <th className="pb-3 pr-4">Status</th>
                  <th className="pb-3 pr-4">Started</th>
                  <th className="pb-3 pr-4 text-right">Scanned</th>
                  <th className="pb-3 pr-4 text-right">Rec</th>
                  <th className="pb-3 pr-4 text-right">Watch</th>
                  <th className="pb-3 pr-4 text-right">Rej</th>
                  <th className="pb-3 pr-4">Distribution</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-2">
                {scanResults.map((s) => {
                  const total = s.total_scanned || 1;
                  const recPct = ((s.total_recommended / total) * 100).toFixed(0);
                  const watchPct = ((s.total_watchlist / total) * 100).toFixed(0);
                  const rejPct = ((s.total_rejected / total) * 100).toFixed(0);
                  return (
                    <tr key={s.run_id} className="hover:bg-surface-1">
                      <td className="py-3 pr-4 font-mono text-xs text-gray-600">
                        {s.run_id.slice(0, 8)}
                      </td>
                      <td className="py-3 pr-4">
                        <span
                          className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                            s.status === "COMPLETED"
                              ? "bg-emerald-100 text-emerald-800"
                              : s.status === "FAILED"
                              ? "bg-red-100 text-red-800"
                              : "bg-gray-100 text-gray-600"
                          }`}
                        >
                          {s.status}
                        </span>
                      </td>
                      <td className="py-3 pr-4 text-xs text-gray-500">
                        {new Date(s.started_at).toLocaleString()}
                      </td>
                      <td className="py-3 pr-4 text-right font-mono">
                        {s.total_scanned}
                      </td>
                      <td className="py-3 pr-4 text-right font-mono text-emerald-700">
                        {s.total_recommended}
                      </td>
                      <td className="py-3 pr-4 text-right font-mono text-amber-700">
                        {s.total_watchlist}
                      </td>
                      <td className="py-3 pr-4 text-right font-mono text-red-600">
                        {s.total_rejected}
                      </td>
                      <td className="py-3 pr-4">
                        <div className="flex h-4 w-32 overflow-hidden rounded-full bg-surface-2">
                          <div
                            className="bg-emerald-500"
                            style={{ width: `${recPct}%` }}
                            title={`${recPct}% recommended`}
                          />
                          <div
                            className="bg-amber-400"
                            style={{ width: `${watchPct}%` }}
                            title={`${watchPct}% watchlist`}
                          />
                          <div
                            className="bg-red-400"
                            style={{ width: `${rejPct}%` }}
                            title={`${rejPct}% rejected`}
                          />
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="mt-4 rounded-md bg-surface-1 p-8 text-center text-sm text-gray-500">
            No scan history yet. Run a scan from the{" "}
            <a href="/" className="font-medium text-brand-600 hover:underline">
              Dashboard
            </a>{" "}
            to get started.
          </div>
        )}
      </div>

      {/* Visual Trend — mini bar chart */}
      {scanResults.length > 1 && (
        <div className="card">
          <h2 className="text-lg font-semibold">Scan Volume Trend</h2>
          <p className="mt-1 text-xs text-gray-500">
            Tickers scanned per run (most recent on the right)
          </p>
          <div className="mt-4 flex items-end gap-1.5" style={{ height: 120 }}>
            {[...scanResults].reverse().map((s) => {
              const pct = (s.total_scanned / maxScanned) * 100;
              return (
                <div
                  key={s.run_id}
                  className="group relative flex-1"
                  style={{ height: "100%" }}
                >
                  <div
                    className="absolute bottom-0 w-full rounded-t bg-brand-500 transition-all group-hover:bg-brand-600"
                    style={{ height: `${Math.max(pct, 4)}%` }}
                  />
                  <div className="absolute -top-6 left-1/2 hidden -translate-x-1/2 whitespace-nowrap rounded bg-gray-800 px-2 py-0.5 text-xs text-white group-hover:block">
                    {s.total_scanned} scanned
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
