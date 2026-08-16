import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Double-Bezel (Doppelrand) enclosure.
 *
 * Nothing premium sits flat on the background: an outer shell holds an inner
 * core, with concentric radii so the curves stay parallel like machined
 * hardware. Outer radius 2rem, shell padding 0.375rem, inner radius therefore
 * calc(2rem - 0.375rem).
 */
interface BezelProps extends React.HTMLAttributes<HTMLDivElement> {
  innerClassName?: string;
  as?: "div" | "section" | "article" | "aside";
}

export function Bezel({
  className,
  innerClassName,
  children,
  as: Tag = "div",
  ...props
}: BezelProps) {
  return (
    <Tag
      className={cn(
        "rounded-[2rem] bg-[var(--color-shell)] p-1.5",
        "ring-1 ring-[var(--color-hairline)]",
        className,
      )}
      {...props}
    >
      <div
        className={cn(
          "inner-lip h-full rounded-[calc(2rem-0.375rem)] bg-[var(--color-surface)]",
          "ring-1 ring-[var(--color-hairline)]",
          innerClassName,
        )}
      >
        {children}
      </div>
    </Tag>
  );
}

/** Smaller sibling for list rows and compact tiles. */
export function BezelSm({
  className,
  innerClassName,
  children,
  ...props
}: BezelProps) {
  return (
    <div
      className={cn(
        "rounded-[1.25rem] bg-[var(--color-shell)] p-1 ring-1 ring-[var(--color-hairline)]",
        className,
      )}
      {...props}
    >
      <div
        className={cn(
          "inner-lip h-full rounded-[calc(1.25rem-0.25rem)] bg-[var(--color-surface)]",
          "ring-1 ring-[var(--color-hairline)]",
          innerClassName,
        )}
      >
        {children}
      </div>
    </div>
  );
}
