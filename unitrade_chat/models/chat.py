import base64
import logging
import uuid
from datetime import datetime, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)
UNITRADE_CHAT_IMAGE_MAX_BYTES = 2 * 1024 * 1024
UNITRADE_CHAT_IMAGE_TYPES = {
    'image/jpeg',
    'image/png',
    'image/webp',
}
UNITRADE_CHAT_SEND_LIMIT = 20
UNITRADE_CHAT_REPORT_LIMIT = 3
UNITRADE_CHAT_RATE_WINDOW_SECONDS = 60
UNITRADE_CHAT_RETENTION_DAYS = 180
UNITRADE_CHAT_WIB = pytz.timezone('Asia/Jakarta')
UNITRADE_CHAT_MONTHS_ID = {
    1: 'Januari',
    2: 'Februari',
    3: 'Maret',
    4: 'April',
    5: 'Mei',
    6: 'Juni',
    7: 'Juli',
    8: 'Agustus',
    9: 'September',
    10: 'Oktober',
    11: 'November',
    12: 'Desember',
}


def _unitrade_chat_to_wib(value):
    if not value:
        return None
    dt_value = value if isinstance(value, datetime) else fields.Datetime.to_datetime(value)
    if not dt_value:
        return None
    if dt_value.tzinfo:
        return dt_value.astimezone(UNITRADE_CHAT_WIB)
    return pytz.UTC.localize(dt_value).astimezone(UNITRADE_CHAT_WIB)


def _unitrade_chat_format_wib_time(value):
    local_dt = _unitrade_chat_to_wib(value)
    return local_dt.strftime('%H:%M WIB') if local_dt else ''


def _unitrade_chat_format_wib_date(value, include_year=True):
    local_dt = _unitrade_chat_to_wib(value)
    if not local_dt:
        return ''
    month = UNITRADE_CHAT_MONTHS_ID.get(local_dt.month, local_dt.strftime('%B'))
    if include_year:
        return '%s %s %s' % (local_dt.day, month, local_dt.year)
    return '%s %s' % (local_dt.day, month)


def _unitrade_chat_last_message_label(value):
    local_dt = _unitrade_chat_to_wib(value)
    if not local_dt:
        return ''
    now_wib = _unitrade_chat_to_wib(fields.Datetime.now())
    if now_wib and local_dt.date() == now_wib.date():
        return _unitrade_chat_format_wib_time(local_dt)
    return _unitrade_chat_format_wib_date(local_dt, include_year=now_wib and local_dt.year != now_wib.year)


