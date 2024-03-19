$(document).ready(function () {
  var options = {
    day: "numeric",
    month: "long",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  };
  var utc_dates = document.querySelectorAll(".local-date");
  const utc_dates_copy = Array.from(utc_dates).map((date) => date.innerHTML);

  function UpdateDeadLine() {
    const now = new Date();
    var stillDeadline = 0;
    const until_deadlines = document.querySelectorAll(".until-deadline");
    until_deadlines.forEach((deadline, i) => {
      const homeworkDeadline = new Date(utc_dates_copy[i]);
      let days = 0;
      let hours = 0;
      let minutes = 0;
      let diff = homeworkDeadline.getTime() - now.getTime();
      if (diff > 0) {
        stillDeadline++;
        minutes = Math.floor((diff / (1000 * 60)) % 60);
        hours = Math.floor((diff / (1000 * 60 * 60)) % 24);
        days = Math.floor(diff / (1000 * 60 * 60 * 24));
        deadline.innerHTML = `days: ${days}, hours: ${hours}, minutes: ${minutes}`;
      } else {
        deadline.innerHTML = `Deadline Passed`;
      }
    });
    if (stillDeadline === 0) {
      clearInterval(IntervalId);
    }
  }
  UpdateDeadLine();
  var IntervalId = setInterval(UpdateDeadLine, 1000);
  utc_dates.forEach((date) => {
    var formattedDate = new Date(date.innerHTML);
    date.innerHTML = formattedDate.toLocaleString("en-US", options);
  });
});
