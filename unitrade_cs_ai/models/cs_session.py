import logging
import uuid

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)

CS_AI_RATE_ACTION = 'cs_ai'


class UnitradeCsSession(models.Model):
    _name = 'unitrade.cs.session'
    _description = 'UniTrade Customer Service Session'
    _order = 'last_activity desc, id desc'

    name = fields.Char(string='Referensi', compute='_compute_name', store=True)
    user_id = fields.Many2one(
        'res.users', string='Customer', required=True, index=True, ondelete='cascade',
        default=lambda self: self.env.user,
    )
    partner_id = fields.Many2one('res.partner', string='Kontak Customer', index=True)
    ticket_id = fields.Many2one(
        'unitrade.customer.ticket', string='Tiket', index=True, ondelete='set null', copy=False,
    )
    order_id = fields.Many2one('sale.order', string='Pesanan Terkait', index=True, ondelete='set null')
    state = fields.Selection([
        ('ai_active', 'AI Aktif'),
        ('waiting_admin', 'Menunggu Admin'),
        ('admin_handling', 'Ditangani Admin'),
        ('closed', 'Selesai'),
    ], string='Status', default='ai_active', required=True, index=True, copy=False)
    assigned_admin_id = fields.Many2one('res.users', string='Admin Penangan', index=True, copy=False)
    ai_enabled = fields.Boolean(string='AI Aktif', default=True)
    message_ids = fields.One2many('unitrade.cs.session.message', 'session_id', string='Pesan')
    last_activity = fields.Datetime(string='Aktivitas Terakhir', index=True, default=fields.Datetime.now)
    escalated_at = fields.Datetime(string='Waktu Eskalasi', copy=False)
    bus_token = fields.Char(
        string='Bus Token', copy=False, readonly=True,
        default=lambda self: str(uuid.uuid4()),
    )

    @api.depends('user_id.name', 'create_date')
    def _compute_name(self):
        for record in self:
            record.name = _('CS %s') % (record.user_id.name or _('Customer'))

    # ------------------------------------------------------------------
    # Access & helpers
    # ------------------------------------------------------------------
    def _is_admin(self, user=None):
        user = user or self.env.user
        return (
            user.has_group('unitrade_seller.group_unitrade_admin')
            or user.has_group('base.group_system')
        )

    def _check_participant(self, user=None):
        user = user or self.env.user
        for record in self:
            if record.user_id.id != user.id and not record._is_admin(user):
                raise AccessError(_('Kamu tidak punya akses ke percakapan ini.'))
        return True

    def _bus_target(self):
        self.ensure_one()
        if not self.bus_token:
            self.sudo().write({'bus_token': str(uuid.uuid4())})
        return 'unitrade_cs_session_%s' % self.bus_token

    @api.model
    def _admin_queue_target(self):
        return 'unitrade_cs_admin_queue'

    @api.model
    def _quick_replies(self):
        """Saran topik awal untuk floating chatbot (mirip quick-reply chips)."""
        return [
            'Bagaimana cara melakukan pembayaran?',
            'Bagaimana proses pengiriman GoSend?',
            'Bagaimana cara refund / pengembalian?',
            'Pesanan saya belum sampai, apa yang harus saya lakukan?',
        ]

    @api.model
    def get_or_create_active(self, user=None):
        user = (user or self.env.user)
        if user._is_public():
            raise AccessError(_('Login diperlukan untuk memakai Customer Service.'))
        session = self.sudo().search([
            ('user_id', '=', user.id),
            ('state', '!=', 'closed'),
        ], order='last_activity desc, id desc', limit=1)
        if session:
            return session
        ai_enabled = self.env['unitrade.cs.ai.service']._ai_enabled()
        session = self.sudo().create({
            'user_id': user.id,
            'partner_id': user.partner_id.id,
            'ai_enabled': ai_enabled,
            'state': 'ai_active' if ai_enabled else 'waiting_admin',
        })
        session._post_greeting()
        return session

    def _post_greeting(self):
        self.ensure_one()
        greeting = _(
            'Halo %s, saya asisten Customer Service UniTrade. Ada yang bisa saya bantu? '
            'Kamu juga bisa memilih "Chat dengan Admin" kapan saja.'
        ) % (self.user_id.name or _('Customer'))
        self.env['unitrade.cs.session.message'].sudo().create({
            'session_id': self.id,
            'author_type': 'ai' if self.state == 'ai_active' else 'admin',
            'body': greeting,
        })

    def _session_payload(self, user=None):
        self.ensure_one()
        user = user or self.env.user
        return {
            'id': self.id,
            'state': self.state,
            'state_label': dict(self._fields['state'].selection).get(self.state, self.state),
            'ai_enabled': self.ai_enabled,
            'bus_channel': self._bus_target(),
            'can_escalate': self.state in ('ai_active',),
            'is_admin_view': self._is_admin(user),
            'title': self.user_id.name if self._is_admin(user) else _('Customer Service UniTrade'),
        }

    # ------------------------------------------------------------------
    # Messaging & state transitions
    # ------------------------------------------------------------------
    def _create_message(self, author_type, body, author_user=None):
        self.ensure_one()
        return self.env['unitrade.cs.session.message'].sudo().create({
            'session_id': self.id,
            'author_type': author_type,
            'author_user_id': author_user.id if author_user else False,
            'body': body,
        })

    def post_user_message(self, body):
        self.ensure_one()
        self._check_participant()
        body = (body or '').strip()
        if not body:
            raise UserError(_('Pesan tidak boleh kosong.'))
        if self.state == 'closed':
            raise UserError(_('Sesi sudah ditutup. Mulai percakapan baru untuk melanjutkan.'))
        body = body[:2000]
        user_message = self._create_message('user', body, author_user=self.env.user)

        ai_message = False
        if self.state == 'ai_active' and self.ai_enabled:
            ai_message = self._maybe_generate_ai_reply(body)
        # state waiting_admin / admin_handling: simpan saja, tanpa AI
        return {
            'user_message': user_message,
            'ai_message': ai_message,
        }

    def _maybe_generate_ai_reply(self, user_message_body):
        self.ensure_one()
        service = self.env['unitrade.cs.ai.service']
        try:
            self.env['unitrade.chat.rate.limit'].check(
                self.env.user, CS_AI_RATE_ACTION, service._rate_limit(),
            )
        except UserError as error:
            return self._create_message('ai', error.args[0] if error.args else _(
                'Terlalu banyak permintaan. Coba lagi sebentar, atau pilih "Chat dengan Admin".'
            ))
        try:
            reply_text = service.generate_reply(self, user_message_body)
            if not reply_text:
                raise ValueError('empty AI reply')
            return self._create_message('ai', reply_text)
        except Exception:
            _logger.exception('CS AI reply failed for session %s', self.id)
            return self._create_message('ai', _(
                'Maaf, asisten AI sedang tidak tersedia saat ini. '
                'Silakan pilih "Chat dengan Admin" agar tim kami membantu kamu.'
            ))

    def escalate_to_admin(self):
        self.ensure_one()
        self._check_participant()
        if self.state == 'closed':
            raise UserError(_('Sesi sudah ditutup.'))
        if self.state in ('waiting_admin', 'admin_handling'):
            return self
        ticket = self._ensure_ticket()
        self.sudo().write({
            'state': 'waiting_admin',
            'ticket_id': ticket.id,
            'escalated_at': fields.Datetime.now(),
        })
        self._create_message('ai', _(
            'Kamu sedang dihubungkan dengan admin UniTrade. Mohon tunggu sebentar ya.'
        ))
        self._notify_admin_queue()
        return self

    def _ensure_ticket(self):
        self.ensure_one()
        if self.ticket_id:
            return self.ticket_id
        Ticket = self.env['unitrade.customer.ticket'].sudo()
        first_user_msg = self.message_ids.filtered(lambda m: m.author_type == 'user')[:1]
        title = (first_user_msg.body[:80] if first_user_msg else _('Permintaan bantuan Customer Service'))
        description = '\n'.join(
            '%s: %s' % (m.author_type.upper(), m.body)
            for m in self.message_ids.sorted('id')
        )[:5000] or _('Percakapan Customer Service via chat AI.')
        ticket = Ticket.create({
            'user_id': self.user_id.id,
            'partner_id': (self.partner_id or self.user_id.partner_id).id,
            'category': 'contact_cs',
            'title': title,
            'description': description,
            'cs_session_id': self.id,
            'ai_handled': True,
            'escalated_at': fields.Datetime.now(),
        })
        return ticket

    def admin_start_handling(self, admin=None):
        """Admin/CS mengambil alih sesi (tombol 'Di Proses').

        - state -> admin_handling
        - assign admin penangan
        - kirim notifikasi otomatis ke user bahwa CS sudah terhubung
        Idemponten: jika sudah admin_handling oleh admin yang sama, tidak
        mengirim notifikasi ganda.
        """
        self.ensure_one()
        admin = admin or self.env.user
        if not self._is_admin(admin):
            raise AccessError(_('Hanya admin yang dapat menangani sesi ini.'))
        if self.state == 'closed':
            raise UserError(_('Sesi sudah ditutup.'))

        already_handling = self.state == 'admin_handling' and self.assigned_admin_id.id == admin.id
        values = {'state': 'admin_handling'}
        if not self.assigned_admin_id:
            values['assigned_admin_id'] = admin.id
        # pastikan tiket terhubung agar arsip tetap konsisten
        if not self.ticket_id:
            ticket = self._ensure_ticket()
            values['ticket_id'] = ticket.id
            if not self.escalated_at:
                values['escalated_at'] = fields.Datetime.now()
        self.sudo().write(values)
        if self.ticket_id and self.ticket_id.status == 'pending':
            self.ticket_id.sudo().write({'status': 'in_progress'})

        if not already_handling:
            admin_name = admin.name or _('CS UniTrade')
            self._create_message('admin', _(
                'Anda sudah terhubung dengan CS, %s. Silakan lanjutkan percakapan Anda.'
            ) % admin_name, author_user=admin)
        return self

    def admin_reply(self, body, admin=None):
        self.ensure_one()
        admin = admin or self.env.user
        if not self._is_admin(admin):
            raise AccessError(_('Hanya admin yang dapat membalas dari dashboard.'))
        body = (body or '').strip()
        if not body:
            raise UserError(_('Balasan tidak boleh kosong.'))
        if self.state == 'closed':
            raise UserError(_('Sesi sudah ditutup.'))
        values = {'state': 'admin_handling'}
        if not self.assigned_admin_id:
            values['assigned_admin_id'] = admin.id
        self.sudo().write(values)
        return self._create_message('admin', body[:2000], author_user=admin)

    def close_session(self, admin=None):
        self.ensure_one()
        user = admin or self.env.user
        self._check_participant(user)
        if self.state == 'closed':
            return self
        self.sudo().write({'state': 'closed'})
        if self.ticket_id:
            self.ticket_id.sudo().write({
                'status': 'done',
                'resolved_at': fields.Datetime.now(),
                'resolved_by_id': user.id if self._is_admin(user) else False,
            })
        self._create_message('admin', _('Sesi Customer Service telah ditutup. Terima kasih.'),
                             author_user=user if self._is_admin(user) else None)
        return self

    def _notify_admin_queue(self):
        self.ensure_one()
        self.env['bus.bus'].sudo()._sendone(
            self._admin_queue_target(),
            'unitrade_cs_queue_update',
            {'session_id': self.id, 'user_name': self.user_id.name, 'state': self.state},
        )


