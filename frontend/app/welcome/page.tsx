"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowRight } from "lucide-react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { AuthGuard } from "@/components/app/auth-guard";
import { AvatarPicker } from "@/components/app/avatar-picker";
import { AuthShell } from "@/components/auth/auth-shell";
import { Button } from "@/components/ui/button";
import { Field, Input, Textarea } from "@/components/ui/primitives";
import { useApplyUser } from "@/hooks/use-api";
import { api, apiErrorMessage } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
import type { User } from "@/types/api";

const schema = z.object({
  display_name: z.string().min(2, "Enter your name.").max(120),
  bio: z.string().max(250, "Maximum 250 characters.").optional(),
});
type Values = z.infer<typeof schema>;

/**
 * Shown once, straight after signing up. Everything here is optional and
 * editable later in Settings, so it offers a way out rather than blocking the
 * product behind a form — but it is the one moment someone is willing to fill
 * this in, so it is worth asking.
 */
function Welcome() {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const applyUser = useApplyUser();

  const form = useForm<Values>({
    resolver: zodResolver(schema),
    values: { display_name: user?.display_name ?? "", bio: user?.bio ?? "" },
  });

  const finish = form.handleSubmit(async (values) => {
    try {
      const { data } = await api.patch<User>("/auth/me", values);
      applyUser(data);
      toast.success("Profile saved.");
      router.replace("/dashboard");
    } catch (error) {
      toast.error(apiErrorMessage(error, "Could not save your profile."));
    }
  });

  const firstName = (user?.display_name ?? "").trim().split(/\s+/)[0];

  return (
    <AuthShell
      title={firstName ? `Welcome, ${firstName}` : "Welcome to DesignEye"}
      subtitle="Finish your profile so your workspace feels like yours. It takes a moment, and you can change any of it later."
      footer={
        <button
          type="button"
          onClick={() => router.replace("/dashboard")}
          className="font-semibold text-[var(--color-muted)] underline-offset-4 hover:underline"
        >
          Skip for now
        </button>
      }
    >
      <form onSubmit={finish} className="space-y-6" noValidate>
        <div className="rounded-2xl bg-[var(--color-surface-2)] p-5 ring-1 ring-[var(--color-hairline)]">
          {/* The picture uploads on choice rather than on submit, so skipping
              from here still keeps a photo someone has already picked. */}
          <AvatarPicker user={user} size={72} />
        </div>

        <Field label="Full name" error={form.formState.errors.display_name?.message}>
          <Input {...form.register("display_name")} autoComplete="name" />
        </Field>

        <Field
          label="Short bio"
          hint={
            <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-[var(--color-faint)]">
              Optional
            </span>
          }
          error={form.formState.errors.bio?.message}
        >
          <Textarea
            {...form.register("bio")}
            rows={3}
            maxLength={250}
            placeholder="Product designer focused on conversion-critical interfaces."
          />
        </Field>

        <Button
          type="submit"
          variant="primary"
          size="lg"
          className="w-full"
          disabled={form.formState.isSubmitting}
          trailingIcon={<ArrowRight size={16} strokeWidth={1.5} />}
        >
          {form.formState.isSubmitting ? "Saving…" : "Go to my workspace"}
        </Button>
      </form>
    </AuthShell>
  );
}

export default function WelcomePage() {
  return (
    <AuthGuard>
      <Welcome />
    </AuthGuard>
  );
}
