"use client";

import { animate, motion, useMotionValue, useTransform } from "framer-motion";
import {
  ArrowLeftRight,
  Columns2,
  Download,
  GitCompareArrows,
  Link2,
  Link2Off,
  Trophy,
} from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { HeatmapViewer, type ViewMode } from "@/components/app/heatmap-viewer";
import { Bezel } from "@/components/ui/bezel";
import { Button } from "@/components/ui/button";
import {
  Badge,
  Eyebrow,
  Reveal,
  Skeleton,
  Stagger,
  StaggerItem,
} from "@/components/ui/primitives";
import {
  useComparisons,
  useCreateComparison,
  useCurrentComparison,
  useResults,
} from "@/hooks/use-api";
import { api } from "@/lib/api";
import { clarityBand, cn, formatRelative } from "@/lib/utils";
import type { ComparisonSide } from "@/types/api";

interface Transform {
  zoom: number;
  panX: number;
  panY: number;
}

const IDENTITY: Transform = { zoom: 1, panX: 0, panY: 0 };

/** Counts to the delta rather than snapping, so the change reads as a change. */
function DeltaBadge({ delta }: { delta: number }) {
  const value = useMotionValue(0);
  const text = useTransform(value, (v) => `${v > 0 ? "+" : ""}${v.toFixed(1)}`);

  useEffect(() => {
    const controls = animate(value, delta, {
      duration: 1.2,
      ease: [0.32, 0.72, 0, 1],
    });
    return () => controls.stop();
  }, [delta, value]);

  const tone =
    delta > 0 ? "#10b981" : delta < 0 ? "#ef4444" : "var(--color-muted)";

  return (
    <div className="flex flex-col items-center rounded-2xl bg-[var(--color-surface)] px-6 py-4 shadow-[var(--shadow-lifted)] ring-1 ring-[var(--color-hairline)]">
      <motion.span
        className="tabular font-display text-3xl font-bold leading-none"
        style={{ color: tone }}
      >
        {text}
      </motion.span>
      <span className="mt-1.5 text-[10px] uppercase tracking-[0.16em] text-[var(--color-faint)]">
        Clarity points
      </span>
    </div>
  );
}

function SidePanel({
  side,
  label,
  winner,
  mode,
  opacity,
  transform,
  onTransform,
}: {
  side: ComparisonSide;
  label: string;
  winner: boolean;
  mode: ViewMode;
  opacity: number;
  transform: Transform | null;
  onTransform: (t: Transform) => void;
}) {
  const band = clarityBand(side.clarity_score);
  return (
    <Bezel className="min-w-0">
      <div className="p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h2 className="font-display text-[16px] font-semibold">{label}</h2>
              {winner ? (
                <Badge tone="success">
                  <Trophy size={11} strokeWidth={1.5} />
                  Winner
                </Badge>
              ) : null}
            </div>
            <p className="mt-0.5 truncate text-[12px] text-[var(--color-muted)]">
              {side.original_filename}
            </p>
          </div>
          <div className="text-right">
            <p className="tabular font-display text-2xl font-bold" style={{ color: band.hex }}>
              {side.clarity_score.toFixed(1)}
            </p>
            <p className="text-[10px] uppercase tracking-[0.14em] text-[var(--color-faint)]">
              {band.label}
            </p>
          </div>
        </div>

        <HeatmapViewer
          mockupUrl={side.mockup_url}
          heatmapUrl={side.heatmap_url}
          imageWidth={side.width}
          imageHeight={side.height}
          focusNodes={side.focus_nodes}
          mode={mode}
          opacity={opacity}
          className="mt-4 h-[22rem] sm:h-[26rem]"
          externalTransform={transform}
          onTransformChange={onTransform}
        />

        <dl className="mt-4 grid grid-cols-2 gap-3">
          <div className="rounded-xl bg-[var(--color-surface-2)] px-3 py-2.5 ring-1 ring-[var(--color-hairline)]">
            <dt className="text-[10px] uppercase tracking-[0.12em] text-[var(--color-faint)]">
              Focus index
            </dt>
            <dd className="tabular mt-0.5 text-[14px] font-semibold">
              {side.focus_index.toFixed(3)}
            </dd>
          </div>
          <div className="rounded-xl bg-[var(--color-surface-2)] px-3 py-2.5 ring-1 ring-[var(--color-hairline)]">
            <dt className="text-[10px] uppercase tracking-[0.12em] text-[var(--color-faint)]">
              Clutter index
            </dt>
            <dd className="tabular mt-0.5 text-[14px] font-semibold">
              {side.clutter_index.toFixed(3)}
            </dd>
          </div>
        </dl>
      </div>
    </Bezel>
  );
}

