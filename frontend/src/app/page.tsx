"use client";

import { useEffect, useState } from "react";
import {
  api,
  DashboardSummary,
  HealthResponse,
  ScanRunResponse,
  UpcomingEarningsResponse,
} from "@/lib/api";
import { useToast } from "@/components/Toast";
import { useScanProgress, ScanCompleteEvent, ScanErrorEvent } from "@/lib/useScanProgress";

export default function Dashboard() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [earnings, setEarnings] = useState<UpcomingEarningsResponse | null>(null);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [scanResult, setScanResult] = useState<ScanRunResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { toast } = useToast();

  const progress = useScanProgress(
    async (e: ScanCompleteEvent) => {
      setScanResult(null);
      setScanning(false);
      progress.disconnect();
      toast(`Scan complete — ${e.total_recommended} recommended, ${e.total_watchlist} watchlist`, "success");
      try {
        const [s, result] = await Promise.all([
          api.dashboardSummary(),
          api.getScanRun(e.run_id),
        ]);
        setSummary(s);
        setScanResult(result);
      } catch {}
    },
    (e: ScanErrorEvent) => {
      setScanning(false);
      progress.disconnect();
      setError(e.error || "Scan failed");
      toast(e.error || "Scan failed", "error");
    },
  );

  useEffect(() => {
    loadDashboard();
  }, []);

  async function loadDashboard() {
    setLoading(true);
    setError(null);
    try {
      const [h, e, s] = await Promise.allSettled([
        api.health(),
        api.upcomingEarnings(),
        api.dashboardSummary(),
      ]);
      if (h.status === "fulfilled") setHealth(h.value);
      if (e.status === "fulfilled") setEarnings(e.value);
      if (s.status === "fulfilled") setSummary(s.value);
    } catch (err: any) {
      setError(err.message || "Failed to load dashboard data");
    } finally {
      setLoading(false);
    }
  }

  async function runScan() {
    setScanning(true);
    setError(null);
    progress.reset();
    progress.connect();
    try {
      await api.runScanAsync();
      // Scan now runs in background; onComplete callback above handles the rest
    } catch (err: any) {
      setScanning(false);
      progress.disconnect();
      setError(err.message || "Scan failed");
      toast(err.message || "Scan failed", "error");
    }
  }

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="text-gray-500">Loading dashboard...</div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
          <p className="mt-1 text-sm text-gray-500">
            Pre-earnings Double Calendar Scanner
          </p>
        </div>
        <button onClick={runScan} disabled={scanning} className="btn-primary">
          {scanning ? "Scanning..." : "Run Scan"}
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          {error}
        </div>
      )}

      {/* Live Scan Progress */}
      {scanning && progress.events.length > 0 && (
        <div className="card">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">Scan Progress</h2>
            <span className="text-sm font-mono text-brand-700">
              {progress.events[progress.events.length - 1].pct}%
            </span>
          </div>
          <div className="mt-3 h-3 w-full overflow-hidden rounded-full bg-surface-2">
            <div
              className="h-3 rounded-full bg-brand-500 transition-all duration-300"
              style={{ width: `${progress.events[progress.events.length - 1].pct}%` }}
            />
          </div>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {progress.events.slice(-12).map((e) => (
              <span
                key={e.ticker}
                className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${
                  e.classification === "RECOMMEND"
                    ? "bg-emerald-100 text-emerald-800"
                    : e.classification === "WATCHLIST"
                    ? "bg-amber-100 text-amber-800"
                    : "bg-gray-100 text-gray-600"
                }`}
              >
                {e.ticker}
                {e.score != null && (
                  <span className="ml-1 font-mono text-[10px]">{e.score.toFixed(0)}</span>
                )}
              </span>
            ))}
          </div>
          <p className="mt-2 text-xs text-gray-400">
            {progress.events[progress.events.length - 1].index} / {progress.events[progress.events.length - 1].total} tickers processed
          </p>
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div className="card text-center">
          <p className="text-3xl font-bold text-brand-700">
            {summary?.total_scans ?? 0}
          </p>
          <p className="mt-1 text-xs text-gray-500">Total Scans</p>
        </div>
        <div className="card text-center">
          <p className="text-3xl font-bold text-emerald-700">
            {summary?.total_recommendations ?? 0}
          </p>
          <p className="mt-1 text-xs text-gray-500">Recommendations</p>
        </div>
        <div className="card text-center">
          <p className="text-3xl font-bold text-amber-700">
            {summary?.total_watchlist ?? 0}
          </p>
          <p className="mt-1 text-xs text-gray-500">Watchlist</p>
        </div>
        <div className="card text-center">
          <p className="text-3xl font-bold text-gray-700">
            {summary?.avg_score != null ? summary.avg_score.toFixed(1) : "—"}
          </p>
          <p className="mt-1 text-xs text-gray-500">Avg Score</p>
        </div>
      </div>

      {/* Health Status */}
      {health && (
        <div className="card">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">System Health</h2>
            <span
              className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                health.status === "HEALTHY"
                  ? "bg-emerald-100 text-emerald-800"
                  : health.status === "DEGRADED"
                  ? "bg-amber-100 text-amber-800"
                  : "bg-red-100 text-red-800"
              }`}
            >
              {health.status}
            </span>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div>
              <p className="text-xs text-gray-500">Environment</p>
              <p className="text-sm font-medium">{health.environment}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Mode</p>
              <p className="text-sm font-medium">{health.operating_mode}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Version</p>
              <p className="text-sm font-medium">{health.version}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">DB Connected</p>
              <p className="text-sm font-medium">
                {health.database_connected ? "Yes" : "No"}
              </p>
            </div>
          </div>
          <div className="mt-4">
            <h3 className="text-sm font-medium text-gray-700">Providers</h3>
            <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
              {health.providers.map((p) => (
                <div
                  key={p.provider}
                  className="flex items-center justify-between rounded-md bg-surface-1 px-3 py-2 text-sm"
                >
                  <span className="font-medium capitalize">{p.provider}</span>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-500">
                      {p.source_name}
                    </span>
                    <span
                      className={`h-2.5 w-2.5 rounded-full ${
                        p.severity === "HEALTHY"
                          ? "bg-emerald-500"
                          : p.severity === "DEGRADED"
                          ? "bg-amber-500"
                          : "bg-red-500"
                      }`}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Two-column: Top Candidates + Recent Scans */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Top Candidates */}
        <div className="card">
          <h2 className="text-lg font-semibold">Top Candidates</h2>
          <p className="mt-1 text-xs text-gray-500">
            Highest-scoring from latest scan
          </p>
          {summary && summary.top_candidates.length > 0 ? (
            <div className="mt-4 space-y-2">
              {summary.top_candidates.map((c, i) => (
                <a
                  key={c.ticker}
                  href={`/candidates/${c.ticker}`}
                  className="flex items-center justify-between rounded-md bg-surface-1 px-3 py-2.5 text-sm transition hover:bg-surface-2"
                >
                  <div className="flex items-center gap-3">
                    <span className="flex h-6 w-6 items-center justify-center rounded-full bg-brand-100 text-xs font-bold text-brand-700">
                      {i + 1}
                    </span>
                    <span className="font-semibold text-brand-700">{c.ticker}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span
                      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                        c.classification === "RECOMMEND"
                          ? "bg-emerald-100 text-emerald-800"
                          : "bg-amber-100 text-amber-800"
                      }`}
                    >
                      {c.classification}
                    </span>
                    <span className="w-10 text-right font-mono text-sm font-bold">
                      {c.score.toFixed(1)}
                    </span>
                  </div>
                </a>
              ))}
            </div>
          ) : (
            <div className="mt-4 rounded-md bg-surface-1 p-6 text-center text-sm text-gray-500">
              No candidates yet. Run a scan to see results.
            </div>
          )}
        </div>

        {/* Recent Scans */}
        <div className="card">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">Recent Scans</h2>
            <a href="/scan" className="text-xs font-medium text-brand-600 hover:underline">
              View all
            </a>
          </div>
          {summary && summary.recent_scans.length > 0 ? (
            <div className="mt-4 space-y-2">
              {summary.recent_scans.map((s) => (
                <div
                  key={s.run_id}
                  className="rounded-md bg-surface-1 px-3 py-2.5 text-sm"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs text-gray-500">
                      {s.run_id.slice(0, 8)}
                    </span>
                    <span className="text-xs text-gray-500">
                      {new Date(s.started_at).toLocaleString()}
                    </span>
                  </div>
                  <div className="mt-1.5 flex items-center gap-4 text-xs">
                    <span>{s.total_scanned} scanned</span>
                    <span className="font-semibold text-emerald-700">
                      {s.total_recommended} rec
                    </span>
                    <span className="text-amber-700">{s.total_watchlist} watch</span>
                    <span className="text-red-600">{s.total_rejected} rej</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="mt-4 rounded-md bg-surface-1 p-6 text-center text-sm text-gray-500">
              No scans yet. Run your first scan above.
            </div>
          )}
          {summary?.last_scan_at && (
            <p className="mt-3 text-xs text-gray-400">
              Last scan: {new Date(summary.last_scan_at).toLocaleString()}
            </p>
          )}
        </div>
      </div>

      {/* Upcoming Earnings */}
      {earnings && earnings.earnings.length > 0 && (
        <div className="card">
          <h2 className="text-lg font-semibold">
            Upcoming Earnings ({earnings.total})
          </h2>
          <div className="mt-4 overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-surface-3 text-left text-xs font-medium uppercase text-gray-500">
                  <th className="pb-3 pr-4">Ticker</th>
                  <th className="pb-3 pr-4">Date</th>
                  <th className="pb-3 pr-4">Days</th>
                  <th className="pb-3 pr-4">Timing</th>
                  <th className="pb-3 pr-4">Confidence</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-2">
                {earnings.earnings.map((e) => (
                  <tr key={e.ticker} className="hover:bg-surface-1">
                    <td className="py-3 pr-4 font-semibold text-brand-700">
                      <a href={`/candidates/${e.ticker}`} className="hover:underline">{e.ticker}</a>
                    </td>
                    <td className="py-3 pr-4">{e.earnings_date}</td>
                    <td className="py-3 pr-4">{e.days_until_earnings}d</td>
                    <td className="py-3 pr-4 text-xs">{e.report_timing}</td>
                    <td className="py-3 pr-4">
                      <span
                        className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                          e.confidence === "CONFIRMED"
                            ? "bg-emerald-100 text-emerald-800"
                            : e.confidence === "ESTIMATED"
                            ? "bg-amber-100 text-amber-800"
                            : "bg-red-100 text-red-800"
                        }`}
                      >
                        {e.confidence}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Ad-hoc Scan Results */}
      {scanResult && (
        <div className="card">
          <h2 className="text-lg font-semibold">
            Latest Scan — {scanResult.run_id.slice(0, 8)}
          </h2>
          <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div className="rounded-lg bg-surface-1 p-4 text-center">
              <p className="text-2xl font-bold">{scanResult.total_scanned}</p>
              <p className="text-xs text-gray-500">Scanned</p>
            </div>
            <div className="rounded-lg bg-emerald-50 p-4 text-center">
              <p className="text-2xl font-bold text-emerald-700">
                {scanResult.total_recommended}
              </p>
              <p className="text-xs text-emerald-600">Recommend</p>
            </div>
            <div className="rounded-lg bg-amber-50 p-4 text-center">
              <p className="text-2xl font-bold text-amber-700">
                {scanResult.total_watchlist}
              </p>
              <p className="text-xs text-amber-600">Watchlist</p>
            </div>
            <div className="rounded-lg bg-red-50 p-4 text-center">
              <p className="text-2xl font-bold text-red-700">
                {scanResult.total_rejected}
              </p>
              <p className="text-xs text-red-600">Rejected</p>
            </div>
          </div>
          <div className="mt-6">
            <a href="/scan" className="btn-secondary text-sm">
              View Full Results
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
