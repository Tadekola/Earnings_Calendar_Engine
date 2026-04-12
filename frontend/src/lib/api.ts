const API_BASE = '';

export interface ProviderHealth {
  provider: string;
  source_name: string;
  is_connected: boolean;
  confidence_score: number;
  severity: 'HEALTHY' | 'DEGRADED' | 'CRITICAL';
  error_details: string | null;
}

export interface HealthResponse {
  status: 'HEALTHY' | 'DEGRADED' | 'CRITICAL';
  environment: string;
  operating_mode: string;
  timestamp: string;
  version: string;
  providers: ProviderHealth[];
  database_connected: boolean;
}

export interface EarningsEvent {
  ticker: string;
  earnings_date: string;
  report_timing: string;
  confidence: string;
  source: string;
  source_confidence: number;
  fiscal_quarter: string | null;
  fiscal_year: number | null;
  days_until_earnings: number;
}

export interface UpcomingEarningsResponse {
  total: number;
  window_start: string;
  window_end: string;
  earnings: EarningsEvent[];
}

export interface ScoreBreakdown {
  factor: string;
  weight: number;
  raw_score: number;
  weighted_score: number;
  rationale: string;
}

export interface ScanResult {
  ticker: string;
  classification: 'RECOMMEND' | 'WATCHLIST' | 'NO_TRADE';
  overall_score: number | null;
  stage_reached: string;
  rejection_reasons: string[] | null;
  rationale_summary: string | null;
  score_breakdown: ScoreBreakdown[] | null;
  risk_warnings: string[] | null;
  processing_time_ms: number | null;
  strategy_type?: string;
  layer_id?: string;
  account_id?: string;
}

export interface ScanRunResponse {
  run_id: string;
  status: string;
  total_scanned: number;
  total_recommended: number;
  total_watchlist: number;
  total_rejected: number;
  operating_mode: string;
  scoring_version: string;
  started_at: string;
  completed_at: string | null;
  results: ScanResult[];
}

export interface TradeLeg {
  leg_number: number;
  option_type: 'CALL' | 'PUT';
  side: 'BUY' | 'SELL';
  strike: number;
  expiration: string;
  bid: number | null;
  ask: number | null;
  mid: number | null;
  implied_volatility: number | null;
  delta: number | null;
  open_interest: number | null;
  spread_to_mid: number | null;
}

export interface RecommendedTrade {
  ticker: string;
  spot_price: number;
  earnings_date: string;
  earnings_confidence: string;
  entry_date_start: string;
  entry_date_end: string;
  planned_exit_date: string;
  short_expiry: string;
  long_expiry: string;
  lower_strike: number;
  upper_strike: number;
  total_debit_mid: number;
  total_debit_pessimistic?: number;
  estimated_max_loss: number;
  profit_zone_low?: number;
  profit_zone_high?: number;
  classification: string;
  overall_score: number;
  rationale_summary?: string;
  key_risks: string[];
  risk_disclaimer: string;
  strategy_type?: string;
  layer_id?: string;
  account_id?: string;
  legs: TradeLeg[];
}

export interface ExplainFactor {
  factor: string;
  score: number;
  weight: number;
  weighted_contribution: number;
  explanation: string;
}

export interface ExplainResponse {
  ticker: string;
  classification: string;
  overall_score: number | null;
  summary: string;
  factors: ExplainFactor[];
  rejection_reasons: string[];
  risk_warnings: string[];
  data_quality_notes: string[];
  recommendation_rationale: string | null;
}

export interface UniverseTicker {
  ticker: string;
  name: string | null;
  sector: string | null;
  is_active: boolean;
}

export interface TopCandidate {
  ticker: string;
  score: number;
  classification: string;
  scan_run_id: string;
  strategy_type?: string;
  scanned_at?: string;
}

export interface RecentScan {
  run_id: string;
  status: string;
  total_scanned: number;
  total_recommended: number;
  total_watchlist: number;
  total_rejected: number;
  started_at: string;
  completed_at: string | null;
}

export interface DashboardSummary {
  total_scans: number;
  total_candidates_scanned: number;
  total_recommendations: number;
  total_watchlist: number;
  avg_score: number | null;
  recent_scans: RecentScan[];
  top_candidates: TopCandidate[];
  last_scan_at: string | null;
}

export interface AuditEntry {
  id: number;
  event_type: string;
  scan_run_id: string | null;
  ticker: string | null;
  payload: string | null;
  created_at: string | null;
}

export interface AppSettings {
  operating_mode: string;
  universe_source: string;
  scoring: Record<string, number | string>;
  liquidity: Record<string, number>;
  earnings_window: Record<string, number | boolean>;
  universe_tickers: string[];
}

export interface SchedulerJob {
  id: string;
  name: string;
  next_run: string | null;
}

export interface SchedulerStatus {
  running: boolean;
  jobs: SchedulerJob[];
}

export interface IVPoint {
  expiration: string;
  days_to_expiry: number;
  atm_iv: number;
  call_iv: number | null;
  put_iv: number | null;
}

export interface IVTermStructure {
  ticker: string;
  spot_price: number;
  points: IVPoint[];
}

// ── Backtesting ──────────────────────────────────────────

export interface BacktestTrade {
  id: number;
  backtest_id: string;
  ticker: string;
  strategy_type: string;
  layer_id: string | null;
  account_id: string | null;
  entry_score: number;
  entry_date: string;
  entry_spot: number;
  entry_debit: number;
  exit_date: string | null;
  exit_spot: number | null;
  exit_credit: number | null;
  exit_reason: string | null;
  earnings_date: string | null;
  earnings_move_pct: number | null;
  realized_pnl: number | null;
  realized_pnl_pct: number | null;
  hold_days: number | null;
  outcome: string | null;
  lower_strike: number | null;
  upper_strike: number | null;
}

