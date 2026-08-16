"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Lock } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { AuthShell } from "@/components/auth/auth-shell";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/primitives";
import { api, apiErrorMessage } from "@/lib/api";
import type { MessageResponse } from "@/types/api";

const schema = z
  .object({
    token: z.string().min(1, "A reset token is required."),
    new_password: z
      .string()
      .min(8, "At least 8 characters.")
      .refine((v) => /[a-zA-Z]/.test(v) && /\d/.test(v), {
        message: "Include at least one letter and one number.",
      }),
    confirm: z.string(),
  })
  .refine((v) => v.new_password === v.confirm, {
    message: "Passwords do not match.",
    path: ["confirm"],
  });

type FormValues = z.infer<typeof schema>;

function ResetForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [submitting, setSubmitting] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { token: params.get("token") ?? "" },
  });

  const onSubmit = handleSubmit(async (values) => {
    setSubmitting(true);
    try {
      await api.post<MessageResponse>("/auth/reset-password/confirm", {
        token: values.token,
        new_password: values.new_password,
      });
      toast.success("Password updated. You can log in now.");
      router.push("/login");
    } catch (error) {
      toast.error(apiErrorMessage(error, "Could not reset your password."));
    } finally {
      setSubmitting(false);
    }
  });

  return (
    <form onSubmit={onSubmit} className="space-y-5" noValidate>
      <Field label="Reset token" error={errors.token?.message}>
        <Input
          {...register("token")}
          placeholder="Paste the token from your reset link"
          className="font-mono text-[12px]"
        />
      </Field>

      <Field label="New password" error={errors.new_password?.message}>
        <div className="relative">
          <Lock
            size={16}
            strokeWidth={1.5}
            className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-[var(--color-faint)]"
          />
          <Input
            {...register("new_password")}
            type="password"
            autoComplete="new-password"
            placeholder="Min. 8 characters"
            className="pl-10"
          />
        </div>
      </Field>

      <Field label="Confirm new password" error={errors.confirm?.message}>
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
            placeholder="Repeat your new password"
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
        {submitting ? "Updating…" : "Update password"}
      </Button>
    </form>
  );
}

export default function ResetPasswordPage() {
  return (
    <AuthShell
      title="Choose a new password"
      subtitle="Set a new password for your DesignEye account."
      footer={
        <Link href="/login" className="font-semibold text-violet-600 hover:underline">
          Back to login
        </Link>
      }
    >
      <Suspense fallback={<div className="h-64" />}>
        <ResetForm />
      </Suspense>
    </AuthShell>
  );
}
