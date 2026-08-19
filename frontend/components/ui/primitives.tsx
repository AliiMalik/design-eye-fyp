"use client";

import { motion, type Variants } from "framer-motion";
import * as React from "react";

import { cn } from "@/lib/utils";

/** Microscopic pill that precedes a major heading. */
export function Eyebrow({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-3 py-1",
        "text-[10px] font-medium uppercase tracking-[0.2em]",
        "bg-indigo-50 text-indigo-700 ring-1 ring-indigo-200/70",
        "dark:bg-indigo-500/10 dark:text-indigo-300 dark:ring-indigo-400/20",
        className,
      )}
    >
      {children}
    </span>
  );
}

const EASE = [0.32, 0.72, 0, 1] as const;

/**
 * Scroll entry: a heavy fade-up that resolves out of a blur. Elements never
 * appear statically. Uses whileInView (IntersectionObserver under the hood) --
 * never a scroll listener, which would reflow continuously.
 *
 * Reduced motion is handled globally by MotionConfig in providers.tsx, NOT by
 * branching here: useReducedMotion() disagrees between server and client, and
 * swapping the element type on that value strands content at opacity 0.
 */
export function Reveal({
  children,
  delay = 0,
  y = 44,
  className,
  once = true,
}: {
  children: React.ReactNode;
  delay?: number;
  y?: number;
  className?: string;
  once?: boolean;
}) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y, filter: "blur(10px)" }}
      whileInView={{ opacity: 1, y: 0, filter: "blur(0px)" }}
      viewport={{ once, margin: "-80px" }}
      transition={{ duration: 0.85, delay, ease: EASE }}
    >
      {children}
    </motion.div>
  );
}

/** Staggered container for lists of Reveal-like children. */
export const staggerParent: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.07, delayChildren: 0.05 } },
};

export const staggerChild: Variants = {
  hidden: { opacity: 0, y: 26, filter: "blur(8px)" },
  show: {
    opacity: 1,
    y: 0,
    filter: "blur(0px)",
    transition: { duration: 0.7, ease: EASE },
  },
};

export function Stagger({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <motion.div
      className={className}
      variants={staggerParent}
      initial="hidden"
      whileInView="show"
      viewport={{ once: true, margin: "-60px" }}
    >
      {children}
    </motion.div>
  );
}

export function StaggerItem({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <motion.div className={className} variants={staggerChild}>
      {children}
    </motion.div>
  );
}

// --- badge -----------------------------------------------------------------
const badgeTone = {
  neutral: "bg-[var(--color-shell)] text-[var(--color-muted)] ring-[var(--color-hairline)]",
  success: "bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-400/20",
  warning: "bg-amber-50 text-amber-700 ring-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-400/20",
  danger: "bg-red-50 text-red-700 ring-red-200 dark:bg-red-500/10 dark:text-red-300 dark:ring-red-400/20",
  indigo: "bg-indigo-50 text-indigo-700 ring-indigo-200 dark:bg-indigo-500/10 dark:text-indigo-300 dark:ring-indigo-400/20",
  violet: "bg-violet-50 text-violet-700 ring-violet-200 dark:bg-violet-500/10 dark:text-violet-300 dark:ring-violet-400/20",
} as const;

export function Badge({
  tone = "neutral",
  className,
  children,
}: {
  tone?: keyof typeof badgeTone;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1",
        "text-[11px] font-medium ring-1",
        badgeTone[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

// --- skeleton (never a spinner) -------------------------------------------
export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-xl bg-[var(--color-shell)]",
        "after:absolute after:inset-0 after:-translate-x-full",
        "after:bg-gradient-to-r after:from-transparent after:via-white/45 after:to-transparent",
        "after:animate-[shimmer_1.8s_infinite] dark:after:via-white/6",
        className,
      )}
    />
  );
}

// --- inputs ----------------------------------------------------------------
/**
 * Ties a Field's label and error message to whichever control it wraps.
 *
 * Context rather than cloneElement, because the control is not always the
 * direct child -- the password fields nest an input beside a show/hide button,
 * and cloning would put the id on the wrapper div instead.
 */
const FieldContext = React.createContext<{
  id?: string;
  describedBy?: string;
  invalid?: boolean;
}>({});

function useFieldProps(props: {
  id?: string;
  "aria-describedby"?: string;
  "aria-invalid"?: React.AriaAttributes["aria-invalid"];
}) {
  const field = React.useContext(FieldContext);
  return {
    id: props.id ?? field.id,
    "aria-describedby": props["aria-describedby"] ?? field.describedBy,
    "aria-invalid": props["aria-invalid"] ?? (field.invalid ? true : undefined),
  };
}

export const Input = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(({ className, ...props }, ref) => (
  <input
    ref={ref}
    className={cn(
      "h-12 w-full rounded-xl bg-[var(--color-surface-2)] px-4 text-sm",
      "text-[var(--color-ink)] placeholder:text-[var(--color-faint)]",
      "ring-1 ring-[var(--color-hairline)] transition-all duration-300",
      "ease-[cubic-bezier(0.32,0.72,0,1)]",
      "focus:bg-[var(--color-surface)] focus:outline-none focus:ring-2 focus:ring-indigo-500",
      "disabled:opacity-60",
      className,
    )}
    {...props}
    {...useFieldProps(props)}
  />
));
Input.displayName = "Input";

export const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea
    ref={ref}
    className={cn(
      "w-full rounded-xl bg-[var(--color-surface-2)] px-4 py-3 text-sm",
      "text-[var(--color-ink)] placeholder:text-[var(--color-faint)]",
      "ring-1 ring-[var(--color-hairline)] transition-all duration-300",
      "focus:bg-[var(--color-surface)] focus:outline-none focus:ring-2 focus:ring-indigo-500",
      className,
    )}
    {...props}
    {...useFieldProps(props)}
  />
));
Textarea.displayName = "Textarea";

export function Field({
  label,
  hint,
  error,
  children,
  className,
}: {
  label: string;
  hint?: React.ReactNode;
  error?: string;
  children: React.ReactNode;
  className?: string;
}) {
  // The label was previously rendered without htmlFor and the control arrives as
  // children, so every form in the app was announced as an unnamed edit box.
  // One id, generated here, wires the label, the error text and the control.
  const id = React.useId();
  const errorId = `${id}-error`;

  return (
    <FieldContext.Provider
      value={{ id, describedBy: error ? errorId : undefined, invalid: Boolean(error) }}
    >
      <div className={cn("space-y-2", className)}>
        <div className="flex items-baseline justify-between gap-3">
          <label
            htmlFor={id}
            className="text-[13px] font-medium text-[var(--color-ink)]"
          >
            {label}
          </label>
          {hint}
        </div>
        {children}
        {/* role="alert" so a validation failure is announced, not just shown. */}
        {error ? (
          <p id={errorId} role="alert" className="text-xs text-red-500">
            {error}
          </p>
        ) : null}
      </div>
    </FieldContext.Provider>
  );
}
