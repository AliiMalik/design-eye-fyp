"use client";

import {
  AlertCircle,
  ArrowLeft,
  Download,
  Loader2,
  Sparkles,
  Trash2,
  TrendingDown,
  Trophy,
  WandSparkles,
} from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { Area, AreaChart, ReferenceDot, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { toast } from "sonner";

import { ClarityPill } from "@/components/app/clarity-gauge";
import { Bezel, BezelSm } from "@/components/ui/bezel";
import { Button } from "@/components/ui/button";
import {
  Badge,
  Eyebrow,
  Reveal,
  Skeleton,
  Stagger,
  StaggerItem,
  Textarea,
} from "@/components/ui/primitives";
import { useBatch, useBatchSuggestions, useDeleteBatch } from "@/hooks/use-api";
import { api } from "@/lib/api";
import { clarityBand, cn, formatRelative } from "@/lib/utils";

const SEVERITY_TONE = { high: "danger", medium: "warning", low: "neutral" } as const;

export default function BatchPage() {
  const params = useParams<{ id: string }>();
  const batchId = params.id;
  const router = useRouter();

  const { data: batch, isLoading, isError } = useBatch(batchId);
  const review = useBatchSuggestions(batchId);
  const remove = useDeleteBatch();

  const [context, setContext] = useState("");
  const [showContext, setShowContext] = useState(false);
  const [downloading, setDownloading] = useState(false);

  const downloadReport = async () => {
    setDownloading(true);
    try {
      const response = await api.get(`/batches/${batchId}/report.pdf`, {
        responseType: "blob",
      });
      const url = URL.createObjectURL(response.data as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `designeye-flow-${batch?.source_filename ?? batchId}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success("Flow report downloaded.");
    } catch {
      toast.error("Could not generate the flow report.");
    } finally {
      setDownloading(false);
    }
  };

  if (isLoading) {
    return (
      <div className="mx-auto max-w-[76rem] space-y-6">
        <Skeleton className="h-11 w-80" />
        <Skeleton className="h-40 rounded-[2rem]" />
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-72 rounded-[2rem]" />
          ))}
        </div>
      </div>
    );
  }

  if (isError || !batch) {
    return (
      <div className="mx-auto max-w-[44rem]">
        <Bezel>
          <div className="px-8 py-16 text-center">
            <h2 className="font-display text-xl font-semibold">Flow unavailable</h2>
            <p className="mt-2 text-[14px] text-[var(--color-muted)]">
              It may have been deleted, or it belongs to another account.
            </p>
            <Button asChild className="mt-6">
              <Link href="/projects">Back to projects</Link>
            </Button>
          </div>
        </Bezel>
      </div>
    );
  }

  const processing = batch.status === "processing";
  const done = batch.screens_complete + batch.screens_failed;
  const progress = batch.page_count ? (done / batch.page_count) * 100 : 0;
  const reviewed = batch.flow_summary.length > 0;

  const trend = batch.screens
    .filter((s) => s.clarity_score !== null)
    .map((s) => ({ screen: s.page_number, clarity: s.clarity_score as number }));

  const weakest = trend.find((p) => p.screen === batch.weakest_screen);

  return (
    <div className="mx-auto max-w-[76rem] space-y-8">
      <Reveal>
        <Link
          href="/projects"
          className="inline-flex items-center gap-1.5 text-[12px] font-medium text-[var(--color-muted)] transition-colors hover:text-indigo-600"
        >
          <ArrowLeft size={13} strokeWidth={1.5} />
          All projects
        </Link>

        <div className="mt-4 flex flex-wrap items-start justify-between gap-5">
          <div className="min-w-0">
            <Eyebrow>Multi-screen flow</Eyebrow>
            <h1 className="mt-4 truncate font-display text-[2rem] font-bold tracking-[-0.028em]">
              {batch.source_filename}
            </h1>
            <p className="tabular mt-2 text-[13px] text-[var(--color-muted)]">
              {batch.page_count} screens · uploaded {formatRelative(batch.created_at)}
            </p>
            {/* The whole point of this module was to stop dropping screens
                quietly, so say plainly when the cap bites. */}
            {batch.pages_skipped > 0 ? (
              <p className="mt-1.5 text-[12.5px] text-amber-700 dark:text-amber-400">
                The last {batch.pages_skipped}{" "}
                {batch.pages_skipped === 1 ? "screen was" : "screens were"} left out —
                we analyse the first {batch.page_count} in one go.
              </p>
            ) : null}
          </div>

          <div className="flex flex-wrap gap-2.5">
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                if (!window.confirm(`Delete this flow and all ${batch.page_count} screens?`))
                  return;
                remove.mutate(batchId, {
                  onSuccess: () => {
                    toast.success("Flow deleted.");
                    router.push("/projects");
                  },
                  onError: () => toast.error("Could not delete the flow."),
                });
              }}
            >
              <Trash2 size={14} strokeWidth={1.5} />
              Delete
            </Button>
            <Button
              size="sm"
              variant="navy"
              disabled={downloading || processing}
              onClick={downloadReport}
              trailingIcon={<Download size={13} strokeWidth={1.5} />}
            >
              {downloading ? "Preparing…" : "Export flow PDF"}
            </Button>
          </div>
        </div>
      </Reveal>

      {/* progress while screens are still analysing */}
      {processing ? (
        <Reveal>
          <Bezel>
            <div className="p-6">
              <div className="flex items-center gap-3">
                <Loader2 size={16} strokeWidth={1.5} className="animate-spin text-indigo-600" />
                <p className="text-[14px] font-medium">
                  Analysing screen {Math.min(done + 1, batch.page_count)} of{" "}
                  {batch.page_count}
                </p>
                <span className="tabular ml-auto text-[13px] text-[var(--color-muted)]">
                  {done}/{batch.page_count}
                </span>
              </div>
              <div className="mt-4 h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-shell)]">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-indigo-600 to-violet-600 transition-[width] duration-700 ease-[cubic-bezier(0.32,0.72,0,1)]"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          </Bezel>
        </Reveal>
      ) : null}

      {/* flow-level stats */}
      <Stagger className="grid gap-5 sm:grid-cols-3">
        <StaggerItem>
          <Bezel className="h-full">
            <div className="p-6">
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--color-faint)]">
                Average clarity
              </p>
              <p className="tabular mt-1.5 font-display text-4xl font-bold">
                {batch.avg_clarity_score?.toFixed(1) ?? "—"}
              </p>
              <p className="mt-1 text-[12px] text-[var(--color-muted)]">
                across {batch.screens_complete} analysed screens
              </p>
            </div>
          </Bezel>
        </StaggerItem>
        <StaggerItem>
          <Bezel className="h-full">
            <div className="p-6">
              <div className="flex items-center justify-between">
                <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--color-faint)]">
                  Weakest screen
                </p>
                <TrendingDown size={16} strokeWidth={1.5} className="text-red-500" />
              </div>
              <p className="tabular mt-1.5 font-display text-4xl font-bold">
                {batch.weakest_screen ?? "—"}
              </p>
              <p className="mt-1 text-[12px] text-[var(--color-muted)]">
                needs attention first
              </p>
            </div>
          </Bezel>
        </StaggerItem>
        <StaggerItem>
          <Bezel className="h-full">
            <div className="p-6">
              <div className="flex items-center justify-between">
                <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--color-faint)]">
                  Strongest screen
                </p>
                <Trophy size={16} strokeWidth={1.5} className="text-emerald-500" />
              </div>
              <p className="tabular mt-1.5 font-display text-4xl font-bold">
                {batch.strongest_screen ?? "—"}
              </p>
              <p className="mt-1 text-[12px] text-[var(--color-muted)]">
                use as the reference
              </p>
            </div>
          </Bezel>
        </StaggerItem>
      </Stagger>

      {/* clarity across the flow */}
      {trend.length > 1 ? (
        <Reveal>
          <Bezel>
            <div className="p-7">
              <h2 className="font-display text-lg font-semibold">Clarity across the flow</h2>
              <p className="mt-1 text-[13px] text-[var(--color-muted)]">
                Where attention holds up, and where it falls away.
              </p>
              <div className="mt-6 h-56 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={trend} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                    <defs>
                      <linearGradient id="flowFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#4f5bd5" stopOpacity={0.3} />
                        <stop offset="100%" stopColor="#4f5bd5" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <XAxis
                      dataKey="screen"
                      tick={{ fontSize: 11, fill: "var(--color-faint)" }}
                      tickLine={false}
                      axisLine={false}
                      label={{ value: "screen", position: "insideBottomRight",
                               fontSize: 10, fill: "var(--color-faint)" }}
                    />
                    <YAxis
                      domain={[0, 100]}
                      tick={{ fontSize: 11, fill: "var(--color-faint)" }}
                      tickLine={false}
                      axisLine={false}
                      width={40}
                    />
                    <Tooltip
                      contentStyle={{
                        borderRadius: 14,
                        border: "1px solid var(--color-hairline)",
                        background: "var(--color-surface)",
                        fontSize: 12,
                      }}
                      formatter={(v: number) => [`${v.toFixed(1)} / 100`, "Clarity"]}
                      labelFormatter={(l) => `Screen ${l}`}
                    />
                    <Area
                      type="monotone"
                      dataKey="clarity"
                      stroke="#4f5bd5"
                      strokeWidth={2.5}
                      fill="url(#flowFill)"
                      animationDuration={900}
                    />
                    {weakest ? (
                      <ReferenceDot
                        x={weakest.screen}
                        y={weakest.clarity}
                        r={6}
                        fill="#ef4444"
                        stroke="#fff"
                        strokeWidth={2}
                      />
                    ) : null}
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
          </Bezel>
        </Reveal>
      ) : null}

      {/* the one batched review */}
      <Reveal>
        <Bezel>
          <div className="p-7 sm:p-8">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <h2 className="flex items-center gap-2 font-display text-lg font-semibold">
                  <WandSparkles size={18} strokeWidth={1.5} className="text-violet-600" />
                  Review the whole flow
                </h2>
                <p className="mt-1.5 max-w-2xl text-[13px] leading-relaxed text-[var(--color-muted)]">
                  All {batch.page_count} screens are reviewed together in a{" "}
                  <span className="font-medium text-[var(--color-ink)]">single request</span>,
                  so it costs one use of your daily limit instead of {batch.page_count} —
                  and because the reviewer sees every screen at once, it can tell you
                  where the flow gets worse, not just what each screen looks like.
                </p>
              </div>
              <div className="flex items-center gap-2.5">
                {batch.llm_provider ? (
                  <Badge tone="violet">
                    {batch.llm_provider}
                    {batch.llm_model ? ` · ${batch.llm_model}` : ""}
                  </Badge>
                ) : null}
                <Button
                  size="sm"
                  variant={reviewed ? "outline" : "primary"}
                  disabled={review.isPending || processing}
                  onClick={() =>
                    review.mutate(
                      { user_context: context.trim() || undefined, regenerate: reviewed },
                      {
                        onSuccess: (res) => {
                          if (res.llm_status === "ok") toast.success("Flow reviewed.");
                          else if (res.llm_status === "rate_limited")
                            toast.error("Daily limit reached. Try again tomorrow.");
                          else toast.error("The reviewer is unavailable right now.");
                        },
                        onError: () => toast.error("Could not review the flow."),
                      },
                    )
                  }
                >
                  {review.isPending ? (
                    <>
                      <Loader2 size={14} strokeWidth={1.5} className="animate-spin" />
                      Reviewing…
                    </>
                  ) : reviewed ? (
                    "Review again"
                  ) : (
                    <>
                      <Sparkles size={14} strokeWidth={1.5} />
                      Review all {batch.page_count} screens
                    </>
                  )}
                </Button>
              </div>
            </div>

            <button
              type="button"
              onClick={() => setShowContext((v) => !v)}
              className="mt-4 text-[12px] font-medium text-indigo-600 hover:underline"
            >
              {showContext ? "Hide context" : "Add context about this flow (optional)"}
            </button>
            {showContext ? (
              <Textarea
                value={context}
                onChange={(e) => setContext(e.target.value)}
                rows={2}
                maxLength={1000}
                placeholder="e.g. This is a checkout flow; the goal is completing payment."
                className="mt-3"
              />
            ) : null}

            {review.isPending ? (
              <div className="mt-6 space-y-3">
                <Skeleton className="h-20 rounded-2xl" />
                <Skeleton className="h-14 rounded-2xl" />
              </div>
            ) : batch.flow_summary ? (
              <p className="mt-6 rounded-2xl bg-[var(--color-surface-2)] p-5 text-[13.5px] leading-relaxed text-[var(--color-ink-2)] ring-1 ring-[var(--color-hairline)]">
                {batch.flow_summary}
              </p>
            ) : (
              <p className="mt-6 rounded-2xl bg-[var(--color-surface-2)] p-5 text-[13px] text-[var(--color-muted)] ring-1 ring-[var(--color-hairline)]">
                {processing
                  ? "Waiting for every screen to finish analysing first."
                  : "Not reviewed yet. One request covers the whole flow."}
              </p>
            )}
          </div>
        </Bezel>
      </Reveal>

      {/* screens */}
      <div>
        <Reveal>
          <h2 className="font-display text-xl font-semibold">
            Screens ({batch.page_count})
          </h2>
        </Reveal>

        <Stagger className="mt-5 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {batch.screens.map((screen) => {
            const band =
              screen.clarity_score !== null ? clarityBand(screen.clarity_score) : null;
            const isWeakest = screen.page_number === batch.weakest_screen;
            const isStrongest = screen.page_number === batch.strongest_screen;

            return (
              <StaggerItem key={screen.asset_id}>
                <BezelSm
                  className={cn(
                    "h-full",
                    isWeakest && "ring-2 ring-red-400/60",
                    isStrongest && "ring-2 ring-emerald-400/60",
                  )}
                >
                  <article className="flex h-full flex-col overflow-hidden rounded-[1rem]">
                    <div className="relative aspect-[16/10] w-full overflow-hidden bg-[var(--color-shell)]">
                      {screen.heatmap_url ?? screen.mockup_url ? (
                        // eslint-disable-next-line @next/next/no-img-element -- external CDN host
                        <img
                          src={(screen.heatmap_url ?? screen.mockup_url) as string}
                          alt={`Screen ${screen.page_number}`}
                          className="h-full w-full object-cover object-top"
                        />
                      ) : null}
                      <span className="absolute left-3 top-3 flex h-7 w-7 items-center justify-center rounded-full bg-navy-900/90 font-mono text-[12px] font-bold text-white backdrop-blur">
                        {screen.page_number}
                      </span>
                      {isWeakest ? (
                        <span className="absolute right-3 top-3">
                          <Badge tone="danger">Weakest</Badge>
                        </span>
                      ) : isStrongest ? (
                        <span className="absolute right-3 top-3">
                          <Badge tone="success">Strongest</Badge>
                        </span>
                      ) : null}
                    </div>

                    <div className="flex flex-1 flex-col p-5">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-[12px] font-medium text-[var(--color-muted)]">
                          Screen {screen.page_number}
                        </span>
                        {/* The score itself belongs to the pill below; repeating
                            it here read as a rendering bug. Say what it means. */}
                        {band ? (
                          <span
                            className="text-[11.5px] font-semibold uppercase tracking-[0.08em]"
                            style={{ color: band.hex }}
                          >
                            {band.label}
                          </span>
                        ) : (
                          <Badge tone="neutral">{screen.status}</Badge>
                        )}
                      </div>

                      <div className="mt-3">
                        <ClarityPill score={screen.clarity_score} />
                      </div>

                      {screen.headline ? (
                        <p className="mt-4 text-[12.5px] font-medium leading-snug text-[var(--color-ink)]">
                          {screen.headline}
                        </p>
                      ) : null}

                      {screen.suggestions.length > 0 ? (
                        <ul className="mt-3 space-y-2">
                          {screen.suggestions.map((s, i) => (
                            <li
                              key={`${screen.asset_id}-${i}`}
                              className="rounded-xl bg-[var(--color-surface-2)] p-3 ring-1 ring-[var(--color-hairline)]"
                            >
                              <div className="flex items-start justify-between gap-2">
                                <p className="text-[12.5px] font-semibold leading-snug">
                                  {s.title}
                                </p>
                                <Badge tone={SEVERITY_TONE[s.severity] ?? "neutral"}>
                                  {s.severity}
                                </Badge>
                              </div>
                              <p className="mt-1.5 text-[11.5px] leading-relaxed text-[var(--color-muted)]">
                                {s.detail}
                              </p>
                            </li>
                          ))}
                        </ul>
                      ) : null}

                      <Button
                        asChild
                        variant="outline"
                        size="sm"
                        className="mt-auto w-full pt-0"
                      >
                        <Link href={`/results/${screen.asset_id}`}>Open full analysis</Link>
                      </Button>
                    </div>
                  </article>
                </BezelSm>
              </StaggerItem>
            );
          })}
        </Stagger>
      </div>

      {batch.screens_failed > 0 ? (
        <Reveal>
          <div className="flex items-start gap-3 rounded-2xl bg-amber-50 p-4 ring-1 ring-amber-200 dark:bg-amber-500/10 dark:ring-amber-400/20">
            <AlertCircle
              size={18}
              strokeWidth={1.5}
              className="mt-0.5 shrink-0 text-amber-600 dark:text-amber-400"
            />
            <p className="text-[13px] text-amber-800 dark:text-amber-300">
              {batch.screens_failed} of {batch.page_count} screens could not be analysed.
              The rest of the flow is unaffected.
            </p>
          </div>
        </Reveal>
      ) : null}
    </div>
  );
}
