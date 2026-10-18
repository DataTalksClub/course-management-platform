#!/usr/bin/env node
// scripts/check-borders.mjs — Zero-dependency Node CLI to enforce border rules in dakit and consuming sites.
//
// Rule: ACCENT BORDERS ARE FORBIDDEN.
// - Borders are always NEUTRAL, 1px, even on all sides.
// - Neutral border roles: --dk-border-default, --dk-border-control-hover, --dk-border-strong.
// - Status = tinted background fill (--dk-*-bg) + text/icon/badge (fill-only).
// - Selection = --dk-accent-soft fill with neutral border.
// - Single exception: keyboard focus indicator (outline with --dk-focus-ring on :focus / :focus-visible).

import { readFileSync, statSync, readdirSync } from "node:fs";
import { resolve, join, basename, extname } from "node:path";
import { fileURLToPath } from "node:url";

const NEUTRAL_BORDER_ROLES = new Set([
  "--dk-border-default",
  "--dk-border-control-hover",
  "--dk-border-strong",
]);

const REMOVED_BORDER_ROLES = new Set([
  "--dk-accent-border",
  "--dk-success-border",
  "--dk-warning-border",
  "--dk-danger-border",
  "--dk-info-border",
]);

const NEUTRAL_KEYWORDS = new Set([
  "transparent",
  "none",
  "currentcolor",
  "inherit",
  "initial",
  "unset",
  "black",
  "white",
  "gray",
  "grey",
  "lightgray",
  "lightgrey",
  "darkgray",
  "darkgrey",
  "dimgray",
  "dimgrey",
  "slategray",
  "slategrey",
  "darkslategray",
  "darkslategrey",
  "silver",
  "gainsboro",
  "whitesmoke",
  "ghostwhite",
  "snow",
]);

const NON_NEUTRAL_NAMED_COLORS = new Set([
  "red", "blue", "green", "yellow", "orange", "purple", "pink", "cyan", "magenta",
  "brown", "navy", "teal", "olive", "maroon", "aqua", "fuchsia", "lime", "crimson",
  "coral", "gold", "indigo", "violet", "khaki", "plum", "salmon", "tan", "turquoise",
  "tomato", "wheat", "azure", "beige", "bisque", "chartreuse", "chocolate", "cornflowerblue",
  "darkblue", "darkcyan", "darkgoldenrod", "darkgreen", "darkkhaki", "darkmagenta",
  "darkolivegreen", "darkorange", "darkorchid", "darkred", "darksalmon", "darkseagreen",
  "darkturquoise", "darkviolet", "deeppink", "deepskyblue", "dodgerblue", "firebrick",
  "forestgreen", "goldenrod", "greenyellow", "hotpink", "indianred", "lawngreen",
  "lightblue", "lightcoral", "lightcyan", "lightgoldenrodyellow", "lightgreen",
  "lightpink", "lightsalmon", "lightseagreen", "lightskyblue", "lightsteelblue",
  "lightyellow", "limegreen", "mediumaquamarine", "mediumblue", "mediumorchid",
  "mediumpurple", "mediumseagreen", "mediumslateblue", "mediumspringgreen",
  "mediumturquoise", "mediumvioletred", "midnightblue", "mintcream", "moccasin",
  "navajowhite", "olivedrab", "orangered", "orchid", "palegoldenrod", "palegreen",
  "paleturquoise", "palevioletred", "papayawhip", "peachpuff", "peru", "powderblue",
  "rosybrown", "royalblue", "saddlebrown", "sandybrown", "seagreen", "seashell",
  "sienna", "skyblue", "slateblue", "springgreen", "steelblue", "yellowgreen",
]);

const BORDER_STYLES = new Set([
  "none", "hidden", "dotted", "dashed", "solid", "double", "groove", "ridge", "inset", "outset",
]);

const SKIP_DIRS = new Set([
  "node_modules",
  "dist",
  ".git",
  ".venv",
  ".pytest_cache",
  ".ruff_cache",
  ".worktrees",
  ".dm-shots",
  ".tmp",
  "coverage",
]);

