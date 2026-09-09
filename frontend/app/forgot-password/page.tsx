"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowLeft, CheckCircle2, Mail } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { AuthShell } from "@/components/auth/auth-shell";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/primitives";
import { api, apiErrorMessage } from "@/lib/api";
import type { ResetRequestResponse } from "@/types/api";

const schema = z.object({ email: z.string().email("Enter a valid email address.") });
type FormValues = z.infer<typeof schema>;

export default function ForgotPasswordPage() {
  const [sent, setSent] = useState<string | null>(null);
  // Only ever set when the API runs with EXPOSE_RESET_TOKEN; otherwise the link
  // arrives by email and never reaches the browser.
  const [devToken, setDevToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const onSubmit = handleSubmit(async (values) => {
    setSubmitting(true);
    setError(null);
    try {
      const { data } = await api.post<ResetRequestResponse>(
        "/auth/reset-password",
        values,
      );
      setSent(data.message);
      setDevToken(data.reset_token ?? null);
    } catch (err) {
      setError(apiErrorMessage(err, "Could not send the reset link."));
    } finally {
      setSubmitting(false);
    }
  });

  return (
    <AuthShell
      title="Reset your password"
      subtitle="Enter your email address and we'll send you a link to reset your password."
    >
      {sent ? (
        <div className="space-y-6">
          <div className="flex items-start gap-3 rounded-2xl bg-emerald-50 p-4 ring-1 ring-emerald-200 dark:bg-emerald-500/10 dark:ring-emerald-400/20">
            <CheckCircle2
              size={18}
              strokeWidth={1.5}
              className="mt-0.5 shrink-0 text-emerald-600 dark:text-emerald-400"
            />
            <div className="min-w-0">
              <p className="text-[13.5px] font-medium text-emerald-800 dark:text-emerald-300">
                {sent}
              </p>
              {/* Present only when the server is configured to hand the token
                  back instead of emailing it. */}
              {devToken ? (
                <p className="mt-2 break-all font-mono text-[11px] text-emerald-700 dark:text-emerald-400">
                  {devToken}
                </p>
              ) : null}
            </div>
          </div>

          {devToken ? (
            <Button asChild variant="outline" size="lg" className="w-full">
              <Link href={`/reset-password?token=${encodeURIComponent(devToken)}`}>
                Continue to reset form
              </Link>
            </Button>
          ) : null}

          <Link
            href="/login"
            className="flex items-center justify-center gap-2 text-[13px] font-medium text-indigo-600 hover:underline"
          >
            <ArrowLeft size={14} strokeWidth={1.5} />
            Back to login
          </Link>
        </div>
      ) : (
        <form onSubmit={onSubmit} className="space-y-5" noValidate>
          <Field label="Email address" error={errors.email?.message ?? error ?? undefined}>
            <div className="relative">
              <Mail
                size={16}
                strokeWidth={1.5}
                className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-[var(--color-faint)]"
              />
              <Input
                {...register("email")}
                type="email"
                autoComplete="email"
                placeholder="name@company.com"
                className="pl-10"
              />
            </div>
          </Field>

          <Button
            type="submit"
            variant="primary"
            size="lg"
            disabled={submitting}
            className="w-full"
          >
            {submitting ? "Sending…" : "Send reset link"}
          </Button>

          <Link
            href="/login"
            className="flex items-center justify-center gap-2 pt-2 text-[13px] font-medium text-indigo-600 hover:underline"
          >
            <ArrowLeft size={14} strokeWidth={1.5} />
            Back to login
          </Link>
        </form>
      )}
    </AuthShell>
  );
}
