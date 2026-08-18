"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import type {
  AnalysisResult,
  Batch,
  BatchListResponse,
  BatchUploadResponse,
  Comparison,
  ComparisonListResponse,
  DashboardStats,
  HealthResponse,
  Project,
  ProjectDetail,
  ProjectListResponse,
  ResultListResponse,
  SuggestionsResponse,
  TaskStatus,
  UploadResponse,
  User,
} from "@/types/api";

export const qk = {
  health: ["health"] as const,
  me: ["me"] as const,
  dashboard: ["dashboard"] as const,
  projects: (page: number) => ["projects", page] as const,
  project: (id: string) => ["project", id] as const,
  results: (page: number, projectId?: string) => ["results", page, projectId ?? ""] as const,
  result: (assetId: string) => ["result", assetId] as const,
  suggestions: (assetId: string) => ["suggestions", assetId] as const,
  comparisons: (page: number) => ["comparisons", page] as const,
  comparison: (id: string) => ["comparison", id] as const,
  batches: (page: number) => ["batches", page] as const,
  batch: (id: string) => ["batch", id] as const,
};

// --- reads -----------------------------------------------------------------
export function useHealth(): UseQueryResult<HealthResponse> {
  return useQuery({
    queryKey: qk.health,
    queryFn: async () => (await api.get<HealthResponse>("/health")).data,
    refetchInterval: 60_000,
    retry: false,
  });
}

export function useMe(enabled = true) {
  return useQuery({
    queryKey: qk.me,
    queryFn: async () => (await api.get<User>("/auth/me")).data,
    enabled,
    retry: false,
  });
}

export function useDashboard() {
  return useQuery({
    queryKey: qk.dashboard,
    queryFn: async () => (await api.get<DashboardStats>("/dashboard")).data,
  });
}

export function useProjects(page = 1, limit = 20) {
  return useQuery({
    queryKey: qk.projects(page),
    queryFn: async () =>
      (await api.get<ProjectListResponse>("/projects", { params: { page, limit } })).data,
  });
}

export function useProject(projectId: string) {
  return useQuery({
    queryKey: qk.project(projectId),
    queryFn: async () => (await api.get<ProjectDetail>(`/projects/${projectId}`)).data,
    enabled: Boolean(projectId),
  });
}

export function useResults(page = 1, limit = 20, projectId?: string) {
  return useQuery({
    queryKey: qk.results(page, projectId),
    queryFn: async () =>
      (
        await api.get<ResultListResponse>("/results", {
          params: { page, limit, ...(projectId ? { project_id: projectId } : {}) },
        })
      ).data,
  });
}

export function useResult(assetId: string) {
  return useQuery({
    queryKey: qk.result(assetId),
    queryFn: async () => (await api.get<AnalysisResult>(`/results/${assetId}`)).data,
    enabled: Boolean(assetId),
    retry: 1,
  });
}

export function useSuggestions(assetId: string, enabled = true) {
  return useQuery({
    queryKey: qk.suggestions(assetId),
    queryFn: async () =>
      (await api.get<SuggestionsResponse>(`/results/${assetId}/suggestions`)).data,
    enabled: Boolean(assetId) && enabled,
  });
}

export function useComparisons(page = 1, limit = 20) {
  return useQuery({
    queryKey: qk.comparisons(page),
    queryFn: async () =>
      (await api.get<ComparisonListResponse>("/compare", { params: { page, limit } })).data,
  });
}

export function useComparison(comparisonId: string) {
  return useQuery({
    queryKey: qk.comparison(comparisonId),
    queryFn: async () => (await api.get<Comparison>(`/compare/${comparisonId}`)).data,
    enabled: Boolean(comparisonId),
  });
}

// --- writes ----------------------------------------------------------------
export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { title: string; description?: string }) =>
      (await api.post<Project>("/projects", body)).data,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["projects"] });
      void qc.invalidateQueries({ queryKey: qk.dashboard });
    },
  });
}

export function useUpdateProject(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { title?: string; description?: string }) =>
      (await api.patch<Project>(`/projects/${projectId}`, body)).data,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["projects"] });
      void qc.invalidateQueries({ queryKey: qk.project(projectId) });
    },
  });
}

export function useDeleteProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (projectId: string) =>
      (await api.delete(`/projects/${projectId}`)).data,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["projects"] });
      void qc.invalidateQueries({ queryKey: qk.dashboard });
    },
  });
}

export function useUpload() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      file,
      projectId,
      onProgress,
    }: {
      file: File;
      projectId?: string;
      onProgress?: (pct: number) => void;
    }) => {
      const form = new FormData();
      form.append("file", file);
      if (projectId) form.append("project_id", projectId);
      const { data } = await api.post<UploadResponse>("/upload", form, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (e) => {
          if (onProgress && e.total) {
            onProgress(Math.round((e.loaded / e.total) * 100));
          }
        },
      });
      return data;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["results"] });
      void qc.invalidateQueries({ queryKey: qk.dashboard });
    },
  });
}

export function useRerun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (assetId: string) =>
      (await api.post<{ new_task_id: string; status: string }>(
        `/results/${assetId}/rerun`,
      )).data,
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["results"] }),
  });
}

export function useDeleteResult() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (assetId: string) => (await api.delete(`/results/${assetId}`)).data,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["results"] });
      void qc.invalidateQueries({ queryKey: qk.dashboard });
    },
  });
}

export function useGenerateSuggestions(assetId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { user_context?: string; regenerate?: boolean }) =>
      (await api.post<SuggestionsResponse>(`/results/${assetId}/suggestions`, body)).data,
    onSuccess: (data) => qc.setQueryData(qk.suggestions(assetId), data),
  });
}