const CANDIDATE_EXTENSIONS = new Set([
  ".css",
  ".html",
  ".htm",
  ".vue",
  ".svelte",
  ".jsx",
  ".tsx",
  ".js",
  ".mjs",
  ".cjs",
  ".ts",
]);

// --- Color parsing and Chroma measurement -----------------------------------

// Raw colour literals: hex and the CSS colour functions. Shared with
// check-colors.mjs, which bans them from app CSS outright.
export const COLOR_LITERAL =
  /#(?:[0-9a-f]{8}|[0-9a-f]{6}|[0-9a-f]{3,4})\b|\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\([^()]*(?:\([^()]*\)[^()]*)*\)/gi;

function parseRgb(colorStr) {
  const s = colorStr.trim();
  if (s.startsWith("#")) {
    const hex = s.slice(1);
    if (hex.length === 3 || hex.length === 4) {
      const r = parseInt(hex[0] + hex[0], 16);
      const g = parseInt(hex[1] + hex[1], 16);
      const b = parseInt(hex[2] + hex[2], 16);
      return { r, g, b };
    }
    if (hex.length === 6 || hex.length === 8) {
      const r = parseInt(hex.slice(0, 2), 16);
      const g = parseInt(hex.slice(2, 4), 16);
      const b = parseInt(hex.slice(4, 6), 16);
      return { r, g, b };
    }
  }

  const rgbMatch = s.match(/^rgba?\(\s*([\d.]+%?)\s*[, ]\s*([\d.]+%?)\s*[, ]\s*([\d.]+%?)(?:\s*[/,]\s*[\d.]+%?)?\s*\)$/i);
  if (rgbMatch) {
    const parseComponent = (c) => (c.endsWith("%") ? (parseFloat(c) / 100) * 255 : parseFloat(c));
    return {
      r: parseComponent(rgbMatch[1]),
      g: parseComponent(rgbMatch[2]),
      b: parseComponent(rgbMatch[3]),
    };
  }

  return null;
}

