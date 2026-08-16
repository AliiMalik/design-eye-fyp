"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  AlertCircle,
  ArrowRight,
  Check,
  FileImage,
  Loader2,
  UploadCloud,
  X,
} from "lucide-react";
import Image from "next/image";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { Bezel } from "@/components/ui/bezel";
import { Button } from "@/components/ui/button";
import { Badge, Eyebrow, Reveal } from "@/components/ui/primitives";
import { useProjects, useTaskPolling, useUpload } from "@/hooks/use-api";
import { apiErrorMessage } from "@/lib/api";
import { STAGE_LABELS, STAGE_ORDER, cn, formatBytes } from "@/lib/utils";

const ACCEPT = ".png,.jpg,.jpeg,.webp,.svg,.pdf";
const MAX_MB = 10;
const EASE = [0.32, 0.72, 0, 1] as const;

function UploadFlow() {
  const router = useRouter();
  const params = useSearchParams();
  const upload = useUpload();
  const { data: projectData } = useProjects(1, 100);

  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [projectId, setProjectId] = useState<string>("");
  const [uploadPct, setUploadPct] = useState(0);
  const [taskId, setTaskId] = useState<string | null>(params.get("task"));
  const [assetId, setAssetId] = useState<string | null>(params.get("asset"));
  const inputRef = useRef<HTMLInputElement>(null);

  const { status, timedOut, elapsedMs } = useTaskPolling(taskId);

  useEffect(() => {
    if (!preview) return;
    return () => URL.revokeObjectURL(preview);
  }, [preview]);

  useEffect(() => {
    if (status?.status === "complete" && assetId) {
      const t = window.setTimeout(() => router.push(`/results/${assetId}`), 900);
      return () => window.clearTimeout(t);
    }
  }, [status?.status, assetId, router]);

  const accept = useCallback((chosen: File) => {
    const ext = chosen.name.split(".").pop()?.toLowerCase() ?? "";
    if (!["png", "jpg", "jpeg", "webp", "svg", "pdf"].includes(ext)) {
      toast.error("Unsupported file. Use PNG, JPG, JPEG, WEBP, SVG, or PDF.");
      return;
    }
    if (chosen.size > MAX_MB * 1024 * 1024) {
      toast.error(`File size exceeds the ${MAX_MB}MB limit.`);
      return;
    }
    setFile(chosen);
    setPreview(
      ["png", "jpg", "jpeg", "webp"].includes(ext) ? URL.createObjectURL(chosen) : null,
    );
  }, []);

  const start = () => {
    if (!file) return;
    setUploadPct(0);
    upload.mutate(
      { file, projectId: projectId || undefined, onProgress: setUploadPct },
      {
        onSuccess: (data) => {
          setTaskId(data.task_id);
          setAssetId(data.asset_id);
        },
        onError: (error) => toast.error(apiErrorMessage(error, "Upload failed.")),
      },
    );
  };

  const reset = () => {
    setFile(null);
    setPreview(null);
    setTaskId(null);
    setAssetId(null);
    setUploadPct(0);
  };

  const activeStageIndex = useMemo(() => {
    if (!status) return upload.isPending ? 0 : -1;
    const idx = STAGE_ORDER.indexOf(status.stage);
    return idx === -1 ? 0 : idx;
  }, [status, upload.isPending]);

  const failed = status?.status === "failed" || timedOut;

  return (
    <div className="mx-auto max-w-[46rem] space-y-8">
      <Reveal>
        <div className="text-center">
          <Eyebrow>Utility · Mockup tool</Eyebrow>
          <h1 className="mt-5 font-display text-[2.2rem] font-bold tracking-[-0.028em] sm:text-[2.6rem]">
            Upload UI mockup
          </h1>
          <p className="mx-auto mt-3 max-w-md text-[14.5px] leading-relaxed text-[var(--color-muted)]">
            Prepare your design assets for attention analysis using DesignEye&apos;s
            saliency engine.
          </p>
        </div>
      </Reveal>

      <AnimatePresence mode="wait">
        {!taskId ? (
          <motion.div
            key="picker"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20, filter: "blur(6px)" }}
            transition={{ duration: 0.5, ease: EASE }}
          >
            <Bezel>
              <div className="p-6 sm:p-8">
                <div
                  onDragOver={(e) => {
                    e.preventDefault();
                    setDragging(true);
                  }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={(e) => {
                    e.preventDefault();
                    setDragging(false);
                    const dropped = e.dataTransfer.files?.[0];
                    if (dropped) accept(dropped);
                  }}
                  onClick={() => inputRef.current?.click()}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
                  }}
                  className={cn(
                    "flex cursor-pointer flex-col items-center justify-center rounded-[1.5rem]",
                    "border-2 border-dashed px-6 py-14 text-center",
                    "transition-all duration-500 ease-[cubic-bezier(0.32,0.72,0,1)]",
                    dragging
                      ? "scale-[1.015] border-indigo-500 bg-indigo-50/70 shadow-[var(--shadow-glow)] dark:bg-indigo-500/10"
                      : "border-[var(--color-hairline-strong)] bg-[var(--color-surface-2)] hover:border-indigo-400",
                  )}
                >
                  <motion.span
                    animate={{ scale: dragging ? 1.12 : 1, y: dragging ? -4 : 0 }}
                    transition={{ duration: 0.45, ease: EASE }}
                    className="flex h-16 w-16 items-center justify-center rounded-2xl bg-[var(--color-surface)] text-indigo-600 shadow-[var(--shadow-ambient)]"
                  >
                    <UploadCloud size={26} strokeWidth={1.5} />
                  </motion.span>

                  <p className="mt-6 font-display text-[17px] font-semibold">
                    Drag &amp; drop your mockup here
                  </p>
                  <p className="mt-1.5 text-[13px] text-[var(--color-muted)]">
                    Files are processed securely.{" "}
                    <span className="font-medium text-indigo-600">or browse files</span>
                  </p>

                  <input
                    ref={inputRef}
                    type="file"
                    accept={ACCEPT}
                    className="hidden"
                    onChange={(e) => {
                      const chosen = e.target.files?.[0];
                      if (chosen) accept(chosen);
                      e.target.value = "";
                    }}
                  />
                </div>

                <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                  <p className="text-[12px] text-[var(--color-muted)]">
                    Supported: <span className="font-medium">PNG, JPG, WEBP, SVG, PDF</span>{" "}
                    · Max size: <span className="font-medium">{MAX_MB}MB</span>
                  </p>
                  <Badge tone="neutral">stage3-ui-v1</Badge>
                </div>

                <AnimatePresence>
                  {file ? (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                      transition={{ duration: 0.45, ease: EASE }}
                      className="overflow-hidden"
                    >
                      <p className="mt-7 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--color-faint)]">
                        Selected asset
                      </p>
                      <div className="mt-3 flex items-center gap-4 rounded-2xl bg-[var(--color-surface-2)] p-3.5 ring-1 ring-[var(--color-hairline)]">
                        <div className="relative h-14 w-14 shrink-0 overflow-hidden rounded-xl bg-[var(--color-shell)]">
                          {preview ? (
                            <Image
                              src={preview}
                              alt=""
                              fill
                              unoptimized
                              className="object-cover"
                            />
                          ) : (
                            <span className="flex h-full items-center justify-center text-[var(--color-faint)]">
                              <FileImage size={20} strokeWidth={1.5} />
                            </span>
                          )}
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-[13.5px] font-medium">{file.name}</p>
                          <p className="tabular mt-0.5 text-[12px] text-[var(--color-muted)]">
                            {formatBytes(Math.round(file.size / 1024))}
                          </p>
                        </div>
                        <button
                          type="button"
                          aria-label="Remove file"
                          onClick={reset}
                          className="rounded-lg p-2 text-[var(--color-faint)] transition-colors hover:text-red-500"
                        >
                          <X size={16} strokeWidth={1.5} />
                        </button>
                      </div>

                      {projectData && projectData.projects.length > 0 ? (
                        <div className="mt-4">
                          <label
                            htmlFor="project"
                            className="text-[12px] font-medium text-[var(--color-ink)]"
                          >
                            Project (optional)
                          </label>
                          <select
                            id="project"
                            value={projectId}
                            onChange={(e) => setProjectId(e.target.value)}
                            className="mt-2 h-11 w-full rounded-xl bg-[var(--color-surface-2)] px-3 text-[13.5px] ring-1 ring-[var(--color-hairline)] focus:outline-none focus:ring-2 focus:ring-indigo-500"
                          >
                            <option value="">My Uploads (default)</option>
                            {projectData.projects.map((p) => (
                              <option key={p.project_id} value={p.project_id}>
                                {p.title}
                              </option>
                            ))}
                          </select>
                        </div>
                      ) : null}
                    </motion.div>
                  ) : null}
                </AnimatePresence>

                <Button
                  size="lg"
                  variant="primary"
                  className="mt-7 w-full"
                  disabled={!file || upload.isPending}
                  onClick={start}
                  trailingIcon={<ArrowRight size={16} strokeWidth={1.5} />}
                >
                  {upload.isPending ? `Uploading ${uploadPct}%` : "Analyse design"}
                </Button>
              </div>
            </Bezel>
          </motion.div>
        ) : (
          <motion.div
            key="progress"
            initial={{ opacity: 0, y: 24, filter: "blur(8px)" }}
            animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            transition={{ duration: 0.6, ease: EASE }}
          >
            <Bezel>
              <div className="p-7 sm:p-9">
                <div className="flex items-center gap-4">
                  <div className="relative h-16 w-16 shrink-0 overflow-hidden rounded-2xl bg-[var(--color-shell)]">
                    {preview ? (
                      <Image src={preview} alt="" fill unoptimized className="object-cover" />
                    ) : (
                      <span className="flex h-full items-center justify-center text-[var(--color-faint)]">
                        <FileImage size={22} strokeWidth={1.5} />
                      </span>
                    )}
                  </div>
                  <div className="min-w-0">
                    <h2 className="truncate font-display text-[17px] font-semibold">
                      {file?.name ?? "Analysing mockup"}
                    </h2>
                    <p className="tabular mt-1 text-[12.5px] text-[var(--color-muted)]">
                      {failed
                        ? "Analysis did not finish"
                        : status?.status === "complete"
                          ? "Complete — opening results…"
                          : `Working… ${Math.round(elapsedMs / 1000)}s elapsed`}
                    </p>
                  </div>
                </div>

                <ol className="mt-8 space-y-1">
                  {STAGE_ORDER.filter((s) => s !== "complete").map((stage, i) => {
                    const done = activeStageIndex > i || status?.status === "complete";
                    const current = activeStageIndex === i && status?.status !== "complete";
                    return (
                      <li
                        key={stage}
                        className={cn(
                          "flex items-center gap-3 rounded-xl px-3 py-3 transition-colors duration-500",
                          current && "bg-indigo-50/70 dark:bg-indigo-500/10",
                        )}
                      >
                        <span
                          className={cn(
                            "flex h-7 w-7 shrink-0 items-center justify-center rounded-full",
                            "transition-all duration-500 ease-[cubic-bezier(0.32,0.72,0,1)]",
                            done
                              ? "bg-emerald-500 text-white"
                              : current
                                ? "bg-indigo-600 text-white"
                                : "bg-[var(--color-shell)] text-[var(--color-faint)]",
                          )}
                        >
                          {done ? (
                            <Check size={14} strokeWidth={2.5} />
                          ) : current ? (
                            <Loader2 size={14} strokeWidth={2} className="animate-spin" />
                          ) : (
                            <span className="tabular text-[11px]">{i + 1}</span>
                          )}
                        </span>
                        <span
                          className={cn(
                            "text-[13.5px] transition-colors duration-500",
                            done || current
                              ? "font-medium text-[var(--color-ink)]"
                              : "text-[var(--color-faint)]",
                          )}
                        >
                          {STAGE_LABELS[stage]}
                        </span>
                      </li>
                    );
                  })}
                </ol>

                {failed ? (
                  <div className="mt-7 flex items-start gap-3 rounded-2xl bg-red-50 p-4 ring-1 ring-red-200 dark:bg-red-500/10 dark:ring-red-400/20">
                    <AlertCircle
                      size={18}
                      strokeWidth={1.5}
                      className="mt-0.5 shrink-0 text-red-600 dark:text-red-400"
                    />
                    <div>
                      <p className="text-[13.5px] font-medium text-red-800 dark:text-red-300">
                        {timedOut
                          ? "This is taking longer than expected."
                          : (status?.error ?? "Analysis failed.")}
                      </p>
                      <Button size="sm" variant="outline" className="mt-3" onClick={reset}>
                        Try another upload
                      </Button>
                    </div>
                  </div>
                ) : null}
              </div>
            </Bezel>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default function UploadPage() {
  return (
    <Suspense fallback={<div className="h-96" />}>
      <UploadFlow />
    </Suspense>
  );
}
