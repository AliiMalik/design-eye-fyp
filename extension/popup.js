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
  return "Attention is scattered — a lot competes for the first look.";
}

async function boot() {
  const { token, apiBase } = await chrome.storage.local.get(["token", "apiBase"]);
  $("apiBase").value = apiBase || DEFAULT_API;
  $("signout").hidden = !token;
  show(token ? "ready" : "auth");
}

$("login").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("authError").hidden = true;
  const btn = e.target.querySelector("button");
  btn.disabled = true;
  btn.textContent = "Signing in…";

  const res = await send({
    type: "LOGIN",
    email: $("email").value.trim(),
    password: $("password").value,
  });

  btn.disabled = false;
  btn.textContent = "Sign in";
  if (!res?.ok) return fail($("authError"), res?.error || "Could not sign in.");
  $("signout").hidden = false;
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
  show("auth");
});

$("again").addEventListener("click", () => show("ready"));

$("analyse").addEventListener("click", async () => {
  $("readyError").hidden = true;
  const fullPage = $("fullPage").checked;
  show("working");
  $("workingText").textContent = fullPage ? "Scrolling and capturing…" : "Capturing…";

  const res = await send({ type: "ANALYSE", fullPage });

  if (!res?.ok) {
    show("ready");
    // A stale token is the one failure worth handling rather than reporting.
    if (res?.error === "SESSION_EXPIRED") {
      await send({ type: "LOGOUT" });
      $("signout").hidden = true;
      show("auth");
      return fail($("authError"), "Your session expired. Sign in again.");
    }
    return fail($("readyError"), res?.error || "Something went wrong.");
  }

  const { result } = res.data;
  const b = band(result.clarity_score);
  $("scoreValue").textContent = result.clarity_score.toFixed(1);
  $("scoreValue").style.color = b.hex;
  $("scoreBand").textContent = b.label;
  $("scoreBand").style.color = b.hex;
  $("scoreNote").textContent = explain(result.clarity_score, result.viewport_count);
  $("heatmap").src = result.heatmap_url;

  const { apiBase } = await chrome.storage.local.get("apiBase");
  const web = (apiBase || DEFAULT_API)
    .replace(/\/api\/v1$/, "")
    .replace(/:8000$/, ":3000");
  $("openFull").href = `${web}/results/${result.asset_id}`;

  show("result");
});

boot();
