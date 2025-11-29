$(document).ready(function () {
  $('#add-learning-public-link').click(function () {
    let currentLinkCount = $('#learning-in-public-links input[type="url"]').length;
    let cap = global_learning_in_public_cap;
    if (currentLinkCount < cap) {
        let html = '<input type="url" class="form-control" name="learning_in_public_links[]">';
        $('#learning-in-public-links').append(html);
    }
    if (currentLinkCount + 1 >= cap) {
        $(this).prop('disabled', true);
    }
  });
});