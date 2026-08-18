"use client";

import {
  AlertCircle,
  ArrowLeft,
  Download,
  Info,
  Layers,
  RefreshCw,
  Sparkles,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { ClarityGauge } from "@/components/app/clarity-gauge";
import { HeatmapViewer, type ViewMode } from "@/components/app/heatmap-viewer";
import { ScanpathPlayer } from "@/components/app/scanpath-player";
import { SuggestionsPanel } from "@/components/app/suggestions-panel";
import { Bezel } from "@/components/ui/bezel";
import { Button } from "@/components/ui/button";
import { Badge, Eyebrow, Reveal, Skeleton } from "@/components/ui/primitives";
import { useDeleteResult, useResult, useRerun } from "@/hooks/use-api";
import { API_URL, api } from "@/lib/api";
import { clarityBand, cn, formatRelative } from "@/lib/utils";

/** "scanpath" is a sibling view, not a HeatmapViewer mode -- it owns its canvas. */
type PanelMode = ViewMode | "scanpath";

const MODES: { key: PanelMode; label: string }[] = [
  { key: "both", label: "Both" },
  { key: "heatmap", label: "Heatmap" },
  { key: "focus", label: "Focus order" },
  { key: "scanpath", label: "Watch the replay" },
  { key: "original", label: "Original" },
];

const REGION_LABELS: Record<string, string> = {
  top_left: "Top left", top_center: "Top centre", top_right: "Top right",
  mid_left: "Mid left", mid_center: "Mid centre", mid_right: "Mid right",
  bot_left: "Bottom left", bot_center: "Bottom centre", bot_right: "Bottom right",
};

export default function ResultPage() {
  const params = useParams<{ assetId: string }>();
  const assetId = params.assetId;
  const router = useRouter();

  const { data: result, isLoading, isError, refetch } = useResult(assetId);
  const rerun = useRerun();
  const remove = useDeleteResult();

  const [mode, setMode] = useState<PanelMode>("both");
  const [opacity, setOpacity] = useState(0.75);
  const [downloading, setDownloading] = useState(false);

  const downloadReport = async () => {
    setDownloading(true);
    try {
      const response = await api.get(`/results/${assetId}/report.pdf`, {
        responseType: "blob",
      });
      const url = URL.createObjectURL(response.data as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `designeye-${result?.original_filename ?? assetId}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success("Report downloaded.");
    } catch {
      toast.error("Could not generate the PDF report.");
    } finally {
      setDownloading(false);
    }
  };

  if (isLoading) {
    return (
      <div className="mx-auto max-w-[80rem] space-y-6">
        <Skeleton className="h-10 w-72" />
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_23rem]">
          <Skeleton className="h-[34rem] rounded-[2rem]" />
          <div className="space-y-5">
            <Skeleton className="h-72 rounded-[2rem]" />
            <Skeleton className="h-56 rounded-[2rem]" />
          </div>
        </div>
      </div>
    );
  }

  if (isError || !result) {
    return (
      <div className="mx-auto max-w-[46rem]">
        <Bezel>
          <div className="flex flex-col items-center px-8 py-16 text-center">
            <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-amber-50 text-amber-600 dark:bg-amber-500/10">
              <AlertCircle size={22} strokeWidth={1.5} />
            </span>
            <h2 className="mt-5 font-display text-xl font-semibold">
              This analysis isn&apos;t ready
            </h2>
            <p className="mt-2 max-w-md text-[14px] text-[var(--color-muted)]">
              The result may still be processing, or it may have been removed.
            </p>
            <div className="mt-7 flex gap-3">
              <Button variant="outline" onClick={() => refetch()}>
                <RefreshCw size={15} strokeWidth={1.5} />
                Retry
              </Button>
              <Button asChild>
                <Link href="/projects">Back to projects</Link>
              </Button>
            </div>
          </div>
        </Bezel>
      </div>
    );
  }

  const band = clarityBand(result.clarity_score);
  // A page taller than one screen was scored a screenful at a time, so the
  // headline number is an average and needs to say so.
  const isScrolling = result.viewport_count > 1 && result.viewports.length > 0;
  const regions = Object.entries(result.region_saliency);
  const maxRegion = Math.max(...regions.map(([, v]) => v), 0.0001);
  const totalIntensity =
    result.focus_nodes.reduce((sum, n) => sum + n.intensity, 0) || 1;

  return (
    <div className="mx-auto max-w-[80rem] space-y-7">
      <Reveal>
        <div className="flex flex-wrap items-start justify-between gap-5">
          <div className="min-w-0">
            <Link
              href="/projects"
              className="inline-flex items-center gap-1.5 text-[12px] font-medium text-[var(--color-muted)] transition-colors hover:text-indigo-600"
            >
              <ArrowLeft size={13} strokeWidth={1.5} />
              All projects
            </Link>
            <h1 className="mt-3 truncate font-display text-[1.9rem] font-bold tracking-[-0.025em]">
              {result.original_filename}
            </h1>
            <p className="tabular mt-1.5 text-[13px] text-[var(--color-muted)]">
              {result.image_width} × {result.image_height} px · analysed{" "}
              {formatRelative(result.created_at)} · {result.inference_time_ms} ms
            </p>
          </div>

          <div className="flex flex-wrap gap-2.5">
            <Button
              variant="outline"
              size="sm"
              disabled={rerun.isPending}
              onClick={() =>
                rerun.mutate(assetId, {
                  onSuccess: (d) => {
                    toast.success("Re-analysis queued.");
                    router.push(`/upload?task=${d.new_task_id}&asset=${assetId}`);
                  },
                  onError: () => toast.error("Could not start the re-analysis."),
                })
              }
            >
              <RefreshCw
                size={14}
                strokeWidth={1.5}
                className={cn(rerun.isPending && "animate-spin")}
              />
              Rerun
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                if (!window.confirm("Delete this analysis? This cannot be undone.")) return;
                remove.mutate(assetId, {
                  onSuccess: () => {
                    toast.success("Analysis deleted.");
                    router.push("/projects");
                  },
                  onError: () => toast.error("Could not delete this analysis."),
                });
              }}
            >
              <Trash2 size={14} strokeWidth={1.5} />
              Delete
            </Button>
            <Button
              size="sm"
              variant="navy"
              disabled={downloading}
              onClick={downloadReport}
              trailingIcon={<Download size={13} strokeWidth={1.5} />}
            >
              {downloading ? "Preparing…" : "Export PDF"}
            </Button>
          </div>
        </div>
      </Reveal>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_23rem]">
        {/* ---------------- canvas ---------------- */}
        <Reveal className="min-w-0">
          <Bezel>
            <div className="p-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex rounded-full bg-[var(--color-shell)] p-1">
                  {MODES.map((m) => (
                    <button
                      key={m.key}
                      type="button"
                      onClick={() => setMode(m.key)}
                      className={cn(
                        "rounded-full px-3.5 py-1.5 text-[12.5px] font-medium",
                        "transition-all duration-400 ease-[cubic-bezier(0.32,0.72,0,1)]",
                        mode === m.key
                          ? "bg-[var(--color-surface)] text-[var(--color-ink)] shadow-[var(--shadow-ambient)]"
                          : "text-[var(--color-muted)] hover:text-[var(--color-ink)]",
                      )}
                    >
                      {m.label}
                    </button>
                  ))}
                </div>

                <div
                  className={cn(
                    "flex items-center gap-2.5",
                    mode === "scanpath" && "hidden",
                  )}
                >
                  <span className="text-[10px] uppercase tracking-[0.14em] text-[var(--color-faint)]">
                    Low
                  </span>
                  <span
                    className="h-2 w-24 rounded-full"
                    style={{
                      background:
                        "linear-gradient(90deg,#000083,#0000ff,#00ffff,#7cff79,#ffff00,#ff7f00,#ff0000,#800000)",
                    }}
                  />
                  <span className="text-[10px] uppercase tracking-[0.14em] text-[var(--color-faint)]">
                    High
                  </span>
                </div>
              </div>

              {mode === "scanpath" ? (
                <ScanpathPlayer
                  className="mt-5"
                  assetId={assetId}
                  mockupUrl={result.mockup_url}
                  imageWidth={result.image_width}
                  imageHeight={result.image_height}
                  steps={result.scanpath}
                  totalMs={result.scanpath_total_ms}
                  filename={result.original_filename}
                />
              ) : (
                <HeatmapViewer
                  mockupUrl={result.mockup_url}
                  heatmapUrl={result.heatmap_url}
                  imageWidth={result.image_width}
                  imageHeight={result.image_height}
                  focusNodes={result.focus_nodes}
                  mode={mode}
                  opacity={opacity}
                  className="mt-5 h-[30rem] sm:h-[34rem]"
                />
              )}

              <div
                className={cn(
                  "mt-5 flex items-center gap-4",
                  mode === "scanpath" && "hidden",
                )}
              >
                <label
                  htmlFor="opacity"
                  className="flex items-center gap-2 text-[12px] font-medium text-[var(--color-muted)]"
                >
                  <Layers size={14} strokeWidth={1.5} />
                  Overlay
                </label>
                <input
                  id="opacity"
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={opacity}
                  disabled={mode === "original" || mode === "focus"}
                  onChange={(e) => setOpacity(Number(e.target.value))}
                  className="h-1.5 flex-1 cursor-pointer appearance-none rounded-full bg-[var(--color-shell)] accent-indigo-600 disabled:opacity-40"
                />
                <span className="tabular w-10 text-right text-[12px] text-[var(--color-muted)]">
                  {Math.round(opacity * 100)}%
                </span>
              </div>
              {mode !== "scanpath" ? (
                <p className="mt-2 text-[11px] text-[var(--color-faint)]">
                  Ctrl/⌘ + scroll to zoom, drag to pan when zoomed in.
                </p>
              ) : null}
            </div>
          </Bezel>
        </Reveal>

        {/* ---------------- metrics rail ---------------- */}
        <div className="space-y-6">
          <Reveal delay={0.05}>
            <Bezel>
              <div className="p-7">
                <div className="flex items-center justify-between">
                  <Eyebrow>Analysis results</Eyebrow>
                  <Badge tone={band.tone}>{band.label}</Badge>
                </div>

                <div className="mt-6 flex justify-center">
                  <ClarityGauge score={result.clarity_score} />
                </div>

                <p className="mt-5 text-center text-[13px] font-semibold">
                  {isScrolling ? "Average across the page" : "Overall Clarity Score"}
                </p>
                <p className="mt-2 text-center text-[13px] leading-relaxed text-[var(--color-muted)]">
                  {isScrolling
                    ? `This design is longer than one screen, so each screenful was scored on its own and averaged. Screen ${result.weakest_viewport} needs attention first.`
                    : result.clarity_score >= 75
                      ? "Attention concentrates cleanly. The layout creates a clear entry point."
                      : result.clarity_score >= 40
                        ? "Attention is workable but spread. Some elements compete for the first fixation."
                        : "Attention is scattered across a visually dense layout. Consider consolidating."}
                </p>

                {!result.score_in_range ? (
                  <div className="mt-5 rounded-xl bg-amber-50 p-3.5 ring-1 ring-amber-200 dark:bg-amber-500/10 dark:ring-amber-400/20">
                    <p className="text-[12.5px] leading-relaxed text-amber-900 dark:text-amber-200">
                      This image is an unusual shape, so there is not enough detail
                      left to score it reliably. Treat the number with caution and
                      upload the design one screen at a time.
                    </p>
                  </div>
                ) : null}

                <dl className="mt-7 space-y-3 border-t border-[var(--color-hairline)] pt-5">
                  {[
                    { k: "Focus index", v: result.focus_index.toFixed(3), hint: "concentration" },
                    { k: "Clutter index", v: result.clutter_index.toFixed(3), hint: "edge density" },
                    { k: "Model", v: result.model_version, hint: "" },
                  ].map((row) => (
                    <div key={row.k} className="flex items-baseline justify-between gap-3">
                      <dt className="text-[12.5px] text-[var(--color-muted)]">
                        {row.k}
                        {row.hint ? (
                          <span className="ml-1.5 text-[10px] uppercase tracking-[0.1em] text-[var(--color-faint)]">
                            {row.hint}
                          </span>
                        ) : null}
                      </dt>
                      <dd className="tabular truncate text-[12.5px] font-semibold">{row.v}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            </Bezel>
          </Reveal>

          {isScrolling ? (
            <Reveal delay={0.08}>
              <Bezel>
                <div className="p-7">
                  <h2 className="font-display text-[15px] font-semibold">
                    Screen by screen
                  </h2>
                  <p className="mt-1.5 text-[12px] leading-relaxed text-[var(--color-muted)]">
                    Nobody sees a long page all at once, so we score one screenful
                    at a time as you scroll down.
                  </p>

                  <ol className="mt-5 space-y-2">
                    {result.viewports.map((vp) => {
                      const vband = clarityBand(vp.clarity_score);
                      const weakest = vp.index === result.weakest_viewport;
                      return (
                        <li
                          key={vp.index}
                          className={cn(
                            "flex items-center gap-3 rounded-xl px-3 py-2.5 ring-1",
                            weakest
                              ? "bg-red-50 ring-red-200 dark:bg-red-500/10 dark:ring-red-400/20"
                              : "bg-[var(--color-surface-2)] ring-[var(--color-hairline)]",
                          )}
                        >
                          <span className="tabular w-5 shrink-0 text-[12px] font-semibold text-[var(--color-muted)]">
                            {vp.index}
                          </span>
                          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[var(--color-shell)]">
                            <div
                              className="h-full rounded-full"
                              style={{
                                width: `${Math.max(2, vp.clarity_score)}%`,
                                backgroundColor: vband.hex,
                              }}
                            />
                          </div>
                          <span
                            className="tabular w-11 shrink-0 text-right text-[12.5px] font-semibold"
                            style={{ color: vband.hex }}
                          >
                            {vp.clarity_score.toFixed(1)}
                          </span>
                        </li>
                      );
                    })}
                  </ol>

                  <p className="mt-4 text-[11.5px] leading-relaxed text-[var(--color-faint)]">
                    Screen height assumed from a {result.viewport_device}. Screens
                    overlap slightly so nothing that straddles a fold gets missed.
                  </p>
                </div>
              </Bezel>
            </Reveal>
          ) : null}

          <Reveal delay={0.1}>
            <Bezel>
              <div className="p-7">
                <h2 className="flex items-center gap-2 font-display text-[15px] font-semibold">
                  <Sparkles size={16} strokeWidth={1.5} className="text-indigo-600" />
                  Predictive focus order
                </h2>
                <p className="mt-1.5 text-[12px] text-[var(--color-muted)]">
                  Where the eye is predicted to land, in sequence.
                </p>

                <ol className="mt-5 space-y-2.5">
                  {result.focus_nodes.map((node) => (
                    <li
                      key={node.rank}
                      className="flex items-center gap-3 rounded-xl bg-[var(--color-surface-2)] px-3 py-2.5 ring-1 ring-[var(--color-hairline)]"
                    >
                      <span
                        className={cn(
                          "flex h-7 w-7 shrink-0 items-center justify-center rounded-full",
                          "font-mono text-[11px] font-bold text-white",
                          node.rank === 1 ? "bg-violet-600" : "bg-indigo-600",
                        )}
                      >
                        {node.rank}
                      </span>
                      <span className="tabular min-w-0 flex-1 text-[12px] text-[var(--color-muted)]">
                        x {node.x} · y {node.y}
                      </span>
                      <span className="tabular text-[12.5px] font-bold text-[var(--color-ink)]">
                        {((node.intensity / totalIntensity) * 100).toFixed(0)}%
                      </span>
                    </li>
                  ))}
                </ol>
              </div>
            </Bezel>
          </Reveal>

          <Reveal delay={0.15}>
            <Bezel>
              <div className="p-7">
                <h2 className="flex items-center gap-2 font-display text-[15px] font-semibold">
                  <Info size={16} strokeWidth={1.5} className="text-indigo-600" />
                  Regional attention
                </h2>
                <div className="mt-5 grid grid-cols-3 gap-1.5">
                  {regions.map(([key, value]) => (
                    <div
                      key={key}
                      title={`${REGION_LABELS[key] ?? key}: ${(value * 100).toFixed(1)}%`}
                      className="flex aspect-square flex-col items-center justify-center rounded-lg ring-1 ring-[var(--color-hairline)]"
                      style={{
                        backgroundColor: `rgba(79,91,213,${(value / maxRegion) * 0.85 + 0.04})`,
                      }}
                    >
                      <span
                        className={cn(
                          "tabular text-[12px] font-bold",
                          value / maxRegion > 0.55 ? "text-white" : "text-[var(--color-ink)]",
                        )}
                      >
                        {(value * 100).toFixed(0)}
                      </span>
                    </div>
                  ))}
                </div>
                <p className="mt-3 text-[11px] text-[var(--color-faint)]">
                  Mean predicted attention per cell, ×100.
                </p>
              </div>
            </Bezel>
          </Reveal>
        </div>
      </div>

      <Reveal>
        <SuggestionsPanel assetId={assetId} />
      </Reveal>

      <p className="pb-4 text-center text-[11px] text-[var(--color-faint)]">
        Predictions estimate where viewers are likely to look. They are not a
        substitute for testing with real users. · API {API_URL}
      </p>
    </div>
  );
}
