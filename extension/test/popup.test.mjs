/**
 * Drive the real extension/popup.js through every state.
 *
 * A DOM harness rather than a browser: the popup is a plain script with no
 * framework, so the surface it touches is small and can be faked exactly. This
 * exercises the code that actually ships, including the branches that only
 * appear when something goes wrong.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const DIR = join(dirname(fileURLToPath(import.meta.url)), "..");
const html = readFileSync(join(DIR, "popup.html"), "utf8");
const source = readFileSync(join(DIR, "popup.js"), "utf8");

// Every id the markup declares -- so the harness cannot drift from the real page.
const ids = [...html.matchAll(/id="([^"]+)"/g)].map((m) => m[1]);

let results = [];
const check = (name, cond, detail = "") => {
  results.push({ name, ok: !!cond, detail });
  console.log(`  ${cond ? "PASS" : "FAIL"}  ${name}${detail ? "  — " + detail : ""}`);
};

function makeEl(id) {
  const listeners = {};
  return {
    id,
    hidden: true,
    textContent: "",
    value: "",
    checked: true,
    href: "",
    src: "",
    disabled: false,
    style: {},
    addEventListener: (ev, fn) => { listeners[ev] = fn; },
    _fire: (ev, arg) => listeners[ev]?.(arg),
    _has: (ev) => Boolean(listeners[ev]),
    querySelector: () => ({ disabled: false, textContent: "" }),
  };
}

const els = Object.fromEntries(ids.map((i) => [i, makeEl(i)]));

// --- chrome shim ---------------------------------------------------------
let store = {};
let nextResponse = null;
let lastMessage = null;

const chrome = {
  storage: {
    local: {
      get: async (keys) => {
        const k = Array.isArray(keys) ? keys : [keys];
        return Object.fromEntries(k.map((x) => [x, store[x]]));
      },
      set: async (obj) => { Object.assign(store, obj); },
      remove: async (keys) => {
        (Array.isArray(keys) ? keys : [keys]).forEach((k) => delete store[k]);
      },
    },
  },
  runtime: {
    sendMessage: async (msg) => {
      lastMessage = msg;
      const r = typeof nextResponse === "function" ? nextResponse(msg) : nextResponse;
      return r;
    },
  },
};

const sandbox = {
  document: { getElementById: (id) => els[id] || makeEl(id) },
  chrome,
  console,
  setTimeout,
  URL,
};
vm.createContext(sandbox);
vm.runInContext(source, sandbox);

const settle = () => new Promise((r) => setImmediate(r));
const visible = () => ["auth", "ready", "working", "result"].filter((v) => !els[v].hidden);

// --- 1. signed out --------------------------------------------------------
console.log("\n1. boot with no token");
store = {};
await sandbox.boot();
await settle();
check("shows the sign-in view", visible().join() === "auth", visible().join() || "nothing visible");
check("sign-out is hidden", els.signout.hidden === true);
check("api field is prefilled", els.apiBase.value.includes("localhost:8000"), els.apiBase.value);

// --- 2. boot signed in ----------------------------------------------------
console.log("\n2. boot with a stored token");
store = { token: "t0ken" };
await sandbox.boot();
await settle();
check("shows the ready view", visible().join() === "ready", visible().join());
check("sign-out is offered", els.signout.hidden === false);

// --- 3. login failure -----------------------------------------------------
console.log("\n3. wrong password");
store = {};
await sandbox.boot(); await settle();
nextResponse = { ok: false, error: "Those details did not work." };
els.email.value = "a@b.com"; els.password.value = "nope";
await els.login._fire("submit", { preventDefault() {}, target: els.login });
await settle();
check("stays on sign-in", visible().join() === "auth", visible().join());
check("shows the error", els.authError.hidden === false && /did not work/.test(els.authError.textContent),
      els.authError.textContent);

// --- 4. login success -----------------------------------------------------
console.log("\n4. correct password");
nextResponse = { ok: true, data: { email: "demo@designeye.app" } };
await els.login._fire("submit", { preventDefault() {}, target: els.login });
await settle();
check("moves to ready", visible().join() === "ready", visible().join());
check("sends email and password", lastMessage.type === "LOGIN" && lastMessage.email === "a@b.com");

// --- 5. analyse success ---------------------------------------------------
console.log("\n5. analyse a page");
store = { token: "t0ken", apiBase: "http://localhost:8000/api/v1" };
nextResponse = {
  ok: true,
  data: { result: { clarity_score: 31.45, viewport_count: 3, heatmap_url: "http://h/x.png", asset_id: "abc123" } },
};
els.fullPage.checked = true;
await els.analyse._fire("click");
await settle(); await settle();
check("shows the result", visible().join() === "result", visible().join());
check("score matches the web app's toFixed(1)", els.scoreValue.textContent === "31.4", els.scoreValue.textContent);
check("band is Needs work", els.scoreBand.textContent === "Needs work", els.scoreBand.textContent);
check("explains the multi-screen average", /3 screens/.test(els.scoreNote.textContent), els.scoreNote.textContent);
check("heatmap wired", els.heatmap.src === "http://h/x.png");
check("full-page flag passed through", lastMessage.fullPage === true);
check("deep link points at the web app", els.openFull.href === "http://localhost:3000/results/abc123",
      els.openFull.href);

// --- 6. band boundaries ---------------------------------------------------
console.log("\n6. score bands");
check("75 is Strong", sandbox.band(75).label === "Strong");
check("74.9 is Moderate", sandbox.band(74.9).label === "Moderate");
check("40 is Moderate", sandbox.band(40).label === "Moderate");
check("39.9 is Needs work", sandbox.band(39.9).label === "Needs work");

// --- 7. expired session ---------------------------------------------------
console.log("\n7. token expired mid-analysis");
store = { token: "stale" };
await sandbox.boot(); await settle();
const sent = [];
nextResponse = (msg) => { sent.push(msg.type); return msg.type === "ANALYSE" ? { ok: false, error: "SESSION_EXPIRED" } : { ok: true }; };
await els.analyse._fire("click");
await settle(); await settle();
check("returns to sign-in", visible().join() === "auth", visible().join());
check("says the session expired", /expired/i.test(els.authError.textContent), els.authError.textContent);
check("asks the worker to sign out", sent.includes("LOGOUT"), sent.join(","));

// --- 8. a normal failure --------------------------------------------------
console.log("\n8. capture blocked on a chrome:// page");
store = { token: "t0ken" };
await sandbox.boot(); await settle();
nextResponse = { ok: false, error: "Chrome blocks capture on browser pages. Open a website first." };
await els.analyse._fire("click");
await settle(); await settle();
check("stays on ready", visible().join() === "ready", visible().join());
check("surfaces the reason", /Chrome blocks capture/.test(els.readyError.textContent), els.readyError.textContent);


// --- 9. creating an account ----------------------------------------------
console.log("\n9. create an account from the extension");
store = {};
await sandbox.boot(); await settle();
els.swapMode._fire("click");
check("switches to create mode", els.authSubmit.textContent === "Create account", els.authSubmit.textContent);
check("asks for a name", els.nameRow.hidden === false);
check("shows the password rule", els.pwHint.hidden === false);

els.email.value = "new@designeye.dev"; els.password.value = "short";
await els.login._fire("submit", { preventDefault() {}, target: els.login });
await settle();
check("rejects a short password before calling the server",
      /8 characters/.test(els.authError.textContent), els.authError.textContent);

els.password.value = "LongEnough1";
els.displayName.value = "New User";
nextResponse = { ok: true, data: { email: "new@designeye.dev" } };
await els.login._fire("submit", { preventDefault() {}, target: els.login });
await settle();
check("sends REGISTER, not LOGIN", lastMessage.type === "REGISTER", lastMessage.type);
check("passes the name through", lastMessage.displayName === "New User");
check("lands on ready", visible().join() === "ready", visible().join());
check("shows the new account", els.account.textContent === "new@designeye.dev", els.account.textContent);

// --- 10. swapping back ----------------------------------------------------
console.log("\n10. switch back to signing in");
store = {}; await sandbox.boot(); await settle();
els.swapMode._fire("click");
els.swapMode._fire("click");
check("returns to sign-in", els.authSubmit.textContent === "Sign in", els.authSubmit.textContent);
check("hides the name field", els.nameRow.hidden === true);
els.email.value = "a@b.com"; els.password.value = "pw";
nextResponse = { ok: true, data: { email: "a@b.com" } };
await els.login._fire("submit", { preventDefault() {}, target: els.login });
await settle();
check("sends LOGIN", lastMessage.type === "LOGIN", lastMessage.type);

// --- 11. says where the capture was filed ---------------------------------
console.log("\n11. result names the project");
store = { token: "t0ken" };
await sandbox.boot(); await settle();
nextResponse = { ok: true, data: {
  site: "figma.com",
  result: { clarity_score: 88.2, viewport_count: 1, heatmap_url: "http://h/y.png", asset_id: "zzz" },
} };
await els.analyse._fire("click");
await settle(); await settle();
check("names the project", /figma\.com/.test(els.savedTo.textContent), els.savedTo.textContent);
check("saved-to is visible", els.savedTo.hidden === false);

const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} passed`);
if (failed.length) { console.log("FAILED:", failed.map((f) => f.name).join(", ")); process.exit(1); }
