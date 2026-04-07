"use client";

import { useEffect, useState } from "react";
import { api, AppSettings, SchedulerStatus } from "@/lib/api";

export default function SettingsPage() {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [scheduler, setScheduler] = useState<SchedulerStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [triggering, setTriggering] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [editMode, setEditMode] = useState(false);
  const [draft, setDraft] = useState<Record<string, any>>({});

  useEffect(() => {
    loadSettings();
  }, []);

  async function loadSettings() {
    setLoading(true);
    try {
      const [settingsData, schedulerData] = await Promise.allSettled([
        api.settings(),
        api.schedulerStatus(),
      ]);
      if (settingsData.status === "fulfilled") setSettings(settingsData.value);
      if (schedulerData.status === "fulfilled") setScheduler(schedulerData.value);
      if (settingsData.status === "rejected") setError(settingsData.reason?.message);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const updated = await api.updateSettings(draft);
      setSettings(updated);
      setDraft({});
      setEditMode(false);
      setSuccess("Settings saved successfully");
      setTimeout(() => setSuccess(null), 3000);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleTriggerScan() {
    setTriggering(true);
    try {
      await api.triggerScan();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setTriggering(false);
    }
  }

  function updateDraft(key: string, value: any) {
    setDraft((prev) => ({ ...prev, [key]: value }));
  }

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center text-gray-500">
        Loading settings...
      </div>
    );
  }

  if (!settings) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
        {error || "Failed to load settings"}
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Settings</h1>
          <p className="text-sm text-gray-500">
            Configure scanning parameters, thresholds, and operating mode
          </p>
        </div>
        <div className="flex items-center gap-3">
          {editMode ? (
            <>
              <button
                onClick={() => { setEditMode(false); setDraft({}); }}
                className="rounded-md border border-surface-3 px-4 py-2 text-sm text-gray-600 hover:bg-surface-1"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={saving || Object.keys(draft).length === 0}
                className="btn-primary text-sm"
              >
                {saving ? "Saving..." : "Save Changes"}
              </button>
            </>
          ) : (
            <button
              onClick={() => setEditMode(true)}
              className="rounded-md border border-brand-500 px-4 py-2 text-sm font-medium text-brand-600 hover:bg-brand-50"
            >
              Edit Settings
            </button>
          )}
        </div>
      </div>

      {success && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
          {success}
        </div>
      )}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          {error}
        </div>
      )}

      {/* Operating Mode */}
      <div className="card">
        <h2 className="text-lg font-semibold">Operating Mode</h2>
        <p className="mt-1 text-sm text-gray-500">
          Strict mode rejects all recommendations when critical data is stale.
          Graceful mode allows watchlist entries with warnings.
        </p>
        <div className="mt-4 flex items-center gap-4">
          {["STRICT", "GRACEFUL"].map((mode) => (
            <button
              key={mode}
              disabled={!editMode}
              onClick={() => editMode && updateDraft("operating_mode", mode)}
              className={`rounded-lg border-2 px-4 py-3 text-center text-sm font-medium transition ${
                (draft.operating_mode || settings.operating_mode) === mode
                  ? "border-brand-600 bg-brand-50 text-brand-700"
                  : "border-surface-3 text-gray-500"
              } ${editMode ? "cursor-pointer hover:border-brand-400" : ""}`}
            >
              {mode}
            </button>
          ))}
        </div>
      </div>

      {/* Scoring Thresholds */}
      <div className="card">
        <h2 className="text-lg font-semibold">Scoring Weights</h2>
        <p className="mt-1 text-sm text-gray-500">
          Weighted score out of 100. Version: {settings.scoring.scoring_version}
        </p>
        <div className="mt-4 space-y-3">
          {[
            { key: "liquidity_weight", label: "Liquidity Quality" },
            { key: "earnings_timing_weight", label: "Earnings Timing" },
            { key: "vol_term_structure_weight", label: "Vol Term Structure" },
            { key: "containment_weight", label: "Pre-earnings Containment" },
            { key: "pricing_efficiency_weight", label: "Pricing Efficiency" },
            { key: "event_cleanliness_weight", label: "Event Cleanliness" },
            { key: "historical_fit_weight", label: "Historical Fit" },
          ].map((item) => (
            <div key={item.key} className="flex items-center justify-between">
              <span className="text-sm text-gray-700">{item.label}</span>
              <div className="flex items-center gap-3">
                <div className="h-2 w-32 rounded-full bg-surface-2">
                  <div
                    className="h-2 rounded-full bg-brand-500"
                    style={{
                      width: `${((settings.scoring[item.key] as number) / 25) * 100}%`,
                    }}
                  />
                </div>
                <span className="w-8 text-right text-sm font-mono font-medium">
                  {settings.scoring[item.key]}
                </span>
              </div>
            </div>
          ))}
        </div>
        <div className="mt-4 flex items-center gap-6 rounded-md bg-surface-1 p-3">
          <div className="text-sm flex items-center gap-2">
            <span className="text-gray-500">Recommend threshold:</span>
            {editMode ? (
              <input
                type="number"
                step="1"
                min="0"
                max="100"
                defaultValue={settings.scoring.recommend_threshold as number}
                onChange={(e) => updateDraft("recommend_threshold", Number(e.target.value))}
                className="w-16 rounded border border-surface-3 px-2 py-0.5 text-sm font-mono"
              />
            ) : (
              <span className="font-semibold text-emerald-700">
                {settings.scoring.recommend_threshold}
              </span>
            )}
          </div>
          <div className="text-sm flex items-center gap-2">
            <span className="text-gray-500">Watchlist threshold:</span>
            {editMode ? (
              <input
                type="number"
                step="1"
                min="0"
                max="100"
                defaultValue={settings.scoring.watchlist_threshold as number}
                onChange={(e) => updateDraft("watchlist_threshold", Number(e.target.value))}
                className="w-16 rounded border border-surface-3 px-2 py-0.5 text-sm font-mono"
              />
            ) : (
              <span className="font-semibold text-amber-700">
                {settings.scoring.watchlist_threshold}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Liquidity Rules */}
      <div className="card">
        <h2 className="text-lg font-semibold">Liquidity Rules</h2>
        <p className="mt-1 text-sm text-gray-500">
          Minimum thresholds for trade eligibility
        </p>
        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
          {Object.entries(settings.liquidity).map(([key, val]) => (
            <div key={key} className="flex items-center justify-between rounded-md bg-surface-1 px-3 py-2">
              <span className="text-xs text-gray-600">
                {key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
              </span>
              <span className="font-mono text-sm font-medium">
                {typeof val === "number" ? val.toLocaleString() : String(val)}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Earnings Window */}
      <div className="card">
        <h2 className="text-lg font-semibold">Earnings Window</h2>
        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
          {Object.entries(settings.earnings_window).map(([key, val]) => (
            <div key={key} className="flex items-center justify-between rounded-md bg-surface-1 px-3 py-2">
              <span className="text-xs text-gray-600">
                {key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
              </span>
              <span className="font-mono text-sm font-medium">
                {typeof val === "boolean" ? (val ? "Yes" : "No") : String(val)}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Universe */}
      <div className="card">
        <h2 className="text-lg font-semibold">Active Universe</h2>
        <p className="mt-1 text-sm text-gray-500">
          Source: {settings.universe_source} | {settings.universe_tickers.length} tickers
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          {settings.universe_tickers.map((t) => (
            <span
              key={t}
              className="inline-flex items-center rounded-md bg-brand-50 px-2.5 py-1 text-xs font-medium text-brand-700"
            >
              {t}
            </span>
          ))}
        </div>
      </div>

      {/* Scheduler */}
      <div className="card">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">Scan Scheduler</h2>
            <p className="mt-1 text-sm text-gray-500">
              Automated scans run before market open and after close on weekdays
            </p>
          </div>
          <div className="flex items-center gap-3">
            {scheduler && (
              <span
                className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                  scheduler.running
                    ? "bg-emerald-100 text-emerald-800"
                    : "bg-gray-100 text-gray-600"
                }`}
              >
                {scheduler.running ? "Running" : "Stopped"}
              </span>
            )}
            <button
              onClick={handleTriggerScan}
              disabled={triggering}
              className="btn-primary text-sm"
            >
              {triggering ? "Triggering..." : "Run Scan Now"}
            </button>
          </div>
        </div>
        {scheduler && scheduler.jobs.length > 0 && (
          <div className="mt-4 space-y-2">
            {scheduler.jobs.map((job) => (
              <div
                key={job.id}
                className="flex items-center justify-between rounded-md bg-surface-1 px-3 py-2 text-sm"
              >
                <span className="font-medium">{job.name}</span>
                <span className="text-xs text-gray-500">
                  Next: {job.next_run ? new Date(job.next_run).toLocaleString() : "—"}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Editable Earnings Window */}
      {editMode && (
        <div className="card">
          <h2 className="text-lg font-semibold">Edit Earnings Window</h2>
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
            {[
              { key: "min_days_to_earnings", label: "Min Days to Earnings", current: settings.earnings_window.min_days_to_earnings },
              { key: "max_days_to_earnings", label: "Max Days to Earnings", current: settings.earnings_window.max_days_to_earnings },
              { key: "exit_days_before_earnings", label: "Exit Days Before Earnings", current: settings.earnings_window.exit_days_before_earnings },
            ].map((item) => (
              <div key={item.key} className="flex items-center justify-between rounded-md bg-surface-1 px-3 py-2">
                <span className="text-xs text-gray-600">{item.label}</span>
                <input
                  type="number"
                  min="0"
                  defaultValue={item.current as number}
                  onChange={(e) => updateDraft(item.key, Number(e.target.value))}
                  className="w-16 rounded border border-surface-3 px-2 py-0.5 text-sm font-mono"
                />
              </div>
            ))}
            {[
              { key: "min_avg_stock_volume", label: "Min Avg Stock Volume", current: settings.liquidity.min_avg_stock_volume },
              { key: "min_avg_option_volume", label: "Min Avg Option Volume", current: settings.liquidity.min_avg_option_volume },
            ].map((item) => (
              <div key={item.key} className="flex items-center justify-between rounded-md bg-surface-1 px-3 py-2">
                <span className="text-xs text-gray-600">{item.label}</span>
                <input
                  type="number"
                  min="0"
                  defaultValue={item.current}
                  onChange={(e) => updateDraft(item.key, Number(e.target.value))}
                  className="w-24 rounded border border-surface-3 px-2 py-0.5 text-sm font-mono"
                />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Info notice */}
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
        <p className="text-xs text-amber-800">
          {editMode
            ? "Changes are saved to the database and applied immediately. Restart the server to revert to .env defaults."
            : "Click \"Edit Settings\" to modify thresholds and operating mode. Changes persist across restarts."}
        </p>
      </div>
    </div>
  );
}
