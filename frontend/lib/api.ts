"use client";

import { useCallback } from "react";
import { useAuth } from "./auth";
import { config } from "./config";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public retryAfter?: number,
    public detail?: Record<string, unknown>,
  ) {
    super(message);
  }
}

const NETWORK_MESSAGE = "เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ ตรวจสอบว่า backend ทำงานอยู่ แล้วลองใหม่";

export function useApi() {
  const { getToken, mockUser } = useAuth();

  const request = useCallback(
    async (path: string, init: RequestInit = {}): Promise<Response> => {
      const headers = new Headers(init.headers);
      const token = await getToken();
      if (token) headers.set("Authorization", `Bearer ${token}`);
      if (config.authMode === "mock") headers.set("X-Mock-User", mockUser);
      if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
        headers.set("Content-Type", "application/json");
      }
      let res: Response;
      try {
        res = await fetch(`${config.apiBase}${path}`, { ...init, headers });
      } catch {
        throw new ApiError(0, "network", NETWORK_MESSAGE);
      }
      if (!res.ok) {
        let code = "http_error";
        let message = `เกิดข้อผิดพลาด (HTTP ${res.status})`;
        let detail: Record<string, unknown> | undefined;
        try {
          const body = await res.json();
          code = body?.error?.code ?? code;
          message = body?.error?.message ?? message;
          detail = body?.error?.detail;
        } catch {
          /* non-JSON error */
        }
        const ra = res.headers.get("Retry-After");
        throw new ApiError(res.status, code, message, ra ? Number(ra) : undefined, detail);
      }
      return res;
    },
    [getToken, mockUser],
  );

  const json = useCallback(
    async <T,>(path: string, init: RequestInit = {}): Promise<T> => (await request(path, init)).json() as Promise<T>,
    [request],
  );

  const blob = useCallback(async (path: string) => (await request(path)).blob(), [request]);

  return { request, json, blob };
}

export function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    return e.retryAfter ? `${e.message} (ลองใหม่ได้ในอีก ${e.retryAfter} วินาที)` : e.message;
  }
  return e instanceof Error ? e.message : String(e);
}
