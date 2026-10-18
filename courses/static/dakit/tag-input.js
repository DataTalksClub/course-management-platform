/* dakit 0.2.0 0e283cd */
/* dakit tag input (docs/tag-input.md): a multi-select combobox. The chosen
   values sit in the field as removable chips; typing filters a listbox of
   the rest, and Enter or a click adds the active option.

     var tags = dakitTagInput.create({
       options: [{ value, label, aliases?, icon?, group? }],
       value: ["youtube"],              // chosen values, in order
       label: "Needs",                  // accessible name (or labelledBy: id)
       placeholder: "Add a resource…",
       noMatches: "No matches",
       onChange: function (values, change) {}  // change = { added } | { removed }
     });
     host.append(tags.element);
     tags.getValue(); tags.setValue([...]); tags.setOptions([...]);
     tags.setDisabled(true); tags.focus(); tags.open(); tags.close();

   Matching is a case-insensitive substring test on the label and every
   alias; label-prefix matches rank first within their group. An option's
   icon is a Node (cloned), a function returning a Node, or a short string;
   it shows in the option and on the chip. Options with a group render under
   that group's heading, in first-seen group order.

   ARIA 1.2 combobox: the <input> has role=combobox, aria-expanded,
   aria-controls and aria-activedescendant; the popup is role=listbox with
   role=option rows (role=group per group). Chosen values are a labelled
   list whose remove buttons say "Remove <label>", and adds and removes are
   announced through a polite status region.

   Keyboard: ↓/↑ open and move, Enter adds, Backspace on an empty field
   removes the last chip, Esc closes (then clears the text), Tab leaves.
   Mouse and touch: tap the field to open, tap an option to add, tap × to
   remove. Classic script with an idempotent global guard, like shell.js. */
