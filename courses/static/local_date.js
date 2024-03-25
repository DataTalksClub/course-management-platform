$(document).ready(function () {
  var utc_dates = document.querySelectorAll(".local-date");

  utc_dates.forEach((date) => {
    var formattedDate = new Date(date.innerHTML);

    var day = formattedDate.getDate();
    var month = formattedDate.toLocaleString('default', { month: 'long' });
    var year = formattedDate.getFullYear();
    var hours = formattedDate.getHours().toString().padStart(2, '0');
    var minutes = formattedDate.getMinutes().toString().padStart(2, '0');

    var formattedDateString = `${day} ${month} ${year} ${hours}:${minutes}`;

    date.innerHTML = formattedDateString;
  });
});
