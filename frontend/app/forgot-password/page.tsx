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
import type { MessageResponse } from "@/types/api";

const schema = z.object({ email: z.string().email("Enter a valid email address.") });
type FormValues = z.infer<typeof schema>;

export default function ForgotPasswordPage() {
  const [sent, setSent] = useState<string | null>(null);
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
      const { data } = await api.post<MessageResponse>("/auth/reset-password", values);
      setSent(data.message);
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
                Reset link sent to your email.
              </p>
              {/* In DEV_MODE the API returns the token inline; there is no mail service. */}
              {sent.includes("DEV_MODE token:") ? (
                <p className="mt-2 break-all font-mono text-[11px] text-emerald-700 dark:text-emerald-400">
                  {sent.replace("Reset link sent. ", "")}
                </p>
              ) : null}
            </div>
          </div>

          {sent.includes("DEV_MODE token:") ? (
            <Button asChild variant="outline" size="lg" className="w-full">
              <Link
                href={`/reset-password?token=${encodeURIComponent(
                  sent.split("DEV_MODE token:")[1]?.trim() ?? "",
                )}`}
              >
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