class UnitradeChatConversation(models.Model):
    _name = 'unitrade.chat.conversation'
    _description = 'UniTrade Chat Conversation'
    _order = 'last_message_date desc, create_date desc'

    name = fields.Char(string='Reference', compute='_compute_name', store=True)
    buyer_user_id = fields.Many2one(
        'res.users',
        string='Buyer',
        required=True,
        index=True,
        ondelete='cascade',
    )
    seller_id = fields.Many2one(
        'unitrade.seller',
        string='Seller',
        required=True,
        index=True,
        ondelete='cascade',
    )
    seller_user_id = fields.Many2one(
        'res.users',
        string='Seller User',
        related='seller_id.user_id',
        store=True,
        readonly=True,
    )
    product_id = fields.Many2one(
        'product.template',
        string='Product',
        index=True,
        ondelete='set null',
    )
    message_ids = fields.One2many(
        'unitrade.chat.message',
        'conversation_id',
        string='Messages',
    )
    last_message_id = fields.Many2one(
        'unitrade.chat.message',
        string='Last Message Record',
        readonly=True,
        ondelete='set null',
    )
    last_message_body = fields.Char(string='Last Message', readonly=True)
    last_message_date = fields.Datetime(string='Last Message Date', readonly=True, index=True)
    buyer_last_read_at = fields.Datetime(string='Buyer Last Read')
    seller_last_read_at = fields.Datetime(string='Seller Last Read')
    buyer_unread_count = fields.Integer(string='Buyer Unread', default=0, readonly=True)
    seller_unread_count = fields.Integer(string='Seller Unread', default=0, readonly=True)
    active = fields.Boolean(default=True)
    bus_token = fields.Char(
        string='Bus Token',
        copy=False,
        readonly=True,
        default=lambda self: str(uuid.uuid4()),
    )

    @api.depends('buyer_user_id.name', 'seller_id.name', 'product_id.name')
    def _compute_name(self):
        for record in self:
            parts = [record.buyer_user_id.name or _('Pembeli'), record.seller_id.name or _('Penjual')]
            if record.product_id:
                parts.append(record.product_id.name)
            record.name = ' - '.join(parts)

    @api.model
    def _participant_domain(self, user=None):
        user = user or self.env.user
        return ['|', ('buyer_user_id', '=', user.id), ('seller_user_id', '=', user.id)]

    @api.model
    def _role_domain(self, user=None, role='buyer'):
        user = user or self.env.user
        role = role if role in ('buyer', 'seller') else 'buyer'
        field_name = 'seller_user_id' if role == 'seller' else 'buyer_user_id'
        return [(field_name, '=', user.id)]

    @api.model
    def nav_unread_count(self, user=None, role='buyer'):
        user = (user or self.env.user).sudo()
        if not user or user._is_public():
            return 0
        role = role if role in ('buyer', 'seller') else 'buyer'
        conversations = self.sudo().search([('active', '=', True)] + self._role_domain(user, role=role))
        unread_count = 0
        for conversation in conversations:
            if role == 'buyer' and conversation.buyer_user_id.id == user.id:
                unread_count += conversation.buyer_unread_count
            elif role == 'seller' and conversation.seller_user_id.id == user.id:
                unread_count += conversation.seller_unread_count
        return unread_count

    @api.model
    def _get_verified_seller(self, seller_id=None, profile_ref=None):
        Seller = self.env['unitrade.seller'].sudo()
        seller = Seller.browse()
        if seller_id:
            try:
                seller = Seller.browse(int(seller_id)).exists()
            except (TypeError, ValueError):
                seller = Seller.browse()
        elif profile_ref:
            seller = Seller.search([('x_store_slug', '=', profile_ref)], limit=1)
            if not seller:
                seller = Seller.search([('x_profile_uuid', '=', profile_ref)], limit=1)
            if not seller and str(profile_ref).isdigit():
                seller = Seller.browse(int(profile_ref)).exists()
        if not seller or seller.status != 'verified':
            raise UserError(_('Seller tidak ditemukan atau belum terverifikasi.'))
        return seller

    @api.model
    def _get_marketplace_product(self, product_id):
        if not product_id:
            return self.env['product.template'].browse()
        try:
            product = self.env['product.template'].sudo().browse(int(product_id)).exists()
        except (TypeError, ValueError):
            product = self.env['product.template'].browse()
        if not product:
            raise UserError(_('Produk tidak ditemukan.'))
        if (
            'x_is_marketplace' in product._fields
            and not product.x_is_marketplace
        ):
            raise UserError(_('Produk ini tidak tersedia di marketplace UniTrade.'))
        return product

    @api.model_create_multi
    def create(self, vals_list):
        conversations = self.browse()
        for vals in vals_list:
            buyer_id = vals.get('buyer_user_id')
            seller_id = vals.get('seller_id')
            existing = self.browse()
            if buyer_id and seller_id:
                existing = self.sudo().search([
                    ('buyer_user_id', '=', buyer_id),
                    ('seller_id', '=', seller_id),
                    ('active', '=', True),
                ], order='last_message_date desc, create_date desc, id desc', limit=1)
            if existing:
                product_id = vals.get('product_id')
                if product_id and not existing.product_id:
                    existing.sudo().write({'product_id': product_id})
                conversations |= existing
                continue
            conversations |= super(UnitradeChatConversation, self).create([vals])
        return conversations

    @api.model
    def open_for_seller(self, seller=None, seller_id=None, profile_ref=None, product_id=None):
        user = self.env.user
        if user._is_public():
            raise AccessError(_('Login diperlukan untuk membuka chat.'))

        seller = seller or self._get_verified_seller(seller_id=seller_id, profile_ref=profile_ref)
        if seller.user_id.id == user.id:
            raise UserError(_('Kamu tidak bisa membuka chat dengan toko sendiri.'))
        product = self._get_marketplace_product(product_id)
        if product and product.x_seller_id and product.x_seller_id.id != seller.id:
            raise UserError(_('Produk ini tidak dimiliki oleh seller yang dipilih.'))

        domain = [
            ('buyer_user_id', '=', user.id),
            ('seller_id', '=', seller.id),
            ('active', '=', True),
        ]
        conversation = self.sudo().search(domain, order='last_message_date desc, create_date desc, id desc', limit=1)
        if conversation:
            if product and not conversation.product_id:
                conversation.sudo().write({'product_id': product.id})
            return conversation
        if 'x_chat_enabled' in seller._fields and not seller.x_chat_enabled:
            raise UserError(_('Toko ini sedang tidak menerima chat baru.'))

        conversation = self.sudo().create({
            'buyer_user_id': user.id,
            'seller_id': seller.id,
            'product_id': product.id or False,
        })
        body = _('Selamat datang %s, silahkan tinggalkan chat untuk menanyakan barang. Pesan ini terkirim otomatis.') % user.name
        self.env['unitrade.chat.message'].sudo().create({
            'conversation_id': conversation.id,
            'author_user_id': seller.user_id.id,
            'message_type': 'system',
            'body': body,
        })
        _logger.info('UniTrade chat conversation %s opened by user %s for seller %s', conversation.id, user.id, seller.id)
        return conversation

    def _canonical_for_pair(self):
        self.ensure_one()
        return self.sudo().search([
            ('buyer_user_id', '=', self.buyer_user_id.id),
            ('seller_id', '=', self.seller_id.id),
            ('active', '=', True),
        ], order='last_message_date desc, create_date desc, id desc', limit=1) or self

    def _check_participant(self, user=None):
        user = user or self.env.user
        for record in self:
            if user.id not in (record.buyer_user_id.id, record.seller_user_id.id):
                raise AccessError(_('Kamu tidak punya akses ke percakapan ini.'))
        return True

    def _bus_target(self):
        self.ensure_one()
        if not self.bus_token:
            self.sudo().write({'bus_token': str(uuid.uuid4())})
        return 'unitrade_chat_conversation_%s' % self.bus_token

    def _notification_targets(self):
        self.ensure_one()
        return {
            self.buyer_user_id.sudo()._unitrade_chat_bus_target(),
            self.seller_user_id.sudo()._unitrade_chat_bus_target(),
        }

    def _other_user(self, user=None):
        self.ensure_one()
        user = user or self.env.user
        return self.seller_user_id if user.id == self.buyer_user_id.id else self.buyer_user_id

    def _is_other_online(self, user=None):
        other = self._other_user(user=user).sudo()
        return bool(other._unitrade_chat_is_online())

    def _avatar_url(self, user):
        if not user or not user.id:
            return '/web/static/img/user_menu_avatar.png'
        return '/unitrade/chat/avatar/%s?unique=%s' % (
            user.id,
            user.write_date or '',
        )

    def _product_payload(self, product):
        if not product:
            return False
        currency = self.env.company.currency_id
        variant = product.product_variant_id
        return {
            'id': product.id,
            'variant_id': variant.id if variant else False,
            'name': product.name,
            'price': product.list_price,
            'price_label': '%s %s' % (currency.symbol or 'Rp', ('{:,.0f}'.format(product.list_price or 0.0)).replace(',', '.')),
            'url': product.website_url or '/unitrade/product/%s' % product.id,
            'image_url': '/web/image/product.template/%s/image_256' % product.id,
            'cart_url': '/shop/cart/update?product_id=%s&add_qty=1' % (variant.id if variant else 0),
            'checkout_url': '/shop/checkout',
            'seller_name': product.x_seller_id.name if 'x_seller_id' in product._fields and product.x_seller_id else '',
        }

    def _conversation_payload(self, user=None, include_token=False):
        self.ensure_one()
        user = user or self.env.user
        self._check_participant(user)
        is_buyer = user.id == self.buyer_user_id.id
        counterpart = self.seller_user_id if is_buyer else self.buyer_user_id
        last_message_date = self.last_message_date or self.create_date
        payload = {
            'id': self.id,
            'chat_key': '%s:%s' % (self.buyer_user_id.id, self.seller_id.id),
            'buyer_user_id': self.buyer_user_id.id,
            'seller_id': self.seller_id.id,
            'seller_user_id': self.seller_user_id.id,
            'title': self.seller_id.name if is_buyer else self.buyer_user_id.name,
            'subtitle': self.product_id.name if self.product_id else 'Chat UniTrade',
            'avatar_url': self._avatar_url(counterpart),
            'buyer_avatar_url': self._avatar_url(self.buyer_user_id),
            'seller_avatar_url': self._avatar_url(self.seller_user_id),
            'counterpart_user_id': counterpart.id,
            'online': self._is_other_online(user),
            'last_seen_label': 'Online' if self._is_other_online(user) else 'Offline',
            'last_message': self.last_message_body or '',
            'last_message_date': fields.Datetime.to_string(last_message_date) if last_message_date else '',
            'last_message_label': _unitrade_chat_last_message_label(last_message_date),
            'unread_count': self.buyer_unread_count if is_buyer else self.seller_unread_count,
            'product': self._product_payload(self.product_id),
            'is_seller_view': not is_buyer,
        }
        if include_token:
            payload.update({
                'conversation_channel': self._bus_target(),
                'bus_channel': self._bus_target(),
                'user_channel': user._unitrade_chat_bus_target(),
            })
        return payload

    def _notify(self, notification_type, payload):
        Bus = self.env['bus.bus'].sudo()
        for conversation in self:
            targets = {conversation._bus_target()} | conversation._notification_targets()
            for target in targets:
                Bus._sendone(target, notification_type, payload)

    def _notify_message(self, message):
        self.ensure_one()
        Bus = self.env['bus.bus'].sudo()
        conversation_payloads = {}
        for participant in (self.buyer_user_id, self.seller_user_id):
            conversation_payloads[participant.id] = {
                'conversation': self._conversation_payload(participant),
                'message': message._message_payload(participant),
            }
            Bus._sendone(
                participant.sudo()._unitrade_chat_bus_target(),
                'unitrade_chat_notification',
                conversation_payloads[participant.id],
            )
        Bus._sendone(
            self._bus_target(),
            'unitrade_chat_message',
            {
                'conversation_id': self.id,
                'message_id': message.id,
                'messages_by_user': conversation_payloads,
            },
        )

    def mark_read(self, user=None, last_seen_message_id=None):
        user = user or self.env.user
        now = fields.Datetime.now()
        for conversation in self:
            conversation._check_participant(user)
            try:
                last_seen_message_id = int(last_seen_message_id or 0)
            except (TypeError, ValueError):
                last_seen_message_id = 0
            if not last_seen_message_id:
                return False

            readable_messages = conversation.message_ids.sudo().filtered(
                lambda message: (
                    message.id <= last_seen_message_id
                    and message.author_user_id.id != user.id
                    and not message.read_at
                )
            )
            if not readable_messages:
                return False

            readable_messages.write({'read_at': now})
            remaining_unread = self.env['unitrade.chat.message'].sudo().search_count([
                ('conversation_id', '=', conversation.id),
                ('author_user_id', '!=', user.id),
                ('read_at', '=', False),
                ('message_type', '!=', 'system'),
            ])
            vals = {}
            if user.id == conversation.buyer_user_id.id:
                vals.update({'buyer_last_read_at': now, 'buyer_unread_count': remaining_unread})
            else:
                vals.update({'seller_last_read_at': now, 'seller_unread_count': remaining_unread})
            conversation.sudo().write(vals)
            conversation._notify('unitrade_chat_read', {
                'conversation_id': conversation.id,
                'reader_user_id': user.id,
                'receiver_id': user.id,
                'last_seen_message_id': last_seen_message_id,
                'read_message_ids': readable_messages.ids,
                'read_at': fields.Datetime.to_string(now),
            })
        return True


