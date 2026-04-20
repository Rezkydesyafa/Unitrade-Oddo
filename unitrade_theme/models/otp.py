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
    expires_at = fields.Datetime(string='Expires At', required=True)
    is_used = fields.Boolean(string='Used', default=False)
    create_date = fields.Datetime(string='Created', readonly=True)

    @api.model
    def generate_otp(self, user_id, email):
        """Generate a 6-digit OTP code for the given user."""
        # Invalidate any previous unused OTPs for this user
        self.search([
            ('user_id', '=', user_id),
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
            'expires_at': expires_at,
        })

        return otp_record

    @api.model
    def verify_otp(self, user_id, code):
        """Verify the OTP code for the given user. Returns True if valid."""
        otp_record = self.search([
            ('user_id', '=', user_id),
            ('code', '=', code),
            ('is_used', '=', False),
        ], order='create_date desc', limit=1)

        if not otp_record:
            return False

        # Check expiration
        if fields.Datetime.now() > otp_record.expires_at:
            return False

        # Mark as used
        otp_record.is_used = True
        return True
