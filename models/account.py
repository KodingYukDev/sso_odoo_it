import re
import hashlib
import secrets
from datetime import timedelta
import uuid

from passlib.context import CryptContext

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


PASSWORD_CONTEXT = CryptContext(schemes=["pbkdf2_sha512"], deprecated="auto")
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")


class KyAccount(models.Model):
    _name = "ky.account"
    _description = "KodingYuk External Account"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"
    _rec_name = "name"

    subject_uuid = fields.Char(
        string="Subject UUID",
        required=True,
        readonly=True,
        copy=False,
        index=True,
        default=lambda self: str(uuid.uuid4()),
        tracking=True,
        help="Immutable public identifier used as the OpenID Connect sub claim.",
    )
    name = fields.Char(required=True, tracking=True)
    username = fields.Char(index=True, tracking=True)
    email = fields.Char(index=True, tracking=True)
    password_hash = fields.Char(copy=False, groups="sso_odoo_it.group_accounts_manager")
    account_type = fields.Selection(
        [
            ("public", "Public"),
            ("student", "Student"),
            ("guardian", "Parent / Guardian"),
            ("client", "Product Client"),
        ],
        required=True,
        default="public",
        tracking=True,
    )
    status = fields.Selection(
        [
            ("pending", "Pending Verification"),
            ("active", "Active"),
            ("suspended", "Suspended"),
            ("deleted", "Deleted"),
        ],
        required=True,
        default="pending",
        index=True,
        tracking=True,
    )
    email_verified = fields.Boolean(default=False, tracking=True)
    email_verified_at = fields.Datetime(readonly=True, copy=False)
    partner_id = fields.Many2one(
        "res.partner",
        string="CRM / Billing Contact",
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    locale = fields.Char(default="id_ID")
    timezone = fields.Char(default="Asia/Jakarta")
    created_source = fields.Char(index=True, tracking=True)
    last_login_at = fields.Datetime(readonly=True, copy=False)
    student_link_ids = fields.One2many(
        "ky.account.student.link", "account_id", string="Student Links"
    )
    identity_ids = fields.One2many(
        "ky.account.identity", "account_id", string="External Identities"
    )
    consent_ids = fields.One2many(
        "ky.account.consent", "account_id", string="Consents"
    )
    token_ids = fields.One2many("ky.account.token", "account_id", string="Security Tokens")

    _sql_constraints = [
        ("subject_uuid_unique", "unique(subject_uuid)", "Subject UUID must be unique."),
        ("username_unique", "unique(username)", "Username is already used."),
        ("email_unique", "unique(email)", "Email is already registered."),
    ]

    @api.model
    def _normalize_email(self, value):
        return (value or "").strip().lower() or False

    @api.model
    def _normalize_username(self, value):
        return (value or "").strip().lower() or False

    @api.constrains("username")
    def _check_username(self):
        for account in self:
            if account.username and not USERNAME_RE.fullmatch(account.username):
                raise ValidationError(
                    _("Username must be 3-32 characters using letters, numbers, dot, dash, or underscore.")
                )

    @api.constrains("email", "username")
    def _check_case_insensitive_identity_unique(self):
        for account in self:
            for field_name in ("email", "username"):
                value = account[field_name]
                if not value:
                    continue
                duplicate = self.sudo().search(
                    [(field_name, "=ilike", value), ("id", "!=", account.id)], limit=1
                )
                if duplicate:
                    raise ValidationError(_("%s is already registered.") % field_name.title())

    @api.model_create_multi
    def create(self, vals_list):
        normalized = []
        for incoming in vals_list:
            vals = dict(incoming)
            vals["email"] = self._normalize_email(vals.get("email"))
            vals["username"] = self._normalize_username(vals.get("username"))
            normalized.append(vals)
        return super().create(normalized)

    def write(self, vals):
        vals = dict(vals)
        previous_status = {account.id: account.status for account in self} if "status" in vals else {}
        if "email" in vals:
            vals["email"] = self._normalize_email(vals.get("email"))
        if "username" in vals:
            vals["username"] = self._normalize_username(vals.get("username"))
        if vals.get("email_verified"):
            vals.setdefault("email_verified_at", fields.Datetime.now())
        result = super().write(vals)
        if "status" in vals:
            for account in self:
                if previous_status.get(account.id) != account.status:
                    self.env["ky.account.audit.log"].sudo().create(
                        {
                            "event": "account.status_changed",
                            "outcome": "success",
                            "account_id": account.id,
                            "source": "odoo_model",
                            "details": {"from": previous_status.get(account.id), "to": account.status},
                        }
                    )
        return result

    def set_password(self, raw_password):
        self.ensure_one()
        if not raw_password or len(raw_password) < 10:
            raise ValidationError(_("Password must contain at least 10 characters."))
        self.sudo().write({"password_hash": PASSWORD_CONTEXT.hash(raw_password)})

    def check_password(self, raw_password):
        self.ensure_one()
        if not self.password_hash or not raw_password:
            return False
        try:
            valid, replacement = PASSWORD_CONTEXT.verify_and_update(
                raw_password, self.password_hash
            )
        except (TypeError, ValueError):
            return False
        if valid and replacement:
            self.sudo().write({"password_hash": replacement})
        return bool(valid)

    @api.model
    def find_by_identifier(self, identifier):
        normalized = (identifier or "").strip().lower()
        if not normalized:
            return self.browse()
        return self.sudo().search(
            ["|", ("email", "=ilike", normalized), ("username", "=ilike", normalized)],
            limit=1,
        )

    def oidc_claims(self):
        self.ensure_one()
        verified_links = self.student_link_ids.filtered(lambda link: link.status == "verified")
        return {
            "sub": self.subject_uuid,
            "name": self.name,
            "preferred_username": self.username or "",
            "email": self.email or "",
            "email_verified": bool(self.email_verified or self.status == "active"),
            "account_type": self.account_type,
            "is_student": bool(verified_links),
            "locale": self.locale or "id_ID",
            "zoneinfo": self.timezone or "Asia/Jakarta",
        }

    def issue_token(self, purpose, lifetime_minutes):
        self.ensure_one()
        now = fields.Datetime.now()
        self.env["ky.account.token"].sudo().search(
            [
                ("account_id", "=", self.id),
                ("purpose", "=", purpose),
                ("consumed_at", "=", False),
            ]
        ).write({"consumed_at": now})
        raw_token = secrets.token_urlsafe(32)
        self.env["ky.account.token"].sudo().create(
            {
                "account_id": self.id,
                "purpose": purpose,
                "token_hash": hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
                "expires_at": now + timedelta(minutes=lifetime_minutes),
            }
        )
        return raw_token


class KyAccountIdentity(models.Model):
    _name = "ky.account.identity"
    _description = "KodingYuk External Identity"
    _order = "create_date desc"

    account_id = fields.Many2one("ky.account", required=True, ondelete="cascade", index=True)
    provider = fields.Selection(
        [("google", "Google"), ("legacy_kodyhost", "Legacy KodyHost"), ("legacy_lms", "Legacy LMS")],
        required=True,
        index=True,
    )
    provider_subject = fields.Char(required=True, index=True)
    provider_email = fields.Char()
    last_used_at = fields.Datetime(readonly=True)

    _sql_constraints = [
        (
            "provider_subject_unique",
            "unique(provider, provider_subject)",
            "This provider identity is already linked.",
        )
    ]


class KyAccountToken(models.Model):
    _name = "ky.account.token"
    _description = "KodingYuk Account One-Time Security Token"
    _order = "create_date desc"

    account_id = fields.Many2one("ky.account", required=True, ondelete="cascade", index=True)
    purpose = fields.Selection(
        [("email_verification", "Email Verification"), ("password_reset", "Password Reset")],
        required=True,
        index=True,
    )
    token_hash = fields.Char(required=True, readonly=True, copy=False, index=True)
    expires_at = fields.Datetime(required=True, readonly=True, copy=False, index=True)
    consumed_at = fields.Datetime(readonly=True, copy=False, index=True)

    _sql_constraints = [
        ("token_hash_unique", "unique(token_hash)", "Security token hash must be unique."),
    ]

    @api.model
    def consume(self, raw_token, purpose):
        token_hash = hashlib.sha256((raw_token or "").encode("utf-8")).hexdigest()
        token = self.sudo().search(
            [
                ("token_hash", "=", token_hash),
                ("purpose", "=", purpose),
                ("consumed_at", "=", False),
                ("expires_at", ">", fields.Datetime.now()),
            ],
            limit=1,
        )
        if not token:
            return self.browse()
        token.write({"consumed_at": fields.Datetime.now()})
        return token


class KyAccountAuditLog(models.Model):
    _name = "ky.account.audit.log"
    _description = "KodingYuk Account Security Audit Log"
    _order = "occurred_at desc, id desc"
    _rec_name = "event"

    occurred_at = fields.Datetime(required=True, readonly=True, default=fields.Datetime.now, index=True)
    event = fields.Char(required=True, readonly=True, index=True)
    outcome = fields.Selection(
        [("success", "Success"), ("failure", "Failure"), ("pending", "Pending")],
        required=True,
        readonly=True,
        index=True,
    )
    account_id = fields.Many2one("ky.account", readonly=True, ondelete="set null", index=True)
    actor_user_id = fields.Many2one(
        "res.users", readonly=True, ondelete="set null", default=lambda self: self.env.user, index=True
    )
    subject_uuid = fields.Char(readonly=True, index=True)
    identifier_hint = fields.Char(readonly=True, help="Masked identifier; never stores the full login value.")
    client_id = fields.Char(readonly=True, index=True)
    request_id = fields.Char(readonly=True, index=True)
    ip_address = fields.Char(readonly=True, groups="sso_odoo_it.group_accounts_manager")
    user_agent = fields.Char(readonly=True, groups="sso_odoo_it.group_accounts_manager")
    source = fields.Char(readonly=True, index=True)
    details = fields.Json(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        normalized = []
        for incoming in vals_list:
            vals = dict(incoming)
            account = (
                self.env["ky.account"].sudo().browse(vals["account_id"]).exists()
                if vals.get("account_id")
                else self.env["ky.account"].browse()
            )
            if account:
                vals.setdefault("subject_uuid", account.subject_uuid)
            vals["event"] = str(vals.get("event") or "unknown")[:128]
            vals["identifier_hint"] = str(vals.get("identifier_hint") or "")[:128]
            vals["client_id"] = str(vals.get("client_id") or "")[:128]
            vals["request_id"] = str(vals.get("request_id") or "")[:128]
            vals["ip_address"] = str(vals.get("ip_address") or "")[:64]
            vals["user_agent"] = str(vals.get("user_agent") or "")[:512]
            vals["source"] = str(vals.get("source") or "accounts_service")[:128]
            normalized.append(vals)
        return super().create(normalized)

    def write(self, _vals):
        raise UserError(_("Security audit logs are append-only and cannot be changed."))

    def unlink(self):
        raise UserError(_("Security audit logs are append-only and cannot be deleted."))

    @api.model
    def _cron_purge_expired(self):
        raw_days = self.env["ir.config_parameter"].sudo().get_param(
            "accounts.audit_retention_days", "365"
        )
        try:
            retention_days = max(30, int(raw_days))
        except (TypeError, ValueError):
            retention_days = 365
        cutoff = fields.Datetime.now() - timedelta(days=retention_days)
        self.env.cr.execute(
            "DELETE FROM ky_account_audit_log WHERE occurred_at < %s",
            [cutoff],
        )
        deleted_count = self.env.cr.rowcount
        if deleted_count:
            self.sudo().create(
                {
                    "event": "audit.retention_purge",
                    "outcome": "success",
                    "source": "scheduled_action",
                    "details": {
                        "deleted_count": deleted_count,
                        "retention_days": retention_days,
                    },
                }
            )


class KyAccountStudentLink(models.Model):
    _name = "ky.account.student.link"
    _description = "KodingYuk Account to Student Link"
    _inherit = ["mail.thread"]
    _order = "create_date desc"

    account_id = fields.Many2one(
        "ky.account", required=True, ondelete="cascade", index=True, tracking=True
    )
    student_id = fields.Many2one(
        "m.siswa", required=True, ondelete="restrict", index=True, tracking=True
    )
    relationship = fields.Selection(
        [("self", "Self"), ("parent", "Parent"), ("guardian", "Guardian")],
        required=True,
        default="self",
        tracking=True,
    )
    status = fields.Selection(
        [("pending", "Pending"), ("verified", "Verified"), ("revoked", "Revoked")],
        required=True,
        default="pending",
        index=True,
        tracking=True,
    )
    verified_method = fields.Selection(
        [
            ("student_access_code", "Student Access Code"),
            ("guardian_otp", "Guardian OTP"),
            ("admin", "Admin Approval"),
            ("legacy_mapping", "Legacy Migration"),
        ],
        tracking=True,
    )
    verified_at = fields.Datetime(readonly=True, copy=False)
    revoked_at = fields.Datetime(readonly=True, copy=False)

    _sql_constraints = [
        (
            "account_student_unique",
            "unique(account_id, student_id)",
            "This account is already linked to the student.",
        )
    ]

    def write(self, vals):
        vals = dict(vals)
        previous_status = {link.id: link.status for link in self} if "status" in vals else {}
        if vals.get("status") == "verified":
            vals.setdefault("verified_at", fields.Datetime.now())
        if vals.get("status") == "revoked":
            vals.setdefault("revoked_at", fields.Datetime.now())
        result = super().write(vals)
        if "status" in vals:
            for link in self:
                if previous_status.get(link.id) != link.status:
                    self.env["ky.account.audit.log"].sudo().create(
                        {
                            "event": "student.link_status_changed",
                            "outcome": "success",
                            "account_id": link.account_id.id,
                            "source": "odoo_model",
                            "details": {
                                "student_id": link.student_id.id,
                                "from": previous_status.get(link.id),
                                "to": link.status,
                                "method": link.verified_method or "",
                            },
                        }
                    )
        return result


class KyAccountConsent(models.Model):
    _name = "ky.account.consent"
    _description = "KodingYuk Account Consent"
    _order = "create_date desc"
    _log_access = True

    account_id = fields.Many2one("ky.account", required=True, ondelete="cascade", index=True)
    student_id = fields.Many2one("m.siswa", ondelete="restrict", index=True)
    purpose = fields.Selection(
        [
            ("terms", "Terms of Service"),
            ("privacy", "Privacy Policy"),
            ("marketing", "Marketing"),
            ("events", "Events and Information"),
            ("project_publication", "Student Project Publication"),
        ],
        required=True,
        index=True,
    )
    channel = fields.Selection(
        [("service", "Service"), ("email", "Email"), ("whatsapp", "WhatsApp"), ("public_web", "Public Web")],
        required=True,
        default="service",
        index=True,
    )
    status = fields.Selection(
        [("granted", "Granted"), ("revoked", "Revoked")], required=True, index=True
    )
    actor_account_id = fields.Many2one(
        "ky.account", string="Consent Given By", ondelete="restrict"
    )
    policy_version = fields.Char(required=True)
    source = fields.Char(required=True)
    evidence_ref = fields.Char(copy=False)
    consented_at = fields.Datetime(readonly=True, copy=False)
    revoked_at = fields.Datetime(readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        now = fields.Datetime.now()
        normalized = []
        for incoming in vals_list:
            vals = dict(incoming)
            if vals.get("status") == "granted":
                vals.setdefault("consented_at", now)
            else:
                vals.setdefault("revoked_at", now)
            normalized.append(vals)
        return super().create(normalized)


class KyOidcClient(models.Model):
    _name = "ky.oidc.client"
    _description = "KodingYuk OpenID Connect Client"
    _order = "name"

    name = fields.Char(required=True)
    client_id = fields.Char(required=True, index=True)
    public_client = fields.Boolean(default=True, required=True)
    redirect_uris = fields.Text(
        required=True, help="One exact HTTPS redirect URI per line. HTTP is allowed only for localhost."
    )
    post_logout_redirect_uris = fields.Text(help="One exact URI per line.")
    scope = fields.Char(default="openid profile email student.basic")
    status = fields.Selection(
        [("active", "Active"), ("disabled", "Disabled")], default="active", required=True
    )

    _sql_constraints = [
        ("client_id_unique", "unique(client_id)", "Client ID must be unique.")
    ]

    @api.constrains("redirect_uris", "post_logout_redirect_uris")
    def _check_redirect_uris(self):
        for client in self:
            for value in (client.redirect_uris or "").splitlines() + (
                client.post_logout_redirect_uris or ""
            ).splitlines():
                uri = value.strip()
                if not uri:
                    continue
                if not (uri.startswith("https://") or uri.startswith("http://localhost")):
                    raise ValidationError(_("Redirect URIs must use HTTPS or localhost HTTP."))

    def as_provider_configuration(self):
        self.ensure_one()
        if not self.public_client:
            raise ValidationError(_("Confidential clients are not exposed by the MVP registry."))
        return {
            "client_id": self.client_id,
            "client_name": self.name,
            "redirect_uris": [uri.strip() for uri in self.redirect_uris.splitlines() if uri.strip()],
            "post_logout_redirect_uris": [
                uri.strip() for uri in (self.post_logout_redirect_uris or "").splitlines() if uri.strip()
            ],
            "response_types": ["code"],
            "grant_types": ["authorization_code", "refresh_token"],
            "token_endpoint_auth_method": "none",
            "application_type": "web",
        }
