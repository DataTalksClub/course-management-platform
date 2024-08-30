$(document).ready(function () {
  $('.toggle-lip').click(function () {
    var targetId = $(this).data('target');
    $('#' + targetId).slideToggle();

    var $icon = $(this).find('i');
    var $text = $(this).find('span.fas-show');

    if ($icon.hasClass('fa-chevron-down')) {
      $icon.removeClass('fa-chevron-down').addClass('fa-chevron-up');
      $text.text("Hide");
    } else {
      $icon.removeClass('fa-chevron-up').addClass('fa-chevron-down');
      $text.text("Show");
    }
  });
});