"use client";

import { ArrowUpRight, Eye, FolderPlus, Layers, Plus, RefreshCw, Search, Trash2 } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { ClarityPill } from "@/components/app/clarity-gauge";
import { Bezel } from "@/components/ui/bezel";
import { Button } from "@/components/ui/button";
import {
  Badge,
  Eyebrow,
  Input,
  Reveal,
  Skeleton,
  Stagger,
  StaggerItem,
} from "@/components/ui/primitives";
import {
  useBatches,
  useCreateProject,
  useDeleteResult,
  useProjects,
  useRerun,
  useResults,
} from "@/hooks/use-api";
import { cn, formatDate } from "@/lib/utils";

const STATUS_TONE = {
  complete: "success",
  processing: "warning",
  pending: "neutral",
  failed: "danger",
} as const;

const PAGE_SIZE = 8;

export default function ProjectsPage() {
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");

  const { data, isLoading } = useResults(page, PAGE_SIZE);
  const { data: projectData } = useProjects(1, 100);
  const { data: batchData } = useBatches(1, 6);
  const createProject = useCreateProject();
  const rerun = useRerun();
  const remove = useDeleteResult();

  const rows = useMemo(() => {
    let items = data?.results ?? [];
    if (query.trim()) {
      const q = query.toLowerCase();
      items = items.filter((r) => r.original_filename.toLowerCase().includes(q));
    }
    if (statusFilter !== "all") items = items.filter((r) => r.status === statusFilter);
    return items;
  }, [data, query, statusFilter]);

  const totalPages = Math.max(1, Math.ceil((data?.total_count ?? 0) / PAGE_SIZE));
  const avgClarity = useMemo(() => {
    const scored = (data?.results ?? []).filter((r) => r.clarity_score !== null);
    if (scored.length === 0) return null;
    return scored.reduce((s, r) => s + (r.clarity_score ?? 0), 0) / scored.length;
  }, [data]);

  return (
    <div className="mx-auto max-w-[76rem] space-y-8">
      <Reveal>
        <div className="flex flex-wrap items-end justify-between gap-5">
          <div>
            <Eyebrow>Workspace</Eyebrow>
            <h1 className="mt-4 font-display text-[2.1rem] font-bold tracking-[-0.028em]">
              My projects
            </h1>
            <p className="mt-2 text-[14.5px] text-[var(--color-muted)]">
              Manage past audits and track clarity improvements over time.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="rounded-2xl bg-[var(--color-surface)] px-5 py-3 ring-1 ring-[var(--color-hairline)]">
              <p className="text-[10px] uppercase tracking-[0.14em] text-[var(--color-faint)]">
                Total analyses
              </p>
              <p className="tabular mt-0.5 font-display text-xl font-bold">
                {data?.total_count ?? 0}
              </p>
            </div>
            <div className="rounded-2xl bg-[var(--color-surface)] px-5 py-3 ring-1 ring-[var(--color-hairline)]">
              <p className="text-[10px] uppercase tracking-[0.14em] text-[var(--color-faint)]">
                Avg clarity
              </p>
              <p className="tabular mt-0.5 font-display text-xl font-bold">
                {avgClarity === null ? "—" : avgClarity.toFixed(1)}
              </p>
            </div>
            <Button
              asChild
              size="md"
              variant="primary"
              trailingIcon={<ArrowUpRight size={15} strokeWidth={1.5} />}
            >
              <Link href="/upload">New analysis</Link>
            </Button>
          </div>
        </div>
      </Reveal>

      {/* --- project creator --- */}
      <Reveal>
        <Bezel>
          <div className="p-6">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="flex flex-wrap items-center gap-2.5">
                <span className="text-[12px] font-medium text-[var(--color-muted)]">
                  Projects:
                </span>
                {(projectData?.projects ?? []).slice(0, 5).map((p) => (
                  <Link key={p.project_id} href={`/projects/${p.project_id}`}>
                    <Badge tone="indigo">
                      {p.title} · {p.asset_count}
                    </Badge>
                  </Link>
                ))}
                {(projectData?.projects.length ?? 0) === 0 ? (
                  <span className="text-[12px] text-[var(--color-faint)]">none yet</span>
                ) : null}
              </div>
              <Button size="sm" variant="outline" onClick={() => setCreating((v) => !v)}>
                <FolderPlus size={14} strokeWidth={1.5} />
                {creating ? "Cancel" : "New project"}
              </Button>
            </div>

            {creating ? (
              <div className="mt-5 grid gap-3 sm:grid-cols-[1fr_1.4fr_auto]">
                <Input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Project title"
                />
                <Input
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Description (optional)"
                />
                <Button
                  disabled={!title.trim() || createProject.isPending}
                  onClick={() =>
                    createProject.mutate(
                      { title: title.trim(), description: description.trim() || undefined },
                      {
                        onSuccess: () => {
                          toast.success("Project created.");
                          setTitle("");
                          setDescription("");
                          setCreating(false);
                        },
                        onError: () => toast.error("Could not create the project."),
                      },
                    )
                  }
                >
                  <Plus size={15} strokeWidth={1.5} />
                  Create
                </Button>
              </div>
            ) : null}
          </div>
        </Bezel>
      </Reveal>

      {/* --- multi-screen flows --- */}
      {(batchData?.batches.length ?? 0) > 0 ? (
        <Reveal>
          <div className="flex items-center justify-between">
            <h2 className="flex items-center gap-2 font-display text-lg font-semibold">
              <Layers size={17} strokeWidth={1.5} className="text-indigo-600" />
              Multi-screen flows
            </h2>
            <span className="text-[12px] text-[var(--color-muted)]">
              {batchData?.total_count} total
            </span>
          </div>
          <Stagger className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {batchData?.batches.map((b) => (
              <StaggerItem key={b.batch_id}>
                <Link href={`/batches/${b.batch_id}`}>
                  <Bezel className="h-full transition-transform duration-500 ease-[cubic-bezier(0.32,0.72,0,1)] hover:-translate-y-0.5">
                    <div className="p-5">
                      <div className="flex items-start justify-between gap-3">
                        <p className="truncate font-display text-[14.5px] font-semibold">
                          {b.source_filename}
                        </p>
                        <Badge tone={b.status === "complete" ? "success" : "warning"}>
                          {b.status}
                        </Badge>
                      </div>
                      <p className="tabular mt-2 text-[12px] text-[var(--color-faint)]">
                        {b.page_count} screens · {formatDate(b.created_at)}
                      </p>
                      <div className="mt-3">
                        <ClarityPill score={b.avg_clarity_score} />
                      </div>
                    </div>
                  </Bezel>
                </Link>
              </StaggerItem>
            ))}
          </Stagger>
        </Reveal>
      ) : null}

      {/* --- filters --- */}
      <Reveal>
        <div className="flex flex-wrap gap-3">
          <div className="relative min-w-[15rem] flex-1">
            <Search
              size={16}
              strokeWidth={1.5}
              className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-[var(--color-faint)]"
            />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by file name…"
              className="pl-10"
            />
          </div>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="h-12 rounded-xl bg-[var(--color-surface-2)] px-4 text-[13.5px] ring-1 ring-[var(--color-hairline)] focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="all">All status</option>
            <option value="complete">Completed</option>
            <option value="processing">Processing</option>
            <option value="pending">Pending</option>
            <option value="failed">Failed</option>
          </select>
        </div>
      </Reveal>

      {/* --- table --- */}
      {isLoading ? (
        <div className="space-y-3">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-24 rounded-2xl" />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <Bezel>
          <div className="flex flex-col items-center px-8 py-16 text-center">
            <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-300">
              <Eye size={22} strokeWidth={1.5} />
            </span>
            <h3 className="mt-5 font-display text-lg font-semibold">
              {query || statusFilter !== "all" ? "No matches" : "No analyses yet"}
            </h3>
            <p className="mt-2 max-w-sm text-[14px] text-[var(--color-muted)]">
              {query || statusFilter !== "all"
                ? "Try a different search term or status filter."
                : "Upload your first mockup to start building analysis history."}
            </p>
            {!query && statusFilter === "all" ? (
              <Button asChild className="mt-7">
                <Link href="/upload">Upload a mockup</Link>
              </Button>
            ) : null}
          </div>
        </Bezel>
      ) : (
        <Stagger className="space-y-3">
          {rows.map((row) => (
            <StaggerItem key={row.asset_id}>
              <Bezel>
                <div className="flex flex-wrap items-center gap-4 p-4 sm:flex-nowrap sm:p-5">
                  <div className="relative h-16 w-24 shrink-0 overflow-hidden rounded-xl bg-[var(--color-shell)]">
                    {row.heatmap_url ?? row.mockup_url ? (
                      <Image
                        src={(row.heatmap_url ?? row.mockup_url) as string}
                        alt=""
                        fill
                        unoptimized
                        sizes="96px"
                        className="object-cover object-top"
                      />
                    ) : null}
                  </div>

                  <div className="min-w-0 flex-1">
                    <Link
                      href={`/results/${row.asset_id}`}
                      className="block truncate font-display text-[15px] font-semibold transition-colors hover:text-indigo-600"
                    >
                      {row.original_filename}
                    </Link>
                    <p className="tabular mt-1 text-[12px] text-[var(--color-faint)]">
                      {formatDate(row.uploaded_at)} · {row.width}×{row.height}
                    </p>
                  </div>

                  <div className="w-32 shrink-0">
                    <ClarityPill score={row.clarity_score} />
                  </div>

                  <Badge tone={STATUS_TONE[row.status as keyof typeof STATUS_TONE] ?? "neutral"}>
                    {row.status}
                  </Badge>

                  <div className="flex shrink-0 items-center gap-1">
                    <Link
                      href={`/results/${row.asset_id}`}
                      aria-label="View analysis"
                      className="rounded-lg p-2 text-indigo-600 transition-colors hover:bg-indigo-50 dark:hover:bg-indigo-500/10"
                    >
                      <Eye size={16} strokeWidth={1.5} />
                    </Link>
                    <button
                      type="button"
                      aria-label="Rerun analysis"
                      onClick={() =>
                        rerun.mutate(row.asset_id, {
                          onSuccess: () => toast.success("Re-analysis queued."),
                          onError: () => toast.error("Could not rerun."),
                        })
                      }
                      className="rounded-lg p-2 text-[var(--color-muted)] transition-colors hover:bg-[var(--color-shell)]"
                    >
                      <RefreshCw
                        size={16}
                        strokeWidth={1.5}
                        className={cn(rerun.isPending && "animate-spin")}
                      />
                    </button>
                    <button
                      type="button"
                      aria-label="Delete analysis"
                      onClick={() => {
                        if (!window.confirm(`Delete "${row.original_filename}" and its analysis? This cannot be undone.`)) return;
                        remove.mutate(row.asset_id, {
                          onSuccess: () => toast.success("Deleted."),
                          onError: () => toast.error("Could not delete."),
                        });
                      }}
                      className="rounded-lg p-2 text-[var(--color-faint)] transition-colors hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-500/10"
                    >
                      <Trash2 size={16} strokeWidth={1.5} />
                    </button>
                  </div>
                </div>
              </Bezel>
            </StaggerItem>
          ))}
        </Stagger>
      )}

      {totalPages > 1 ? (
        <div className="flex items-center justify-between">
          <p className="text-[12.5px] text-[var(--color-muted)]">
            Page {page} of {totalPages} · {data?.total_count} analyses
          </p>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
              Previous
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
