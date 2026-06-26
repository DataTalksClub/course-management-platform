document.addEventListener('DOMContentLoaded', function() {
  function isValidUrl(urlString) {
    try {
      var url = new URL(urlString.trim());
      return url.protocol === 'http:' || url.protocol === 'https:';
    } catch (e) {
      return false;
    }
  }

  function isValidCommitId(commitId) {
    return /^[0-9a-f]{7}$/i.test(commitId);
  }

  function setFieldError(field, message) {
    if (!field) {
      return;
    }

    field.classList.toggle('is-invalid', Boolean(message));
    field.setCustomValidity(message || '');

    var feedback = field.parentElement.querySelector('.invalid-feedback');
    if (!feedback) {
      feedback = document.createElement('div');
      feedback.className = 'invalid-feedback';
      field.insertAdjacentElement('afterend', feedback);
    }
    feedback.textContent = message;
  }

  function validateUrlField(selector, name, optional) {
    var linkField = document.querySelector(selector);
    if (!linkField) {
      return '';
    }

    var link = linkField.value.trim();
    if (!link) {
      var missingMessage = optional ? '' : name + ' URL is missing.';
      setFieldError(linkField, missingMessage);
      return missingMessage;
    }
    if (!isValidUrl(link)) {
      var invalidMessage = name + ' URL must start with http:// or https://.';
      setFieldError(linkField, invalidMessage);
      return invalidMessage;
    }
    setFieldError(linkField, '');
    return '';
  }

  function validateFaqContributionField(selector) {
    var field = document.querySelector(selector);
    if (!field) {
      return '';
    }

    var link = field.value.trim();
    if (!link) {
      setFieldError(field, '');
      return '';
    }
    if (!isValidUrl(link)) {
      var invalidMessage = 'FAQ contribution URL must start with https://.';
      setFieldError(field, invalidMessage);
      return invalidMessage;
    }

    var url = new URL(link);
    var pathPattern = /^\/datatalksclub\/faq\/(issues|pull)\/[0-9]+\/?$/;
    if (url.protocol !== 'https:' || url.hostname !== 'github.com' || !pathPattern.test(url.pathname.toLowerCase())) {
      var repoMessage = 'FAQ contribution must be a DataTalksClub/faq issue or pull request URL.';
      setFieldError(field, repoMessage);
      return repoMessage;
    }

    setFieldError(field, '');
    return '';
  }

  function validateCommitIdField(selector) {
    var commitField = document.querySelector(selector);
    if (!commitField) {
      return '';
    }

    var commitId = commitField.value;
    if (!commitId) {
      var missingMessage = 'Commit ID is missing.';
      setFieldError(commitField, missingMessage);
      return missingMessage;
    }
    if (!isValidCommitId(commitId)) {
      var invalidMessage = 'Commit ID must be a 7-character hexadecimal string. For example, "468aacb".';
      setFieldError(commitField, invalidMessage);
      return invalidMessage;
    }
    setFieldError(commitField, '');
    return '';
  }

  var form = document.querySelector('form.needs-validation');
  if (!form) {
    return;
  }

  form.addEventListener('submit', function(event) {
    var errors = [];
    var urlFieldsToValidate = [
      ['#homework_url', 'Homework', false],
      ['#github_link', 'GitHub link', false],
      ['#id_github_url', 'GitHub profile link', true],
      ['#id_linkedin_url', 'LinkedIn profile link', true],
      ['#id_personal_website_url', 'Personal website link', true],
    ];

    urlFieldsToValidate.forEach(function(item) {
      var error = validateUrlField(item[0], item[1], item[2]);
      if (error) {
        errors.push(error);
      }
    });

    var faqContributionError = validateFaqContributionField('#faq_contribution_url');
    if (faqContributionError) {
      errors.push(faqContributionError);
    }

    var commitError = validateCommitIdField('#commit_id');
    if (commitError) {
      errors.push(commitError);
    }

    document.querySelectorAll('input[name="learning_in_public_links[]"]').forEach(function(input) {
      var link = input.value.trim();
      if (link && !isValidUrl(link)) {
        var error = 'Learning in public URL must start with http:// or https://.';
        setFieldError(input, error);
        errors.push(error);
      } else {
        setFieldError(input, '');
      }
    });

    var certificateNameField = document.getElementById('certificate_name');
    if (certificateNameField && certificateNameField.value.trim() === '') {
      var certificateError = 'Certificate name is required.';
      setFieldError(certificateNameField, certificateError);
      errors.push(certificateError);
    } else {
      setFieldError(certificateNameField, '');
    }

    if (errors.length > 0) {
      event.preventDefault();
      var firstInvalid = form.querySelector('.is-invalid');
      if (firstInvalid) {
        firstInvalid.focus();
        firstInvalid.reportValidity();
      }
    }
  });
});
