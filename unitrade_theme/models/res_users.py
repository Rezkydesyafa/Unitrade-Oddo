import logging

from odoo import api, models, fields
from odoo.exceptions import AccessDenied

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    is_otp_verified = fields.Boolean(string='Is OTP Verified', default=False)

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
