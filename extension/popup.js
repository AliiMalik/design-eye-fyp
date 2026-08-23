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

  // Say where it went. Captures land in a project named after the site, so this
  // is the difference between "it worked" and "I know where to find it".
  const site = res.data.site;
  $("savedTo").textContent = site ? `Saved to your “${site}” project.` : "";
  $("savedTo").hidden = !site;

  const { apiBase } = await chrome.storage.local.get("apiBase");
  const web = (apiBase || DEFAULT_API)
    .replace(/\/api\/v1$/, "")
    .replace(/:8000$/, ":3000");
  $("openFull").href = `${web}/results/${result.asset_id}`;

  show("result");
});

boot();
