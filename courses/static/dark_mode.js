$(document).ready(function() {
  var STORAGE_KEY = 'darkMode';

  // Initialize dark mode based on localStorage or server-side setting
  function initDarkMode() {
    var isAuthenticated = $('#csrf-token').length > 0;
    var serverDarkMode = $('body').attr('data-dark-mode') === 'true';
    
    if (isAuthenticated) {
      // For authenticated users, use server-side preference (already set)
      return serverDarkMode;
    } else {
      // For unauthenticated users, use localStorage
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
  }

  // Apply dark mode classes to the page
  function applyDarkMode(isDarkMode) {
    var $html = $('html');
    var $body = $('body');
    var $toggle = $('#dark-mode-toggle');
    var $icon = $('#dark-mode-icon');
    var $header = $('#header-container');
    var $content = $('#main-content');

    if (isDarkMode) {
      $html.addClass('dark-mode');
      $body.addClass('dark-mode').attr('data-dark-mode', 'true');
      $toggle.removeClass('btn-dark').addClass('btn-light');
      $icon.removeClass('fa-moon').addClass('fa-sun');
      $header.removeClass('bg-light border-bottom').addClass('bg-dark border-dark');
      $content.removeClass('bg-light').addClass('bg-dark');
    } else {
      $html.removeClass('dark-mode');
      $body.removeClass('dark-mode').attr('data-dark-mode', 'false');
      $toggle.removeClass('btn-light').addClass('btn-dark');
      $icon.removeClass('fa-sun').addClass('fa-moon');
      $header.removeClass('bg-dark border-dark').addClass('bg-light border-bottom');
      $content.removeClass('bg-dark').addClass('bg-light');
    }
  }

  // Handle dark mode toggle click
  $('#dark-mode-toggle').click(function() {
    var isAuthenticated = $('#csrf-token').length > 0;
    var currentDarkMode = $('body').attr('data-dark-mode') === 'true';
    var newDarkMode = !currentDarkMode;

    if (isAuthenticated) {
      // For authenticated users, save to server
      var csrfToken = $('#csrf-token').val();
      $.ajax({
        url: '/accounts/toggle-dark-mode/',
        type: 'POST',
        headers: {
          'X-CSRFToken': csrfToken
        },
        success: function(data) {
          applyDarkMode(data.dark_mode);
          // Also save to localStorage for consistency
          localStorage.setItem(STORAGE_KEY, data.dark_mode.toString());
        },
        error: function(xhr, status, error) {
          console.error('Error toggling dark mode:', error);
        }
      });
    } else {
      // For unauthenticated users, save to localStorage only
      localStorage.setItem(STORAGE_KEY, newDarkMode.toString());
      applyDarkMode(newDarkMode);
    }
  });

  // Initialize on page load
  initDarkMode();
});
