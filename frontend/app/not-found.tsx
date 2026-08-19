import Link from "next/link";

import { Button } from "@/components/ui/button";

/**
 * A mistyped or stale URL previously landed on Next's unstyled default page:
 * no branding, no navigation, and no way back into the product. A dead end is
 * the one thing a 404 must not be.
 */
export default function NotFound() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-[var(--color-canvas)] px-6">
      <div className="w-full max-w-md text-center">
        <p className="text-[11px] font-medium uppercase tracking-[0.2em] text-[var(--color-faint)]">
          Page not found
        </p>
        <h1 className="mt-4 font-display text-[2rem] font-bold tracking-[-0.028em] text-[var(--color-ink)]">
          We couldn&rsquo;t find that page
        </h1>
        <p className="mt-3 text-[14px] leading-relaxed text-[var(--color-muted)]">
          The link may be out of date, or the analysis it pointed to may have
          been deleted.
        </p>

        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <Button asChild size="lg">
            <Link href="/dashboard">Go to dashboard</Link>
          </Button>
          <Button asChild size="lg" variant="outline">
            <Link href="/upload">Upload a mockup</Link>
          </Button>
        </div>
      </div>
    </main>
  );
}
