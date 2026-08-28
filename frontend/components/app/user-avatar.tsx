"use client";

import Image from "next/image";

import { cn } from "@/lib/utils";
import type { User } from "@/types/api";

/** Matches AVATAR_PX in backend/app/services/avatars.py. */
const STORED_PX = 256;

type AvatarUser = Pick<User, "display_name" | "email" | "avatar_url">;

export function initialFor(user?: AvatarUser | null): string {
  return (user?.display_name ?? user?.email ?? "D").slice(0, 1).toUpperCase();
}

/**
 * The user's picture, falling back to their initial.
 *
 * Every avatar is stored square, so `object-cover` here is a safety net rather
 * than a crop — the crop already happened once, on upload, so the picture is
 * the same everywhere it appears.
 */
export function UserAvatar({
  user,
  size = 36,
  className,
}: {
  user?: AvatarUser | null;
  size?: number;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "relative flex shrink-0 items-center justify-center overflow-hidden rounded-full",
        "bg-gradient-to-br from-indigo-500 to-violet-600 font-display font-bold text-white",
        className,
      )}
      style={{ width: size, height: size, fontSize: Math.round(size * 0.4) }}
    >
      {user?.avatar_url ? (
        <Image
          src={user.avatar_url}
          alt=""
          width={STORED_PX}
          height={STORED_PX}
          // Avatars sit in the header and on the profile card — always above
          // the fold. Lazy would leave an empty circle until the observer runs.
          loading="eager"
          className="h-full w-full object-cover"
        />
      ) : (
        initialFor(user)
      )}
    </span>
  );
}
