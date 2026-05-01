document.addEventListener('DOMContentLoaded', function() {
  function isValidUrl(urlString) {
    try {
      var url = new URL(urlString);
      return url.protocol === 'http:' || url.protocol === 'https:';
    } catch (e) {
      return false;
    }
  }

  function isValidCommitId(commitId) {
    return /^[0-9a-f]{7}$/i.test(commitId);
  }

  function validateUrlField(selector, name, optional) {
    var linkField = document.querySelector(selector);
    if (!linkField) {
      return '';
    }

    var link = linkField.value;
    if (!link) {
      return optional ? '' : name + ' link URL is missing.\n';
    }
    if (!isValidUrl(link)) {
      return name + ' link URL is invalid. It should start with http:// or https://\n';
    }
    return '';
  }

  function validateCommitIdField(selector) {
    var commitField = document.querySelector(selector);
    if (!commitField) {
      return '';
    }

    var commitId = commitField.value;
    if (!commitId) {
      return 'Commit ID is missing.\n';
    }
    if (!isValidCommitId(commitId)) {
      return 'Commit ID is invalid. It should be a 7-character hexadecimal string. For example, "468aacb"\n';
    }
    return '';
  }

  var submitButton = document.getElementById('submit-button');
  if (!submitButton) {
    return;
  }

  submitButton.addEventListener('click', function(event) {
    var errorMessage = '';
    var urlFieldsToValidate = [
      ['#homework_url', 'Homework', false],
      ['#github_link', 'GitHub link', false],
      ['#id_github_url', 'GitHub profile link', true],
      ['#id_linkedin_url', 'LinkedIn profile link', true],
      ['#id_personal_website_url', 'Personal website link', true],
    ];

    urlFieldsToValidate.forEach(function(item) {
      errorMessage += validateUrlField(item[0], item[1], item[2]);
    });

    errorMessage += validateCommitIdField('#commit_id');

    document.querySelectorAll('input[name="learning_in_public_links[]"]').forEach(function(input) {
      var link = input.value;
      if (link && !isValidUrl(link)) {
        errorMessage += 'Invalid learning in public link URL.\n';
      }
    });

    var certificateNameField = document.getElementById('certificate_name');
    if (certificateNameField && certificateNameField.value.trim() === '') {
      errorMessage += 'Certificate name is required. Please enter the name you would like to appear on your certificate.\n';
    }

    if (errorMessage) {
      alert(errorMessage);
      event.preventDefault();
    }
  });
});
