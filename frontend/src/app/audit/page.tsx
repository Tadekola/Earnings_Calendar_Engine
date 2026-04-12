"use client";

import { useEffect, useState } from "react";
import { api, AuditEntry } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { CardSkeleton } from "@/components/ui/skeleton";
import { ClipboardList } from "lucide-react";

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

  function eventVariant(type: string): "default" | "healthy" | "watchlist" {
    if (type === "scan_completed") return "healthy";
    if (type === "setting_changed") return "watchlist";
    return "default";
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="h-7 w-32 rounded bg-surface-3 animate-pulse-subtle" />
        <CardSkeleton />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-gray-900 dark:text-gray-100">Audit Trail</h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Chronological record of system events and user actions
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
          {error}
        </div>
      )}

      {entries.length === 0 ? (
        <Card>
          <CardContent className="p-8 text-center">
            <ClipboardList className="mx-auto h-8 w-8 text-gray-300 dark:text-gray-600" />
            <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
              No audit entries yet. Run a scan or change a setting to generate entries.
            </p>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <ClipboardList className="h-4 w-4 text-gray-500" />
              <CardTitle>Event Log ({entries.length})</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="border-b border-surface-3 text-left text-[10px] font-medium uppercase tracking-wider text-gray-400 dark:border-gray-600">
                    <th className="pb-3 pr-4">Time</th>
                    <th className="pb-3 pr-4">Event</th>
                    <th className="pb-3 pr-4">Run ID</th>
                    <th className="pb-3">Details</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-2 dark:divide-gray-700">
                  {entries.map((e) => {
                    const payload = parsePayload(e.payload);
                    return (
                      <tr key={e.id} className="transition-colors hover:bg-surface-1 dark:hover:bg-gray-700/50">
                        <td className="whitespace-nowrap py-3 pr-4 font-mono text-xs text-gray-500 dark:text-gray-400">
                          {e.created_at ? new Date(e.created_at).toLocaleString() : "—"}
                        </td>
                        <td className="py-3 pr-4">
                          <Badge variant={eventVariant(e.event_type)}>
                            {e.event_type}
                          </Badge>
                        </td>
                        <td className="py-3 pr-4 font-mono text-xs text-gray-500 dark:text-gray-400">
                          {e.scan_run_id ? e.scan_run_id.slice(0, 8) : "—"}
                        </td>
                        <td className="py-3 text-xs text-gray-600 dark:text-gray-300">
                          {payload ? (
                            <div className="flex flex-wrap gap-1">
                              {Object.entries(payload).map(([k, v]) => (
                                <span
                                  key={k}
                                  className="inline-flex rounded bg-surface-2 px-1.5 py-0.5 font-mono dark:bg-gray-700"
                                >
                                  <span className="font-medium text-gray-700 dark:text-gray-200">{k}:</span>
                                  <span className="ml-1 text-gray-500 dark:text-gray-400">
                                    {typeof v === "object" ? JSON.stringify(v) : String(v)}
                                  </span>
                                </span>
                              ))}
                            </div>
                          ) : (
                            <span className="text-gray-400">—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
