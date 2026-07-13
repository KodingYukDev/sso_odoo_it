import hmac
import html
import logging
import re
from urllib.parse import urlencode

from psycopg2 import IntegrityError

from odoo import fields, http
from odoo.exceptions import ValidationError
from odoo.http import request


_logger = logging.getLogger(__name__)
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _response(payload, status=200):
    return request.make_json_response(payload, status=status)


def _ok(**payload):
    return _response({"success": True, **payload})


def _error(code, message, status=400):
    return _response({"success": False, "error": code, "message": message}, status=status)


def _payload():
    try:
        value = request.get_json_data()
    except Exception:
        value = {}
    return value if isinstance(value, dict) else {}


def _is_authorized():
    expected = request.env["ir.config_parameter"].sudo().get_param("accounts.api_key")
    provided = request.httprequest.headers.get("X-Accounts-Key", "")
    if not expected:
        _logger.error("accounts.api_key is not configured")
        return False
    return hmac.compare_digest(expected.encode("utf-8"), provided.encode("utf-8"))


def _mask_identifier(value):
    value = (value or "").strip().lower()
    if not value:
        return ""
    if "@" in value:
        local, domain = value.split("@", 1)
        return "%s***@%s" % ((local[:1] or "*"), domain[:96])
    return "%s***" % value[:2]


