import base64
import logging

from odoo import _, fields, http
from odoo.http import Stream, request
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.mimetypes import guess_mimetype

_logger = logging.getLogger(__name__)


class UnitradeChatController(http.Controller):
    _CHAT_ROLES = ('buyer', 'seller')

    def _json_error(self, message, code='error'):
        return {
            'success': False,
            'error': code,
            'message': message,
        }

<<<<<<< HEAD
    def _marketplace_block_message(self, feature_label=None):
        user = request.env.user
        if user._is_public() or not hasattr(user, '_check_unitrade_marketplace_access'):
            return ''
        try:
            user._check_unitrade_marketplace_access(feature_label or _('menggunakan chat'))
        except UserError as error:
            return error.args[0] if error.args else str(error)
        return ''

    def _marketplace_block_payload(self, feature_label=None):
        message = self._marketplace_block_message(feature_label)
        return self._json_error(message, code='account_blocked') if message else False

=======
>>>>>>> origin/main
    def _chat_role(self, role=None):
        return role if role in self._CHAT_ROLES else 'buyer'

    def _dashboard_seller(self):
        user = request.env.user
        return request.env['unitrade.seller'].sudo().search([
            ('user_id', '=', user.id),
            ('status', '=', 'verified'),
        ], limit=1)

    def _check_role_access(self, conversation, role='buyer'):
        role = self._chat_role(role)
        user = request.env.user
        if role == 'seller':
            seller = self._dashboard_seller()
            if not seller or conversation.seller_id.id != seller.id or conversation.seller_user_id.id != user.id:
                raise AccessError('Kamu tidak punya akses sebagai penjual untuk percakapan ini.')
        elif conversation.buyer_user_id.id != user.id:
            raise AccessError('Kamu tidak punya akses sebagai pembeli untuk percakapan ini.')
        return True

    def _conversation(self, conversation_id, role='buyer'):
<<<<<<< HEAD
        block_message = self._marketplace_block_message(_('menggunakan chat'))
        if block_message:
            raise UserError(block_message)
=======
>>>>>>> origin/main
        try:
            conversation_id = int(conversation_id or 0)
        except (TypeError, ValueError):
            conversation_id = 0
        conversation = request.env['unitrade.chat.conversation'].sudo().browse(conversation_id).exists()
        if not conversation:
            raise UserError('Percakapan tidak ditemukan.')
        conversation._check_participant(request.env.user)
        canonical = conversation._canonical_for_pair()
        canonical._check_participant(request.env.user)
        self._check_role_access(canonical, role=role)
        return canonical

    def _dedupe_conversations(self, conversations):
        seen = set()
        result = request.env['unitrade.chat.conversation'].sudo().browse()
        for conversation in conversations:
            key = (conversation.buyer_user_id.id, conversation.seller_id.id)
            if key in seen:
                continue
            seen.add(key)
            result |= conversation
        return result

    def _chat_avatar_url(self, user):
        if not user or not user.id:
            return '/web/static/img/user_menu_avatar.png'
        return '/unitrade/chat/avatar/%s?unique=%s' % (
            user.id,
            user.write_date or '',
        )

<<<<<<< HEAD
    def _chat_page_values(self, conversation_id=None, role='buyer', seller=False):
=======
    def _pending_order_count(self, seller):
        if not seller:
            return 0
        Product = request.env['product.template'].sudo()
        seller_product_ids = Product.search([
            ('x_seller_id', '=', seller.id),
            ('x_is_marketplace', '=', True),
        ]).mapped('product_variant_id').ids
        if not seller_product_ids:
            return 0
        return request.env['sale.order.line'].sudo().search_count([
            ('product_id', 'in', seller_product_ids),
            ('order_id.state', 'in', ['sale', 'sent']),
        ])

    def _chat_page_values(self, conversation_id=None, role='buyer', seller=None):
        role = self._chat_role(role)
>>>>>>> origin/main
        initial_id = 0
        try:
            initial_id = int(conversation_id or 0)
        except (TypeError, ValueError):
            initial_id = 0
