import base64
import binascii
import logging

from odoo import _, fields, http
from odoo.exceptions import ValidationError
from odoo.http import request

_logger = logging.getLogger(__name__)


class UnitradeCustomerServiceController(http.Controller):
    """Buyer customer service pages and JSON endpoints."""

    _MAX_EVIDENCE_SIZE = 5 * 1024 * 1024
    _ALLOWED_EVIDENCE_MIMETYPES = {
        'image/jpeg',
        'image/png',
        'video/mp4',
    }
    _CATEGORY_META = {
        'order_issue': {
            'label': 'Pesanan Bermasalah',
            'description': 'Laporkan masalah dengan pesanan Anda',
            'tone': 'red',
        },
        'refund_return': {
            'label': 'Refund / Pengembalian',
            'description': 'Ajukan pengembalian dana atau produk',
            'tone': 'orange',
        },
        'contact_cs': {
            'label': 'Hubungi Customer Service',
            'description': 'Chat langsung dengan tim kami',
            'tone': 'blue',
        },
    }
    _STATUS_META = {
        'pending': {'label': 'Pending', 'tone': 'orange'},
        'in_progress': {'label': 'Diproses', 'tone': 'blue'},
        'done': {'label': 'Selesai', 'tone': 'green'},
    }

    @http.route(
        ['/customer-service', '/my/customer-service'],
        type='http',
        auth='user',
        website=True,
        sitemap=False,
    )
    def customer_service_page(self, **kwargs):
        return request.render('unitrade_theme.customer_service_page', {
            'page_title': 'Customer Service',
        })

    @http.route(
        '/customer-service/data',
        type='json',
        auth='user',
        website=True,
        methods=['POST'],
    )
    def customer_service_data(self, **kwargs):
        tickets = self._customer_tickets(limit=3)
        return {
            'success': True,
            'categories': self._category_payloads(),
            'orders': self._order_options(),
            'recent_tickets': [self._ticket_payload(ticket) for ticket in tickets],
            'all_tickets_url': '/my/customer-service/tickets',
        }

    @http.route(
        '/customer-service/ticket/create',
        type='json',
        auth='user',
        website=True,
        methods=['POST'],
    )
    def create_customer_ticket(self, **kwargs):
        category = (kwargs.get('category') or '').strip()
        order_ref = (kwargs.get('order_ref') or '').strip()
        title = (kwargs.get('title') or '').strip()
        description = (kwargs.get('description') or '').strip()
        evidence_files = kwargs.get('evidence_files') or []

        if category not in self._CATEGORY_META:
            return {'success': False, 'message': _('Kategori masalah wajib dipilih.')}
        if not title:
            return {'success': False, 'message': _('Judul masalah wajib diisi.')}
        if not description:
            return {'success': False, 'message': _('Deskripsi keluhan wajib diisi.')}
        if not isinstance(evidence_files, list):
            return {'success': False, 'message': _('Format bukti upload tidak valid.')}

        order = False
        if order_ref:
            order = self._find_customer_order(order_ref)
            if not order:
                return {
                    'success': False,
                    'message': _('Nomor pesanan tidak ditemukan atau bukan milik akun Anda.'),
                }

        prepared_files = []
        for file_payload in evidence_files:
            try:
                prepared_files.append(self._prepare_evidence_payload(file_payload))
            except ValidationError as error:
                return {'success': False, 'message': str(error)}

        partner = request.env.user.partner_id
        ticket_vals = {
            'user_id': request.env.uid,
            'partner_id': partner.id,
            'category': category,
            'order_id': order.id if order else False,
            'title': title,
            'description': description,
        }

        uid = request.env.uid
        try:
            with request.env.cr.savepoint():
                ticket = request.env['unitrade.customer.ticket'].sudo().create(ticket_vals)
                self._create_evidence_records(ticket, prepared_files)
                ticket.action_add_thread_message(
                    description,
                    author=request.env.user,
                    message_type='customer',
                    notify_customer=False,
                )
                if category == 'refund_return' and order:
                    refund_context = self._refund_context(ticket)
                    if refund_context.get('url'):
                        ticket.action_add_thread_message(
                            _(
                                'Untuk proses refund resmi, buka tombol "%s" pada detail tiket agar alur pengembalian tercatat lengkap.'
                            ) % refund_context.get('label'),
                            author=request.env.user,
                            message_type='system',
                            notify_customer=False,
                        )
        except Exception as error:
            request.env.clear()
            _logger.exception('Failed to create customer service ticket for user %s', uid)
            return {
                'success': False,
                'message': str(error) or _('Tiket belum bisa dikirim. Coba lagi sebentar.'),
            }

        recent_tickets = self._customer_tickets(limit=3)
        return {
            'success': True,
            'message': _('Tiket berhasil dikirim.'),
            'ticket': self._ticket_payload(ticket),
            'recent_tickets': [self._ticket_payload(item) for item in recent_tickets],
        }

    @http.route(
        ['/my/customer-service/tickets', '/customer-service/tickets'],
        type='http',
        auth='user',
        website=True,
        sitemap=False,
    )
    def customer_tickets_page(self, **kwargs):
        tickets = self._customer_tickets(limit=80)
        return request.render('unitrade_theme.customer_service_tickets_page', {
            'page_title': 'Tiket Bantuan',
            'tickets': [self._ticket_payload(ticket, include_description=True) for ticket in tickets],
        })

    @http.route(
        '/my/customer-service/tickets/<int:ticket_id>',
        type='http',
        auth='user',
        website=True,
        sitemap=False,
    )
    def customer_ticket_detail_page(self, ticket_id, **kwargs):
        ticket = self._customer_ticket(ticket_id)
        if not ticket:
            return request.not_found()
        return request.render('unitrade_theme.customer_service_ticket_detail_page', {
            'page_title': ticket.name,
            'ticket': self._ticket_detail_payload(ticket),
        })

    @http.route(
        '/my/customer-service/tickets/<int:ticket_id>/reply',
        type='json',
        auth='user',
        website=True,
        methods=['POST'],
    )
    def customer_ticket_reply(self, ticket_id, **kwargs):
        ticket = self._customer_ticket(ticket_id)
        if not ticket:
            return {'success': False, 'message': _('Tiket bantuan tidak ditemukan.')}
        body = (kwargs.get('body') or '').strip()
        if not body:
            return {'success': False, 'message': _('Balasan tidak boleh kosong.')}
        try:
            with request.env.cr.savepoint():
                if ticket.status == 'done':
                    ticket.sudo().write({
                        'status': 'pending',
                        'resolved_note': False,
                        'resolved_at': False,
                        'resolved_by_id': False,
                    })
                    ticket.sudo().action_add_thread_message(
                        _('User membuka kembali tiket karena ada balasan lanjutan.'),
                        author=request.env.user,
                        message_type='system',
                        notify_customer=False,
                    )
                ticket.sudo().action_add_thread_message(
                    body,
                    author=request.env.user,
                    message_type='customer',
                    notify_customer=False,
                )
        except Exception:
            request.env.clear()
            _logger.exception('Failed to add customer reply to ticket %s', ticket_id)
            return {'success': False, 'message': _('Balasan belum bisa dikirim. Coba lagi.')}
        return {
            'success': True,
            'message': _('Balasan terkirim.'),
            'ticket': self._ticket_detail_payload(ticket.sudo()),
        }

    @http.route(
        '/my/customer-service/tickets/evidence/<int:evidence_id>',
        type='http',
        auth='user',
        website=True,
        sitemap=False,
    )
    def customer_ticket_evidence(self, evidence_id, **kwargs):
        evidence = request.env['unitrade.customer.ticket.evidence'].sudo().browse(evidence_id).exists()
        if not evidence or evidence.ticket_id.user_id.id != request.env.uid:
            return request.not_found()
        attachment = evidence.attachment_id.sudo()
        raw = base64.b64decode(attachment.datas or b'')
        filename = (attachment.name or 'bukti').replace('"', '')
        return request.make_response(
            raw,
            headers=[
                ('Content-Type', attachment.mimetype or 'application/octet-stream'),
                ('Content-Disposition', 'inline; filename="%s"' % filename),
            ],
        )

    def _category_payloads(self):
        return [
            {
                'key': key,
                'label': meta['label'],
                'description': meta['description'],
                'tone': meta['tone'],
            }
            for key, meta in self._CATEGORY_META.items()
        ]

    def _customer_partner_ids(self):
        partner = request.env.user.partner_id.commercial_partner_id
        partners = request.env['res.partner'].sudo().search([
            ('commercial_partner_id', '=', partner.id),
        ])
        return partners.ids or [request.env.user.partner_id.id]

    def _order_options(self, limit=30):
        orders = request.env['sale.order'].sudo().search(
            [('partner_id', 'in', self._customer_partner_ids())],
            order='date_order desc, id desc',
            limit=limit,
        )
        return [
            {
                'id': order.id,
                'name': order.name,
                'label': '%s - %s' % (
                    order.name,
                    self._format_datetime(order.date_order) if order.date_order else _('Tanpa tanggal'),
                ),
            }
            for order in orders
        ]

    def _find_customer_order(self, order_ref):
        reference = (order_ref or '').strip()
        if not reference:
            return False
        normalized = reference[1:] if reference.startswith('#') else reference
        candidates = []
        for value in (reference, normalized, '#%s' % normalized):
            if value and value not in candidates:
                candidates.append(value)

        SaleOrder = request.env['sale.order'].sudo()
        base_domain = [('partner_id', 'in', self._customer_partner_ids())]
        for value in candidates:
            order = SaleOrder.search(base_domain + [('name', '=ilike', value)], limit=1)
            if order:
                return order
            order = SaleOrder.search(base_domain + [('client_order_ref', '=ilike', value)], limit=1)
            if order:
                return order
        if normalized.isdigit():
            return SaleOrder.search(base_domain + [('id', '=', int(normalized))], limit=1)
        return False

    def _customer_tickets(self, limit=None):
        domain = [('user_id', '=', request.env.uid)]
        return request.env['unitrade.customer.ticket'].sudo().search(
            domain,
            order='create_date desc, id desc',
            limit=limit,
        )

    def _customer_ticket(self, ticket_id):
        return request.env['unitrade.customer.ticket'].sudo().search([
            ('id', '=', ticket_id),
            ('user_id', '=', request.env.uid),
        ], limit=1)

    def _ticket_payload(self, ticket, include_description=False):
        status = self._STATUS_META.get(ticket.status, self._STATUS_META['pending'])
        category = self._CATEGORY_META.get(ticket.category, {})
        description = ticket.description or ''
        payload = {
            'id': ticket.id,
            'name': ticket.name,
            'title': ticket.title,
            'summary': self._truncate(description, 78),
            'created_label': self._relative_time(ticket.create_date),
            'created_at': self._format_datetime(ticket.create_date),
            'status': ticket.status,
            'status_label': status['label'],
            'status_tone': status['tone'],
            'category_label': category.get('label') or ticket.category,
            'order_name': ticket.order_id.name if ticket.order_id else '',
            'detail_url': '/my/customer-service/tickets/%s' % ticket.id,
            'last_message_label': self._relative_time(ticket.last_message_at) if ticket.last_message_at else '',
        }
        if include_description:
            payload['description'] = description
        return payload

    def _ticket_detail_payload(self, ticket):
        payload = self._ticket_payload(ticket, include_description=True)
        refund_context = self._refund_context(ticket)
        payload.update({
            'evidence': [
                {
                    'id': evidence.id,
                    'name': evidence.name,
                    'mimetype': evidence.mimetype,
                    'is_video': evidence.mimetype == 'video/mp4',
                    'url': '/my/customer-service/tickets/evidence/%s' % evidence.id,
                }
                for evidence in ticket.evidence_ids.sudo()
            ],
            'messages': self._ticket_message_payloads(ticket),
            'reply_url': '/my/customer-service/tickets/%s/reply' % ticket.id,
            'resolved_note': ticket.resolved_note or '',
            'resolved_at': self._format_datetime(ticket.resolved_at) if ticket.resolved_at else '',
            'refund': refund_context,
        })
        return payload

    def _ticket_message_payloads(self, ticket):
        labels = {
            'customer': _('User'),
            'admin': _('Customer Service'),
            'system': _('Sistem'),
        }
        return [
            {
                'id': message.id,
                'body': message.body or '',
                'type': message.message_type,
                'type_label': labels.get(message.message_type, message.message_type),
                'author': message.author_id.name or labels.get(message.message_type, '-'),
                'created_at': self._format_datetime(message.create_date),
                'created_label': self._relative_time(message.create_date),
                'is_admin': message.message_type == 'admin',
                'is_system': message.message_type == 'system',
            }
            for message in ticket.message_ids.sudo()
        ]

    def _refund_context(self, ticket):
        if ticket.category != 'refund_return' or not ticket.order_id:
            return {}
        order = ticket.order_id.sudo()
        context = {
            'title': _('Alur refund resmi'),
            'message': _('Tiket ini terkait refund. Gunakan halaman refund resmi agar bukti, SLA, dan keputusan admin tercatat di alur pengembalian.'),
            'url': '',
            'label': '',
            'state_label': '',
            'is_blocked': False,
        }
        if 'unitrade.dispute' in request.env.registry:
            dispute = request.env['unitrade.dispute'].sudo().search(
                [('order_id', '=', order.id)],
                order='create_date desc, id desc',
                limit=1,
            )
            if dispute:
                context.update({
                    'url': '/unitrade/order/%s/refund/%s' % (order.id, dispute.id),
                    'label': _('Lihat status refund'),
                    'state_label': self._selection_label(dispute, 'state'),
                    'message': _('Pengajuan refund untuk pesanan ini sudah tercatat. Pantau status refund melalui halaman refund resmi.'),
                })
                return context
        blocker = False
        if hasattr(order, '_unitrade_refund_blocker'):
            try:
                blocker = order._unitrade_refund_blocker(partner=request.env.user.partner_id)
            except Exception:
                _logger.exception('Failed to evaluate refund blocker for order %s', order.name)
                blocker = _('Status refund belum bisa dicek saat ini.')
        if blocker:
            context.update({
                'is_blocked': True,
                'message': str(blocker),
            })
            return context
        context.update({
            'url': '/unitrade/order/%s/refund/new' % order.id,
            'label': _('Ajukan refund resmi'),
        })
        return context

    def _prepare_evidence_payload(self, file_payload):
        if not isinstance(file_payload, dict):
            raise ValidationError(_('Format bukti upload tidak valid.'))
        name = (file_payload.get('name') or 'bukti').strip()[:160]
        mimetype = (file_payload.get('mimetype') or '').strip().lower()
        data = file_payload.get('data') or ''
        if ',' in data:
            data = data.split(',', 1)[1]
        if mimetype not in self._ALLOWED_EVIDENCE_MIMETYPES:
            raise ValidationError(_('Format bukti harus JPG, PNG, atau MP4.'))
        try:
            raw = base64.b64decode(data, validate=True)
        except (binascii.Error, ValueError):
            raise ValidationError(_('File bukti gagal dibaca.'))
        if len(raw) > self._MAX_EVIDENCE_SIZE:
            raise ValidationError(_('Ukuran setiap bukti maksimal 5 MB.'))
        return {
            'name': name,
            'mimetype': mimetype,
            'datas': base64.b64encode(raw).decode('ascii'),
            'size': len(raw),
        }

    def _create_evidence_records(self, ticket, prepared_files):
        for file_payload in prepared_files:
            attachment = request.env['ir.attachment'].sudo().create({
                'name': file_payload['name'],
                'datas': file_payload['datas'],
                'res_model': 'unitrade.customer.ticket',
                'res_id': ticket.id,
                'mimetype': file_payload['mimetype'],
            })
            request.env['unitrade.customer.ticket.evidence'].sudo().create({
                'ticket_id': ticket.id,
                'attachment_id': attachment.id,
            })

    @staticmethod
    def _selection_label(record, field_name):
        if not record or field_name not in record._fields:
            return ''
        value = record[field_name]
        return dict(record._fields[field_name].selection).get(value, value or '')

    @staticmethod
    def _truncate(value, limit):
        value = (value or '').strip()
        if len(value) <= limit:
            return value
        return value[:limit].rstrip() + '...'

    @staticmethod
    def _format_datetime(value):
        if not value:
            return ''
        local_dt = fields.Datetime.context_timestamp(
            request.env.user,
            fields.Datetime.to_datetime(value),
        )
        return local_dt.strftime('%d %b %Y, %H:%M')

    @staticmethod
    def _relative_time(value):
        if not value:
            return ''
        current = fields.Datetime.context_timestamp(
            request.env.user,
            fields.Datetime.to_datetime(fields.Datetime.now()),
        )
        local_value = fields.Datetime.context_timestamp(
            request.env.user,
            fields.Datetime.to_datetime(value),
        )
        delta = current - local_value
        seconds = max(int(delta.total_seconds()), 0)
        if seconds < 60:
            return _('Baru saja')
        minutes = seconds // 60
        if minutes < 60:
            return _('%s menit lalu') % minutes
        hours = minutes // 60
        if hours < 24:
            return _('%s jam lalu') % hours
        days = hours // 24
        if days == 1:
            return _('Kemarin')
        return _('%s hari lalu') % days
