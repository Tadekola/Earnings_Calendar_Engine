"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  api,
  ScanRunResponse,
} from "@/lib/api";
import { useScanProgress, ScanCompleteEvent, ScanErrorEvent } from "@/lib/useScanProgress";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge, classificationVariant, severityVariant, confidenceVariant } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { KPICardSkeleton, CardSkeleton } from "@/components/ui/skeleton";
import {
  Play,
  BarChart3,
  CheckCircle2,
  Eye,
  Target,
  Server,
  Database,
  Wifi,
  WifiOff,
  Calendar,
  Clock,
  TrendingUp,
  ArrowRight,
  Loader2,
} from "lucide-react";

export default function Dashboard() {
  const queryClient = useQueryClient();
  const [scanResult, setScanResult] = useState<ScanRunResponse | null>(null);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: () => api.health(),
    refetchInterval: 30_000,
  });

  const { data: earnings } = useQuery({
    queryKey: ["earnings"],
    queryFn: () => api.upcomingEarnings(),
    staleTime: 60_000,
  });

  const { data: summary, isLoading: loading } = useQuery({
    queryKey: ["dashboard-summary"],
    queryFn: () => api.dashboardSummary(),
    staleTime: 15_000,
  });

  const progress = useScanProgress(
    async (e: ScanCompleteEvent) => {
      setScanResult(null);
      setScanning(false);
      progress.disconnect();
      toast.success(`Scan complete — ${e.total_recommended} recommended, ${e.total_watchlist} watchlist`);
      queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
      try {
        const result = await api.getScanRun(e.run_id);
        setScanResult(result);
      } catch {}
    },
    (e: ScanErrorEvent) => {
      setScanning(false);
      progress.disconnect();
      setError(e.error || "Scan failed");
      toast.error(e.error || "Scan failed");
    },
  );

  async function runScan() {
    setScanning(true);
    setError(null);
    progress.reset();
    progress.connect();
    try {
      await api.runScanAsync();
    } catch (err: any) {
      setScanning(false);
      progress.disconnect();
      setError(err.message || "Scan failed");
      toast.error(err.message || "Scan failed");
    }
  }

  if (loading) {
    return (
      <div className="space-y-8">
        <div className="flex items-center justify-between">
          <div>
            <div className="h-7 w-40 rounded bg-surface-3 animate-pulse-subtle" />
            <div className="mt-2 h-4 w-64 rounded bg-surface-3 animate-pulse-subtle" />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {[1, 2, 3, 4].map((i) => <KPICardSkeleton key={i} />)}
        </div>
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <CardSkeleton />
          <CardSkeleton />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900 dark:text-gray-100">
            Dashboard
          </h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Earnings-driven options scanner &amp; trade recommendation engine
          </p>
        </div>
        <Button onClick={runScan} disabled={scanning} size="default">
          {scanning ? (
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

      {/* Live Scan Progress */}
      {scanning && progress.events.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin text-brand-600" />
                Scan Progress
              </CardTitle>
              <span className="font-mono text-sm font-semibold text-brand-700 dark:text-brand-400">
                {progress.events[progress.events.length - 1].pct}%
              </span>
            </div>
          </CardHeader>
          <CardContent>
            <div className="h-2.5 w-full overflow-hidden rounded-full bg-surface-2 dark:bg-gray-700">
              <div
                className="h-2.5 rounded-full bg-gradient-to-r from-brand-500 to-brand-600 transition-all duration-500 ease-out"
                style={{ width: `${progress.events[progress.events.length - 1].pct}%` }}
              />
            </div>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {progress.events.slice(-15).map((e) => (
                <Badge
                  key={e.ticker}
                  variant={classificationVariant(e.classification || "")}
                >
                  {e.ticker}
                  {e.score != null && (
                    <span className="ml-1 font-mono text-[10px]">{e.score.toFixed(0)}</span>
                  )}
                </Badge>
              ))}
            </div>
            <p className="mt-2 text-xs text-gray-400 dark:text-gray-500">
              {progress.events[progress.events.length - 1].index} / {progress.events[progress.events.length - 1].total} tickers processed
            </p>
          </CardContent>
        </Card>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Card className="relative overflow-hidden">
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Total Scans</p>
                <p className="mt-1 text-3xl font-bold tracking-tight text-gray-900 dark:text-gray-100">
                  {summary?.total_scans ?? 0}
                </p>
              </div>
              <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand-50 dark:bg-brand-900/30">
                <BarChart3 className="h-5 w-5 text-brand-600 dark:text-brand-400" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="relative overflow-hidden">
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Recommendations</p>
                <p className="mt-1 text-3xl font-bold tracking-tight text-emerald-700 dark:text-emerald-400">
                  {summary?.total_recommendations ?? 0}
                </p>
              </div>
              <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-emerald-50 dark:bg-emerald-900/30">
                <CheckCircle2 className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="relative overflow-hidden">
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Watchlist</p>
                <p className="mt-1 text-3xl font-bold tracking-tight text-amber-700 dark:text-amber-400">
                  {summary?.total_watchlist ?? 0}
                </p>
              </div>
              <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-amber-50 dark:bg-amber-900/30">
                <Eye className="h-5 w-5 text-amber-600 dark:text-amber-400" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="relative overflow-hidden">
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Avg Score</p>
                <p className="mt-1 text-3xl font-bold tracking-tight text-gray-900 dark:text-gray-100">
                  {summary?.avg_score != null ? summary.avg_score.toFixed(1) : "—"}
                </p>
              </div>
              <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-surface-2 dark:bg-gray-700">
                <Target className="h-5 w-5 text-gray-500 dark:text-gray-400" />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* System Health */}
      {health && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Server className="h-4 w-4 text-gray-500" />
                <CardTitle>System Health</CardTitle>
              </div>
              <Badge variant={severityVariant(health.status)}>{health.status}</Badge>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <div className="rounded-lg bg-surface-1 p-3 dark:bg-gray-700/50">
                <p className="text-[10px] font-medium uppercase tracking-wider text-gray-400">Environment</p>
                <p className="mt-0.5 text-sm font-semibold text-gray-900 dark:text-gray-100">{health.environment}</p>
              </div>
              <div className="rounded-lg bg-surface-1 p-3 dark:bg-gray-700/50">
                <p className="text-[10px] font-medium uppercase tracking-wider text-gray-400">Mode</p>
                <p className="mt-0.5 text-sm font-semibold text-gray-900 dark:text-gray-100">{health.operating_mode}</p>
              </div>
              <div className="rounded-lg bg-surface-1 p-3 dark:bg-gray-700/50">
                <p className="text-[10px] font-medium uppercase tracking-wider text-gray-400">Version</p>
                <p className="mt-0.5 text-sm font-semibold text-gray-900 dark:text-gray-100">{health.version}</p>
              </div>
              <div className="rounded-lg bg-surface-1 p-3 dark:bg-gray-700/50">
                <p className="text-[10px] font-medium uppercase tracking-wider text-gray-400">Database</p>
                <div className="mt-0.5 flex items-center gap-1.5">
                  {health.database_connected ? (
                    <Database className="h-3.5 w-3.5 text-emerald-500" />
                  ) : (
                    <WifiOff className="h-3.5 w-3.5 text-red-500" />
                  )}
                  <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                    {health.database_connected ? "Connected" : "Disconnected"}
                  </p>
                </div>
              </div>
            </div>
            <div className="mt-4">
              <p className="mb-2 text-[10px] font-medium uppercase tracking-wider text-gray-400">Data Providers</p>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {(health.providers || []).map((p) => (
                  <div
                    key={p.provider}
                    className="flex items-center justify-between rounded-lg border border-surface-3 bg-white px-3 py-2.5 dark:border-gray-600 dark:bg-gray-700/50"
                  >
                    <div className="flex items-center gap-2">
                      <Wifi className={`h-3.5 w-3.5 ${
                        p.severity === "HEALTHY" ? "text-emerald-500" : p.severity === "DEGRADED" ? "text-amber-500" : "text-red-500"
                      }`} />
                      <span className="text-sm font-medium capitalize text-gray-900 dark:text-gray-100">{p.provider}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[10px] text-gray-400">{p.source_name}</span>
                      <span className={`h-2 w-2 rounded-full ${
                        p.severity === "HEALTHY" ? "bg-emerald-500" : p.severity === "DEGRADED" ? "bg-amber-500" : "bg-red-500"
                      }`} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Two-column: Top Candidates + Recent Scans */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Top Candidates */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-emerald-500" />
              <CardTitle>Top Candidates</CardTitle>
            </div>
            <CardDescription>Highest-scoring from latest scan</CardDescription>
          </CardHeader>
          <CardContent>
            {summary && summary.top_candidates.length > 0 ? (
              <div className="space-y-1.5">
                {summary.top_candidates.map((c, i) => (
                  <a
                    key={c.ticker}
                    href={`/candidates/${c.ticker}`}
                    className="flex items-center justify-between rounded-lg border border-transparent bg-surface-1 px-3 py-2.5 text-sm transition-all hover:border-brand-200 hover:bg-brand-50/50 dark:bg-gray-700/50 dark:hover:border-brand-800 dark:hover:bg-brand-900/20"
                  >
                    <div className="flex items-center gap-3">
                      <span className="flex h-6 w-6 items-center justify-center rounded-full bg-brand-100 text-xs font-bold text-brand-700 dark:bg-brand-900/50 dark:text-brand-300">
                        {i + 1}
                      </span>
                      <span className="font-semibold text-gray-900 dark:text-gray-100">{c.ticker}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant={classificationVariant(c.classification)}>{c.classification}</Badge>
                      {c.strategy_type && (
                        <Badge variant="strategy">{c.strategy_type.replace('_', ' ')}</Badge>
                      )}
                      <span className="w-10 text-right font-mono text-sm font-bold text-gray-900 dark:text-gray-100">
                        {c.score.toFixed(1)}
                      </span>
                    </div>
                  </a>
                ))}
              </div>
            ) : (
              <div className="rounded-lg bg-surface-1 p-8 text-center dark:bg-gray-700/50">
                <Target className="mx-auto h-8 w-8 text-gray-300 dark:text-gray-600" />
                <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">No candidates yet. Run a scan to see results.</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Recent Scans */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Clock className="h-4 w-4 text-gray-500" />
                <CardTitle>Recent Scans</CardTitle>
              </div>
              <a href="/scan" className="flex items-center gap-1 text-xs font-medium text-brand-600 hover:text-brand-700 dark:text-brand-400">
                View all <ArrowRight className="h-3 w-3" />
              </a>
            </div>
          </CardHeader>
          <CardContent>
            {summary && summary.recent_scans.length > 0 ? (
              <div className="space-y-2">
                {summary.recent_scans.map((s) => (
                  <div
                    key={s.run_id}
                    className="rounded-lg border border-surface-3 bg-surface-1 px-3 py-2.5 dark:border-gray-600 dark:bg-gray-700/50"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-xs text-gray-500 dark:text-gray-400">
                        {s.run_id.slice(0, 8)}
                      </span>
                      <span className="text-xs text-gray-400">
                        {new Date(s.started_at).toLocaleString()}
                      </span>
                    </div>
                    <div className="mt-1.5 flex items-center gap-4 text-xs">
                      <span className="text-gray-600 dark:text-gray-300">{s.total_scanned} scanned</span>
                      <span className="font-semibold text-emerald-600">{s.total_recommended} rec</span>
                      <span className="text-amber-600">{s.total_watchlist} watch</span>
                      <span className="text-red-500">{s.total_rejected} rej</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded-lg bg-surface-1 p-8 text-center dark:bg-gray-700/50">
                <BarChart3 className="mx-auto h-8 w-8 text-gray-300 dark:text-gray-600" />
                <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">No scans yet. Run your first scan above.</p>
              </div>
            )}
            {summary?.last_scan_at && (
              <p className="mt-3 text-xs text-gray-400 dark:text-gray-500">
                Last scan: {new Date(summary.last_scan_at).toLocaleString()}
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Upcoming Earnings */}
      {earnings && earnings.earnings.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Calendar className="h-4 w-4 text-brand-600" />
              <CardTitle>Upcoming Earnings ({earnings.total})</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="border-b border-surface-3 text-left text-[10px] font-medium uppercase tracking-wider text-gray-400 dark:border-gray-600">
                    <th className="pb-3 pr-4">Ticker</th>
                    <th className="pb-3 pr-4">Date</th>
                    <th className="pb-3 pr-4">Days</th>
                    <th className="pb-3 pr-4">Timing</th>
                    <th className="pb-3 pr-4">Confidence</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-2 dark:divide-gray-700">
                  {earnings.earnings.map((e) => (
                    <tr key={e.ticker} className="transition-colors hover:bg-surface-1 dark:hover:bg-gray-700/50">
                      <td className="py-3 pr-4">
                        <a href={`/candidates/${e.ticker}`} className="font-semibold text-brand-700 hover:underline dark:text-brand-400">{e.ticker}</a>
                      </td>
                      <td className="py-3 pr-4 font-mono text-xs text-gray-600 dark:text-gray-300">{e.earnings_date}</td>
                      <td className="py-3 pr-4">
                        <span className={`font-mono text-xs font-semibold ${
                          e.days_until_earnings <= 3 ? "text-red-600" : e.days_until_earnings <= 7 ? "text-amber-600" : "text-gray-600 dark:text-gray-300"
                        }`}>
                          {e.days_until_earnings}d
                        </span>
                      </td>
                      <td className="py-3 pr-4 text-xs text-gray-600 dark:text-gray-300">{e.report_timing}</td>
                      <td className="py-3 pr-4">
                        <Badge variant={confidenceVariant(e.confidence)}>{e.confidence}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Ad-hoc Scan Results */}
      {scanResult && (
        <Card>
          <CardHeader>
            <CardTitle>Latest Scan — <span className="font-mono">{scanResult.run_id.slice(0, 8)}</span></CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <div className="rounded-lg bg-surface-1 p-4 text-center dark:bg-gray-700/50">
                <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{scanResult.total_scanned}</p>
                <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">Scanned</p>
              </div>
              <div className="rounded-lg bg-emerald-50 p-4 text-center dark:bg-emerald-900/20">
                <p className="text-2xl font-bold text-emerald-700 dark:text-emerald-400">{scanResult.total_recommended}</p>
                <p className="mt-0.5 text-xs text-emerald-600 dark:text-emerald-400">Recommend</p>
              </div>
              <div className="rounded-lg bg-amber-50 p-4 text-center dark:bg-amber-900/20">
                <p className="text-2xl font-bold text-amber-700 dark:text-amber-400">{scanResult.total_watchlist}</p>
                <p className="mt-0.5 text-xs text-amber-600 dark:text-amber-400">Watchlist</p>
              </div>
              <div className="rounded-lg bg-red-50 p-4 text-center dark:bg-red-900/20">
                <p className="text-2xl font-bold text-red-700 dark:text-red-400">{scanResult.total_rejected}</p>
                <p className="mt-0.5 text-xs text-red-600 dark:text-red-400">Rejected</p>
              </div>
            </div>
            <div className="mt-6">
              <Button variant="secondary" size="sm" asChild>
                <a href="/scan">View Full Results <ArrowRight className="h-3 w-3" /></a>
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
