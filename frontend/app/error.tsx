"use client";

import { useEffect } from "react";
import Link from "next/link";

import { Button } from "@/components/ui/button";

/**
 * Route error boundary. Without one, an unhandled render error showed Next's
 * raw error screen -- a stack trace in development and a blank grey page in
 * production, either way with no route back into the app.
 *
 * The message stays generic on purpose: the same rule the API follows, since a
 * thrown error can carry internals a user should not read.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Unhandled error boundary:", error);
  }, [error]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-[var(--color-canvas)] px-6">
      <div className="w-full max-w-md text-center">
        <p className="text-[11px] font-medium uppercase tracking-[0.2em] text-[var(--color-faint)]">
          Something went wrong
        </p>
        <h1 className="mt-4 font-display text-[2rem] font-bold tracking-[-0.028em] text-[var(--color-ink)]">
          This page didn&rsquo;t load
        </h1>
        <p className="mt-3 text-[14px] leading-relaxed text-[var(--color-muted)]">
          Your work is safe and nothing was lost. Try again, and if it keeps
          happening, head back to your dashboard.
        </p>

        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <Button size="lg" onClick={reset}>
            Try again
          </Button>
          <Button asChild size="lg" variant="outline">
            <Link href="/dashboard">Back to dashboard</Link>
          </Button>
        </div>

        {error.digest ? (
          <p className="mt-6 text-[11px] text-[var(--color-faint)]">
            Reference: {error.digest}
          </p>
        ) : null}
      </div>
    </main>
  );
}
