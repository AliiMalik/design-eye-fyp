"use client";

import { Camera, Loader2, Trash2 } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { UserAvatar } from "@/components/app/user-avatar";
import { Button } from "@/components/ui/button";
import { useApplyUser } from "@/hooks/use-api";
import { api, apiErrorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { User } from "@/types/api";

/** Both mirror backend/app/services/avatars.py, so the file is refused here
 *  rather than after a pointless round trip. */
const MAX_MB = 5;
const ACCEPT = ["image/png", "image/jpeg", "image/webp"];

export function AvatarPicker({
  user,
  size = 84,
  className,
  children,
}: {
  user: User | null;
  size?: number;
  className?: string;
  /** Identity text to sit beside the picture, above the controls. */
  children?: React.ReactNode;
}) {
  const applyUser = useApplyUser();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState<"upload" | "remove" | null>(null);

  const send = async (file: File) => {
    if (!ACCEPT.includes(file.type)) {
      toast.error("Choose a PNG, JPG, or WEBP image.");
      return;
    }
    if (file.size > MAX_MB * 1024 * 1024) {
      toast.error(`That picture is over ${MAX_MB}MB. Pick a smaller one.`);
      return;
    }

    setBusy("upload");
    try {
      const form = new FormData();
      form.append("file", file);
      const { data } = await api.post<User>("/auth/me/avatar", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      applyUser(data);
      toast.success("Profile picture updated.");
    } catch (error) {
      toast.error(apiErrorMessage(error, "Could not upload that picture."));
    } finally {
      setBusy(null);
    }
  };

  const remove = async () => {
    setBusy("remove");
    try {
      const { data } = await api.delete<User>("/auth/me/avatar");
      applyUser(data);
      toast.success("Profile picture removed.");
    } catch (error) {
      toast.error(apiErrorMessage(error, "Could not remove your picture."));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className={cn("flex items-center gap-5", className)}>
      <button
        type="button"
        onClick={() => input.current?.click()}
        disabled={busy !== null}
        aria-label={user?.avatar_url ? "Change your profile picture" : "Add a profile picture"}
        className={cn(
          "group relative rounded-full outline-none",
          "focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2",
          "focus-visible:ring-offset-[var(--color-surface)]",
        )}
      >
        <UserAvatar user={user} size={size} />
        <span
          className={cn(
            "absolute inset-0 flex items-center justify-center rounded-full bg-navy-900/55 text-white",
            "opacity-0 transition-opacity duration-300 ease-[cubic-bezier(0.32,0.72,0,1)]",
            "group-hover:opacity-100 group-focus-visible:opacity-100",
            busy === "upload" && "opacity-100",
          )}
        >
          {busy === "upload" ? (
            <Loader2 size={20} strokeWidth={1.5} className="animate-spin" />
          ) : (
            <Camera size={20} strokeWidth={1.5} />
          )}
        </span>
      </button>

      <div className="min-w-0 flex-1">
        {children}
        <div className={cn("flex flex-wrap gap-2.5", children && "mt-3")}>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={busy !== null}
            onClick={() => input.current?.click()}
          >
            <Camera size={14} strokeWidth={1.5} />
            {user?.avatar_url ? "Change photo" : "Add a photo"}
          </Button>
          {user?.avatar_url ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={busy !== null}
              onClick={remove}
            >
              <Trash2 size={14} strokeWidth={1.5} />
              {busy === "remove" ? "Removing…" : "Remove"}
            </Button>
          ) : null}
        </div>
        <p className="mt-2 text-[11.5px] text-[var(--color-faint)]">
          PNG, JPG, or WEBP, up to {MAX_MB}MB. We crop it to a square for you.
        </p>
      </div>

      <input
        ref={input}
        type="file"
        accept={ACCEPT.join(",")}
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          // Reset first: picking the same file twice otherwise fires nothing.
          e.target.value = "";
          if (file) void send(file);
        }}
      />
    </div>
  );
}