<<<<<<< HEAD
        is_seller_view = role == 'seller' and bool(seller)
        return {
            'page_title': 'Chat Pembeli - UniTrade' if is_seller_view else 'Chat Penjual - UniTrade',
            'initial_conversation_id': initial_id,
            'is_seller_view': is_seller_view,
=======
        user = request.env.user
        unread_chat_count = request.env['unitrade.chat.conversation'].sudo().nav_unread_count(user, role=role)
        pending_order_count = self._pending_order_count(seller) if role == 'seller' else 0
        if seller:
            seller._ensure_profile_uuid()
        seller_public_ref = (seller.x_store_slug or seller.x_profile_uuid or seller.id) if seller else ''
        return {
            'page_title': 'Chat Pembeli - UniTrade' if role == 'seller' else 'Chat Penjual - UniTrade',
            'initial_conversation_id': initial_id,
            'chat_role': role,
            'chat_base_path': '/unitrade/seller/chat' if role == 'seller' else '/unitrade/chat',
            'seller_dashboard_chat': role == 'seller',
            'seller': seller,
            'seller_avatar_url': (
                '/web/image/res.users/%s/avatar_128?unique=%s' % (user.id, user.write_date or '')
                if seller else '/web/static/img/user_menu_avatar.png'
            ),
            'seller_profile_url': (
                '/seller-profile/%s' % seller_public_ref
                if seller else '/unitrade/seller/dashboard'
            ),
            'unread_chat_count': unread_chat_count,
            'pending_order_count': pending_order_count,
>>>>>>> origin/main
        }

    @http.route('/unitrade/chat', type='http', auth='user', website=True, sitemap=False)
    def chat_page(self, conversation_id=None, **kwargs):
<<<<<<< HEAD
        if self._marketplace_block_message(_('menggunakan chat')):
            return request.redirect('/my/profile?unitrade_blocked=1')
=======
>>>>>>> origin/main
        values = self._chat_page_values(
            conversation_id=conversation_id or kwargs.get('conversation_id'),
            role='buyer',
        )
        return request.render('unitrade_chat.chat_page_template', values)

    @http.route('/unitrade/seller/chat', type='http', auth='user', website=True, sitemap=False)
    def seller_chat_page(self, conversation_id=None, **kwargs):
<<<<<<< HEAD
        if self._marketplace_block_message(_('menggunakan chat seller')):
            return request.redirect('/my/profile?unitrade_blocked=1')
=======
>>>>>>> origin/main
        seller = self._dashboard_seller()
        if not seller:
            return request.redirect('/seller-onboarding')
        values = self._chat_page_values(
            conversation_id=conversation_id or kwargs.get('conversation_id'),
            role='seller',
            seller=seller,
        )
        return request.render('unitrade_chat.chat_page_template', values)

    @http.route('/unitrade/chat/open', type='json', auth='user', website=True, methods=['POST'])
    def open_chat(self, seller_id=None, profile_ref=None, product_id=None, **kwargs):
        try:
            block_payload = self._marketplace_block_payload(_('membuka chat'))
            if block_payload:
                return block_payload
            conversation = request.env['unitrade.chat.conversation'].open_for_seller(
                seller_id=seller_id,
                profile_ref=profile_ref,
                product_id=product_id,
            )
            return {
                'success': True,
                'conversation': conversation._conversation_payload(request.env.user, include_token=True),
            }
        except (AccessError, UserError, ValidationError) as error:
            return self._json_error(str(error))

    @http.route('/unitrade/chat/bootstrap', type='json', auth='user', website=True, methods=['POST'])
    def bootstrap(self, conversation_id=None, role='buyer', **kwargs):
<<<<<<< HEAD
        block_payload = self._marketplace_block_payload(_('menggunakan chat'))
        if block_payload:
            return block_payload
=======
>>>>>>> origin/main
        role = self._chat_role(role)
        user = request.env.user
        user.sudo().write({'x_unitrade_chat_last_seen': fields.Datetime.now()})
        Conversation = request.env['unitrade.chat.conversation'].sudo()
        conversations = Conversation.search(
            Conversation._role_domain(user, role=role) + [('active', '=', True)],
            order='last_message_date desc, create_date desc',
            limit=80,
        )
        conversations = self._dedupe_conversations(conversations)
        active = Conversation.browse()
        if conversation_id:
            try:
                active = self._conversation(conversation_id, role=role)
            except (AccessError, UserError):
                active = Conversation.browse()
        if not active and conversations:
            active = conversations[:1]
        if active and active not in conversations:
            conversations = active | conversations
        payload = {
            'success': True,
            'user_id': user.id,
            'current_user_avatar_url': self._chat_avatar_url(user),
            'user_channel': user._unitrade_chat_bus_target(),
            'role': role,
            'base_path': '/unitrade/seller/chat' if role == 'seller' else '/unitrade/chat',
            'is_seller_view': role == 'seller',
            'conversations': [
                conversation._conversation_payload(user, include_token=conversation == active)
                for conversation in conversations
            ],
            'active_conversation_id': active.id if active else False,
            'messages': [],
            'has_more_messages': False,
            'products': [],
        }
        if active:
            page = self._paged_message_payloads(active, limit=40)
            payload['messages'] = page['messages']
            payload['has_more_messages'] = page['has_more']
            payload['products'] = self._seller_product_payloads(active)
        return payload

    def _message_payloads(self, conversation, limit=80):
        messages = request.env['unitrade.chat.message'].sudo().search(
            [('conversation_id', '=', conversation.id)],
            order='create_date desc, id desc',
            limit=limit,
        )
        return [
            message._message_payload(request.env.user)
            for message in reversed(messages)
        ]

    def _paged_message_payloads(self, conversation, before_id=None, after_id=None, limit=40):
        Message = request.env['unitrade.chat.message'].sudo()
        domain = [('conversation_id', '=', conversation.id)]
        if before_id:
            domain.append(('id', '<', int(before_id)))
            messages = Message.search(domain, order='create_date desc, id desc', limit=limit + 1)
            has_more = len(messages) > limit
            messages = messages[:limit]
            return {
                'messages': [message._message_payload(request.env.user) for message in reversed(messages)],
                'has_more': has_more,
            }
        if after_id:
            domain.append(('id', '>', int(after_id)))
        messages = Message.search(domain, order='create_date asc, id asc', limit=limit + 1)
        has_more = len(messages) > limit
        return {
            'messages': [message._message_payload(request.env.user) for message in messages[:limit]],
            'has_more': has_more,
        }

    def _seller_product_payloads(self, conversation):
        products = request.env['product.template'].sudo().search([
            ('x_seller_id', '=', conversation.seller_id.id),
            ('x_is_marketplace', '=', True),
            ('sale_ok', '=', True),
            ('website_published', '=', True),
        ], order='create_date desc', limit=12)
        return [conversation._product_payload(product) for product in products]

    @http.route('/unitrade/chat/conversation', type='json', auth='user', website=True, methods=['POST'])
    def load_conversation(self, conversation_id=None, role='buyer', **kwargs):
        role = self._chat_role(role)
        try:
            conversation = self._conversation(conversation_id, role=role)
            request.env.user.sudo().write({'x_unitrade_chat_last_seen': fields.Datetime.now()})
            return {
                'success': True,
                'conversation': conversation._conversation_payload(request.env.user, include_token=True),
                **self._paged_message_payloads(conversation, limit=40),
                'products': self._seller_product_payloads(conversation),
            }
        except (AccessError, UserError, ValidationError) as error:
            return self._json_error(str(error))

    @http.route('/unitrade/chat/messages', type='json', auth='user', website=True, methods=['POST'])
    def list_messages(self, conversation_id=None, after_id=None, before_id=None, limit=40, role='buyer', **kwargs):
        role = self._chat_role(role)
        try:
            conversation = self._conversation(conversation_id, role=role)
            try:
                limit = max(10, min(int(limit or 40), 80))
            except (TypeError, ValueError):
                limit = 40
            page = self._paged_message_payloads(conversation, before_id=before_id, after_id=after_id, limit=limit)
            return {
                'success': True,
                'messages': page['messages'],
                'has_more': page['has_more'],
                'conversation': conversation._conversation_payload(request.env.user),
            }
        except (AccessError, UserError, ValidationError) as error:
            return self._json_error(str(error))

    @http.route('/unitrade/chat/send', type='json', auth='user', website=True, methods=['POST'])
    def send_message(self, conversation_id=None, message_type='text', body='', product_id=None,
                     image_data=None, filename=None, mimetype=None, role='buyer', **kwargs):
        role = self._chat_role(role)
        try:
            conversation = self._conversation(conversation_id, role=role)
            request.env['unitrade.chat.rate.limit'].check(request.env.user, 'send', 20)
            request.env.user.sudo().write({'x_unitrade_chat_last_seen': fields.Datetime.now()})
            message = request.env['unitrade.chat.message'].create_from_controller(conversation, {
                'message_type': message_type,
                'body': body,
                'product_id': product_id,
                'image_data': image_data,
                'filename': filename,
                'mimetype': mimetype,
            })
            return {
                'success': True,
                'message': message._message_payload(request.env.user),
                'conversation': conversation._conversation_payload(request.env.user),
            }
        except (AccessError, UserError, ValidationError) as error:
            return self._json_error(str(error))
        except Exception:
            _logger.exception('Failed to send UniTrade chat message')
            return self._json_error('Pesan gagal dikirim.', code='send_failed')

    @http.route('/unitrade/chat/cart/add', type='json', auth='user', website=True, methods=['POST'])
    def add_product_to_cart(self, conversation_id=None, product_id=None, checkout=False, role='buyer', **kwargs):
        role = self._chat_role(role)
        try:
            conversation = self._conversation(conversation_id, role=role)
            product = conversation._get_marketplace_product(product_id)
            if product.x_seller_id and product.x_seller_id.id != conversation.seller_id.id:
                raise UserError('Produk ini tidak termasuk percakapan dengan seller tersebut.')
            if not product.sale_ok or not product.website_published:
                raise UserError('Produk ini tidak tersedia untuk dibeli.')
            variant = product.product_variant_id
            if not variant:
                raise UserError('Varian produk tidak tersedia.')
            order = request.website.sale_get_order(force_create=True)
            order._cart_update(product_id=variant.id, add_qty=1)
            return {
                'success': True,
                'cart_quantity': order.cart_quantity,
                'cart_url': '/shop/cart',
                'checkout_url': '/shop/checkout' if checkout else '',
            }
        except (AccessError, UserError, ValidationError) as error:
            return self._json_error(str(error), code='cart_failed')
        except Exception:
            _logger.exception('Failed to add UniTrade chat product to cart')
            return self._json_error('Produk gagal ditambahkan ke keranjang.', code='cart_failed')

    @http.route('/unitrade/chat/report', type='json', auth='user', website=True, methods=['POST'])
    def report_user(self, conversation_id=None, reason=None, proof_image_data=None,
                    proof_filename=None, proof_mimetype=None, proof_images=None, role='buyer', **kwargs):
        role = self._chat_role(role)
        try:
            conversation = self._conversation(conversation_id, role=role)
            request.env['unitrade.chat.rate.limit'].check(request.env.user, 'report', 3)
            report = request.env['unitrade.chat.report'].create_from_controller(conversation, {
                'reason': reason,
                'proof_image_data': proof_image_data,
                'proof_filename': proof_filename,
                'proof_mimetype': proof_mimetype,
                'proof_images': proof_images,
            })
            return {
                'success': True,
                'report_id': report.id,
                'message': 'Laporan berhasil dikirim.',
            }
        except (AccessError, UserError, ValidationError) as error:
            return self._json_error(str(error), code='report_failed')
        except Exception:
            _logger.exception('Failed to submit UniTrade chat report')
            return self._json_error('Laporan gagal dikirim.', code='report_failed')

    @http.route('/unitrade/chat/read', type='json', auth='user', website=True, methods=['POST'])
    def mark_read(self, conversation_id=None, last_seen_message_id=None, active_conversation_id=None,
                  receiver_id=None, page_visible=False, window_focused=False, role='buyer', **kwargs):
        role = self._chat_role(role)
        try:
            conversation = self._conversation(conversation_id, role=role)
            try:
                active_conversation_id = int(active_conversation_id or 0)
                receiver_id = int(receiver_id or 0)
            except (TypeError, ValueError):
                active_conversation_id = 0
                receiver_id = 0
            if active_conversation_id != conversation.id or receiver_id != request.env.user.id:
                return self._json_error('Read receipt tidak valid.', code='invalid_read_receipt')
            if not page_visible or not window_focused:
                return {
                    'success': True,
                    'read': False,
                    'conversation': conversation._conversation_payload(request.env.user),
                }
            read = conversation.mark_read(request.env.user, last_seen_message_id=last_seen_message_id)
            return {
                'success': True,
                'read': bool(read),
                'conversation': conversation._conversation_payload(request.env.user),
            }
        except (AccessError, UserError, ValidationError) as error:
            return self._json_error(str(error))

    @http.route('/unitrade/chat/presence', type='json', auth='user', website=True, methods=['POST'])
    def presence(self, conversation_id=None, role='buyer', **kwargs):
<<<<<<< HEAD
        block_payload = self._marketplace_block_payload(_('menggunakan chat'))
        if block_payload:
            return block_payload
=======
>>>>>>> origin/main
        role = self._chat_role(role)
        user = request.env.user
        user.sudo().write({'x_unitrade_chat_last_seen': fields.Datetime.now()})
        payload = {
            'user_id': user.id,
            'last_seen': fields.Datetime.to_string(user.x_unitrade_chat_last_seen or fields.Datetime.now()),
        }
        if conversation_id:
            try:
                conversation = self._conversation(conversation_id, role=role)
                conversation._notify('unitrade_chat_presence', payload)
                return {
                    'success': True,
                    'conversation': conversation._conversation_payload(user),
                }
            except (AccessError, UserError, ValidationError):
                pass
        request.env['bus.bus'].sudo()._sendone(user._unitrade_chat_bus_target(), 'unitrade_chat_presence', payload)
        return {'success': True}

    @http.route('/unitrade/chat/typing', type='json', auth='user', website=True, methods=['POST'])
    def typing(self, conversation_id=None, typing=False, role='buyer', **kwargs):
        role = self._chat_role(role)
        try:
            conversation = self._conversation(conversation_id, role=role)
            request.env.user.sudo().write({'x_unitrade_chat_last_seen': fields.Datetime.now()})
            request.env['bus.bus'].sudo()._sendone(
                conversation._bus_target(),
                'unitrade_chat_typing',
                {
                    'conversation_id': conversation.id,
                    'user_id': request.env.user.id,
                    'typing': bool(typing),
                },
            )
            return {'success': True}
        except (AccessError, UserError, ValidationError) as error:
            return self._json_error(str(error))

    @http.route('/unitrade/chat/attachment/<int:attachment_id>', type='http', auth='user', website=True)
    def attachment(self, attachment_id, **kwargs):
        if self._marketplace_block_message(_('mengakses lampiran chat')):
            return request.not_found()
        attachment = request.env['ir.attachment'].sudo().browse(attachment_id).exists()
        if not attachment:
            return request.not_found()
        message = request.env['unitrade.chat.message'].sudo().search([('attachment_id', '=', attachment.id)], limit=1)
        if not message:
            return request.not_found()
        try:
            message.conversation_id._check_participant(request.env.user)
        except AccessError:
            return request.not_found()
        return Stream.from_attachment(attachment).get_response(as_attachment=False)

    @http.route('/unitrade/chat/avatar/<int:user_id>', type='http', auth='user', website=True)
    def avatar(self, user_id, **kwargs):
        if self._marketplace_block_message(_('mengakses chat')):
            return request.not_found()
        user = request.env['res.users'].sudo().browse(user_id).exists()
        if not user:
            return request.redirect('/web/static/img/user_menu_avatar.png')

        Conversation = request.env['unitrade.chat.conversation'].sudo()
        allowed = Conversation.search_count([
            ('active', '=', True),
            '|',
            '&', ('buyer_user_id', '=', request.env.user.id), ('seller_user_id', '=', user.id),
            '&', ('seller_user_id', '=', request.env.user.id), ('buyer_user_id', '=', user.id),
        ])
        if not allowed and user.id != request.env.user.id:
            return request.not_found()

        image = user.image_128 or user.partner_id.sudo().image_128
        if not image:
            return request.redirect('/web/static/img/user_menu_avatar.png')
        raw = base64.b64decode(image)
        headers = [
            ('Content-Type', guess_mimetype(raw, default='image/png')),
            ('Cache-Control', 'public, max-age=86400'),
        ]
        return request.make_response(raw, headers=headers)
