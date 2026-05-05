import logging

from odoo import api, models, fields
from odoo.exceptions import AccessDenied

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    is_otp_verified = fields.Boolean(string='Is OTP Verified', default=False)
    x_gender = fields.Selection([
        ('male', 'Laki-laki'),
        ('female', 'Perempuan'),
    ], string='Jenis Kelamin')
    x_birth_date = fields.Date(string='Tanggal Lahir')
    x_notify_all = fields.Boolean(string='Semua Notifikasi UniTrade', default=True)
    x_notify_transaction = fields.Boolean(string='Notifikasi Transaksi UniTrade', default=True)
    x_notify_promo = fields.Boolean(string='Notifikasi Promo UniTrade', default=True)

    def unitrade_allows_notification(self, category):
        """Return whether UniTrade may send a non-security notification to this user."""
        self.ensure_one()
        if category == 'transaction':
            return bool(self.x_notify_all and self.x_notify_transaction)
        if category == 'promo':
            return bool(self.x_notify_all and self.x_notify_promo)
        return bool(self.x_notify_all)

    def unitrade_send_notification_email(self, category, subject, body_html, email_values=None):
        """Send an email only when the user's UniTrade notification preference allows it."""
        self.ensure_one()
        if not self.unitrade_allows_notification(category):
            _logger.info(
                "Skipped UniTrade %s notification for user %s because it is disabled.",
                category, self.login,
            )
            return False

        email_to = self.email or self.partner_id.email
        if not email_to:
            _logger.info("Skipped UniTrade %s notification for user %s because email is empty.", category, self.login)
            return False

        values = {
            'email_to': email_to,
            'subject': subject,
            'body_html': body_html,
            'auto_delete': True,
        }
        if email_values:
            values.update(email_values)
        return self.env['mail.mail'].sudo().create(values).send()

    @api.model
    def _auth_oauth_signin(self, provider, validation, params):
        """Override to link existing users by email when signing in via OAuth.
        
        If a user registered via normal signup with the same email,
        link their account to the OAuth provider instead of failing.
        """
        oauth_uid = validation['user_id']
        
        # First, try the standard flow: search by oauth_uid + provider
        oauth_user = self.search([
            ("oauth_uid", "=", oauth_uid),
            ('oauth_provider_id', '=', provider)
        ])
        if oauth_user:
            oauth_user.write({'oauth_access_token': params['access_token']})
            return oauth_user.login

        # Not found by oauth_uid — try to find existing user by email
        email = validation.get('email')
        if email:
            existing_user = self.search([('login', '=', email)], limit=1)
            if existing_user:
                # Link the existing account to Google OAuth
                existing_user.write({
                    'oauth_provider_id': provider,
                    'oauth_uid': oauth_uid,
                    'oauth_access_token': params['access_token'],
                })
                _logger.info(
                    "Linked existing user %s to OAuth provider %s",
                    existing_user.login, provider
                )
                return existing_user.login

        # No existing user found — fall back to default signup flow
        return super()._auth_oauth_signin(provider, validation, params)
