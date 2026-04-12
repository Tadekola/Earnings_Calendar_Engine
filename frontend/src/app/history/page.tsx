"use client";

import { useQuery } from "@tanstack/react-query";
import { api, DashboardSummary } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { KPICardSkeleton, CardSkeleton } from "@/components/ui/skeleton";
import {
  BarChart3,
  CheckCircle2,
  Eye,
  Target,
  Users,
  Download,
  History,
} from "lucide-react";

export default function HistoryPage() {
  const { data: summary } = useQuery({
    queryKey: ["dashboard-summary"],
    queryFn: () => api.dashboardSummary(),
    staleTime: 15_000,
  });

  const { data: scanResults = [], isLoading: loading, error: queryError } = useQuery({
    queryKey: ["scan-results"],
    queryFn: () => api.scanResults(),
    staleTime: 15_000,
  });

  const error = queryError ? (queryError as Error).message : null;

  if (loading) {
    return (
      <div className="space-y-8">
        <div className="h-7 w-40 rounded bg-surface-3 animate-pulse-subtle" />
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
          {[1, 2, 3, 4, 5].map((i) => <KPICardSkeleton key={i} />)}
        </div>
        <CardSkeleton />
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
          <h1 className="text-2xl font-bold tracking-tight text-gray-900 dark:text-gray-100">Scan History</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Scan-over-scan trends and historical comparison
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="sm" asChild>
            <a href={api.exportScansCSV()}>
              <Download className="h-3.5 w-3.5" /> Scans CSV
            </a>
          </Button>
          <Button variant="secondary" size="sm" asChild>
            <a href={api.exportCandidatesCSV()}>
              <Download className="h-3.5 w-3.5" /> Candidates CSV
            </a>
          </Button>
          <Button variant="default" size="sm" asChild>
            <a href={api.exportScoresCSV()}>
              <Download className="h-3.5 w-3.5" /> Scores CSV
            </a>
          </Button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
          {error}
        </div>
      )}

      {/* Lifetime Stats */}
      {summary && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
          <Card>
            <CardContent className="p-5">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Total Scans</p>
                  <p className="mt-1 text-2xl font-bold tracking-tight text-brand-700 dark:text-brand-400">{summary.total_scans}</p>
                </div>
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-50 dark:bg-brand-900/30">
                  <BarChart3 className="h-5 w-5 text-brand-600 dark:text-brand-400" />
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-5">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Tickers</p>
                  <p className="mt-1 text-2xl font-bold tracking-tight text-gray-900 dark:text-gray-100">{summary.total_candidates_scanned}</p>
                </div>
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-surface-2 dark:bg-gray-700">
                  <Users className="h-5 w-5 text-gray-500 dark:text-gray-400" />
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-5">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Recommendations</p>
                  <p className="mt-1 text-2xl font-bold tracking-tight text-emerald-700 dark:text-emerald-400">{summary.total_recommendations}</p>
                </div>
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-50 dark:bg-emerald-900/30">
                  <CheckCircle2 className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-5">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Watchlist</p>
                  <p className="mt-1 text-2xl font-bold tracking-tight text-amber-700 dark:text-amber-400">{summary.total_watchlist}</p>
                </div>
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-50 dark:bg-amber-900/30">
                  <Eye className="h-5 w-5 text-amber-600 dark:text-amber-400" />
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-5">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Avg Score</p>
                  <p className="mt-1 text-2xl font-bold tracking-tight text-gray-900 dark:text-gray-100">{summary.avg_score != null ? summary.avg_score.toFixed(1) : "—"}</p>
                </div>
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-surface-2 dark:bg-gray-700">
                  <Target className="h-5 w-5 text-gray-500 dark:text-gray-400" />
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Scan Runs Table */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <History className="h-4 w-4 text-gray-500" />
            <CardTitle>All Scan Runs</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          {scanResults.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="border-b border-surface-3 text-left text-[10px] font-medium uppercase tracking-wider text-gray-400 dark:border-gray-600">
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
                <tbody className="divide-y divide-surface-2 dark:divide-gray-700">
                  {scanResults.map((s) => {
                    const total = s.total_scanned || 1;
                    const recPct = ((s.total_recommended / total) * 100).toFixed(0);
                    const watchPct = ((s.total_watchlist / total) * 100).toFixed(0);
                    const rejPct = ((s.total_rejected / total) * 100).toFixed(0);
                    return (
                      <tr key={s.run_id} className="transition-colors hover:bg-surface-1 dark:hover:bg-gray-700/50">
                        <td className="py-3 pr-4 font-mono text-xs text-gray-600 dark:text-gray-300">
                          {s.run_id.slice(0, 8)}
                        </td>
                        <td className="py-3 pr-4">
                          <Badge variant={s.status === "COMPLETED" ? "healthy" : s.status === "FAILED" ? "critical" : "outline"}>
                            {s.status}
                          </Badge>
                        </td>
                        <td className="py-3 pr-4 text-xs text-gray-500 dark:text-gray-400">
                          {new Date(s.started_at).toLocaleString()}
                        </td>
                        <td className="py-3 pr-4 text-right font-mono text-gray-900 dark:text-gray-100">
                          {s.total_scanned}
                        </td>
                        <td className="py-3 pr-4 text-right font-mono font-semibold text-emerald-600">
                          {s.total_recommended}
                        </td>
                        <td className="py-3 pr-4 text-right font-mono text-amber-600">
                          {s.total_watchlist}
                        </td>
                        <td className="py-3 pr-4 text-right font-mono text-red-500">
                          {s.total_rejected}
                        </td>
                        <td className="py-3 pr-4">
                          <div className="flex h-3.5 w-32 overflow-hidden rounded-full bg-surface-2 dark:bg-gray-700">
                            <div className="bg-emerald-500" style={{ width: `${recPct}%` }} title={`${recPct}% recommended`} />
                            <div className="bg-amber-400" style={{ width: `${watchPct}%` }} title={`${watchPct}% watchlist`} />
                            <div className="bg-red-400" style={{ width: `${rejPct}%` }} title={`${rejPct}% rejected`} />
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="rounded-lg bg-surface-1 p-8 text-center dark:bg-gray-700/50">
              <History className="mx-auto h-8 w-8 text-gray-300 dark:text-gray-600" />
              <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                No scan history yet. Run a scan from the{" "}
                <a href="/" className="font-medium text-brand-600 hover:underline dark:text-brand-400">Dashboard</a>
                {" "}to get started.
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Visual Trend — mini bar chart */}
      {scanResults.length > 1 && (
        <Card>
          <CardHeader>
            <CardTitle>Scan Volume Trend</CardTitle>
            <CardDescription>Tickers scanned per run (most recent on the right)</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-end gap-1.5" style={{ height: 120 }}>
              {[...scanResults].reverse().map((s) => {
                const pct = (s.total_scanned / maxScanned) * 100;
                return (
                  <div key={s.run_id} className="group relative flex-1" style={{ height: "100%" }}>
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
          </CardContent>
        </Card>
      )}
    </div>
  );
}