class UnitradeChatMessage(models.Model):
    _name = 'unitrade.chat.message'
    _description = 'UniTrade Chat Message'
    _order = 'create_date asc, id asc'

    conversation_id = fields.Many2one(
        'unitrade.chat.conversation',
        string='Conversation',
        required=True,
        index=True,
        ondelete='cascade',
    )
    author_user_id = fields.Many2one(
        'res.users',
        string='Author',
        required=True,
        index=True,
        default=lambda self: self.env.user,
        ondelete='cascade',
    )
    message_type = fields.Selection([
        ('text', 'Text'),
        ('image', 'Image'),
        ('product', 'Product'),
        ('system', 'System'),
    ], default='text', required=True, index=True)
    body = fields.Text(string='Message')
    product_id = fields.Many2one('product.template', string='Product', ondelete='set null')
    attachment_id = fields.Many2one('ir.attachment', string='Attachment', ondelete='set null')
    delivered_at = fields.Datetime(string='Delivered At', readonly=True)
    read_at = fields.Datetime(string='Read At')

    @api.model_create_multi
    def create(self, vals_list):
        now = fields.Datetime.now()
        for vals in vals_list:
            vals.setdefault('delivered_at', now)
        messages = super().create(vals_list)
        for message in messages:
            message.conversation_id.sudo().write(message._conversation_update_vals())
            message.conversation_id._notify_message(message)
        return messages

    def _conversation_update_vals(self):
        self.ensure_one()
        body = self._preview_text()
        vals = {
            'last_message_id': self.id,
            'last_message_body': body,
            'last_message_date': self.create_date or fields.Datetime.now(),
        }
        if self.author_user_id.id == self.conversation_id.buyer_user_id.id:
            vals['seller_unread_count'] = self.conversation_id.seller_unread_count + 1
        elif self.message_type != 'system':
            vals['buyer_unread_count'] = self.conversation_id.buyer_unread_count + 1
        return vals

    def _preview_text(self):
        self.ensure_one()
        if self.message_type == 'image':
            return _('Gambar')
        if self.message_type == 'product':
            return _('Produk: %s') % (self.product_id.name if self.product_id else _('Produk'))
        return (self.body or '').strip()[:120]

    def _message_payload(self, user=None):
        self.ensure_one()
        user = user or self.env.user
        conversation = self.conversation_id
        is_mine = self.author_user_id.id == user.id
        delivery_state = 'read' if self.read_at else 'delivered' if self.delivered_at else 'sent'
        return {
            'id': self.id,
            'conversation_id': conversation.id,
            'author_user_id': self.author_user_id.id,
            'author_name': self.author_user_id.name,
            'author_avatar_url': conversation._avatar_url(self.author_user_id),
            'is_mine': is_mine,
            'type': self.message_type,
            'body': self.body or '',
            'time': _unitrade_chat_format_wib_time(self.create_date),
            'date': _unitrade_chat_format_wib_date(self.create_date),
            'delivered': bool(self.delivered_at),
            'delivered_at': fields.Datetime.to_string(self.delivered_at) if self.delivered_at else '',
            'read': bool(self.read_at),
            'read_at': fields.Datetime.to_string(self.read_at) if self.read_at else '',
            'delivery_state': delivery_state,
            'image_url': '/unitrade/chat/attachment/%s' % self.attachment_id.id if self.attachment_id else '',
            'product': conversation._product_payload(self.product_id),
        }

    @api.model
    def create_from_controller(self, conversation, values):
        conversation._check_participant(self.env.user)
        if self.env.user.sudo().x_unitrade_chat_blocked:
            raise AccessError(_('Akun kamu sedang dibatasi untuk mengirim chat.'))
        message_type = values.get('message_type') or 'text'
        body = (values.get('body') or '').strip()
        product = self.env['product.template'].browse()
        attachment = self.env['ir.attachment'].browse()

        if message_type == 'text':
            if not body:
                raise UserError(_('Pesan tidak boleh kosong.'))
            body = body[:2000]
        elif message_type == 'product':
            product = conversation._get_marketplace_product(values.get('product_id'))
            if product.x_seller_id and product.x_seller_id.id != conversation.seller_id.id:
                raise UserError(_('Produk ini tidak termasuk percakapan dengan seller tersebut.'))
            body = body or product.name
        elif message_type == 'image':
            attachment = self._create_chat_attachment(conversation, values)
            body = body[:500]
        else:
            raise UserError(_('Tipe pesan tidak didukung.'))

        return self.sudo().create({
            'conversation_id': conversation.id,
            'author_user_id': self.env.user.id,
            'message_type': message_type,
            'body': body,
            'product_id': product.id or False,
            'attachment_id': attachment.id or False,
        })

    def _create_chat_attachment(self, conversation, values):
        data_url = values.get('image_data') or ''
        filename = (values.get('filename') or 'chat-image').strip()[:120]
        mimetype = values.get('mimetype') or ''
        if ',' in data_url:
            header, encoded = data_url.split(',', 1)
            if not mimetype and ';' in header:
                mimetype = header.split(';', 1)[0].replace('data:', '')
        else:
            encoded = data_url
        if mimetype not in UNITRADE_CHAT_IMAGE_TYPES:
            raise ValidationError(_('Format gambar harus JPG, PNG, atau WebP.'))
        try:
            raw = base64.b64decode(encoded)
        except Exception as error:
            raise ValidationError(_('Gambar gagal dibaca.')) from error
        if not raw:
            raise ValidationError(_('Gambar tidak boleh kosong.'))
        if len(raw) > UNITRADE_CHAT_IMAGE_MAX_BYTES:
            raise ValidationError(_('Ukuran gambar maksimal 2 MB.'))
        attachment = self.env['ir.attachment'].sudo().create({
            'name': filename,
            'datas': base64.b64encode(raw),
            'mimetype': mimetype,
            'res_model': 'unitrade.chat.conversation',
            'res_id': conversation.id,
            'type': 'binary',
            'public': False,
        })
        return attachment


