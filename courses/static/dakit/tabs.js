/* dakit 0.2.0 0e283cd */
/* dakit segmented control (docs/segmented.md): keyboard for the two
   single-choice roles a .dk-tabs track can carry.

     role="tablist"     segments are role="tab" + aria-selected (views)
     role="radiogroup"  segments are role="radio" + aria-checked (filters)

   One segment is in the tab order (roving tabindex); ←/→ (↑/↓ too), Home
   and End move to the neighbour and choose it at once by clicking it, so the
   app's own click handler stays the only place a choice is made. Disabled
   segments are skipped. If the app re-renders the track on that click, focus
   follows to the same segment in the new track (matched by the track's id or
   aria-label). Route tabs (<nav> of links with aria-current) and
   aria-pressed toggles keep plain Tab order and get nothing from this file.

   Classic script with an idempotent global guard, like shell.js. Listeners
   are delegated on document, so tracks rendered later work without re-init;
   dakitTabs.sync(root) fixes tabindex on tracks the app has just rendered
   (it also runs on load and on the first focus into a track). */
(function () {
  "use strict";
  if (globalThis.dakitTabs) return;

  var GROUP = '.dk-tabs[role="tablist"], .dk-tabs[role="radiogroup"]';
  var KEYS = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1, Home: "first", End: "last" };

  function segments(group) {
    var role = group.getAttribute("role") === "radiogroup" ? "radio" : "tab";
    return Array.prototype.filter.call(group.querySelectorAll('[role="' + role + '"]'), function (el) {
      return el.closest(".dk-tabs") === group;
    });
  }
  function enabled(el) { return !el.hidden && !el.disabled && el.getAttribute("aria-disabled") !== "true"; }
  function isSelected(el) { return el.getAttribute("aria-selected") === "true" || el.getAttribute("aria-checked") === "true"; }

  // Exactly one segment is tabbable: the selected one, else the first enabled.
  function sync(group) {
    var all = segments(group);
    var current = all.filter(function (el) { return isSelected(el) && enabled(el); })[0] || all.filter(enabled)[0];
    all.forEach(function (el) { el.setAttribute("tabindex", el === current ? "0" : "-1"); });
    return current;
  }
  function syncAll(root) {
    var scope = root && root.querySelectorAll ? root : document;
    if (scope.matches && scope.matches(GROUP)) sync(scope);
    Array.prototype.forEach.call(scope.querySelectorAll(GROUP), sync);
  }

  // Keep the chosen segment visible inside a track that scrolls (phones).
  function reveal(el) {
    var track = el.closest(".dk-tabs");
    if (!track || track.scrollWidth <= track.clientWidth) return;
    var left = el.offsetLeft - track.offsetLeft;
    if (left < track.scrollLeft) track.scrollLeft = left - 8;
    else if (left + el.offsetWidth > track.scrollLeft + track.clientWidth) track.scrollLeft = left + el.offsetWidth - track.clientWidth + 8;
  }

  function key(group) {
    if (group.id) return "#" + CSS.escape(group.id);
    var label = group.getAttribute("aria-label");
    return label ? '.dk-tabs[aria-label="' + CSS.escape(label) + '"]' : null;
  }

  // After the click the app may have replaced the track; find the same
  // segment (by index) in the new one and put focus there.
  function follow(selector, index) {
    var group = selector && document.querySelector(selector);
    if (!group) return;
    var target = segments(group)[index] || sync(group);
    if (!target) return;
    sync(group);
    target.focus();
    reveal(target);
  }

  function choose(group, target) {
    var all = segments(group);
    var index = all.indexOf(target);
    var selector = key(group);
    all.forEach(function (el) { el.setAttribute("tabindex", el === target ? "0" : "-1"); });
    target.focus();
    reveal(target);
    target.click();
    if (target.isConnected && group.isConnected) { sync(group); return; }
    if (document.activeElement && document.activeElement !== document.body) return;
    follow(selector, index);
    // An async re-render lands a frame later.
    requestAnimationFrame(function () {
      if (document.activeElement && document.activeElement !== document.body) return;
      follow(selector, index);
    });
  }

  document.addEventListener("keydown", function (event) {
    if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey) return;
    var step = KEYS[event.key];
    if (!step) return;
    var group = event.target.closest && event.target.closest(GROUP);
    if (!group) return;
    var all = segments(group);
    var from = all.indexOf(event.target);
    if (from < 0) return;
    var usable = all.filter(enabled);
    if (!usable.length) return;
    var target;
    if (step === "first") target = usable[0];
    else if (step === "last") target = usable[usable.length - 1];
    else {
      var rtl = getComputedStyle(group).direction === "rtl";
      var dir = (event.key === "ArrowLeft" || event.key === "ArrowRight") && rtl ? -step : step;
      for (var i = 1; i <= all.length; i += 1) {
        var candidate = all[(from + dir * i + all.length * i) % all.length];
        if (enabled(candidate)) { target = candidate; break; }
      }
    }
    event.preventDefault();
    if (!target || target === event.target) return;
    choose(group, target);
  });

  // A track rendered after load gets its tabindex fixed when focus first
  // reaches it, before the user can Tab past an unselected segment twice.
  document.addEventListener("focusin", function (event) {
    var group = event.target.closest && event.target.closest(GROUP);
    if (group && !group.hasAttribute("data-dk-tabs-synced")) {
      group.setAttribute("data-dk-tabs-synced", "");
      sync(group);
    }
  });

  // A click (mouse or touch) moves the roving stop with the choice.
  document.addEventListener("click", function (event) {
    var group = event.target.closest && event.target.closest(GROUP);
    if (!group) return;
    var seg = segments(group).filter(function (el) { return el.contains(event.target); })[0];
    if (!seg || !enabled(seg) || !seg.isConnected) return;
    segments(group).forEach(function (el) { el.setAttribute("tabindex", el === seg ? "0" : "-1"); });
  });

  function init() {
    syncAll(document);
    Array.prototype.forEach.call(document.querySelectorAll(".dk-tabs"), function (track) {
      var current = track.querySelector('[aria-current="page"], [aria-selected="true"], [aria-checked="true"]');
      if (current) reveal(current);
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();

  globalThis.dakitTabs = { sync: syncAll, reveal: reveal };
})();
