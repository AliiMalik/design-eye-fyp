"use client";

import Image, { type StaticImageData } from "next/image";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

import markCompactDark from "@/assets/brand/mark-compact-dark.png";
import markCompactLight from "@/assets/brand/mark-compact-light.png";
import markDark from "@/assets/brand/mark-dark.png";
import markLight from "@/assets/brand/mark-light.png";
import { cn } from "@/lib/utils";

const ART: Record<"full" | "compact", Record<"light" | "dark", StaticImageData>> = {
  full: { light: markLight, dark: markDark },
  compact: { light: markCompactLight, dark: markCompactDark },
};

/**
 * The DesignEye mark: saliency contours closing on a bright pupil.
 *
 * `size` is the rendered height. The artwork is wider than it is tall, so the
 * width follows from it rather than being passed in.
 *
 * There are two artworks because the mark has a dark pupil, which disappears on
 * anything dark. `tone="light"` means "this chrome is dark whatever the theme"
 * — the app sidebar is navy in both — so it pins the dark artwork instead of
 * following next-themes. Everywhere else swaps in CSS, which keeps the choice
 * out of hydration's way.
 *
 * `variant="compact"` drops the two outer rings: five strokes need about 3px
 * each to stay separate, so the full mark only holds together above ~48px.
 * Regenerate all of it with `python scripts/build_brand_assets.py`.
 */
export function Logo({
  className,
  size = 26,
  tone = "brand",
  variant = "compact",
}: {
  className?: string;
  size?: number;
  tone?: "brand" | "light";
  variant?: "full" | "compact";
}) {
  const art = ART[variant];
  const box = { height: size, width: "auto" } as const;

  // eager, not `priority`: which artwork is visible is decided in CSS, so
  // `priority` preloads both and the browser reports the hidden one as an
  // unused preload on every page. Plain lazy is worse -- the logo is above the
  // fold, and it would hold the nav blank until the observer fires.
  const load = { loading: "eager" } as const;

  if (tone === "light") {
    return <Image src={art.dark} alt="" {...load} style={box} className={cn("shrink-0", className)} />;
  }

  return (
    <span className={cn("inline-flex shrink-0 items-center", className)}>
      <Image src={art.light} alt="" {...load} style={box} className="dark:hidden" />
      <Image src={art.dark} alt="" {...load} style={box} className="hidden dark:block" />
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
