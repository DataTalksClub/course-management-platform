/* dakit 0.2.0 0e283cd */
/* dakit list–detail split (docs/list-detail.md): keyboard movement in the
   list, focus that follows the visible pane, and the optional resize grip.
   Classic script with an idempotent global guard, like shell.js. Listeners
   are delegated on document, so splits rendered later work without re-init.
   Selection, data and the URL stay in the app. */
(function () {
  "use strict";
  if (globalThis.dakitSplit) return;

  var ITEM = ".dk-split__item";
  var MIN = 240;
  var STEP = 16;
  var phone = typeof matchMedia === "function" ? matchMedia("(max-width: 820px)") : { matches: false };

  function read(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }
  function write(key, value) { try { localStorage.setItem(key, value); } catch (e) { /* defaults */ } }
  function storageKey(split) { var k = split.getAttribute("data-dk-split"); return k ? "dk-split:" + k : null; }

  function visible(el) { return !el.hidden && !el.disabled && el.getAttribute("aria-disabled") !== "true" && el.getClientRects().length > 0; }
  function items(split) {
    var list = split.querySelector(".dk-split__list");
    return list ? Array.prototype.filter.call(list.querySelectorAll(ITEM), visible) : [];
  }
  function selected(split) {
    return split.querySelector('.dk-split__list ' + ITEM + '[aria-current="true"], .dk-split__list ' + ITEM + '[aria-current="page"], .dk-split__list ' + ITEM + '[aria-selected="true"]');
  }
  function native(el) { return el.matches("a[href], button, input, select, textarea, summary"); }

  // The detail pane's focus target: [data-dk-autofocus], else its heading.
  function detailTarget(split) {
    var detail = split.querySelector(".dk-split__detail");
    if (!detail) return null;
    var el = detail.querySelector("[data-dk-autofocus]") || detail.querySelector(".dk-split__title, h1, h2, h3");
    if (el && !el.hasAttribute("tabindex") && !native(el)) el.setAttribute("tabindex", "-1");
    return el;
  }

  // Bring the selected row into view inside the list without moving the page.
  function reveal(split) {
    var row = selected(split);
    var scroller = row && row.closest(".dk-split__scroll");
    if (!row || !scroller) return;
    var top = row.offsetTop - scroller.offsetTop;
    if (top < scroller.scrollTop || top + row.offsetHeight > scroller.scrollTop + scroller.clientHeight) {
      scroller.scrollTop = Math.max(0, top - (scroller.clientHeight - row.offsetHeight) / 2);
    }
  }

  // Switch the visible pane on a phone and move focus with it: the detail
  // heading when opening, the row it came from when going back. On desktop
  // both panes show, so focus is left where the person put it.
  function show(split, view, opts) {
    if (!split) return;
    var focus = !opts || opts.focus !== false;
    split.setAttribute("data-view", view === "detail" ? "detail" : "list");
    if (view === "detail") {
      var scroller = split.querySelector(".dk-split__detail .dk-split__scroll");
      if (scroller && (!opts || opts.resetScroll !== false)) scroller.scrollTop = 0;
      if (focus && phone.matches) { var t = detailTarget(split); if (t) t.focus({ preventScroll: true }); }
    } else {
      reveal(split);
      if (focus && phone.matches) { var row = selected(split) || items(split)[0]; if (row) row.focus({ preventScroll: true }); }
    }
  }

  // --- keyboard in the list: ↑/↓ move, Home/End jump, Enter/Space open -----------
  document.addEventListener("keydown", function (event) {
    if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey) return;
    var target = event.target;
    if (!(target instanceof Element)) return;
    var handle = target.closest(".dk-split__handle");
    if (handle) { handleKey(event, handle); return; }
    var item = target.closest(ITEM);
    var split = item && item.closest(".dk-split");
    if (!split || !item.closest(".dk-split__list")) return;
    if (target !== item && target.matches("input, select, textarea, button, a[href], [contenteditable]")) return;
    var all = items(split);
    var i = all.indexOf(item);
    var next = null;
    if (event.key === "ArrowDown") next = all[Math.min(all.length - 1, i + 1)];
    else if (event.key === "ArrowUp") next = all[Math.max(0, i - 1)];
    else if (event.key === "Home") next = all[0];
    else if (event.key === "End") next = all[all.length - 1];
    else if ((event.key === "Enter" || event.key === " ") && !native(item)) { event.preventDefault(); remember(split); item.click(); return; }
    else if (event.key === "Enter") { remember(split); return; }
    else return;
    event.preventDefault();
    if (next && next !== item) next.focus();
  });

  document.addEventListener("click", function (event) {
    var item = event.target instanceof Element && event.target.closest(ITEM);
    var split = item && item.closest(".dk-split");
    if (split) remember(split);
  });

  // Apps re-render the list after a selection, sometimes more than once (a
  // loading pass, then the data); whenever that drops focus to <body> within
  // the next two seconds, put it back on the selected row (or the detail
  // heading on a phone).
  var last = null;
  function remember(split) { last = { split: split, at: Date.now() }; }
  function rescue() {
    if (!last || Date.now() - last.at > 2000) return;
    var active = document.activeElement;
    if (active && active !== document.body && document.contains(active)) return;
    var split = document.contains(last.split) ? last.split : document.querySelector(".dk-split");
    if (!split) return;
    var target = phone.matches && split.getAttribute("data-view") === "detail" ? detailTarget(split) : selected(split);
    if (target) target.focus({ preventScroll: true });
  }

  // --- resize grip ------------------------------------------------------------------
  function bounds(split) { return { min: MIN, max: Math.max(MIN, Math.floor(split.getBoundingClientRect().width / 2)) }; }
  // The width set last, else the laid-out one. Reading the set value first
  // keeps repeated key presses exact while a transition (reduced motion still
  // runs a 0.01ms one) leaves layout a tick behind.
  function current(split) {
    var set = parseFloat(split.style.getPropertyValue("--dk-split-list"));
    if (set > 0) return Math.min(bounds(split).max, Math.max(MIN, set));
    var list = split.querySelector(".dk-split__list");
    return list ? Math.round(list.getBoundingClientRect().width) : MIN;
  }
  function setWidth(split, px, persist) {
    var b = bounds(split);
    var w = Math.round(Math.min(b.max, Math.max(b.min, px)));
    split.style.setProperty("--dk-split-list", w + "px");
    var handle = split.querySelector(".dk-split__handle");
    if (handle) {
      handle.setAttribute("aria-valuenow", String(w));
      handle.setAttribute("aria-valuemin", String(b.min));
      handle.setAttribute("aria-valuemax", String(b.max));
    }
    var key = storageKey(split);
    if (persist !== false && key) write(key, String(w));
    return w;
  }
  function handleKey(event, handle) {
    var split = handle.closest(".dk-split");
    if (!split) return;
    var w = current(split);
    var b = bounds(split);
    var next = null;
    if (event.key === "ArrowLeft") next = w - STEP;
    else if (event.key === "ArrowRight") next = w + STEP;
    else if (event.key === "Home") next = b.min;
    else if (event.key === "End") next = b.max;
    if (next === null) return;
    event.preventDefault();
    setWidth(split, next);
  }
  document.addEventListener("pointerdown", function (event) {
    var handle = event.target instanceof Element && event.target.closest(".dk-split__handle");
    if (!handle || event.button !== 0) return;
    var split = handle.closest(".dk-split");
    var list = split && split.querySelector(".dk-split__list");
    if (!list) return;
    event.preventDefault();
    var left = list.getBoundingClientRect().left;
    handle.setAttribute("data-dragging", "");
    try { handle.setPointerCapture(event.pointerId); } catch (e) { /* older engines */ }
    function move(e) { setWidth(split, e.clientX - left, false); }
    function up() {
      handle.removeAttribute("data-dragging");
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", up);
      handle.removeEventListener("pointercancel", up);
      setWidth(split, current(split));
    }
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", up);
    handle.addEventListener("pointercancel", up);
  });

  // Measure sticky bands instead of assuming a height: labels and touch
  // targets can wrap. Anchors then land below the complete band.
  var stickyBands = new Set();
  function measureSticky(band) {
    var scroller = band.closest(".dk-split__scroll");
    if (scroller) scroller.style.setProperty("--dk-split-sticky-height", band.getBoundingClientRect().height + "px");
  }
  var stickyObserver = typeof ResizeObserver === "function" ? new ResizeObserver(function (entries) {
    entries.forEach(function (entry) { measureSticky(entry.target); });
  }) : null;
  function initSticky(scope) {
    stickyBands.forEach(function (band) {
      if (document.contains(band)) return;
      if (stickyObserver) stickyObserver.unobserve(band);
      stickyBands.delete(band);
    });
    Array.prototype.forEach.call(scope.querySelectorAll(".dk-split__sticky"), function (band) {
      measureSticky(band);
      if (stickyBands.has(band)) return;
      stickyBands.add(band);
      if (stickyObserver) stickyObserver.observe(band);
    });
  }

  // --- init: stored widths and grip semantics, also for splits rendered later ------
  function initSplit(root) {
    var scope = root || document;
    initSticky(scope);
    var splits = scope.matches && scope.matches(".dk-split") ? [scope] : scope.querySelectorAll(".dk-split");
    Array.prototype.forEach.call(splits, function (split) {
      var handle = split.querySelector(".dk-split__handle");
      if (!handle || handle.hasAttribute("data-dk-ready")) return;
      handle.setAttribute("data-dk-ready", "");
      handle.setAttribute("role", "separator");
      handle.setAttribute("aria-orientation", "vertical");
      if (!handle.hasAttribute("aria-label")) handle.setAttribute("aria-label", "Resize list");
      if (!handle.hasAttribute("tabindex")) handle.setAttribute("tabindex", "0");
      var key = storageKey(split);
      var stored = key ? parseInt(read(key), 10) : NaN;
      if (stored > 0) setWidth(split, stored, false);
      else if (!phone.matches) { handle.setAttribute("aria-valuenow", String(current(split))); handle.setAttribute("aria-valuemin", String(MIN)); }
    });
  }

  var queued = false;
  function onMutate() {
    if (queued) return;
    queued = true;
    Promise.resolve().then(function () { queued = false; initSplit(document); rescue(); });
  }
  if (typeof MutationObserver === "function") {
    new MutationObserver(onMutate).observe(document.documentElement, { childList: true, subtree: true });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", function () { initSplit(document); });
  else initSplit(document);

  globalThis.dakitSplit = { initSplit: initSplit, show: show, reveal: reveal, setWidth: setWidth };
})();
