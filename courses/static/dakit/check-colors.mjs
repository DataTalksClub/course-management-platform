#!/usr/bin/env node
// scripts/check-colors.mjs — Zero-dependency Node CLI that keeps raw colours out of app CSS.
//
// Rule: apps colour things through semantic roles only (--dk-text-muted,
// --dk-danger-bg, …). A raw hex, rgb(a)(), hsl(a)() or other colour-function
// literal in a declaration fails, including a fallback inside var() and a
// site-local custom property, because a raw value has no dark-theme remap.
// If a role is missing, add it to dakit's tokens (both themes) instead.
//
// Same file discovery as check-borders.mjs (vendored dakit assets are
// skipped), and it runs the same way: node check-colors.mjs <paths...>

import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { COLOR_LITERAL, collectFiles, extractDeclarations } from "./check-borders.mjs";

// Colour-bearing properties in JS template literals that are read as CSS.
const TEMPLATE_PROPS = /(color|background|border|outline|shadow|fill|stroke)\s*:/i;

export function checkColors(paths = []) {
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
      // An inline image (url(data:…)) may spell colours for its own pixels.
      const scanned = value.replace(/url\((?:[^()]|\([^()]*\))*\)/gi, "url()");
      for (const literal of scanned.match(COLOR_LITERAL) || []) {
        violations.push({
          file,
          line,
          reason: `raw colour ${literal} in ${property}: use a semantic --dk-* role`,
        });
      }
    }
  }
  return violations;
}

function runCli() {
  const args = process.argv.slice(2);
  if (args.length === 0) {
    console.error("Usage: node check-colors.mjs <paths...>");
    process.exit(1);
  }

  const violations = checkColors(args);
  if (violations.length > 0) {
    for (const v of violations) console.error(`${v.file}:${v.line}: ${v.reason}`);
    console.error(`\nFAIL: found ${violations.length} raw colour literal(s).`);
    process.exit(1);
  }
  console.log("PASS: no raw colour literals found.");
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  runCli();
}
