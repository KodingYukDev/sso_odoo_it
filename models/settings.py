from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    accounts_public_origin = fields.Char(
        string="Public Accounts URL",
        config_parameter="accounts.public_origin",
        help="Exact public origin, for example https://account.kodingyuk.id",
    )
    accounts_api_key = fields.Char(
        string="Accounts Service API Key",
        config_parameter="accounts.api_key",
        help="Server-to-server secret shared only with the Accounts web service.",
    )
    accounts_email_from = fields.Char(
        string="Security Email Sender",
        config_parameter="accounts.email_from",
        help="Verified sender address used for verification and password reset email.",
    )
    accounts_allow_direct_student_claim = fields.Boolean(
        string="Verify Student Claim from ST Code Directly",
        config_parameter="accounts.allow_direct_student_claim",
        default=False,
        help="Keep disabled until the additional student or guardian verification policy is approved.",
    )
    accounts_audit_retention_days = fields.Integer(
        string="Audit Log Retention (Days)",
        config_parameter="accounts.audit_retention_days",
        default=365,
        help="Audit records older than this are removed by a controlled scheduled action. Minimum 30 days.",
    )
