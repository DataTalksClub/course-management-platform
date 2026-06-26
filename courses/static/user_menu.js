document.addEventListener('DOMContentLoaded', function() {
  var menus = Array.prototype.slice.call(
    document.querySelectorAll('details.user-menu')
  );

  if (!menus.length) {
    return;
  }

  function closeMenusExcept(currentMenu) {
    menus.forEach(function(menu) {
      if (menu !== currentMenu) {
        menu.removeAttribute('open');
      }
    });
  }

  document.addEventListener('click', function(event) {
    var clickedMenu = event.target.closest('details.user-menu');
    if (clickedMenu) {
      closeMenusExcept(clickedMenu);
      return;
    }
    closeMenusExcept(null);
  });

  document.addEventListener('keydown', function(event) {
    if (event.key === 'Escape') {
      closeMenusExcept(null);
    }
  });
});