(function () {
  "use strict";
  if (globalThis.dakitTagInput) return;

  var CLOSE = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M6 6l12 12M18 6L6 18"/></svg>';
  var counter = 0;

  function norm(text) { return String(text == null ? "" : text).toLocaleLowerCase(); }

  function iconNode(doc, icon) {
    if (icon == null || icon === "") return null;
    // A function builds a fresh node per render; a Node is cloned so the
    // caller's original is never moved; a string is shown as text.
    var node = typeof icon === "function" ? icon() : icon;
    if (node == null) return null;
    if (typeof node === "string") {
      var span = doc.createElement("span");
      span.textContent = node;
      node = span;
    } else if (typeof icon !== "function") {
      node = node.cloneNode(true);
    }
    var wrap = doc.createElement("span");
    wrap.className = "dk-tag-input__icon";
    wrap.setAttribute("aria-hidden", "true");
    wrap.append(node);
    return wrap;
  }

  // Label with the matched run marked; plain text when there is no query or
  // the match came from an alias.
  function labelNode(doc, label, query) {
    var span = doc.createElement("span");
    span.className = "dk-tag-input__text";
    var at = query ? norm(label).indexOf(query) : -1;
    if (at < 0) { span.textContent = label; return span; }
    var mark = doc.createElement("mark");
    mark.className = "dk-tag-input__match";
    mark.textContent = label.slice(at, at + query.length);
    span.append(doc.createTextNode(label.slice(0, at)), mark, doc.createTextNode(label.slice(at + query.length)));
    return span;
  }

  function matches(option, query) {
    if (!query) return 0;
    var label = norm(option.label);
    if (label.indexOf(query) === 0) return 0;
    if (label.indexOf(query) > 0) return 1;
    var aliases = option.aliases || [];
    for (var i = 0; i < aliases.length; i++) if (norm(aliases[i]).indexOf(query) >= 0) return 1;
    return -1;
  }

  function create(config) {
    config = config || {};
    var doc = config.document || globalThis.document;
    var id = config.id || "dk-tag-input-" + (++counter);
    var options = [];
    var byValue = new Map();
    var value = [];
    var disabled = false;
    var expanded = false;
    var visible = []; // options currently in the listbox, in display order
    var active = -1;
    var onChange = typeof config.onChange === "function" ? config.onChange : function () {};
    var labelText = config.label || "";
    var noMatches = config.noMatches || "No matches";

    var root = doc.createElement("div");
    root.className = "dk-tag-input";
    root.dataset.dkTagInput = "";

    var field = doc.createElement("div");
    field.className = "dk-tag-input__field";

    var chips = doc.createElement("ul");
    chips.className = "dk-tag-input__chips";
    chips.id = id + "-chips";
    chips.setAttribute("aria-label", labelText ? "Selected " + labelText : "Selected");

    var input = doc.createElement("input");
    input.type = "text";
    input.className = "dk-tag-input__input";
    input.id = id + "-input";
    input.autocomplete = "off";
    input.spellcheck = false;
    input.setAttribute("autocapitalize", "off");
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-expanded", "false");
    input.setAttribute("aria-controls", id + "-listbox");
    input.setAttribute("aria-describedby", chips.id);
    if (config.labelledBy) input.setAttribute("aria-labelledby", config.labelledBy);
    else if (labelText) input.setAttribute("aria-label", labelText);
    if (config.placeholder) input.placeholder = config.placeholder;
    if (config.name) input.dataset.name = config.name;

    var popup = doc.createElement("div");
    popup.className = "dk-tag-input__popup";
    popup.hidden = true;
    var listbox = doc.createElement("div");
    listbox.className = "dk-tag-input__listbox";
    listbox.id = id + "-listbox";
    listbox.setAttribute("role", "listbox");
    listbox.setAttribute("aria-label", labelText || "Options");
    var empty = doc.createElement("div");
    empty.className = "dk-tag-input__empty";
    empty.hidden = true;
    empty.textContent = noMatches;
    popup.append(listbox, empty);

    var status = doc.createElement("span");
    status.className = "dk-visually-hidden";
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");

    field.append(chips, input);
    root.append(field, popup, status);

    function say(text) {
      // Clear first so the same sentence twice is still announced.
      status.textContent = "";
      setTimeout(function () { status.textContent = text; }, 30);
    }

    function setOptions(list) {
      options = (list || []).filter(function (o) { return o && o.value != null; }).map(function (o) {
        return { value: String(o.value), label: String(o.label == null ? o.value : o.label), aliases: Array.isArray(o.aliases) ? o.aliases.map(String) : [], icon: o.icon, group: o.group ? String(o.group) : "" };
      });
      byValue = new Map(options.map(function (o) { return [o.value, o]; }));
      renderChips();
      if (expanded) filter();
    }

    function renderChips() {
      chips.replaceChildren();
      value.forEach(function (v) {
        var option = byValue.get(v) || { value: v, label: v };
        var chip = doc.createElement("li");
        chip.className = "dk-tag-input__chip";
        chip.dataset.value = v;
        var icon = iconNode(doc, option.icon);
        if (icon) chip.append(icon);
        var text = doc.createElement("span");
        text.className = "dk-tag-input__text";
        text.textContent = option.label;
        var remove = doc.createElement("button");
        remove.type = "button";
        remove.className = "dk-tag-input__remove";
        remove.setAttribute("aria-label", "Remove " + option.label);
        remove.title = "Remove " + option.label;
        remove.disabled = disabled;
        remove.innerHTML = CLOSE;
        remove.addEventListener("click", function (event) {
          event.stopPropagation();
          removeValue(v);
          input.focus();
        });
        chip.append(text, remove);
        chips.append(chip);
      });
      chips.hidden = value.length === 0;
      if (value.length === 0) input.removeAttribute("aria-describedby");
      else input.setAttribute("aria-describedby", chips.id);
    }

    function filter() {
      var query = norm(input.value.trim());
      var groups = [];
      var byGroup = new Map();
      options.forEach(function (o, index) {
        if (value.indexOf(o.value) >= 0) return;
        var rank = matches(o, query);
        if (rank < 0) return;
        if (!byGroup.has(o.group)) { byGroup.set(o.group, []); groups.push(o.group); }
        byGroup.get(o.group).push({ o: o, rank: rank, index: index });
      });
      var previous = visible[active] && visible[active].value;
      visible = [];
      listbox.replaceChildren();
      groups.forEach(function (group, g) {
        var rows = byGroup.get(group).sort(function (a, b) { return a.rank - b.rank || a.index - b.index; });
        var container = listbox;
        if (group) {
          container = doc.createElement("div");
          container.className = "dk-tag-input__group";
          container.setAttribute("role", "group");
          var heading = doc.createElement("div");
          heading.className = "dk-tag-input__group-label";
          heading.id = id + "-group-" + g;
          heading.setAttribute("role", "presentation");
          heading.textContent = group;
          container.setAttribute("aria-labelledby", heading.id);
          container.append(heading);
          listbox.append(container);
        }
        rows.forEach(function (row) {
          var o = row.o;
          var el = doc.createElement("div");
          el.className = "dk-tag-input__option";
          el.id = id + "-option-" + visible.length;
          el.setAttribute("role", "option");
          el.dataset.value = o.value;
          el.dataset.index = String(visible.length);
          var icon = iconNode(doc, o.icon);
          if (icon) el.append(icon);
          el.append(labelNode(doc, o.label, query));
          container.append(el);
          visible.push(o);
        });
      });
      empty.hidden = visible.length > 0;
      listbox.hidden = visible.length === 0;
      var keep = previous ? visible.findIndex(function (o) { return o.value === previous; }) : -1;
      // Typing makes the best match active so Enter takes it; opening with
      // an empty field leaves nothing active until an arrow key or a hover.
      setActive(query ? 0 : keep, false);
    }

    function optionEl(index) { return listbox.querySelector('[data-index="' + index + '"]'); }

    function setActive(index, scroll) {
      var old = optionEl(active);
      if (old) old.classList.remove("is-active");
      active = index >= 0 && index < visible.length ? index : -1;
      var el = optionEl(active);
      if (el) {
        el.classList.add("is-active");
        input.setAttribute("aria-activedescendant", el.id);
        if (scroll !== false && typeof el.scrollIntoView === "function") el.scrollIntoView({ block: "nearest" });
      } else {
        input.removeAttribute("aria-activedescendant");
      }
    }

    function open() {
      if (disabled) return;
      if (!expanded) {
        expanded = true;
        popup.hidden = false;
        root.classList.add("is-open");
        input.setAttribute("aria-expanded", "true");
      }
      filter();
      if (!visible.length) say(noMatches);
    }

    function close() {
      if (!expanded) return;
      expanded = false;
      popup.hidden = true;
      root.classList.remove("is-open");
      input.setAttribute("aria-expanded", "false");
      setActive(-1);
    }

    function emit(change) {
      try { onChange(value.slice(), change); } catch (error) { setTimeout(function () { throw error; }); }
    }

    function addValue(v) {
      if (disabled || value.indexOf(v) >= 0 || !byValue.has(v)) return;
      var index = active;
      value = value.concat([v]);
      renderChips();
      input.value = "";
      if (expanded) {
        filter();
        // Stay on the row that slid into the added one's place.
        setActive(visible.length ? Math.min(Math.max(index, 0), visible.length - 1) : -1);
      }
      say("Added " + byValue.get(v).label + ". " + value.length + " selected.");
      emit({ added: v });
    }

    function removeValue(v) {
      if (disabled || value.indexOf(v) < 0) return;
      var label = (byValue.get(v) || { label: v }).label;
      value = value.filter(function (x) { return x !== v; });
      renderChips();
      if (expanded) filter();
      say("Removed " + label + ". " + value.length + " selected.");
      emit({ removed: v });
    }

    input.addEventListener("input", function () { open(); });
    input.addEventListener("click", function () { open(); });
    input.addEventListener("keydown", function (event) {
      if (disabled || event.isComposing) return;
      var key = event.key;
      if (key === "ArrowDown" || key === "ArrowUp") {
        event.preventDefault();
        if (!expanded) { open(); if (event.altKey) return; }
        if (!visible.length) return;
        var step = key === "ArrowDown" ? 1 : -1;
        var next = active < 0 ? (step > 0 ? 0 : visible.length - 1) : (active + step + visible.length) % visible.length;
        setActive(next);
      } else if (key === "Enter") {
        if (expanded && active >= 0) {
          event.preventDefault();
          addValue(visible[active].value);
        } else if (input.value) {
          // Free text that matches nothing is never added; don't submit a form with it.
          event.preventDefault();
        }
      } else if (key === "Escape") {
        if (expanded) { event.preventDefault(); event.stopPropagation(); close(); }
        else if (input.value) { event.preventDefault(); event.stopPropagation(); input.value = ""; }
      } else if (key === "Backspace") {
        if (!input.value && input.selectionStart === 0 && input.selectionEnd === 0 && value.length) {
          event.preventDefault();
          removeValue(value[value.length - 1]);
        }
      } else if (key === "Tab") {
        close();
      }
    });

    // Keep focus in the field while pressing an option, so the press never
    // blurs and closes the list; a touch tap sends the same compat mousedown.
    popup.addEventListener("mousedown", function (event) { event.preventDefault(); });
    listbox.addEventListener("click", function (event) {
      var el = event.target.closest && event.target.closest('[role="option"]');
      if (!el || !listbox.contains(el)) return;
      addValue(el.dataset.value);
      input.focus();
    });
    listbox.addEventListener("mousemove", function (event) {
      var el = event.target.closest && event.target.closest('[role="option"]');
      if (el && Number(el.dataset.index) !== active) setActive(Number(el.dataset.index), false);
    });
    // A press anywhere on the field that is not a chip's button lands in the input.
    field.addEventListener("mousedown", function (event) {
      if (disabled || event.target === input || (event.target.closest && event.target.closest("button"))) return;
      event.preventDefault();
      input.focus();
      open();
    });
    root.addEventListener("focusout", function (event) {
      var next = event.relatedTarget;
      if (next && root.contains(next)) return;
      // relatedTarget is null when focus leaves the page or a chip's button
      // was removed under it; decide once focus has settled.
      setTimeout(function () {
        if (!root.contains(doc.activeElement)) close();
      }, 0);
    });

    function setDisabled(flag) {
      disabled = Boolean(flag);
      input.disabled = disabled;
      root.classList.toggle("is-disabled", disabled);
      if (disabled) close();
      renderChips();
    }

    setOptions(config.options);
    value = (config.value || []).map(String).filter(function (v, i, all) { return all.indexOf(v) === i; });
    renderChips();
    if (config.disabled) setDisabled(true);

    return {
      element: root,
      input: input,
      getValue: function () { return value.slice(); },
      setValue: function (next) {
        value = (next || []).map(String).filter(function (v, i, all) { return all.indexOf(v) === i; });
        renderChips();
        if (expanded) filter();
      },
      setOptions: setOptions,
      setDisabled: setDisabled,
      focus: function () { input.focus(); },
      open: open,
      close: close,
    };
  }

  globalThis.dakitTagInput = { create: create };
})();
