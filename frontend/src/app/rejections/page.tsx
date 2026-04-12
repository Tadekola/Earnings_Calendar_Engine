"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CardSkeleton } from "@/components/ui/skeleton";
import {
  RefreshCw,
  XCircle,
  ArrowRight,
} from "lucide-react";

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
  const { data, isLoading: loading, error: queryError, refetch } = useQuery<RejectionsData>({
    queryKey: ["rejections"],
    queryFn: () => api.rejections(),
    staleTime: 15_000,
  });

  const error = queryError ? (queryError as Error).message : null;

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="h-7 w-32 rounded bg-surface-3 animate-pulse-subtle" />
        {[1, 2, 3].map((i) => <CardSkeleton key={i} />)}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900 dark:text-gray-100">Rejections</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Understand why names were rejected — builds trust and aids debugging
          </p>
        </div>
        <Button onClick={() => refetch()} disabled={loading} variant="secondary">
          <RefreshCw className="h-4 w-4" /> Refresh
        </Button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
          {error}
        </div>
      )}

      {data && data.rejections.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center gap-4">
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {data.total} name{data.total !== 1 ? "s" : ""} rejected
            </p>
            {data.scan_run_id && (
              <span className="text-xs font-mono text-gray-400">
                Scan: {data.scan_run_id.slice(0, 8)}
              </span>
            )}
          </div>
          {data.rejections.map((r) => (
            <Card key={r.ticker}>
              <CardContent className="p-5">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="font-semibold text-gray-900 dark:text-gray-100">{r.ticker}</h3>
                      <Badge variant="notrade">NO_TRADE</Badge>
                    </div>
                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                      Stage: <span className="font-mono">{r.stage}</span>
                    </p>
                  </div>
                  <Button variant="ghost" size="sm" asChild>
                    <a href={`/trades?ticker=${r.ticker}`}>
                      Try anyway <ArrowRight className="h-3 w-3" />
                    </a>
                  </Button>
                </div>

                <div className="mt-3">
                  <p className="text-[10px] font-medium uppercase tracking-wider text-gray-400">Rejection Reason</p>
                  <p className="mt-1 flex items-start gap-2 text-sm text-gray-700 dark:text-gray-300">
                    <XCircle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-red-400" />
                    {r.reason}
                  </p>
                </div>

                {r.details && (
                  <p className="mt-3 text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
                    {r.details}
                  </p>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {data && data.rejections.length === 0 && (
        <div className="flex h-64 flex-col items-center justify-center text-gray-400 dark:text-gray-500">
          <XCircle className="mb-3 h-10 w-10 text-gray-300 dark:text-gray-600" />
          <p className="text-sm">No rejections found</p>
          <p className="mt-1 text-xs">Run a scan first from the Scan page</p>
        </div>
      )}
    </div>
  );
}
