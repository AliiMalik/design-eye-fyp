"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Download, Info, Pause, Play, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { computeFit, toScreenCoords, type ImageFit } from "@/lib/coords";
import { cn } from "@/lib/utils";
import type { ScanpathStep } from "@/types/api";

const SPEEDS = [0.5, 1, 2] as const;
type Speed = (typeof SPEEDS)[number];

interface ScanpathPlayerProps {
  assetId: string;
  mockupUrl: string;
  imageWidth: number;
  imageHeight: number;
  steps: ScanpathStep[];
  totalMs: number;
  filename: string;
  className?: string;
}

/**
 * Plays the predicted viewing order back over the mockup.
 *
 * The dot rests on each point, then travels to the next one, so the motion
 * reads the way a person's eye actually moves. Timing comes from the same
 * source the exported video uses, so both always agree.
 */
export function ScanpathPlayer({
  assetId,
  mockupUrl,
  imageWidth,
  imageHeight,
  steps,
  totalMs,
  filename,
  className,
}: ScanpathPlayerProps) {
  const stageRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [elapsed, setElapsed] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [speed, setSpeed] = useState<Speed>(1);
  const [downloading, setDownloading] = useState<"gif" | "mp4" | null>(null);

  const holdMs = 700;
  const runtime = totalMs + holdMs;

  useEffect(() => {
    const el = stageRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect;
      if (rect) setSize({ width: rect.width, height: rect.height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const fit: ImageFit = useMemo(
    () => computeFit(imageWidth, imageHeight, size.width, size.height),
    [imageWidth, imageHeight, size.width, size.height],
  );

  // Drive the clock off rAF timestamps rather than an interval, so playback
  // stays accurate if the browser throttles a background tab.
  const frame = useRef<number>(0);
  const last = useRef<number | null>(null);

  useEffect(() => {
    if (!playing) {
      last.current = null;
      return;
    }
    const tick = (now: number) => {
      if (last.current !== null) {
        setElapsed((prev) => {
          const next = prev + (now - last.current!) * speed;
          return next >= runtime ? runtime : next;
        });
      }
      last.current = now;
      frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame.current);
  }, [playing, speed, runtime]);

  useEffect(() => {
    if (elapsed >= runtime) setPlaying(false);
  }, [elapsed, runtime]);

  const replay = useCallback(() => {
    setElapsed(0);
    setPlaying(true);
  }, []);

  /** Where the eye is right now: resting on a point, or travelling between two. */
  const gaze = useMemo(() => {
    if (steps.length === 0) return { x: 0, y: 0, reached: 0 };
    for (let i = 0; i < steps.length; i += 1) {
      const step = steps[i];
      if (elapsed < step.start_ms) {
        const prev = steps[i - 1];
        const span = Math.max(1, step.start_ms - prev.end_ms);
        const t = Math.min(1, Math.max(0, (elapsed - prev.end_ms) / span));
        return {
          x: prev.x + (step.x - prev.x) * t,
          y: prev.y + (step.y - prev.y) * t,
          reached: i,
        };
      }
      if (elapsed <= step.end_ms) return { x: step.x, y: step.y, reached: i + 1 };
    }
    const last = steps[steps.length - 1];
    return { x: last.x, y: last.y, reached: steps.length };
  }, [steps, elapsed]);

  const gazeScreen = toScreenCoords({ x: gaze.x, y: gaze.y }, fit);
  const visible = steps.slice(0, gaze.reached);

  const trail = visible
    .map((s, i) => {
      const p = toScreenCoords({ x: s.x, y: s.y }, fit);
      return `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`;
    })
    .join(" ");

  const download = async (format: "gif" | "mp4") => {
    setDownloading(format);
    try {
      const response = await api.get(`/results/${assetId}/scanpath.${format}`, {
        responseType: "blob",
      });
      const url = URL.createObjectURL(response.data as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `designeye-scanpath-${filename.replace(/\.[^.]+$/, "")}.${format}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success(`Saved as ${format.toUpperCase()}.`);
    } catch (error) {
      const status = (error as { response?: { status?: number } })?.response?.status;
      toast.error(
        status === 503
          ? "Video export isn't available on this server. Download the GIF instead."
          : `Could not create the ${format.toUpperCase()}.`,
      );
    } finally {
      setDownloading(null);
    }
  };

  if (steps.length === 0) {
    return (
      <div className="rounded-[1.25rem] bg-[var(--color-shell)] p-10 text-center">
        <p className="text-[14px] text-[var(--color-muted)]">
          This analysis has no viewing order to play back.
        </p>
      </div>
    );
  }

  const progress = Math.min(100, (elapsed / runtime) * 100);
  const currentRank = visible.length > 0 ? visible[visible.length - 1].rank : 0;

  return (
    <div className={cn("space-y-4", className)}>
      <div
        ref={stageRef}
        className="relative h-[26rem] w-full overflow-hidden rounded-[1.25rem] bg-[var(--color-shell)] sm:h-[30rem]"
      >
        {/* eslint-disable-next-line @next/next/no-img-element -- external CDN host, sized by the fit helper */}
        <img
          src={mockupUrl}
          alt=""
          className="pointer-events-none absolute select-none"
          style={{
            left: fit.offsetX,
            top: fit.offsetY,
            width: fit.drawWidth,
            height: fit.drawHeight,
            filter: "brightness(0.5)",
          }}
        />

        {/* A soft bright circle marks where the eye is looking right now. */}
        <div
          className="pointer-events-none absolute transition-none"
          style={{
            left: fit.offsetX,
            top: fit.offsetY,
            width: fit.drawWidth,
            height: fit.drawHeight,
            backgroundImage: `url(${mockupUrl})`,
            backgroundSize: `${fit.drawWidth}px ${fit.drawHeight}px`,
            WebkitMaskImage: `radial-gradient(circle 110px at ${gazeScreen.x - fit.offsetX}px ${gazeScreen.y - fit.offsetY}px, #000 35%, transparent 72%)`,
            maskImage: `radial-gradient(circle 110px at ${gazeScreen.x - fit.offsetX}px ${gazeScreen.y - fit.offsetY}px, #000 35%, transparent 72%)`,
          }}
        />

        <svg className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden>
          {trail ? (
            <path
              d={trail}
              fill="none"
              stroke="#4f5bd5"
              strokeWidth={2.5}
              strokeLinecap="round"
              opacity={0.75}
            />
          ) : null}
          {visible.length > 0 ? (
            <line
              x1={toScreenCoords({ x: visible[visible.length - 1].x, y: visible[visible.length - 1].y }, fit).x}
              y1={toScreenCoords({ x: visible[visible.length - 1].x, y: visible[visible.length - 1].y }, fit).y}
              x2={gazeScreen.x}
              y2={gazeScreen.y}
              stroke="#4f5bd5"
              strokeWidth={2}
              strokeDasharray="6 6"
              opacity={0.6}
            />
          ) : null}
        </svg>

        <AnimatePresence>
          {visible.map((step, i) => {
            const p = toScreenCoords({ x: step.x, y: step.y }, fit);
            return (
              <motion.span
                key={step.rank}
                className={cn(
                  "pointer-events-none absolute flex h-8 w-8 -translate-x-1/2 -translate-y-1/2",
                  "items-center justify-center rounded-full font-mono text-[12px] font-bold",
                  "text-white ring-2 ring-white/85 shadow-lg",
                  i === 0 ? "bg-violet-600" : "bg-indigo-600",
                )}
                style={{ left: p.x, top: p.y }}
                initial={{ scale: 0, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={{ type: "spring", stiffness: 520, damping: 22 }}
              >
                {step.rank}
              </motion.span>
            );
          })}
        </AnimatePresence>

        {/* The travelling marker. */}
        <span
          className="pointer-events-none absolute -translate-x-1/2 -translate-y-1/2"
          style={{ left: gazeScreen.x, top: gazeScreen.y }}
        >
          <span className="block h-12 w-12 rounded-full border-[3px] border-red-500/90" />
          <span className="absolute left-1/2 top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-red-500" />
        </span>

        <span className="tabular absolute bottom-3 right-3 rounded-lg bg-[var(--color-surface)]/90 px-2.5 py-1.5 text-[11px] text-[var(--color-muted)] ring-1 ring-[var(--color-hairline)] backdrop-blur-xl">
          {(elapsed / 1000).toFixed(1)}s / {(runtime / 1000).toFixed(1)}s
          {currentRank > 0 ? ` · stop ${currentRank} of ${steps.length}` : ""}
        </span>
      </div>

      {/* progress */}
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-shell)]">
        <div
          className="h-full rounded-full bg-gradient-to-r from-indigo-600 to-violet-600"
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* controls */}
      <div className="flex flex-wrap items-center gap-3">
        <Button size="sm" variant="primary" onClick={() => setPlaying((v) => !v)}>
          {playing ? (
            <>
              <Pause size={14} strokeWidth={1.5} />
              Pause
            </>
          ) : (
            <>
              <Play size={14} strokeWidth={1.5} />
              Play
            </>
          )}
        </Button>

        <Button size="sm" variant="outline" onClick={replay}>
          <RotateCcw size={14} strokeWidth={1.5} />
          Start again
        </Button>

        <div className="flex rounded-full bg-[var(--color-shell)] p-1">
          {SPEEDS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setSpeed(s)}
              className={cn(
                "rounded-full px-3 py-1 text-[12px] font-medium",
                "transition-all duration-400 ease-[cubic-bezier(0.32,0.72,0,1)]",
                speed === s
                  ? "bg-[var(--color-surface)] text-[var(--color-ink)] shadow-[var(--shadow-ambient)]"
                  : "text-[var(--color-muted)] hover:text-[var(--color-ink)]",
              )}
            >
              {s}×
            </button>
          ))}
        </div>

        <div className="ml-auto flex gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={downloading !== null}
            onClick={() => download("gif")}
          >
            <Download size={13} strokeWidth={1.5} />
            {downloading === "gif" ? "Saving…" : "GIF"}
          </Button>
          <Button
            size="sm"
            variant="navy"
            disabled={downloading !== null}
            onClick={() => download("mp4")}
          >
            <Download size={13} strokeWidth={1.5} />
            {downloading === "mp4" ? "Saving…" : "Video"}
          </Button>
        </div>
      </div>

      {/* The honest bit, in plain words. */}
      <div className="flex items-start gap-2.5 rounded-xl bg-[var(--color-surface-2)] p-4 ring-1 ring-[var(--color-hairline)]">
        <Info
          size={15}
          strokeWidth={1.5}
          className="mt-0.5 shrink-0 text-[var(--color-faint)]"
        />
        <p className="text-[12.5px] leading-relaxed text-[var(--color-muted)]">
          This is a <span className="font-medium text-[var(--color-ink)]">simulation</span>,
          not a recording. DesignEye predicts <em>where</em> people are most likely to
          look, then plays those spots back strongest-first, using pause lengths taken
          from published eye-tracking research. Real viewers won&apos;t follow this exact
          route — treat it as a guide to what stands out, not a prediction of the order
          someone will look in.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="violet">{steps.length} points</Badge>
        <Badge tone="neutral">{(totalMs / 1000).toFixed(1)}s sequence</Badge>
        <Badge tone="indigo">Strongest first</Badge>
      </div>
    </div>
  );
}
