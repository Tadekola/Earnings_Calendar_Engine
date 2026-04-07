"use client";

import { useEffect, useState } from "react";
import { api, AuditEntry } from "@/lib/api";

export default function AuditPage() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadAudit();
  }, []);

  async function loadAudit() {
    setLoading(true);
    try {
      const data = await api.auditLog();
      setEntries(data);
    } catch (err: any) {
      setError(err.message || "Failed to load audit log");
    } finally {
      setLoading(false);
    }
  }

  function parsePayload(payload: string | null): Record<string, any> | null {
    if (!payload) return null;
    try {
      return JSON.parse(payload);
    } catch {
      return null;
    }
  }

  const typeColors: Record<string, string> = {
    scan_triggered: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
    scan_completed: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200",
    setting_changed: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200",
  };

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center text-gray-500">
        Loading audit log...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold dark:text-gray-100">Audit Trail</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Chronological record of system events and user actions
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
          {error}
        </div>
      )}

      {entries.length === 0 ? (
        <div className="card text-center text-sm text-gray-500 dark:text-gray-400">
          No audit entries yet. Run a scan or change a setting to generate entries.
        </div>
      ) : (
        <div className="card overflow-x-auto p-0">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-surface-3 text-left text-xs font-medium uppercase text-gray-500 dark:border-gray-700 dark:text-gray-400">
                <th className="px-4 py-3">Time</th>
                <th className="px-4 py-3">Event</th>
                <th className="px-4 py-3">Run ID</th>
                <th className="px-4 py-3">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-2 dark:divide-gray-700">
              {entries.map((e) => {
                const payload = parsePayload(e.payload);
                return (
                  <tr key={e.id} className="hover:bg-surface-1 dark:hover:bg-gray-700/50">
                    <td className="whitespace-nowrap px-4 py-3 text-xs text-gray-500 dark:text-gray-400">
                      {e.created_at
                        ? new Date(e.created_at).toLocaleString()
                        : "—"}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                          typeColors[e.event_type] || "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300"
                        }`}
                      >
                        {e.event_type}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-gray-500 dark:text-gray-400">
                      {e.scan_run_id ? e.scan_run_id.slice(0, 8) : "—"}
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-600 dark:text-gray-300">
                      {payload ? (
                        <div className="flex flex-wrap gap-1">
                          {Object.entries(payload).map(([k, v]) => (
                            <span
                              key={k}
                              className="inline-flex rounded bg-surface-2 px-1.5 py-0.5 dark:bg-gray-700"
                            >
                              <span className="font-medium">{k}:</span>{" "}
                              <span className="ml-1">
                                {typeof v === "object" ? JSON.stringify(v) : String(v)}
                              </span>
                            </span>
                          ))}
                        </div>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
