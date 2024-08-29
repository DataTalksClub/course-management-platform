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

  var isValidCommitId = function(commitId) {
    var commitIdPattern = /^[0-9a-f]{7}$/i;
    return commitIdPattern.test(commitId);
  };

  var validateUrlField = function(selector, name, optional) {
    var linkField = $(selector);
    if (linkField.length == 0) {
      /* the field doesn't exist */
      return '';
    }

    var errorMessage = '';
    var link = linkField.val();
  
    if (!link) {
      if (optional) {
        return '';
      }
      errorMessage += (name + ' link URL is missing.\n');
    } else if (!isValidUrl(link)) {
      errorMessage += (name + ' link URL is invalid. It should start with http:// or https://\n');
    }
    return errorMessage;
  };

  var validateCommitIdField = function(selector) {
    var commitField = $(selector);
    if (commitField.length == 0) {
      /* the field doesn't exist */
      return '';
    }

    var errorMessage = '';
    var commitId = commitField.val();
    if (!commitId) {
      errorMessage += 'Commit ID is missing.\n';
    } else if (!isValidCommitId(commitId)) {
      errorMessage += 'Commit ID is invalid. It should be a 7-character hexadecimal string. For example, "468aacb"\n';
    }
    return errorMessage;
  };

  $('#submit-button').click(function (event) {
    var isValid = true;
    var errorMessage = '';

    var urlFieldsToValidate = [
      ["#homework_url", "Homework", false],
      ["#github_link", "GitHub link", false],
      ["#id_github_url", "GitHub profile link", true],
      ["#id_linkedin_url", "LinkedIn profile link", true],
      ["#id_personal_website_url", "Personal website link", true],
    ];

    for (var i = 0; i < urlFieldsToValidate.length; i++) {
      var selector = urlFieldsToValidate[i][0];
      var description = urlFieldsToValidate[i][1];
      var optional = urlFieldsToValidate[i][1];

      var message = validateUrlField(selector, description, optional);

      if (message) {
        isValid = false;
        errorMessage += message;
      }
    }

    var commitIdMessage = validateCommitIdField('#commit_id');
    if (commitIdMessage) {
      isValid = false;
      errorMessage += commitIdMessage;
    }

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