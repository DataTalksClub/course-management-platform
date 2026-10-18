/* dakit 0.2.0 0e283cd */
// Dakit app shell behaviour — the contract is docs/shell.md.
//
// Load once per page, at the end of <body> (no defer, so the persisted
// collapse state applies before first paint):
//   <script src="dakit/dist/shell.js"></script>      or   import "dakit/dist/shell.js";
// Everything is wired by data attributes and delegated on document, so
// markup added later works. The programmatic API is globalThis.dakitShell:
//   setSidebar(shell, "collapsed" | "expanded"), toggleDrawer(shell, open?),
//   openPopover(id, { trigger }), closePopovers({ restoreFocus }),
//   setCount(countEl, n), announce(message), initShell(root)
// Every storage access is wrapped: blocked storage means defaults, never a throw.

(() => {
  if (globalThis.dakitShell) return;

  const MOBILE = "(max-width: 820px)";
  const THEME_KEY = "dakit-theme";
  const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

  const store = {
    get(key) { try { return localStorage.getItem(key); } catch { return null; } },
    set(key, value) { try { localStorage.setItem(key, value); } catch { /* storage blocked */ } },
  };
  const isMobile = () => matchMedia(MOBILE).matches;
  const visible = (el) => el && el.getClientRects().length > 0;
  const focusables = (root) => [...root.querySelectorAll(FOCUSABLE)].filter(visible);
  const isTyping = (el) => el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName));

  // --- sidebar collapse ---------------------------------------------------------

  function setSidebar(shell, state) {
    shell.dataset.sidebar = state;
    const collapsed = state === "collapsed";
    for (const toggle of shell.querySelectorAll("[data-dk-sidebar-toggle]")) {
      toggle.setAttribute("aria-label", collapsed ? "Expand sidebar" : "Collapse sidebar");
      toggle.setAttribute("aria-expanded", String(!collapsed));
    }
    if (shell.dataset.app) store.set(`dk-sidebar:${shell.dataset.app}`, state);
    hideTooltip();
    closePopovers({ restoreFocus: false });
  }

  // --- mobile drawer --------------------------------------------------------------

  let drawerReturn = null;
  const MODAL_ATTRS = ["role", "aria-modal", "aria-label"];

  // While open on mobile the drawer is a modal dialog; the desktop sidebar is
  // a plain landmark. Originals are saved once and restored exactly (a missing
  // attribute is removed again).
  function setDrawerSemantics(sidebar, open) {
    if (!sidebar) return;
    if (open) {
      if (!sidebar.__dkDrawerAttrs) {
        sidebar.__dkDrawerAttrs = Object.fromEntries(MODAL_ATTRS.map((name) => [name, sidebar.getAttribute(name)]));
      }
      const saved = sidebar.__dkDrawerAttrs;
      sidebar.setAttribute("role", "dialog");
      sidebar.setAttribute("aria-modal", "true");
      if (!sidebar.hasAttribute("aria-labelledby")) sidebar.setAttribute("aria-label", saved["aria-label"] || "Navigation");
    } else if (sidebar.__dkDrawerAttrs) {
      for (const [name, value] of Object.entries(sidebar.__dkDrawerAttrs)) {
        if (value === null) sidebar.removeAttribute(name); else sidebar.setAttribute(name, value);
      }
      sidebar.__dkDrawerAttrs = null;
    }
  }

  function toggleDrawer(shell, open = shell.dataset.drawer !== "open", { restoreFocus = true } = {}) {
    const sidebar = shell.querySelector(".dk-sidebar");
    const scrim = shell.querySelector(".dk-scrim");
    const toggles = shell.querySelectorAll("[data-dk-drawer-toggle]");
    const outside = shell.querySelectorAll(".dk-main, .dk-topbar");
    if (open) {
      // Already open: keep the saved return focus and attributes as they are.
      if (shell.dataset.drawer === "open") return true;
      closePopovers({ restoreFocus: false });
      drawerReturn = document.activeElement;
      shell.dataset.drawer = "open";
      setDrawerSemantics(sidebar, true);
      if (scrim) scrim.hidden = false;
      outside.forEach((el) => { el.inert = true; });
      toggles.forEach((t) => t.setAttribute("aria-expanded", "true"));
      // The open drawer is visible at once (shell.css transitions only its
      // transform on open), so focus moves in this task. Should an app style
      // still delay visibility, retry until the target is visible, bounded by
      // time rather than frame count: a busy page can run many frames before
      // a transition starts, and the modal drawer must never keep focus on body.
      const target = sidebar && (sidebar.querySelector('[aria-current="page"]') || focusables(sidebar)[0]);
      const deadline = performance.now() + 2000;
      const focusWhenVisible = () => {
        if (shell.dataset.drawer !== "open" || !target) return;
        if (sidebar.contains(document.activeElement) && document.activeElement !== sidebar) return;
        if (getComputedStyle(target).visibility === "visible") target.focus();
        if (document.activeElement !== target && performance.now() < deadline) requestAnimationFrame(focusWhenVisible);
      };
      focusWhenVisible();
    } else {
      if (shell.dataset.drawer !== "open") return false;
      delete shell.dataset.drawer;
      setDrawerSemantics(sidebar, false);
      if (scrim) scrim.hidden = true;
      outside.forEach((el) => { el.inert = false; });
      toggles.forEach((t) => t.setAttribute("aria-expanded", "false"));
      const back = drawerReturn && drawerReturn.isConnected && visible(drawerReturn) ? drawerReturn : toggles[0];
      drawerReturn = null;
      if (restoreFocus && back) back.focus();
    }
    return open;
  }

  // Bell + account trigger live in the sidebar on desktop and in the mobile bar
  // on phones. They are moved, never cloned, so ids and counts stay singular.
  function placeTriggers(shell) {
    const slot = shell.querySelector(".dk-topbar__end");
    if (!slot) return;
    const mobile = isMobile();
    for (const el of shell.querySelectorAll(".dk-sidebar .dk-notif-trigger, .dk-sidebar .dk-account-trigger, .dk-topbar .dk-notif-trigger, .dk-topbar .dk-account-trigger")) {
      if (mobile && !slot.contains(el)) {
        const mark = document.createComment("dk-trigger");
        el.before(mark);
        el.__dkHome = mark;
        slot.append(el);
      } else if (!mobile && el.__dkHome) {
        el.__dkHome.replaceWith(el);
        el.__dkHome = null;
      }
    }
    if (!mobile) toggleDrawer(shell, false);
  }

  // --- popovers ----------------------------------------------------------------------

  let open = null; // { popover, trigger }

  function triggersFor(id) {
    return document.querySelectorAll(`[data-dk-popover-trigger="${CSS.escape(id)}"]`);
  }

  // Keyboard opening moves focus to the first row (visible ring). Pointer
  // opening focuses the menu container instead, so no row shows a ring that
  // reads like a selection; ArrowDown then enters the rows.
  function openPopover(id, { trigger, keyboard = false } = {}) {
    const popover = document.getElementById(id);
    if (!popover) return;
    closePopovers({ restoreFocus: false });
    hideTooltip();
    let returnTo = trigger || triggersFor(id)[0];
    // A trigger inside the open mobile drawer (the brand switcher): the drawer
    // is modal and popovers are its siblings, so the popover would sit
    // outside the dialog that traps focus. The drawer hands over instead: it
    // closes without moving focus, the popover opens as the sheet under the
    // bar, and closing it returns focus to the drawer's menu button.
    const shell = returnTo && returnTo.closest(".dk-shell");
    if (shell && shell.dataset.drawer === "open" && returnTo.closest(".dk-sidebar")) {
      toggleDrawer(shell, false, { restoreFocus: false });
      returnTo = shell.querySelector("[data-dk-drawer-toggle]") || returnTo;
    }
    popover.hidden = false;
    triggersFor(id).forEach((t) => t.setAttribute("aria-expanded", "true"));
    open = { popover, trigger: returnTo };
    const autofocus = popover.querySelector("[data-dk-autofocus]");
    if (autofocus) { autofocus.focus(); return; }
    if (!keyboard && popover.matches(".dk-menu")) {
      if (!popover.hasAttribute("tabindex")) popover.tabIndex = -1;
      popover.focus();
      return;
    }
    const first = popover.querySelector(".dk-menu__item:not([disabled])") || focusables(popover)[0];
    if (first) first.focus();
  }

  function closePopovers({ restoreFocus = true } = {}) {
    if (!open) return;
    const { popover, trigger } = open;
    open = null;
    popover.hidden = true;
    triggersFor(popover.id).forEach((t) => t.setAttribute("aria-expanded", "false"));
    if (restoreFocus && trigger && trigger.isConnected) trigger.focus();
  }

  function moveInMenu(popover, key) {
    const items = [...popover.querySelectorAll(".dk-menu__item")].filter((el) => !el.disabled && visible(el));
    if (!items.length) return false;
    const i = items.indexOf(document.activeElement);
    const next = key === "Home" ? 0 : key === "End" ? items.length - 1
      : key === "ArrowDown" ? (i + 1) % items.length
      : i < 0 ? items.length - 1 : (i - 1 + items.length) % items.length;
    items[next].focus();
    return true;
  }

  // --- counts and announcements ----------------------------------------------------------

  function setCount(el, n) {
    const value = Number.isFinite(n) ? Math.floor(n) : 0;
    el.hidden = value <= 0;
    el.textContent = value > 99 ? "99+" : value > 0 ? String(value) : "";
    const owner = el.closest("[data-dk-count-label]");
    if (owner) {
      const label = owner.dataset.dkCountLabel;
      owner.setAttribute("aria-label", value > 0 ? `${label}, ${value > 99 ? "99+" : value} unread` : label);
    }
  }

  function announce(message) {
    let live = document.getElementById("dk-live");
    if (!live) {
      live = document.createElement("div");
      live.id = "dk-live";
      live.className = "dk-visually-hidden";
      live.setAttribute("aria-live", "polite");
      document.body.append(live);
    }
    live.textContent = "";
    setTimeout(() => { live.textContent = message; }, 50);
  }

  // --- theme ---------------------------------------------------------------------------------

  function syncTheme() {
    const dark = document.documentElement.dataset.theme === "dark";
    for (const t of document.querySelectorAll("[data-dk-theme-toggle]")) t.setAttribute("aria-checked", String(dark));
  }

  function toggleTheme() {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    store.set(THEME_KEY, next);
    syncTheme();
  }

  // --- copy -------------------------------------------------------------------------------------

  async function copy(button) {
    const ref = button.dataset.dkCopy;
    const source = (ref && document.querySelector(ref)) ||
      button.closest(".dk-code-block")?.querySelector("code, pre");
    if (!source) return;
    const text = source.textContent;
    const initial = button.dataset.dkCopyLabel || (button.dataset.dkCopyLabel = button.textContent.trim());
    // CSS reserves the width of "Copied" before the first click. The rare
    // "Press Ctrl+C" fallback may widen the button while it shows.
    let label;
    try {
      await navigator.clipboard.writeText(text);
      label = "Copied";
      button.dataset.copied = "true";
      announce("Copied");
    } catch {
      const range = document.createRange();
      range.selectNodeContents(source);
      getSelection().removeAllRanges();
      getSelection().addRange(range);
      label = /Mac/.test(navigator.platform) ? "Press ⌘C" : "Press Ctrl+C";
    }
    button.textContent = label;
    clearTimeout(button.__dkCopyTimer);
    button.__dkCopyTimer = setTimeout(() => {
      button.textContent = initial;
      delete button.dataset.copied;
    }, 1500);
  }

  // --- rail tooltip -------------------------------------------------------------------------------

  let tooltip = null;
  const RAIL_TARGETS = ".dk-nav-item, .dk-brand, .dk-icon-button, .dk-account-trigger, .dk-search__rail";

  function railItem(target) {
    const el = target && target.closest && target.closest(RAIL_TARGETS);
    if (!el || isMobile()) return null;
    const shell = el.closest('.dk-shell[data-sidebar="collapsed"]');
    return shell && el.closest(".dk-sidebar") ? el : null;
  }

  function showTooltip(el) {
    const text = (el.querySelector(".dk-nav-item__label, .dk-brand__name, .dk-account-trigger__name")?.textContent ||
      el.getAttribute("aria-label") || "").trim();
    if (!text) return;
    if (!tooltip) {
      tooltip = document.createElement("div");
      tooltip.className = "dk-tooltip";
      tooltip.setAttribute("aria-hidden", "true");
      document.body.append(tooltip);
    }
    const box = el.getBoundingClientRect();
    const column = el.closest(".dk-sidebar").getBoundingClientRect();
    tooltip.textContent = text.replace(/\s+/g, " ");
    tooltip.style.left = `${column.right + 8}px`;
    tooltip.style.top = `${box.top + box.height / 2}px`;
    tooltip.hidden = false;
  }

  function hideTooltip() { if (tooltip) tooltip.hidden = true; }

  // --- wiring --------------------------------------------------------------------------------------

  // Idempotent: runs as soon as the script executes (shells already parsed) and
  // again on DOMContentLoaded (shells parsed later); each shell is set up once.
  function initShell(root = document) {
    const shells = root.matches?.(".dk-shell") ? [root] : root.querySelectorAll(".dk-shell");
    for (const shell of shells) {
      if (shell.__dkReady) continue;
      shell.__dkReady = true;
      const saved = shell.dataset.app && store.get(`dk-sidebar:${shell.dataset.app}`);
      const state = saved === "collapsed" || saved === "expanded" ? saved : (shell.dataset.sidebar || "expanded");
      if (shell.querySelector(".dk-sidebar")) {
        shell.dataset.sidebar = state;
        for (const toggle of shell.querySelectorAll("[data-dk-sidebar-toggle]")) {
          toggle.setAttribute("aria-label", state === "collapsed" ? "Expand sidebar" : "Collapse sidebar");
          toggle.setAttribute("aria-expanded", String(state !== "collapsed"));
        }
      }
      placeTriggers(shell);
    }
    // Initial counts from markup are consumed once, so they never override a
    // later setCount() from the app.
    for (const count of root.querySelectorAll(".dk-count[data-dk-count]")) {
      setCount(count, Number(count.dataset.dkCount));
      delete count.dataset.dkCount;
    }
    syncTheme();
  }

  document.addEventListener("click", (event) => {
    const t = event.target.closest("[data-dk-sidebar-toggle], [data-dk-drawer-toggle], [data-dk-drawer-close], [data-dk-popover-trigger], [data-dk-theme-toggle], [data-dk-copy], [data-dk-search-expand], .dk-sidebar a.dk-nav-item");
    if (!t) return;
    const shell = t.closest(".dk-shell");
    if (t.matches("[data-dk-sidebar-toggle]") && shell) {
      setSidebar(shell, shell.dataset.sidebar === "collapsed" ? "expanded" : "collapsed");
    } else if (t.matches("[data-dk-drawer-toggle]") && shell) {
      toggleDrawer(shell);
    } else if (t.matches("[data-dk-drawer-close]") && shell) {
      toggleDrawer(shell, false);
    } else if (t.matches("[data-dk-popover-trigger]")) {
      const id = t.dataset.dkPopoverTrigger;
      if (open && open.popover.id === id) closePopovers();
      else openPopover(id, { trigger: t, keyboard: event.detail === 0 });
    } else if (t.matches("[data-dk-theme-toggle]")) {
      toggleTheme();
    } else if (t.matches("[data-dk-copy]")) {
      copy(t);
    } else if (t.matches("[data-dk-search-expand]") && shell) {
      setSidebar(shell, "expanded");
      shell.querySelector(".dk-search input")?.focus();
    } else if (t.matches("a.dk-nav-item") && shell && shell.dataset.drawer === "open" && !event.defaultPrevented) {
      toggleDrawer(shell, false);
    }
  });

  // A real control the person can land on. A tabindex="-1" container (main,
  // a dialog body) or <body> is background, not a destination.
  const CONTROL = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), summary, [contenteditable=""], [contenteditable="true"], [tabindex]:not([tabindex^="-"])';
  const ownsFocus = (popover, el) => !!el && (popover.contains(el) || !!el.closest?.(`[data-dk-popover-trigger="${CSS.escape(popover.id)}"]`));

  // Outside pointer-down closes the open popover. When focus was inside it,
  // focus returns to the trigger — unless the click lands on a control, which
  // keeps the focus the browser gives it. The browser moves focus after
  // pointerdown (to the clicked control, or to a tabindex="-1" background such
  // as main), so the return waits a task and then checks where focus landed.
  document.addEventListener("pointerdown", (event) => {
    if (!open) return;
    const { popover, trigger } = open;
    if (ownsFocus(popover, event.target)) return;
    const restore = popover.contains(document.activeElement);
    closePopovers({ restoreFocus: false });
    if (!restore || !trigger || !trigger.isConnected) return;
    setTimeout(() => {
      // The click may have opened another popover (its trigger), which owns focus now.
      if (open) return;
      const now = document.activeElement;
      if (now && now !== document.body && now.matches(CONTROL)) return;
      trigger.focus();
    }, 0);
  });

  // A press inside the open popover. Pressing its non-focusable parts (text, a
  // row's padding) drops focus to <body> without the person leaving it.
  let pressedInside = false;
  document.addEventListener("pointerdown", (event) => {
    pressedInside = !!open && open.popover.contains(event.target);
  }, true);
  document.addEventListener("keydown", () => { pressedInside = false; }, true);

  // Non-modal: tabbing out closes without trapping. relatedTarget is null when
  // focus leaves the document (Tab past the last element into browser chrome)
  // or goes to something unfocusable, so that case is settled a task later
  // from where focus actually is. A window blur keeps activeElement inside the
  // popover, so switching apps does not close it.
  //
  // Focus can also be dropped inside the popover rather than moved out of it:
  // the focused control went busy (disabled), was hidden, or was re-rendered
  // away, or a press landed on the popover's own background. The document
  // keeps focus and it falls to <body>. That is not the person leaving, so the
  // popover stays open and focus is caught on its container, where the app
  // can hand it on (to the re-rendered control, an error) and the keyboard
  // still works. Tab into browser chrome leaves the departed control intact,
  // so it still closes.
  document.addEventListener("focusout", (event) => {
    if (!open || !open.popover.contains(event.target)) return;
    const { popover } = open;
    const left = event.target;
    const next = event.relatedTarget;
    if (next) {
      if (!ownsFocus(popover, next)) closePopovers({ restoreFocus: false });
      return;
    }
    setTimeout(() => {
      if (!open || open.popover !== popover) return;
      const now = document.activeElement;
      if (ownsFocus(popover, now)) return;
      const dropped = !left.isConnected || left.disabled || !visible(left) || pressedInside;
      if (dropped && document.hasFocus() && (!now || now === document.body)) {
        if (!popover.hasAttribute("tabindex")) popover.tabIndex = -1;
        popover.focus({ preventScroll: true });
        return;
      }
      closePopovers({ restoreFocus: false });
    }, 0);
  });

  // Focus arriving anywhere outside the open popover and its trigger (for
  // example Tab wrapping back in from browser chrome) closes it.
  document.addEventListener("focusin", (event) => {
    if (open && !ownsFocus(open.popover, event.target)) closePopovers({ restoreFocus: false });
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      if (open) { event.preventDefault(); closePopovers(); return; }
      const shell = document.querySelector('.dk-shell[data-drawer="open"]');
      if (shell) { event.preventDefault(); toggleDrawer(shell, false); }
      return;
    }
    if (open && open.popover.matches(".dk-menu") && ["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key) && !isTyping(event.target)) {
      if (moveInMenu(open.popover, event.key)) event.preventDefault();
      return;
    }
    if (event.key === "Tab") {
      const shell = document.querySelector('.dk-shell[data-drawer="open"]');
      const sidebar = shell && shell.querySelector(".dk-sidebar");
      if (!sidebar) return;
      const items = focusables(sidebar);
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      return;
    }
    if (isTyping(event.target) || event.altKey) return;
    const shell = document.querySelector(".dk-shell");
    if (!shell) return;
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "b" && shell.querySelector(".dk-sidebar") && !isMobile()) {
      event.preventDefault();
      setSidebar(shell, shell.dataset.sidebar === "collapsed" ? "expanded" : "collapsed");
    } else if (event.key === "/" && !event.metaKey && !event.ctrlKey) {
      const input = shell.querySelector(".dk-search input");
      if (!input) return;
      event.preventDefault();
      if (isMobile()) toggleDrawer(shell, true);
      else if (shell.dataset.sidebar === "collapsed") setSidebar(shell, "expanded");
      requestAnimationFrame(() => input.focus());
    } else if (event.key === "?" && !event.metaKey && !event.ctrlKey) {
      document.dispatchEvent(new CustomEvent("dk:shortcuts"));
    }
  });

  document.addEventListener("pointerover", (event) => {
    const el = railItem(event.target);
    if (el) showTooltip(el); else hideTooltip();
  });
  document.addEventListener("focusin", (event) => {
    const el = railItem(event.target);
    if (el && event.target.matches(":focus-visible")) showTooltip(el); else hideTooltip();
  });
  document.addEventListener("scroll", hideTooltip, true);

  matchMedia(MOBILE).addEventListener("change", () => {
    hideTooltip();
    closePopovers({ restoreFocus: false });
    document.querySelectorAll(".dk-shell").forEach(placeTriggers);
  });

  globalThis.dakitShell = { initShell, setSidebar, toggleDrawer, openPopover, closePopovers, setCount, announce };

  initShell();
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => initShell());
})();
