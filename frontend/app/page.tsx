import Link from "next/link";
import {
  ArrowRight,
  ArrowUpRight,
  BarChart3,
  Check,
  CircuitBoard,
  Eye,
  Gauge,
  Layers,
  ScanEye,
  Upload,
} from "lucide-react";

import { Logo, Wordmark } from "@/components/brand";
import { HeroDemo } from "@/components/marketing/hero-demo";
import { SiteNav } from "@/components/marketing/site-nav";
import { SmoothScroll } from "@/components/smooth-scroll";
import { Button } from "@/components/ui/button";
import { Bezel } from "@/components/ui/bezel";
import { Eyebrow, Reveal, Stagger, StaggerItem } from "@/components/ui/primitives";

const CAPABILITIES = [
  {
    icon: Upload,
    tag: "PNG / JPG / WEBP / SVG / PDF",
    title: "Upload a mockup",
    body: "Drop in a static export from Figma, Sketch, or Adobe XD. No code, no tracking script, and no live traffic required.",
  },
  {
    icon: ScanEye,
    tag: "SalGAN + U-Net",
    title: "The model predicts attention",
    body: "A saliency network trained on eye-tracking data returns a per-pixel prediction of where human eyes land first.",
  },
  {
    icon: BarChart3,
    tag: "Clarity Score + Focus Order",
    title: "Act on the numbers",
    body: "A 0-100 Clarity Score, a ranked focus sequence, and grounded suggestions that cite the metric behind each one.",
  },
];

const STEPS = [
  {
    n: "01",
    title: "Upload your design",
    body: "Drag a mockup into the dropzone. Files are validated, normalised, and stored against your account only.",
  },
  {
    n: "02",
    title: "Analyse in seconds",
    body: "Inference runs on the trained saliency model, then analytics compute dispersion, edge clutter, and peak ordering.",
  },
  {
    n: "03",
    title: "Refine and compare",
    body: "Fix what competes for the first fixation, upload the variant, and let the A/B module score the difference.",
  },
];

const PROOF = [
  { label: "Correlation coefficient", value: "0.675", note: "CC on held-out validation" },
  { label: "Normalised scanpath", value: "2.43", note: "NSS, higher is better" },
  { label: "Analysis time", value: "<1s", note: "per mockup on CPU" },
  { label: "Users needed", value: "Zero", note: "works pre-launch" },
];

