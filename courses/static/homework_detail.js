$(document).ready(function () {
  $('#add-link').click(function () {
    let html = '<input type="url" name="learning_in_public_links" class="url-input">';
    $('#learning-in-public-links').append(html);
  });

  $('#submit-button').click(function (event) {
    let isValid = true;
    let errorMessage = '';

    // Validate homework link
    const homeworkLink = $('#homework_link').val();
    if (homeworkLink && !isValidUrl(homeworkLink)) {
      isValid = false;
      errorMessage += 'Invalid homework link URL.\n';
    }

    // Validate learning in public links
    $('.learning-url-input').each(function () {
      const link = $(this).val();
      if (link && !isValidUrl(link)) {
        isValid = false;
        errorMessage += 'Invalid learning in public link URL.\n';
      }
    });

    if (!isValid) {
      alert(errorMessage);
      event.preventDefault(); // Prevent form submission
    }
  });

  function isValidUrl(urlString) {
    try {
      new URL(urlString);
      return true;
    } catch (e) {
      return false;
    }
  }
});