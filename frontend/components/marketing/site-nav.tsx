"use client";

import { AnimatePresence, motion } from "framer-motion";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Logo, ThemeToggle, Wordmark } from "@/components/brand";
import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/lib/auth-store";
import { cn } from "@/lib/utils";

const LINKS = [
  { href: "#capabilities", label: "Features" },
  { href: "#flow", label: "How it works" },
  { href: "#proof", label: "Accuracy" },
];

const EASE = [0.32, 0.72, 0, 1] as const;

/** Floating glass island, detached from the top edge. Never glued edge-to-edge. */
export function SiteNav() {
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const accessToken = useAuthStore((s) => s.accessToken);
  const hydrated = useAuthStore((s) => s.hydrated);

  useEffect(() => {
    // Passive + rAF-free: a single boolean flip, no layout reads per frame.
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  const signedIn = hydrated && Boolean(accessToken);

  return (
    <>
      <header className="pointer-events-none fixed inset-x-0 top-0 z-40 flex justify-center px-4 pt-6">
        <nav
          className={cn(
            "pointer-events-auto flex w-full max-w-[62rem] items-center gap-2 rounded-full",
            "px-3 py-2 backdrop-blur-2xl transition-all duration-700",
            "ease-[cubic-bezier(0.32,0.72,0,1)]",
            scrolled
              ? "bg-[var(--color-surface)]/80 shadow-[var(--shadow-lifted)] ring-1 ring-[var(--color-hairline)]"
              : "bg-[var(--color-surface)]/45 ring-1 ring-[var(--color-hairline)]",
          )}
        >
          <Link href="/" className="flex items-center gap-2.5 pl-1">
            <Logo size={26} />
            <Wordmark />
          </Link>

          <div className="ml-4 hidden items-center gap-1 md:flex">
            {LINKS.map((l) => (
              <a
                key={l.href}
                href={l.href}
                className={cn(
                  "rounded-full px-3.5 py-2 text-[13px] text-[var(--color-ink-2)]",
                  "transition-colors duration-300 hover:bg-[var(--color-shell)]",
                )}
              >
                {l.label}
              </a>
            ))}
          </div>

          <div className="ml-auto flex items-center gap-2">
            <ThemeToggle className="hidden sm:inline-flex" />
            {signedIn ? (
              <Button asChild size="sm" variant="primary">
                <Link href="/dashboard">Dashboard</Link>
              </Button>
            ) : (
              <>
                <Link
                  href="/login"
                  className="hidden rounded-full px-3.5 py-2 text-[13px] text-[var(--color-ink-2)] transition-colors hover:bg-[var(--color-shell)] sm:block"
                >
                  Log in
                </Link>
                <Button asChild size="sm" variant="primary">
                  <Link href="/register">Get started</Link>
                </Button>
              </>
            )}

            <button
              type="button"
              aria-label={open ? "Close menu" : "Open menu"}
              aria-expanded={open}
              onClick={() => setOpen((v) => !v)}
              className="relative ml-1 flex h-9 w-9 items-center justify-center rounded-full ring-1 ring-[var(--color-hairline-strong)] md:hidden"
            >
              {/* Two bars that rotate into a true X, not a swap. */}
              <motion.span
                className="absolute h-[1.5px] w-4 rounded bg-[var(--color-ink)]"
                animate={open ? { rotate: 45, y: 0 } : { rotate: 0, y: -3.5 }}
                transition={{ duration: 0.5, ease: EASE }}
              />
              <motion.span
                className="absolute h-[1.5px] w-4 rounded bg-[var(--color-ink)]"
                animate={open ? { rotate: -45, y: 0 } : { rotate: 0, y: 3.5 }}
                transition={{ duration: 0.5, ease: EASE }}
              />
            </button>
          </div>
        </nav>
      </header>

      <AnimatePresence>
        {open ? (
          <motion.div
            className="fixed inset-0 z-30 flex flex-col justify-center gap-2 bg-[var(--color-canvas)]/85 px-8 backdrop-blur-3xl md:hidden"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.4, ease: EASE }}
          >
            {[...LINKS, { href: "/login", label: "Log in" }].map((l, i) => (
              <motion.a
                key={l.href}
                href={l.href}
                onClick={() => setOpen(false)}
                className="font-display text-4xl font-semibold tracking-tight text-[var(--color-ink)]"
                initial={{ opacity: 0, y: 48 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 24 }}
                transition={{ duration: 0.6, delay: 0.05 + i * 0.05, ease: EASE }}
              >
                {l.label}
              </motion.a>
            ))}
            <motion.div
              initial={{ opacity: 0, y: 48 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.28, ease: EASE }}
              className="mt-6 flex items-center gap-3"
            >
              <ThemeToggle />
              <span className="text-sm text-[var(--color-muted)]">Toggle theme</span>
            </motion.div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </>
  );
}
