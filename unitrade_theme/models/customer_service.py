import logging

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class UnitradeCustomerTicket(models.Model):
    _name = 'unitrade.customer.ticket'
    _description = 'UniTrade Customer Service Ticket'
    _order = 'create_date desc, id desc'

    name = fields.Char(
        string='Nomor Tiket',
        required=True,
        readonly=True,
        copy=False,
        default=lambda self: _('New'),
    )
    user_id = fields.Many2one(
        'res.users',
        string='Pembeli',
        required=True,
        index=True,
        default=lambda self: self.env.user,
        ondelete='restrict',
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Kontak Pembeli',
        required=True,
        index=True,
        ondelete='restrict',
    )
    category = fields.Selection(
        [
            ('order_issue', 'Pesanan Bermasalah'),
            ('refund_return', 'Refund / Pengembalian'),
            ('contact_cs', 'Hubungi Customer Service'),
        ],
        string='Kategori Masalah',
        required=True,
        index=True,
    )
    order_id = fields.Many2one(
        'sale.order',
        string='Nomor Pesanan',
        index=True,
        ondelete='set null',
    )
    title = fields.Char(string='Judul Masalah', required=True)
    description = fields.Text(string='Deskripsi Keluhan', required=True)
    status = fields.Selection(
        [
            ('pending', 'Pending'),
            ('in_progress', 'Diproses'),
            ('done', 'Selesai'),
        ],
        string='Status',
        default='pending',
        required=True,
        index=True,
    )
    evidence_ids = fields.One2many(
        'unitrade.customer.ticket.evidence',
        'ticket_id',
        string='Bukti Upload',
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('partner_id') and vals.get('user_id'):
                user = self.env['res.users'].browse(vals['user_id'])
                vals['partner_id'] = user.partner_id.id
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code('unitrade.customer.ticket')
                    or _('New')
                )
        return super().create(vals_list)

    @api.constrains('partner_id', 'order_id')
    def _check_order_owner(self):
        for ticket in self:
            if not ticket.order_id or not ticket.partner_id:
                continue
            buyer_commercial = ticket.partner_id.commercial_partner_id
            order_commercial = ticket.order_id.partner_id.commercial_partner_id
            if buyer_commercial != order_commercial:
                _logger.warning(
                    'Blocked customer ticket %s with non-owned order %s for partner %s',
                    ticket.name,
                    ticket.order_id.name,
                    ticket.partner_id.id,
                )
                raise ValidationError(
                    _('Nomor pesanan tidak ditemukan atau bukan milik akun Anda.')
                )


class UnitradeCustomerTicketEvidence(models.Model):
    _name = 'unitrade.customer.ticket.evidence'
    _description = 'UniTrade Customer Service Ticket Evidence'
    _order = 'id asc'

    ticket_id = fields.Many2one(
        'unitrade.customer.ticket',
        string='Tiket',
        required=True,
        index=True,
        ondelete='cascade',
    )
    attachment_id = fields.Many2one(
        'ir.attachment',
        string='Attachment',
        required=True,
        ondelete='cascade',
    )
    name = fields.Char(related='attachment_id.name', string='Nama File', readonly=True)
    mimetype = fields.Char(related='attachment_id.mimetype', string='MIME Type', readonly=True)
    file_size = fields.Integer(related='attachment_id.file_size', string='Ukuran File', readonly=True)
