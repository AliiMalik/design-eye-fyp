"use client";

import {
  ArrowUpRight,
  CheckCircle2,
  Clock,
  Eye,
  Layers,
  Sparkles,
  TrendingUp,
  Zap,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

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
} from "@/components/ui/primitives";
import { useDashboard } from "@/hooks/use-api";
import { useAuthStore } from "@/lib/auth-store";
import { clarityBand, formatDate, formatRelative } from "@/lib/utils";

const STATUS_TONE = {
  complete: "success",
  processing: "warning",
  pending: "neutral",
  failed: "danger",
} as const;

export default function DashboardPage() {
  const user = useAuthStore((s) => s.user);
  const { data, isLoading, isError } = useDashboard();

  const firstName = (user?.display_name ?? "Designer").split(" ")[0];

  if (isLoading) {
    return (
      <div className="mx-auto max-w-[74rem] space-y-8">
        <Skeleton className="h-12 w-80" />
        <div className="grid gap-5 sm:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-36 rounded-[2rem]" />
          ))}
        </div>
        <Skeleton className="h-72 rounded-[2rem]" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="mx-auto max-w-[74rem]">
        <Bezel>
          <div className="px-8 py-14 text-center">
            <h2 className="font-display text-xl font-semibold">
              Could not load your dashboard
            </h2>
            <p className="mt-2 text-[14px] text-[var(--color-muted)]">
              The API did not respond. Check that the backend is running, then retry.
            </p>
            <Button className="mt-6" onClick={() => window.location.reload()}>
              Retry
            </Button>
          </div>
        </Bezel>
      </div>
    );
  }

  // A brand-new account has analysed nothing, and an average over nothing is not
  // zero -- it is absent. Showing "0.0 / Needs work" told first-time users their
  // work scored badly before they had uploaded any, which is both false and
  // discouraging. The projects page already used an em dash for this; the two
  // now agree.
  const hasScores = data.total_analyses > 0;

  const stats = [
    {
      label: "Total projects",
      value: data.total_projects,
      note: `+${data.projects_this_month} this month`,
      icon: Layers,
      tone: "indigo" as const,
    },
    {
      label: "Analyses run",
      value: data.total_analyses,
      note: "across all projects",
      icon: Zap,
      tone: "success" as const,
    },
    {
      label: "Avg. clarity score",
      value: hasScores ? data.avg_clarity_score.toFixed(1) : "—",
      note: hasScores ? clarityBand(data.avg_clarity_score).label : "no analyses yet",
      icon: CheckCircle2,
      tone: "violet" as const,
    },
  ];

  // Several analyses often land on the same day, so label by file rather than
  // repeating an identical date across every tick.
  const trend = data.clarity_trend.map((p, i) => ({
    name: p.original_filename
      ? p.original_filename.replace(/\.[^.]+$/, "").slice(0, 14)
      : formatDate(p.date),
    score: p.clarity_score,
    index: i,
  }));

  return (
    <div className="mx-auto max-w-[74rem] space-y-10">
      <Reveal>
        <div className="flex flex-wrap items-end justify-between gap-5">
          <div>
            <Eyebrow>Dashboard</Eyebrow>
            {/* "Welcome back" greeted people who had never been here, and
                promised insights that did not exist yet. */}
            <h1 className="mt-4 font-display text-[2.1rem] font-bold tracking-[-0.028em] sm:text-[2.5rem]">
              {hasScores ? `Welcome back, ${firstName}` : `Welcome, ${firstName}`}
            </h1>
            <p className="mt-2 text-[14.5px] text-[var(--color-muted)]">
              {hasScores
                ? "Your design insights are ready for review."
                : "Upload a mockup and DesignEye will show you where people look first."}
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Button asChild variant="outline" size="md">
              <Link href="/compare">
                <Eye size={16} strokeWidth={1.5} />
                A/B compare
              </Link>
            </Button>
            <Button
              asChild
              size="md"
              variant="primary"
              trailingIcon={<ArrowUpRight size={15} strokeWidth={1.5} />}
            >
              <Link href="/upload">Run new analysis</Link>
            </Button>
          </div>
        </div>
      </Reveal>

      <Stagger className="grid gap-5 sm:grid-cols-3">
        {stats.map((s) => (
          <StaggerItem key={s.label}>
            <Bezel className="h-full">
              <div className="p-6">
                <div className="flex items-start justify-between">
                  <span className="inline-flex h-11 w-11 items-center justify-center rounded-xl bg-[var(--color-shell)] text-[var(--color-ink-2)]">
                    <s.icon size={18} strokeWidth={1.5} />
                  </span>
                  <Badge tone={s.tone}>{s.note}</Badge>
                </div>
                <p className="mt-6 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--color-faint)]">
                  {s.label}
                </p>
                <p className="tabular mt-1.5 font-display text-4xl font-bold">{s.value}</p>
              </div>
            </Bezel>
          </StaggerItem>
        ))}
      </Stagger>

      {trend.length > 1 ? (
        <Reveal>
          <Bezel>
            <div className="p-7">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <h2 className="font-display text-lg font-semibold">Clarity trend</h2>
                  <p className="mt-1 text-[13px] text-[var(--color-muted)]">
                    Your last {trend.length} analyses, oldest first.
                  </p>
                </div>
                <TrendingUp size={18} strokeWidth={1.5} className="text-[var(--color-faint)]" />
              </div>

              <div className="mt-6 h-52 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={trend} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                    <defs>
                      <linearGradient id="clarityFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#4f5bd5" stopOpacity={0.32} />
                        <stop offset="100%" stopColor="#4f5bd5" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <XAxis
                      dataKey="name"
                      tick={{ fontSize: 11, fill: "var(--color-faint)" }}
                      tickLine={false}
                      axisLine={false}
                    />
                    <YAxis
                      domain={[0, 100]}
                      tick={{ fontSize: 11, fill: "var(--color-faint)" }}
                      tickLine={false}
                      axisLine={false}
                      width={44}
                    />
                    <Tooltip
                      cursor={{ stroke: "var(--color-hairline-strong)" }}
                      contentStyle={{
                        borderRadius: 14,
                        border: "1px solid var(--color-hairline)",
                        background: "var(--color-surface)",
                        fontSize: 12,
                      }}
                      formatter={(value: number) => [`${value.toFixed(1)} / 100`, "Clarity"]}
                    />
                    <Area
                      type="monotone"
                      dataKey="score"
                      stroke="#4f5bd5"
                      strokeWidth={2.5}
                      fill="url(#clarityFill)"
                      animationDuration={1100}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
          </Bezel>
        </Reveal>
      ) : null}

      <div>
        <Reveal>
          <div className="flex items-center justify-between">
            <h2 className="font-display text-xl font-semibold">Recent analyses</h2>
            <Link
              href="/projects"
              className="text-[13px] font-medium text-indigo-600 hover:underline"
            >
              View all projects
            </Link>
          </div>
        </Reveal>

        {data.recent_assets.length === 0 ? (
          <Reveal>
            <Bezel className="mt-5">
              <div className="flex flex-col items-center px-8 py-16 text-center">
                <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-300">
                  <Sparkles size={22} strokeWidth={1.5} />
                </span>
                <h3 className="mt-5 font-display text-lg font-semibold">
                  No analyses yet
                </h3>
                <p className="mt-2 max-w-sm text-[14px] text-[var(--color-muted)]">
                  Upload your first mockup and DesignEye will predict where attention
                  lands, score its clarity, and rank the focus order.
                </p>
                <Button
                  asChild
                  className="mt-7"
                  trailingIcon={<ArrowUpRight size={15} strokeWidth={1.5} />}
                >
                  <Link href="/upload">Upload a mockup</Link>
                </Button>
              </div>
            </Bezel>
          </Reveal>
        ) : (
          <Stagger className="mt-5 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {data.recent_assets.map((asset) => (
              <StaggerItem key={asset.asset_id}>
                <BezelSm className="h-full">
                  <article className="flex h-full flex-col overflow-hidden rounded-[1rem]">
                    <div className="relative aspect-[16/10] w-full overflow-hidden bg-[var(--color-shell)]">
                      {asset.heatmap_url ?? asset.mockup_url ? (
                        <Image
                          src={(asset.heatmap_url ?? asset.mockup_url) as string}
                          alt={asset.original_filename}
                          fill
                          unoptimized
                          sizes="(max-width: 640px) 100vw, 320px"
                          className="object-cover object-top"
                        />
                      ) : null}
                      <span className="absolute right-3 top-3">
                        <Badge tone={STATUS_TONE[asset.status as keyof typeof STATUS_TONE] ?? "neutral"}>
                          {asset.status}
                        </Badge>
                      </span>
                    </div>

                    <div className="flex flex-1 flex-col p-5">
                      <h3 className="truncate font-display text-[15px] font-semibold">
                        {asset.original_filename}
                      </h3>
                      <p className="mt-1.5 flex items-center gap-1.5 text-[12px] text-[var(--color-faint)]">
                        <Clock size={12} strokeWidth={1.5} />
                        {formatRelative(asset.uploaded_at)}
                      </p>

                      <div className="mt-4">
                        <ClarityPill score={asset.clarity_score} />
                      </div>

                      <Button
                        asChild
                        variant="outline"
                        size="sm"
                        className="mt-5 w-full"
                        trailingIcon={<Eye size={13} strokeWidth={1.5} />}
                      >
                        <Link href={`/results/${asset.asset_id}`}>View heatmap</Link>
                      </Button>
                    </div>
                  </article>
                </BezelSm>
              </StaggerItem>
            ))}
          </Stagger>
        )}
      </div>
    </div>
  );
}
