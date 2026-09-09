"use client";

import { AlertTriangle, RefreshCw, Sparkles, WandSparkles } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Bezel } from "@/components/ui/bezel";
import { Button } from "@/components/ui/button";
import { Badge, Skeleton, Textarea } from "@/components/ui/primitives";
import { useGenerateSuggestions, useSuggestions } from "@/hooks/use-api";
import { cn } from "@/lib/utils";

const SEVERITY_TONE = { high: "danger", medium: "warning", low: "neutral" } as const;

const BASIS_LABEL: Record<string, string> = {
  clarity_score: "Clarity Score",
  focus_order: "Focus order",
  region_saliency: "Region saliency",
  clutter_index: "Clutter index",
};

/**
 * Suggestions load after the heatmap and never block it: a slow, dead, or
 * unconfigured provider degrades to a retry affordance.
 */
export function SuggestionsPanel({ assetId }: { assetId: string }) {
  const { data, isLoading } = useSuggestions(assetId);
  const generate = useGenerateSuggestions(assetId);
  const [context, setContext] = useState("");
  const [showContext, setShowContext] = useState(false);

  const run = (regenerate: boolean) =>
    generate.mutate(
      { user_context: context.trim() || undefined, regenerate },
      {
        onSuccess: (res) => {
          if (res.llm_status === "ok") toast.success("Suggestions generated.");
          else if (res.llm_status === "rate_limited")
            toast.error("Daily suggestion limit reached.");
          else toast.error("The suggestions provider is unavailable.");
        },
        onError: () => toast.error("Could not generate suggestions."),
      },
    );

  const hasItems = (data?.suggestions.length ?? 0) > 0;

  return (
    <Bezel>
      <div className="p-7 sm:p-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="flex items-center gap-2 font-display text-lg font-semibold">
              <WandSparkles size={18} strokeWidth={1.5} className="text-violet-600" />
              AI design suggestions
            </h2>
            <p className="mt-1.5 max-w-xl text-[13px] leading-relaxed text-[var(--color-muted)]">
              Generated from the numeric analytics only. The model never sees your
              image, so every suggestion cites the metric that motivated it.
            </p>
          </div>

          <div className="flex items-center gap-2.5">
            <Button
              size="sm"
              variant={hasItems ? "outline" : "primary"}
              disabled={generate.isPending}
              onClick={() => run(hasItems)}
            >
              <RefreshCw
                size={14}
                strokeWidth={1.5}
                className={cn(generate.isPending && "animate-spin")}
              />
              {generate.isPending
                ? "Generating…"
                : hasItems
                  ? "Regenerate"
                  : "Generate suggestions"}
            </Button>
          </div>
        </div>

        <button
          type="button"
          onClick={() => setShowContext((v) => !v)}
          className="mt-4 text-[12px] font-medium text-indigo-600 hover:underline"
        >
          {showContext ? "Hide design context" : "Add design context (optional)"}
        </button>

        {showContext ? (
          <Textarea
            value={context}
            onChange={(e) => setContext(e.target.value)}
            rows={3}
            maxLength={1000}
            placeholder="e.g. This is a pricing page; the primary goal is the 'Start trial' button."
            className="mt-3"
          />
        ) : null}

        <div className="mt-6">
          {isLoading || generate.isPending ? (
            <div className="space-y-3">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-24 rounded-2xl" />
              ))}
            </div>
          ) : hasItems ? (
            <>
              {data?.summary ? (
                <p className="rounded-2xl bg-[var(--color-surface-2)] p-5 text-[13.5px] leading-relaxed text-[var(--color-ink-2)] ring-1 ring-[var(--color-hairline)]">
                  {data.summary}
                </p>
              ) : null}

              <ul className="mt-4 space-y-3">
                {data?.suggestions.map((s, i) => (
                  <li
                    key={`${s.title}-${i}`}
                    className="rounded-2xl bg-[var(--color-surface-2)] p-5 ring-1 ring-[var(--color-hairline)]"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <h3 className="font-display text-[14.5px] font-semibold">
                        {s.title}
                      </h3>
                      <div className="flex shrink-0 items-center gap-2">
                        <Badge tone={SEVERITY_TONE[s.severity] ?? "neutral"}>
                          {s.severity}
                        </Badge>
                        <Badge tone="indigo">{BASIS_LABEL[s.based_on] ?? s.based_on}</Badge>
                      </div>
                    </div>
                    <p className="mt-2.5 text-[13.5px] leading-relaxed text-[var(--color-muted)]">
                      {s.detail}
                    </p>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <div className="flex flex-col items-center rounded-2xl bg-[var(--color-surface-2)] px-6 py-12 text-center ring-1 ring-[var(--color-hairline)]">
              <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-violet-50 text-violet-600 dark:bg-violet-500/10 dark:text-violet-300">
                {data?.llm_status === "error" ? (
                  <AlertTriangle size={20} strokeWidth={1.5} />
                ) : (
                  <Sparkles size={20} strokeWidth={1.5} />
                )}
              </span>
              <h3 className="mt-4 font-display text-[15px] font-semibold">
                {data?.llm_status === "error"
                  ? "The suggestions provider failed"
                  : "No suggestions generated yet"}
              </h3>
              <p className="mt-2 max-w-md text-[13px] leading-relaxed text-[var(--color-muted)]">
                {data?.llm_status === "error"
                  ? "The heatmap, Clarity Score, and focus order above are unaffected. Try again in a moment."
                  : "Generate written recommendations grounded in the metrics above. Your heatmap and scores are already complete."}
              </p>
            </div>
          )}
        </div>
      </div>
    </Bezel>
  );
}
