"use client";

import axios, {
  AxiosError,
  type AxiosInstance,
  type InternalAxiosRequestConfig,
} from "axios";

import { authSnapshot, useAuthStore } from "@/lib/auth-store";
import type { AccessTokenResponse } from "@/types/api";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export const api: AxiosInstance = axios.create({
  baseURL: API_URL,
  headers: { "Content-Type": "application/json" },
  timeout: 120_000,
});

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = authSnapshot().accessToken;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

/**
 * Routes where a 401 means "these credentials are wrong", not "this access
 * token expired", so refreshing and retrying is pointless.
 *
 * Matched as an explicit list rather than a `/auth/` prefix test: every other
 * route under /auth/ -- me, me/avatar, change-password, logout -- carries an
 * ordinary access token and MUST refresh like any other call. Treating the
 * whole prefix as un-refreshable made the settings page fail hard the moment
 * the 15-minute access token expired.
 */
const NO_REFRESH_ROUTES = [
  "/auth/login",
  "/auth/register",
  "/auth/refresh",
  "/auth/reset-password",
];

/** Queue concurrent 401s behind a single refresh so we mint one token, not N. */
let refreshing: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const { refreshToken } = authSnapshot();
  if (!refreshToken) return null;
  try {
    const { data } = await axios.post<AccessTokenResponse>(
      `${API_URL}/auth/refresh`,
      { refresh_token: refreshToken },
      { headers: { "Content-Type": "application/json" } },
    );
    useAuthStore.getState().setAccessToken(data.access_token);
    return data.access_token;
  } catch {
    useAuthStore.getState().clear();
    return null;
  }
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as
      | (InternalAxiosRequestConfig & { _retried?: boolean })
      | undefined;

    const path = original?.url ?? "";
    const isCredentialCall = NO_REFRESH_ROUTES.some((route) => path.includes(route));
    if (
      error.response?.status !== 401 ||
      !original ||
      original._retried ||
      isCredentialCall
    ) {
      return Promise.reject(error);
    }

    original._retried = true;
    refreshing = refreshing ?? refreshAccessToken().finally(() => {
      refreshing = null;
    });

    const token = await refreshing;
    if (!token) {
      if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
        window.location.href = "/login?expired=1";
      }
      return Promise.reject(error);
    }

    original.headers.Authorization = `Bearer ${token}`;
    return api(original);
  },
);

/** Pull a readable message out of a FastAPI error body. */
export function apiErrorMessage(error: unknown, fallback = "Something went wrong."): string {
  if (axios.isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: string };
      if (first?.msg) return first.msg;
    }
    if (error.code === "ECONNABORTED") return "The request timed out. Please try again.";
    if (!error.response) return "Cannot reach the server. Is the API running?";
  }
  return fallback;
}
