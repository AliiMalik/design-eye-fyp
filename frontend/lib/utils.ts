import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Clarity band used consistently across gauge, badges, and tables. */
export function clarityBand(score: number): {
  label: string;
  tone: "success" | "warning" | "danger";
  hex: string;
} {
  if (score >= 75) return { label: "Strong", tone: "success", hex: "#10b981" };
  if (score >= 40) return { label: "Moderate", tone: "warning", hex: "#f59e0b" };
  return { label: "Needs work", tone: "danger", hex: "#ef4444" };
}

export function formatRelative(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const diff = Date.now() - then;
  const mins = Math.round(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function formatBytes(kb: number): string {
  if (kb < 1024) return `${kb} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}

/** Human label for each pipeline stage reported by GET /status/{task_id}. */
export const STAGE_LABELS: Record<string, string> = {
  queued: "Uploading",
  preprocessing: "Preprocessing",
  running_inference: "Running inference",
  computing_analytics: "Computing analytics",
  persisting: "Generating suggestions",
  complete: "Complete",
  failed: "Failed",
};

export const STAGE_ORDER = [
  "queued",
  "preprocessing",
  "running_inference",
  "computing_analytics",
  "persisting",
  "complete",
];
