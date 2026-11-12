"use client";
import { useCallback, useEffect, useRef, useState } from "react";

import { get } from "./api";

export function useApi<T = any>(path: string | null, params?: Record<string, any>, refreshMs?: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState<boolean>(!!path);
  const key = path ? path + JSON.stringify(params || {}) : null;
  const alive = useRef(true);

  const load = useCallback(async () => {
    if (!path) return;
    setLoading(true);
    try {
      const d = await get<T>(path, params);
      if (alive.current) {
        setData(d);
        setError(null);
      }
    } catch (e) {
      if (alive.current) setError(e);
    } finally {
      if (alive.current) setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  useEffect(() => {
    alive.current = true;
    load();
    let t: ReturnType<typeof setInterval> | undefined;
    if (refreshMs) t = setInterval(load, refreshMs);
    return () => {
      alive.current = false;
      if (t) clearInterval(t);
    };
  }, [load, refreshMs]);

  return { data, error, loading, reload: load };
}
