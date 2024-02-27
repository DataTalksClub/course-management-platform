var options = {
  day: "numeric",
  month: "long",
  year: "numeric",
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
};
var utc_dates = document.querySelectorAll(".local-date");
const homeworkDeadline = new Date(utc_dates[0].innerHTML);
utc_dates.forEach((date) => {
  var formattedDate = new Date(date.innerHTML);
  date.innerHTML = formattedDate.toLocaleString("en-US", options);
});
const now = new Date();
let days = 0;
let hours = 0;
let minutes = 0;
let diff = homeworkDeadline.getTime() - now.getTime();
if (diff > 0) {
  let milliseconds = Math.floor((diff % 1000) / 1);
  let seconds = Math.floor((diff / 1000) % 60);
  minutes = Math.floor((diff / (1000 * 60)) % 60);
  hours = Math.floor((diff / (1000 * 60 * 60)) % 24);
  days = Math.floor(diff / (1000 * 60 * 60 * 24));
}

const until_deadline = document.querySelector(".until-deadline");
until_deadline.innerHTML = `days: ${days}, hours: ${hours}, minutes: ${minutes}`;
