"use client";

import { animate, motion, useMotionValue, useTransform } from "framer-motion";
import { useEffect } from "react";

import { clarityBand, cn } from "@/lib/utils";

/** Animated radial gauge; the number counts up as the arc sweeps. */
export function ClarityGauge({
  score,
  size = 168,
  stroke = 12,
  label = "Clarity Score",
  className,
}: {
  score: number;
  size?: number;
  stroke?: number;
  label?: string;
  className?: string;
}) {
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const band = clarityBand(score);

  const progress = useMotionValue(0);
  const dashOffset = useTransform(
    progress,
    (v) => circumference - (v / 100) * circumference,
  );
  const display = useTransform(progress, (v) => v.toFixed(1));

  useEffect(() => {
    const controls = animate(progress, score, {
      duration: 1.4,
      ease: [0.32, 0.72, 0, 1],
    });
    return () => controls.stop();
  }, [score, progress]);

  return (
    <div className={cn("relative inline-flex items-center justify-center", className)}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={stroke}
          className="stroke-[var(--color-shell)]"
        />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={stroke}
          strokeLinecap="round"
          stroke={band.hex}
          strokeDasharray={circumference}
          style={{ strokeDashoffset: dashOffset }}
        />
      </svg>

      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <motion.span
          className="tabular font-display font-bold leading-none"
          style={{ fontSize: size * 0.26, color: band.hex }}
        >
          {display}
        </motion.span>
        <span className="mt-1 text-[10px] uppercase tracking-[0.16em] text-[var(--color-faint)]">
          / 100
        </span>
      </div>

      <span className="sr-only">
        {label}: {score} out of 100 ({band.label})
      </span>
    </div>
  );
}

/** Compact horizontal readout for tables and cards. */
export function ClarityPill({ score }: { score: number | null }) {
  if (score === null || score === undefined) {
    return <span className="tabular text-[13px] text-[var(--color-faint)]">—</span>;
  }
  const band = clarityBand(score);
  return (
    <div className="flex items-center gap-2.5">
      <span className="tabular text-[15px] font-bold" style={{ color: band.hex }}>
        {score.toFixed(1)}
      </span>
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-[var(--color-shell)]">
        <div
          className="h-full rounded-full transition-[width] duration-700 ease-[cubic-bezier(0.32,0.72,0,1)]"
          style={{ width: `${Math.max(2, score)}%`, backgroundColor: band.hex }}
        />
      </div>
    </div>
  );
}
