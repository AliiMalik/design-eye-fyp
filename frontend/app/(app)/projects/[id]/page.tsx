"use client";

import { ArrowLeft, Check, Eye, Pencil, Trash2, UploadCloud, X } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
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
  useDeleteProject,
  useProject,
  useResults,
  useUpdateProject,
} from "@/hooks/use-api";
import { formatDate, formatRelative } from "@/lib/utils";

const STATUS_TONE = {
  complete: "success",
  processing: "warning",
  pending: "neutral",
  failed: "danger",
} as const;

export default function ProjectDetailPage() {
  const params = useParams<{ id: string }>();
  const projectId = params.id;
  const router = useRouter();

  const { data, isLoading, isError } = useProject(projectId);
  const { data: results } = useResults(1, 100, projectId);
  const update = useUpdateProject(projectId);
  const remove = useDeleteProject();

  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");

  useEffect(() => {
    if (data?.project) {
      setTitle(data.project.title);
      setDescription(data.project.description ?? "");
    }
  }, [data?.project]);

  if (isLoading) {
    return (
      <div className="mx-auto max-w-[72rem] space-y-6">
        <Skeleton className="h-11 w-72" />
        <Skeleton className="h-28 rounded-[2rem]" />
        <Skeleton className="h-72 rounded-[2rem]" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="mx-auto max-w-[42rem]">
        <Bezel>
          <div className="px-8 py-16 text-center">
            <h2 className="font-display text-xl font-semibold">Project unavailable</h2>
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

  const { project } = data;
  const scoreById = new Map(
    (results?.results ?? []).map((r) => [r.asset_id, r]),
  );

  return (
    <div className="mx-auto max-w-[72rem] space-y-8">
      <Reveal>
        <Link
          href="/projects"
          className="inline-flex items-center gap-1.5 text-[12px] font-medium text-[var(--color-muted)] transition-colors hover:text-indigo-600"
        >
          <ArrowLeft size={13} strokeWidth={1.5} />
          All projects
        </Link>

        <div className="mt-4 flex flex-wrap items-start justify-between gap-5">
          <div className="min-w-0 flex-1">
            <Eyebrow>Project</Eyebrow>
            {editing ? (
              <div className="mt-4 max-w-xl space-y-3">
                <Input value={title} onChange={(e) => setTitle(e.target.value)} />
                <Input
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Description"
                />
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    disabled={!title.trim() || update.isPending}
                    onClick={() =>
                      update.mutate(
                        { title: title.trim(), description: description.trim() },
                        {
                          onSuccess: () => {
                            toast.success("Project updated.");
                            setEditing(false);
                          },
                          onError: () => toast.error("Could not update the project."),
                        },
                      )
                    }
                  >
                    <Check size={14} strokeWidth={1.5} />
                    Save
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>
                    <X size={14} strokeWidth={1.5} />
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <>
                <h1 className="mt-4 font-display text-[2.1rem] font-bold tracking-[-0.028em]">
                  {project.title}
                </h1>
                <p className="mt-2 max-w-2xl text-[14.5px] text-[var(--color-muted)]">
                  {project.description || "No description."}
                </p>
                <p className="tabular mt-2 text-[12px] text-[var(--color-faint)]">
                  Created {formatDate(project.created_at)} · {project.asset_count} assets
                  {project.avg_clarity_score !== null
                    ? ` · avg clarity ${project.avg_clarity_score.toFixed(1)}`
                    : ""}
                </p>
              </>
            )}
          </div>

          {!editing ? (
            <div className="flex flex-wrap gap-2.5">
              <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
                <Pencil size={14} strokeWidth={1.5} />
                Edit
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  if (
                    !window.confirm(
                      `Delete "${project.title}" and all ${project.asset_count} analyses? This cannot be undone.`,
                    )
                  )
                    return;
                  remove.mutate(projectId, {
                    onSuccess: () => {
                      toast.success("Project deleted.");
                      router.push("/projects");
                    },
                    onError: () => toast.error("Could not delete the project."),
                  });
                }}
              >
                <Trash2 size={14} strokeWidth={1.5} />
                Delete
              </Button>
              <Button asChild size="sm" variant="primary">
                <Link href="/upload">
                  <UploadCloud size={14} strokeWidth={1.5} />
                  Add mockup
                </Link>
              </Button>
            </div>
          ) : null}
        </div>
      </Reveal>

      {data.assets.length === 0 ? (
        <Reveal>
          <Bezel>
            <div className="flex flex-col items-center px-8 py-16 text-center">
              <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-300">
                <UploadCloud size={22} strokeWidth={1.5} />
              </span>
              <h3 className="mt-5 font-display text-lg font-semibold">No mockups yet</h3>
              <p className="mt-2 max-w-sm text-[14px] text-[var(--color-muted)]">
                Upload a design into this project to see its predicted attention.
              </p>
              <Button asChild className="mt-7">
                <Link href="/upload">Upload a mockup</Link>
              </Button>
            </div>
          </Bezel>
        </Reveal>
      ) : (
        <Stagger className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {data.assets.map((asset) => {
            const row = scoreById.get(asset.asset_id);
            return (
              <StaggerItem key={asset.asset_id}>
                <Bezel className="h-full">
                  <article className="flex h-full flex-col overflow-hidden rounded-[calc(2rem-0.375rem)]">
                    <div className="relative aspect-[16/10] w-full overflow-hidden bg-[var(--color-shell)]">
                      {row?.heatmap_url ?? asset.file_url ? (
                        <Image
                          src={(row?.heatmap_url ?? asset.file_url) as string}
                          alt={asset.original_filename}
                          fill
                          unoptimized
                          sizes="(max-width: 640px) 100vw, 320px"
                          className="object-cover object-top"
                        />
                      ) : null}
                      <span className="absolute right-3 top-3">
                        <Badge
                          tone={STATUS_TONE[asset.status as keyof typeof STATUS_TONE] ?? "neutral"}
                        >
                          {asset.status}
                        </Badge>
                      </span>
                    </div>

                    <div className="flex flex-1 flex-col p-5">
                      <h3 className="truncate font-display text-[15px] font-semibold">
                        {asset.original_filename}
                      </h3>
                      <p className="tabular mt-1 text-[12px] text-[var(--color-faint)]">
                        {asset.width}×{asset.height} · {formatRelative(asset.uploaded_at)}
                      </p>
                      <div className="mt-4">
                        <ClarityPill score={row?.clarity_score ?? null} />
                      </div>
                      <Button
                        asChild
                        variant="outline"
                        size="sm"
                        className="mt-5 w-full"
                        trailingIcon={<Eye size={13} strokeWidth={1.5} />}
                      >
                        <Link href={`/results/${asset.asset_id}`}>View analysis</Link>
                      </Button>
                    </div>
                  </article>
                </Bezel>
              </StaggerItem>
            );
          })}
        </Stagger>
      )}
    </div>
  );
}
