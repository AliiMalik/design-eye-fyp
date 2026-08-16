"use client";

import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

import { cn } from "@/lib/utils";

/** The DesignEye eye mark from the Visily screens. */
export function Logo({
  className,
  size = 36,
  tone = "brand",
}: {
  className?: string;
  size?: number;
  tone?: "brand" | "light";
}) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-[0.7rem]",
        tone === "brand"
          ? "bg-navy-900 text-white"
          : "bg-white/12 text-white ring-1 ring-white/20",
        className,
      )}
      style={{ width: size, height: size }}
      aria-hidden
    >
      <svg
        width={size * 0.55}
        height={size * 0.55}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.6}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M1.5 12S5.2 5.5 12 5.5 22.5 12 22.5 12 18.8 18.5 12 18.5 1.5 12 1.5 12Z" />
        <circle cx="12" cy="12" r="3.1" fill="currentColor" stroke="none" />
      </svg>
    </span>
  );
}

export function Wordmark({
  className,
  onDark = false,
}: {
  className?: string;
  onDark?: boolean;
}) {
  return (
    <span
      className={cn(
        "font-display text-[19px] font-bold tracking-tight",
        onDark ? "text-white" : "text-[var(--color-ink)]",
        className,
      )}
    >
      Design<span className={onDark ? "text-indigo-300" : "text-indigo-600"}>Eye</span>
    </span>
  );
}

export function ThemeToggle({ className }: { className?: string }) {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const isDark = resolvedTheme === "dark";

  return (
    <button
      type="button"
      aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
      onClick={() => setTheme(isDark ? "light" : "dark")}
      className={cn(
        "relative inline-flex h-9 w-9 items-center justify-center rounded-full",
        "ring-1 ring-[var(--color-hairline-strong)] text-[var(--color-ink-2)]",
        "transition-all duration-500 ease-[cubic-bezier(0.32,0.72,0,1)]",
        "hover:bg-[var(--color-shell)] active:scale-95",
        className,
      )}
    >
      {mounted ? (
        isDark ? (
          <Sun size={16} strokeWidth={1.5} />
        ) : (
          <Moon size={16} strokeWidth={1.5} />
        )
      ) : (
        <span className="h-4 w-4" />
      )}
    </button>
  );
}
