/**
 * Drive background.js's onMessageExternal handler — the handshake the website
 * uses to hand the extension a session.
 *
 * This is the security-sensitive listener: it accepts an auth token. The origin
 * check is Chrome's (externally_connectable in the manifest), so what is tested
 * here is that the handler itself is strict about what it will act on.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const DIR = join(dirname(fileURLToPath(import.meta.url)), "..");
const source = readFileSync(join(DIR, "background.js"), "utf8");
const manifest = JSON.parse(readFileSync(join(DIR, "manifest.json"), "utf8"));

const results = [];
const check = (name, ok, detail = "") => {
  results.push({ name, ok: !!ok });
  console.log(`  ${ok ? "PASS" : "FAIL"}  ${name}${detail ? "  — " + detail : ""}`);
};

let store = {};
let external = null;

const chrome = {
  runtime: {
    onMessage: { addListener: () => {} },
    onMessageExternal: { addListener: (fn) => { external = fn; } },
    getManifest: () => manifest,
  },
  storage: {
    local: {
      get: async (keys) => Object.fromEntries(
        (Array.isArray(keys) ? keys : [keys]).map((k) => [k, store[k]]),
      ),
      set: async (obj) => { Object.assign(store, obj); },
      remove: async (keys) => {
        (Array.isArray(keys) ? keys : [keys]).forEach((k) => delete store[k]);
      },
    },
  },
  tabs: { query: async () => [], captureVisibleTab: async () => "" },
  scripting: { executeScript: async () => [{ result: {} }] },
};

const sandbox = {
  chrome, console, setTimeout, fetch: async () => { throw new Error("no network"); },
  FormData: class {}, FileReader: class {}, OffscreenCanvas: class {},
  createImageBitmap: async () => ({}), URL,
};
vm.createContext(sandbox);
vm.runInContext(source, sandbox);

const ask = (msg) => new Promise((resolve) => external(msg, {}, resolve));

console.log("\n1. the listener is registered");
check("onMessageExternal has a handler", typeof external === "function");

console.log("\n2. only the website's origin can reach it");
const matches = manifest.externally_connectable?.matches ?? [];
check("externally_connectable is declared", matches.length > 0, matches.join(", "));
check("no wildcard origin", !matches.some((m) => m === "*://*/*" || m.startsWith("*://*")),
      matches.join(", "));

console.log("\n3. PING reports state without leaking the token");
store = {};
let res = await ask({ type: "PING" });
check("reports installed", res.ok === true && res.installed === true);
check("reports signed out", res.signedIn === false);
check("returns the version", res.version === manifest.version, res.version);
check("never returns the token", !("token" in res), Object.keys(res).join(","));

store = { token: "abc", user: { email: "a@b.com" } };
res = await ask({ type: "PING" });
check("reports signed in", res.signedIn === true);
check("names the account", res.email === "a@b.com", res.email);
check("still no token in the reply", !("token" in res));

console.log("\n4. CONNECT adopts the site's session");
store = {};
res = await ask({
  type: "CONNECT",
  token: "site-token",
  user: { email: "ali@designeye.dev" },
  apiBase: "https://api.example.com/api/v1",
});
check("accepted", res.ok === true);
check("token stored", store.token === "site-token", String(store.token));
check("user stored", store.user?.email === "ali@designeye.dev");
check("server address stored", store.apiBase === "https://api.example.com/api/v1", store.apiBase);

console.log("\n5. CONNECT refuses nonsense");
store = { token: "keep-me" };
res = await ask({ type: "CONNECT" });
check("rejects a missing token", res.ok === false, res.error);
check("leaves the existing session alone", store.token === "keep-me", String(store.token));

res = await ask({ type: "WIPE_EVERYTHING" });
check("rejects an unknown request", res.ok === false, res.error);

console.log("\n6. connecting replaces an older session");
store = { token: "old", user: { email: "old@x.com" }, apiBase: "http://localhost:8000/api/v1" };
await ask({ type: "CONNECT", token: "new", user: { email: "new@x.com" } });
check("token replaced", store.token === "new", String(store.token));
check("account replaced", store.user.email === "new@x.com");
check("keeps the address when none is sent",
      store.apiBase === "http://localhost:8000/api/v1", store.apiBase);

const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} passed`);
if (failed.length) {
  console.log("FAILED:", failed.map((f) => f.name).join(", "));
  process.exit(1);
}