class UnitradeChatReport(models.Model):
    _name = 'unitrade.chat.report'
    _description = 'UniTrade Chat User Report'
    _order = 'create_date desc, id desc'

    conversation_id = fields.Many2one(
        'unitrade.chat.conversation',
        string='Conversation',
        required=True,
        index=True,
        ondelete='cascade',
    )
    reporter_user_id = fields.Many2one(
        'res.users',
        string='Reporter',
        required=True,
        index=True,
        ondelete='cascade',
    )
    reported_user_id = fields.Many2one(
        'res.users',
        string='Reported User',
        required=True,
        index=True,
        ondelete='cascade',
    )
    reason = fields.Selection([
        ('spam', 'Spam'),
        ('harmful_content', 'Konten mengandung SARA, diskriminasi, vulgar, ancaman, dan pelanggaran nilai / norma sosial'),
        ('abuse', 'Abuse or Harassment'),
        ('fraud', 'Fraud or Suspicious Activity'),
        ('other', 'Other'),
    ], string='Reason Category', default='other', required=True)
    reason_detail = fields.Text(string='Reason Detail', required=True)
    proof_attachment_id = fields.Many2one('ir.attachment', string='Proof Photo', ondelete='set null')
    proof_attachment_ids = fields.Many2many(
        'ir.attachment',
        'unitrade_chat_report_ir_attachment_rel',
        'report_id',
        'attachment_id',
        string='Proof Photos',
    )
    state = fields.Selection([
        ('submitted', 'Submitted'),
        ('under_review', 'Under Review'),
        ('reviewed', 'Reviewed'),
        ('rejected', 'Rejected'),
        ('blocked', 'Blocked'),
    ], string='Status', default='submitted', required=True)
    reviewer_user_id = fields.Many2one('res.users', string='Reviewer', readonly=True, ondelete='set null')
    reviewed_at = fields.Datetime(string='Reviewed At', readonly=True)
    admin_note = fields.Text(string='Admin Note')

    @api.model
    def create_from_controller(self, conversation, values):
        conversation._check_participant(self.env.user)
        if self.env.user.sudo().x_unitrade_chat_blocked:
            raise AccessError(_('Akun kamu sedang dibatasi untuk membuat laporan chat.'))
        reason_detail = (values.get('reason') or '').strip()
        if not reason_detail:
            raise ValidationError(_('Alasan laporan wajib diisi.'))
        reason_detail = reason_detail[:1000]
        reason_category = reason_detail if reason_detail in dict(self._fields['reason'].selection) else 'other'

        reported_user = conversation._other_user(self.env.user)
        report = self.sudo().create({
            'conversation_id': conversation.id,
            'reporter_user_id': self.env.user.id,
            'reported_user_id': reported_user.id,
            'reason': reason_category,
            'reason_detail': reason_detail,
        })
        attachments = self._create_proof_attachments(report, values)
        if attachments:
            report.sudo().write({
                'proof_attachment_id': attachments[:1].id,
                'proof_attachment_ids': [(6, 0, attachments.ids)],
            })
        _logger.info(
            'UniTrade chat report %s submitted by user %s against user %s',
            report.id,
            self.env.user.id,
            reported_user.id,
        )
        return report

    def _proof_values(self, values):
        proof_images = values.get('proof_images')
        if proof_images is None and values.get('proof_image_data'):
            proof_images = [{
                'data': values.get('proof_image_data'),
                'filename': values.get('proof_filename'),
                'mimetype': values.get('proof_mimetype'),
            }]
        proof_images = proof_images or []
        if len(proof_images) > 3:
            raise ValidationError(_('Maksimal upload 3 gambar bukti laporan.'))
        return proof_images

    def _create_proof_attachments(self, report, values):
        attachments = self.env['ir.attachment'].sudo().browse()
        for index, proof in enumerate(self._proof_values(values), start=1):
            attachments |= self._create_proof_attachment(report, proof, index=index)
        return attachments

    def _create_proof_attachment(self, report, values, index=1):
        data_url = values.get('data') or values.get('proof_image_data') or ''
        filename = (values.get('filename') or values.get('proof_filename') or 'chat-report-proof-%s' % index).strip()[:120]
        mimetype = values.get('mimetype') or values.get('proof_mimetype') or ''
        if ',' in data_url:
            header, encoded = data_url.split(',', 1)
            if not mimetype and ';' in header:
                mimetype = header.split(';', 1)[0].replace('data:', '')
        else:
            encoded = data_url
        if mimetype not in UNITRADE_CHAT_IMAGE_TYPES:
            raise ValidationError(_('Bukti foto harus berupa JPG, PNG, atau WebP.'))
        try:
            raw = base64.b64decode(encoded)
        except Exception as error:
            raise ValidationError(_('Bukti foto gagal dibaca.')) from error
        if not raw:
            raise ValidationError(_('Bukti foto tidak boleh kosong.'))
        if len(raw) > UNITRADE_CHAT_IMAGE_MAX_BYTES:
            raise ValidationError(_('Ukuran bukti foto maksimal 2 MB.'))
        return self.env['ir.attachment'].sudo().create({
            'name': filename,
            'datas': base64.b64encode(raw),
            'mimetype': mimetype,
            'res_model': 'unitrade.chat.report',
            'res_id': report.id,
            'type': 'binary',
            'public': False,
        })

    def _review_vals(self, state):
        return {
            'state': state,
            'reviewer_user_id': self.env.user.id,
            'reviewed_at': fields.Datetime.now(),
        }

    def action_start_review(self):
        self.write(self._review_vals('under_review'))

    def action_mark_reviewed(self):
        self.write(self._review_vals('reviewed'))

    def action_reject(self):
        self.write(self._review_vals('rejected'))

    def action_block_reported_user(self):
        for report in self:
            report.reported_user_id.sudo().write({
                'x_unitrade_chat_blocked': True,
                'x_unitrade_chat_block_reason': (report.reason_detail or report.reason or '')[:120],
            })
        self.write(self._review_vals('blocked'))

    def action_unblock_reported_user(self):
        for report in self:
            report.reported_user_id.sudo().write({
                'x_unitrade_chat_blocked': False,
                'x_unitrade_chat_block_reason': False,
            })


