$(document).ready(function () {

  var isValidUrl = function(urlString) {
    try {
      var url = new URL(urlString);
      var validProtocol = url.protocol === "http:" || url.protocol === "https:";
      return validProtocol;
    } catch (e) {
      return false;
    }
  };

  var validateUrlField = function(selector, name) {
    var linkField = $(selector);
    if (linkField.length == 0) {
      /* the field doesn't exist */
      return '';
    }

    var errorMessage = '';
    var link = linkField.val();
    if (!link) {
      errorMessage += (name + ' link URL is missing.\n');
    } else if (!isValidUrl(link)) {
      errorMessage += (name + ' link URL is invalid. It should start with http:// or https://\n');
    }
    return errorMessage;
  };

  $('#submit-button').click(function (event) {
    console.log("test");

    var isValid = true;
    var errorMessage = '';

    var urlFieldsToValidate = [
      ["#homework_url", "Homework"],
      ["#github_link", "GitHub link"]
    ];

    for (var i = 0; i < urlFieldsToValidate.length; i++) {
      var selector = urlFieldsToValidate[i][0];
      var description = urlFieldsToValidate[i][1];
      
      var message = validateUrlField(selector, description);
      if (message) {
        isValid = false;
        errorMessage += message;
      }
    }

    // Validate learning in public links
    $('input[name="learning_in_public_links[]"]').each(function () {
      var link = $(this).val();
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

});