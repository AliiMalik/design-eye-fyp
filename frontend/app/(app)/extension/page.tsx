"use client";

import { Check, Chrome, Download, Loader2, Puzzle, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Bezel } from "@/components/ui/bezel";
import { Button } from "@/components/ui/button";
import { Badge, Eyebrow, Reveal } from "@/components/ui/primitives";
import { API_URL } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";

/** Pinned by the "key" field in extension/manifest.json, so it never changes. */
const EXTENSION_ID = "illaijihjmgpodgbpbpiagnaplnjbdnf";

type Probe =
  | { state: "checking" }
  | { state: "missing" }
  | { state: "installed"; signedIn: boolean; email: string | null; version: string };

/**
 * chrome.runtime is only present in Chromium, and only exposes sendMessage to a
 * page when some extension has listed it under externally_connectable. Both
 * absences mean the same thing here: we cannot reach it.
 */
type ChromeRuntime = {
  runtime?: {
    sendMessage?: (
      id: string,
      message: unknown,
      cb: (response?: unknown) => void,
    ) => void;
    lastError?: { message?: string };
  };
};

function askExtension<T>(message: unknown): Promise<T | null> {
  // Held in a local so the narrowing survives into the callback below.
  const runtime = (globalThis as unknown as { chrome?: ChromeRuntime }).chrome?.runtime;
  const send = runtime?.sendMessage;
  if (!runtime || !send) return Promise.resolve(null);

  return new Promise((resolve) => {
    // Not installed produces lastError rather than a rejection, and a wedged
    // service worker can produce neither, so the timeout is the real backstop.
    const timer = setTimeout(() => resolve(null), 1500);
    try {
      send(EXTENSION_ID, message, (response?: unknown) => {
        clearTimeout(timer);
        resolve(runtime.lastError ? null : ((response as T) ?? null));
      });
    } catch {
      clearTimeout(timer);
      resolve(null);
    }
  });
}

