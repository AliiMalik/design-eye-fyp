"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Maximize2, Minus, Plus, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { computeFit, focusPath, toScreenCoords, type ImageFit } from "@/lib/coords";
import { cn } from "@/lib/utils";
import type { FocusNode } from "@/types/api";

export type ViewMode = "original" | "heatmap" | "focus" | "both";

const EASE = [0.32, 0.72, 0, 1] as const;
const MIN_ZOOM = 1;
const MAX_ZOOM = 5;

interface Transform {
  zoom: number;
  panX: number;
  panY: number;
}

const IDENTITY: Transform = { zoom: 1, panX: 0, panY: 0 };

export interface HeatmapViewerProps {
  mockupUrl: string;
  heatmapUrl: string;
  imageWidth: number;
  imageHeight: number;
  focusNodes: FocusNode[];
  mode: ViewMode;
  opacity: number;
  className?: string;
  /** Broadcast transform changes so an A/B pair can stay in sync. */
  onTransformChange?: (t: Transform) => void;
  /** Drive the transform externally (synchronised scroll and zoom). */
  externalTransform?: Transform | null;
}

export function HeatmapViewer({
  mockupUrl,
  heatmapUrl,
  imageWidth,
  imageHeight,
  focusNodes,
  mode,
  opacity,
  className,
  onTransformChange,
  externalTransform,
}: HeatmapViewerProps) {
  const stageRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [transform, setTransform] = useState<Transform>(IDENTITY);
  const [loaded, setLoaded] = useState(false);
  const imagesRef = useRef<{ base?: HTMLImageElement; heat?: HTMLImageElement }>({});
  const dragRef = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null);

  const active = externalTransform ?? transform;

  const applyTransform = useCallback(
    (next: Transform) => {
      setTransform(next);
      onTransformChange?.(next);
    },
    [onTransformChange],
  );

  // --- track stage size ---------------------------------------------------
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

  // --- load both bitmaps once --------------------------------------------
  useEffect(() => {
    let cancelled = false;
    setLoaded(false);

    const load = (src: string) =>
      new Promise<HTMLImageElement>((resolve, reject) => {
        const img = new window.Image();
        img.crossOrigin = "anonymous";
        img.onload = () => resolve(img);
        img.onerror = reject;
        img.src = src;
      });

    Promise.all([load(mockupUrl), load(heatmapUrl)])
      .then(([base, heat]) => {
        if (cancelled) return;
        imagesRef.current = { base, heat };
        setLoaded(true);
      })
      .catch(() => {
        if (!cancelled) setLoaded(false);
      });

    return () => {
      cancelled = true;
    };
  }, [mockupUrl, heatmapUrl]);

  // --- paint --------------------------------------------------------------
  useEffect(() => {
    const canvas = canvasRef.current;
    const { base, heat } = imagesRef.current;
    if (!canvas || !loaded || !base || fit.drawWidth === 0) return;

    // Canvas is chosen over CSS layering for pixel-accurate compositing (SDS).
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(size.width * dpr);
    canvas.height = Math.round(size.height * dpr);
    canvas.style.width = `${size.width}px`;
    canvas.style.height = `${size.height}px`;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, size.width, size.height);
    ctx.imageSmoothingQuality = "high";

    ctx.drawImage(base, fit.offsetX, fit.offsetY, fit.drawWidth, fit.drawHeight);

    if ((mode === "heatmap" || mode === "both") && heat) {
      ctx.globalAlpha = opacity;
      ctx.drawImage(heat, fit.offsetX, fit.offsetY, fit.drawWidth, fit.drawHeight);
      ctx.globalAlpha = 1;
    }
  }, [loaded, fit, size.width, size.height, mode, opacity]);

  // --- zoom & pan ---------------------------------------------------------
  const zoomBy = (delta: number) => {
    const zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, active.zoom + delta));
    applyTransform(
      zoom === MIN_ZOOM ? IDENTITY : { ...active, zoom },
    );
  };

  const onWheel = (e: React.WheelEvent) => {
    if (!e.ctrlKey && !e.metaKey) return; // plain scroll still scrolls the page
    e.preventDefault();
    zoomBy(e.deltaY > 0 ? -0.25 : 0.25);
  };

  const onPointerDown = (e: React.PointerEvent) => {
    if (active.zoom <= 1) return;
    (e.target as Element).setPointerCapture(e.pointerId);
    dragRef.current = { x: e.clientX, y: e.clientY, panX: active.panX, panY: active.panY };
  };

  const onPointerMove = (e: React.PointerEvent) => {
    const drag = dragRef.current;
    if (!drag) return;
    applyTransform({
      ...active,
      panX: drag.panX + (e.clientX - drag.x),
      panY: drag.panY + (e.clientY - drag.y),
    });
  };

  const endDrag = () => {
    dragRef.current = null;
  };

  const showFocus = mode === "focus" || mode === "both";
  const nodePoints = focusNodes.map((n) => ({ x: n.x, y: n.y }));

  return (
    <div className={cn("relative", className)}>
      <div
        ref={stageRef}
        onWheel={onWheel}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        className={cn(
          "relative h-full w-full overflow-hidden rounded-[1.25rem] bg-[var(--color-shell)]",
          active.zoom > 1 ? "cursor-grab active:cursor-grabbing" : "cursor-default",
        )}
        style={{ touchAction: active.zoom > 1 ? "none" : "auto" }}
      >
        <div
          className="absolute inset-0 origin-center transition-transform duration-300 ease-[cubic-bezier(0.32,0.72,0,1)]"
          style={{
            transform: `translate3d(${active.panX}px, ${active.panY}px, 0) scale(${active.zoom})`,
          }}
        >
          <canvas ref={canvasRef} className="absolute inset-0" />

          {/* Focus layer: absolutely positioned SVG above the canvas. */}
          <svg
            className="pointer-events-none absolute inset-0"
            width={size.width}
            height={size.height}
            aria-hidden
          >
            <AnimatePresence>
              {showFocus && focusNodes.length > 1 ? (
                <motion.path
                  key="gaze-path"
                  d={focusPath(nodePoints, fit)}
                  fill="none"
                  stroke="#7c3aed"
                  strokeWidth={2.5}
                  strokeDasharray="9 7"
                  strokeLinecap="round"
                  initial={{ pathLength: 0, opacity: 0 }}
                  animate={{ pathLength: 1, opacity: 0.9 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 1.1, ease: EASE }}
                />
              ) : null}
            </AnimatePresence>
          </svg>

          <AnimatePresence>
            {showFocus
              ? focusNodes.map((node, i) => {
                  const p = toScreenCoords({ x: node.x, y: node.y }, fit);
                  return (
                    <motion.div
                      key={node.rank}
                      className="pointer-events-none absolute"
                      style={{ left: p.x, top: p.y }}
                      initial={{ scale: 0, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      exit={{ scale: 0, opacity: 0 }}
                      transition={{
                        type: "spring",
                        stiffness: 500,
                        damping: 22,
                        delay: i * 0.12,
                      }}
                    >
                      <span
                        className={cn(
                          "-ml-[15px] -mt-[15px] flex h-[30px] w-[30px] items-center justify-center",
                          "rounded-full font-mono text-[12px] font-bold text-white",
                          "shadow-lg ring-2 ring-white/85",
                          node.rank === 1 ? "bg-violet-600" : "bg-indigo-600",
                        )}
                        style={{ transform: `scale(${1 / active.zoom})` }}
                      >
                        {node.rank}
                      </span>
                    </motion.div>
                  );
                })
              : null}
          </AnimatePresence>
        </div>

        {!loaded ? (
          <div className="absolute inset-0 animate-pulse bg-[var(--color-shell)]" />
        ) : null}
      </div>

      {/* zoom controls */}
      <div className="absolute bottom-4 left-4 flex flex-col overflow-hidden rounded-xl bg-[var(--color-surface)]/90 ring-1 ring-[var(--color-hairline)] backdrop-blur-xl">
        <button
          type="button"
          aria-label="Zoom in"
          onClick={() => zoomBy(0.5)}
          className="p-2.5 text-[var(--color-ink-2)] transition-colors hover:bg-[var(--color-shell)]"
        >
          <Plus size={15} strokeWidth={1.5} />
        </button>
        <button
          type="button"
          aria-label="Zoom out"
          onClick={() => zoomBy(-0.5)}
          className="border-t border-[var(--color-hairline)] p-2.5 text-[var(--color-ink-2)] transition-colors hover:bg-[var(--color-shell)]"
        >
          <Minus size={15} strokeWidth={1.5} />
        </button>
        <button
          type="button"
          aria-label="Reset view"
          onClick={() => applyTransform(IDENTITY)}
          className="border-t border-[var(--color-hairline)] p-2.5 text-[var(--color-ink-2)] transition-colors hover:bg-[var(--color-shell)]"
        >
          <RotateCcw size={15} strokeWidth={1.5} />
        </button>
      </div>

      <span className="tabular absolute bottom-4 right-4 rounded-lg bg-[var(--color-surface)]/90 px-2.5 py-1.5 text-[11px] text-[var(--color-muted)] ring-1 ring-[var(--color-hairline)] backdrop-blur-xl">
        <Maximize2 size={11} strokeWidth={1.5} className="mr-1 inline" />
        {Math.round(active.zoom * 100)}%
      </span>
    </div>
  );
}
