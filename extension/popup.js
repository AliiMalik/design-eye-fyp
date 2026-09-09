const DEFAULT_API = "http://localhost:8000/api/v1";

const $ = (id) => document.getElementById(id);
const views = ["auth", "ready", "working", "result"];

function show(name) {
  views.forEach((v) => { $(v).hidden = v !== name; });
}

function fail(el, message) {
  el.textContent = message;
  el.hidden = false;
}

function send(msg) {
  return chrome.runtime.sendMessage(msg);
}

/** Same bands as the web app, so the two never disagree. */
function band(score) {
  if (score >= 75) return { label: "Strong", hex: "#10b981" };
  if (score >= 40) return { label: "Moderate", hex: "#f59e0b" };
  return { label: "Needs work", hex: "#ef4444" };
}

function explain(score, viewportCount) {
  if (viewportCount > 1) {
    return `Scored one screenful at a time across ${viewportCount} screens, then averaged.`;
  }
  if (score >= 75) return "Attention concentrates cleanly on this page.";
  if (score >= 40) return "Attention is workable but spread across several places.";
  return "Attention is scattered; a lot competes for the first look.";
}

async function boot() {
  const { token, apiBase, user } = await chrome.storage.local.get([
    "token", "apiBase", "user",
  ]);
  $("apiBase").value = apiBase || DEFAULT_API;
  $("signout").hidden = !token;
  // The extension holds its own session, separate from the web app's. Naming
  // the account makes a mismatch visible here rather than as a confusing
  // "belongs to another account" after clicking through to the full analysis.
  $("account").textContent = user?.email || "";
  $("account").hidden = !token || !user?.email;
  // Reset the sign-in/create toggle explicitly rather than relying on the popup
  // being torn down between openings. Chrome does destroy it today, but state
  // that only holds because of that is a trap for the next change.
  setAuthMode(false);
  show(token ? "ready" : "auth");
}

// Signing up from here matters: someone handed the extension should not have to
// find the web app first just to get an account.
let creating = false;

function setAuthMode(create) {
  creating = create;
  $("authError").hidden = true;
  $("nameRow").hidden = !create;
  $("pwHint").hidden = !create;
  $("authLede").textContent = create
    ? "Create an account and start analysing pages."
    : "Sign in to analyse the page you are on.";
  $("authSubmit").textContent = create ? "Create account" : "Sign in";
  $("swapText").textContent = create ? "Already have an account?" : "New here?";
  $("swapMode").textContent = create ? "Sign in" : "Create an account";
  $("password").autocomplete = create ? "new-password" : "current-password";
}

$("swapMode").addEventListener("click", () => setAuthMode(!creating));

$("login").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("authError").hidden = true;

  const password = $("password").value;
  if (creating && password.length < 8) {
    return fail($("authError"), "Use at least 8 characters for your password.");
  }

  const btn = $("authSubmit");
  const label = btn.textContent;
  btn.disabled = true;
  btn.textContent = creating ? "Creating…" : "Signing in…";

  const res = await send({
    type: creating ? "REGISTER" : "LOGIN",
    email: $("email").value.trim(),
    password,
    ...(creating ? { displayName: $("displayName").value.trim() } : {}),
  });

  btn.disabled = false;
  btn.textContent = label;
  if (!res?.ok) {
    return fail($("authError"), res?.error || "That did not work.");
  }
  $("signout").hidden = false;
  $("account").textContent = res.data?.email || "";
  $("account").hidden = !res.data?.email;
  show("ready");
});

$("saveApi").addEventListener("click", async () => {
  const value = $("apiBase").value.trim().replace(/\/+$/, "");
  await chrome.storage.local.set({ apiBase: value || DEFAULT_API });
  $("saveApi").textContent = "Saved";
  setTimeout(() => { $("saveApi").textContent = "Save"; }, 1400);
});

$("signout").addEventListener("click", async () => {
  await send({ type: "LOGOUT" });
  $("signout").hidden = true;
  $("account").hidden = true;
  setAuthMode(false);
  show("auth");
});

$("again").addEventListener("click", () => { clearPasted(); show("ready"); });

/* --- paste a screenshot ---------------------------------------------------
 *
 * The other half of the extension: analysing the page you are on covers the
 * live web, and this covers everything else -- a Figma frame, a mockup in
 * another app, or the browser pages Chrome refuses to let us capture.
 */

// Mirrors MAX_UPLOAD_MB in backend/app/config.py. Checked here so an oversized
// image is refused before it is base64-inflated into a worker message, rather
// than after a slow round trip ending in a 400.
const MAX_IMAGE_MB = 10;
const PASTEABLE = { "image/png": "png", "image/jpeg": "jpg", "image/webp": "webp" };

let pastedDataUrl = null;
let pastedName = "";

if (/Mac|iPhone|iPad|iPod/.test(navigator.userAgent)) $("modKey").textContent = "⌘";

