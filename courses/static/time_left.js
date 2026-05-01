document.addEventListener('DOMContentLoaded', function() {
  function formatTimeLeft(deadline) {
    var now = new Date();
    var diff = deadline - now;

    if (Number.isNaN(deadline.getTime())) {
      return '';
    }

    if (diff <= 0) {
      return 'Deadline passed';
    }

    var totalMinutes = Math.ceil(diff / (1000 * 60));
    var totalHours = Math.floor(totalMinutes / 60);
    var days = Math.floor(totalHours / 24);
    var hours = totalHours % 24;
    var minutes = totalMinutes % 60;

    if (days > 0) {
      var dayText = days + (days === 1 ? ' day' : ' days');
      var hourText = hours > 0 ? ' ' + hours + (hours === 1 ? ' hour' : ' hours') : '';
      return dayText + hourText + ' left';
    }

    if (totalHours > 0) {
      return totalHours + (totalHours === 1 ? ' hour' : ' hours') + (minutes > 0 ? ' ' + minutes + ' min' : '') + ' left';
    }

    return totalMinutes + (totalMinutes === 1 ? ' minute' : ' minutes') + ' left';
  }

  function renderTimeLeft(el) {
    var deadline = new Date(el.getAttribute('data-deadline'));
    var text = formatTimeLeft(deadline);

    if (!text) {
      el.textContent = '';
      return;
    }

    el.textContent = text;

    var diff = deadline - new Date();
    var days = Math.floor(diff / (1000 * 60 * 60 * 24));

    el.classList.remove('text-slate-500', 'text-[#9a6700]', 'text-[#cf222e]', 'dark:text-[#8b949e]');

    if (diff <= 0 || days < 1) {
      el.classList.add('text-[#cf222e]');
    } else if (days < 3) {
      el.classList.add('text-[#9a6700]');
    } else {
      el.classList.add('text-slate-500');
    }
  }

  document.querySelectorAll('.time-left').forEach(function(el) {
    renderTimeLeft(el);
    window.setInterval(function() {
      renderTimeLeft(el);
    }, 60000);
  });
});
