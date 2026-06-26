document.addEventListener('DOMContentLoaded', function() {
  var csrfToken = document.getElementById('csrf-token')?.value || '';

  function emailPreferenceInputs() {
    return Array.prototype.slice.call(
      document.querySelectorAll('.js-email-preference-toggle')
    );
  }

  function setEmailPreferencesDisabled(disabled) {
    emailPreferenceInputs().forEach(function(input) {
      input.disabled = disabled;
    });
  }

  function setEmailPreferencesStatus(message) {
    var status = document.querySelector('.js-email-preferences-status');
    if (status) {
      status.textContent = message;
    }
  }

  function hydrateEmailPreferences() {
    var section = document.querySelector('[data-email-preferences-url]');
    if (!section) {
      return;
    }

    var preferencesUrl = section.getAttribute('data-email-preferences-url');
    if (!preferencesUrl) {
      return;
    }

    setEmailPreferencesDisabled(true);
    fetch(preferencesUrl, {
      method: 'GET',
      headers: {
        'X-Requested-With': 'XMLHttpRequest',
      },
    })
      .then(function(response) {
        if (!response.ok) {
          throw new Error('Email preferences fetch failed');
        }
        return response.json();
      })
      .then(function(data) {
        var preferences = data.preferences || {};
        emailPreferenceInputs().forEach(function(input) {
          if (Object.prototype.hasOwnProperty.call(preferences, input.name)) {
            input.checked = Boolean(preferences[input.name]);
          }
        });
        setEmailPreferencesStatus('Email subscriptions loaded.');
        setEmailPreferencesDisabled(false);
      })
      .catch(function(error) {
        setEmailPreferencesStatus(
          'Email preferences are temporarily unavailable. Try again later.'
        );
        setEmailPreferencesDisabled(true);
        console.error('Error loading email preferences:', error);
      });
  }

  function persistToggle(row, input) {
    var previousValue = !input.checked;
    var toggleUrl = row.getAttribute('data-toggle-url');
    input.disabled = true;

    var formData = new FormData();
    formData.append('field', input.name);
    formData.append('value', input.checked ? 'true' : 'false');

    fetch(toggleUrl, {
      method: 'POST',
      headers: {
        'X-CSRFToken': csrfToken,
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: formData,
    })
      .then(function(response) {
        if (!response.ok) {
          throw new Error('Toggle update failed');
        }
        return response.json();
      })
      .then(function(data) {
        if (data.field === 'dark_mode') {
          window.applyDarkModePreference?.(data.value);
          localStorage.setItem('darkMode', data.value.toString());
        }
      })
      .catch(function(error) {
        input.checked = previousValue;
        if (input.classList.contains('js-email-preference-toggle')) {
          setEmailPreferencesStatus(
            'Email preferences are temporarily unavailable. Try again later.'
          );
        }
        console.error('Error updating setting:', error);
      })
      .finally(function() {
        input.disabled = false;
      });
  }

  document.querySelectorAll('.js-immediate-toggle-row').forEach(function(row) {
    var input = row.querySelector('input[type="checkbox"]');
    if (!input || !row.getAttribute('data-toggle-url')) {
      return;
    }

    input.addEventListener('change', function() {
      persistToggle(row, input);
    });
  });

  hydrateEmailPreferences();
});
