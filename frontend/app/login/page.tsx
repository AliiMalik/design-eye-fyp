"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowRight, Eye, EyeOff, Lock, Mail } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { AuthShell } from "@/components/auth/auth-shell";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/primitives";
import { api, apiErrorMessage } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
import type { TokenResponse } from "@/types/api";

const schema = z.object({
  email: z.string().email("Enter a valid email address."),
  password: z.string().min(1, "Enter your password."),
});
type FormValues = z.infer<typeof schema>;

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const setSession = useAuthStore((s) => s.setSession);
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  useEffect(() => {
    if (params.get("expired")) {
      toast.error("Your session expired. Please log in again.");
    }
    if (params.get("registered")) {
      toast.success("Account created. Log in to continue.");
    }
  }, [params]);

  const onSubmit = handleSubmit(async (values) => {
    setSubmitting(true);
    try {
      const { data } = await api.post<TokenResponse>("/auth/login", values);
      setSession(data.access_token, data.refresh_token, data.user);
      toast.success(`Welcome back, ${data.user.display_name ?? "designer"}.`);
      router.push("/dashboard");
    } catch (error) {
      toast.error(apiErrorMessage(error, "Could not log you in."));
    } finally {
      setSubmitting(false);
    }
  });

  return (
    <form onSubmit={onSubmit} className="space-y-5" noValidate>
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
          <Link
            href="/forgot-password"
            className="text-[12px] font-medium text-indigo-600 hover:underline"
          >
            Forgot password?
          </Link>
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
            type={showPassword ? "text" : "password"}
            autoComplete="current-password"
            placeholder="Your password"
            className="pl-10 pr-11"
          />
          <button
            type="button"
            onClick={() => setShowPassword((v) => !v)}
            aria-label={showPassword ? "Hide password" : "Show password"}
            className="absolute right-3 top-1/2 -translate-y-1/2 rounded-lg p-1.5 text-[var(--color-faint)] transition-colors hover:text-[var(--color-ink)]"
          >
            {showPassword ? (
              <EyeOff size={16} strokeWidth={1.5} />
            ) : (
              <Eye size={16} strokeWidth={1.5} />
            )}
          </button>
        </div>
      </Field>

      <Button
        type="submit"
        variant="navy"
        size="lg"
        disabled={submitting}
        className="w-full"
        trailingIcon={<ArrowRight size={16} strokeWidth={1.5} />}
      >
        {submitting ? "Signing in…" : "Log in to workspace"}
      </Button>
    </form>
  );
}

export default function LoginPage() {
  return (
    <AuthShell
      title="DesignEye"
      subtitle="Welcome back. Access your workspace."
      footer={
        <>
          Don&apos;t have an account?{" "}
          <Link href="/register" className="font-semibold text-violet-600 hover:underline">
            Sign up for free
          </Link>
        </>
      }
    >
      <Suspense fallback={<div className="h-64" />}>
        <LoginForm />
      </Suspense>
    </AuthShell>
  );
}
