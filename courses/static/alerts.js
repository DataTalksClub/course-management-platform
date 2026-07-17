document.addEventListener('click', function(event) {
  var button = event.target.closest('[data-dismiss="alert"]');
  if (!button) {
    return;
  }

  var alert = button.closest('[role="alert"]');
  if (alert) {
    alert.remove();
  }
});
