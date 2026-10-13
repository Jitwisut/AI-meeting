"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { errorText, useApi } from "./api";

/** Fetch JSON with loading/error state. Pass `null` as path to skip. */
export function useResource<T>(path: string | null, pollMs?: (data: T | null) => number | null) {
  const { json } = useApi();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(!!path);
  const pollRef = useRef(pollMs);
  pollRef.current = pollMs;

  const load = useCallback(async () => {
    if (!path) return;
    try {
      const d = await json<T>(path);
      setData(d);
      setError(null);
      return d;
    } catch (e) {
      setError(errorText(e));
    } finally {
      setLoading(false);
    }
  }, [json, path]);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    let alive = true;
    const tick = async () => {
      const d = await load();
      const next = pollRef.current?.(d ?? null);
      if (alive && next) timer = setTimeout(tick, next);
    };
    setLoading(!!path);
    tick();
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, [load, path]);

  return { data, setData, error, loading, reload: load };
}
