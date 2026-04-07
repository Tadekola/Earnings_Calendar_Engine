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

export function useScanProgress() {
  const [events, setEvents] = useState<ScanProgressEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

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
        const data: ScanProgressEvent = JSON.parse(e.data);
        setEvents((prev) => [...prev, data]);
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
