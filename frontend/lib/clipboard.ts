/**
 * Turning a copied screenshot into an upload.
 *
 * Shared by the paste handler and the "Paste screenshot" button so the two can
 * never disagree about what is acceptable or how the file gets named.
 */

/** Raster types a clipboard can actually hold that the API also accepts.
 *
 *  SVG and PDF are deliberately absent: they are supported uploads, but a
 *  clipboard never carries them as an image, so listing them here would only
 *  produce a File the backend then rejects. */
export const PASTEABLE_TYPES: Record<string, string> = {
  "image/png": "png",
  "image/jpeg": "jpg",
  "image/webp": "webp",
};

/**
 * A clipboard image arrives either unnamed or called "image.png" by every OS
 * alike. That name is stored on the asset and shown in the history list, the
 * results header and the PDF report, so three pasted screenshots would be
 * indistinguishable a day later. Stamp each one with the moment it was pasted.
 */
export function screenshotFilename(type: string, now = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  const stamp =
    `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}` +
    `-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
  return `screenshot-${stamp}.${PASTEABLE_TYPES[type] ?? "png"}`;
}

/** Wrap a clipboard blob as a named File, or null if it is not a usable image. */
export function fileFromImageBlob(blob: Blob): File | null {
  if (!PASTEABLE_TYPES[blob.type]) return null;
  return new File([blob], screenshotFilename(blob.type), { type: blob.type });
}

/**
 * The image carried by a paste event, or null when the clipboard holds only
 * text. Returning null rather than throwing is what lets the caller leave an
 * ordinary text paste completely alone.
 */
export function imageFromPaste(event: ClipboardEvent): File | null {
  const items = Array.from(event.clipboardData?.items ?? []);
  const image = items.find(
    (item) => item.kind === "file" && item.type.startsWith("image/"),
  );
  const blob = image?.getAsFile();
  return blob ? fileFromImageBlob(blob) : null;
}

export type ClipboardRead =
  | { ok: true; file: File }
  | { ok: false; reason: "empty" | "blocked" };

/**
 * Read the clipboard on demand, for the button.
 *
 * Ctrl+V needs no permission but has to be discovered first; a button is
 * obvious but has to go through the async Clipboard API, which Firefox does not
 * implement for images and which any browser may refuse without a gesture it
 * trusts. Failure comes back as "blocked" so the caller can point at the
 * keyboard shortcut instead of dead-ending the user.
 */
export async function readImageFromClipboard(): Promise<ClipboardRead> {
  try {
    if (!navigator.clipboard?.read) return { ok: false, reason: "blocked" };
    for (const item of await navigator.clipboard.read()) {
      const type = item.types.find((t) => t in PASTEABLE_TYPES);
      if (!type) continue;
      const file = fileFromImageBlob(await item.getType(type));
      if (file) return { ok: true, file };
    }
    return { ok: false, reason: "empty" };
  } catch {
    return { ok: false, reason: "blocked" };
  }
}
