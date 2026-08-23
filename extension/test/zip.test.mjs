/**
 * The website hands out a prebuilt ZIP, so it can silently go stale: change
 * background.js, forget to rebuild, and everyone downloads yesterday's
 * extension. This compares the archive against the source it claims to package.
 */
import { readFileSync, existsSync, statSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";

const DIR = join(dirname(fileURLToPath(import.meta.url)), "..");
const ROOT = join(DIR, "..");
const ZIP = join(ROOT, "frontend", "public", "designeye-extension.zip");

const results = [];
const check = (name, ok, detail = "") => {
  results.push({ name, ok: !!ok });
  console.log(`  ${ok ? "PASS" : "FAIL"}  ${name}${detail ? "  — " + detail : ""}`);
};

console.log("\nextension archive");
check("the zip exists", existsSync(ZIP), ZIP);

if (existsSync(ZIP)) {
  const before = createHash("sha256").update(readFileSync(ZIP)).digest("hex");
  // The builder is deterministic, so rebuilding must reproduce the same bytes
  // unless the source actually changed.
  execFileSync(process.platform === "win32" ? "python" : "python3",
    [join(ROOT, "scripts", "build_extension.py")], { cwd: ROOT, stdio: "ignore" });
  const after = createHash("sha256").update(readFileSync(ZIP)).digest("hex");

  check("the zip is up to date with extension/", before === after,
        before === after ? "" : "run: python scripts/build_extension.py");
  check("the zip is a sensible size", statSync(ZIP).size > 5000, `${statSync(ZIP).size} bytes`);
}

const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} passed`);
if (failed.length) process.exit(1);
