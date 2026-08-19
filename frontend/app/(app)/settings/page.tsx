"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Cpu, Lock, Monitor, Moon, Palette, ShieldCheck, Sun, User } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Bezel } from "@/components/ui/bezel";
import { Button } from "@/components/ui/button";
import {
  Badge,
  Eyebrow,
  Field,
  Input,
  Reveal,
  Textarea,
} from "@/components/ui/primitives";
import { useHealth, useMe } from "@/hooks/use-api";
import { api, apiErrorMessage } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
import { cn, formatDate } from "@/lib/utils";
import type { User as ApiUser } from "@/types/api";

const profileSchema = z.object({
  display_name: z.string().min(2, "Enter your name.").max(120),
  bio: z.string().max(250, "Maximum 250 characters.").optional(),
});
type ProfileValues = z.infer<typeof profileSchema>;

const passwordSchema = z
  .object({
    current_password: z.string().min(1, "Enter your current password."),
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
type PasswordValues = z.infer<typeof passwordSchema>;

const THEMES = [
  { key: "light", label: "Light", icon: Sun },
  { key: "dark", label: "Dark", icon: Moon },
  { key: "system", label: "System", icon: Monitor },
] as const;

export default function SettingsPage() {
  const { data: me } = useMe();
  const { data: health } = useHealth();
  const setUser = useAuthStore((s) => s.setUser);
  const storedUser = useAuthStore((s) => s.user);
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  const user = me ?? storedUser;

  const profileForm = useForm<ProfileValues>({
    resolver: zodResolver(profileSchema),
    values: {
      display_name: user?.display_name ?? "",
      bio: user?.bio ?? "",
    },
  });

  const passwordForm = useForm<PasswordValues>({ resolver: zodResolver(passwordSchema) });

  const saveProfile = profileForm.handleSubmit(async (values) => {
    try {
      const { data } = await api.patch<ApiUser>("/auth/me", values);
      setUser(data);
      toast.success("Profile updated.");
    } catch (error) {
      toast.error(apiErrorMessage(error, "Could not update your profile."));
    }
  });

  const changePassword = passwordForm.handleSubmit(async (values) => {
    try {
      await api.post("/auth/change-password", {
        current_password: values.current_password,
        new_password: values.new_password,
      });
      passwordForm.reset();
      toast.success("Password updated.");
    } catch (error) {
      toast.error(apiErrorMessage(error, "Could not update your password."));
    }
  });

  const initial = (user?.display_name ?? user?.email ?? "D").slice(0, 1).toUpperCase();

  return (
    <div className="mx-auto max-w-[52rem] space-y-7">
      <Reveal>
        <Eyebrow>Account</Eyebrow>
        <h1 className="mt-4 font-display text-[2.1rem] font-bold tracking-[-0.028em]">
          Settings
        </h1>
        <p className="mt-2 text-[14.5px] text-[var(--color-muted)]">
          Manage your profile, security, and workspace appearance.
        </p>
      </Reveal>

      {/* --- profile --- */}
      <Reveal>
        <Bezel>
          <form onSubmit={saveProfile} className="p-7 sm:p-8" noValidate>
            <h2 className="flex items-center gap-2 font-display text-[17px] font-semibold">
              <User size={17} strokeWidth={1.5} className="text-indigo-600" />
              Profile
            </h2>
            <p className="mt-1.5 text-[13px] text-[var(--color-muted)]">
              This is how you appear across your workspace.
            </p>

            <div className="mt-6 flex items-center gap-4 rounded-2xl bg-[var(--color-surface-2)] p-5 ring-1 ring-[var(--color-hairline)]">
              <span className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-600 font-display text-2xl font-bold text-white">
                {initial}
              </span>
              <div className="min-w-0">
                <p className="truncate text-[15px] font-semibold">
                  {user?.display_name ?? "Designer"}
                </p>
                <p className="truncate text-[13px] text-[var(--color-muted)]">
                  {user?.email}
                </p>
                {user?.created_at ? (
                  <p className="mt-1 text-[11px] text-[var(--color-faint)]">
                    Member since {formatDate(user.created_at)}
                  </p>
                ) : null}
              </div>
              <Badge tone="indigo" className="ml-auto shrink-0">
                {user?.role ?? "designer"}
              </Badge>
            </div>

            <div className="mt-6 grid gap-5 sm:grid-cols-2">
              <Field
                label="Full name"
                error={profileForm.formState.errors.display_name?.message}
              >
                <Input {...profileForm.register("display_name")} />
              </Field>
              <Field
                label="Email address"
                hint={
                  <span className="rounded-full bg-[var(--color-shell)] px-2 py-0.5 text-[10px] uppercase tracking-[0.1em] text-[var(--color-faint)]">
                    Read only
                  </span>
                }
              >
                <Input value={user?.email ?? ""} readOnly disabled />
              </Field>
            </div>

            <Field
              label="Short bio"
              className="mt-5"
              error={profileForm.formState.errors.bio?.message}
            >
              <Textarea
                {...profileForm.register("bio")}
                rows={3}
                maxLength={250}
                placeholder="Product designer focused on conversion-critical interfaces."
              />
            </Field>
            <p className="mt-2 text-[11px] text-[var(--color-faint)]">
              Brief description for your profile. Maximum 250 characters.
            </p>

            <Button
              type="submit"
              variant="navy"
              className="mt-6"
              disabled={profileForm.formState.isSubmitting}
            >
              {profileForm.formState.isSubmitting ? "Saving…" : "Save profile changes"}
            </Button>
          </form>
        </Bezel>
      </Reveal>

      {/* --- security --- */}
      <Reveal>
        <Bezel>
          <form onSubmit={changePassword} className="p-7 sm:p-8" noValidate>
            <h2 className="flex items-center gap-2 font-display text-[17px] font-semibold">
              <ShieldCheck size={17} strokeWidth={1.5} className="text-indigo-600" />
              Security &amp; access
            </h2>
            <p className="mt-1.5 text-[13px] text-[var(--color-muted)]">
              Your password is stored scrambled, so nobody — including us — can read it.
            </p>

            <Field
              label="Current password"
              className="mt-6"
              error={passwordForm.formState.errors.current_password?.message}
            >
              <div className="relative">
                <Lock
                  size={16}
                  strokeWidth={1.5}
                  className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-[var(--color-faint)]"
                />
                <Input
                  {...passwordForm.register("current_password")}
                  type="password"
                  autoComplete="current-password"
                  className="pl-10"
                />
              </div>
            </Field>

            <div className="mt-5 grid gap-5 sm:grid-cols-2">
              <Field
                label="New password"
                error={passwordForm.formState.errors.new_password?.message}
              >
                <Input
                  {...passwordForm.register("new_password")}
                  type="password"
                  autoComplete="new-password"
                  placeholder="Min. 8 characters"
                />
              </Field>
              <Field
                label="Confirm new password"
                error={passwordForm.formState.errors.confirm?.message}
              >
                <Input
                  {...passwordForm.register("confirm")}
                  type="password"
                  autoComplete="new-password"
                />
              </Field>
            </div>

            <Button
              type="submit"
              variant="outline"
              className="mt-6"
              disabled={passwordForm.formState.isSubmitting}
            >
              {passwordForm.formState.isSubmitting ? "Updating…" : "Update password"}
            </Button>
          </form>
        </Bezel>
      </Reveal>

      {/* --- appearance --- */}
      <Reveal>
        <Bezel>
          <div className="p-7 sm:p-8">
            <h2 className="flex items-center gap-2 font-display text-[17px] font-semibold">
              <Palette size={17} strokeWidth={1.5} className="text-indigo-600" />
              Appearance
            </h2>
            <p className="mt-1.5 text-[13px] text-[var(--color-muted)]">
              Your choice is remembered on this device.
            </p>

            <div className="mt-6 grid gap-3 sm:grid-cols-3">
              {THEMES.map((t) => {
                const active = mounted && theme === t.key;
                return (
                  <button
                    key={t.key}
                    type="button"
                    onClick={() => setTheme(t.key)}
                    className={cn(
                      "flex items-center gap-3 rounded-2xl px-4 py-3.5 text-[13.5px] font-medium",
                      "ring-1 transition-all duration-400 ease-[cubic-bezier(0.32,0.72,0,1)]",
                      active
                        ? "bg-indigo-50 text-indigo-700 ring-indigo-300 dark:bg-indigo-500/10 dark:text-indigo-300 dark:ring-indigo-400/30"
                        : "bg-[var(--color-surface-2)] text-[var(--color-ink-2)] ring-[var(--color-hairline)] hover:bg-[var(--color-shell)]",
                    )}
                  >
                    <t.icon size={16} strokeWidth={1.5} />
                    {t.label}
                  </button>
                );
              })}
            </div>
          </div>
        </Bezel>
      </Reveal>

      {/* --- system --- */}
      <Reveal>
        <Bezel>
          <div className="p-7 sm:p-8">
            <h2 className="flex items-center gap-2 font-display text-[17px] font-semibold">
              <Cpu size={17} strokeWidth={1.5} className="text-indigo-600" />
              System
            </h2>
            <p className="mt-1.5 text-[13px] text-[var(--color-muted)]">
              Live status of the inference backend.
            </p>

            <dl className="mt-6 space-y-3">
              {[
                { k: "API status", v: health?.status ?? "unknown" },
                { k: "Model loaded", v: health?.model_loaded ? "yes" : "no" },
                { k: "Database", v: health?.db ? "connected" : "unavailable" },
                { k: "Job queue", v: health?.redis ? "connected" : "not required" },
                { k: "Model version", v: String(health?.model_info?.model_version ?? "—") },
                { k: "Model build", v: String(health?.model_info?.checkpoint_version ?? "—") },
                { k: "Device", v: String(health?.model_info?.device ?? "—") },
                { k: "API version", v: health?.version ?? "—" },
              ].map((row) => (
                <div
                  key={row.k}
                  className="flex items-baseline justify-between gap-3 border-b border-[var(--color-hairline)] pb-2.5 last:border-0"
                >
                  <dt className="text-[13px] text-[var(--color-muted)]">{row.k}</dt>
                  <dd className="tabular truncate text-[13px] font-semibold">{row.v}</dd>
                </div>
              ))}
            </dl>
          </div>
        </Bezel>
      </Reveal>
    </div>
  );
}