// Determines if a color has noticeable chroma / saturation.
// Sane threshold: max-min delta > 25 and HSL saturation > 18%.
// Neutral grays, slates, and dark backgrounds have low delta (<= 20) and pass.
function hasNoticeableChroma(colorStr, customProps = new Map(), visited = new Set()) {
  const s = colorStr.trim().replace(/!important/g, "").trim();
  if (!s) return { colored: false };

  // A compound value (outline shorthand, a shadow) is coloured when any of
  // its parts is: `2px dashed #3b82f6`, `inset 0 0 0 1px rgba(...)`.
  const parts = tokenizeValue(s);
  if (parts.length > 1) {
    for (const part of parts) {
      const res = hasNoticeableChroma(part, customProps, visited);
      if (res.colored) return res;
    }
    return { colored: false };
  }

  const lower = s.toLowerCase();
  if (NEUTRAL_KEYWORDS.has(lower)) {
    return { colored: false };
  }

  if (NON_NEUTRAL_NAMED_COLORS.has(lower)) {
    return { colored: true, reason: `named color '${s}' has noticeable chroma` };
  }

  // Check var(...) references
  const varMatches = [...s.matchAll(/var\(\s*(--[a-zA-Z0-9_-]+)/g)];
  if (varMatches.length > 0) {
    for (const m of varMatches) {
      const varName = m[1];
      if (REMOVED_BORDER_ROLES.has(varName)) {
        return { colored: true, reason: `removed role ${varName} is forbidden` };
      }
      if (varName.startsWith("--dk-")) {
        if (!NEUTRAL_BORDER_ROLES.has(varName)) {
          return { colored: true, reason: `var(${varName}) is not a neutral border role` };
        }
      } else {
        // Site-local custom property
        if (visited.has(varName)) continue;
        visited.add(varName);
        if (customProps.has(varName)) {
          const defs = customProps.get(varName);
          for (const def of defs) {
            const res = hasNoticeableChroma(def, customProps, new Set(visited));
            if (res.colored) {
              return { colored: true, reason: `${varName} resolves to '${def}' (${res.reason})` };
            }
          }
        } else if (/(accent|danger|warning|success|info|color|red|blue|green|amber)/i.test(varName)) {
          return { colored: true, reason: `unresolved variable ${varName} appears to be colored` };
        }
      }
    }
    // A raw fallback inside var(--role, #3b82f6) is still a colour.
    for (const literal of s.match(COLOR_LITERAL) || []) {
      const res = hasNoticeableChroma(literal, customProps, visited);
      if (res.colored) return { colored: true, reason: `fallback ${res.reason}` };
    }
    // If all var(...) references inside the color string are neutral
    if (s.startsWith("var(")) {
      return { colored: false };
    }
  }

  // Check HSL
  const hslMatch = s.match(/^hsla?\(\s*[\d.]+(?:deg)?\s*[, ]\s*([\d.]+)%\s*[, ]\s*([\d.]+)%/i);
  if (hslMatch) {
    const sat = parseFloat(hslMatch[1]);
    const light = parseFloat(hslMatch[2]);
    if (sat > 18 && light > 4 && light < 96) {
      return { colored: true, reason: `hsl color '${s}' has noticeable chroma (${sat}% saturation)` };
    }
    return { colored: false };
  }

  // Check OKLCH
  const oklchMatch = s.match(/^oklch\(\s*[\d.]+%?\s+([\d.]+)/i);
  if (oklchMatch) {
    const chroma = parseFloat(oklchMatch[1]);
    if (chroma > 0.03) {
      return { colored: true, reason: `oklch color '${s}' has noticeable chroma (${chroma})` };
    }
    return { colored: false };
  }

  // Check Hex / RGB
  const rgb = parseRgb(s);
  if (rgb) {
    const delta = Math.max(rgb.r, rgb.g, rgb.b) - Math.min(rgb.r, rgb.g, rgb.b);
    if (delta <= 20) return { colored: false };
    const l = (Math.max(rgb.r, rgb.g, rgb.b) + Math.min(rgb.r, rgb.g, rgb.b)) / 510;
    const sat = (delta / 255) / (1 - Math.abs(2 * l - 1));
    if (delta > 25 && sat > 0.18) {
      return {
        colored: true,
        reason: `color '${s}' has noticeable chroma (saturation ${(sat * 100).toFixed(0)}%, delta ${delta})`,
      };
    }
    return { colored: false };
  }

  return { colored: false };
}

// Tokenize value keeping parentheses intact
function tokenizeValue(val) {
  const tokens = [];
  let cur = "";
  let paren = 0;
  for (let i = 0; i < val.length; i++) {
    const c = val[i];
    if (c === "(") paren++;
    else if (c === ")") {
      if (paren > 0) paren--;
    }
    if (paren === 0 && /\s/.test(c)) {
      if (cur.trim()) tokens.push(cur.trim());
      cur = "";
    } else {
      cur += c;
    }
  }
  if (cur.trim()) tokens.push(cur.trim());
  return tokens;
}

// Parses numeric width in px equivalent. Returns number (e.g. 1, 3, 0) or null.
function parseWidthNumber(token) {
  const t = token.toLowerCase();
  if (t === "0" || t === "none") return 0;
  if (t === "thin") return 1;
  if (t === "medium") return 3;
  if (t === "thick") return 5;

  const m = t.match(/^([\d.]+)(px|rem|em|pt)?$/);
  if (!m) return null;
  const num = parseFloat(m[1]);
  const unit = m[2] || "px";
  if (unit === "px") return num;
  if (unit === "pt") return num * 1.333;
  if (unit === "rem" || unit === "em") return num * 16;
  return num;
}

function parseBorderShorthand(val) {
  const tokens = tokenizeValue(val);
  let width = null;
  let style = null;
  const colorTokens = [];

  for (const tok of tokens) {
    if (BORDER_STYLES.has(tok.toLowerCase())) {
      style = tok;
      continue;
    }
    const w = parseWidthNumber(tok);
    if (w !== null && width === null) {
      width = { text: tok, px: w };
      continue;
    }
    colorTokens.push(tok);
  }

  const color = colorTokens.length > 0 ? colorTokens.join(" ") : null;
  return { width, style, color };
}

// --- CSS Parsing ------------------------------------------------------------

function stripComments(src) {
  // Replace comment contents with spaces/newlines to preserve line numbers
  return src.replace(/\/\*[\s\S]*?\*\//g, (match) => {
    return match.replace(/[^\n]/g, " ");
  });
}

function parseCssRules(cssText, startLine = 1, file = "") {
  const declarations = [];
  const text = stripComments(cssText);

  let line = startLine;
  let inQuote = null;
  let parenDepth = 0;
  const scopeStack = [];
  let buffer = "";
  let declStartLine = line;

  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (c === "\n") line++;

    if (inQuote) {
      if (c === "\\") {
        buffer += c;
        if (i + 1 < text.length) {
          i++;
          if (text[i] === "\n") line++;
          buffer += text[i];
        }
        continue;
      }
      if (c === inQuote) inQuote = null;
      buffer += c;
      continue;
    }

    if (c === '"' || c === "'") {
      inQuote = c;
      buffer += c;
      continue;
    }

    if (c === "(") {
      parenDepth++;
      buffer += c;
      continue;
    }
    if (c === ")") {
      if (parenDepth > 0) parenDepth--;
      buffer += c;
      continue;
    }

    if (parenDepth === 0) {
      if (c === "{") {
        const selector = buffer.trim();
        scopeStack.push(selector);
        buffer = "";
        declStartLine = line;
        continue;
      }
      if (c === "}") {
        const decl = buffer.trim();
        if (decl.includes(":")) {
          emitDeclaration(declarations, decl, scopeStack, declStartLine, file);
        }
        scopeStack.pop();
        buffer = "";
        declStartLine = line;
        continue;
      }
      if (c === ";") {
        const decl = buffer.trim();
        if (decl.includes(":")) {
          emitDeclaration(declarations, decl, scopeStack, declStartLine, file);
        }
        buffer = "";
        declStartLine = line;
        continue;
      }
    }

    if (buffer.length === 0 && !/\s/.test(c)) {
      declStartLine = line;
    }
    buffer += c;
  }

  const trailing = buffer.trim();
  if (trailing.includes(":")) {
    emitDeclaration(declarations, trailing, scopeStack, declStartLine, file);
  }

  return declarations;
}

function emitDeclaration(list, declStr, scopeStack, line, file) {
  const colon = declStr.indexOf(":");
  if (colon === -1) return;
  const prop = declStr.slice(0, colon).trim().toLowerCase();
  const val = declStr.slice(colon + 1).trim();
  const selector = scopeStack.join(" ");
  const rule = scopeStack[scopeStack.length - 1] || "";
  list.push({ property: prop, value: val, selector, rule, line, file });
}

function parseInlineStyles(styleAttr, line, file) {
  const declarations = [];
  const parts = [];
  let cur = "";
  let paren = 0;
  let inQuote = null;

  for (let i = 0; i < styleAttr.length; i++) {
    const c = styleAttr[i];
    if (inQuote) {
      if (c === inQuote) inQuote = null;
      cur += c;
      continue;
    }
    if (c === '"' || c === "'") {
      inQuote = c;
      cur += c;
      continue;
    }
    if (c === "(") paren++;
    else if (c === ")") {
      if (paren > 0) paren--;
    }

    if (c === ";" && paren === 0) {
      if (cur.trim()) parts.push(cur.trim());
      cur = "";
    } else {
      cur += c;
    }
  }
  if (cur.trim()) parts.push(cur.trim());

  for (const part of parts) {
    const colon = part.indexOf(":");
    if (colon !== -1) {
      const prop = part.slice(0, colon).trim().toLowerCase();
      const val = part.slice(colon + 1).trim();
      declarations.push({ property: prop, value: val, selector: "[style attribute]", line, file });
    }
  }

  return declarations;
}

// Extracts CSS declarations from files of various formats. A JS template
// literal is read as CSS only when it declares one of `templateProps`.
export function extractDeclarations(filePath, templateProps = /(border|outline|box-shadow)\s*:/i) {
  const content = readFileSync(filePath, "utf8");
  const ext = extname(filePath).toLowerCase();

  if (ext === ".css") {
    return parseCssRules(content, 1, filePath);
  }

  const declarations = [];

  // 1. <style> blocks
  const styleTagRegex = /<style\b[^>]*>([\s\S]*?)<\/style>/gi;
  let match;
  while ((match = styleTagRegex.exec(content)) !== null) {
    const upToMatch = content.slice(0, match.index);
    const startLine = upToMatch.split("\n").length;
    declarations.push(...parseCssRules(match[1], startLine, filePath));
  }

  // 2. style="..." and style='...' attributes
  const styleAttrRegex = /\bstyle\s*=\s*(["'])([\s\S]*?)\1/gi;
  while ((match = styleAttrRegex.exec(content)) !== null) {
    const upToMatch = content.slice(0, match.index);
    const startLine = upToMatch.split("\n").length;
    declarations.push(...parseInlineStyles(match[2], startLine, filePath));
  }

  // 3. Template literals in JS/TS files containing CSS rules
  if ([".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"].includes(ext)) {
    const templateLitRegex = /`([\s\S]*?)`/g;
    while ((match = templateLitRegex.exec(content)) !== null) {
      const templateContent = match[1];
      // If it contains border or box-shadow and rule blocks
      if (templateProps.test(templateContent)) {
        const upToMatch = content.slice(0, match.index);
        const startLine = upToMatch.split("\n").length;
        if (templateContent.includes("{") && templateContent.includes("}")) {
          declarations.push(...parseCssRules(templateContent, startLine, filePath));
        } else {
          declarations.push(...parseInlineStyles(templateContent, startLine, filePath));
        }
      }
    }
  }

  return declarations;
}

// --- File Discovery ---------------------------------------------------------

function isVendoredDakit(fullPath) {
  const p = fullPath.replace(/\\/g, "/");
  const base = basename(p);

  // Skip vendored dakit assets in consuming projects
  if (base.startsWith("dakit-") || base === "dakit.css" || base === "dakit.js") {
    // Only skip if outside dakit's own css/ directory
    if (!p.includes("/dakit/css/")) return true;
  }
  if (p.includes("/static/dakit/") || p.includes("/src/dakit/") || p.includes("/web/vendor/")) {
    return true;
  }
  return false;
}

export function collectFiles(targetPath, out = []) {
  const stat = statSync(targetPath);
  if (stat.isFile()) {
    const ext = extname(targetPath).toLowerCase();
    if (CANDIDATE_EXTENSIONS.has(ext) && !isVendoredDakit(targetPath)) {
      out.push(resolve(targetPath));
    }
    return out;
  }

  if (stat.isDirectory()) {
    const base = basename(targetPath);
    if (SKIP_DIRS.has(base)) return out;

    const entries = readdirSync(targetPath);
    for (const entry of entries) {
      if (SKIP_DIRS.has(entry)) continue;
      const sub = join(targetPath, entry);
      if (isVendoredDakit(sub)) continue;
      collectFiles(sub, out);
    }
  }

  return out;
}

// --- Border & Outline Validator ---------------------------------------------

const SINGLE_SIDE_PROPS = new Set([
  "border-top",
  "border-right",
  "border-bottom",
  "border-left",
  "border-inline",
  "border-inline-start",
  "border-inline-end",
  "border-block",
  "border-block-start",
  "border-block-end",
]);

const SINGLE_SIDE_WIDTH_PROPS = new Set([
  "border-top-width",
  "border-right-width",
  "border-bottom-width",
  "border-left-width",
  "border-inline-width",
  "border-inline-start-width",
  "border-inline-end-width",
  "border-block-width",
  "border-block-start-width",
  "border-block-end-width",
]);

const SINGLE_SIDE_COLOR_PROPS = new Set([
  "border-top-color",
  "border-right-color",
  "border-bottom-color",
  "border-left-color",
  "border-inline-color",
  "border-inline-start-color",
  "border-inline-end-color",
  "border-block-color",
  "border-block-start-color",
  "border-block-end-color",
]);

// Every selector in the list must target :focus-visible, so
// `.a, .b:focus-visible { outline: … }` doesn't smuggle a ring onto .a.
function isFocusVisibleRule(rule = "") {
  return splitTopLevel(rule, ",").every((part) => /:focus-visible\b/i.test(part));
}

function splitTopLevel(text, sep) {
  const out = [];
  let cur = "";
  let depth = 0;
  for (const c of text) {
    if (c === "(" || c === "[") depth++;
    else if ((c === ")" || c === "]") && depth > 0) depth--;
    if (c === sep && depth === 0) {
      out.push(cur);
      cur = "";
    } else cur += c;
  }
  out.push(cur);
  return out.map((part) => part.trim()).filter(Boolean);
}

function checkDeclaration(decl, customProps) {
  const { property, value, rule, line, file } = decl;
  const p = property;
  const v = value;

  // 1. Box-Shadow Checks
  if (p === "box-shadow") {
    // Split multiple shadows by comma outside parens
    const shadows = [];
    let cur = "";
    let paren = 0;
    for (let i = 0; i < v.length; i++) {
      const c = v[i];
      if (c === "(") paren++;
      else if (c === ")") {
        if (paren > 0) paren--;
      }
      if (c === "," && paren === 0) {
        if (cur.trim()) shadows.push(cur.trim());
        cur = "";
      } else {
        cur += c;
      }
    }
    if (cur.trim()) shadows.push(cur.trim());

    for (const shadow of shadows) {
      // A spread-only shadow (0 0 0 Npx) draws a ring: a coloured one is an
      // accent perimeter, allowed only as the :focus-visible indicator.
      const lengths = [...shadow.replace(/\([^)]*\)/g, "").matchAll(/(-?[\d.]+)(px|rem|em)?/g)].map((m) => parseFloat(m[1]));
      if (lengths.length >= 4 && lengths[0] === 0 && lengths[1] === 0 && lengths[2] === 0 && lengths[3] !== 0 && !isFocusVisibleRule(rule)) {
        const ring = hasNoticeableChroma(shadow, customProps);
        if (ring.colored) {
          return { file, line, reason: `forbidden colored box-shadow ring '${shadow}' (${ring.reason})` };
        }
      }
      if (/\binset\b/i.test(shadow)) {
        // Condition: box-shadow with inset and a colored value
        const chromaCheck = hasNoticeableChroma(shadow, customProps);
        if (chromaCheck.colored) {
          return {
            file,
            line,
            reason: `forbidden inset box-shadow with colored value '${shadow}' (${chromaCheck.reason})`,
          };
        }

        // Condition: box-shadow used as an edge stripe (e.g. inset Npx 0 0)
        // Extract lengths outside parens
        const withoutParens = shadow.replace(/\([^)]*\)/g, "");
        const lengthMatches = [...withoutParens.matchAll(/(-?[\d.]+)(px|rem|em)?/g)];
        if (lengthMatches.length >= 2) {
          const x = parseFloat(lengthMatches[0][1]);
          const y = parseFloat(lengthMatches[1][1]);
          const blur = lengthMatches.length >= 3 ? parseFloat(lengthMatches[2][1]) : 0;
          if (((x !== 0 && y === 0) || (x === 0 && y !== 0)) && blur === 0) {
            return {
              file,
              line,
              reason: `forbidden inset box-shadow edge stripe '${shadow}'`,
            };
          }
        }
      }
    }
    return null;
  }

  // 2. Outline Checks: only the keyboard focus ring may be coloured.
  if (p === "outline" || p === "outline-color") {
    if (!isFocusVisibleRule(rule)) {
      const chroma = hasNoticeableChroma(v, customProps);
      if (chroma.colored) {
        return {
          file,
          line,
          reason: `forbidden colored outline outside :focus-visible '${v}' (${chroma.reason})`,
        };
      }
    }
    return null;
  }

  // 3. Single-Side Border Width Properties
  if (SINGLE_SIDE_WIDTH_PROPS.has(p)) {
    const w = parseWidthNumber(v);
    if (w !== null && w > 1) {
      return {
        file,
        line,
        reason: `forbidden single-side border width: ${p}: ${v} exceeds 1px`,
      };
    }
    return null;
  }

  // 4. Single-Side Border Color Properties
  if (SINGLE_SIDE_COLOR_PROPS.has(p)) {
    const chroma = hasNoticeableChroma(v, customProps);
    if (chroma.colored) {
      return {
        file,
        line,
        reason: `forbidden colored single-side border: ${p}: ${v} (${chroma.reason})`,
      };
    }
    return null;
  }

  // 5. Single-Side Border Shorthand Properties
  if (SINGLE_SIDE_PROPS.has(p)) {
    const parsed = parseBorderShorthand(v);
    if (parsed.width && parsed.width.px > 1) {
      return {
        file,
        line,
        reason: `forbidden single-side border width: ${p}: ${v} is wider than 1px (${parsed.width.text})`,
      };
    }
    if (parsed.color) {
      const chroma = hasNoticeableChroma(parsed.color, customProps);
      if (chroma.colored) {
        return {
          file,
          line,
          reason: `forbidden colored single-side border: ${p}: ${v} (${chroma.reason})`,
        };
      }
    }
    return null;
  }

  // 6. Perimeter Border Width Properties
  if (p === "border-width") {
    const tokens = tokenizeValue(v);
    for (const tok of tokens) {
      const w = parseWidthNumber(tok);
      if (w !== null && w > 1) {
        return {
          file,
          line,
          reason: `forbidden border-width: ${v} exceeds 1px`,
        };
      }
    }
    return null;
  }

  // 7. Perimeter Border Color Properties
  if (p === "border-color") {
    const tokens = tokenizeValue(v);
    for (const tok of tokens) {
      const chroma = hasNoticeableChroma(tok, customProps);
      if (chroma.colored) {
        return {
          file,
          line,
          reason: `forbidden accent border-color: ${v} (${chroma.reason})`,
        };
      }
    }
    return null;
  }

  // 8. Perimeter Border Shorthand Properties
  if (p === "border") {
    const parsed = parseBorderShorthand(v);
    if (parsed.width && parsed.width.px > 1) {
      return {
        file,
        line,
        reason: `forbidden border width: ${v} is wider than 1px (${parsed.width.text})`,
      };
    }
    if (parsed.color) {
      const chroma = hasNoticeableChroma(parsed.color, customProps);
      if (chroma.colored) {
        return {
          file,
          line,
          reason: `forbidden accent border: ${v} (${chroma.reason})`,
        };
      }
    }
    return null;
  }

  return null;
}

// --- Main Engine ------------------------------------------------------------

export function checkBorders(paths = []) {
  if (paths.length === 0) return [];

  const allFiles = [];
  for (const p of paths) {
    collectFiles(p, allFiles);
  }

  // Pass 1: Collect site-local custom property definitions across all files
  const customProps = new Map();
  const fileDeclarations = [];

  for (const file of allFiles) {
    try {
      const decls = extractDeclarations(file);
      fileDeclarations.push(...decls);
      for (const d of decls) {
        if (d.property.startsWith("--")) {
          if (!customProps.has(d.property)) {
            customProps.set(d.property, new Set());
          }
          customProps.get(d.property).add(d.value);
        }
      }
    } catch (err) {
      console.warn(`warning: failed to read/parse ${file}: ${err.message}`);
    }
  }

  // Pass 2: Validate each declaration against border rules
  const violations = [];
  for (const decl of fileDeclarations) {
    const violation = checkDeclaration(decl, customProps);
    if (violation) {
      violations.push(violation);
    }
  }

  return violations;
}

// --- CLI Runner -------------------------------------------------------------

function runCli() {
  const args = process.argv.slice(2);
  if (args.length === 0) {
    console.error("Usage: node scripts/check-borders.mjs <paths...>");
    process.exit(1);
  }

  const violations = checkBorders(args);

  if (violations.length > 0) {
    for (const v of violations) {
      console.error(`${v.file}:${v.line}: ${v.reason}`);
    }
    console.error(`\nFAIL: found ${violations.length} border rule violation(s).`);
    process.exit(1);
  } else {
    console.log("PASS: no border violations found.");
    process.exit(0);
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  runCli();
}