/** Cache slot holding the comparison currently on screen. */
export const CURRENT_COMPARISON_KEY = ["comparison-current"] as const;

export function useCreateComparison() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { asset_id_a: string; asset_id_b: string }) =>
      (await api.post<Comparison>("/compare", body)).data,
    // Written into the cache rather than component state: React Query drops the
    // callbacks passed to mutate() if the component unmounts mid-flight (Strict
    // Mode remounts in dev), but hook-level onSuccess always runs.
    onSuccess: (data) => {
      qc.setQueryData(CURRENT_COMPARISON_KEY, data);
      void qc.invalidateQueries({ queryKey: ["comparisons"] });
    },
  });
}

/** Reactive read of the comparison currently on screen; survives remounts. */
export function useCurrentComparison() {
  return useQuery<Comparison | null>({
    queryKey: CURRENT_COMPARISON_KEY,
    queryFn: () => null,
    staleTime: Infinity,
    gcTime: Infinity,
    initialData: null,
  });
}

// --- task polling ----------------------------------------------------------
const POLL_BASE_MS = 2000;
const BACKOFF_AFTER_MS = 30_000;
const HARD_TIMEOUT_MS = 180_000;

export interface PollState {
  status: TaskStatus | null;
  timedOut: boolean;
  elapsedMs: number;
}

/**
 * Poll GET /status/{task_id} every 2s, easing off after 30s and giving up at
 * 3 minutes so a stuck task surfaces a retry instead of spinning forever.
 */
export function useTaskPolling(taskId: string | null): PollState {
  const [timedOut, setTimedOut] = useState(false);
  const [elapsedMs, setElapsedMs] = useState(0);
  const startedAt = useRef<number>(Date.now());

  useEffect(() => {
    startedAt.current = Date.now();
    setTimedOut(false);
    setElapsedMs(0);
  }, [taskId]);

  useEffect(() => {
    if (!taskId || timedOut) return;
    const id = window.setInterval(() => {
      setElapsedMs(Date.now() - startedAt.current);
    }, 500);
    return () => window.clearInterval(id);
  }, [taskId, timedOut]);

  const query = useQuery({
    queryKey: ["task-status", taskId],
    queryFn: async () => (await api.get<TaskStatus>(`/status/${taskId}`)).data,
    enabled: Boolean(taskId) && !timedOut,
    refetchInterval: (q) => {
      const data = q.state.data as TaskStatus | undefined;
      if (!data) return POLL_BASE_MS;
      if (data.status === "complete" || data.status === "failed") return false;

      const elapsed = Date.now() - startedAt.current;
      if (elapsed > HARD_TIMEOUT_MS) return false;
      if (elapsed > BACKOFF_AFTER_MS) {
        // ease off: 2s -> 4s -> 8s, capped at 10s
        const factor = Math.min(2 ** Math.floor((elapsed - BACKOFF_AFTER_MS) / 30_000 + 1), 5);
        return Math.min(POLL_BASE_MS * factor, 10_000);
      }
      return POLL_BASE_MS;
    },
    retry: 2,
  });

  useEffect(() => {
    if (!taskId || timedOut) return;
    const status = query.data?.status;
    if (status === "complete" || status === "failed") return;
    if (elapsedMs > HARD_TIMEOUT_MS) setTimedOut(true);
  }, [elapsedMs, query.data?.status, taskId, timedOut]);

  return { status: query.data ?? null, timedOut, elapsedMs };
}

// --- batches (multi-screen flows) ------------------------------------------
export function useBatches(page = 1, limit = 20) {
  return useQuery({
    queryKey: qk.batches(page),
    queryFn: async () =>
      (await api.get<BatchListResponse>("/batches", { params: { page, limit } })).data,
  });
}

/** Polls while screens are still analysing, then settles. */
export function useBatch(batchId: string) {
  return useQuery({
    queryKey: qk.batch(batchId),
    queryFn: async () => (await api.get<Batch>(`/batches/${batchId}`)).data,
    enabled: Boolean(batchId),
    refetchInterval: (q) => {
      const data = q.state.data as Batch | undefined;
      return data && data.status !== "processing" ? false : 2500;
    },
  });
}

export function useUploadBatch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      file,
      projectTitle,
      onProgress,
    }: {
      file: File;
      projectTitle?: string;
      onProgress?: (pct: number) => void;
    }) => {
      const form = new FormData();
      form.append("file", file);
      if (projectTitle) form.append("project_title", projectTitle);
      const { data } = await api.post<BatchUploadResponse>("/upload/batch", form, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (e) => {
          if (onProgress && e.total) onProgress(Math.round((e.loaded / e.total) * 100));
        },
      });
      return data;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["batches"] });
      void qc.invalidateQueries({ queryKey: ["results"] });
      void qc.invalidateQueries({ queryKey: qk.dashboard });
    },
  });
}

/** One provider call reviews every screen; see backend generate_flow_suggestions. */
export function useBatchSuggestions(batchId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { user_context?: string; regenerate?: boolean }) =>
      (await api.post<Batch>(`/batches/${batchId}/suggestions`, body)).data,
    onSuccess: (data) => qc.setQueryData(qk.batch(batchId), data),
  });
}

export function useDeleteBatch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (batchId: string) => (await api.delete(`/batches/${batchId}`)).data,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["batches"] });
      void qc.invalidateQueries({ queryKey: ["results"] });
      void qc.invalidateQueries({ queryKey: qk.dashboard });
    },
  });
}
