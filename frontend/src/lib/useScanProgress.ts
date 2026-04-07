"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export interface ScanProgressEvent {
  type: "ticker_complete";
  run_id: string;
  ticker: string;
  classification: string;
  score: number | null;
  index: number;
  total: number;
  pct: number;
}

export interface ScanCompleteEvent {
  type: "scan_complete";
  run_id: string;
  total_scanned: number;
  total_recommended: number;
  total_watchlist: number;
  total_rejected: number;
}

export interface ScanErrorEvent {
  type: "scan_error";
  run_id: string;
  error: string;
}

export type ScanWsEvent = ScanProgressEvent | ScanCompleteEvent | ScanErrorEvent;

export function useScanProgress(onComplete?: (e: ScanCompleteEvent) => void, onError?: (e: ScanErrorEvent) => void) {
  const [events, setEvents] = useState<ScanProgressEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const onCompleteRef = useRef(onComplete);
  const onErrorRef = useRef(onError);
  onCompleteRef.current = onComplete;
  onErrorRef.current = onError;

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/api/v1/ws/scan`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onerror = () => setConnected(false);
    ws.onmessage = (e) => {
      try {
        const data: ScanWsEvent = JSON.parse(e.data);
        if (data.type === "ticker_complete") {
          setEvents((prev) => [...prev, data]);
        } else if (data.type === "scan_complete") {
          onCompleteRef.current?.(data);
        } else if (data.type === "scan_error") {
          onErrorRef.current?.(data);
        }
      } catch {}
    };
  }, []);

  const reset = useCallback(() => {
    setEvents([]);
  }, []);

  const disconnect = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    setConnected(false);
  }, []);

  useEffect(() => {
    return () => {
      wsRef.current?.close();
    };
  }, []);

  return { events, connected, connect, disconnect, reset };
}
