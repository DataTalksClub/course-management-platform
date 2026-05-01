document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('.local-date').forEach(function(date) {
    var timestamp = date.getAttribute('data-timestamp');
    var originalValue = date.getAttribute('datetime') || date.getAttribute('data-date') || date.textContent.trim();
    var formattedDate = timestamp ? new Date(Number(timestamp) * 1000) : new Date(originalValue);

    if (Number.isNaN(formattedDate.getTime())) {
      return;
    }

    var day = formattedDate.getDate();
    var month = formattedDate.toLocaleString(undefined, { month: 'long' });
    var year = formattedDate.getFullYear();
    var hours = formattedDate.getHours().toString().padStart(2, '0');
    var minutes = formattedDate.getMinutes().toString().padStart(2, '0');

    var timezone = '';
    if (date.dataset.showTimezone === 'true') {
      var timezoneName = formattedDate.toLocaleTimeString(undefined, { timeZoneName: 'short' }).split(' ').pop();
      timezone = timezoneName ? ' (' + timezoneName + ')' : '';
    }

    date.textContent = day + ' ' + month + ' ' + year + ', ' + hours + ':' + minutes + timezone;
    date.setAttribute('datetime', originalValue);
  });
});
