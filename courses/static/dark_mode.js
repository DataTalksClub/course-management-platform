document.addEventListener('DOMContentLoaded', function() {
  var STORAGE_KEY = 'darkMode';
  var body = document.body;
  var toggle = document.getElementById('dark-mode-toggle');
  var icon = document.getElementById('dark-mode-icon');
  var label = document.getElementById('dark-mode-label');

  function applyDarkMode(isDarkMode) {
    body.classList.toggle('dark', isDarkMode);
    body.classList.toggle('dark-mode', isDarkMode);
    body.setAttribute('data-dark-mode', isDarkMode ? 'true' : 'false');

    if (toggle) {
      toggle.setAttribute('aria-pressed', isDarkMode ? 'true' : 'false');
    }

    if (icon) {
      icon.classList.toggle('fa-moon', !isDarkMode);
      icon.classList.toggle('fa-sun', isDarkMode);
    }

    if (label) {
      label.textContent = isDarkMode ? 'Light mode' : 'Dark mode';
    }
  }

  function initDarkMode() {
    var isAuthenticated = body.getAttribute('data-authenticated') === 'true';
    var serverDarkMode = body.getAttribute('data-dark-mode') === 'true';

    if (isAuthenticated) {
      return serverDarkMode;
    }

    var storedPreference = localStorage.getItem(STORAGE_KEY);
    if (storedPreference !== null) {
      var isDarkMode = storedPreference === 'true';
      if (isDarkMode !== serverDarkMode) {
        applyDarkMode(isDarkMode);
      }
      return isDarkMode;
    }

    return serverDarkMode;
  }

  if (toggle) {
    toggle.addEventListener('click', function() {
      var isAuthenticated = body.getAttribute('data-authenticated') === 'true';
      var currentDarkMode = body.getAttribute('data-dark-mode') === 'true';
      var newDarkMode = !currentDarkMode;

      if (!isAuthenticated) {
        localStorage.setItem(STORAGE_KEY, newDarkMode.toString());
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
        })
        .catch(function(error) {
          console.error('Error toggling dark mode:', error);
        });
    });
  }

  initDarkMode();
});
