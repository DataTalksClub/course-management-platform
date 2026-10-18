document.addEventListener('DOMContentLoaded', function() {
  var STORAGE_KEY = 'darkMode';
  var DAKIT_STORAGE_KEY = 'dakit-theme';
  var body = document.body;
  var toggle = document.getElementById('dark-mode-toggle');
  var label = document.getElementById('dark-mode-label');

  function applyDarkMode(isDarkMode) {
    var theme = isDarkMode ? 'dark' : 'light';
    document.documentElement.dataset.theme = theme;
    body.classList.toggle('dark', isDarkMode);
    body.classList.toggle('dark-mode', isDarkMode);
    body.setAttribute('data-dark-mode', isDarkMode ? 'true' : 'false');

    if (toggle) {
      toggle.setAttribute('aria-pressed', isDarkMode ? 'true' : 'false');
    }

    if (label) {
      label.textContent = isDarkMode ? 'Light mode' : 'Dark mode';
    }
  }

  window.applyDarkModePreference = applyDarkMode;

  function initDarkMode() {
    var isAuthenticated = body.getAttribute('data-authenticated') === 'true';
    var serverDarkMode = body.getAttribute('data-dark-mode') === 'true';

    if (isAuthenticated) {
      applyDarkMode(serverDarkMode);
      return serverDarkMode;
    }

    var storedPreference = localStorage.getItem(STORAGE_KEY);
    if (storedPreference !== null) {
      var isDarkMode = storedPreference === 'true';
      applyDarkMode(isDarkMode);
      return isDarkMode;
    }

    var dakitPreference = localStorage.getItem(DAKIT_STORAGE_KEY);
    if (dakitPreference === 'dark' || dakitPreference === 'light') {
      var isDakitDark = dakitPreference === 'dark';
      applyDarkMode(isDakitDark);
      return isDakitDark;
    }

    applyDarkMode(serverDarkMode);
    return serverDarkMode;
  }

  if (toggle) {
    toggle.addEventListener('click', function() {
      var isAuthenticated = body.getAttribute('data-authenticated') === 'true';
      var currentDarkMode = body.getAttribute('data-dark-mode') === 'true';
      var newDarkMode = !currentDarkMode;

      if (!isAuthenticated) {
        localStorage.setItem(STORAGE_KEY, newDarkMode.toString());
        localStorage.setItem(DAKIT_STORAGE_KEY, newDarkMode ? 'dark' : 'light');
        applyDarkMode(newDarkMode);
        return;
      }

      fetch(body.getAttribute('data-toggle-url'), {
        method: 'POST',
        headers: {
          'X-CSRFToken': document.getElementById('csrf-token')?.value || '',
          'X-Requested-With': 'XMLHttpRequest',
        },
      })
        .then(function(response) {
          if (!response.ok) {
            throw new Error('Dark mode toggle failed');
          }
          return response.json();
        })
        .then(function(data) {
          applyDarkMode(data.dark_mode);
          localStorage.setItem(STORAGE_KEY, data.dark_mode.toString());
          localStorage.setItem(DAKIT_STORAGE_KEY, data.dark_mode ? 'dark' : 'light');
        })
        .catch(function(error) {
          console.error('Error toggling dark mode:', error);
        });
    });
  }

  initDarkMode();
});