function CompareView() {
  const params = useSearchParams();
  const { data: results, isLoading } = useResults(1, 100);
  const { data: history } = useComparisons(1, 10);
  const create = useCreateComparison();

  const [a, setA] = useState(params.get("a") ?? "");
  const [b, setB] = useState(params.get("b") ?? "");
  const [mode, setMode] = useState<ViewMode>("both");
  const [opacity, setOpacity] = useState(0.75);
  const [synced, setSynced] = useState(true);
  const [shared, setShared] = useState<Transform>(IDENTITY);
  const [downloading, setDownloading] = useState(false);

  const analysed = (results?.results ?? []).filter(
    (r) => r.status === "complete" && r.clarity_score !== null,
  );

  // The result lives in the query cache, not in this component: React Query
  // drops mutate()'s callbacks when a component unmounts mid-flight, and Strict
  // Mode remounts in dev, so component-local state never received the result.
  const { data: comparison } = useCurrentComparison();
  // A remounted Strict Mode instance can leave an orphaned pending mutation, so
  // treat "busy" as pending with nothing yet on screen.
  const busy = create.isPending && !comparison;

  const run = (silent = false) => {
    if (!a || !b) return;
    setShared(IDENTITY);
    create.mutate(
      { asset_id_a: a, asset_id_b: b },
      {
        onSuccess: () => {
          if (!silent) toast.success("Comparison ready.");
        },
        onError: () => {
          if (!silent) toast.error("Could not compare these designs.");
        },
      },
    );
  };

  // ?a=<assetId>&b=<assetId> makes a comparison shareable as a link.
  const requested = useRef<string | null>(null);
  useEffect(() => {
    if (!a || !b) return;
    const key = `${a}|${b}`;
    if (requested.current === key) return;
    requested.current = key;
    // Skip if this exact pair is already the comparison on screen.
    if (comparison?.design_a.asset_id === a && comparison?.design_b.asset_id === b) return;
    if (!create.isPending) run(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [a, b]);

  const downloadReport = async () => {
    if (!comparison) return;
    setDownloading(true);
    try {
      const response = await api.get(
        `/compare/${comparison.comparison_id}/report.pdf`,
        { responseType: "blob" },
      );
      const url = URL.createObjectURL(response.data as Blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `designeye-comparison-${comparison.comparison_id.slice(0, 8)}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      toast.success("Comparison report downloaded.");
    } catch {
      toast.error("Could not generate the comparison PDF.");
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="mx-auto max-w-[82rem] space-y-8">
      <Reveal>
        <div className="text-center">
          <Eyebrow>
            <GitCompareArrows size={11} strokeWidth={1.5} />
            A/B saliency comparison
          </Eyebrow>
          <h1 className="mt-5 font-display text-[2.1rem] font-bold tracking-[-0.028em] sm:text-[2.5rem]">
            Compare two variants
          </h1>
          <p className="mx-auto mt-3 max-w-xl text-[14.5px] leading-relaxed text-[var(--color-muted)]">
            Put two analysed designs side by side and see which one earns the first
            fixation, scored on the same Clarity scale.
          </p>
        </div>
      </Reveal>

      {/* --- picker --- */}
      <Reveal>
        <Bezel>
          <div className="p-6">
            {isLoading ? (
              <Skeleton className="h-12" />
            ) : analysed.length < 2 ? (
              <div className="py-8 text-center">
                <p className="text-[14px] text-[var(--color-muted)]">
                  You need at least two completed analyses to compare.
                </p>
                <Button asChild className="mt-5">
                  <Link href="/upload">Upload another mockup</Link>
                </Button>
              </div>
            ) : (
              <div className="grid items-end gap-4 md:grid-cols-[1fr_auto_1fr_auto]">
                <div>
                  <label
                    htmlFor="design-a"
                    className="text-[12px] font-medium text-[var(--color-ink)]"
                  >
                    Design A
                  </label>
                  <select
                    id="design-a"
                    value={a}
                    onChange={(e) => setA(e.target.value)}
                    className="mt-2 h-12 w-full rounded-xl bg-[var(--color-surface-2)] px-3 text-[13.5px] ring-1 ring-[var(--color-hairline)] focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    <option value="">Select a design…</option>
                    {analysed
                      .filter((r) => r.asset_id !== b)
                      .map((r) => (
                        <option key={r.asset_id} value={r.asset_id}>
                          {r.original_filename} ({r.clarity_score?.toFixed(1)})
                        </option>
                      ))}
                  </select>
                </div>

                <button
                  type="button"
                  aria-label="Swap A and B"
                  onClick={() => {
                    setA(b);
                    setB(a);
                  }}
                  className="mb-1 hidden h-12 w-12 items-center justify-center rounded-xl text-[var(--color-muted)] ring-1 ring-[var(--color-hairline)] transition-colors hover:bg-[var(--color-shell)] md:flex"
                >
                  <ArrowLeftRight size={16} strokeWidth={1.5} />
                </button>

                <div>
                  <label
                    htmlFor="design-b"
                    className="text-[12px] font-medium text-[var(--color-ink)]"
                  >
                    Design B
                  </label>
                  <select
                    id="design-b"
                    value={b}
                    onChange={(e) => setB(e.target.value)}
                    className="mt-2 h-12 w-full rounded-xl bg-[var(--color-surface-2)] px-3 text-[13.5px] ring-1 ring-[var(--color-hairline)] focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    <option value="">Select a design…</option>
                    {analysed
                      .filter((r) => r.asset_id !== a)
                      .map((r) => (
                        <option key={r.asset_id} value={r.asset_id}>
                          {r.original_filename} ({r.clarity_score?.toFixed(1)})
                        </option>
                      ))}
                  </select>
                </div>

                <Button
                  size="lg"
                  disabled={!a || !b || busy}
                  onClick={() => run()}
                  className="h-12"
                >
                  {busy ? "Comparing…" : "Compare"}
                </Button>
              </div>
            )}
          </div>
        </Bezel>
      </Reveal>

      {/* --- result --- */}
      {comparison ? (
        <>
          <Reveal>
            <div className="flex flex-wrap items-center justify-center gap-4">
              <div className="flex rounded-full bg-[var(--color-shell)] p-1">
                {(["both", "heatmap", "focus", "original"] as ViewMode[]).map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setMode(m)}
                    className={cn(
                      "rounded-full px-3.5 py-1.5 text-[12.5px] font-medium capitalize",
                      "transition-all duration-400 ease-[cubic-bezier(0.32,0.72,0,1)]",
                      mode === m
                        ? "bg-[var(--color-surface)] text-[var(--color-ink)] shadow-[var(--shadow-ambient)]"
                        : "text-[var(--color-muted)] hover:text-[var(--color-ink)]",
                    )}
                  >
                    {m}
                  </button>
                ))}
              </div>

              <button
                type="button"
                onClick={() => {
                  setSynced((v) => !v);
                  setShared(IDENTITY);
                }}
                className={cn(
                  "flex items-center gap-2 rounded-full px-4 py-2 text-[12.5px] font-medium",
                  "ring-1 transition-all duration-400",
                  synced
                    ? "bg-indigo-50 text-indigo-700 ring-indigo-200 dark:bg-indigo-500/10 dark:text-indigo-300 dark:ring-indigo-400/20"
                    : "text-[var(--color-muted)] ring-[var(--color-hairline-strong)]",
                )}
              >
                {synced ? (
                  <Link2 size={14} strokeWidth={1.5} />
                ) : (
                  <Link2Off size={14} strokeWidth={1.5} />
                )}
                {synced ? "Zoom synced" : "Independent zoom"}
              </button>

              <div className="flex items-center gap-3">
                <Columns2 size={14} strokeWidth={1.5} className="text-[var(--color-faint)]" />
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={opacity}
                  disabled={mode === "original" || mode === "focus"}
                  onChange={(e) => setOpacity(Number(e.target.value))}
                  aria-label="Overlay opacity"
                  className="h-1.5 w-28 cursor-pointer appearance-none rounded-full bg-[var(--color-shell)] accent-indigo-600 disabled:opacity-40"
                />
                <span className="tabular w-9 text-[12px] text-[var(--color-muted)]">
                  {Math.round(opacity * 100)}%
                </span>
              </div>

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
          </Reveal>

          <div className="relative grid gap-6 lg:grid-cols-2">
            <SidePanel
              side={comparison.design_a}
              label="Design A"
              winner={comparison.winner === "A"}
              mode={mode}
              opacity={opacity}
              transform={synced ? shared : null}
              onTransform={(t) => synced && setShared(t)}
            />
            <SidePanel
              side={comparison.design_b}
              label="Design B"
              winner={comparison.winner === "B"}
              mode={mode}
              opacity={opacity}
              transform={synced ? shared : null}
              onTransform={(t) => synced && setShared(t)}
            />

            <div className="pointer-events-none absolute left-1/2 top-1/2 z-10 hidden -translate-x-1/2 -translate-y-1/2 lg:block">
              <DeltaBadge delta={comparison.clarity_delta} />
            </div>
          </div>

          <div className="lg:hidden">
            <div className="flex justify-center">
              <DeltaBadge delta={comparison.clarity_delta} />
            </div>
          </div>

          <Reveal>
            <Bezel>
              <div className="p-7">
                <h2 className="font-display text-lg font-semibold">What the numbers say</h2>
                <p className="mt-2.5 text-[14px] leading-relaxed text-[var(--color-muted)]">
                  {comparison.winner === "tie" ? (
                    "Both variants score identically on the Clarity scale. Consider the focus order below to break the tie."
                  ) : (
                    <>
                      <span className="font-semibold text-[var(--color-ink)]">
                        Design {comparison.winner}
                      </span>{" "}
                      scores {Math.abs(comparison.clarity_delta).toFixed(1)} clarity
                      points higher. That gap comes from how tightly predicted
                      attention concentrates and how much edge clutter competes with it.
                    </>
                  )}
                </p>
              </div>
            </Bezel>
          </Reveal>
        </>
      ) : null}

      {/* --- history --- */}
      {(history?.comparisons.length ?? 0) > 0 ? (
        <div>
          <Reveal>
            <h2 className="font-display text-lg font-semibold">Recent comparisons</h2>
          </Reveal>
          <Stagger className="mt-4 space-y-2.5">
            {history?.comparisons.map((c) => (
              <StaggerItem key={c.comparison_id}>
                <Bezel>
                  <div className="flex flex-wrap items-center justify-between gap-3 p-4">
                    <p className="font-mono text-[12px] text-[var(--color-muted)]">
                      {c.comparison_id.slice(0, 8)} · {formatRelative(c.created_at)}
                    </p>
                    <Badge
                      tone={
                        c.clarity_delta > 0
                          ? "success"
                          : c.clarity_delta < 0
                            ? "danger"
                            : "neutral"
                      }
                    >
                      {c.clarity_delta > 0 ? "+" : ""}
                      {c.clarity_delta.toFixed(1)} pts
                    </Badge>
                  </div>
                </Bezel>
              </StaggerItem>
            ))}
          </Stagger>
        </div>
      ) : null}
    </div>
  );
}

export default function ComparePage() {
  return (
    <Suspense fallback={<div className="h-96" />}>
      <CompareView />
    </Suspense>
  );
}
