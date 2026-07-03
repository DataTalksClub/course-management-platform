(function () {
  const input = document.querySelector("[data-country-combobox-input]");
  const panel = document.querySelector("[data-country-combobox-panel]");
  const optionsScript = document.getElementById("country-options-json");

  if (!input || !panel || !optionsScript) {
    return;
  }

  const countries = JSON.parse(optionsScript.textContent);
  let activeIndex = -1;
  let visibleCountries = [];

  function normalize(value) {
    return value.trim().toLowerCase();
  }

  function matchingCountries(query) {
    const normalizedQuery = normalize(query);
    if (!normalizedQuery) {
      return countries.slice();
    }

    const startsWith = [];
    const contains = [];

    countries.forEach((country) => {
      const normalizedCountry = normalize(country);
      if (normalizedCountry.startsWith(normalizedQuery)) {
        startsWith.push(country);
      } else if (normalizedCountry.includes(normalizedQuery)) {
        contains.push(country);
      }
    });

    return startsWith.concat(contains).slice(0, 12);
  }

  function selectCountry(country) {
    input.value = country;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
    hidePanel();
  }

  function hidePanel() {
    panel.hidden = true;
    panel.innerHTML = "";
    activeIndex = -1;
    input.removeAttribute("aria-activedescendant");
  }

  function renderPanel() {
    visibleCountries = matchingCountries(input.value);
    activeIndex = visibleCountries.length ? 0 : -1;
    panel.innerHTML = "";

    if (!visibleCountries.length) {
      const empty = document.createElement("div");
      empty.className = "country-combobox-empty";
      empty.textContent = "No matching countries";
      panel.appendChild(empty);
      panel.hidden = false;
      return;
    }

    visibleCountries.forEach((country, index) => {
      const option = document.createElement("button");
      option.type = "button";
      option.id = "country-option-" + index;
      option.className = "country-combobox-option";
      option.textContent = country;
      option.setAttribute("role", "option");
      option.setAttribute("aria-selected", index === activeIndex ? "true" : "false");
      option.addEventListener("mousedown", (event) => {
        event.preventDefault();
        selectCountry(country);
      });
      panel.appendChild(option);
    });

    panel.hidden = false;
    input.setAttribute("aria-activedescendant", "country-option-" + activeIndex);
  }

  function updateActiveOption(nextIndex) {
    if (!visibleCountries.length) {
      return;
    }

    activeIndex = (nextIndex + visibleCountries.length) % visibleCountries.length;
    panel.querySelectorAll(".country-combobox-option").forEach((option, index) => {
      const isActive = index === activeIndex;
      option.setAttribute("aria-selected", isActive ? "true" : "false");
      if (isActive) {
        option.scrollIntoView({ block: "nearest" });
      }
    });
    input.setAttribute("aria-activedescendant", "country-option-" + activeIndex);
  }

  input.setAttribute("role", "combobox");
  input.setAttribute("aria-autocomplete", "list");
  input.setAttribute("aria-expanded", "false");
  input.setAttribute("aria-controls", "country-combobox-listbox");
  panel.id = "country-combobox-listbox";
  panel.setAttribute("role", "listbox");

  input.addEventListener("focus", () => {
    renderPanel();
    input.setAttribute("aria-expanded", "true");
  });

  input.addEventListener("input", () => {
    renderPanel();
    input.setAttribute("aria-expanded", "true");
  });

  input.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (panel.hidden) {
        renderPanel();
      } else {
        updateActiveOption(activeIndex + 1);
      }
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      updateActiveOption(activeIndex - 1);
    } else if (event.key === "Enter" && !panel.hidden && activeIndex >= 0) {
      event.preventDefault();
      selectCountry(visibleCountries[activeIndex]);
    } else if (event.key === "Escape") {
      hidePanel();
    }
  });

  input.addEventListener("blur", () => {
    window.setTimeout(() => {
      hidePanel();
      input.setAttribute("aria-expanded", "false");
    }, 120);
  });
})();
