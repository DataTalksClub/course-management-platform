/* dakit 0.2.0 0e283cd */
// Dakit avatar: a person's initials, with their photo on top when there is one.
//
// ES module, no globals:
//   import { createAvatar, updateAvatar, avatarInitials } from "dakit/dist/avatar.js";
//
//   createAvatar({ name: "Orin Vale", src, size: "xs" })   → <span class="dk-avatar dk-avatar--xs">
//   updateAvatar(element, { name, src }, document?)        re-point an existing .dk-avatar
//
// The initials are always rendered. The photo is an <img> laid over them, so
// while it loads, when there is none, and after it fails to load, the avatar
// still reads as the person. A failed photo is removed, not left as a broken
// image. The photo is requested with no referrer: photo hosts such as Google's
// may refuse hotlinked requests that carry one, and the page URL is nobody
// else's business.
//
// The avatar is decorative (aria-hidden): the caller puts the name next to
// it or on the owning element's accessible label.

const SIZES = new Set(["xs", "sm", "lg"]);

// One person, up to two letters: the first letter of the first two words,
// uppercased; "?" for an empty name.
export function avatarInitials(name) {
  const parts = String(name ?? "").trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  return parts.slice(0, 2).map((part) => [...part][0]).join("").toUpperCase();
}

// Only an absolute https URL becomes an <img>; anything else (empty, relative,
// http, data:, javascript:) leaves the initials alone.
function photoUrl(src) {
  if (!src) return "";
  try {
    const url = new URL(String(src));
    return url.protocol === "https:" ? url.href : "";
  } catch {
    return "";
  }
}

// The document defaults to the element's own; pass it for detached or test
// documents. An unchanged avatar keeps its nodes: shell menus decide
// "inside or outside" from the click target, so a re-render must not swap
// the node under the pointer.
export function updateAvatar(element, { name = "", initials, src = "" } = {}, doc = element.ownerDocument) {
  const href = photoUrl(src);
  const letters = initials || avatarInitials(name);
  let label = element.querySelector(".dk-avatar__initials");
  if (!label) {
    label = doc.createElement("span");
    label.className = "dk-avatar__initials";
  }
  if (label.textContent !== letters) label.textContent = letters;
  // A photo that already failed here is not fetched again on every render.
  const failed = Boolean(href) && element.dataset.avatarFailedSrc === href;
  const current = element.querySelector("img");
  const img = !href || failed ? null : current?.getAttribute("src") === href ? current : photo(doc, element, href);
  const wanted = img ? [label, img] : [label];
  const present = [...(element.childNodes || element.children)];
  if (present.length !== wanted.length || wanted.some((node, index) => present[index] !== node)) {
    element.replaceChildren(...wanted);
  }
  element.setAttribute("aria-hidden", "true");
  element.classList.toggle("dk-avatar--photo", Boolean(img));
  if (img) element.dataset.avatarPhoto = "shown";
  else if (failed) element.dataset.avatarPhoto = "failed";
  else delete element.dataset.avatarPhoto;
  return element;
}

function photo(doc, element, href) {
  const img = doc.createElement("img");
  img.alt = "";
  img.decoding = "async";
  img.setAttribute("referrerpolicy", "no-referrer");
  img.addEventListener("error", () => {
    img.remove();
    element.classList.remove("dk-avatar--photo");
    element.dataset.avatarPhoto = "failed";
    element.dataset.avatarFailedSrc = href;
  }, { once: true });
  img.setAttribute("src", href);
  return img;
}

export function createAvatar({ document: doc = globalThis.document, name = "", initials, src = "", size = "", className = "" } = {}) {
  const element = doc.createElement("span");
  element.className = ["dk-avatar", SIZES.has(size) ? `dk-avatar--${size}` : "", className].filter(Boolean).join(" ");
  return updateAvatar(element, { name, initials, src }, doc);
}
