document.addEventListener('DOMContentLoaded', function() {
  var csrfToken = document.getElementById('csrf-token')?.value || '';

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
});
