import random
import string
from datetime import timedelta
from odoo import api, fields, models


class UnitradeOtp(models.Model):
    _name = 'unitrade.otp'
    _description = 'UniTrade OTP Verification Codes'

    user_id = fields.Many2one('res.users', string='User', required=True, ondelete='cascade')
    code = fields.Char(string='OTP Code', required=True)
    email = fields.Char(string='Email', required=True)
    purpose = fields.Selection([
        ('account_verification', 'Account Verification'),
        ('seller_onboarding', 'Seller Onboarding'),
        ('settings_password_reset', 'Settings Password Reset'),
    ], string='Purpose', default='account_verification', required=True, index=True)
    expires_at = fields.Datetime(string='Expires At', required=True)
    is_used = fields.Boolean(string='Used', default=False)
    create_date = fields.Datetime(string='Created', readonly=True)

    @api.model
    def rate_limit_status(self, user_id, purpose='account_verification', window_minutes=10, max_attempts=3):
        """Return whether a user can request another OTP for a purpose."""
        cutoff = fields.Datetime.now() - timedelta(minutes=window_minutes)
        attempts = self.search_count([
            ('user_id', '=', user_id),
            ('purpose', '=', purpose),
            ('create_date', '>=', cutoff),
        ])
        return {
            'allowed': attempts < max_attempts,
            'attempts': attempts,
            'max_attempts': max_attempts,
            'window_minutes': window_minutes,
        }

    @api.model
    def generate_otp(self, user_id, email, purpose='account_verification'):
        """Generate a 6-digit OTP code for the given user."""
        # Invalidate any previous unused OTPs for this user and purpose.
        self.search([
            ('user_id', '=', user_id),
            ('purpose', '=', purpose),
            ('is_used', '=', False),
        ]).write({'is_used': True})

        # Generate a new 6-digit code
        code = ''.join(random.choices(string.digits, k=6))

        # OTP valid for 5 minutes
        expires_at = fields.Datetime.now() + timedelta(minutes=5)

        otp_record = self.create({
            'user_id': user_id,
            'code': code,
            'email': email,
            'purpose': purpose,
            'expires_at': expires_at,
        })

        return otp_record

    @api.model
    def verify_otp(self, user_id, code, purpose=None):
        """Verify the OTP code for the given user. Returns True if valid."""
        domain = [
            ('user_id', '=', user_id),
            ('code', '=', code),
            ('is_used', '=', False),
        ]
        if purpose:
            domain.append(('purpose', '=', purpose))
        otp_record = self.search(domain, order='create_date desc', limit=1)

        if not otp_record:
            return False

        # Check expiration
        if fields.Datetime.now() > otp_record.expires_at:
            return False

        # Mark as used
        otp_record.is_used = True
        return True
