#!/usr/bin/env node
// scripts/check-scale.mjs — Zero-dependency Node CLI that keeps app CSS on dakit's type and space scales.
//
// Rule: spacing sits on the 4px grid (--dk-space-*) and type uses the text
// scale (--dk-text-*). A px padding/margin/gap/inset value that is not a
// multiple of 4, a raw px font-size, and any negative margin fails. Negative
// margins are layout tricks (a hit area faked by margin: -6px) that the grid
// cannot express; restructure the box instead.
//
// Existing debt is listed in a baseline file (--baseline <file>) that may only
// shrink: a violation not in the baseline fails, and so does a baseline entry
// that no longer occurs, so the list ratchets down as files are migrated.
// `--write-baseline <file>` creates the file, or rewrites it with entries
// removed; it refuses to add or raise an entry.
//
// Same file discovery as check-borders.mjs (vendored dakit assets are
// skipped): node check-scale.mjs [--baseline <file>] <paths...>

import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { collectFiles, extractDeclarations } from "./check-borders.mjs";

const TEMPLATE_PROPS = /(padding|margin|gap|inset|font-size)[a-z-]*\s*:/i;
const SPACING = /^(?:padding|margin|gap|row-gap|column-gap|inset)(?:-(?:top|right|bottom|left|block|inline|block-start|block-end|inline-start|inline-end))?$/;
const PX = /(-?\d*\.?\d+)px\b/g;

function withoutUrls(value) {
  return value.replace(/url\((?:[^()]|\([^()]*\))*\)/gi, "url()");
}

function pxValues(value) {
  return [...withoutUrls(value).matchAll(PX)].map((m) => parseFloat(m[1]));
}

export function scaleReasons(property, value) {
  const reasons = [];
  if (property === "font-size") {
    if (pxValues(value).length) reasons.push("raw px font-size: use a --dk-text-* step");
    return reasons;
  }
  if (!SPACING.test(property)) return reasons;
  if (property.startsWith("margin") && /(?:^|[\s(,*/+])-\s*[\d.]/.test(withoutUrls(value))) {
    reasons.push("negative margin: restructure the box instead");
  }
  const off = pxValues(value).filter((n) => n % 4 !== 0);
  if (off.length) reasons.push(`${off.map((n) => `${n}px`).join(", ")} off the 4px grid: use a --dk-space-* step`);
  return reasons;
}

export function scaleViolations(paths = []) {
  const files = [];
  for (const p of paths) collectFiles(p, files);

  const violations = [];
  for (const file of files) {
    let decls;
    try {
      decls = extractDeclarations(file, TEMPLATE_PROPS);
    } catch (err) {
      console.warn(`warning: failed to read/parse ${file}: ${err.message}`);
      continue;
    }
    for (const { property, value, line } of decls) {
      const cleaned = value.replace(/\s*!important\s*$/i, "").replace(/\s+/g, " ");
      for (const reason of scaleReasons(property, cleaned)) {
        violations.push({ file, line, reason: `${property}: ${cleaned}: ${reason}`, key: `${property}: ${cleaned}` });
      }
    }
  }
  return violations;
}

// Baseline: { "<file relative to the baseline>": { "<property>: <value>": count } }
function tally(violations, base) {
  const counts = {};
  for (const v of violations) {
    const file = relative(base, v.file).split(sep).join("/");
    counts[file] ??= {};
    counts[file][v.key] = (counts[file][v.key] || 0) + 1;
  }
  return counts;
}

function readBaseline(file) {
  if (!existsSync(file)) return {};
  return JSON.parse(readFileSync(file, "utf8"));
}

export function checkScale(paths = [], { baseline } = {}) {
  const violations = scaleViolations(paths);
  if (!baseline) return { failures: violations.map((v) => `${v.file}:${v.line}: ${v.reason}`), violations, counts: {} };

  const base = dirname(resolve(baseline));
  const allowed = readBaseline(baseline);
  const counts = tally(violations, base);
  const failures = [];
  const seen = new Map();
  for (const v of violations) {
    const file = relative(base, v.file).split(sep).join("/");
    const id = `${file}\0${v.key}`;
    const n = (seen.get(id) || 0) + 1;
    seen.set(id, n);
    if (n > (allowed[file]?.[v.key] || 0)) failures.push(`${v.file}:${v.line}: ${v.reason}`);
  }
  for (const [file, entries] of Object.entries(allowed)) {
    for (const [key, n] of Object.entries(entries)) {
      const now = counts[file]?.[key] || 0;
      if (now < n) failures.push(`${baseline}: ${file} lists "${key}" x${n} but only ${now} remain: lower or delete the entry`);
    }
  }
  return { failures, violations, counts };
}

export function writeBaseline(paths, file) {
  const base = dirname(resolve(file));
  const counts = tally(scaleViolations(paths), base);
  if (existsSync(file)) {
    const old = readBaseline(file);
    for (const [path, entries] of Object.entries(counts)) {
      for (const [key, n] of Object.entries(entries)) {
        if (n > (old[path]?.[key] || 0)) {
          throw new Error(`refusing to grow the baseline: ${path} "${key}" x${n} (listed ${old[path]?.[key] || 0}); fix the CSS`);
        }
      }
    }
  }
  const sorted = Object.fromEntries(
    Object.keys(counts).sort().map((f) => [f, Object.fromEntries(Object.entries(counts[f]).sort(([a], [b]) => a.localeCompare(b)))]),
  );
  writeFileSync(file, `${JSON.stringify(sorted, null, 2)}\n`);
  return sorted;
}

function runCli() {
  const args = process.argv.slice(2);
  let baseline;
  let write;
  const paths = [];
  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--baseline") baseline = args[++i];
    else if (args[i] === "--write-baseline") write = args[++i];
    else paths.push(args[i]);
  }
  if (paths.length === 0 || (args.includes("--baseline") && !baseline) || (args.includes("--write-baseline") && !write)) {
    console.error("Usage: node check-scale.mjs [--baseline <file> | --write-baseline <file>] <paths...>");
    process.exit(1);
  }

  if (write) {
    try {
      const out = writeBaseline(paths, write);
      const total = Object.values(out).reduce((a, e) => a + Object.values(e).reduce((x, y) => x + y, 0), 0);
      console.log(`Wrote ${write}: ${total} baselined violation(s) in ${Object.keys(out).length} file(s).`);
    } catch (err) {
      console.error(`FAIL: ${err.message}`);
      process.exit(1);
    }
    return;
  }

  const { failures, violations } = checkScale(paths, { baseline });
  if (failures.length > 0) {
    for (const f of failures) console.error(f);
    console.error(`\nFAIL: ${failures.length} scale problem(s).`);
    process.exit(1);
  }
  console.log(baseline ? `PASS: no new scale violations (${violations.length} baselined).` : "PASS: CSS is on the type and space scales.");
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  runCli();
}
