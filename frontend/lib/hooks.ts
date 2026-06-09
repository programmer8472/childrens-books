"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { PipelineEvent } from "./types";

const WS_BASE =
  process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8001";

/** Subscribe to the pipeline event stream for a single book. */
export function useBookStream(bookId: string) {
  const [events, setEvents] = useState<PipelineEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const ws = new WebSocket(`${WS_BASE}/books/${bookId}/stream`);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onerror = () => setConnected(false);
    ws.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data as string) as PipelineEvent;
        setEvents((prev) => [...prev.slice(-99), event]);
      } catch {}
    };

    return () => {
      ws.close();
    };
  }, [bookId]);

  const clear = useCallback(() => setEvents([]), []);
  return { events, connected, clear };
}

/** Poll a data-fetching function on an interval. Returns [data, loading, error, refresh]. */
export function usePolling<T>(
  fetcher: () => Promise<T>,
  intervalMs = 8000
): [T | null, boolean, string | null, () => void] {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const counterRef = useRef(0);

  const run = useCallback(async () => {
    try {
      const result = await fetcher();
      setData(result);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    run();
    const id = setInterval(run, intervalMs);
    return () => clearInterval(id);
  }, [run, intervalMs]);

  const refresh = useCallback(() => {
    counterRef.current += 1;
    run();
  }, [run]);

  return [data, loading, error, refresh];
}