export default function ExtensionPage() {
  const user = useAuthStore((s) => s.user);
  const accessToken = useAuthStore((s) => s.accessToken);
  const refreshToken = useAuthStore((s) => s.refreshToken);

  const [probe, setProbe] = useState<Probe>({ state: "checking" });
  const [connecting, setConnecting] = useState(false);

  const check = useCallback(async () => {
    setProbe({ state: "checking" });
    const res = await askExtension<{
      ok: boolean;
      version: string;
      signedIn: boolean;
      email: string | null;
    }>({ type: "PING" });

    setProbe(
      res?.ok
        ? {
            state: "installed",
            signedIn: res.signedIn,
            email: res.email,
            version: res.version,
          }
        : { state: "missing" },
    );
  }, []);

  useEffect(() => {
    void check();
    // Someone installing in another tab comes back to this one; re-checking on
    // focus saves them wondering why it still says "not installed".
    const onFocus = () => void check();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [check]);

  const connect = async () => {
    if (!accessToken) return;
    setConnecting(true);
    const res = await askExtension<{ ok: boolean; error?: string }>({
      type: "CONNECT",
      token: accessToken,
      refreshToken,
      user,
      apiBase: API_URL,
    });
    setConnecting(false);

    if (!res?.ok) {
      toast.error(res?.error ?? "Could not reach the extension. Reload it and try again.");
      return;
    }
    toast.success("Extension connected to your account.");
    void check();
  };

  const installed = probe.state === "installed";

  return (
    <div className="mx-auto max-w-[52rem] space-y-8">
      <Reveal>
        <Eyebrow>Chrome extension</Eyebrow>
        <h1 className="mt-4 font-display text-[2.1rem] font-bold tracking-[-0.028em]">
          Analyse any live page
        </h1>
        <p className="mt-2 max-w-[38rem] text-[14.5px] leading-relaxed text-[var(--color-muted)]">
          The web app analyses files you export. The extension analyses whatever
          is on screen: a competitor&rsquo;s site, a staging build, a page you
          haven&rsquo;t exported yet.
        </p>
      </Reveal>

      {/* status */}
      <Reveal delay={0.05}>
        <Bezel>
          <div className="flex flex-wrap items-center justify-between gap-4 p-6">
            <div className="flex items-center gap-3">
              <span
                className={
                  installed
                    ? "flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10"
                    : "flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--color-surface-2)] text-[var(--color-muted)]"
                }
              >
                {probe.state === "checking" ? (
                  <Loader2 size={18} strokeWidth={1.5} className="animate-spin" />
                ) : installed ? (
                  <Check size={18} strokeWidth={1.5} />
                ) : (
                  <Puzzle size={18} strokeWidth={1.5} />
                )}
              </span>
              <div>
                <p className="text-[14px] font-semibold">
                  {probe.state === "checking"
                    ? "Looking for the extension…"
                    : installed
                      ? `Installed, version ${probe.version}`
                      : "Not installed yet"}
                </p>
                <p className="mt-0.5 text-[12.5px] text-[var(--color-muted)]">
                  {installed && probe.signedIn
                    ? `Signed in as ${probe.email ?? "your account"}.`
                    : installed
                      ? "Connect it to your account below."
                      : "Download it and follow the three steps."}
                </p>
              </div>
            </div>

            <div className="flex flex-wrap gap-2.5">
              <Button variant="outline" size="sm" onClick={() => void check()}>
                <RefreshCw size={14} strokeWidth={1.5} />
                Check again
              </Button>
              {installed ? (
                <Button size="sm" disabled={connecting} onClick={connect}>
                  {connecting ? "Connecting…" : probe.signedIn ? "Reconnect" : "Connect my account"}
                </Button>
              ) : (
                <Button asChild size="sm">
                  <a href="/designeye-extension.zip" download>
                    <Download size={14} strokeWidth={1.5} />
                    Download
                  </a>
                </Button>
              )}
            </div>
          </div>
        </Bezel>
      </Reveal>

      {/* install steps */}
      <Reveal delay={0.1}>
        <Bezel>
          <div className="p-7">
            <h2 className="font-display text-[15px] font-semibold">
              Adding it to Chrome
            </h2>
            <p className="mt-1.5 text-[12.5px] leading-relaxed text-[var(--color-muted)]">
              Chrome only installs extensions automatically from its own Web
              Store, so this one is added by hand. It takes about a minute, and
              only once.
            </p>

            <ol className="mt-6 space-y-5">
              {[
                {
                  title: "Download and unzip",
                  body: (
                    <>
                      Save <code className="rounded bg-[var(--color-surface-2)] px-1.5 py-0.5 text-[12px]">designeye-extension.zip</code>{" "}
                      and unzip it somewhere you won&rsquo;t delete. Chrome loads the
                      folder from where it sits.
                    </>
                  ),
                },
                {
                  title: "Open the extensions page",
                  body: (
                    <>
                      Go to{" "}
                      <code className="rounded bg-[var(--color-surface-2)] px-1.5 py-0.5 text-[12px]">chrome://extensions</code>{" "}
                      and turn on <strong>Developer mode</strong>, top right.
                    </>
                  ),
                },
                {
                  title: "Load unpacked",
                  body: (
                    <>
                      Click <strong>Load unpacked</strong> and pick the unzipped
                      folder. Then come back here and press{" "}
                      <strong>Check again</strong>.
                    </>
                  ),
                },
              ].map((step, i) => (
                <li key={step.title} className="flex gap-4">
                  <span className="tabular flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--color-primary)] text-[12.5px] font-semibold text-white">
                    {i + 1}
                  </span>
                  <div>
                    <p className="text-[13.5px] font-medium">{step.title}</p>
                    <p className="mt-1 text-[13px] leading-relaxed text-[var(--color-muted)]">
                      {step.body}
                    </p>
                  </div>
                </li>
              ))}
            </ol>

            <div className="mt-7 flex flex-wrap items-center gap-3 border-t border-[var(--color-hairline)] pt-6">
              <Button asChild>
                <a href="/designeye-extension.zip" download>
                  <Download size={15} strokeWidth={1.5} />
                  Download the extension
                </a>
              </Button>
              <span className="inline-flex items-center gap-1.5 text-[12.5px] text-[var(--color-faint)]">
                <Chrome size={14} strokeWidth={1.5} />
                Chrome and Edge
              </span>
            </div>
          </div>
        </Bezel>
      </Reveal>

      {/* what it does */}
      <Reveal delay={0.15}>
        <Bezel>
          <div className="p-7">
            <div className="flex items-center gap-2.5">
              <h2 className="font-display text-[15px] font-semibold">
                Once it&rsquo;s connected
              </h2>
              <Badge tone="indigo">No second sign-in</Badge>
            </div>
            <p className="mt-1.5 text-[12.5px] leading-relaxed text-[var(--color-muted)]">
              Connecting hands the extension the session you already have here,
              so it works as <strong>you</strong> straight away, and your captures
              open correctly from this app instead of belonging to a different
              account.
            </p>
            <ul className="mt-5 space-y-2.5 text-[13px] text-[var(--color-muted)]">
              {[
                "Click the toolbar icon on any site to score the page you're looking at.",
                "Whole-page capture scrolls and stitches, so long pages are scored screen by screen.",
                "Captures are filed into a project named after the site they came from.",
              ].map((line) => (
                <li key={line} className="flex gap-2.5">
                  <Check
                    size={15}
                    strokeWidth={1.5}
                    className="mt-0.5 shrink-0 text-emerald-600"
                  />
                  {line}
                </li>
              ))}
            </ul>
          </div>
        </Bezel>
      </Reveal>
    </div>
  );
}