class UnitradeChatRateLimit(models.Model):
    _name = 'unitrade.chat.rate.limit'
    _description = 'UniTrade Chat Rate Limit'
    _rec_name = 'key'
    _order = 'window_start desc, id desc'

    key = fields.Char(required=True, index=True)
    user_id = fields.Many2one('res.users', string='User', required=True, index=True, ondelete='cascade')
    action = fields.Selection([
        ('send', 'Send Message'),
        ('report', 'Submit Report'),
    ], required=True, index=True)
    window_start = fields.Datetime(required=True, default=fields.Datetime.now)
    request_count = fields.Integer(default=0, required=True)

    @api.model
    def check(self, user, action, limit, window_seconds=UNITRADE_CHAT_RATE_WINDOW_SECONDS):
        user = user.sudo()
        if user.has_group('base.group_system') or user.has_group('unitrade_seller.group_unitrade_admin'):
            return True
        now = fields.Datetime.now()
        key = '%s:%s' % (user.id, action)
        window_delta = timedelta(seconds=window_seconds)
        record = self.sudo().search([('key', '=', key)], limit=1)
        if not record or not record.window_start or now - record.window_start >= window_delta:
            if record:
                record.write({'window_start': now, 'request_count': 1})
            else:
                self.sudo().create({
                    'key': key,
                    'user_id': user.id,
                    'action': action,
                    'window_start': now,
                    'request_count': 1,
                })
            return True
        if record.request_count >= limit:
            raise UserError(_('Terlalu banyak aktivitas chat. Coba lagi sebentar.'))
        record.write({'request_count': record.request_count + 1})
        return True

    @api.model
    def _cron_cleanup(self):
        cutoff = fields.Datetime.now() - timedelta(days=int(
            self.env['ir.config_parameter'].sudo().get_param(
                'unitrade_chat.attachment_retention_days',
                UNITRADE_CHAT_RETENTION_DAYS,
            )
        ))
        Message = self.env['unitrade.chat.message'].sudo()
        messages = Message.search([
            ('message_type', '=', 'image'),
            ('attachment_id', '!=', False),
            ('create_date', '<', cutoff),
        ], limit=500)
        attachments = messages.mapped('attachment_id')
        messages.write({'attachment_id': False})
        if attachments:
            attachments.unlink()
        stale_limits = self.sudo().search([('window_start', '<', fields.Datetime.now() - timedelta(days=2))], limit=2000)
        stale_limits.unlink()
        _logger.info('UniTrade chat cleanup removed %s attachments and %s stale rate rows', len(attachments), len(stale_limits))