export default function LandingPage() {
  return (
    <>
      <SmoothScroll />
      <SiteNav />

      <main className="relative overflow-x-clip">
        {/* ---------------- hero ---------------- */}
        <section className="mesh relative px-4 pb-24 pt-36 sm:pt-44">
          <div className="mx-auto grid max-w-[78rem] items-center gap-16 lg:grid-cols-[1.12fr_1.1fr] lg:gap-14">
            <div>
              <Reveal>
                <Eyebrow>
                  <span className="h-1.5 w-1.5 rounded-full bg-indigo-500" />
                  Alpha Release 1.0
                </Eyebrow>
              </Reveal>

              <Reveal delay={0.06}>
                <h1 className="mt-7 font-display text-[2.5rem] font-bold leading-[1.05] tracking-[-0.03em] sm:text-[3.1rem] lg:text-[3.35rem]">
                  See your design
                  <br />
                  <span className="text-gradient whitespace-nowrap italic">
                    through users&apos; eyes
                  </span>
                </h1>
              </Reveal>

              <Reveal delay={0.12}>
                <p className="mt-7 max-w-lg text-[15px] leading-relaxed text-[var(--color-muted)] sm:text-base">
                  DesignEye predicts where attention lands on a static mockup
                  before a single user sees it. Upload a design, get a
                  predicted-attention heatmap, a Clarity Score, and the focus
                  order your layout actually creates.
                </p>
              </Reveal>

              <Reveal delay={0.18}>
                <div className="mt-9 flex flex-wrap items-center gap-3">
                  <Button
                    asChild
                    size="lg"
                    variant="gradient"
                    trailingIcon={<ArrowUpRight size={16} strokeWidth={1.5} />}
                  >
                    <Link href="/register">Get started free</Link>
                  </Button>
                  <Button asChild size="lg" variant="outline">
                    <Link href="/login">
                      <Eye size={16} strokeWidth={1.5} />
                      See a live analysis
                    </Link>
                  </Button>
                </div>
              </Reveal>

              <Reveal delay={0.24}>
                <ul className="mt-9 flex flex-wrap items-center gap-x-7 gap-y-3">
                  {["No credit card required", "Figma-ready exports", "Pre-launch, no traffic"].map(
                    (t) => (
                      <li
                        key={t}
                        className="flex items-center gap-2 text-[12px] uppercase tracking-[0.1em] text-[var(--color-faint)]"
                      >
                        <Check size={13} strokeWidth={2} className="text-emerald-500" />
                        {t}
                      </li>
                    ),
                  )}
                </ul>
              </Reveal>
            </div>

            <Reveal delay={0.1} y={60}>
              <HeroDemo />
            </Reveal>
          </div>
        </section>

        {/* ---------------- capabilities ---------------- */}
        <section id="capabilities" className="px-4 py-28 sm:py-36">
          <div className="mx-auto max-w-[76rem]">
            <Reveal>
              <Eyebrow>Core capabilities</Eyebrow>
              <h2 className="mt-6 max-w-2xl font-display text-3xl font-bold leading-[1.1] tracking-[-0.025em] sm:text-5xl">
                Everything you need to master visual hierarchy.
              </h2>
            </Reveal>

            <Stagger className="mt-16 grid gap-6 md:grid-cols-3">
              {CAPABILITIES.map((c) => (
                <StaggerItem key={c.title}>
                  <Bezel className="h-full">
                    <div className="flex h-full flex-col p-8">
                      <span className="inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-600 ring-1 ring-indigo-100 dark:bg-indigo-500/10 dark:text-indigo-300 dark:ring-indigo-400/20">
                        <c.icon size={20} strokeWidth={1.5} />
                      </span>
                      <h3 className="mt-7 font-display text-xl font-semibold tracking-tight">
                        {c.title}
                      </h3>
                      <p className="mt-3 flex-1 text-[14px] leading-relaxed text-[var(--color-muted)]">
                        {c.body}
                      </p>
                      <span className="mt-7 inline-flex w-fit rounded-full bg-[var(--color-shell)] px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-[var(--color-muted)]">
                        {c.tag}
                      </span>
                    </div>
                  </Bezel>
                </StaggerItem>
              ))}
            </Stagger>
          </div>
        </section>

        {/* ---------------- flow ---------------- */}
        <section id="flow" className="px-4 py-28 sm:py-36">
          <div className="mx-auto max-w-[76rem]">
            <Reveal>
              <div className="flex flex-wrap items-end justify-between gap-6">
                <div>
                  <Eyebrow>Operational flow</Eyebrow>
                  <h2 className="mt-6 max-w-xl font-display text-3xl font-bold leading-[1.1] tracking-[-0.025em] sm:text-5xl">
                    Three steps to cognitive-first design.
                  </h2>
                </div>
                <span className="inline-flex items-center gap-2 rounded-full bg-[var(--color-surface)] px-4 py-2.5 text-[12px] text-[var(--color-muted)] ring-1 ring-[var(--color-hairline)]">
                  <Layers size={14} strokeWidth={1.5} />
                  Supports Figma, XD &amp; Sketch exports
                </span>
              </div>
            </Reveal>

            <Stagger className="mt-16 grid gap-x-10 gap-y-12 md:grid-cols-3">
              {STEPS.map((s) => (
                <StaggerItem key={s.n}>
                  <div className="relative">
                    <span className="font-display text-6xl font-bold text-[var(--color-hairline-strong)]">
                      {s.n}
                    </span>
                    <div className="mt-4 h-px w-full bg-gradient-to-r from-[var(--color-hairline-strong)] to-transparent" />
                    <h3 className="mt-6 font-display text-lg font-semibold">{s.title}</h3>
                    <p className="mt-2.5 text-[14px] leading-relaxed text-[var(--color-muted)]">
                      {s.body}
                    </p>
                  </div>
                </StaggerItem>
              ))}
            </Stagger>
          </div>
        </section>

        {/* ---------------- proof ---------------- */}
        <section id="proof" className="px-4 py-28 sm:py-36">
          <div className="mx-auto max-w-[76rem]">
            <Bezel className="overflow-hidden">
              <div className="mesh px-8 py-16 sm:px-14 sm:py-20">
                <Reveal>
                  <Eyebrow>Model accuracy</Eyebrow>
                  <h2 className="mt-6 max-w-2xl font-display text-3xl font-bold leading-[1.1] tracking-[-0.025em] sm:text-[2.75rem]">
                    Trained on human eye-tracking data, measured on held-out designs.
                  </h2>
                </Reveal>

                <Stagger className="mt-14 grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
                  {PROOF.map((p) => (
                    <StaggerItem key={p.label}>
                      <p className="tabular font-display text-4xl font-bold text-[var(--color-ink)]">
                        {p.value}
                      </p>
                      <p className="mt-2.5 text-[13px] font-medium text-[var(--color-ink-2)]">
                        {p.label}
                      </p>
                      <p className="mt-1 text-[12px] text-[var(--color-faint)]">{p.note}</p>
                    </StaggerItem>
                  ))}
                </Stagger>
              </div>
            </Bezel>
          </div>
        </section>

        {/* ---------------- cta ---------------- */}
        <section className="px-4 pb-32">
          <div className="mx-auto max-w-[76rem]">
            <Reveal>
              <div className="relative overflow-hidden rounded-[2.5rem] bg-gradient-to-br from-indigo-600 via-violet-600 to-violet-700 px-8 py-20 text-center sm:px-16 sm:py-28">
                <div className="pointer-events-none absolute inset-0 opacity-30 [background:radial-gradient(30rem_20rem_at_50%_0%,white,transparent_70%)]" />
                <div className="relative">
                  <h2 className="mx-auto max-w-2xl font-display text-3xl font-bold leading-[1.1] tracking-[-0.025em] text-white sm:text-5xl">
                    Ready to see what you&apos;ve been missing?
                  </h2>
                  <p className="mx-auto mt-6 max-w-xl text-[15px] leading-relaxed text-white/75">
                    Stop guessing which element wins the first fixation. Upload
                    a mockup and find out in under a second.
                  </p>
                  <div className="mt-11 flex flex-wrap items-center justify-center gap-3">
                    <Button
                      asChild
                      size="lg"
                      className="bg-white text-navy-900 shadow-none hover:bg-white/90"
                      trailingIcon={
                        <ArrowRight size={16} strokeWidth={1.5} className="text-navy-900" />
                      }
                    >
                      <Link href="/register">Create your account</Link>
                    </Button>
                    <Button
                      asChild
                      size="lg"
                      variant="ghost"
                      className="text-white ring-1 ring-white/25 hover:bg-white/10"
                    >
                      <Link href="/login">Log in</Link>
                    </Button>
                  </div>
                  <p className="mt-10 font-mono text-[10px] uppercase tracking-[0.28em] text-white/45">
                    D-Eye system online // ready for input
                  </p>
                </div>
              </div>
            </Reveal>
          </div>
        </section>
      </main>

      {/* ---------------- footer ---------------- */}
      <footer className="border-t border-[var(--color-hairline)] bg-[var(--color-surface)] px-4 py-16">
        <div className="mx-auto grid max-w-[76rem] gap-12 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <Link href="/" className="flex items-center gap-2.5">
              <Logo size={32} />
              <Wordmark />
            </Link>
            <p className="mt-5 max-w-xs text-[13px] leading-relaxed text-[var(--color-muted)]">
              Predictive visual-attention analysis for static UI mockups, built
              on a SalGAN-style saliency model.
            </p>
          </div>

          <FooterCol
            title="Product"
            links={[
              { label: "Heatmap engine", href: "#capabilities" },
              { label: "A/B testing", href: "#flow" },
              { label: "Model accuracy", href: "#proof" },
            ]}
          />
          <FooterCol
            title="Account"
            links={[
              { label: "Log in", href: "/login" },
              { label: "Create account", href: "/register" },
              { label: "Reset password", href: "/forgot-password" },
            ]}
          />
          <div>
            <h4 className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--color-faint)]">
              Project
            </h4>
            <p className="mt-5 text-[13px] leading-relaxed text-[var(--color-muted)]">
              Final Year Project &mdash; Group S26CS003
              <br />
              University of Central Punjab
            </p>
            <span className="mt-5 inline-flex items-center gap-2 rounded-full bg-[var(--color-shell)] px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-[var(--color-muted)]">
              <CircuitBoard size={12} strokeWidth={1.5} />
              stage3-ui-v1
            </span>
          </div>
        </div>

        <div className="mx-auto mt-14 flex max-w-[76rem] flex-wrap items-center justify-between gap-4 border-t border-[var(--color-hairline)] pt-8">
          <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--color-faint)]">
            &copy; 2026 DesignEye &middot; All rights reserved
          </p>
          <p className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--color-faint)]">
            <Gauge size={12} strokeWidth={1.5} />
            Status: operational
          </p>
        </div>
      </footer>
    </>
  );
}

function FooterCol({
  title,
  links,
}: {
  title: string;
  links: { label: string; href: string }[];
}) {
  return (
    <div>
      <h4 className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--color-faint)]">
        {title}
      </h4>
      <ul className="mt-5 space-y-3">
        {links.map((l) => (
          <li key={l.label}>
            <Link
              href={l.href}
              className="text-[13px] text-[var(--color-muted)] transition-colors duration-300 hover:text-indigo-600"
            >
              {l.label}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
