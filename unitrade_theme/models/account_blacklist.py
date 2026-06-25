import re

from odoo import api, fields, models


class UnitradeAccountBlacklist(models.Model):
    _name = 'unitrade.account.blacklist'
    _description = 'UniTrade Account Contact Blacklist'
    _order = 'create_date desc, id desc'

    contact_type = fields.Selection(
        [
            ('email', 'Email'),
            ('phone', 'Nomor Telepon'),
        ],
        string='Tipe Kontak',
        required=True,
        index=True,
    )
    value = fields.Char(string='Kontak Asli', required=True)
    normalized_value = fields.Char(string='Kontak Normalisasi', required=True, index=True)
    source_user_id = fields.Many2one('res.users', string='User Sumber', ondelete='set null', index=True)
    source_partner_id = fields.Many2one('res.partner', string='Partner Sumber', ondelete='set null', index=True)
    reason = fields.Text(string='Alasan')
    requested_at = fields.Datetime(string='Tanggal Permintaan', required=True, default=fields.Datetime.now, index=True)
    ip_address = fields.Char(string='IP Address')
    user_agent = fields.Char(string='User Agent')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            'contact_type_normalized_value_unique',
            'unique(contact_type, normalized_value)',
            'Kontak ini sudah masuk daftar blokir UniTrade.',
        ),
    ]

    @api.model
    def _normalize_email(self, value):
        return (value or '').strip().lower()

    @api.model
    def _normalize_phone(self, value):
        return re.sub(r'[\s\-.()]+', '', (value or '').strip())

    @api.model
    def _contact_values_from_user(self, user):
        user = user.sudo()
        partner = user.partner_id.sudo()
        contacts = []
        seen = set()

        email_values = [user.login, user.email, partner.email]
        for value in email_values:
            normalized = self._normalize_email(value)
            if normalized and '@' in normalized and ('email', normalized) not in seen:
                seen.add(('email', normalized))
                contacts.append(('email', value, normalized))

        phone_values = [
            user.x_whatsapp if 'x_whatsapp' in user._fields else '',
            partner.phone,
            partner.mobile,
        ]
        for value in phone_values:
            normalized = self._normalize_phone(value)
            if normalized and ('phone', normalized) not in seen:
                seen.add(('phone', normalized))
                contacts.append(('phone', value, normalized))

        return contacts

    @api.model
    def add_user_contacts(self, user, reason=False, ip_address=False, user_agent=False):
        records = self.sudo().browse()
        user = user.sudo()
        partner = user.partner_id.sudo()
        for contact_type, value, normalized in self._contact_values_from_user(user):
            vals = {
                'contact_type': contact_type,
                'value': value,
                'normalized_value': normalized,
                'source_user_id': user.id,
                'source_partner_id': partner.id if partner else False,
                'reason': reason or '',
                'requested_at': fields.Datetime.now(),
                'ip_address': ip_address or '',
                'user_agent': user_agent or '',
                'active': True,
            }
            existing = self.sudo().with_context(active_test=False).search([
                ('contact_type', '=', contact_type),
                ('normalized_value', '=', normalized),
            ], limit=1)
            if existing:
                existing.write(vals)
                records |= existing
            else:
                records |= self.sudo().create(vals)
        return records

    @api.model
    def is_contact_blocked(self, email=False, phone=False):
        checks = []
        normalized_email = self._normalize_email(email)
        if normalized_email:
            checks.append(('email', normalized_email))
        normalized_phone = self._normalize_phone(phone)
        if normalized_phone:
            checks.append(('phone', normalized_phone))

        for contact_type, normalized in checks:
            if self.sudo().search_count([
                ('active', '=', True),
                ('contact_type', '=', contact_type),
                ('normalized_value', '=', normalized),
            ], limit=1):
                return True
        return False
