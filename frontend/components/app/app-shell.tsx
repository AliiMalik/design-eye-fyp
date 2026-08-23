"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  GitCompareArrows,
  Layers,
  LayoutGrid,
  LogOut,
  Menu,
  Puzzle,
  Settings,
  UploadCloud,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Logo, ThemeToggle, Wordmark } from "@/components/brand";
import { api } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutGrid },
  { href: "/projects", label: "My Projects", icon: Layers },
  { href: "/upload", label: "Upload New", icon: UploadCloud },
  { href: "/compare", label: "A/B Compare", icon: GitCompareArrows },
  { href: "/extension", label: "Chrome Extension", icon: Puzzle },
];

const EASE = [0.32, 0.72, 0, 1] as const;

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [mobileOpen, setMobileOpen] = useState(false);
  const user = useAuthStore((s) => s.user);
  const refreshToken = useAuthStore((s) => s.refreshToken);
  const clear = useAuthStore((s) => s.clear);

  useEffect(() => setMobileOpen(false), [pathname]);

  const logout = async () => {
    try {
      await api.post("/auth/logout", { refresh_token: refreshToken });
    } catch {
      // Revoking is best-effort; the local session is cleared either way.
    }
    clear();
    toast.success("Signed out.");
    router.push("/login");
  };

  const sidebar = (
    <div className="flex h-full flex-col bg-navy-900 px-4 py-6 text-white">
      <Link href="/dashboard" className="flex items-center gap-2.5 px-2">
        <Logo size={34} tone="light" />
        <Wordmark onDark />
      </Link>

      <p className="mt-9 px-3 text-[10px] font-semibold uppercase tracking-[0.18em] text-white/35">
        Main menu
      </p>

      <nav className="mt-3 space-y-1">
        {NAV.map((item) => {
          const active =
            pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-[13.5px]",
                "transition-colors duration-300 ease-[cubic-bezier(0.32,0.72,0,1)]",
                active ? "text-white" : "text-white/55 hover:bg-white/5 hover:text-white/90",
              )}
            >
              {active ? (
                <motion.span
                  layoutId="nav-active"
                  className="absolute inset-0 rounded-xl bg-indigo-600"
                  transition={{ duration: 0.45, ease: EASE }}
                />
              ) : null}
              <item.icon size={17} strokeWidth={1.5} className="relative z-10" />
              <span className="relative z-10 font-medium">{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto space-y-1 border-t border-white/10 pt-5">
        <Link
          href="/settings"
          className={cn(
            "flex items-center gap-3 rounded-xl px-3 py-2.5 text-[13.5px] transition-colors duration-300",
            pathname === "/settings"
              ? "bg-white/10 text-white"
              : "text-white/55 hover:bg-white/5 hover:text-white/90",
          )}
        >
          <Settings size={17} strokeWidth={1.5} />
          <span className="font-medium">Settings</span>
        </Link>
        <button
          type="button"
          onClick={logout}
          className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-[13.5px] text-red-300/80 transition-colors duration-300 hover:bg-red-500/10 hover:text-red-300"
        >
          <LogOut size={17} strokeWidth={1.5} />
          <span className="font-medium">Log out</span>
        </button>
      </div>
    </div>
  );

  return (
    <div className="flex min-h-[100dvh]">
      {/* Without this a keyboard user tabs through all six sidebar links and the
          account menu before reaching the page, on every single navigation.
          Visually hidden until focused, which is the point. */}
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[100] focus:rounded-xl focus:bg-[var(--color-primary)] focus:px-4 focus:py-2.5 focus:text-[13px] focus:font-medium focus:text-white focus:outline-none focus:ring-2 focus:ring-white"
      >
        Skip to main content
      </a>

      <aside className="fixed inset-y-0 left-0 hidden w-[15.5rem] lg:block">{sidebar}</aside>

      <AnimatePresence>
        {mobileOpen ? (
          <>
            <motion.div
              className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm lg:hidden"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setMobileOpen(false)}
            />
            <motion.aside
              className="fixed inset-y-0 left-0 z-50 w-[15.5rem] lg:hidden"
              initial={{ x: "-100%" }}
              animate={{ x: 0 }}
              exit={{ x: "-100%" }}
              transition={{ duration: 0.45, ease: EASE }}
            >
              {sidebar}
            </motion.aside>
          </>
        ) : null}
      </AnimatePresence>

      <div className="flex min-w-0 flex-1 flex-col lg:pl-[15.5rem]">
        <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-[var(--color-hairline)] bg-[var(--color-surface)]/85 px-4 py-3 backdrop-blur-xl sm:px-7">
          <button
            type="button"
            aria-label="Open navigation"
            onClick={() => setMobileOpen((v) => !v)}
            className="rounded-xl p-2 text-[var(--color-ink-2)] ring-1 ring-[var(--color-hairline-strong)] lg:hidden"
          >
            {mobileOpen ? <X size={17} strokeWidth={1.5} /> : <Menu size={17} strokeWidth={1.5} />}
          </button>

          <div className="ml-auto flex items-center gap-3">
            <ThemeToggle />
            <div className="hidden h-8 w-px bg-[var(--color-hairline)] sm:block" />
            <div className="hidden text-right leading-tight sm:block">
              <p className="text-[13px] font-semibold text-[var(--color-ink)]">
                {user?.display_name ?? "Designer"}
              </p>
              <p className="text-[10px] uppercase tracking-[0.14em] text-[var(--color-faint)]">
                {user?.role ?? "designer"}
              </p>
            </div>
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 text-[13px] font-bold text-white">
              {(user?.display_name ?? user?.email ?? "D").slice(0, 1).toUpperCase()}
            </span>
          </div>
        </header>

        <main id="main" tabIndex={-1} className="flex-1 px-4 py-8 sm:px-7 sm:py-10">
          {children}
        </main>
      </div>
    </div>
  );
}
