import logging

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class UnitradeSponsorshipRequest(models.Model):
    _name = 'unitrade.sponsorship.request'
    _description = 'UniTrade Sponsorship Request'
    _order = 'create_date desc, id desc'

    name = fields.Char(string='Nama Brand/Organisasi', required=True)
    contact_name = fields.Char(string='Nama Kontak', required=True)
    email = fields.Char(string='Email')
    phone = fields.Char(string='Nomor HP')
    campaign_goal = fields.Text(string='Tujuan Sponsorship', required=True)
    budget_note = fields.Char(string='Estimasi Budget')
    status = fields.Selection([
        ('new', 'Baru'),
        ('contacted', 'Dihubungi'),
        ('approved', 'Disetujui'),
        ('rejected', 'Ditolak'),
    ], string='Status', default='new', required=True, index=True)
    user_id = fields.Many2one('res.users', string='Diajukan Oleh', index=True, ondelete='set null')
    note = fields.Text(string='Catatan Admin')

    @api.constrains('email', 'phone')
    def _check_contact(self):
        for record in self:
            if not (record.email or record.phone):
                raise ValidationError('Isi minimal email atau nomor HP agar tim UniTrade dapat menghubungi Anda.')
