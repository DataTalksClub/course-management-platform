/* dakit 0.2.0 0e283cd */
// Dakit device-login code helpers — the contract is docs/device-login.md.
//
// ES module; pure functions plus one optional input binder. Usable in the
// browser (<script type="module">) and server-side (Node, workers):
//   import { normalizeUserCode, formatUserCode, bindCodeInput } from "dakit/dist/device-code.js";
//
// Rules: case-insensitive, separators ignored, NEVER truncate — an overlong
// or invalid code is an error the page shows, not something silently fixed.

export const USER_CODE_ALPHABET = "BCDFGHJKMNPQRSTWXZ23456789"; // no vowels, no L/V, no 0/1
export const USER_CODE_LENGTH = 8;

const SEPARATORS = /[\s\-‐-―−._]/g;

const strip = (raw) => String(raw ?? "").replace(SEPARATORS, "").toUpperCase();

// Display form: uppercase, separators removed, a hyphen after every 4th char.
// Keeps every character, invalid and overflow included.
export function formatUserCode(raw) {
  return strip(raw).replace(/(.{4})(?=.)/g, "$1-");
}

// → { ok: true, code, display }
// → { ok: false, error: "empty" | "too_short" | "too_long" | "invalid_char", length, char?, display }
export function normalizeUserCode(raw, { alphabet = USER_CODE_ALPHABET, length = USER_CODE_LENGTH } = {}) {
  const code = strip(raw);
  const display = formatUserCode(raw);
  if (!code) return { ok: false, error: "empty", length: 0, display };
  const bad = [...code].find((ch) => !alphabet.includes(ch));
  if (bad) return { ok: false, error: "invalid_char", char: bad, length: code.length, display };
  if (code.length < length) return { ok: false, error: "too_short", length: code.length, display };
  if (code.length > length) return { ok: false, error: "too_long", length: code.length, display };
  return { ok: true, code, display };
}

// One human sentence per result (docs/device-login.md §4.1); "" when ok/empty.
export function describeUserCodeError(result, { length = USER_CODE_LENGTH } = {}) {
  if (!result || result.ok || result.error === "empty") return "";
  if (result.error === "invalid_char") {
    const what = /[0-9]/.test(result.char) ? `the digit “${result.char}”` : /[A-Z]/.test(result.char) ? `the letter “${result.char}”` : `“${result.char}”`;
    return `Codes don't use ${what}. Check the code in your terminal.`;
  }
  if (result.error === "too_short") return `Codes have ${length} characters. This one has ${result.length}.`;
  return `Codes have ${length} characters. This one has ${result.length}. Check for an extra character.`;
}

// Formats an <input> as the person types, keeping the caret next to the same
// character, and dispatches "dk-code-change" (detail = normalizeUserCode result).
// Returns an unbind function.
export function bindCodeInput(input, options = {}) {
  const meaningful = (text) => text.replace(SEPARATORS, "").length;
  const update = () => {
    const raw = input.value;
    const caret = input.selectionStart ?? raw.length;
    const before = meaningful(raw.slice(0, caret));
    const formatted = formatUserCode(raw);
    if (formatted !== raw) {
      input.value = formatted;
      let pos = 0;
      for (let seen = 0; pos < formatted.length && seen < before; pos++) if (formatted[pos] !== "-") seen++;
      if (document.activeElement === input) input.setSelectionRange(pos, pos);
    }
    input.dispatchEvent(new CustomEvent("dk-code-change", { detail: normalizeUserCode(formatted, options) }));
  };
  input.addEventListener("input", update);
  if (input.value) update();
  return () => input.removeEventListener("input", update);
}