class KodingYukAccountsApi(http.Controller):
    def _require_service(self):
        if not _is_authorized():
            return _error("unauthorized", "Unauthorized", status=401)
        return None

    def _public_origin(self):
        return request.env["ir.config_parameter"].sudo().get_param(
            "accounts.public_origin", ""
        ).rstrip("/")

    def _audit(self, event, outcome, data=None, account=None, identifier="", client_id="", details=None):
        data = data if isinstance(data, dict) else {}
        context = data.get("_audit") if isinstance(data.get("_audit"), dict) else {}
        try:
            with request.env.cr.savepoint():
                request.env["ky.account.audit.log"].sudo().create(
                    {
                        "event": event,
                        "outcome": outcome,
                        "account_id": account.id if account else False,
                        "identifier_hint": _mask_identifier(identifier),
                        "client_id": client_id or context.get("client_id") or "",
                        "request_id": context.get("request_id") or "",
                        "ip_address": context.get("ip_address")
                        or request.httprequest.remote_addr
                        or "",
                        "user_agent": context.get("user_agent")
                        or request.httprequest.headers.get("User-Agent", ""),
                        "source": context.get("source") or "accounts_api",
                        "details": details or {},
                    }
                )
        except Exception:
            _logger.exception("Could not append account audit event %s", event)

    def _queue_security_email(self, account, purpose, raw_token):
        origin = self._public_origin()
        if not origin:
            raise ValidationError("accounts.public_origin is not configured.")
        sender = request.env["ir.config_parameter"].sudo().get_param(
            "accounts.email_from", ""
        ).strip()
        if not sender:
            raise ValidationError("accounts.email_from is not configured.")
        if purpose == "email_verification":
            path = "/verify-email"
            subject = "Verifikasi KodingYuk Account"
            action = "Verifikasi email"
            explanation = "Gunakan tombol ini untuk mengaktifkan KodingYuk Account kamu."
        else:
            path = "/reset-password"
            subject = "Reset password KodingYuk Account"
            action = "Buat password baru"
            explanation = "Abaikan email ini jika kamu tidak meminta reset password."
        url = "%s%s?%s" % (origin, path, urlencode({"token": raw_token}))
        body = """
            <div style="font-family:Arial,sans-serif;max-width:560px;margin:auto">
              <h2>KodingYuk Account</h2>
              <p>Halo %s,</p><p>%s</p>
              <p><a href="%s" style="display:inline-block;padding:12px 18px;background:#2457f5;color:#fff;text-decoration:none;border-radius:8px">%s</a></p>
              <p style="color:#667085;font-size:13px">Link ini bersifat sekali pakai dan akan kedaluwarsa.</p>
            </div>
        """ % (html.escape(account.name), explanation, html.escape(url, quote=True), action)
        request.env["mail.mail"].sudo().create(
            {
                "subject": subject,
                "body_html": body,
                "email_to": account.email,
                "email_from": sender,
                "auto_delete": True,
            }
        )

    @http.route("/accounts/v1/health", type="http", auth="public", methods=["GET"], csrf=False)
    def health(self):
        configured = bool(
            request.env["ir.config_parameter"].sudo().get_param("accounts.api_key")
        )
        return _ok(service="sso_odoo_it", configured=configured)

    @http.route("/accounts/v1/register", type="http", auth="public", methods=["POST"], csrf=False)
    def register(self):
        denied = self._require_service()
        if denied:
            return denied
        email_from = request.env["ir.config_parameter"].sudo().get_param(
            "accounts.email_from", ""
        ).strip()
        if not self._public_origin() or not email_from:
            return _error(
                "configuration_error",
                "Public origin and security email sender must be configured.",
                status=503,
            )
        data = _payload()
        name = (data.get("name") or "").strip()
        email = (data.get("email") or "").strip().lower()
        username = (data.get("username") or "").strip().lower() or False
        password = data.get("password") or ""
        source = (data.get("source") or "accounts_web").strip()[:128]
        accepted_policy = data.get("accept_policy") is True
        policy_version = str(data.get("policy_version") or "").strip()[:64]

        if not name or not email or not password or not accepted_policy or not policy_version:
            return _error(
                "invalid_payload",
                "Name, email, password, and policy acceptance are required.",
            )
        if not EMAIL_RE.fullmatch(email):
            return _error("invalid_payload", "Email format is invalid.")
        if len(password) < 10:
            return _error("weak_password", "Password must contain at least 10 characters.")

        Account = request.env["ky.account"].sudo()
        if Account.find_by_identifier(email) or (username and Account.find_by_identifier(username)):
            return _error("already_exists", "Account already exists.", status=409)

        try:
            partner = request.env["res.partner"].sudo().search([("email", "=ilike", email)], limit=1)
            if not partner:
                partner = request.env["res.partner"].sudo().create(
                    {"name": name, "email": email, "type": "contact"}
                )
            account = Account.create(
                {
                    "name": name,
                    "email": email,
                    "username": username,
                    "partner_id": partner.id,
                    "status": "pending",
                    "created_source": source,
                }
            )
            account.set_password(password)
            consent_base = {
                "account_id": account.id,
                "actor_account_id": account.id,
                "channel": "service",
                "status": "granted",
                "policy_version": policy_version,
                "source": source,
                "evidence_ref": str(data.get("evidence_ref") or "")[:256],
            }
            consents = [
                {**consent_base, "purpose": "terms"},
                {**consent_base, "purpose": "privacy"},
            ]
            if data.get("marketing") is True:
                consents.append({**consent_base, "purpose": "marketing", "channel": "email"})
            request.env["ky.account.consent"].sudo().create(consents)
            verification_token = account.issue_token("email_verification", 24 * 60)
            self._queue_security_email(account, "email_verification", verification_token)
            self._audit(
                "account.registered", "success", data=data, account=account,
                identifier=email, details={"marketing_consent": data.get("marketing") is True},
            )
            return _ok(account=account.oidc_claims())
        except IntegrityError as exc:
            request.env.cr.rollback()
            _logger.info("Account registration rejected: %s", exc)
            self._audit("account.registration_failed", "failure", data=data, identifier=email, details={"reason": "duplicate"})
            return _error("already_exists", "Account could not be registered.", status=409)
        except ValidationError as exc:
            request.env.cr.rollback()
            _logger.info("Account registration validation failed: %s", exc)
            self._audit("account.registration_failed", "failure", data=data, identifier=email, details={"reason": "validation"})
            return _error("invalid_payload", "Account data is invalid.", status=400)
        except Exception:
            request.env.cr.rollback()
            _logger.exception("Account registration failed")
            self._audit("account.registration_failed", "failure", data=data, identifier=email, details={"reason": "internal"})
            return _error("register_failed", "Account could not be registered.", status=500)

    @http.route(
        "/accounts/v1/authenticate", type="http", auth="public", methods=["POST"], csrf=False
    )
    def authenticate(self):
        denied = self._require_service()
        if denied:
            return denied
        data = _payload()
        identifier = data.get("identifier") or ""
        password = data.get("password") or ""
        account = request.env["ky.account"].sudo().find_by_identifier(identifier)
        if not account or not account.check_password(password):
            self._audit("auth.login_failed", "failure", data=data, account=account, identifier=identifier, details={"reason": "credentials"})
            return _error("invalid_credentials", "Invalid credentials.", status=401)
        if account.status == "pending":
            self._audit("auth.login_failed", "failure", data=data, account=account, identifier=identifier, details={"reason": "email_not_verified"})
            return _error("email_not_verified", "Email verification is required.", status=403)
        if account.status != "active":
            self._audit("auth.login_failed", "failure", data=data, account=account, identifier=identifier, details={"reason": "account_unavailable"})
            return _error("account_unavailable", "Account is unavailable.", status=403)
        account.sudo().write({"last_login_at": fields.Datetime.now()})
        self._audit("auth.login_succeeded", "success", data=data, account=account, identifier=identifier)
        return _ok(account=account.oidc_claims())

    @http.route(
        "/accounts/v1/email/verification/request",
        type="http", auth="public", methods=["POST"], csrf=False,
    )
    def request_email_verification(self):
        denied = self._require_service()
        if denied:
            return denied
        data = _payload()
        identifier = data.get("identifier") or ""
        account = request.env["ky.account"].sudo().find_by_identifier(identifier)
        eligible = bool(account and account.status == "pending" and account.email)
        if eligible:
            token = account.issue_token("email_verification", 24 * 60)
            self._queue_security_email(account, "email_verification", token)
        self._audit(
            "email.verification_requested", "success" if eligible else "failure",
            data=data, account=account, identifier=identifier,
            details={"queued": eligible},
        )
        return _ok(message="If eligible, a verification email has been queued.")

    @http.route(
        "/accounts/v1/email/verify", type="http", auth="public", methods=["POST"], csrf=False
    )
    def verify_email(self):
        denied = self._require_service()
        if denied:
            return denied
        data = _payload()
        token = request.env["ky.account.token"].sudo().consume(
            data.get("token") or "", "email_verification"
        )
        if not token:
            self._audit("email.verification_failed", "failure", data=data, details={"reason": "invalid_or_expired"})
            return _error("invalid_token", "Verification link is invalid or expired.", status=400)
        token.account_id.write(
            {"email_verified": True, "email_verified_at": fields.Datetime.now(), "status": "active"}
        )
        self._audit("email.verified", "success", data=data, account=token.account_id)
        return _ok(account=token.account_id.oidc_claims())

    @http.route(
        "/accounts/v1/password/reset/request",
        type="http", auth="public", methods=["POST"], csrf=False,
    )
    def request_password_reset(self):
        denied = self._require_service()
        if denied:
            return denied
        data = _payload()
        identifier = data.get("identifier") or ""
        account = request.env["ky.account"].sudo().find_by_identifier(identifier)
        eligible = bool(account and account.status == "active" and account.email)
        if eligible:
            token = account.issue_token("password_reset", 30)
            self._queue_security_email(account, "password_reset", token)
        self._audit(
            "password.reset_requested", "success" if eligible else "failure",
            data=data, account=account, identifier=identifier,
            details={"queued": eligible},
        )
        return _ok(message="If eligible, a password reset email has been queued.")

    @http.route(
        "/accounts/v1/password/reset", type="http", auth="public", methods=["POST"], csrf=False
    )
    def reset_password(self):
        denied = self._require_service()
        if denied:
            return denied
        data = _payload()
        if len(data.get("password") or "") < 10:
            self._audit("password.reset_failed", "failure", data=data, details={"reason": "weak_password"})
            return _error("weak_password", "Password must contain at least 10 characters.")
        token = request.env["ky.account.token"].sudo().consume(
            data.get("token") or "", "password_reset"
        )
        if not token:
            self._audit("password.reset_failed", "failure", data=data, details={"reason": "invalid_or_expired"})
            return _error("invalid_token", "Reset link is invalid or expired.", status=400)
        token.account_id.set_password(data["password"])
        self._audit("password.reset_completed", "success", data=data, account=token.account_id)
        return _ok(message="Password has been updated.")

    @http.route(
        "/accounts/v1/account/claims", type="http", auth="public", methods=["POST"], csrf=False
    )
    def account_claims(self):
        denied = self._require_service()
        if denied:
            return denied
        subject = (_payload().get("subject_uuid") or "").strip()
        account = request.env["ky.account"].sudo().search(
            [("subject_uuid", "=", subject), ("status", "=", "active")], limit=1
        )
        if not account:
            return _error("not_found", "Account not found.", status=404)
        return _ok(account=account.oidc_claims())

    @http.route(
        "/accounts/v1/student/claim", type="http", auth="public", methods=["POST"], csrf=False
    )
    def claim_student(self):
        denied = self._require_service()
        if denied:
            return denied
        data = _payload()
        subject = (data.get("subject_uuid") or "").strip()
        access_code = (data.get("access_code") or "").strip().upper()
        relationship = data.get("relationship") or "self"
        if relationship not in {"self", "parent", "guardian"}:
            return _error("invalid_payload", "Relationship is invalid.")

        Account = request.env["ky.account"].sudo()
        account = Account.search([("subject_uuid", "=", subject), ("status", "=", "active")], limit=1)
        student = request.env["m.siswa"].sudo().search(
            [("access_code", "=", access_code), ("access_code_active", "=", True)], limit=1
        )
        if not account or not student:
            self._audit("student.claim_failed", "failure", data=data, account=account, details={"reason": "not_found"})
            return _error("claim_failed", "Student claim could not be completed.", status=400)

        Link = request.env["ky.account.student.link"].sudo()
        link = Link.search(
            [("account_id", "=", account.id), ("student_id", "=", student.id)], limit=1
        )
        allow_direct = (
            request.env["ir.config_parameter"].sudo().get_param(
                "accounts.allow_direct_student_claim", "False"
            ).lower()
            == "true"
        )
        target_status = "verified" if allow_direct else "pending"
        vals = {
            "relationship": relationship,
            "status": target_status,
            "verified_method": "student_access_code" if allow_direct else False,
        }
        if link:
            if link.status == "revoked":
                link.write(vals)
        else:
            link = Link.create({"account_id": account.id, "student_id": student.id, **vals})

        if target_status == "verified" and account.account_type == "public":
            account.write({"account_type": "student" if relationship == "self" else "guardian"})
        self._audit(
            "student.claim_requested", "success" if target_status == "verified" else "pending",
            data=data, account=account,
            details={"relationship": relationship, "claim_status": target_status, "student_id": student.id},
        )
        return _ok(
            claim={
                "status": link.status,
                "relationship": link.relationship,
                "student_name": student.name,
            }
        )

    @http.route(
        "/accounts/v1/consent", type="http", auth="public", methods=["POST"], csrf=False
    )
    def record_consent(self):
        denied = self._require_service()
        if denied:
            return denied
        data = _payload()
        subject = (data.get("subject_uuid") or "").strip()
        account = request.env["ky.account"].sudo().search(
            [("subject_uuid", "=", subject), ("status", "=", "active")], limit=1
        )
        allowed_purposes = {key for key, _label in request.env["ky.account.consent"]._fields["purpose"].selection}
        allowed_channels = {key for key, _label in request.env["ky.account.consent"]._fields["channel"].selection}
        status = data.get("status")
        if (
            not account
            or data.get("purpose") not in allowed_purposes
            or data.get("channel") not in allowed_channels
            or status not in {"granted", "revoked"}
            or not data.get("policy_version")
        ):
            return _error("invalid_payload", "Consent payload is invalid.")
        consent = request.env["ky.account.consent"].sudo().create(
            {
                "account_id": account.id,
                "actor_account_id": account.id,
                "purpose": data["purpose"],
                "channel": data["channel"],
                "status": status,
                "policy_version": str(data["policy_version"])[:64],
                "source": str(data.get("source") or "accounts_web")[:128],
                "evidence_ref": str(data.get("evidence_ref") or "")[:256],
            }
        )
        self._audit(
            "consent.recorded", "success", data=data, account=account,
            details={"purpose": data["purpose"], "channel": data["channel"], "status": status},
        )
        return _ok(consent_id=consent.id)

    @http.route(
        "/accounts/v1/audit", type="http", auth="public", methods=["POST"], csrf=False
    )
    def append_service_audit(self):
        denied = self._require_service()
        if denied:
            return denied
        data = _payload()
        allowed_events = {
            "oidc.authorization_succeeded",
            "oidc.authorization_failed",
            "oidc.token_issued",
            "oidc.token_failed",
            "oidc.logout_succeeded",
        }
        event = data.get("event")
        outcome = data.get("outcome")
        if event not in allowed_events or outcome not in {"success", "failure", "pending"}:
            return _error("invalid_payload", "Audit event is invalid.")
        subject = str(data.get("subject_uuid") or "")[:64]
        account = request.env["ky.account"].sudo().search(
            [("subject_uuid", "=", subject)], limit=1
        ) if subject else request.env["ky.account"].browse()
        incoming_details = data.get("details") if isinstance(data.get("details"), dict) else {}
        safe_details = {}
        if incoming_details.get("error"):
            safe_details["error"] = str(incoming_details["error"])[:128]
        self._audit(
            event, outcome, data=data, account=account,
            client_id=str(data.get("client_id") or "")[:128],
            details=safe_details,
        )
        return _ok(recorded=True)

    @http.route(
        "/accounts/v1/oidc/clients", type="http", auth="public", methods=["GET"], csrf=False
    )
    def oidc_clients(self):
        denied = self._require_service()
        if denied:
            return denied
        clients = request.env["ky.oidc.client"].sudo().search(
            [("status", "=", "active"), ("public_client", "=", True)]
        )
        return _ok(clients=[client.as_provider_configuration() for client in clients])
