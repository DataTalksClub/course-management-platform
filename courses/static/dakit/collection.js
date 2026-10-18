/* dakit 0.2.0 0e283cd */
/* dakit collection header (docs/guidelines.md "Action placement"): a create
   action belongs to the collection it creates into, right after that
   collection's title, never in the page header's far corner.

     dakitCollection.header({ title, meta, create, actions })   DOM header
     dakitCollection.createButton({ label, onClick })            "+ Label" button
     dakitCollection.headerMarkup({ title, meta, createHtml, actionsHtml })
     dakitCollection.createButtonMarkup({ label, attributes })   string twins

   The page's one create button carries data-dk-create, aria-keyshortcuts="c"
   and a "(C)" title; pressing c clicks the first visible, enabled one. The
   shortcut is ignored while the user types in a field, with a modifier held,
   on key repeat, or while a dialog or a visible aria-modal panel is open. Building a shortcut button arms
   the listener once per document, so pages rendered later need no init.

   Classic script with an idempotent global guard, like shell.js. Pass
   `document` to build into another document (tests, iframes). */
(function () {
  "use strict";
  if (globalThis.dakitCollection) return;

  var ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>';
  var armed = typeof WeakSet === "function" ? new WeakSet() : null;

  function escape(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function docOf(options) { return (options && options.document) || globalThis.document; }

  function typing(target) {
    if (!target || typeof target.closest !== "function") return false;
    return Boolean(target.isContentEditable ||
      target.closest("input, textarea, select, [contenteditable]:not([contenteditable='false'])"));
  }

  function installShortcut(doc) {
    doc = doc || globalThis.document;
    if (!doc || typeof doc.addEventListener !== "function" || !armed || armed.has(doc)) return;
    armed.add(doc);
    doc.addEventListener("keydown", function (event) {
      if (event.defaultPrevented || event.repeat) return;
      if (event.metaKey || event.ctrlKey || event.altKey || event.shiftKey) return;
      if (event.key !== "c" || typing(event.target)) return;
      // Apps keep popover panels in the page with aria-modal, hidden; only a
      // modal that is showing blocks the shortcut.
      var modal = Array.prototype.some.call(doc.querySelectorAll('dialog[open], [aria-modal="true"]'), function (el) {
        return el.getClientRects().length > 0;
      });
      if (modal) return;
      var button = Array.prototype.filter.call(doc.querySelectorAll("[data-dk-create]"), function (el) {
        return !el.disabled && el.getClientRects().length > 0;
      })[0];
      if (!button) return;
      event.preventDefault();
      button.click();
    });
  }

  function classes(variant, className) {
    return "dk-button dk-button--" + (variant || "primary") + " dk-button--sm dk-collection-create" +
      (className ? " " + className : "");
  }

  // Only application-authored attributes belong in `attributes`.
  function createButtonMarkup(options) {
    var o = options || {};
    var shortcut = o.shortcut !== false;
    if (shortcut) installShortcut(docOf(o));
    var keys = shortcut ? ' data-dk-create aria-keyshortcuts="c" title="' + escape(o.label) + ' (C)"' : "";
    return '<button type="button" class="' + escape(classes(o.variant, o.className)) + '"' + keys +
      (o.attributes ? " " + o.attributes : "") + '><span class="dk-collection-create__icon" aria-hidden="true">' +
      ICON + "</span><span>" + escape(o.label) + "</span></button>";
  }

  function createButton(options) {
    var o = options || {};
    var doc = docOf(o);
    var shortcut = o.shortcut !== false;
    var button = doc.createElement("button");
    button.type = "button";
    button.className = classes(o.variant, o.className);
    var icon = doc.createElement("span");
    icon.className = "dk-collection-create__icon";
    icon.setAttribute("aria-hidden", "true");
    icon.innerHTML = ICON;
    var text = doc.createElement("span");
    text.textContent = o.label;
    button.append(icon, text);
    if (shortcut) {
      button.setAttribute("data-dk-create", "");
      button.setAttribute("aria-keyshortcuts", "c");
      button.title = o.label + " (C)";
      installShortcut(doc);
    }
    if (o.onClick) button.addEventListener("click", o.onClick);
    return button;
  }

  function header(options) {
    var o = options || {};
    var doc = docOf(o);
    var el = doc.createElement("header");
    el.className = "dk-collection-header" + (o.className ? " " + o.className : "");
    var lead = doc.createElement("div");
    lead.className = "dk-collection-header__lead";
    var title = doc.createElement(o.level || "h2");
    title.className = "dk-collection-header__title";
    title.textContent = o.title;
    if (o.titleId) title.id = o.titleId;
    lead.append(title);
    if (o.create) lead.append(o.create);
    el.append(lead);
    var actions = o.actions || [];
    if (o.meta || actions.length) {
      var trail = doc.createElement("div");
      trail.className = "dk-collection-header__trail";
      if (o.meta) {
        var meta = doc.createElement("span");
        meta.className = "dk-collection-header__meta";
        meta.textContent = o.meta;
        trail.append(meta);
      }
      trail.append.apply(trail, actions);
      el.append(trail);
    }
    return el;
  }

  // `createHtml` and `actionsHtml` are markup the app built (createButtonMarkup,
  // its own buttons); title and meta are text and get escaped.
  function headerMarkup(options) {
    var o = options || {};
    var level = /^h[1-6]$/.test(o.level || "") ? o.level : "h2";
    var trail = o.meta || o.actionsHtml
      ? '<div class="dk-collection-header__trail">' +
        (o.meta ? '<span class="dk-collection-header__meta">' + escape(o.meta) + "</span>" : "") +
        (o.actionsHtml || "") + "</div>"
      : "";
    return '<header class="dk-collection-header' + (o.className ? " " + escape(o.className) : "") + '">' +
      '<div class="dk-collection-header__lead"><' + level + ' class="dk-collection-header__title"' +
      (o.titleId ? ' id="' + escape(o.titleId) + '"' : "") + ">" + escape(o.title) + "</" + level + ">" +
      (o.createHtml || "") + "</div>" + trail + "</header>";
  }

  globalThis.dakitCollection = {
    header: header,
    headerMarkup: headerMarkup,
    createButton: createButton,
    createButtonMarkup: createButtonMarkup,
    installShortcut: installShortcut,
  };
})();
