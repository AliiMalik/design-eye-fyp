"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import Image from "next/image";
import { useEffect, useState } from "react";

import demo from "@/lib/demo-data.json";
import { clarityBand, cn } from "@/lib/utils";

const EASE = [0.32, 0.72, 0, 1] as const;
const NODES = demo.focus_nodes;

/** Cycles through the real product output: mockup -> heatmap -> focus order. */
export function HeroDemo() {
  const reduced = useReducedMotion();
  const [phase, setPhase] = useState(0); // 0 mockup, 1 heatmap, 2 focus order

  useEffect(() => {
    if (reduced) {
      setPhase(2);
      return;
    }
    const timings = [1400, 2600, 4200];
    const id = window.setTimeout(
      () => setPhase((p) => (p + 1) % 3),
      timings[phase],
    );
    return () => window.clearTimeout(id);
  }, [phase, reduced]);

  const pathD = NODES.map((n, i) => `${i === 0 ? "M" : "L"} ${n.x} ${n.y}`).join(" ");

  return (
    <div className="relative">
      {/* Outer shell / inner core: the demo sits in a machined tray. */}
      <div className="rounded-[2rem] bg-[var(--color-shell)] p-1.5 ring-1 ring-[var(--color-hairline)] shadow-[var(--shadow-lifted)]">
        <div className="inner-lip overflow-hidden rounded-[calc(2rem-0.375rem)] bg-[var(--color-surface)] ring-1 ring-[var(--color-hairline)]">
          {/* window chrome */}
          <div className="flex items-center gap-2 border-b border-[var(--color-hairline)] px-4 py-3">
            <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" />
            <span className="h-2.5 w-2.5 rounded-full bg-[#febc2e]" />
            <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]" />
            <span className="ml-3 truncate font-mono text-[11px] text-[var(--color-faint)]">
              landing-hero-v2.png
            </span>
            <span className="ml-auto flex items-center gap-1.5">
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-70" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
              </span>
              <span className="font-mono text-[10px] uppercase tracking-widest text-[var(--color-faint)]">
                {phase === 0 ? "Mockup" : phase === 1 ? "Saliency" : "Focus order"}
              </span>
            </span>
          </div>

          <div
            className="relative w-full"
            style={{ aspectRatio: `${demo.width} / ${demo.height}` }}
          >
            <Image
              src={demo.mockup_src}
              alt="UI mockup being analysed"
              fill
              priority
              sizes="(max-width: 1024px) 100vw, 620px"
              className="object-cover"
            />

            {/* Heatmap wipes in behind a mask rather than cross-fading flatly. */}
            <AnimatePresence>
              {phase >= 1 ? (
                <motion.div
                  className="absolute inset-0"
                  initial={{ opacity: 0, clipPath: "inset(0 100% 0 0)" }}
                  animate={{ opacity: 1, clipPath: "inset(0 0% 0 0)" }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.9, ease: EASE }}
                >
                  <Image
                    src={demo.heatmap_src}
                    alt="Predicted attention heatmap"
                    fill
                    sizes="(max-width: 1024px) 100vw, 620px"
                    className="object-cover"
                  />
                </motion.div>
              ) : null}
            </AnimatePresence>

            {/* Focus nodes + gaze path in one shared coordinate space. */}
            <svg
              viewBox={`0 0 ${demo.width} ${demo.height}`}
              className="absolute inset-0 h-full w-full"
              preserveAspectRatio="none"
              aria-hidden
            >
              <AnimatePresence>
                {phase === 2 ? (
                  <motion.path
                    d={pathD}
                    fill="none"
                    stroke="#7c3aed"
                    strokeWidth={3}
                    strokeDasharray="10 8"
                    strokeLinecap="round"
                    vectorEffect="non-scaling-stroke"
                    initial={{ pathLength: 0, opacity: 0 }}
                    animate={{ pathLength: 1, opacity: 0.9 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 1.1, ease: EASE }}
                  />
                ) : null}
              </AnimatePresence>
            </svg>

            <AnimatePresence>
              {phase === 2
                ? NODES.map((node, i) => (
                    <motion.div
                      key={node.rank}
                      className="absolute"
                      style={{
                        left: `${(node.x / demo.width) * 100}%`,
                        top: `${(node.y / demo.height) * 100}%`,
                      }}
                      initial={{ scale: 0, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      exit={{ scale: 0, opacity: 0 }}
                      transition={{
                        type: "spring",
                        stiffness: 520,
                        damping: 20,
                        delay: i * 0.14,
                      }}
                    >
                      <span
                        className={cn(
                          "-ml-4 -mt-4 flex h-8 w-8 items-center justify-center rounded-full",
                          "font-mono text-[12px] font-bold text-white shadow-lg ring-2 ring-white/80",
                          i === 0 ? "bg-violet-600" : "bg-indigo-600",
                        )}
                      >
                        {node.rank}
                      </span>
                    </motion.div>
                  ))
                : null}
            </AnimatePresence>
          </div>
        </div>
      </div>

      {/* Floating score readout, offset off the tray edge. */}
      <motion.div
        initial={{ opacity: 0, y: 20, filter: "blur(8px)" }}
        animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
        transition={{ duration: 0.9, delay: 0.5, ease: EASE }}
        className={cn(
          "absolute -bottom-6 -left-4 flex items-center gap-3 rounded-2xl px-4 py-3 sm:-left-8",
          "bg-[var(--color-surface)]/90 backdrop-blur-xl",
          "ring-1 ring-[var(--color-hairline)] shadow-[var(--shadow-lifted)]",
        )}
      >
        <div
          className="flex h-11 w-11 items-center justify-center rounded-xl"
          style={{ backgroundColor: `${clarityBand(demo.clarity_score).hex}1a` }}
        >
          <span
            className="tabular text-[15px] font-bold"
            style={{ color: clarityBand(demo.clarity_score).hex }}
          >
            {Math.round(demo.clarity_score)}
          </span>
        </div>
        <div className="leading-tight">
          <p className="text-[11px] uppercase tracking-[0.16em] text-[var(--color-faint)]">
            Clarity Score
          </p>
          <p className="text-[13px] font-medium text-[var(--color-ink)]">
            {clarityBand(demo.clarity_score).label} hierarchy
          </p>
        </div>
      </motion.div>
    </div>
  );
}