export interface BacktestSummary {
  backtest_id: string;
  name: string;
  status: string;
  strategy_filter: string | null;
  min_score: number;
  start_date: string | null;
  end_date: string | null;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  total_pnl: number;
  avg_pnl_per_trade: number | null;
  win_rate: number | null;
  avg_hold_days: number | null;
  max_drawdown: number | null;
  sharpe_ratio: number | null;
  started_at: string;
  completed_at: string | null;
  error_message: string | null;
}

export interface BacktestDetail extends BacktestSummary {
  trades: BacktestTrade[];
}

export interface BacktestListResponse {
  total: number;
  backtests: BacktestSummary[];
}

export interface PnlCurvePoint {
  trade_index: number;
  ticker: string;
  cumulative_pnl: number;
  trade_pnl: number;
  date: string;
}

export interface BacktestAnalytics {
  backtest_id: string;
  pnl_curve: PnlCurvePoint[];
  by_strategy: Record<string, { trades: number; wins: number; pnl: number; win_rate: number }>;
  by_layer: Record<string, { trades: number; wins: number; pnl: number; win_rate: number }>;
  monthly_pnl: Record<string, number>;
}

async function fetchAPI<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `API error: ${res.status}`);
  }
  return res.json();
}

export const api = {
  health: () => fetchAPI<HealthResponse>('/health'),
  upcomingEarnings: (days = 30) =>
    fetchAPI<UpcomingEarningsResponse>(`/api/v1/earnings/upcoming?days_ahead=${days}`),
  runScan: (tickers?: string[]) =>
    fetchAPI<ScanRunResponse>('/api/v1/scan/run', {
      method: 'POST',
      body: JSON.stringify(tickers ? { tickers } : {}),
      signal: AbortSignal.timeout(300_000),
    }),
  runScanAsync: (tickers?: string[]) =>
    fetchAPI<{ run_id: string; status: string }>('/api/v1/scan/run/async', {
      method: 'POST',
      body: JSON.stringify(tickers ? { tickers } : {}),
    }),
  getScanRun: (runId: string) =>
    fetchAPI<ScanRunResponse>(`/api/v1/scan/run/${runId}`),
  scanResults: () => fetchAPI<{ run_id: string; status: string; total_scanned: number; total_recommended: number; total_watchlist: number; total_rejected: number; started_at: string; completed_at: string | null }[]>('/api/v1/scan/results'),
  candidate: (ticker: string) => fetchAPI<any>(`/api/v1/candidates/${ticker}`),
  buildTrade: (ticker: string) =>
    fetchAPI<RecommendedTrade>('/api/v1/trades/build', {
      method: 'POST',
      body: JSON.stringify({ ticker }),
    }),
  explain: (ticker: string, strategy?: string) => {
    let url = `/api/v1/explain/${ticker}`;
    if (strategy) url += `?strategy=${strategy}`;
    return fetchAPI<ExplainResponse>(url);
  },
  recommendedTrade: (ticker: string, strategy?: string) => {
    let url = `/api/v1/trades/${ticker}/recommended`;
    if (strategy) url += `?strategy=${strategy}`;
    return fetchAPI<RecommendedTrade>(url);
  },
  universe: () => fetchAPI<{ total: number; active: number; tickers: UniverseTicker[] }>('/api/v1/universe'),
  rejections: () => fetchAPI<{ total: number; scan_run_id: string | null; rejections: { ticker: string; stage: string; reason: string; details: string | null }[] }>('/api/v1/rejections'),
  dashboardSummary: () => fetchAPI<DashboardSummary>('/api/v1/dashboard/summary'),
  auditLog: () => fetchAPI<AuditEntry[]>('/api/v1/dashboard/audit'),
  settings: () => fetchAPI<AppSettings>('/api/v1/settings'),
  updateSettings: (overrides: Record<string, any>) =>
    fetchAPI<AppSettings>('/api/v1/settings', {
      method: 'PUT',
      body: JSON.stringify(overrides),
    }),
  exportScansCSV: () => `${API_BASE}/api/v1/export/scans/csv`,
  exportCandidatesCSV: (runId?: string) =>
    `${API_BASE}/api/v1/export/candidates/csv${runId ? `?run_id=${runId}` : ''}`,
  exportScoresCSV: (runId?: string) =>
    `${API_BASE}/api/v1/export/scores/csv${runId ? `?run_id=${runId}` : ''}`,
  schedulerStatus: () => fetchAPI<SchedulerStatus>('/api/v1/settings/scheduler'),
  triggerScan: () => fetchAPI<{ status: string; message: string }>('/api/v1/settings/scheduler/trigger', { method: 'POST' }),
  ivTermStructure: (ticker: string) => fetchAPI<IVTermStructure>(`/api/v1/candidates/${ticker}/iv-term-structure`),
  // Backtesting
  createBacktest: (body: { name: string; strategy_filter?: string; min_score?: number; start_date?: string; end_date?: string }) =>
    fetchAPI<BacktestDetail>('/api/v1/backtests', { method: 'POST', body: JSON.stringify(body) }),
  listBacktests: () => fetchAPI<BacktestListResponse>('/api/v1/backtests'),
  getBacktest: (id: string) => fetchAPI<BacktestDetail>(`/api/v1/backtests/${id}`),
  getBacktestAnalytics: (id: string) => fetchAPI<BacktestAnalytics>(`/api/v1/backtests/${id}/analytics`),
  deleteBacktest: (id: string) => fetchAPI<void>(`/api/v1/backtests/${id}`, { method: 'DELETE' }),
};