class UnitradeCsSessionMessage(models.Model):
    _name = 'unitrade.cs.session.message'
    _description = 'UniTrade Customer Service Message'
    _order = 'create_date asc, id asc'

    session_id = fields.Many2one(
        'unitrade.cs.session', string='Sesi', required=True, index=True, ondelete='cascade',
    )
    author_type = fields.Selection([
        ('user', 'Customer'),
        ('ai', 'AI'),
        ('admin', 'Admin'),
    ], string='Tipe Pengirim', required=True, index=True)
    author_user_id = fields.Many2one('res.users', string='Pengirim', index=True)
    body = fields.Text(string='Pesan', required=True)
    is_ai = fields.Boolean(string='Pesan AI', default=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['is_ai'] = vals.get('author_type') == 'ai'
        messages = super().create(vals_list)
        now = fields.Datetime.now()
        for message in messages:
            message.session_id.sudo().write({'last_activity': now})
            message._notify_bus()
        return messages

    def _message_payload(self):
        self.ensure_one()
        author_label = {
            'user': self.author_user_id.name or _('Customer'),
            'ai': _('Asisten AI'),
            'admin': self.author_user_id.name or _('Admin UniTrade'),
        }.get(self.author_type, _('UniTrade'))
        return {
            'id': self.id,
            'session_id': self.session_id.id,
            'author_type': self.author_type,
            'author_name': author_label,
            'body': self.body or '',
            'is_ai': self.is_ai,
            'time': self.create_date.strftime('%H:%M') if self.create_date else '',
            'date': self.create_date.strftime('%d %B %Y') if self.create_date else '',
        }

    def _notify_bus(self):
        self.ensure_one()
        self.env['bus.bus'].sudo()._sendone(
            self.session_id._bus_target(),
            'unitrade_cs_message',
            {
                'session_id': self.session_id.id,
                'message': self._message_payload(),
                'state': self.session_id.state,
            },
        )
