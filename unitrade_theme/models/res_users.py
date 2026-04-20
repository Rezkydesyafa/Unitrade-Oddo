from odoo import models, fields

class ResUsers(models.Model):
    _inherit = 'res.users'

    is_otp_verified = fields.Boolean(string='Is OTP Verified', default=False)