function stampedName(type) {
  const pad = (n) => String(n).padStart(2, "0");
  const d = new Date();
  return `screenshot-${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
    + `-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`
    + `.${PASTEABLE[type] || "png"}`;
}

function readableSize(bytes) {
  return bytes >= 1024 * 1024
    ? `${(bytes / 1024 / 1024).toFixed(1)} MB`
    : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function flashDropzone() {
  $("dropzone").classList.add("hot");
  setTimeout(() => $("dropzone").classList.remove("hot"), 700);
}

function clearPasted() {
  pastedDataUrl = null;
  pastedName = "";
  $("pastedCard").hidden = true;
  $("analysePasted").hidden = true;
  $("pastedThumb").removeAttribute("src");
}

/** Take a blob from any of the three routes in and stage it for analysis. */
function stageImage(blob) {
  if (!blob || !PASTEABLE[blob.type]) {
    return fail($("readyError"), "Use a PNG, JPG, or WEBP image.");
  }
  if (blob.size > MAX_IMAGE_MB * 1024 * 1024) {
    return fail(
      $("readyError"),
      `That image is ${readableSize(blob.size)}; the limit is ${MAX_IMAGE_MB}MB.`,
    );
  }

  const reader = new FileReader();
  reader.onload = () => {
    $("readyError").hidden = true;
    pastedDataUrl = reader.result;
    pastedName = blob.name && blob.name !== "image.png" ? blob.name : stampedName(blob.type);

    $("pastedThumb").src = pastedDataUrl;
    $("pastedName").textContent = pastedName;
    $("pastedSize").textContent = readableSize(blob.size);
    $("pastedCard").hidden = false;
    $("analysePasted").hidden = false;
    flashDropzone();
  };
  reader.onerror = () => fail($("readyError"), "That image could not be read.");
  reader.readAsDataURL(blob);
}

// Ctrl+V anywhere in the popup. No clipboardRead permission is needed for a
// real paste event, which is why this is the primary route in rather than
// navigator.clipboard.read() -- that would add a scary install warning for a
// feature the keystroke already covers.
document.addEventListener("paste", (event) => {
  if ($("ready").hidden) return; // signed out, or a run is under way
  const item = Array.from(event.clipboardData?.items || []).find(
    (i) => i.kind === "file" && i.type.startsWith("image/"),
  );
  if (!item) return; // a text paste; leave the form fields alone
  event.preventDefault();
  stageImage(item.getAsFile());
});

$("dropzone").addEventListener("click", () => $("filePick").click());
$("dropzone").addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    $("filePick").click();
  }
});

$("dropzone").addEventListener("dragover", (e) => {
  e.preventDefault();
  $("dropzone").classList.add("hot");
});
$("dropzone").addEventListener("dragleave", () => $("dropzone").classList.remove("hot"));
$("dropzone").addEventListener("drop", (e) => {
  e.preventDefault();
  $("dropzone").classList.remove("hot");
  stageImage(e.dataTransfer?.files?.[0]);
});

$("filePick").addEventListener("change", (e) => {
  const chosen = e.target.files?.[0];
  if (chosen) stageImage(chosen);
  e.target.value = ""; // so re-picking the same file fires change again
});

$("pastedClear").addEventListener("click", clearPasted);

$("analysePasted").addEventListener("click", async () => {
  if (!pastedDataUrl) return;
  $("readyError").hidden = true;
  show("working");
  $("workingText").textContent = "Analysing your screenshot…";

  const res = await send({
    type: "ANALYSE_IMAGE", dataUrl: pastedDataUrl, filename: pastedName,
  });
  if (!(await handled(res))) return;
  clearPasted();
  await renderResult(res.data);
});

/**
 * Deal with a failed run. Returns true when the caller may keep going.
 *
 * Shared by both routes so a capture and a pasted screenshot cannot end up
 * treating an expired session differently.
 */
async function handled(res) {
  if (res?.ok) return true;
  show("ready");
  // A stale token is the one failure worth handling rather than reporting.
  if (res?.error === "SESSION_EXPIRED") {
    await send({ type: "LOGOUT" });
    $("signout").hidden = true;
    $("account").hidden = true;
    show("auth");
    fail($("authError"), "Your session expired. Sign in again.");
    return false;
  }
  fail($("readyError"), res?.error || "Something went wrong.");
  return false;
}

async function renderResult(data) {
  const { result } = data;
  const b = band(result.clarity_score);
  $("scoreValue").textContent = result.clarity_score.toFixed(1);
  $("scoreValue").style.color = b.hex;
  $("scoreBand").textContent = b.label;
  $("scoreBand").style.color = b.hex;
  $("scoreNote").textContent = explain(result.clarity_score, result.viewport_count);
  $("heatmap").src = result.heatmap_url;

  // Say where it went. Captures land in a project named after the site and
  // pasted shots in one of their own, so this is the difference between "it
  // worked" and "I know where to find it".
  const site = data.site;
  $("savedTo").textContent = site ? `Saved to your “${site}” project.` : "";
  $("savedTo").hidden = !site;

  const { apiBase } = await chrome.storage.local.get("apiBase");
  const web = (apiBase || DEFAULT_API)
    .replace(/\/api\/v1$/, "")
    .replace(/:8000$/, ":3000");
  $("openFull").href = `${web}/results/${result.asset_id}`;

  show("result");
}

$("analyse").addEventListener("click", async () => {
  $("readyError").hidden = true;
  const fullPage = $("fullPage").checked;
  show("working");
  $("workingText").textContent = fullPage ? "Scrolling and capturing…" : "Capturing…";

  const res = await send({ type: "ANALYSE", fullPage });
  if (!(await handled(res))) return;
  await renderResult(res.data);
});

boot();
