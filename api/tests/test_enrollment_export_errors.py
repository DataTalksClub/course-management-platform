from .enrollment_exports_base import EnrollmentExportsAPITestBase


class EnrollmentExportErrorAPITestCase(EnrollmentExportsAPITestBase):
    def mixed_certificate_payload(self):
        enrolled_item = self.certificate_item(
            "enrolled@example.com",
            "/certificates/enrolled.pdf",
        )
        not_enrolled_item = self.certificate_item(
            "not-enrolled@example.com",
            "/certificates/not-enrolled.pdf",
        )
        missing_user_item = self.certificate_item(
            "missing-user@example.com",
            "/certificates/missing.pdf",
        )
        missing_path_item = {"email": "missing-path@example.com"}
        invalid_item = "not an object"
        items = []
        items.append(enrolled_item)
        items.append(not_enrolled_item)
        items.append(missing_user_item)
        items.append(missing_path_item)
        items.append(invalid_item)
        return items

    def assert_mixed_certificate_response(self, response, enrolled):
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertEqual(data["updated_count"], 1)
        self.assertEqual(data["error_count"], 4)
        self.assertEqual(data["updated"][0]["enrollment_id"], enrolled.id)
        error_codes = []
        for error in data["errors"]:
            error_codes.append(error["code"])
        expected_error_codes = [
            "missing_fields",
            "invalid_item",
            "not_enrolled",
            "user_not_found",
        ]
        self.assertEqual(error_codes, expected_error_codes)

    def test_bulk_update_certificates_reports_mixed_item_errors(self):
        enrolled = self.create_enrollment("enrolled@example.com")
        self.create_student("not-enrolled@example.com")

        payload = self.mixed_certificate_payload()
        response = self.post_certificates(payload)

        self.assert_mixed_certificate_response(response, enrolled)
        self.assert_certificate_url(enrolled, "/certificates/enrolled.pdf")
