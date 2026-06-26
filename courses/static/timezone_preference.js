(function() {
  function csrfToken() {
    var input = document.getElementById('csrf-token');
    return input ? input.value : '';
  }

  function detectBrowserTimezone() {
    try {
      if (typeof Intl === 'undefined' || typeof Intl.DateTimeFormat !== 'function') {
        return '';
      }
      var resolved = Intl.DateTimeFormat().resolvedOptions();
      return resolved && resolved.timeZone ? resolved.timeZone : '';
    } catch (e) {
      return '';
    }
  }

  function saveBrowserTimezoneCookie(timezoneName) {
    if (!timezoneName) {
      return;
    }
    document.cookie = 'browser_timezone=' + encodeURIComponent(timezoneName)
      + ';path=/;max-age=31536000;SameSite=Lax';
  }

  function postTimezone(url, timezoneName, passive) {
    return fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken(),
      },
      body: JSON.stringify({
        timezone: timezoneName,
        passive: Boolean(passive),
      }),
    });
  }

  function updateSettingsControl(timezoneName, label) {
    var select = document.getElementById('id_preferred_timezone');
    if (select && timezoneName) {
      select.value = timezoneName;
    }

    var status = document.getElementById('timezone-preference-status');
    if (status && timezoneName) {
      status.textContent = 'Current timezone: ' + (label || timezoneName);
    }
  }

  function init() {
    var body = document.body;
    if (!body || body.dataset.authenticated !== 'true') {
      saveBrowserTimezoneCookie(detectBrowserTimezone());
      return;
    }

    var detected = detectBrowserTimezone();
    saveBrowserTimezoneCookie(detected);

    var url = body.dataset.timezoneUpdateUrl || '';
    if (!url || body.dataset.preferredTimezone) {
      return;
    }

    if (!detected) {
      return;
    }

    postTimezone(url, detected, true)
      .then(function(response) {
        if (!response.ok) {
          return null;
        }
        return response.json();
      })
      .then(function(data) {
        if (!data || data.status !== 'ok') {
          return;
        }
        body.dataset.preferredTimezone = data.timezone || detected;
        updateSettingsControl(data.timezone || detected, data.label);
      })
      .catch(function() {});
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
