/* dakit 0.2.0 0e283cd */
// Dakit dialogs: backdrop dismissal, and load-before-open (openWhenReady).
//
// Load once per page — either form works:
//   <script src="dakit/dist/dialogs.js"></script>
//   import "dakit/dist/dialogs.js";
// Listeners are delegated on document, so dialogs mounted later are covered.
// The programmatic API is globalThis.dakitDialogs: { openWhenReady }.
//
// Dismissal contract: the dialog element is the whole panel and carries no
// padding (.dk-dialog sets padding: 0), so a click whose target IS the dialog
// element can only have landed on the ::backdrop. A drag that starts on
// the panel (text selection) doesn't dismiss: the click only counts when
// the press began on the same element. Escape keeps its native behavior.

if (!globalThis.__dakitDialogDismiss) {
  globalThis.__dakitDialogDismiss = true;

  let pressed = null;

  document.addEventListener(
    "pointerdown",
    (event) => {
      pressed = event.target;
    },
    true,
  );

  document.addEventListener("click", (event) => {
    if (event.target !== pressed) return;
    if (event.target instanceof HTMLDialogElement && event.target.open) {
      event.target.close();
    }
  });

  // --- load before open (docs/dialog-loading.md) -------------------------------
  //
  // openWhenReady(trigger, load, render, options?) → Promise<result>
  //
  // A dialog that needs data never opens half-loaded. The trigger goes busy
  // (aria-busy + aria-disabled; dk buttons show a spinner after
  // --dk-loading-delay-busy, at their own size), load(signal) runs, and only
  // then render(data, signal) fills the dialog and returns it; the helper
  // calls showModal() unless render already opened it. A load that outlasts
  // --dk-loading-delay-overlay (or --dk-loading-delay-busy when the trigger
  // isn't a button) shows the .dk-loading overlay: the dialog backdrop with a
  // centred spinner. Escape, a backdrop click on the overlay, or starting a
  // load from another trigger aborts (signal fires, render never runs).
  // Clicking the same trigger again while it loads is ignored — a
  // double-click never opens two dialogs. A failed load opens nothing: the
  // trigger is restored and options.onError(error, retry) runs, or by default
  // a .dk-toast--danger with Retry. Focus stays on, and returns to, the
  // trigger. The promise never rejects; it resolves to
  //   { status: "open", dialog, data } | { status: "aborted" } | { status: "error", error }.
  //
  // options: label (overlay text, default "Loading…"), spinner ("inline" |
  // "overlay"; default inline for .dk-button/.dk-icon-button/<button>),
  // onError(error, retry), errorMessage (string or error => string).

  const BUTTON = ".dk-button, .dk-icon-button, button";
  let current = null;
  let overlay = null;
  let toast = null;

  const ms = (name, fallback) => {
    const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    const n = parseFloat(raw);
    if (!Number.isFinite(n)) return fallback;
    return /ms$/.test(raw) ? n : /s$/.test(raw) ? n * 1000 : n;
  };

  const getOverlay = () => {
    if (overlay && overlay.isConnected) return overlay;
    overlay = document.createElement("dialog");
    overlay.className = "dk-loading";
    overlay.setAttribute("aria-busy", "true");
    overlay.innerHTML =
      '<div class="dk-loading__body"><span class="dk-spinner dk-spinner--lg" aria-hidden="true"></span><span class="dk-loading__label"></span></div>';
    overlay.tabIndex = -1;
    document.body.append(overlay);
    return overlay;
  };

  const dismissToast = () => {
    if (toast) toast.remove();
    toast = null;
  };

  const showToast = (message, retry) => {
    dismissToast();
    toast = document.createElement("div");
    toast.className = "dk-toast dk-toast--danger";
    toast.setAttribute("role", "alert");
    toast.innerHTML =
      '<span class="dk-toast__message"></span>' +
      '<button type="button" class="dk-button dk-button--secondary dk-button--sm" data-dk-retry>Retry</button>' +
      '<button type="button" class="dk-icon-button" aria-label="Dismiss" data-dk-dismiss>' +
      '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8"/></svg></button>';
    toast.querySelector(".dk-toast__message").textContent = message;
    const own = toast;
    own.querySelector("[data-dk-retry]").addEventListener("click", () => {
      dismissToast();
      retry();
    });
    own.querySelector("[data-dk-dismiss]").addEventListener("click", dismissToast);
    own.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        dismissToast();
      }
    });
    // Inside the top modal dialog if one is open, so it isn't inert under it.
    const modals = [...document.querySelectorAll("dialog[open]")].filter((d) => d.matches(":modal"));
    (modals[modals.length - 1] || document.body).append(own);
  };

  const focusable = (el) => el && el.isConnected && typeof el.focus === "function" && (el.tabIndex >= 0 || el.matches(BUTTON));

  function openWhenReady(trigger, load, render, options = {}) {
    // Same trigger again while it loads (a double-click): the same run.
    if (current && current.trigger === trigger) return current.promise;
    if (current) current.abort();
    dismissToast();

    const controller = new AbortController();
    const prior = { busy: trigger.getAttribute("aria-busy"), disabled: trigger.getAttribute("aria-disabled") };
    const inline = (options.spinner || (trigger.matches(BUTTON) ? "inline" : "overlay")) === "inline";
    let settled = false;
    let timer = 0;
    let resolve;
    const promise = new Promise((done) => (resolve = done));

    // Clicks on a busy trigger go nowhere: no second load, no app handler.
    const swallow = (event) => {
      event.preventDefault();
      event.stopImmediatePropagation();
    };
    const onKey = (event) => {
      if (event.key !== "Escape" || (overlay && overlay.open)) return;
      event.preventDefault();
      event.stopPropagation();
      abort();
    };
    const onOverlayClose = () => {
      if (!settled) abort();
    };

    const restore = () => {
      settled = true;
      clearTimeout(timer);
      if (current === run) current = null;
      document.removeEventListener("keydown", onKey, true);
      trigger.removeEventListener("click", swallow, true);
      if (prior.busy === null) trigger.removeAttribute("aria-busy");
      else trigger.setAttribute("aria-busy", prior.busy);
      if (prior.disabled === null) trigger.removeAttribute("aria-disabled");
      else trigger.setAttribute("aria-disabled", prior.disabled);
      if (overlay) {
        overlay.removeEventListener("close", onOverlayClose);
        if (overlay.open) overlay.close();
      }
    };

    const abort = () => {
      if (settled) return;
      controller.abort();
      const hadOverlay = overlay && overlay.open;
      restore();
      if (hadOverlay && focusable(trigger)) trigger.focus({ preventScroll: true });
      resolve({ status: "aborted" });
    };

    const run = { trigger, promise, abort };
    current = run;

    trigger.setAttribute("aria-busy", "true");
    trigger.setAttribute("aria-disabled", "true");
    trigger.addEventListener("click", swallow, true);
    document.addEventListener("keydown", onKey, true);

    timer = setTimeout(
      () => {
        if (settled) return;
        const el = getOverlay();
        el.querySelector(".dk-loading__label").textContent = options.label || "Loading…";
        el.setAttribute("aria-label", options.label || "Loading…");
        el.addEventListener("close", onOverlayClose);
        el.showModal();
      },
      inline ? ms("--dk-loading-delay-overlay", 500) : ms("--dk-loading-delay-busy", 150),
    );

    const retry = () => openWhenReady(trigger, load, render, options);

    Promise.resolve()
      .then(() => load(controller.signal))
      .then((data) =>
        settled ? undefined : Promise.resolve(render(data, controller.signal)).then((dialog) => [data, dialog]),
      )
      .then(
        (out) => {
          if (!out || settled) return;
          const [data, dialog] = out;
          const hadOverlay = overlay && overlay.open;
          restore();
          if (hadOverlay && focusable(trigger)) trigger.focus({ preventScroll: true });
          if (dialog instanceof HTMLDialogElement) {
            if (!dialog.open) dialog.showModal();
            dialog.addEventListener(
              "close",
              () => {
                if (focusable(trigger)) trigger.focus({ preventScroll: true });
              },
              { once: true },
            );
          }
          resolve({ status: "open", dialog, data });
        },
        (error) => {
          if (settled) return;
          const hadOverlay = overlay && overlay.open;
          restore();
          if (hadOverlay && focusable(trigger)) trigger.focus({ preventScroll: true });
          if (options.onError) {
            options.onError(error, retry);
          } else {
            const custom = typeof options.errorMessage === "function" ? options.errorMessage(error) : options.errorMessage;
            showToast(custom || "Couldn't load this. Check your connection and try again.", retry);
          }
          resolve({ status: "error", error });
        },
      );

    return promise;
  }

  globalThis.dakitDialogs = { openWhenReady };
}
