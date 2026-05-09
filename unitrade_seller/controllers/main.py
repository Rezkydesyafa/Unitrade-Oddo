from collections import defaultdict
from datetime import timedelta
import json
import math
import logging

# pyrefly: ignore [missing-import]
from odoo import fields, http
# pyrefly: ignore [missing-import]
from odoo.http import request
from markupsafe import Markup, escape
from werkzeug.urls import url_encode

_logger = logging.getLogger(__name__)


def _safe_get(record, field_name, default=False):
    """Safely read optional custom fields that may come from another addon."""
    try:
        return record[field_name] if field_name in record._fields else default
    except Exception:
        return default


class UnitradeSellerController(http.Controller):
    _PROFILE_TABS = ('home', 'latest', 'sold', 'reviews')

    @staticmethod
    def _seller_public_ref(seller):
        seller._ensure_profile_uuid()
        return seller.x_profile_uuid

    @staticmethod
    def _get_seller_by_public_ref(profile_ref=None, seller_id=None):
        Seller = request.env['unitrade.seller'].sudo()
        seller = Seller.browse()
        found_by_uuid = False
        if seller_id:
            seller = Seller.browse(seller_id).exists()
        elif profile_ref:
            seller = Seller.search([('x_profile_uuid', '=', profile_ref)], limit=1)
            found_by_uuid = bool(seller)
            if not seller and profile_ref.isdigit():
                seller = Seller.browse(int(profile_ref)).exists()

        if seller and (found_by_uuid or UnitradeSellerController._can_view_seller_profile(seller)):
            seller._ensure_profile_uuid()
            return seller
        return Seller.browse()

    @staticmethod
    def _can_view_seller_profile(seller):
        if seller.status == 'verified':
            return True

        user = request.env.user
        if user._is_public():
            return False

        if seller.user_id.id == user.id:
            return True

        return (
            user.has_group('base.group_system')
            or user.has_group('unitrade_seller.group_unitrade_admin')
        )

    @staticmethod
    def _seller_products(seller, search=None, tab='home', limit=15):
        Product = request.env['product.template'].sudo()
        domain = [
            ('x_seller_id', '=', seller.id),
            ('x_is_marketplace', '=', True),
            ('sale_ok', '=', True),
            ('website_published', '=', True),
        ]
        if search:
            domain += ['|', ('name', 'ilike', search), ('description_sale', 'ilike', search)]

        if tab == 'latest':
            order = 'create_date desc'
        elif tab == 'sold' and 'sales_count' in Product._fields:
            order = 'sales_count desc, create_date desc'
        else:
            order = 'website_sequence asc, create_date desc'

        return Product.search(domain, order=order, limit=limit)

    @staticmethod
    def _seller_address(seller):
        if seller.x_profile_address:
            return seller.x_profile_address

        partner = seller.partner_id
        if not partner:
            return seller.x_profile_location or 'Area kampus UNISA Yogyakarta'

        address_parts = [
            partner.street,
            partner.street2,
            partner.city,
            partner.state_id.name,
        ]
        return ', '.join([part for part in address_parts if part]) or seller.x_profile_location or 'Area kampus UNISA Yogyakarta'

    @staticmethod
    def _seller_map_coordinates(seller):
        lat = seller.x_profile_latitude
        lng = seller.x_profile_longitude
        if lat and lng:
            return lat, lng
        return -7.7162, 110.3554

    @staticmethod
    def _seller_review_summary(products):
        if not products or 'unitrade.review' not in request.env.registry:
            return {
                'rating': 0.0,
                'review_count': 0,
                'counts': {str(star): 0 for star in range(1, 6)},
            }

        domain = [
            ('product_id', 'in', products.ids),
            ('is_visible', '=', True),
        ]
        Review = request.env['unitrade.review'].sudo()
        reviews = Review.search(domain)
        review_count = len(reviews)
        counts = {}
        for star in range(1, 6):
            counts[str(star)] = Review.search_count(domain + [('rating', '=', star)])
        return {
            'rating': round(sum(reviews.mapped('rating')) / review_count, 1) if review_count else 0.0,
            'review_count': review_count,
            'counts': counts,
        }

    @staticmethod
    def _seller_reviews(products, rating=None, limit=12):
        if not products or 'unitrade.review' not in request.env.registry:
            return request.env['ir.ui.view'].browse()
        domain = [
            ('product_id', 'in', products.ids),
            ('is_visible', '=', True),
        ]
        if rating:
            domain.append(('rating', '=', rating))
        return request.env['unitrade.review'].sudo().search(domain, order='create_date desc', limit=limit)

    @staticmethod
    def _seller_review_star_filters(review_summary, rating, active_rating=None):
        rounded_rating = int(round(rating or 0))
        counts = review_summary.get('counts') or {}
        filters = [
            {
                'star': star,
                'count': counts.get(str(star), 0),
                'active': active_rating == star,
            }
            for star in range(5, 0, -1)
        ]
        display = [
            {
                'star': star,
                'count': counts.get(str(star), 0),
                'active': star <= rounded_rating,
            }
            for star in range(1, 6)
        ]
        return filters, display

    @staticmethod
    def _active_review_rating(value):
        try:
            rating = int(value or 0)
        except (TypeError, ValueError):
            return 0
        return rating if 1 <= rating <= 5 else 0

    @staticmethod
    def _format_money(amount, currency=None):
        currency = currency or request.website.currency_id or request.env.company.currency_id
        formatted = ('{:,.0f}'.format(amount or 0.0)).replace(',', '.')
        symbol = currency.symbol or 'Rp'
        if currency.position == 'after':
            return '%s %s' % (formatted, symbol)
        return '%s %s' % (symbol, formatted)

    @staticmethod
    def _format_datetime_label(value):
        if not value:
            return ''
        try:
            localized = fields.Datetime.context_timestamp(request.env.user, value)
        except Exception:
            localized = value
        return localized.strftime('%d %b %Y')

    @staticmethod
    def _dashboard_seller():
        user = request.env.user
        return request.env['unitrade.seller'].sudo().search([
            ('user_id', '=', user.id),
            ('status', '=', 'verified'),
        ], limit=1)

    @staticmethod
    def _seller_dashboard_product_domain(seller, active_only=False):
        Product = request.env['product.template'].sudo()
        required_fields = {'x_seller_id', 'x_is_marketplace'}
        if not required_fields.issubset(Product._fields):
            return [('id', '=', 0)]
        domain = [
            ('x_seller_id', '=', seller.id),
            ('x_is_marketplace', '=', True),
        ]
        if active_only:
            domain += [
                ('sale_ok', '=', True),
                ('website_published', '=', True),
            ]
        return domain

    def _seller_dashboard_products(self, seller, limit=8):
        Product = request.env['product.template'].sudo()
        products = Product.search(
            self._seller_dashboard_product_domain(seller, active_only=True),
            order='write_date desc, create_date desc',
            limit=limit,
        )
        return products

    @staticmethod
    def _stock_label(product):
        qty = _safe_get(product, 'x_unitrade_free_qty', False)
        if qty is False:
            variant = product.product_variant_id or product.product_variant_ids[:1]
            qty = variant.free_qty if variant and 'free_qty' in variant._fields else 0
        try:
            qty = float(qty or 0)
        except (TypeError, ValueError):
            qty = 0
        if qty <= 0:
            return 'Stok habis'
        if qty.is_integer():
            return '%s stok' % int(qty)
        return '%s stok' % qty

    def _listing_expiry(self, product):
        expires_at = _safe_get(product, 'x_listing_expires_at', False)
        if not expires_at:
            return {'label': 'Tanpa batas', 'state': 'neutral'}
        now = fields.Datetime.now()
        if expires_at < now:
            return {'label': 'Expired', 'state': 'error'}
        days = max(0, int(math.ceil((expires_at - now).total_seconds() / 86400.0)))
        if days <= 0:
            return {'label': 'Exp: hari ini', 'state': 'warning'}
        return {'label': 'Exp: %s hari' % days, 'state': 'warning' if days <= 3 else 'neutral'}

    def _seller_dashboard_product_payloads(self, seller):
        payloads = []
        for product in self._seller_dashboard_products(seller):
            expiry = self._listing_expiry(product)
            payloads.append({
                'id': product.id,
                'name': product.name,
                'price_label': self._format_money(product.list_price, request.website.currency_id),
                'image_url': '/web/image/product.template/%s/image_256' % product.id,
                'url': product.website_url or '/unitrade/product/%s' % product.id,
                'listing_fee_label': self._format_money(_safe_get(product, 'x_listing_fee', 0.0), request.website.currency_id),
                'expiry_label': expiry['label'],
                'expiry_state': expiry['state'],
                'stock_label': self._stock_label(product),
                'rating_label': '%.1f' % (_safe_get(product, 'x_average_rating', 0.0) or 0.0),
            })
        return payloads

    def _seller_dashboard_order_lines(self, seller, limit=None, revenue_only=False):
        SaleOrderLine = request.env['sale.order.line'].sudo()
        Product = request.env['product.template'].sudo()
        if 'x_seller_id' not in Product._fields:
            return SaleOrderLine.browse()

        domain = [
            ('display_type', '=', False),
            ('product_id', '!=', False),
            ('product_id.product_tmpl_id.x_seller_id', '=', seller.id),
        ]
        if revenue_only:
            domain.append(('order_id.state', 'in', ['sale', 'done']))
            if 'x_payment_status' in request.env['sale.order']._fields:
                domain.append(('order_id.x_payment_status', '=', 'paid'))
        else:
            domain.append(('order_id.state', 'in', ['sent', 'sale', 'done', 'cancel']))
        return SaleOrderLine.search(domain, order='create_date desc, id desc', limit=limit)

    def _delivery_by_order(self, order_ids):
        if not order_ids or 'unitrade.delivery' not in request.env.registry:
            return {}
        deliveries = request.env['unitrade.delivery'].sudo().search([
            ('order_id', 'in', order_ids),
        ], order='create_date desc')
        result = {}
        for delivery in deliveries:
            result.setdefault(delivery.order_id.id, delivery)
        return result

    def _order_status_payload(self, order, delivery=False):
        payment_status = _safe_get(order, 'x_payment_status', '') or ''
        delivery_status = delivery.status if delivery else ''
        if order.state == 'cancel':
            return {'key': 'cancel', 'label': 'Dibatalkan'}
        if delivery_status == 'delivered':
            return {'key': 'done', 'label': 'Terkirim'}
        if delivery_status in ('picked_up', 'in_transit'):
            return {'key': 'shipping', 'label': 'Dikirim'}
        if payment_status in ('failed', 'expired'):
            return {'key': 'cancel', 'label': 'Pembayaran gagal'}
        if payment_status == 'pending':
            return {'key': 'pending', 'label': 'Menunggu bayar'}
        if order.state in ('sale', 'done'):
            return {'key': 'processing', 'label': 'Perlu diproses'}
        return {'key': 'pending', 'label': 'Masuk'}

    def _customer_avatar_url(self, order):
        user = request.env['res.users'].sudo().search([
            ('partner_id', '=', order.partner_id.id),
        ], limit=1)
        if user:
            return '/web/image/res.users/%s/avatar_128?unique=%s' % (user.id, user.write_date or '')
        return '/web/static/img/user_menu_avatar.png'

    def _seller_dashboard_order_payloads(self, seller, limit=6):
        lines = self._seller_dashboard_order_lines(seller, limit=limit)
        deliveries = self._delivery_by_order(lines.mapped('order_id').ids)
        conversations = {}
        if 'unitrade.chat.conversation' in request.env.registry:
            buyer_users = request.env['res.users'].sudo().search([
                ('partner_id', 'in', lines.mapped('order_id.partner_id').ids),
            ])
            chat_records = request.env['unitrade.chat.conversation'].sudo().search([
                ('seller_id', '=', seller.id),
                ('buyer_user_id', 'in', buyer_users.ids),
                ('active', '=', True),
            ], order='last_message_date desc, create_date desc')
            for conversation in chat_records:
                conversations.setdefault(conversation.buyer_user_id.partner_id.id, conversation)

        payloads = []
        for line in lines:
            order = line.order_id
            status = self._order_status_payload(order, deliveries.get(order.id))
            conversation = conversations.get(order.partner_id.id)
            payloads.append({
                'order_name': order.name,
                'customer_name': order.partner_id.name or 'Pembeli UniTrade',
                'customer_avatar_url': self._customer_avatar_url(order),
                'product_name': line.product_id.product_tmpl_id.name,
                'date_label': self._format_datetime_label(order.date_order),
                'total_label': self._format_money(line.price_total, order.currency_id),
                'status_key': status['key'],
                'status_label': status['label'],
                'action_url': '/unitrade/chat?conversation_id=%s' % conversation.id if conversation else '/unitrade/chat',
            })
        return payloads

    def _seller_dashboard_pending_order_count(self, seller):
        lines = self._seller_dashboard_order_lines(seller)
        deliveries = self._delivery_by_order(lines.mapped('order_id').ids)
        count = 0
        for line in lines:
            status = self._order_status_payload(line.order_id, deliveries.get(line.order_id.id))
            if status['key'] in ('pending', 'processing', 'shipping'):
                count += 1
        return count

    def _seller_dashboard_chat_payloads(self, seller, limit=4):
        if 'unitrade.chat.conversation' not in request.env.registry:
            return [], 0
        all_conversations = request.env['unitrade.chat.conversation'].sudo().search([
            ('seller_id', '=', seller.id),
            ('seller_user_id', '=', request.env.uid),
            ('active', '=', True),
        ], order='last_message_date desc, create_date desc')
        unread_total = sum(all_conversations.mapped('seller_unread_count'))
        conversations = all_conversations[:limit]
        payloads = []
        for conversation in conversations:
            payloads.append({
                'title': conversation.buyer_user_id.name or 'Pembeli UniTrade',
                'subtitle': conversation.product_id.name if conversation.product_id else 'Chat pembeli',
                'last_message': conversation.last_message_body or 'Belum ada pesan',
                'last_message_label': conversation.last_message_date.strftime('%d %b') if conversation.last_message_date else '',
                'unread_count': conversation.seller_unread_count,
                'url': '/unitrade/chat?conversation_id=%s' % conversation.id,
                'avatar_url': conversation._avatar_url(conversation.buyer_user_id),
            })
        return payloads, unread_total

    def _seller_dashboard_review_payloads(self, products, limit=3):
        if not products or 'unitrade.review' not in request.env.registry:
            return []
        reviews = request.env['unitrade.review'].sudo().search([
            ('product_id', 'in', products.ids),
            ('is_visible', '=', True),
        ], order='create_date desc', limit=limit)
        return [{
            'reviewer_name': review.user_id.name or 'Pengguna',
            'product_name': review.product_id.name,
            'rating': review.rating,
            'comment': review.comment or 'Tidak ada komentar.',
            'date_label': self._format_datetime_label(review.create_date),
        } for review in reviews]

    def _seller_dashboard_chart_data(self, seller):
        lines = self._seller_dashboard_order_lines(seller, revenue_only=True)
        daily_revenue = defaultdict(float)
        daily_orders = defaultdict(int)
        for line in lines:
            date_order = line.order_id.date_order
            if not date_order:
                continue
            day = date_order.date()
            daily_revenue[day] += line.price_total
            daily_orders[day] += 1

        today = fields.Date.context_today(request.env.user)
        weekly_days = [today - timedelta(days=offset) for offset in range(6, -1, -1)]
        weekly = {
            'labels': [day.strftime('%d/%m') for day in weekly_days],
            'revenue': [round(daily_revenue.get(day, 0.0), 2) for day in weekly_days],
            'orders': [daily_orders.get(day, 0) for day in weekly_days],
        }

        monthly_days = [today - timedelta(days=offset) for offset in range(29, -1, -1)]
        buckets = []
        for start in range(0, len(monthly_days), 5):
            bucket_days = monthly_days[start:start + 5]
            if not bucket_days:
                continue
            buckets.append({
                'label': '%s-%s' % (bucket_days[0].strftime('%d/%m'), bucket_days[-1].strftime('%d/%m')),
                'revenue': round(sum(daily_revenue.get(day, 0.0) for day in bucket_days), 2),
                'orders': sum(daily_orders.get(day, 0) for day in bucket_days),
            })
        monthly = {
            'labels': [bucket['label'] for bucket in buckets],
            'revenue': [bucket['revenue'] for bucket in buckets],
            'orders': [bucket['orders'] for bucket in buckets],
        }
        return {'weekly': weekly, 'monthly': monthly}

    def _seller_dashboard_context(self, seller):
        all_products = request.env['product.template'].sudo().search(
            self._seller_dashboard_product_domain(seller, active_only=False)
        )
        active_products = request.env['product.template'].sudo().search(
            self._seller_dashboard_product_domain(seller, active_only=True)
        )
        review_summary = self._seller_review_summary(all_products)
        revenue_lines = self._seller_dashboard_order_lines(seller, revenue_only=True)
        total_revenue = sum(revenue_lines.mapped('price_total'))
        order_payloads = self._seller_dashboard_order_payloads(seller)
        chat_payloads, unread_chat_count = self._seller_dashboard_chat_payloads(seller)
        pending_order_count = self._seller_dashboard_pending_order_count(seller)
        sold_count = int(sum(all_products.mapped('sales_count'))) if all_products and 'sales_count' in all_products._fields else len(revenue_lines)
        chart_data = self._seller_dashboard_chart_data(seller)

        return {
            'seller': seller,
            'seller_public_ref': self._seller_public_ref(seller),
            'dashboard_stats': {
                'revenue_label': self._format_money(total_revenue, request.website.currency_id),
                'available_balance_label': self._format_money(total_revenue, request.website.currency_id),
                'active_products': len(active_products),
                'incoming_orders': pending_order_count,
                'average_rating': review_summary['rating'] or seller.average_rating or 0.0,
                'review_count': review_summary['review_count'],
                'sold_count': sold_count,
                'unread_chat_count': unread_chat_count,
                'notification_count': pending_order_count + unread_chat_count,
            },
            'dashboard_products': self._seller_dashboard_product_payloads(seller),
            'dashboard_orders': order_payloads,
            'dashboard_messages': chat_payloads,
            'dashboard_reviews': self._seller_dashboard_review_payloads(all_products),
            'dashboard_chart_json': json.dumps(chart_data),
            'dashboard_search_items_json': json.dumps([]),
            'add_product_url': '/web#action=unitrade_product_ext.action_unitrade_products&model=product.template&view_type=form'
                if request.env.user.has_group('unitrade_seller.group_unitrade_admin') else '',
            'page_title': 'Dashboard Penjual - UniTrade',
        }

    @http.route([
        '/seller-profile/<string:profile_ref>',
        '/unitrade/seller-profile/<string:profile_ref>',
        '/unitrade/seller/<int:seller_id>',
        '/seller/<int:seller_id>',
    ], type='http', auth='public', website=True, sitemap=True)
    def seller_profile(self, profile_ref=None, seller_id=None, **kwargs):
        """Render public seller profile from the Figma seller-page design."""
        seller = self._get_seller_by_public_ref(profile_ref=profile_ref, seller_id=seller_id)
        if not seller:
            return request.not_found()

        search = (kwargs.get('search') or '').strip()
        tab = kwargs.get('tab') or 'home'
        if tab not in self._PROFILE_TABS:
            tab = 'home'
        active_rating = self._active_review_rating(kwargs.get('rating')) if tab == 'reviews' else 0

        all_products = request.env['product.template'].sudo().search([
            ('x_seller_id', '=', seller.id),
            ('x_is_marketplace', '=', True),
            ('sale_ok', '=', True),
            ('website_published', '=', True),
        ])
        products = self._seller_products(seller, search=search, tab=tab)
        review_summary = self._seller_review_summary(all_products)
        seller_rating = review_summary['rating'] or seller.average_rating or 0.0
        review_star_filters, review_star_display = self._seller_review_star_filters(review_summary, seller_rating, active_rating)
        seller_reviews = self._seller_reviews(all_products, rating=active_rating)
        total_sold = int(sum(all_products.mapped('sales_count'))) if all_products and 'sales_count' in all_products._fields else 0
        joined_date = seller.create_date.strftime('%d/%m/%Y') if seller.create_date else ''
        seller_public_ref = self._seller_public_ref(seller)
        seller_map_lat, seller_map_lng = self._seller_map_coordinates(seller)

        values = {
            'seller': seller,
            'seller_public_ref': seller_public_ref,
            'seller_is_preview': seller.status != 'verified',
            'seller_products': products,
            'seller_all_products': all_products,
            'seller_address': self._seller_address(seller),
            'seller_map_lat': seller_map_lat,
            'seller_map_lng': seller_map_lng,
            'seller_rating': seller_rating,
            'seller_review_count': review_summary['review_count'],
            'seller_review_counts': review_summary['counts'],
            'seller_review_star_filters': review_star_filters,
            'seller_review_star_display': review_star_display,
            'seller_review_active_rating': active_rating,
            'seller_reviews': seller_reviews,
            'seller_total_sold': total_sold or seller.total_sold,
            'seller_joined_date': joined_date,
            'active_tab': tab,
            'seller_search': search,
            'seller_tab_urls': {
                key: '/seller-profile/%s?%s' % (
                    seller_public_ref,
                    url_encode({
                        'tab': key,
                        'search': search,
                    } if search else {'tab': key}),
                )
                for key in self._PROFILE_TABS
            },
            'page_title': '%s - Profil Penjual UniTrade' % seller.name,
        }
        return request.render('unitrade_seller.seller_profile_template', values)

    @http.route('/unitrade/seller-profile/products', type='json', auth='public', website=True, methods=['POST'])
    def seller_profile_products(self, **kwargs):
        """Return seller profile tab fragments for OWL switching."""
        profile_ref = kwargs.get('profile_ref') or ''
        tab = kwargs.get('tab') or 'home'
        search = (kwargs.get('search') or '').strip()
        if tab not in self._PROFILE_TABS:
            tab = 'home'
        active_rating = self._active_review_rating(kwargs.get('rating')) if tab == 'reviews' else 0

        seller = self._get_seller_by_public_ref(profile_ref=profile_ref)
        if not seller:
            return {
                'success': False,
                'message': 'Seller tidak ditemukan',
                'html': '',
            }

        all_products = request.env['product.template'].sudo().search([
            ('x_seller_id', '=', seller.id),
            ('x_is_marketplace', '=', True),
            ('sale_ok', '=', True),
            ('website_published', '=', True),
        ])
        template = 'unitrade_seller.seller_profile_reviews_fragment' if tab == 'reviews' else 'unitrade_seller.seller_profile_products_fragment'
        products = self._seller_products(seller, search=search, tab=tab)
        review_summary = self._seller_review_summary(all_products)
        seller_rating = review_summary['rating'] or seller.average_rating or 0.0
        review_star_filters, review_star_display = self._seller_review_star_filters(review_summary, seller_rating, active_rating)
        html = request.env['ir.ui.view']._render_template(
            template,
            {
                'seller': seller,
                'seller_products': products,
                'seller_reviews': self._seller_reviews(all_products, rating=active_rating),
                'seller_rating': seller_rating,
                'seller_review_count': review_summary['review_count'],
                'seller_review_counts': review_summary['counts'],
                'seller_review_star_filters': review_star_filters,
                'seller_review_star_display': review_star_display,
                'seller_review_active_rating': active_rating,
                'seller_search': search,
            },
        )
        return {
            'success': True,
            'html': str(html),
            'tab': tab,
            'search': search,
            'rating': active_rating,
        }

    @http.route('/unitrade/seller/profile', type='http', auth='user', website=True)
    def my_seller_profile(self, **kwargs):
        """Convenience route for the current user's public seller profile."""
        seller = request.env['unitrade.seller'].sudo().search([
            ('user_id', '=', request.env.uid),
            ('status', '=', 'verified'),
        ], limit=1)
        if not seller:
            return request.redirect('/seller-verification')
        return request.redirect('/seller-profile/%s' % self._seller_public_ref(seller))

    @http.route([
        '/seller-profile/<string:profile_ref>/chat',
        '/unitrade/seller/<int:seller_id>/chat',
    ], type='http', auth='user', website=True)
    def seller_chat(self, profile_ref=None, seller_id=None, **kwargs):
        """Open the internal UniTrade chat when available, otherwise keep the old fallback."""
        seller = self._get_seller_by_public_ref(profile_ref=profile_ref, seller_id=seller_id)
        if not seller:
            return request.not_found()

        if 'unitrade.chat.conversation' in request.env.registry:
            product_id = kwargs.get('product_id')
            try:
                conversation = request.env['unitrade.chat.conversation'].open_for_seller(
                    seller=seller,
                    product_id=product_id,
                )
                return request.redirect('/unitrade/chat?conversation_id=%s' % conversation.id)
            except Exception:
                _logger.exception('Internal seller chat failed for user %s and seller %s', request.env.uid, seller.id)
                return request.redirect('/seller-profile/%s?chat=failed' % self._seller_public_ref(seller))

        whatsapp = seller.user_id.x_whatsapp if 'x_whatsapp' in seller.user_id._fields else ''
        if whatsapp:
            phone = ''.join(ch for ch in whatsapp if ch.isdigit())
            if phone.startswith('0'):
                phone = '62%s' % phone[1:]
            return request.redirect('https://wa.me/%s' % phone, local=False)

        _logger.info('Seller chat requested by user %s for seller %s', request.env.uid, seller.id)
        return request.redirect('/seller-profile/%s?chat=requested' % self._seller_public_ref(seller))

    @http.route([
        '/seller-profile/<string:profile_ref>/report',
        '/unitrade/seller/<int:seller_id>/report',
    ], type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def report_seller(self, profile_ref=None, seller_id=None, **kwargs):
        """Create a lightweight moderation note for a reported seller profile."""
        seller = self._get_seller_by_public_ref(profile_ref=profile_ref, seller_id=seller_id)
        if not seller:
            return request.not_found()

        reason = (kwargs.get('reason') or 'Report dari halaman profil penjual').strip()[:500]
        media_files = request.httprequest.files.getlist('media')
        if len(media_files) > 3:
            return request.redirect('/seller-profile/%s?report_error=media_limit' % self._seller_public_ref(seller))

        attachments = []
        for index, media in enumerate(media_files[:3], start=1):
            if not media or not media.filename:
                continue
            mimetype = media.mimetype or ''
            if not mimetype.startswith('image/'):
                continue
            filename = media.filename.rsplit('\\', 1)[-1].rsplit('/', 1)[-1] or 'seller-report-%s.jpg' % index
            attachments.append((filename, media.read()))

        body = Markup('Seller dilaporkan oleh %s: %s') % (escape(request.env.user.name), escape(reason))
        if attachments:
            body += Markup('<br/>Media pendukung: %s gambar.') % len(attachments)
        seller.message_post(body=body, subtype_xmlid='mail.mt_note', attachments=attachments, body_is_html=True)
        _logger.info(
            'Seller %s reported by user %s with %s media attachment(s)',
            seller.id,
            request.env.uid,
            len(attachments),
        )
        return request.redirect('/seller-profile/%s?reported=1' % self._seller_public_ref(seller))

    @http.route(['/unitrade/seller/register', '/seller/register'], type='http', auth='user', website=True)
    def seller_register_page(self, **kwargs):
        """Keep the old seller URL as an alias for the current verification flow."""
        return request.redirect('/seller-verification')

    @http.route('/unitrade/seller/register/submit', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def seller_register_submit(self, **kwargs):
        """Keep the old submit URL from creating a second verification path."""
        return request.redirect('/seller-verification')

    @http.route([
        '/unitrade/seller/dashboard',
        '/seller/dashboard',
        '/my/seller/dashboard',
    ], type='http', auth='user', website=True, sitemap=False)
    def seller_dashboard(self, **kwargs):
        """Render the standalone seller dashboard app shell."""
        seller = self._dashboard_seller()
        if not seller:
            return request.redirect('/seller-verification')

        return request.render(
            'unitrade_seller.seller_dashboard_template',
            self._seller_dashboard_context(seller),
        )

    @http.route('/unitrade/otp/send', type='json', auth='user', methods=['POST'])
    def send_otp(self, **kwargs):
        """Send OTP through the shared unitrade.otp model."""
        try:
            request.env.user.action_send_otp()
            return {'status': 'success', 'message': 'OTP berhasil dikirim ke email Anda.'}
        except Exception as e:
            _logger.exception('Failed to generate OTP for user %s', request.env.uid)
            return {'status': 'error', 'message': str(e)}

    @http.route('/unitrade/otp/verify', type='json', auth='user', methods=['POST'])
    def verify_otp(self, **kwargs):
        """Verify OTP through the shared unitrade.otp model."""
        data = request.jsonrequest or {}
        otp_code = data.get('otp_code', '')

        try:
            request.env.user.action_verify_otp(otp_code)
            request.env.user.sudo().write({'is_otp_verified': True})
            return {'status': 'success', 'message': 'Email berhasil diverifikasi!'}
        except Exception as e:
            _logger.exception('Failed to verify OTP for user %s', request.env.uid)
            return {'status': 'error', 'message': str(e)}
