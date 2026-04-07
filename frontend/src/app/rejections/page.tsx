"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

interface Rejection {
  ticker: string;
  stage: string;
  reason: string;
  details: string | null;
}

interface RejectionsData {
  total: number;
  scan_run_id: string | null;
  rejections: Rejection[];
}

export default function RejectionsPage() {
  const [data, setData] = useState<RejectionsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const result = await api.rejections();
      setData(result);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center text-gray-500">
        Loading rejections...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Rejections</h1>
          <p className="text-sm text-gray-500">
            Understand why names were rejected — builds trust and aids debugging
          </p>
        </div>
        <button onClick={load} disabled={loading} className="btn-primary">
          Refresh
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          {error}
        </div>
      )}

      {data && data.rejections.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center gap-4">
            <p className="text-sm text-gray-500">
              {data.total} name{data.total !== 1 ? "s" : ""} rejected
            </p>
            {data.scan_run_id && (
              <span className="text-xs font-mono text-gray-400">
                Scan: {data.scan_run_id.slice(0, 8)}
              </span>
            )}
          </div>
          {data.rejections.map((r) => (
            <div key={r.ticker} className="card">
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold text-gray-900">{r.ticker}</h3>
                    <span className="badge-no-trade">NO_TRADE</span>
                  </div>
                  <p className="mt-1 text-xs text-gray-500">
                    Stage: {r.stage}
                  </p>
                </div>
                <a
                  href={`/trades?ticker=${r.ticker}`}
                  className="text-xs text-brand-600 hover:underline"
                >
                  Try anyway →
                </a>
              </div>

              <div className="mt-3">
                <p className="text-xs font-medium text-gray-500 uppercase">Rejection Reason</p>
                <p className="mt-1 flex items-start gap-2 text-sm text-gray-700">
                  <span className="mt-0.5 text-red-400">✕</span>
                  {r.reason}
                </p>
              </div>

              {r.details && (
                <p className="mt-3 text-sm text-gray-600 leading-relaxed">
                  {r.details}
                </p>
              )}
            </div>
          ))}
        </div>
      )}

      {data && data.rejections.length === 0 && (
        <div className="flex h-64 flex-col items-center justify-center gap-2 text-gray-400">
          <p>No rejections found</p>
          <p className="text-xs">Run a scan first from the Scan page</p>
        </div>
      )}
    </div>
  );
}
