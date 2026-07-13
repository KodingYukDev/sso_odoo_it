from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestKyAccount(TransactionCase):
    def test_password_is_hashed_and_verified(self):
        account = self.env["ky.account"].create(
            {"name": "Student Test", "email": "Student@Example.com", "status": "active"}
        )
        account.set_password("very-safe-password")
        self.assertNotEqual(account.password_hash, "very-safe-password")
        self.assertTrue(account.check_password("very-safe-password"))
        self.assertFalse(account.check_password("wrong-password"))
        self.assertEqual(account.email, "student@example.com")

    def test_username_is_normalized_and_validated(self):
        account = self.env["ky.account"].create(
            {"name": "Student Test", "username": " Student.One ", "status": "active"}
        )
        self.assertEqual(account.username, "student.one")
        with self.assertRaises(ValidationError):
            self.env["ky.account"].create(
                {"name": "Bad Username", "username": "not allowed!", "status": "active"}
            )

    def test_student_link_does_not_replace_student_record(self):
        student = self.env["m.siswa"].create({"name": "Existing Student"})
        account = self.env["ky.account"].create(
            {"name": "Existing Student", "username": "existing.student", "status": "active"}
        )
        link = self.env["ky.account.student.link"].create(
            {
                "account_id": account.id,
                "student_id": student.id,
                "relationship": "self",
                "status": "verified",
                "verified_method": "admin",
            }
        )
        self.assertEqual(link.student_id, student)
        self.assertTrue(account.oidc_claims()["is_student"])

    def test_security_token_is_hashed_and_single_use(self):
        account = self.env["ky.account"].create(
            {"name": "Token Test", "email": "token@example.com", "status": "pending"}
        )
        raw_token = account.issue_token("email_verification", 60)
        stored = self.env["ky.account.token"].search(
            [("account_id", "=", account.id), ("purpose", "=", "email_verification")]
        )
        self.assertTrue(stored)
        self.assertNotEqual(stored.token_hash, raw_token)
        self.assertEqual(
            self.env["ky.account.token"].consume(raw_token, "email_verification"), stored
        )
        self.assertFalse(
            self.env["ky.account.token"].consume(raw_token, "email_verification")
        )

    def test_audit_log_is_append_only_and_tracks_status(self):
        account = self.env["ky.account"].create(
            {"name": "Audit Test", "email": "audit@example.com", "status": "pending"}
        )
        account.write({"status": "active"})
        audit = self.env["ky.account.audit.log"].search(
            [("account_id", "=", account.id), ("event", "=", "account.status_changed")],
            limit=1,
        )
        self.assertTrue(audit)
        self.assertEqual(audit.details["from"], "pending")
        self.assertEqual(audit.details["to"], "active")
        with self.assertRaises(UserError):
            audit.write({"event": "tampered"})
        with self.assertRaises(UserError):
            audit.unlink()
