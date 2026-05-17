import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class UnitradeSecurityActivity(models.Model):
    _name = 'unitrade.security.activity'
    _description = 'UniTrade Security Activity'
    _order = 'event_date desc, id desc'

    user_id = fields.Many2one('res.users', string='User', required=True, index=True, ondelete='cascade')
    event_type = fields.Selection([
        ('register', 'Registrasi'),
        ('consent_accepted', 'Terms & Privacy Disetujui'),
        ('otp_verified', 'OTP Diverifikasi'),
        ('login', 'Login'),
        ('password_change', 'Perubahan Password'),
        ('session_revoke', 'Session Dicabut'),
        ('session_revoke_all', 'Semua Session Dicabut'),
        ('deactivate_anonymize', 'Akun Dinonaktifkan'),
    ], string='Event', required=True, index=True)
    title = fields.Char(string='Judul', required=True)
    detail = fields.Char(string='Detail')
    ip_address = fields.Char(string='IP Address')
    user_agent = fields.Char(string='User Agent')
    session_id = fields.Char(string='Session ID')
    event_date = fields.Datetime(string='Waktu', required=True, default=fields.Datetime.now, index=True)

    @api.model
    def record_activity(self, user, event_type, title=False, detail=False, ip_address=False,
                        user_agent=False, session_id=False):
        """Create a persistent security activity row for the given user."""
        user = user.sudo() if user else self.env.user.sudo()
        if not user or not user.exists():
            _logger.warning("Skipped UniTrade security activity %s because user is missing.", event_type)
            return self.browse()
        return self.sudo().create({
            'user_id': user.id,
            'event_type': event_type,
            'title': title or dict(self._fields['event_type'].selection).get(event_type, event_type),
            'detail': detail or '',
            'ip_address': ip_address or '',
            'user_agent': user_agent or '',
            'session_id': session_id or '',
        })
