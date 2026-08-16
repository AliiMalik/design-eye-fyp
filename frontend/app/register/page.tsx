"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowRight, Lock, Mail, User } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { AuthShell } from "@/components/auth/auth-shell";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/primitives";
import { api, apiErrorMessage } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
import { cn } from "@/lib/utils";
import type { TokenResponse } from "@/types/api";

const schema = z
  .object({
    display_name: z.string().min(2, "Enter your name.").max(120),
    email: z.string().email("Enter a valid email address."),
    password: z
      .string()
      .min(8, "At least 8 characters.")
      .refine((v) => /[a-zA-Z]/.test(v) && /\d/.test(v), {
        message: "Include at least one letter and one number.",
      }),
    confirm: z.string(),
  })
  .refine((v) => v.password === v.confirm, {
    message: "Passwords do not match.",
    path: ["confirm"],
  });

type FormValues = z.infer<typeof schema>;

function strength(pw: string): { score: 0 | 1 | 2 | 3; label: string; tone: string } {
  if (!pw) return { score: 0, label: "—", tone: "bg-[var(--color-hairline-strong)]" };
  let s = 0;
  if (pw.length >= 8) s += 1;
  if (pw.length >= 12) s += 1;
  if (/[^a-zA-Z0-9]/.test(pw) && /[A-Z]/.test(pw)) s += 1;
  const map = [
    { label: "Weak", tone: "bg-red-500" },
    { label: "Fair", tone: "bg-amber-500" },
    { label: "Good", tone: "bg-emerald-500" },
    { label: "Strong", tone: "bg-emerald-600" },
  ] as const;
  const idx = Math.min(s, 3) as 0 | 1 | 2 | 3;
  return { score: idx, ...map[idx] };
}

export default function RegisterPage() {
  const router = useRouter();
  const setSession = useAuthStore((s) => s.setSession);
  const [submitting, setSubmitting] = useState(false);

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const pw = watch("password") ?? "";
  const meter = strength(pw);

  const onSubmit = handleSubmit(async (values) => {
    setSubmitting(true);
    try {
      const { data } = await api.post<TokenResponse>("/auth/register", {
        email: values.email,
        password: values.password,
        display_name: values.display_name,
      });
      setSession(data.access_token, data.refresh_token, data.user);
      toast.success("Account created. Welcome to DesignEye.");
      router.push("/dashboard");
    } catch (error) {
      toast.error(apiErrorMessage(error, "Could not create your account."));
    } finally {
      setSubmitting(false);
    }
  });

  return (
    <AuthShell
      title="Create your account"
      subtitle="Start your visual design journey today."
      footer={
        <>
          Already have an account?{" "}
          <Link href="/login" className="font-semibold text-violet-600 hover:underline">
            Log in
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} className="space-y-5" noValidate>
        <Field
          label="Full name"
          error={errors.display_name?.message}
          hint={
            <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-indigo-600">
              Required
            </span>
          }
        >
          <div className="relative">
            <User
              size={16}
              strokeWidth={1.5}
              className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-[var(--color-faint)]"
            />
            <Input
              {...register("display_name")}
              autoComplete="name"
              placeholder="e.g. Alex Harrison"
              className="pl-10"
            />
          </div>
        </Field>

        <Field label="Email address" error={errors.email?.message}>
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

        <Field
          label="Password"
          error={errors.password?.message}
          hint={
            <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-[var(--color-faint)]">
              Strength: {meter.label}
            </span>
          }
        >
          <div className="relative">
            <Lock
              size={16}
              strokeWidth={1.5}
              className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-[var(--color-faint)]"
            />
            <Input
              {...register("password")}
              type="password"
              autoComplete="new-password"
              placeholder="Min. 8 characters"
              className="pl-10"
            />
          </div>
          <div className="mt-2 flex gap-1.5">
            {[0, 1, 2, 3].map((i) => (
              <span
                key={i}
                className={cn(
                  "h-1 flex-1 rounded-full transition-colors duration-500",
                  pw && i <= meter.score ? meter.tone : "bg-[var(--color-hairline-strong)]",
                )}
              />
            ))}
          </div>
        </Field>

        <Field label="Confirm password" error={errors.confirm?.message}>
          <div className="relative">
            <Lock
              size={16}
              strokeWidth={1.5}
              className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-[var(--color-faint)]"
            />
            <Input
              {...register("confirm")}
              type="password"
              autoComplete="new-password"
              placeholder="Repeat your password"
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
          trailingIcon={<ArrowRight size={16} strokeWidth={1.5} />}
        >
          {submitting ? "Creating account…" : "Create account"}
        </Button>
      </form>
    </AuthShell>
  );
}
