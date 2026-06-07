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
    message_ids = fields.One2many(
        'unitrade.customer.ticket.message',
        'ticket_id',
        string='Thread Bantuan',
        readonly=True,
    )
    last_message_at = fields.Datetime(
        string='Pesan Terakhir',
        readonly=True,
        copy=False,
        index=True,
    )
    resolved_note = fields.Text(string='Catatan Penyelesaian', copy=False)
    resolved_at = fields.Datetime(string='Diselesaikan Pada', readonly=True, copy=False)
    resolved_by_id = fields.Many2one(
        'res.users',
        string='Diselesaikan Oleh',
        readonly=True,
        copy=False,
        ondelete='set null',
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

    def _customer_ticket_url(self):
        self.ensure_one()
        return '/my/customer-service/tickets/%s' % self.id

    def _status_label(self, status=False):
        self.ensure_one()
        value = status or self.status
        return dict(self._fields['status'].selection).get(value, value or '-')

    def _emit_customer_notification(self, event_code, title, message, discriminator=''):
        if 'unitrade.notification' not in self.env.registry:
            return self.env['res.users'].browse()
        Notification = self.env['unitrade.notification'].sudo()
        for ticket in self.sudo():
            try:
                Notification.emit(
                    user_id=ticket.user_id.id,
                    event_code=event_code,
                    payload={
                        'reference_model': ticket._name,
                        'reference_id': ticket.id,
                        'action_url': ticket._customer_ticket_url(),
                        'title_override': title,
                        'message_override': message,
                    },
                    channels=['in_app'],
                    idempotency_discriminator=discriminator or fields.Datetime.now(),
                )
            except Exception:
                _logger.exception(
                    'Failed to emit customer service notification for ticket %s',
                    ticket.name,
                )
        return True

    def action_add_thread_message(self, body, author=False, message_type='customer', notify_customer=True):
        Message = self.env['unitrade.customer.ticket.message'].sudo()
        author = author or self.env.user
        message_type = message_type if message_type in ('customer', 'admin', 'system') else 'customer'
        body = (body or '').strip()
        if not body:
            raise ValidationError(_('Pesan tidak boleh kosong.'))
        messages = Message.browse()
        now = fields.Datetime.now()
        for ticket in self.sudo():
            message = Message.create({
                'ticket_id': ticket.id,
                'author_id': author.id,
                'message_type': message_type,
                'body': body,
            })
            ticket.write({'last_message_at': now})
            messages |= message
            if notify_customer and message_type in ('admin', 'system'):
                title = _('Balasan Customer Service untuk %s') % ticket.name
                ticket._emit_customer_notification(
                    'system.customer_ticket_reply',
                    title,
                    self._short_notification(body),
                    discriminator='message:%s' % message.id,
                )
        return messages

    def action_update_status_from_admin(self, status, note=False, admin=False):
        status = status if status in ('pending', 'in_progress', 'done') else ''
        if not status:
            raise ValidationError(_('Status tiket tidak valid.'))
        admin = admin or self.env.user
        note = (note or '').strip()
        now = fields.Datetime.now()
        for ticket in self.sudo():
            previous_label = ticket._status_label()
            values = {'status': status}
            if status == 'done':
                values.update({
                    'resolved_note': note or ticket.resolved_note,
                    'resolved_at': now,
                    'resolved_by_id': admin.id,
                })
            elif status != 'done':
                values.update({
                    'resolved_note': False,
                    'resolved_at': False,
                    'resolved_by_id': False,
                })
            ticket.write(values)
            current_label = ticket._status_label(status)
            system_body = note or _('Status tiket berubah dari %s menjadi %s.') % (
                previous_label,
                current_label,
            )
            ticket.action_add_thread_message(
                system_body,
                author=admin,
                message_type='system',
                notify_customer=False,
            )
            ticket._emit_customer_notification(
                'system.customer_ticket_status',
                _('Status tiket %s: %s') % (ticket.name, current_label),
                self._short_notification(system_body),
                discriminator='status:%s:%s' % (status, now),
            )
        return True

    @staticmethod
    def _short_notification(value, limit=140):
        value = (value or '').strip()
        if len(value) <= limit:
            return value
        return value[:limit].rstrip() + '...'


class UnitradeCustomerTicketMessage(models.Model):
    _name = 'unitrade.customer.ticket.message'
    _description = 'UniTrade Customer Service Ticket Message'
    _order = 'create_date asc, id asc'

    ticket_id = fields.Many2one(
        'unitrade.customer.ticket',
        string='Tiket',
        required=True,
        index=True,
        ondelete='cascade',
    )
    author_id = fields.Many2one(
        'res.users',
        string='Pengirim',
        required=True,
        default=lambda self: self.env.user,
        ondelete='restrict',
    )
    message_type = fields.Selection(
        [
            ('customer', 'User'),
            ('admin', 'Customer Service'),
            ('system', 'Sistem'),
        ],
        string='Tipe Pesan',
        default='customer',
        required=True,
        index=True,
    )
    body = fields.Text(string='Pesan', required=True)


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
