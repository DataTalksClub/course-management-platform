$(document).ready(function () {
  $('#add-learning-public-link').click(function () {
    let currentLinkCount = $('#learning-in-public-links input[type="url"]').length;
    let cap = global_learning_in_public_cap;
    if (currentLinkCount < cap) {
        let html = '<div><input type="url" name="learning_in_public_links[]" class="url-input"></div>';
        $('#learning-in-public-links').append(html);
    }
    if (currentLinkCount + 1 >= cap) {
        $(this).prop('disabled', true);
    }
  });

  $('#submit-button').click(function (event) {
    let isValid = true;
    let errorMessage = '';

    // Validate homework link only if the field exists
    const homeworkLinkField = $('#homework_url');
    if (homeworkLinkField.length > 0) {
      const homeworkLink = homeworkLinkField.val();
      if (!homeworkLink) {
        isValid = false;
        errorMessage += 'Homework link URL is missing.\n';
      } else if (!isValidUrl(homeworkLink)) {
        isValid = false;
        errorMessage += 'Homework link URL is invalid.\n';
      }
    }

    // Validate learning in public links
    $('input[name="learning_in_public_links[]"]').each(function () {
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
      let url = new URL(urlString);
      let validProtocol = url.protocol === "http:" || url.protocol === "https:";
      return validProtocol;
    } catch (e) {
      return false;
    }
  }
});