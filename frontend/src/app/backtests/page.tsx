"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  api,
  BacktestSummary,
  BacktestDetail,
  BacktestAnalytics,
} from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { KPICardSkeleton, CardSkeleton } from "@/components/ui/skeleton";
import {
  FlaskConical,
  Plus,
  Trash2,
  TrendingUp,
  TrendingDown,
  Target,
  BarChart3,
  Clock,
  ChevronDown,
  ChevronUp,
  Loader2,
} from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  BarChart,
  Bar,
  Cell,
} from "recharts";

function pnlColor(pnl: number) {
  if (pnl > 0) return "text-emerald-600";
  if (pnl < 0) return "text-red-500";
  return "text-gray-500";
}

function outcomeVariant(outcome: string | null): "healthy" | "critical" | "default" {
  if (outcome === "WIN") return "healthy";
  if (outcome === "LOSS") return "critical";
  return "default";
}

export default function BacktestsPage() {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [formName, setFormName] = useState("");
  const [formStrategy, setFormStrategy] = useState("");
  const [formMinScore, setFormMinScore] = useState(0);

  const { data: list, isLoading } = useQuery({
    queryKey: ["backtests"],
    queryFn: () => api.listBacktests(),
    staleTime: 10_000,
  });

  const { data: detail } = useQuery({
    queryKey: ["backtest-detail", selectedId],
    queryFn: () => api.getBacktest(selectedId!),
    enabled: !!selectedId,
    staleTime: 15_000,
  });

  const { data: analytics } = useQuery({
    queryKey: ["backtest-analytics", selectedId],
    queryFn: () => api.getBacktestAnalytics(selectedId!),
    enabled: !!selectedId,
    staleTime: 15_000,
  });

  const createMutation = useMutation({
    mutationFn: (body: { name: string; strategy_filter?: string; min_score?: number }) =>
      api.createBacktest(body),
    onSuccess: (data) => {
      toast.success(`Backtest "${data.name}" completed — ${data.total_trades} trades`);
      queryClient.invalidateQueries({ queryKey: ["backtests"] });
      setSelectedId(data.backtest_id);
      setShowForm(false);
      setFormName("");
    },
    onError: (err: Error) => {
      toast.error(`Backtest failed: ${err.message}`);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deleteBacktest(id),
    onSuccess: () => {
      toast.success("Backtest deleted");
      queryClient.invalidateQueries({ queryKey: ["backtests"] });
      setSelectedId(null);
    },
  });

  function handleCreate() {
    if (!formName.trim()) {
      toast.error("Enter a backtest name");
      return;
    }
    createMutation.mutate({
      name: formName.trim(),
      strategy_filter: formStrategy || undefined,
      min_score: formMinScore || undefined,
    });
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="h-7 w-40 rounded bg-surface-3 animate-pulse-subtle" />
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <KPICardSkeleton key={i} />
          ))}
        </div>
        <CardSkeleton />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900 dark:text-gray-100">
            Backtests
          </h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Evaluate strategy performance against historical trade data
          </p>
        </div>
        <Button onClick={() => setShowForm(!showForm)}>
          {showForm ? (
            <>
              <ChevronUp className="h-4 w-4" /> Cancel
            </>
          ) : (
            <>
              <Plus className="h-4 w-4" /> New Backtest
            </>
          )}
        </Button>
      </div>

      {/* Create Form */}
      {showForm && (
        <Card>
          <CardContent className="p-5">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
              <div>
                <label className="text-xs font-medium text-gray-500">Name</label>
                <input
                  type="text"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder="My Backtest"
                  className="mt-1 w-full rounded-md border border-surface-3 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-500">
                  Strategy Filter
                </label>
                <select
                  value={formStrategy}
                  onChange={(e) => setFormStrategy(e.target.value)}
                  className="mt-1 w-full rounded-md border border-surface-3 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
                >
                  <option value="">All Strategies</option>
                  <option value="DOUBLE_CALENDAR">Double Calendar</option>
                  <option value="IRON_BUTTERFLY_ATM">Iron Butterfly ATM</option>
                  <option value="IRON_BUTTERFLY_BULLISH">Iron Butterfly Bullish</option>
                </select>
              </div>
              <div>
                <label className="text-xs font-medium text-gray-500">
                  Min Score
                </label>
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={formMinScore}
                  onChange={(e) => setFormMinScore(Number(e.target.value))}
                  className="mt-1 w-full rounded-md border border-surface-3 bg-white px-3 py-2 text-sm font-mono dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
                />
              </div>
              <div className="flex items-end">
                <Button
                  onClick={handleCreate}
                  disabled={createMutation.isPending}
                  className="w-full"
                >
                  {createMutation.isPending ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" /> Running...
                    </>
                  ) : (
                    <>
                      <FlaskConical className="h-4 w-4" /> Run Backtest
                    </>
                  )}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Backtest List */}
      {list && list.backtests.length > 0 && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {list.backtests.map((bt) => (
            <Card
              key={bt.backtest_id}
              className={`cursor-pointer transition hover:shadow-md ${
                selectedId === bt.backtest_id
                  ? "ring-2 ring-brand-500"
                  : ""
              }`}
              onClick={() => setSelectedId(bt.backtest_id)}
            >
              <CardContent className="p-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                    {bt.name}
                  </h3>
                  <Badge
                    variant={
                      bt.status === "COMPLETED"
                        ? "healthy"
                        : bt.status === "FAILED"
                        ? "critical"
                        : "default"
                    }
                  >
                    {bt.status}
                  </Badge>
                </div>
                <div className="mt-3 grid grid-cols-3 gap-2">
                  <div>
                    <p className="text-[10px] uppercase text-gray-400">Trades</p>
                    <p className="font-mono text-sm font-semibold">{bt.total_trades}</p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase text-gray-400">Win Rate</p>
                    <p className="font-mono text-sm font-semibold">
                      {bt.win_rate != null ? `${bt.win_rate}%` : "—"}
                    </p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase text-gray-400">P&L</p>
                    <p className={`font-mono text-sm font-semibold ${pnlColor(bt.total_pnl)}`}>
                      ${bt.total_pnl.toFixed(2)}
                    </p>
                  </div>
                </div>
                {bt.strategy_filter && (
                  <p className="mt-2 text-[10px] text-gray-400">
                    Strategy: {bt.strategy_filter}
                  </p>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {list && list.backtests.length === 0 && !showForm && (
        <div className="flex h-48 flex-col items-center justify-center text-gray-400 dark:text-gray-500">
          <FlaskConical className="mb-3 h-10 w-10 text-gray-300 dark:text-gray-600" />
          <p className="text-sm">No backtests yet</p>
          <p className="mt-1 text-xs">
            Run a scan first, then create a backtest to evaluate performance
          </p>
        </div>
      )}

      {/* Detail + Analytics */}
      {detail && selectedId && (
        <>
          {/* KPI Cards */}
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
            <Card>
              <CardContent className="p-4">
                <div className="flex items-center gap-2">
                  <Target className="h-4 w-4 text-brand-500" />
                  <p className="text-[10px] uppercase text-gray-400">Trades</p>
                </div>
                <p className="mt-1 font-mono text-2xl font-bold">{detail.total_trades}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4">
                <div className="flex items-center gap-2">
                  <BarChart3 className="h-4 w-4 text-emerald-500" />
                  <p className="text-[10px] uppercase text-gray-400">Win Rate</p>
                </div>
                <p className="mt-1 font-mono text-2xl font-bold text-emerald-600">
                  {detail.win_rate != null ? `${detail.win_rate}%` : "—"}
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4">
                <div className="flex items-center gap-2">
                  {detail.total_pnl >= 0 ? (
                    <TrendingUp className="h-4 w-4 text-emerald-500" />
                  ) : (
                    <TrendingDown className="h-4 w-4 text-red-500" />
                  )}
                  <p className="text-[10px] uppercase text-gray-400">Total P&L</p>
                </div>
                <p className={`mt-1 font-mono text-2xl font-bold ${pnlColor(detail.total_pnl)}`}>
                  ${detail.total_pnl.toFixed(2)}
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4">
                <div className="flex items-center gap-2">
                  <Clock className="h-4 w-4 text-amber-500" />
                  <p className="text-[10px] uppercase text-gray-400">Avg Hold</p>
                </div>
                <p className="mt-1 font-mono text-2xl font-bold">
                  {detail.avg_hold_days != null ? `${detail.avg_hold_days}d` : "—"}
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4">
                <div className="flex items-center gap-2">
                  <TrendingDown className="h-4 w-4 text-red-400" />
                  <p className="text-[10px] uppercase text-gray-400">Max DD</p>
                </div>
                <p className="mt-1 font-mono text-2xl font-bold text-red-500">
                  ${detail.max_drawdown?.toFixed(2) || "—"}
                </p>
              </CardContent>
            </Card>
          </div>

          {/* P&L Curve Chart */}
          {analytics && analytics.pnl_curve.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Cumulative P&L</CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={analytics.pnl_curve} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                    <XAxis dataKey="trade_index" tick={{ fill: "#9CA3AF", fontSize: 11 }} />
                    <YAxis
                      tick={{ fill: "#9CA3AF", fontSize: 11 }}
                      tickFormatter={(v: number) => `$${v}`}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "#1F2937",
                        border: "1px solid #374151",
                        borderRadius: 8,
                        fontSize: 12,
                      }}
                      labelStyle={{ color: "#D1D5DB" }}
                      formatter={((v: any) => [`$${Number(v).toFixed(2)}`]) as any}
                      labelFormatter={(idx: any) => {
                        const pt = analytics.pnl_curve[Number(idx) - 1];
                        return pt ? `#${idx} ${pt.ticker}` : `Trade #${idx}`;
                      }}
                    />
                    <ReferenceLine y={0} stroke="#6B7280" strokeDasharray="3 3" />
                    <Line
                      type="monotone"
                      dataKey="cumulative_pnl"
                      stroke="#6366F1"
                      strokeWidth={2.5}
                      dot={{ fill: "#6366F1", r: 3 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}

          {/* Monthly P&L Bar Chart */}
          {analytics && Object.keys(analytics.monthly_pnl).length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Monthly P&L</CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart
                    data={Object.entries(analytics.monthly_pnl).map(([month, pnl]) => ({
                      month,
                      pnl,
                    }))}
                    margin={{ top: 10, right: 20, left: 0, bottom: 5 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                    <XAxis dataKey="month" tick={{ fill: "#9CA3AF", fontSize: 10 }} />
                    <YAxis tick={{ fill: "#9CA3AF", fontSize: 11 }} tickFormatter={(v: number) => `$${v}`} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "#1F2937",
                        border: "1px solid #374151",
                        borderRadius: 8,
                        fontSize: 12,
                      }}
                      formatter={((v: any) => [`$${Number(v).toFixed(2)}`]) as any}
                    />
                    <ReferenceLine y={0} stroke="#6B7280" />
                    <Bar dataKey="pnl">
                      {Object.values(analytics.monthly_pnl).map((pnl, i) => (
                        <Cell key={i} fill={pnl >= 0 ? "#10B981" : "#EF4444"} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}

          {/* By Strategy + By Layer */}
          {analytics && (
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
              {Object.keys(analytics.by_strategy).length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle>By Strategy</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-3">
                      {Object.entries(analytics.by_strategy).map(([strategy, data]) => (
                        <div
                          key={strategy}
                          className="flex items-center justify-between rounded-lg bg-surface-1 p-3 dark:bg-gray-700/50"
                        >
                          <div>
                            <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                              {strategy.replace(/_/g, " ")}
                            </p>
                            <p className="text-xs text-gray-500">
                              {data.trades} trades · {data.win_rate}% win rate
                            </p>
                          </div>
                          <p className={`font-mono text-sm font-bold ${pnlColor(data.pnl)}`}>
                            ${data.pnl.toFixed(2)}
                          </p>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}
              {Object.keys(analytics.by_layer).length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle>By Layer</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-3">
                      {Object.entries(analytics.by_layer).map(([layer, data]) => (
                        <div
                          key={layer}
                          className="flex items-center justify-between rounded-lg bg-surface-1 p-3 dark:bg-gray-700/50"
                        >
                          <div>
                            <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                              {layer}
                            </p>
                            <p className="text-xs text-gray-500">
                              {data.trades} trades · {data.win_rate}% win rate
                            </p>
                          </div>
                          <p className={`font-mono text-sm font-bold ${pnlColor(data.pnl)}`}>
                            ${data.pnl.toFixed(2)}
                          </p>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          )}

          {/* Trade Table */}
          {detail.trades.length > 0 && (
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>Trade Outcomes ({detail.trades.length})</CardTitle>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => deleteMutation.mutate(selectedId!)}
                    disabled={deleteMutation.isPending}
                  >
                    <Trash2 className="h-4 w-4 text-red-400" /> Delete
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-surface-3 text-[10px] uppercase text-gray-400 dark:border-gray-700">
                        <th className="pb-2 pr-4 text-left">Ticker</th>
                        <th className="pb-2 pr-4 text-left">Strategy</th>
                        <th className="pb-2 pr-4 text-right">Score</th>
                        <th className="pb-2 pr-4 text-right">Entry</th>
                        <th className="pb-2 pr-4 text-right">Exit</th>
                        <th className="pb-2 pr-4 text-right">Move%</th>
                        <th className="pb-2 pr-4 text-right">P&L</th>
                        <th className="pb-2 pr-4 text-right">P&L%</th>
                        <th className="pb-2 pr-4 text-center">Outcome</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.trades.map((t) => (
                        <tr
                          key={t.id}
                          className="border-b border-surface-2 dark:border-gray-800"
                        >
                          <td className="py-2 pr-4 font-semibold">{t.ticker}</td>
                          <td className="py-2 pr-4 text-xs text-gray-500">
                            {(t.strategy_type || "").replace(/_/g, " ")}
                          </td>
                          <td className="py-2 pr-4 text-right font-mono">
                            {t.entry_score.toFixed(1)}
                          </td>
                          <td className="py-2 pr-4 text-right font-mono">
                            ${t.entry_spot.toFixed(2)}
                          </td>
                          <td className="py-2 pr-4 text-right font-mono">
                            {t.exit_spot != null ? `$${t.exit_spot.toFixed(2)}` : "—"}
                          </td>
                          <td className="py-2 pr-4 text-right font-mono">
                            {t.earnings_move_pct != null
                              ? `${t.earnings_move_pct > 0 ? "+" : ""}${t.earnings_move_pct.toFixed(1)}%`
                              : "—"}
                          </td>
                          <td
                            className={`py-2 pr-4 text-right font-mono font-semibold ${pnlColor(
                              t.realized_pnl || 0
                            )}`}
                          >
                            {t.realized_pnl != null ? `$${t.realized_pnl.toFixed(2)}` : "—"}
                          </td>
                          <td
                            className={`py-2 pr-4 text-right font-mono ${pnlColor(
                              t.realized_pnl_pct || 0
                            )}`}
                          >
                            {t.realized_pnl_pct != null
                              ? `${t.realized_pnl_pct > 0 ? "+" : ""}${t.realized_pnl_pct.toFixed(1)}%`
                              : "—"}
                          </td>
                          <td className="py-2 pr-4 text-center">
                            <Badge variant={outcomeVariant(t.outcome)}>
                              {t.outcome || "—"}
                            </Badge>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
