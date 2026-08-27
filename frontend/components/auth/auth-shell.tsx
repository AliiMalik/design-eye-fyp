"use client";

import Link from "next/link";
import { ShieldCheck, Activity, Lock } from "lucide-react";

import { Logo, ThemeToggle } from "@/components/brand";
import { Reveal } from "@/components/ui/primitives";

const TRUST = [
  // These sit on the sign-in screen, where the reader is a designer deciding
  // whether to trust the product -- not an engineer reviewing the stack.
  { icon: ShieldCheck, label: "Your designs stay private" },
  { icon: Activity, label: "Results in seconds" },
  { icon: Lock, label: "Secure sign-in" },
];

/** Centred card on a plain field, matching the Visily auth screens. */
export function AuthShell({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <main className="mesh relative flex min-h-[100dvh] flex-col items-center justify-center px-4 py-16">
      <div className="absolute right-5 top-5">
        <ThemeToggle />
      </div>

      <Reveal className="w-full max-w-[27rem]">
        <div className="rounded-[2rem] bg-[var(--color-shell)] p-1.5 ring-1 ring-[var(--color-hairline)] shadow-[var(--shadow-lifted)]">
          <div className="inner-lip rounded-[calc(2rem-0.375rem)] bg-[var(--color-surface)] px-7 py-10 ring-1 ring-[var(--color-hairline)] sm:px-9">
            <div className="flex flex-col items-center text-center">
              <Link href="/" aria-label="DesignEye home">
                <Logo size={46} variant="full" />
              </Link>
              <h1 className="mt-5 font-display text-[1.7rem] font-bold tracking-tight">
                {title}
              </h1>
              <p className="mt-2 text-[13.5px] text-[var(--color-muted)]">{subtitle}</p>
            </div>

            <div className="mt-8">{children}</div>

            {footer ? (
              <div className="mt-7 text-center text-[13px] text-[var(--color-muted)]">
                {footer}
              </div>
            ) : null}
          </div>
        </div>
      </Reveal>

      <Reveal delay={0.1}>
        <ul className="mt-10 flex flex-wrap items-center justify-center gap-x-7 gap-y-3">
          {TRUST.map((t) => (
            <li
              key={t.label}
              className="flex items-center gap-2 text-[11px] uppercase tracking-[0.12em] text-[var(--color-faint)]"
            >
              <t.icon size={13} strokeWidth={1.5} className="text-emerald-500" />
              {t.label}
            </li>
          ))}
        </ul>
      </Reveal>

      <div className="mt-10 flex items-center gap-5">
        {[
          { href: "/", label: "Home" },
          { href: "/login", label: "Log in" },
          { href: "/register", label: "Sign up" },
        ].map((l) => (
          <Link
            key={l.href}
            href={l.href}
            className="font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--color-faint)] transition-colors hover:text-indigo-600"
          >
            {l.label}
          </Link>
        ))}
      </div>
    </main>
  );
}
