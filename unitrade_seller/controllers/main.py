from collections import defaultdict
from datetime import timedelta
import json
import math
import logging

# pyrefly: ignore [missing-import]
<<<<<<< HEAD
from odoo import fields, http
=======
from odoo import _, SUPERUSER_ID, fields, http
# pyrefly: ignore [missing-import]
from odoo.exceptions import UserError, ValidationError
>>>>>>> ca9bf47 (feat : admin fajar anjay sadboy)
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
<<<<<<< HEAD
    def _dashboard_seller():
        user = request.env.user
        return request.env['unitrade.seller'].sudo().search([
            ('user_id', '=', user.id),
            ('status', '=', 'verified'),
        ], limit=1)
=======
    def _format_order_datetime_label(value):
        if not value:
            return ''
        try:
            localized = fields.Datetime.context_timestamp(request.env.user, value)
        except Exception:
            localized = value

        today = fields.Date.context_today(request.env.user)
        order_date = localized.date()
        if order_date == today:
            return 'Today, %s' % localized.strftime('%I:%M %p').lstrip('0')
        if order_date == today - timedelta(days=1):
            return 'Yesterday'
        return localized.strftime('%d %b %Y')

    @staticmethod
    def _format_product_datetime_label(value):
        if not value:
            return ''
        try:
            localized = fields.Datetime.context_timestamp(request.env.user, value)
        except Exception:
            localized = value

        today = fields.Date.context_today(request.env.user)
        product_date = localized.date()
        if product_date == today:
            return 'Hari ini, %s' % localized.strftime('%I:%M %p').lstrip('0')
        if product_date == today - timedelta(days=1):
            return 'Kemarin'
        if product_date >= today - timedelta(days=7):
            return 'Minggu lalu'
        return localized.strftime('%d %b %Y')

    @staticmethod
    def _format_datetime_full_label(value):
        if not value:
            return ''
        try:
            localized = fields.Datetime.context_timestamp(request.env.user, value)
        except Exception:
            localized = value
        return localized.strftime('%d %b %Y, %H:%M')

    @staticmethod
    def _seller_store_is_active(seller):
        return bool(_safe_get(seller, 'x_store_active', True))

    @staticmethod
    def _current_user_block_message(feature_label=None):
        user = request.env.user
        if user._is_public() or not hasattr(user, '_check_unitrade_marketplace_access'):
            return ''
        try:
            user._check_unitrade_marketplace_access(feature_label or _('menggunakan fitur seller'))
        except UserError as error:
            return error.args[0] if error.args else str(error)
        return ''

    @staticmethod
    def _dashboard_seller(active_only=True):
        user = request.env.user
        Seller = request.env['unitrade.seller'].sudo()
        if UnitradeSellerController._current_user_block_message(_('menggunakan fitur seller')):
            return Seller.browse()
        domain = [
            ('user_id', '=', user.id),
            ('status', '=', 'verified'),
        ]
        if active_only and 'x_store_active' in Seller._fields:
            domain.append(('x_store_active', '=', True))
        return Seller.search(domain, limit=1)

    def _seller_not_ready_redirect(self):
        if self._current_user_block_message(_('menggunakan fitur seller')):
            return request.redirect('/my/profile?unitrade_blocked=1')
        seller = self._dashboard_seller(active_only=False)
        if seller and not self._seller_store_is_active(seller):
            return request.redirect('/unitrade/seller/settings?store_inactive=1')
        return request.redirect('/seller-onboarding')

    def _seller_not_ready_message(self):
        block_message = self._current_user_block_message(_('menggunakan fitur seller'))
        if block_message:
            return block_message
        seller = self._dashboard_seller(active_only=False)
        if seller and not self._seller_store_is_active(seller):
            return 'Toko sedang nonaktif. Aktifkan kembali di Pengaturan Toko untuk memakai fitur seller.'
        return 'Akun penjual belum terverifikasi.'
>>>>>>> ca9bf47 (feat : admin fajar anjay sadboy)

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
<<<<<<< HEAD
            return {'label': 'Exp: hari ini', 'state': 'warning'}
        return {'label': 'Exp: %s hari' % days, 'state': 'warning' if days <= 3 else 'neutral'}
=======
            label = 'Aktif sampai hari ini'
        else:
            label = 'Sisa %s hari' % days
        state = 'warning' if days <= 3 else 'active'
        return {
            'is_active': bool(product.sale_ok and product.website_published),
            'status_label': 'Aktif' if product.sale_ok and product.website_published else 'Nonaktif',
            'label': label,
            'expiry_label': label,
            'state': state,
            'expiry_state': state,
            'days_remaining': days,
        }

    def _seller_sync_listing_fee_timeouts(self, seller=False, product=False):
        if 'unitrade.payment.intent' not in request.env.registry:
            return 0
        PaymentIntent = request.env['unitrade.payment.intent'].sudo()
        if not hasattr(PaymentIntent, '_unitrade_expire_stale_listing_fee_intents'):
            return 0
        try:
            return PaymentIntent._unitrade_expire_stale_listing_fee_intents(
                seller=seller.sudo() if seller else False,
                product=product.with_context(active_test=False).sudo() if product else False,
            )
        except Exception:
            _logger.exception('Failed expiring stale listing fee intents for seller %s product %s', seller.id if seller else '', product.id if product else '')
            return 0

    @staticmethod
    def _seller_product_detail_url(product):
        return '/unitrade/seller/products/%s' % product.id

    @staticmethod
    def _seller_product_public_url(product):
        return product.website_url or '/unitrade/product/%s' % product.id

    @staticmethod
    def _seller_payment_state_label(state):
        return {
            'draft': 'Draft',
            'pending': 'Menunggu Pembayaran',
            'paid': 'Berhasil',
            'failed': 'Gagal',
            'expired': 'Kedaluwarsa',
            'cancelled': 'Dibatalkan',
            'refunded': 'Dikembalikan',
        }.get(state or '', state or '-')

    def _seller_listing_fee_intent_search(self, seller, product, domain_extra=None, limit=None):
        if 'unitrade.payment.intent' not in request.env.registry or not product:
            return False
        domain = [
            ('intent_type', '=', 'listing_fee'),
            ('product_template_id', '=', product.id),
        ]
        if seller:
            domain.append(('seller_id', '=', seller.id))
        if domain_extra:
            domain.extend(domain_extra)
        return request.env['unitrade.payment.intent'].sudo().search(
            domain,
            order='create_date desc, id desc',
            limit=limit,
        )

    def _seller_payment_intent_payload(self, intent):
        if not intent:
            return {}
        reference_key = intent._unitrade_reference_key() if hasattr(intent, '_unitrade_reference_key') else (intent.midtrans_order_id or intent.name)
        payment_url = intent.unitrade_public_payment_url() if hasattr(intent, 'unitrade_public_payment_url') else (
            '/unitrade/payment/instructions/%s' % reference_key if reference_key else ''
        )
        return {
            'id': intent.id,
            'name': intent.name or '',
            'state': intent.state or '',
            'state_label': self._seller_payment_state_label(intent.state),
            'provider': intent.provider or '',
            'provider_label': 'Saldo Akun' if intent.payment_method_code == 'account_balance' else (intent.provider or '').title(),
            'method_code': intent.payment_method_code or '',
            'method_label': intent.payment_method_label or ('Saldo Akun' if intent.payment_method_code == 'account_balance' else '-'),
            'amount': intent.amount or 0.0,
            'amount_label': self._format_money(intent.amount, intent.currency_id),
            'reference': intent.payment_reference or reference_key or '',
            'payment_url': payment_url,
            'expires_at': fields.Datetime.to_string(intent.expires_at) if intent.expires_at else '',
            'expires_at_label': self._format_datetime_full_label(intent.expires_at),
            'paid_at': fields.Datetime.to_string(intent.paid_at) if intent.paid_at else '',
            'paid_at_label': self._format_datetime_full_label(intent.paid_at),
            'error_message': intent.error_message or '',
        }

    @staticmethod
    def _seller_product_stock_qty(product):
        stock_qty = _safe_get(product, 'x_unitrade_free_qty', False)
        if stock_qty is False:
            variant = product.product_variant_id or product.product_variant_ids[:1]
            stock_qty = variant.free_qty if variant and 'free_qty' in variant._fields else 0
        try:
            stock_qty = float(stock_qty or 0)
        except (TypeError, ValueError):
            stock_qty = 0
        return stock_qty

    def _seller_product_listing_status(self, seller, product):
        self._seller_sync_listing_fee_timeouts(seller=seller, product=product)
        expiry = self._listing_expiry(product)
        latest_intent = self._seller_listing_fee_intent_search(seller, product, limit=1)
        paid_intent = self._seller_listing_fee_intent_search(seller, product, [('state', '=', 'paid')], limit=1)
        latest_payload = self._seller_payment_intent_payload(latest_intent) if latest_intent else {}
        paid_payload = self._seller_payment_intent_payload(paid_intent) if paid_intent else {}
        now = fields.Datetime.now()
        record_active = bool(_safe_get(product, 'active', True))
        expires_at = _safe_get(product, 'x_listing_expires_at', False)
        latest_expired = bool(latest_intent and latest_intent.expires_at and latest_intent.expires_at <= now)

        key = 'draft'
        label = 'Draft'
        tone = 'neutral'
        note = 'Produk tersimpan sebagai draft dan belum tampil di shop.'
        can_continue_payment = record_active
        payment_url = '/unitrade/seller/products/%s/payment' % product.id if record_active else ''
        public_url = ''

        if paid_intent:
            can_continue_payment = False
            if expires_at and expires_at < now:
                key = 'expired'
                label = 'Masa Aktif Habis'
                tone = 'expired'
                note = 'Masa aktif 30 hari sudah berakhir. Upload ulang produk untuk menjual lagi.'
            elif record_active and expiry.get('is_active'):
                key = 'active'
                label = 'Aktif'
                tone = 'active'
                note = 'Produk aktif dan tampil di shop.'
                public_url = self._seller_product_public_url(product)
            else:
                key = 'inactive'
                label = 'Nonaktif'
                tone = 'inactive'
                note = 'Produk sudah dibayar, tetapi sedang tidak tampil di shop.'
        elif latest_intent and latest_intent.state == 'pending' and not latest_expired and record_active:
            key = 'pending_payment'
            label = 'Menunggu Pembayaran'
            tone = 'warning'
            note = 'Selesaikan pembayaran sebelum batas waktu agar produk tampil di shop.'
            can_continue_payment = True
            payment_url = latest_payload.get('payment_url') or payment_url
        elif latest_intent and latest_intent.state == 'failed' and record_active:
            key = 'draft'
            label = 'Draft'
            tone = 'neutral'
            note = 'Pembayaran sebelumnya gagal dibuat. Pilih metode pembayaran lagi untuk melanjutkan.'
            can_continue_payment = True
        elif (
            (latest_intent and latest_intent.state in ('expired', 'cancelled'))
            or (latest_intent and latest_expired)
            or not record_active
        ):
            key = 'cancelled'
            label = 'Dibatalkan'
            tone = 'danger'
            note = 'Batas pembayaran sudah lewat. Produk ini diarsipkan dan harus diupload ulang.'
            can_continue_payment = False
            payment_url = ''

        if key == 'pending_payment' and latest_payload.get('expires_at_label'):
            expiry_label = 'Bayar sebelum %s' % latest_payload['expires_at_label']
            expiry_state = 'warning'
        elif key in ('draft',):
            expiry_label = 'Belum aktif'
            expiry_state = 'inactive'
        elif key == 'cancelled':
            expiry_label = 'Kedaluwarsa'
            expiry_state = 'expired'
        else:
            expiry_label = expiry.get('expiry_label') or expiry.get('label') or 'Belum aktif'
            expiry_state = expiry.get('expiry_state') or expiry.get('state') or tone

        return {
            'key': key,
            'label': label,
            'tone': tone,
            'note': note,
            'is_active': key == 'active',
            'record_active': record_active,
            'can_continue_payment': can_continue_payment,
            'payment_url': payment_url,
            'public_url': public_url,
            'expiry_label': expiry_label,
            'expiry_state': expiry_state,
            'days_remaining': expiry.get('days_remaining'),
            'activated_at': fields.Datetime.to_string(_safe_get(product, 'x_listing_activated_at', False)) if _safe_get(product, 'x_listing_activated_at', False) else '',
            'activated_at_label': self._format_datetime_full_label(_safe_get(product, 'x_listing_activated_at', False)),
            'expires_at': expiry.get('expires_at') or (fields.Datetime.to_string(expires_at) if expires_at else ''),
            'expires_at_label': self._format_datetime_full_label(expires_at),
            'latest_intent': latest_payload,
            'paid_intent': paid_payload,
        }

    @staticmethod
    def _seller_product_should_be_active(product):
        expires_at = _safe_get(product, 'x_listing_expires_at', False)
        if expires_at:
            return expires_at >= fields.Datetime.now()
        return bool(product.sale_ok and product.website_published)

    @staticmethod
    def _seller_product_image_url(product):
        image = _safe_get(product, 'image_128', False) or _safe_get(product, 'image_1920', False)
        if image:
            return image_data_uri(image)
        return '/web/image/product.template/%s/image_256?unique=%s' % (
            product.id,
            product.write_date or '',
        )

    @staticmethod
    def _seller_product_type_values(fields_map):
        if 'detailed_type' in fields_map:
            return {'detailed_type': 'product'}
        if 'type' in fields_map:
            return {'type': 'product'}
        return {}

    @staticmethod
    def _seller_product_update_stock(product, stock):
        if 'x_unitrade_stock_qty' in product._fields:
            product.with_user(SUPERUSER_ID).sudo().write({'x_unitrade_stock_qty': stock})

    def _seller_product_expiry_label(self, product):
        expiry = self._listing_expiry(product)
        return expiry.get('expiry_label') or expiry.get('label') or 'Belum aktif'

    @staticmethod
    def _seller_product_condition(product):
        condition = _safe_get(product, 'x_condition', '') or ''
        if condition == 'new':
            return {'key': 'new', 'label': 'Baru'}
        return {'key': 'used', 'label': 'Bekas'}

    @staticmethod
    def _seller_product_backend_url(product=None):
        action = request.env.ref('unitrade_product_ext.action_unitrade_products', raise_if_not_found=False)
        params = {
            'model': 'product.template',
            'view_type': 'form',
        }
        if action:
            params['action'] = action.id
        if product:
            params['id'] = product.id
        return '/web#%s' % url_encode(params)

    @staticmethod
    def _seller_product_add_url():
        return '/unitrade/seller/products/new'

    @staticmethod
    def _seller_product_edit_url(product):
        return '/unitrade/seller/products/%s/edit' % product.id

    def _seller_home_category_records(self):
        Category = request.env['product.category'].sudo()
        category_ids = []
        seen_ids = set()
        for xmlid in self._HOME_CATEGORY_XMLIDS:
            category = request.env.ref(xmlid, raise_if_not_found=False)
            if category and category._name == 'product.category' and category.id not in seen_ids:
                category_ids.append(category.id)
                seen_ids.add(category.id)

        selected_names = set(Category.browse(category_ids).mapped('name'))
        for name in self._HOME_CATEGORY_NAMES:
            if name in selected_names:
                continue
            category = Category.search([('name', '=ilike', name)], limit=1)
            if category and category.id not in seen_ids:
                category_ids.append(category.id)
                seen_ids.add(category.id)
                selected_names.add(category.name)
        return Category.browse(category_ids)

    def _seller_product_categories(self):
        categories = self._seller_home_category_records()
        return [{
            'id': category.id,
            'name': category.name,
            'label': category.complete_name or category.name,
        } for category in categories]

    @staticmethod
    def _seller_products_date_filter(value):
        value = str(value or '30').strip().lower()
        return value if value in ('7', '30', 'all') else '30'

    @staticmethod
    def _seller_products_page_number(value):
        try:
            page = int(value or 1)
        except (TypeError, ValueError):
            page = 1
        return max(1, page)

    @staticmethod
    def _seller_products_page_size(value):
        try:
            page_size = int(value or 10)
        except (TypeError, ValueError):
            page_size = 10
        return min(max(page_size, 5), 25)

    @staticmethod
    def _seller_search_text(value):
        return re.sub(r'\s+', ' ', str(value or '').strip())[:80]

    def _seller_products_search_domain(self, query):
        query = self._seller_search_text(query)
        if not query:
            return []
        status_terms = {
            'aktif': ['active'],
            'draft': ['draft'],
            'belum aktif': ['draft', 'pending_payment'],
            'menunggu': ['pending_payment'],
            'pembayaran': ['pending_payment'],
            'kedaluwarsa': ['expired'],
            'expired': ['expired'],
            'batal': ['cancelled'],
            'dibatalkan': ['cancelled'],
            'nonaktif': ['inactive', 'archived'],
            'baru': [],
            'bekas': [],
        }
        status_keys = []
        query_lower = query.lower()
        for term, keys in status_terms.items():
            if term in query_lower:
                status_keys.extend(keys)
        domain = ['|', '|', '|',
            ('name', 'ilike', query),
            ('default_code', 'ilike', query),
            ('categ_id.name', 'ilike', query),
            ('description_sale', 'ilike', query),
        ]
        if 'baru' in query_lower:
            domain = expression.OR([domain, [('x_condition', '=', 'new')]])
        if 'bekas' in query_lower:
            domain = expression.OR([domain, [('x_condition', '=', 'used')]])
        if status_keys and 'x_listing_status' in request.env['product.template']._fields:
            domain = expression.OR([domain, [('x_listing_status', 'in', list(set(status_keys)))]])
        return domain

    def _seller_products_domain(self, seller, date_filter='30', query=''):
        date_filter = self._seller_products_date_filter(date_filter)
        domain = self._seller_dashboard_product_domain(seller, active_only=False)
        if date_filter != 'all':
            domain.append(('write_date', '>=', fields.Datetime.to_string(fields.Datetime.now() - timedelta(days=int(date_filter)))))
        search_domain = self._seller_products_search_domain(query)
        if search_domain:
            domain = expression.AND([domain, search_domain])
        return domain

    def _seller_products_page_payloads(self, seller, limit=None, date_filter='30', offset=0, query=''):
        self._refresh_seller_product_listing_states(seller)
        Product = request.env['product.template'].with_context(active_test=False).sudo()
        domain = self._seller_products_domain(seller, date_filter=date_filter, query=query)
        products = Product.search(
            domain,
            order='write_date desc, create_date desc, id desc',
            offset=offset,
            limit=limit,
        )
        payloads = []
        for product in products:
            condition = self._seller_product_condition(product)
            status = self._seller_product_listing_status(seller, product)
            stock_qty = self._seller_product_stock_qty(product)
            stock_label = int(stock_qty) if stock_qty.is_integer() else stock_qty
            payloads.append({
                'id': product.id,
                'product_code': product.default_code or ('UT%05d' % product.id),
                'image_url': self._seller_product_image_url(product),
                'name': product.name or 'Produk UniTrade',
                'date_label': self._format_product_datetime_label(product.write_date or product.create_date),
                'stock_qty': stock_qty,
                'stock_label': stock_label,
                'stock_warning': stock_qty <= 0,
                'condition_key': condition['key'],
                'condition_label': condition['label'],
                'is_active': bool(status.get('is_active')),
                'status_key': status['key'],
                'status_label': status['label'],
                'edit_url': self._seller_product_edit_url(product),
                'detail_url': self._seller_product_detail_url(product),
                'public_url': status.get('public_url') or self._seller_product_public_url(product),
                'payment_url': status.get('payment_url') or '/unitrade/seller/products/%s/payment' % product.id,
                'can_continue_payment': bool(status.get('can_continue_payment')),
                'show_public_action': status.get('key') == 'active',
                'can_edit': bool(status.get('record_active')),
                'latest_payment_label': (status.get('latest_intent') or {}).get('state_label') or '',
                'expiry_label': status.get('expiry_label') or 'Belum aktif',
                'expiry_state': status.get('expiry_state') or 'neutral',
                'days_remaining': status.get('days_remaining'),
                'expires_at': status.get('expires_at') or '',
            })
        return payloads

    def _seller_products_page_result(self, seller, date_filter='30', page=1, page_size=10, query=''):
        self._refresh_seller_product_listing_states(seller)
        Product = request.env['product.template'].with_context(active_test=False).sudo()
        date_filter = self._seller_products_date_filter(date_filter)
        query = self._seller_search_text(query)
        page = self._seller_products_page_number(page)
        page_size = self._seller_products_page_size(page_size)
        domain = self._seller_products_domain(seller, date_filter=date_filter, query=query)
        total = Product.search_count(domain)
        total_pages = max(1, int(math.ceil(float(total) / float(page_size)))) if total else 1
        page = min(page, total_pages)
        offset = (page - 1) * page_size
        return {
            'products': self._seller_products_page_payloads(
                seller,
                limit=page_size,
                date_filter=date_filter,
                offset=offset,
                query=query,
            ),
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total': total,
                'total_pages': total_pages,
                'has_prev': page > 1,
                'has_next': page < total_pages,
                'start': offset + 1 if total else 0,
                'end': min(offset + page_size, total),
            },
            'query': query,
        }

    def _seller_products_page_context(self, seller, date_filter='30', query=''):
        date_filter = self._seller_products_date_filter(date_filter)
        query = self._seller_search_text(query)
        _, unread_chat_count = self._seller_dashboard_chat_payloads(seller)
        pending_order_count = self._seller_dashboard_pending_order_count(seller)
        page_result = self._seller_products_page_result(seller, date_filter=date_filter, page=1, page_size=10, query=query)
        payload = {
            'seller': {
                'name': seller.name,
                'avatar_url': '/web/image/res.users/%s/avatar_128?unique=%s' % (
                    seller.user_id.id,
                    seller.user_id.write_date or '',
                ),
                'profile_url': '/seller-profile/%s' % self._seller_public_ref(seller),
            },
            'stats': {
                'notification_count': pending_order_count,
                'unread_chat_count': unread_chat_count,
            },
            'products': page_result['products'],
            'pagination': page_result['pagination'],
            'date_filter': date_filter,
            'query': query,
            'page_size': page_result['pagination']['page_size'],
            'add_product_url': self._seller_product_add_url(),
        }
        return {
            'page_title': 'Barang',
            'seller': seller,
            'seller_public_ref': self._seller_public_ref(seller),
            'notification_count': pending_order_count,
            'unread_chat_count': unread_chat_count,
            'add_product_url': payload['add_product_url'],
            'products_payload_json': json.dumps(payload),
        }

    def _seller_product_gallery_payload(self, product):
        images = [{
            'id': 'main-%s' % product.id,
            'url': self._seller_product_image_url(product),
            'alt': product.name or 'Produk UniTrade',
        }]
        for image in product.product_template_image_ids.filtered('image_1920')[:3]:
            images.append({
                'id': 'image-%s' % image.id,
                'url': image_data_uri(image.image_1920),
                'alt': image.name or product.name or 'Gambar produk',
            })
        return images

    def _seller_product_reviews_payload(self, product):
        summary = {
            'average': round(float(_safe_get(product, 'x_average_rating', 0.0) or 0.0), 1),
            'count': int(_safe_get(product, 'x_review_count', 0) or 0),
            'counts': [{'star': star, 'count': 0, 'percent': 0} for star in range(5, 0, -1)],
        }
        if 'unitrade.review' not in request.env.registry:
            return {'summary': summary, 'items': []}

        Review = request.env['unitrade.review'].sudo()
        all_reviews = Review.search([
            ('product_id', '=', product.id),
            ('is_visible', '=', True),
        ], order='create_date desc, id desc')
        total = len(all_reviews)
        counts = {star: 0 for star in range(1, 6)}
        for review in all_reviews:
            rating = int(review.rating or 0)
            if 1 <= rating <= 5:
                counts[rating] += 1
        if total:
            summary['count'] = total
            summary['average'] = round(sum(all_reviews.mapped('rating')) / total, 1)
        summary['counts'] = [
            {
                'star': star,
                'count': counts.get(star, 0),
                'percent': int(round((counts.get(star, 0) / total) * 100)) if total else 0,
            }
            for star in range(5, 0, -1)
        ]

        items = []
        for review in all_reviews[:8]:
            images = []
            for field_name in ('review_image', 'review_image_2', 'review_image_3'):
                image = _safe_get(review, field_name, False)
                if image:
                    images.append(image_data_uri(image))
            tags = [
                tag.strip()
                for tag in (review.review_tags or '').replace(';', ',').split(',')
                if tag.strip()
            ]
            reviewer = review.user_id
            reviewer_name = reviewer.name if reviewer else 'Pembeli UniTrade'
            reviewer_initials = ''.join(
                part[:1].upper()
                for part in (reviewer_name or 'UT').split()
                if part
            )[:2] or 'UT'
            reviewer_image = (
                _safe_get(reviewer, 'avatar_128', False)
                or _safe_get(reviewer, 'image_128', False)
                or _safe_get(reviewer, 'image_1920', False)
                or _safe_get(reviewer.partner_id, 'avatar_128', False)
                or _safe_get(reviewer.partner_id, 'image_128', False)
                or _safe_get(reviewer.partner_id, 'image_1920', False)
            ) if reviewer else False
            items.append({
                'id': review.id,
                'rating': int(review.rating or 0),
                'comment': review.comment or '',
                'tags': tags,
                'images': images,
                'date_label': self._format_datetime_label(review.create_date),
                'reviewer_name': reviewer_name or 'Pembeli UniTrade',
                'reviewer_initials': reviewer_initials,
                'reviewer_avatar_url': image_data_uri(reviewer_image) if reviewer_image else '',
            })
        return {'summary': summary, 'items': items}

    def _seller_product_detail_payload(self, seller, product):
        status = self._seller_product_listing_status(seller, product)
        condition = self._seller_product_condition(product)
        currency = request.website.currency_id or request.env.company.currency_id
        price = product.list_price or 0.0
        discounted_price = product._unitrade_discounted_price() if hasattr(product, '_unitrade_discounted_price') else price
        discount_percent = _safe_get(product, 'x_discount_percent', 0.0) or 0.0
        stock_qty = self._seller_product_stock_qty(product)
        stock_label = int(stock_qty) if stock_qty.is_integer() else stock_qty
        _, unread_chat_count = self._seller_dashboard_chat_payloads(seller)
        pending_order_count = self._seller_dashboard_pending_order_count(seller)
        reviews = self._seller_product_reviews_payload(product)
        category = product.categ_id

        return {
            'seller': {
                'name': seller.name,
                'avatar_url': '/web/image/res.users/%s/avatar_128?unique=%s' % (
                    seller.user_id.id,
                    seller.user_id.write_date or '',
                ),
                'profile_url': '/seller-profile/%s' % self._seller_public_ref(seller),
            },
            'stats': {
                'notification_count': pending_order_count,
                'unread_chat_count': unread_chat_count,
            },
            'product': {
                'id': product.id,
                'name': product.name or 'Produk UniTrade',
                'product_code': product.default_code or ('UT%05d' % product.id),
                'category': category.name if category else 'Barang',
                'category_path': category.complete_name if category else 'Barang',
                'condition_key': condition['key'],
                'condition_label': condition['label'],
                'price': price,
                'price_label': self._format_money(price, currency),
                'discounted_price': discounted_price,
                'discounted_price_label': self._format_money(discounted_price, currency),
                'discount_percent': discount_percent,
                'has_discount': bool(discount_percent and discounted_price < price),
                'stock_qty': stock_qty,
                'stock_label': stock_label,
                'stock_text': self._stock_label(product),
                'description': product.description_sale or 'Belum ada deskripsi produk.',
                'location': _safe_get(product, 'x_seller_location', '') or _safe_get(product, 'x_item_district', '') or 'Lokasi belum diisi',
                'created_label': self._format_datetime_full_label(product.create_date),
                'updated_label': self._format_datetime_full_label(product.write_date),
                'image_url': self._seller_product_image_url(product),
                'images': self._seller_product_gallery_payload(product),
                'status': status,
                'listing_fee_label': self._format_money(_safe_get(product, 'x_listing_fee', 0.0), currency),
                'reviews': reviews,
                'actions': {
                    'products_url': '/unitrade/seller/products',
                    'edit_url': self._seller_product_edit_url(product) if status.get('record_active') else '',
                    'payment_url': status.get('payment_url') or '',
                    'public_url': status.get('public_url') or '',
                    'can_edit': bool(status.get('record_active')),
                    'can_continue_payment': bool(status.get('can_continue_payment')),
                    'can_view_shop': status.get('key') == 'active',
                    'new_product_url': self._seller_product_add_url(),
                },
            },
        }

    def _seller_product_detail_context(self, seller, product):
        payload = self._seller_product_detail_payload(seller, product)
        return {
            'page_title': 'Detail Barang',
            'seller': seller,
            'seller_public_ref': self._seller_public_ref(seller),
            'notification_count': payload['stats']['notification_count'],
            'unread_chat_count': payload['stats']['unread_chat_count'],
            'product_detail_payload_json': json.dumps(payload),
        }

    def _seller_product_create_context(self, seller):
        _, unread_chat_count = self._seller_dashboard_chat_payloads(seller)
        pending_order_count = self._seller_dashboard_pending_order_count(seller)
        payload = {
            'seller': {
                'name': seller.name,
                'avatar_url': '/web/image/res.users/%s/avatar_128?unique=%s' % (
                    seller.user_id.id,
                    seller.user_id.write_date or '',
                ),
                'profile_url': '/seller-profile/%s' % self._seller_public_ref(seller),
            },
            'stats': {
                'notification_count': pending_order_count,
                'unread_chat_count': unread_chat_count,
            },
            'categories': self._seller_product_categories(),
            'max_file_size': 5 * 1024 * 1024,
            'products_url': '/unitrade/seller/products',
            'dashboard_url': '/unitrade/seller/dashboard',
            'mode': 'create',
            'title': 'Tambah Barang',
            'subtitle': 'Lengkapi informasi barang sebelum dipublikasikan.',
            'submit_label': 'Posting',
            'data_url': '/unitrade/seller/products/new/data',
            'submit_url': '/unitrade/seller/products/create',
            'delete_url': '',
            'payment_url': '',
        }
        return {
            'page_title': 'Tambah Barang',
            'seller': seller,
            'seller_public_ref': self._seller_public_ref(seller),
            'notification_count': pending_order_count,
            'unread_chat_count': unread_chat_count,
            'product_create_payload_json': json.dumps(payload),
        }

    @staticmethod
    def _seller_listing_valid_until():
        config = request.env['ir.config_parameter'].sudo()
        try:
            days = int(float(config.get_param('unitrade.seller.listing_fee.validity_days', 30) or 30))
        except (TypeError, ValueError):
            days = 30
        return fields.Datetime.now() + timedelta(days=max(1, days))

    def _seller_listing_fee_policy(self, product_price, currency):
        config = request.env['ir.config_parameter'].sudo()
        try:
            price = max(0.0, float(product_price or 0.0))
        except (TypeError, ValueError):
            price = 0.0

        def get_amount(key, default):
            try:
                return currency.round(float(config.get_param(key, default) or default))
            except (TypeError, ValueError):
                return currency.round(float(default))

        threshold = get_amount('unitrade.seller.listing_fee.threshold', 1000000)
        low_fee = get_amount('unitrade.seller.listing_fee.low_amount', 2000)
        high_fee = get_amount('unitrade.seller.listing_fee.high_amount', 5000)
        enabled_raw = config.get_param('unitrade.seller.listing_fee.enabled', 'True')
        enabled = str(enabled_raw).strip().lower() not in ('false', '0', 'no', 'off')
        threshold_label = self._format_money(threshold, currency)
        if not enabled:
            return {
                'fee': currency.round(0.0),
                'percent': 0.0,
                'percent_label': 'Biaya tetap',
                'tier_label': 'Fee upload nonaktif',
                'enabled': False,
            }

        if price <= 0:
            fee = 0.0
            tier_label = 'Harga belum diisi'
        elif price < threshold:
            fee = low_fee
            tier_label = 'Harga < %s' % threshold_label
        else:
            fee = high_fee
            tier_label = 'Harga >= %s' % threshold_label

        return {
            'fee': currency.round(fee),
            'percent': 0.0,
            'percent_label': 'Biaya tetap',
            'tier_label': tier_label,
            'enabled': True,
        }

    def _seller_listing_fee_amounts(self, currency, product_price=0.0):
        config = request.env['ir.config_parameter'].sudo()
        policy = self._seller_listing_fee_policy(product_price, currency)

        def get_amount(key, default):
            try:
                return currency.round(float(config.get_param(key, default) or default))
            except (TypeError, ValueError):
                return currency.round(float(default))

        posting_fee = policy['fee']
        admin_fee = get_amount('unitrade.seller.posting_admin_fee', 0) if policy.get('enabled') else 0.0
        total = currency.round(posting_fee + admin_fee)
        return posting_fee, admin_fee, total, policy

    @staticmethod
    def _seller_ledger_effective_date(ledger):
        return (
            ledger.completed_at
            or ledger.released_at
            or _safe_get(ledger.order_id, 'x_completed_at')
            or ledger.order_id.date_order
            or ledger.create_date
        )

    def _filter_seller_ledgers_by_date(self, ledgers, date_start=False, date_end=False):
        if not date_start and not date_end:
            return ledgers
        return ledgers.filtered(lambda ledger: (
            (not date_start or (self._seller_ledger_effective_date(ledger) and self._seller_ledger_effective_date(ledger) >= date_start))
            and (not date_end or (self._seller_ledger_effective_date(ledger) and self._seller_ledger_effective_date(ledger) < date_end))
        ))

    def _seller_account_balance_debits(self, seller, currency):
        if 'unitrade.payment.intent' not in request.env.registry:
            return currency.round(0.0)
        PaymentIntent = request.env['unitrade.payment.intent'].sudo()
        domain = [
            ('seller_id', '=', seller.id),
            ('intent_type', '=', 'listing_fee'),
            ('state', '=', 'paid'),
            ('payment_method_code', '=', 'account_balance'),
        ]
        if 'currency_id' in PaymentIntent._fields:
            domain.append(('currency_id', '=', currency.id))
        intents = PaymentIntent.search(domain)
        return currency.round(sum(intents.mapped('amount')))

    def _seller_balance_summary(self, seller, currency, date_start=False, date_end=False):
        empty = {
            'total_revenue': currency.round(0.0),
            'available_balance': currency.round(0.0),
            'payoutable_balance': currency.round(0.0),
            'held_balance': currency.round(0.0),
            'pending_payout': currency.round(0.0),
            'released_balance': currency.round(0.0),
            'used_balance': currency.round(0.0),
            'revenue_ledger_count': 0,
            'payoutable_ledger_count': 0,
        }
        if 'unitrade.escrow.ledger' not in request.env.registry:
            return empty

        Ledger = request.env['unitrade.escrow.ledger'].sudo()
        earned_ledgers = self._seller_valid_balance_ledgers(seller)
        display_ledgers = self._filter_seller_ledgers_by_date(
            earned_ledgers.filtered(lambda ledger: ledger.state in ('releasable', 'released')),
            date_start=date_start,
            date_end=date_end,
        )
        payoutable_ledgers = earned_ledgers.filtered(lambda ledger: self._seller_ledger_is_payoutable(ledger))
        held_ledgers = earned_ledgers.filtered(lambda ledger: self._seller_ledger_is_held_balance(ledger))
        pending_ledgers = earned_ledgers.filtered(lambda ledger: ledger.payout_status in ('pending', 'processing'))
        released_ledgers = earned_ledgers.filtered(lambda ledger: ledger.state == 'released' or ledger.payout_status == 'succeeded')
        used_balance = self._seller_account_balance_debits(seller, currency)
        payoutable_balance = currency.round(sum(payoutable_ledgers.mapped('amount_seller')))
        available_balance = currency.round(max(0.0, payoutable_balance - used_balance))

        return {
            'total_revenue': currency.round(sum(display_ledgers.mapped('amount_seller'))),
            'available_balance': available_balance,
            'payoutable_balance': payoutable_balance,
            'held_balance': currency.round(sum(held_ledgers.mapped('amount_seller'))),
            'pending_payout': currency.round(sum(pending_ledgers.mapped('amount_seller'))),
            'released_balance': currency.round(sum(released_ledgers.mapped('amount_seller'))),
            'used_balance': used_balance,
            'revenue_ledger_count': len(display_ledgers),
            'payoutable_ledger_count': len(payoutable_ledgers),
        }

    def _seller_payout_release_hours(self):
        raw_hours = request.env['ir.config_parameter'].sudo().get_param(
            'unitrade.seller.payout_release_hours',
            default='24',
        )
        try:
            hours = int(float(raw_hours or 24))
        except (TypeError, ValueError):
            hours = 24
        return max(0, min(hours, 24 * 7))

    def _seller_auto_confirm_hours(self):
        raw_hours = request.env['ir.config_parameter'].sudo().get_param(
            'unitrade.escrow.auto_confirm_receipt_hours',
            default='48',
        )
        try:
            hours = int(float(raw_hours or 48))
        except (TypeError, ValueError):
            hours = 48
        return max(1, min(hours, 24 * 14))

    def _seller_valid_balance_ledgers(self, seller):
        if 'unitrade.escrow.ledger' not in request.env.registry:
            return request.env['sale.order'].browse()
        Ledger = request.env['unitrade.escrow.ledger'].sudo()
        ledgers = Ledger.search([
            ('seller_id', '=', seller.id),
            ('state', 'in', ['held', 'releasable', 'released']),
        ])
        if 'x_payment_status' in request.env['sale.order']._fields:
            ledgers = ledgers.filtered(lambda ledger: ledger.order_id.x_payment_status == 'paid')
        return ledgers.filtered(
            lambda ledger: ledger.order_id.state in ('sale', 'done') and (ledger.amount_seller or 0.0) > 0
        )

    def _seller_payout_release_at(self, ledger):
        completed_at = ledger.completed_at or ledger.buyer_confirmed_at
        if not completed_at:
            return False
        return completed_at + timedelta(hours=self._seller_payout_release_hours())

    def _seller_ledger_is_payoutable(self, ledger, now=False):
        now = now or fields.Datetime.now()
        release_at = self._seller_payout_release_at(ledger)
        return bool(
            ledger.state == 'releasable'
            and ledger.payout_status not in ('pending', 'processing', 'succeeded')
            and release_at
            and release_at <= now
        )

    def _seller_ledger_is_held_balance(self, ledger, now=False):
        now = now or fields.Datetime.now()
        if ledger.payout_status in ('pending', 'processing', 'succeeded'):
            return False
        if ledger.state == 'held':
            return True
        release_at = self._seller_payout_release_at(ledger)
        return bool(ledger.state == 'releasable' and release_at and release_at > now)

    def _seller_available_balance(self, seller, currency):
        return self._seller_balance_summary(seller, currency)['available_balance']

    def _seller_product_payment_methods(self, balance, total, currency):
        return [
            {
                'key': 'qris',
                'title': 'QRIS',
                'subtitle': 'Pindai QR dari aplikasi pembayaran',
                'speed': 'Instan',
                'icon': 'fa fa-qrcode',
                'description': 'Kode QRIS akan dibuat setelah Anda menekan Bayar.',
                'channels': [
                    {'key': 'qris', 'name': 'QRIS', 'logo': '/unitrade_theme/static/src/img/payment/qris.svg'},
                ],
            },
            {
                'key': 'ewallet',
                'title': 'E-Wallet',
                'subtitle': 'Pilih dompet digital',
                'speed': 'Instan',
                'icon': 'fa fa-mobile',
                'description': 'Pilih e-wallet yang tersedia. Pembayaran diproses sebagai transaksi instan.',
                'channels': [
                    {'key': 'gopay', 'name': 'GoPay', 'logo': '/unitrade_theme/static/src/img/payment/gopay.svg'},
                    {'key': 'shopeepay', 'name': 'ShopeePay', 'logo': '/unitrade_theme/static/src/img/payment/shopeepay.svg'},
                ],
            },
            {
                'key': 'virtual_account',
                'title': 'Virtual Account',
                'subtitle': 'Pilih channel virtual account',
                'speed': 'Verifikasi otomatis',
                'icon': 'fa fa-credit-card',
                'description': 'Nomor virtual account dibuat otomatis dan dapat dibayar dari mobile banking.',
                'channels': [
                    {'key': 'bca_va', 'name': 'BCA VA', 'logo': '/unitrade_theme/static/src/img/payment/bca.svg'},
                    {'key': 'mandiri_bill', 'name': 'Mandiri Bill', 'logo': '/unitrade_theme/static/src/img/payment/mandiri.svg'},
                    {'key': 'bni_va', 'name': 'BNI VA', 'logo': '/unitrade_theme/static/src/img/payment/bni.svg'},
                    {'key': 'bri_va', 'name': 'BRI VA', 'logo': '/unitrade_theme/static/src/img/payment/bri.svg'},
                    {'key': 'permata_va', 'name': 'Permata VA', 'logo': '/unitrade_theme/static/src/img/payment/permata.svg'},
                    {'key': 'cimb_va', 'name': 'CIMB VA', 'logo': '/unitrade_theme/static/src/img/payment/cimb.svg'},
                ],
            },
            {
                'key': 'account_balance',
                'title': 'Saldo Akun',
                'subtitle': '%s tersedia' % self._format_money(balance, currency),
                'speed': 'Instan',
                'icon': 'fa fa-id-card-o',
                'description': 'Pembayaran akan memotong saldo akun UniTrade Anda.',
                'channels': [
                    {'key': 'account_balance', 'name': 'Gunakan Saldo Akun', 'logo': ''},
                ],
                'insufficient': balance < total,
            },
        ]

    def _seller_product_payment_payload(self, seller, product):
        currency = request.website.currency_id or request.env.company.currency_id
        category_name = product.categ_id.name if product.categ_id else 'Barang'
        price = product._unitrade_discounted_price() if hasattr(product, '_unitrade_discounted_price') else product.list_price
        posting_fee, admin_fee, total, fee_policy = self._seller_listing_fee_amounts(currency, price)
        balance = self._seller_available_balance(seller, currency)
        _, unread_chat_count = self._seller_dashboard_chat_payloads(seller)
        pending_order_count = self._seller_dashboard_pending_order_count(seller)
        existing_intent = request.env['unitrade.payment.intent'].sudo().search([
            ('intent_type', '=', 'listing_fee'),
            ('product_template_id', '=', product.id),
            ('seller_id', '=', seller.id),
            ('state', 'in', ['draft', 'pending']),
        ], order='create_date desc', limit=1) if 'unitrade.payment.intent' in request.env.registry else request.env['product.template'].browse()

        return {
            'seller': {
                'name': seller.name,
                'avatar_url': '/web/image/res.users/%s/avatar_128?unique=%s' % (
                    seller.user_id.id,
                    seller.user_id.write_date or '',
                ),
                'profile_url': '/seller-profile/%s' % self._seller_public_ref(seller),
            },
            'stats': {
                'notification_count': pending_order_count,
                'unread_chat_count': unread_chat_count,
            },
            'product': {
                'id': product.id,
                'name': product.name or 'Produk UniTrade',
                'category': category_name,
                'price': price or 0.0,
                'price_label': self._format_money(price, currency),
                'image_url': self._seller_product_image_url(product),
                'products_url': '/unitrade/seller/products',
            },
            'fees': {
                'posting_fee': posting_fee,
                'posting_fee_label': self._format_money(posting_fee, currency),
                'admin_fee': admin_fee,
                'admin_fee_label': self._format_money(admin_fee, currency),
                'total': total,
                'total_label': self._format_money(total, currency),
                'balance': balance,
                'balance_label': self._format_money(balance, currency),
                'tier_label': fee_policy['tier_label'],
                'percent_label': fee_policy['percent_label'],
            },
            'methods': self._seller_product_payment_methods(balance, total, currency),
            'submit_url': '/unitrade/seller/products/%s/payment/submit' % product.id,
            'data_url': '/unitrade/seller/products/%s/payment/data' % product.id,
            'existing_intent': {
                'id': existing_intent.id if existing_intent else 0,
                'state': existing_intent.state if existing_intent else '',
                'method': existing_intent.payment_method_label if existing_intent else '',
                'reference': existing_intent.payment_reference if existing_intent else '',
            },
        }

    def _seller_product_payment_context(self, seller, product):
        payload = self._seller_product_payment_payload(seller, product)
        return {
            'page_title': 'Tambah Barang - Pembayaran',
            'seller': seller,
            'seller_public_ref': self._seller_public_ref(seller),
            'notification_count': payload['stats']['notification_count'],
            'unread_chat_count': payload['stats']['unread_chat_count'],
            'product_payment_payload_json': json.dumps(payload),
        }

    @staticmethod
    def _store_slug(value):
        slug = re.sub(r'[^a-z0-9-]+', '-', (value or '').strip().lower())
        slug = re.sub(r'-+', '-', slug).strip('-')
        return slug[:80]

    @staticmethod
    def _address_label_text(label):
        return {
            'home': 'Rumah',
            'office': 'Kantor',
            'school': 'Sekolah',
            'other': 'Lainnya',
        }.get(label or 'home', 'Rumah')

    def _partner_address_payload(self, partner):
        if not partner:
            return {
                'has_address': False,
                'label': 'Rumah',
                'line': '',
                'coordinates': '',
            }
        province = _safe_get(partner, 'x_unitrade_province') or (partner.state_id.name if partner.state_id else '')
        city = _safe_get(partner, 'x_unitrade_city') or partner.city or ''
        district = _safe_get(partner, 'x_unitrade_district') or ''
        village = _safe_get(partner, 'x_unitrade_village') or ''
        label_key = _safe_get(partner, 'x_unitrade_address_label') or 'home'
        label = self._address_label_text(label_key)
        latitude = _safe_get(partner, 'x_unitrade_latitude', 0.0) or 0.0
        longitude = _safe_get(partner, 'x_unitrade_longitude', 0.0) or 0.0
        parts = [
            partner.street or '',
            partner.street2 or '',
            village,
            district,
            city,
            province,
            partner.zip or '',
        ]
        line = ', '.join(part for part in parts if part)
        has_address = bool(partner.street and city and partner.zip)
        return {
            'has_address': has_address,
            'label': label,
            'label_key': label_key,
            'line': line,
            'province': province,
            'city': city,
            'district': district,
            'village': village,
            'zip': partner.zip or '',
            'street': partner.street or '',
            'street2': partner.street2 or '',
            'detail': ', '.join(part for part in [partner.street or '', partner.street2 or '', village, district] if part),
            'latitude': latitude or -7.7956,
            'longitude': longitude or 110.3695,
            'place_id': _safe_get(partner, 'x_unitrade_mapbox_place_id') or '',
            'coordinates': '%.6f, %.6f' % (latitude, longitude) if has_address and latitude and longitude else '',
        }

    def _seller_settings_payload(self, seller):
        _, unread_chat_count = self._seller_dashboard_chat_payloads(seller)
        pending_order_count = self._seller_dashboard_pending_order_count(seller)
        partner = seller.partner_id
        address = self._partner_address_payload(partner)
        province = address['province'] or _safe_get(seller, 'x_store_province') or ''
        city = address['city'] or _safe_get(seller, 'x_store_city') or ''
        address_detail = address['detail'] or _safe_get(seller, 'x_store_address_detail') or seller.x_profile_address or ''
        slug = _safe_get(seller, 'x_store_slug') or self._store_slug(seller.name or seller.user_id.login or ('seller-%s' % seller.id))
        return {
            'seller': {
                'name': seller.name,
                'avatar_url': '/web/image/res.users/%s/avatar_128?unique=%s' % (
                    seller.user_id.id,
                    seller.user_id.write_date or '',
                ),
                'profile_url': '/seller-profile/%s' % self._seller_public_ref(seller),
            },
            'stats': {
                'notification_count': pending_order_count,
                'unread_chat_count': unread_chat_count,
            },
            'settings': {
                'store_url_base': 'unitrade.my.id/',
                'slug': slug,
                'description': seller.x_profile_description or '',
                'phone': _safe_get(seller.user_id, 'x_whatsapp') or (partner.phone if partner else '') or '',
                'province': province,
                'city': city,
                'address_detail': address_detail,
                'address_summary': address,
                'bank_name': _safe_get(seller, 'x_payout_channel_code') or '',
                'account_number': _safe_get(seller, 'x_payout_account_number') or '',
                'account_name': _safe_get(seller, 'x_payout_account_name') or '',
                'store_active': bool(_safe_get(seller, 'x_store_active', True)),
                'chat_enabled': bool(_safe_get(seller, 'x_chat_enabled', True)),
                'delete_requested': bool(_safe_get(seller, 'x_delete_requested', False)),
            },
            'bank_options': self._seller_payout_bank_options(seller),
            'data_url': '/unitrade/seller/settings/data',
            'update_url': '/unitrade/seller/settings/update',
            'profile_address_url': '/my/account?redirect=/unitrade/seller/settings',
            'close_url': '/unitrade/seller/settings/close-store',
            'delete_request_url': '/unitrade/seller/settings/request-delete',
        }

    def _seller_settings_context(self, seller):
        payload = self._seller_settings_payload(seller)
        return {
            'page_title': 'Pengaturan Toko',
            'seller': seller,
            'seller_public_ref': self._seller_public_ref(seller),
            'notification_count': payload['stats']['notification_count'],
            'unread_chat_count': payload['stats']['unread_chat_count'],
            'seller_settings_payload_json': json.dumps(payload),
        }

    def _sync_seller_settings(self, seller, values):
        slug = self._store_slug(values.get('slug'))
        if not slug:
            raise ValueError('Tautan toko wajib diisi.')
        duplicate = request.env['unitrade.seller'].sudo().search([
            ('x_store_slug', '=', slug),
            ('id', '!=', seller.id),
        ], limit=1)
        if duplicate:
            raise ValueError('Tautan toko sudah dipakai penjual lain.')

        description = (values.get('description') or '').strip()
        if len(description) > 1000:
            raise ValueError('Deskripsi / catatan toko maksimal 1000 karakter.')

        province = (values.get('province') if values.get('province') is not None else _safe_get(seller, 'x_store_province') or '').strip()
        city = (values.get('city') if values.get('city') is not None else _safe_get(seller, 'x_store_city') or '').strip()
        address_detail = (values.get('address_detail') if values.get('address_detail') is not None else _safe_get(seller, 'x_store_address_detail') or '').strip()
        phone = re.sub(r'[\s-]+', '', (values.get('phone') or '').strip())
        if phone and not re.match(r'^(\+62|62|08)[0-9]{8,13}$', phone):
            raise ValueError('Nomor telepon/WA harus diawali 08, 62, atau +62 dan berisi 10-15 digit.')

        partner = seller.partner_id
        address = self._partner_address_payload(partner)
        using_profile_address = bool(address.get('has_address'))
        if using_profile_address:
            province = address.get('province') or province
            city = address.get('city') or city
            address_detail = address.get('detail') or address.get('line') or address_detail

        seller_values = {
            'x_store_slug': slug,
            'x_profile_description': description,
            'x_store_province': province,
            'x_store_city': city,
            'x_store_address_detail': address_detail,
            'x_profile_address': ', '.join([part for part in [address_detail, city, province] if part]),
            'x_payout_channel_code': values.get('bank_name') or False,
            'x_payout_account_number': (values.get('account_number') or '').strip(),
            'x_payout_account_name': (values.get('account_name') or '').strip(),
            'x_store_active': bool(values.get('store_active', True)),
            'x_chat_enabled': bool(values.get('chat_enabled', True)),
        }
        seller.write(seller_values)

        partner_values = {}
        if partner and phone != (partner.phone or ''):
            partner_values['phone'] = phone or False
        if not using_profile_address:
            if address_detail:
                partner_values['street'] = address_detail
            if city:
                partner_values['city'] = city
            if province:
                state = request.env['res.country.state'].sudo().search([('name', 'ilike', province)], limit=1)
                if state:
                    partner_values['state_id'] = state.id
        if partner_values and seller.partner_id:
            seller.partner_id.sudo().write(partner_values)
        if 'x_whatsapp' in seller.user_id._fields and phone != (seller.user_id.x_whatsapp or ''):
            seller.user_id.sudo().write({'x_whatsapp': phone or False})
        return seller

    def _seller_payout_bank_options(self, seller=False):
        options = [{'value': '', 'label': 'Pilih bank'}]
        selection = []
        try:
            seller_model = seller or request.env['unitrade.seller']
            selection = seller_model._fields['x_payout_channel_code'].selection
            if callable(selection):
                selection = selection(seller_model)
        except Exception:
            selection = [
                ('ID_BCA', 'BCA'),
                ('ID_MANDIRI', 'Mandiri'),
                ('ID_BNI', 'BNI'),
                ('ID_BRI', 'BRI'),
                ('OVO', 'OVO'),
                ('DANA', 'DANA'),
            ]
        seen = {''}
        for value, label in selection or []:
            if value in seen:
                continue
            seen.add(value)
            options.append({'value': value, 'label': label})
        return options

    def _seller_product_for_edit(self, seller, product_id):
        product = request.env['product.template'].with_context(active_test=False).sudo().browse(int(product_id or 0)).exists()
        if not product or (_safe_get(product, 'x_seller_id') and _safe_get(product, 'x_seller_id').id) != seller.id:
            return request.env['product.template'].browse()
        return product

    def _seller_product_for_detail(self, seller, product_id):
        product = request.env['product.template'].with_context(active_test=False).sudo().browse(int(product_id or 0)).exists()
        if not product or (_safe_get(product, 'x_seller_id') and _safe_get(product, 'x_seller_id').id) != seller.id:
            return request.env['product.template'].browse()
        return product

    def _seller_product_form_image_payloads(self, product):
        images = []
        if product.image_1920:
            images.append({
                'id': 'main-%s' % product.id,
                'source': 'main',
                'name': 'Gambar utama',
                'shortName': 'Gambar utama',
                'size': 0,
                'sizeLabel': 'Tersimpan',
                'mimetype': 'image/jpeg',
                'url': '/web/image/product.template/%s/image_256?unique=%s' % (
                    product.id,
                    product.write_date or '',
                ),
                'existing': True,
            })
        for image in product.product_template_image_ids.filtered('image_1920')[:3]:
            images.append({
                'id': 'image-%s' % image.id,
                'source': 'product.image:%s' % image.id,
                'name': image.name or 'Gambar produk',
                'shortName': image.name or 'Gambar produk',
                'size': 0,
                'sizeLabel': 'Tersimpan',
                'mimetype': 'image/jpeg',
                'url': '/web/image/product.image/%s/image_256?unique=%s' % (
                    image.id,
                    image.write_date or '',
                ),
                'existing': True,
            })
        return images[:4]

    def _seller_product_form_payload(self, seller, product):
        discount_percent = _safe_get(product, 'x_discount_percent', 0.0) or 0.0
        discount_price = 0.0
        if discount_percent and product.list_price:
            discount_price = max(0.0, product.list_price * (1 - (discount_percent / 100.0)))
        stock = _safe_get(product, 'x_unitrade_stock_qty', 0.0)
        try:
            stock = float(stock or 0.0)
        except (TypeError, ValueError):
            stock = 0.0
        return {
            'id': product.id,
            'name': product.name or '',
            'description': product.description_sale or '',
            'category_id': product.categ_id.id if product.categ_id else 0,
            'condition': _safe_get(product, 'x_condition', 'used') or 'used',
            'price': product.list_price or 0.0,
            'discount_percent': discount_percent,
            'discount_price': discount_price,
            'stock': stock,
            'images': self._seller_product_form_image_payloads(product),
        }

    def _seller_product_edit_context(self, seller, product):
        values = self._seller_product_create_context(seller)
        payload = json.loads(values['product_create_payload_json'])
        payload.update({
            'mode': 'edit',
            'title': 'Edit Barang',
            'subtitle': 'Ubah isi informasi mengenai barang',
            'submit_label': 'Simpan',
            'delete_label': 'Hapus',
            'product_id': product.id,
            'product': self._seller_product_form_payload(seller, product),
            'data_url': '/unitrade/seller/products/%s/edit/data' % product.id,
            'submit_url': '/unitrade/seller/products/%s/update' % product.id,
            'delete_url': '/unitrade/seller/products/%s/delete' % product.id,
        })
        values.update({
            'page_title': 'Edit Barang',
            'product': product,
            'product_create_payload_json': json.dumps(payload),
        })
        return values

    @staticmethod
    def _seller_default_district(seller):
        location = ' '.join([
            seller.partner_id.city or '',
            seller.partner_id.state_id.name or '',
            seller.x_profile_location or '',
        ]).lower()
        mapping = {
            'yogyakarta': 'yogyakarta',
            'sleman': 'sleman',
            'bantul': 'bantul',
            'kulon': 'kulon_progo',
            'gunungkidul': 'gunungkidul',
        }
        for needle, district in mapping.items():
            if needle in location:
                return district
        return 'sleman'

    @staticmethod
    def _decode_product_image_payload(image, index=1):
        allowed_mimetypes = {
            'image/png',
            'image/jpg',
            'image/jpeg',
            'image/webp',
        }
        max_size = 5 * 1024 * 1024
        name = (image.get('name') or 'produk-%s.jpg' % index).rsplit('\\', 1)[-1].rsplit('/', 1)[-1]
        mimetype = (image.get('mimetype') or '').lower()
        size = int(image.get('size') or 0)
        raw_data = image.get('data') or ''
        if ',' in raw_data and raw_data.startswith('data:'):
            raw_data = raw_data.split(',', 1)[1]
        if mimetype not in allowed_mimetypes:
            raise ValueError('Format foto %s tidak didukung. Gunakan PNG, JPG, JPEG, atau WEBP.' % name)
        try:
            binary = base64.b64decode(raw_data, validate=True)
        except Exception as error:
            raise ValueError('File %s tidak valid.' % name) from error
        if not binary:
            raise ValueError('File %s kosong.' % name)
        actual_size = len(binary)
        if size > max_size or actual_size > max_size:
            raise ValueError('Ukuran foto %s melebihi 5MB.' % name)
        return {
            'name': name,
            'mimetype': mimetype,
            'datas': base64.b64encode(binary).decode('ascii'),
        }

    @classmethod
    def _clean_product_image_payloads(cls, images):
        cleaned = []
        if not isinstance(images, list):
            raise ValueError('Foto produk wajib diupload.')
        if len(images) < 2 or len(images) > 4:
            raise ValueError('Foto produk wajib minimal 2 gambar dan maksimal 4 gambar.')

        for index, image in enumerate(images, start=1):
            cleaned.append(cls._decode_product_image_payload(image, index))
        return cleaned

    def _seller_product_existing_image(self, product, source):
        source = source or ''
        if source == 'main':
            if not product.image_1920:
                raise ValueError('Gambar produk lama tidak ditemukan.')
            return {
                'name': 'Gambar utama',
                'mimetype': 'image/jpeg',
                'datas': product.image_1920.decode('ascii') if isinstance(product.image_1920, bytes) else product.image_1920,
            }
        if source.startswith('product.image:'):
            image_id = int(source.split(':', 1)[1] or 0)
            image = product.product_template_image_ids.filtered(lambda item: item.id == image_id)[:1]
            if not image or not image.image_1920:
                raise ValueError('Gambar produk lama tidak ditemukan.')
            return {
                'name': image.name or 'Gambar produk',
                'mimetype': 'image/jpeg',
                'datas': image.image_1920.decode('ascii') if isinstance(image.image_1920, bytes) else image.image_1920,
            }
        raise ValueError('Referensi gambar produk tidak valid.')

    def _clean_product_edit_image_payloads(self, product, images):
        if not isinstance(images, list):
            raise ValueError('Foto produk wajib diupload.')
        if len(images) < 2 or len(images) > 4:
            raise ValueError('Foto produk wajib minimal 2 gambar dan maksimal 4 gambar.')

        cleaned = []
        new_images = []
        new_indexes = []
        for index, image in enumerate(images):
            if image.get('existing'):
                cleaned.append(self._seller_product_existing_image(product, image.get('source')))
            else:
                cleaned.append(None)
                new_images.append(image)
                new_indexes.append(index)

        if new_images:
            decoded_images = [
                self._decode_product_image_payload(image, index)
                for index, image in enumerate(new_images, start=1)
            ]
            for index, decoded in zip(new_indexes, decoded_images):
                cleaned[index] = decoded
        return cleaned

    @staticmethod
    def _seller_product_discount_percent(payload, price=0.0):
        raw_percent = payload.get('discount_percent')
        if raw_percent not in (None, ''):
            try:
                discount_percent = float(raw_percent or 0.0)
            except (TypeError, ValueError) as error:
                raise ValueError('Diskon harus berupa angka persen.') from error
            if discount_percent < 0:
                raise ValueError('Diskon tidak boleh negatif.')
            if discount_percent > 100:
                raise ValueError('Diskon maksimal 100%.')
            return max(0.0, min(100.0, discount_percent))

        discount_price_raw = payload.get('discount_price')
        try:
            discount_price = float(discount_price_raw or 0.0)
        except (TypeError, ValueError) as error:
            raise ValueError('Harga diskon harus berupa angka.') from error
        if discount_price < 0:
            raise ValueError('Harga diskon tidak boleh negatif.')
        if discount_price and discount_price >= price:
            raise ValueError('Harga diskon harus lebih kecil dari harga normal.')
        if discount_price and price:
            return max(0.0, min(100.0, (price - discount_price) / price * 100.0))
        return 0.0

    @staticmethod
    def _seller_product_payload_condition(payload):
        condition = (payload.get('condition') or payload.get('x_condition') or 'used')
        condition = str(condition).strip()
        if condition not in ('new', 'used'):
            raise ValueError('Kondisi barang harus Baru atau Bekas.')
        return condition

    def _create_seller_product(self, seller, payload):
        name = (payload.get('name') or '').strip()
        description = (payload.get('description') or '').strip()
        category_id = int(payload.get('category_id') or 0)
        price = float(payload.get('price') or 0)
        discount_percent = self._seller_product_discount_percent(payload, price)
        stock = float(payload.get('stock') or 0)
        condition = self._seller_product_payload_condition(payload)
        images = self._clean_product_image_payloads(payload.get('images') or [])

        if not name:
            raise ValueError('Nama produk wajib diisi.')
        if not description:
            raise ValueError('Deskripsi produk wajib diisi.')
        if not category_id:
            raise ValueError('Kategori produk wajib dipilih.')
        if price < 0:
            raise ValueError('Harga tidak boleh negatif.')
        if stock < 0:
            raise ValueError('Stok produk tidak boleh negatif.')

        allowed_categories = self._seller_home_category_records()
        category = allowed_categories.filtered(lambda item: item.id == category_id)[:1]
        if not category:
            raise ValueError('Kategori produk harus sesuai kategori UniTrade.')

        Product = request.env['product.template'].sudo()
        ProductImage = request.env['product.image'].sudo()
        Attachment = request.env['ir.attachment'].sudo()

        district = self._seller_default_district(seller)
        seller_location = self._seller_address(seller)
        product_values = {
            'name': name,
            'description_sale': description,
            'list_price': price,
            'categ_id': category.id,
            'sale_ok': False,
            'website_published': False,
            'image_1920': images[0]['datas'],
            'x_seller_id': seller.id,
            'x_seller_location': seller_location,
            'x_item_province': 'diy',
            'x_item_district': district,
            'x_condition': condition,
            'x_discount_percent': discount_percent,
        }
        if 'company_id' in Product._fields:
            product_values['company_id'] = False
        product_values.update(self._seller_product_type_values(Product._fields))
        if 'allow_out_of_stock_order' in Product._fields:
            product_values['allow_out_of_stock_order'] = False

        product = Product.create(product_values)
        for image in images[1:]:
            ProductImage.create({
                'name': image['name'],
                'product_tmpl_id': product.id,
                'image_1920': image['datas'],
            })
        for image in images:
            Attachment.create({
                'name': image['name'],
                'datas': image['datas'],
                'mimetype': image['mimetype'],
                'res_model': 'product.template',
                'res_id': product.id,
            })
        marketplace_values = {'x_is_marketplace': True}
        marketplace_values.update(self._seller_product_type_values(Product._fields))
        product.write(marketplace_values)
        self._seller_product_update_stock(product, stock)

        _logger.info('Seller %s created UniTrade product %s', seller.id, product.id)
        return product

    def _update_seller_product(self, seller, product, payload):
        product = product.sudo()
        name = (payload.get('name') or '').strip()
        description = (payload.get('description') or '').strip()
        category_id = int(payload.get('category_id') or 0)
        price = float(payload.get('price') or 0)
        discount_percent = self._seller_product_discount_percent(payload, price)
        stock = float(payload.get('stock') or 0)
        condition = self._seller_product_payload_condition(payload)
        images = self._clean_product_edit_image_payloads(product, payload.get('images') or [])

        if not name:
            raise ValueError('Nama produk wajib diisi.')
        if not description:
            raise ValueError('Deskripsi produk wajib diisi.')
        if not category_id:
            raise ValueError('Kategori produk wajib dipilih.')
        if price < 0:
            raise ValueError('Harga tidak boleh negatif.')
        if stock < 0:
            raise ValueError('Stok produk tidak boleh negatif.')

        allowed_categories = self._seller_home_category_records()
        category = allowed_categories.filtered(lambda item: item.id == category_id)[:1]
        if not category:
            raise ValueError('Kategori produk harus sesuai kategori UniTrade.')

        was_marketplace = bool(_safe_get(product, 'x_is_marketplace', False))
        should_be_active = bool(was_marketplace and self._seller_product_should_be_active(product))
        product_guard = product.with_context(
            unitrade_skip_marketplace_validation=True,
            unitrade_preserve_product_type=True,
        ).sudo()
        product_guard.product_template_image_ids.unlink()
        product_values = {
            'name': name,
            'description_sale': description,
            'list_price': price,
            'categ_id': category.id,
            'image_1920': images[0]['datas'],
            'sale_ok': should_be_active,
            'website_published': should_be_active,
            'x_is_marketplace': was_marketplace,
            'x_condition': condition,
            'x_discount_percent': discount_percent,
        }
        if 'company_id' in product._fields:
            product_values['company_id'] = False
        product_values.update(self._seller_product_type_values(product._fields))
        if 'allow_out_of_stock_order' in product._fields:
            product_values['allow_out_of_stock_order'] = False
        product_guard.write(product_values)
        ProductImage = product_guard.env['product.image'].sudo().with_context(unitrade_skip_marketplace_validation=True)
        for image in images[1:]:
            ProductImage.create({
                'name': image['name'],
                'product_tmpl_id': product.id,
                'image_1920': image['datas'],
            })
        if was_marketplace:
            product.with_context(unitrade_preserve_product_type=True)._check_unitrade_required_product_data()
        self._seller_product_update_stock(product, stock)

        _logger.info('Seller %s updated UniTrade product %s', seller.id, product.id)
        return product

    @staticmethod
    def _archive_seller_product(product):
        values = {
            'website_published': False,
            'sale_ok': False,
        }
        if 'active' in product._fields:
            values['active'] = False
        product.write(values)
>>>>>>> ca9bf47 (feat : admin fajar anjay sadboy)

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
        if self._current_user_block_message(_('membuka profil seller')):
            return request.redirect('/my/profile?unitrade_blocked=1')
        seller = request.env['unitrade.seller'].sudo().search([
            ('user_id', '=', request.env.uid),
            ('status', '=', 'verified'),
        ], limit=1)
        if not seller:
            return request.redirect('/seller-onboarding')
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
        if self._current_user_block_message(_('menghubungi seller')):
            return request.redirect('/seller-profile/%s?chat=blocked' % self._seller_public_ref(seller))

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
        if self._current_user_block_message(_('melaporkan seller')):
            return request.redirect('/seller-profile/%s?report_error=account_blocked' % self._seller_public_ref(seller))

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
        seller.sudo().write({
            'report_state': 'reported',
            'report_count': seller.report_count + 1,
            'last_reported_at': fields.Datetime.now(),
            'last_report_reason': reason,
        })
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
        """Keep the old seller URL as an alias for the onboarding flow."""
        if self._current_user_block_message(_('mendaftar sebagai seller')):
            return request.redirect('/my/profile?unitrade_blocked=1')
        return request.redirect('/seller-onboarding')

    @http.route('/unitrade/seller/register/submit', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def seller_register_submit(self, **kwargs):
        """Keep the old submit URL from creating a second verification path."""
        if self._current_user_block_message(_('mendaftar sebagai seller')):
            return request.redirect('/my/profile?unitrade_blocked=1')
        return request.redirect('/seller-onboarding')

    @http.route([
        '/unitrade/seller/dashboard',
        '/seller/dashboard',
        '/my/seller/dashboard',
    ], type='http', auth='user', website=True, sitemap=False)
    def seller_dashboard(self, **kwargs):
        """Render the standalone seller dashboard app shell."""
        seller = self._dashboard_seller()
        if not seller:
            return request.redirect('/seller-onboarding')

        return request.render(
            'unitrade_seller.seller_dashboard_template',
            self._seller_dashboard_context(seller),
        )

<<<<<<< HEAD
=======
    @http.route('/unitrade/seller/dashboard/data', type='json', auth='user', website=True, methods=['POST'])
    def seller_dashboard_data(self, **kwargs):
        """Return seller dashboard data filtered by the requested local date."""
        seller = self._dashboard_seller()
        if not seller:
            return {
                'success': False,
                'message': self._seller_not_ready_message(),
            }

        context = self._seller_dashboard_context(
            seller,
            selected_date=kwargs.get('date'),
            date_mode=kwargs.get('date_mode'),
            orders_period=kwargs.get('orders_period'),
        )
        payload = json.loads(context['dashboard_payload_json'])
        payload['success'] = True
        return payload

    @http.route([
        '/unitrade/seller/payouts',
        '/unitrade/seller/payout',
        '/seller/payouts',
        '/my/seller/payouts',
    ], type='http', auth='user', website=True, sitemap=False)
    def seller_payouts(self, **kwargs):
        """Render seller payout dashboard page."""
        seller = self._dashboard_seller()
        if not seller:
            return self._seller_not_ready_redirect()
        return request.render(
            'unitrade_seller.seller_payouts_template',
            self._seller_payout_context(seller),
        )

    @http.route('/unitrade/seller/payouts/data', type='json', auth='user', website=True, methods=['POST'])
    def seller_payouts_data(self, **kwargs):
        seller = self._dashboard_seller()
        if not seller:
            return {
                'success': False,
                'message': self._seller_not_ready_message(),
            }
        payload = self._seller_payout_context_payload(seller)
        payload['success'] = True
        return payload

    @http.route('/unitrade/seller/payout/account/save', type='json', auth='user', website=True, methods=['POST'])
    def seller_payout_account_save(self, **kwargs):
        seller = self._dashboard_seller(active_only=False)
        if not seller:
            return {
                'success': False,
                'message': 'Akun penjual belum ditemukan.',
            }

        bank_name = (kwargs.get('bank_name') or '').strip()
        account_number = (kwargs.get('account_number') or '').strip()
        account_name = (kwargs.get('account_name') or '').strip()
        valid_bank_codes = {
            option['value']
            for option in self._seller_payout_bank_options(seller)
            if option.get('value')
        }
        try:
            if not bank_name or bank_name not in valid_bank_codes:
                raise ValueError('Pilih bank atau e-wallet yang valid.')
            if not account_number:
                raise ValueError('Nomor rekening wajib diisi.')
            if len(account_number) > 64:
                raise ValueError('Nomor rekening maksimal 64 karakter.')
            if not account_name:
                raise ValueError('Nama pemilik rekening wajib diisi.')
            if len(account_name) > 128:
                raise ValueError('Nama pemilik rekening maksimal 128 karakter.')
            with request.env.cr.savepoint():
                seller.write({
                    'x_payout_channel_code': bank_name,
                    'x_payout_account_number': account_number,
                    'x_payout_account_name': account_name,
                })
        except ValueError as error:
            return {
                'success': False,
                'message': str(error),
            }
        except Exception:
            _logger.exception('Failed saving payout account for seller %s', seller.id)
            return {
                'success': False,
                'message': 'Rekening belum bisa disimpan. Silakan coba lagi.',
            }

        payout_payload = self._seller_payout_context_payload(seller)
        payout_payload['success'] = True
        return {
            'success': True,
            'message': 'Rekening pencairan berhasil disimpan.',
            'payout_payload': payout_payload,
        }

    @http.route('/unitrade/seller/payout/request', type='json', auth='user', website=True, methods=['POST'])
    def seller_payout_request(self, **kwargs):
        """Request payout for releasable seller balances owned by the current seller."""
        seller = self._dashboard_seller()
        if not seller:
            return {
                'success': False,
                'message': self._seller_not_ready_message(),
            }
        if 'unitrade.escrow.ledger' not in request.env.registry:
            return {
                'success': False,
                'message': 'Sistem saldo belum aktif sehingga pencairan belum bisa diproses.',
            }
        currency = request.website.currency_id or request.env.company.currency_id
        balance_summary = self._seller_balance_summary(seller, currency)
        if not _safe_get(seller, 'x_payout_ready', False):
            return {
                'success': False,
                'message': 'Lengkapi rekening pencairan di Pengaturan Toko sebelum tarik saldo.',
            }
        if balance_summary['available_balance'] <= 0:
            return {
                'success': False,
                'message': 'Belum ada saldo yang siap dicairkan.',
            }
        if balance_summary['used_balance'] > 0:
            return {
                'success': False,
                'message': 'Sebagian saldo sudah dipakai untuk biaya posting. Pencairan otomatis menunggu rekonsiliasi saldo.',
            }

        ledger_id = kwargs.get('ledger_id')
        if ledger_id:
            try:
                ledger_id = int(ledger_id)
            except (TypeError, ValueError):
                return {
                    'success': False,
                    'message': 'Referensi dana tidak valid.',
                }
            ledgers = request.env['unitrade.escrow.ledger'].sudo().browse(ledger_id).exists()
            if not ledgers or ledgers.seller_id.id != seller.id or not self._seller_ledger_is_payoutable(ledgers):
                return {
                    'success': False,
                    'message': 'Dana pesanan ini belum siap dicairkan.',
                }
        else:
            ledgers = self._seller_valid_balance_ledgers(seller).filtered(lambda ledger: self._seller_ledger_is_payoutable(ledger))
        if not ledgers:
            return {
                'success': False,
                'message': 'Belum ada transaksi selesai yang siap dicairkan.',
            }
        payout = request.env['unitrade.seller.payout'].sudo().create({
            'seller_id': seller.id,
            'currency_id': currency.id,
            'amount': currency.round(sum(ledgers.mapped('amount_seller'))),
            'state': 'pending',
            'ledger_ids_json': json.dumps(ledgers.ids),
            **self._seller_payout_destination_values(seller),
        }) if 'unitrade.seller.payout' in request.env.registry else False
        try:
            with request.env.cr.savepoint():
                ledgers.action_create_xendit_payout()
                if payout:
                    payout.write({
                        'state': 'processing',
                        'processed_at': fields.Datetime.now(),
                    })
        except UserError as error:
            if payout:
                payout.write({
                    'state': 'failed',
                    'failure_reason': error.args[0] if error.args else str(error),
                })
            return {
                'success': False,
                'message': error.args[0] if error.args else str(error),
            }
        except Exception:
            _logger.exception('Seller payout request failed for seller %s', seller.id)
            if payout:
                payout.write({
                    'state': 'failed',
                    'failure_reason': 'Permintaan pencairan belum bisa diproses. Silakan coba lagi.',
                })
            return {
                'success': False,
                'message': 'Permintaan pencairan belum bisa diproses. Silakan coba lagi.',
            }

        context = self._seller_dashboard_context(seller)
        payload = json.loads(context['dashboard_payload_json'])
        payload['success'] = True
        payout_payload = self._seller_payout_context_payload(seller)
        payout_payload['success'] = True
        return {
            'success': True,
            'message': 'Permintaan pencairan berhasil dikirim.',
            'dashboard_payload': payload,
            'payout_payload': payout_payload,
        }

    @http.route([
        '/unitrade/seller/orders',
        '/seller/orders',
        '/my/seller/orders',
    ], type='http', auth='user', website=True, sitemap=False)
    def seller_orders(self, **kwargs):
        """Render the standalone seller orders app shell."""
        seller = self._dashboard_seller()
        if not seller:
            return self._seller_not_ready_redirect()

        return request.render(
            'unitrade_seller.seller_orders_template',
            self._seller_orders_context(seller),
        )

    @http.route([
        '/unitrade/seller/orders/<int:order_id>',
        '/seller/orders/<int:order_id>',
        '/my/seller/orders/<int:order_id>',
    ], type='http', auth='user', website=True, sitemap=False)
    def seller_order_detail(self, order_id, **kwargs):
        """Render a seller-owned order detail page."""
        seller = self._dashboard_seller()
        if not seller:
            return self._seller_not_ready_redirect()

        order = request.env['sale.order'].sudo().browse(order_id).exists()
        if not order or not self._seller_order_lines_for_order(seller, order):
            return request.not_found()

        return request.render(
            'unitrade_seller.seller_order_detail_template',
            self._seller_order_detail_context(seller, order),
        )

    @http.route('/unitrade/seller/orders/data', type='json', auth='user', website=True, methods=['POST'])
    def seller_orders_data(self, **kwargs):
        """Return seller order rows for the OWL orders page."""
        seller = self._dashboard_seller()
        if not seller:
            return {
                'success': False,
                'message': self._seller_not_ready_message(),
                'orders': [],
                'counts': {},
            }

        query = self._seller_search_text(kwargs.get('query'))
        status_filter = self._seller_orders_status_filter(kwargs.get('status_filter'))
        page = self._seller_orders_page_number(kwargs.get('page'))
        page_size = self._seller_orders_page_size(kwargs.get('page_size'))
        payload = self._seller_orders_payloads(
            seller,
            query=query,
            status_filter=status_filter,
            page=page,
            page_size=page_size,
        )
        _, unread_chat_count = self._seller_dashboard_chat_payloads(seller)
        pending_order_count = self._seller_dashboard_pending_order_count(seller)
        return {
            'success': True,
            'seller': {
                'name': seller.name,
                'avatar_url': '/web/image/res.users/%s/avatar_128?unique=%s' % (
                    seller.user_id.id,
                    seller.user_id.write_date or '',
                ),
                'profile_url': '/seller-profile/%s' % self._seller_public_ref(seller),
            },
            'stats': {
                'notification_count': pending_order_count + unread_chat_count,
                'unread_chat_count': unread_chat_count,
            },
            'orders': payload['orders'],
            'counts': payload['counts'],
            'pagination': payload['pagination'],
            'query': payload['query'],
            'status_filter': payload['status_filter'],
            'page_size': payload['pagination']['page_size'],
            'csrf_token': request.csrf_token(),
        }

    @http.route([
        '/unitrade/seller/refunds',
        '/seller/refunds',
        '/my/seller/refunds',
    ], type='http', auth='user', website=True, sitemap=False)
    def seller_refunds(self, **kwargs):
        """Render the seller refund list app shell."""
        seller = self._dashboard_seller()
        if not seller:
            return self._seller_not_ready_redirect()

        return request.render(
            'unitrade_seller.seller_refunds_template',
            self._seller_refunds_context(seller),
        )

    @http.route('/unitrade/seller/refunds/data', type='json', auth='user', website=True, methods=['POST'])
    def seller_refunds_data(self, **kwargs):
        """Return seller-owned refund rows for the OWL refund page."""
        seller = self._dashboard_seller()
        if not seller:
            return {
                'success': False,
                'message': self._seller_not_ready_message(),
                'refunds': [],
                'counts': {},
            }

        query = self._seller_search_text(kwargs.get('query'))
        status_filter = self._seller_refunds_status_filter(kwargs.get('status_filter'))
        date_from = self._seller_refunds_date_value(kwargs.get('date_from'))
        date_to = self._seller_refunds_date_value(kwargs.get('date_to'))
        page = self._seller_refunds_page_number(kwargs.get('page'))
        page_size = self._seller_refunds_page_size(kwargs.get('page_size'))
        payload = self._seller_refunds_payloads(
            seller,
            query=query,
            status_filter=status_filter,
            date_from=date_from,
            date_to=date_to,
            page=page,
            page_size=page_size,
        )
        unread_chat_count = self._seller_dashboard_chat_payloads(seller)[1]
        pending_order_count = self._seller_dashboard_pending_order_count(seller)
        return {
            'success': True,
            'seller': {
                'name': seller.name,
                'avatar_url': '/web/image/res.users/%s/avatar_128?unique=%s' % (
                    seller.user_id.id,
                    seller.user_id.write_date or '',
                ),
                'profile_url': '/seller-profile/%s' % self._seller_public_ref(seller),
            },
            'stats': {
                'incoming_orders': pending_order_count,
                'notification_count': pending_order_count + unread_chat_count,
                'unread_chat_count': unread_chat_count,
            },
            'refunds': payload['refunds'],
            'counts': payload['counts'],
            'pagination': payload['pagination'],
            'query': payload['query'],
            'status_filter': payload['status_filter'],
            'date_from': payload['date_from'],
            'date_to': payload['date_to'],
            'page_size': payload['pagination']['page_size'],
            'csrf_token': request.csrf_token(),
        }

    @http.route('/unitrade/seller/refunds/<int:dispute_id>', type='http', auth='user', website=True, sitemap=False)
    def seller_refund_detail(self, dispute_id, **kwargs):
        """Render the seller-owned refund detail page."""
        seller = self._dashboard_seller()
        if not seller:
            return self._seller_not_ready_redirect()
        dispute = self._seller_refund_dispute_for_seller(seller, dispute_id)
        if not dispute:
            return request.not_found()
        return request.render(
            'unitrade_seller.seller_refund_detail_template',
            self._seller_refund_detail_context(seller, dispute),
        )

    @http.route('/unitrade/seller/refunds/<int:dispute_id>/decision', type='json', auth='user', website=True, methods=['POST'])
    def seller_refund_decision(self, dispute_id, **kwargs):
        """Persist seller note and approve/reject a seller-owned refund."""
        seller = self._dashboard_seller()
        if not seller:
            return {
                'success': False,
                'message': self._seller_not_ready_message(),
            }
        dispute = self._seller_refund_dispute_for_seller(seller, dispute_id)
        if not dispute:
            return {
                'success': False,
                'message': 'Refund tidak ditemukan atau bukan milik toko Anda.',
            }
        decision = kwargs.get('decision') or kwargs.get('action') or ''
        note = (kwargs.get('seller_note') or '').strip()
        if decision not in ('approve', 'reject'):
            return {
                'success': False,
                'message': 'Keputusan refund tidak valid.',
            }
        allow_initial_decision = dispute.state in ('submitted', 'under_review') and not dispute.seller_decided_at
        allow_return_rejection = dispute.state == 'need_seller_response' and decision == 'reject'
        if not allow_initial_decision and not allow_return_rejection:
            return {
                'success': False,
                'message': 'Keputusan awal seller sudah diproses. Lanjutkan melalui langkah yang tersedia di detail refund.',
            }
        if decision == 'reject' and not note:
            return {
                'success': False,
                'message': 'Catatan Seller wajib diisi sebelum menolak refund.',
            }
        try:
            with request.env.cr.savepoint():
                if decision == 'approve':
                    if allow_return_rejection:
                        raise UserError('Konfirmasi penerimaan barang harus memakai form upload bukti.')
                    dispute.with_user(request.env.user).action_seller_approve_refund(note=note)
                    message = 'Refund disetujui seller. Menunggu pembeli mengembalikan barang.'
                else:
                    dispute.with_user(request.env.user).action_seller_reject_refund(note=note)
                    message = 'Penolakan seller dikirim. Customer Service/admin akan meninjau sebagai mediator.'
        except Exception as error:
            request.env.clear()
            _logger.exception('Seller refund decision failed for dispute %s', dispute_id)
            return {
                'success': False,
                'message': str(error) or 'Keputusan refund belum bisa diproses.',
            }
        dispute = request.env['unitrade.dispute'].sudo().browse(dispute.id).exists()
        return {
            'success': True,
            'message': message,
            'payload': self._seller_refund_detail_payload(seller, dispute),
        }

    @http.route('/unitrade/seller/refunds/<int:dispute_id>/chat', type='http', auth='user', website=True, sitemap=False)
    def seller_refund_chat(self, dispute_id, **kwargs):
        seller = self._dashboard_seller()
        if not seller:
            return self._seller_not_ready_redirect()
        dispute = self._seller_refund_dispute_for_seller(seller, dispute_id)
        if not dispute:
            return request.not_found()
        if 'unitrade.chat.conversation' not in request.env.registry:
            return request.redirect('/unitrade/seller/chat')
        conversation = self._seller_order_conversation(seller, dispute.order_id)
        if not conversation:
            buyer_user = request.env['res.users'].sudo().search([
                ('partner_id', '=', dispute.order_id.partner_id.id),
            ], limit=1)
            line = self._seller_refund_line(seller, dispute)
            product = line.product_id.product_tmpl_id if line and line.product_id else False
            if buyer_user:
                conversation = request.env['unitrade.chat.conversation'].sudo().create({
                    'buyer_user_id': buyer_user.id,
                    'seller_id': seller.id,
                    'product_id': product.id if product else False,
                })
                _logger.info('Seller refund chat conversation %s opened for dispute %s', conversation.id, dispute.id)
        if conversation:
            return request.redirect('/unitrade/seller/chat?conversation_id=%s' % conversation.id)
        return request.redirect('/unitrade/seller/chat')

    @http.route('/unitrade/seller/refund/<int:dispute_id>/approve', type='http', auth='user', website=True, methods=['POST'], csrf=True, sitemap=False)
    def seller_refund_approve(self, dispute_id, **kwargs):
        if self._current_user_block_message(_('merespons refund sebagai seller')):
            return request.redirect('/my/profile?unitrade_blocked=1')
        seller = self._dashboard_seller()
        if not seller or 'unitrade.dispute' not in request.env.registry:
            return request.not_found()
        dispute = request.env['unitrade.dispute'].sudo().browse(dispute_id).exists()
        if not dispute or not dispute.seller_id or dispute.seller_id.id != seller.id:
            return request.not_found()
        try:
            if dispute.state not in ('submitted', 'under_review') or dispute.seller_decided_at:
                raise UserError('Keputusan awal seller sudah diproses. Lanjutkan melalui detail refund.')
            dispute.with_user(request.env.user).action_seller_approve_refund(note=kwargs.get('seller_note') or '')
            return request.redirect(self._seller_refund_detail_url(dispute) + '?refund_approved=1')
        except Exception as error:
            _logger.exception('Seller refund approve failed for dispute %s', dispute_id)
            return request.redirect('%s?seller_error=%s' % (self._seller_refund_detail_url(dispute), quote(str(error))))

    @http.route('/unitrade/seller/refund/<int:dispute_id>/reject', type='http', auth='user', website=True, methods=['POST'], csrf=True, sitemap=False)
    def seller_refund_reject(self, dispute_id, **kwargs):
        if self._current_user_block_message(_('merespons refund sebagai seller')):
            return request.redirect('/my/profile?unitrade_blocked=1')
        seller = self._dashboard_seller()
        if not seller or 'unitrade.dispute' not in request.env.registry:
            return request.not_found()
        dispute = request.env['unitrade.dispute'].sudo().browse(dispute_id).exists()
        if not dispute or not dispute.seller_id or dispute.seller_id.id != seller.id:
            return request.not_found()
        try:
            if dispute.state not in ('submitted', 'under_review') or dispute.seller_decided_at:
                raise UserError('Keputusan awal seller sudah diproses. Lanjutkan melalui detail refund.')
            dispute.with_user(request.env.user).action_seller_reject_refund(note=kwargs.get('seller_note') or '')
            return request.redirect(self._seller_refund_detail_url(dispute) + '?refund_rejected=1')
        except Exception as error:
            _logger.exception('Seller refund reject failed for dispute %s', dispute_id)
            return request.redirect('%s?seller_error=%s' % (self._seller_refund_detail_url(dispute), quote(str(error))))

    @http.route([
        '/unitrade/seller/products',
        '/seller/products',
        '/my/seller/products',
    ], type='http', auth='user', website=True, sitemap=False)
    def seller_products(self, **kwargs):
        """Render the standalone seller products app shell."""
        seller = self._dashboard_seller()
        if not seller:
            return self._seller_not_ready_redirect()

        return request.render(
            'unitrade_seller.seller_products_template',
            self._seller_products_page_context(seller, date_filter=kwargs.get('date_filter')),
        )

    @http.route('/unitrade/seller/products/<int:product_id>', type='http', auth='user', website=True, sitemap=False)
    def seller_product_detail(self, product_id, **kwargs):
        """Render an internal seller-owned product detail page."""
        seller = self._dashboard_seller(active_only=False)
        if not seller:
            return self._seller_not_ready_redirect()
        product = self._seller_product_for_detail(seller, product_id)
        if not product:
            return request.not_found()
        return request.render(
            'unitrade_seller.seller_product_detail_template',
            self._seller_product_detail_context(seller, product),
        )

    @http.route([
        '/unitrade/seller/settings',
        '/seller/settings',
        '/my/seller/settings',
    ], type='http', auth='user', website=True, sitemap=False)
    def seller_settings(self, **kwargs):
        """Render the standalone seller store settings app shell."""
        seller = self._dashboard_seller(active_only=False)
        if not seller:
            return self._seller_not_ready_redirect()
        return request.render(
            'unitrade_seller.seller_settings_template',
            self._seller_settings_context(seller),
        )

    @http.route('/unitrade/seller/settings/data', type='json', auth='user', website=True, methods=['POST'])
    def seller_settings_data(self, **kwargs):
        """Return current settings for the logged-in seller only."""
        seller = self._dashboard_seller(active_only=False)
        if not seller:
            return {
                'success': False,
                'message': self._seller_not_ready_message(),
            }
        payload = self._seller_settings_payload(seller)
        payload['success'] = True
        return payload

    @http.route('/unitrade/seller/settings/update', type='json', auth='user', website=True, methods=['POST'])
    def seller_settings_update(self, **kwargs):
        """Update store settings for the logged-in seller only."""
        seller = self._dashboard_seller(active_only=False)
        if not seller:
            return {
                'success': False,
                'message': self._seller_not_ready_message(),
            }
        try:
            with request.env.cr.savepoint():
                self._sync_seller_settings(seller, kwargs)
        except ValueError as error:
            return {
                'success': False,
                'message': str(error),
            }
        except Exception:
            _logger.exception('Failed updating seller settings for seller %s', seller.id)
            return {
                'success': False,
                'message': 'Pengaturan toko belum bisa disimpan. Silakan coba lagi.',
            }
        payload = self._seller_settings_payload(seller)
        payload.update({
            'success': True,
            'message': 'Pengaturan toko berhasil disimpan.',
        })
        return payload

    @http.route('/unitrade/seller/settings/close-store', type='json', auth='user', website=True, methods=['POST'])
    def seller_settings_close_store(self, **kwargs):
        """Deactivate the current seller store and unpublished marketplace products."""
        seller = self._dashboard_seller(active_only=False)
        if not seller:
            return {
                'success': False,
                'message': self._seller_not_ready_message(),
            }
        if kwargs.get('confirm') != 'CLOSE_STORE':
            return {
                'success': False,
                'message': 'Konfirmasi tutup toko tidak valid.',
            }
        try:
            with request.env.cr.savepoint():
                seller.write({'x_store_active': False})
                products = request.env['product.template'].sudo().search(self._seller_dashboard_product_domain(seller, active_only=False))
                products.write({
                    'website_published': False,
                    'sale_ok': False,
                })
        except Exception:
            _logger.exception('Failed closing seller store %s', seller.id)
            return {
                'success': False,
                'message': 'Toko belum bisa ditutup. Silakan coba lagi.',
            }
        return {
            'success': True,
            'message': 'Toko berhasil dinonaktifkan.',
            'redirect_url': '/unitrade/seller/settings',
        }

    @http.route('/unitrade/seller/settings/request-delete', type='json', auth='user', website=True, methods=['POST'])
    def seller_settings_request_delete(self, **kwargs):
        """Create a safe deletion request without permanently deleting records."""
        seller = self._dashboard_seller(active_only=False)
        if not seller:
            return {
                'success': False,
                'message': self._seller_not_ready_message(),
            }
        if kwargs.get('confirm') != 'REQUEST_SELLER_DELETE':
            return {
                'success': False,
                'message': 'Konfirmasi hapus akun penjual tidak valid.',
            }
        try:
            seller.write({
                'x_delete_requested': True,
                'x_delete_requested_at': fields.Datetime.now(),
                'revoke_reason': 'Seller meminta penghapusan akun melalui Pengaturan Toko.',
            })
        except Exception:
            _logger.exception('Failed creating seller delete request %s', seller.id)
            return {
                'success': False,
                'message': 'Permintaan hapus akun belum bisa diproses. Silakan coba lagi.',
            }
        return {
            'success': True,
            'message': 'Permintaan hapus akun penjual sudah dicatat untuk ditinjau admin.',
            'redirect_url': '/unitrade/seller/settings',
        }

    @http.route([
        '/unitrade/seller/products/new',
        '/seller/products/new',
        '/my/seller/products/new',
    ], type='http', auth='user', website=True, sitemap=False)
    def seller_product_create(self, **kwargs):
        """Render the standalone seller product creation app shell."""
        seller = self._dashboard_seller()
        if not seller:
            return self._seller_not_ready_redirect()

        return request.render(
            'unitrade_seller.seller_product_create_template',
            self._seller_product_create_context(seller),
        )

    @http.route([
        '/unitrade/seller/products/<int:product_id>/payment',
        '/seller/products/<int:product_id>/payment',
        '/my/seller/products/<int:product_id>/payment',
    ], type='http', auth='user', website=True, sitemap=False)
    def seller_product_payment(self, product_id, **kwargs):
        """Render the listing payment step for a newly created seller product."""
        seller = self._dashboard_seller()
        if not seller:
            return self._seller_not_ready_redirect()
        product = self._seller_product_for_edit(seller, product_id)
        if not product:
            return request.redirect('/unitrade/seller/products')
        status = self._seller_product_listing_status(seller, product)
        if not status.get('can_continue_payment'):
            return request.redirect(self._seller_product_detail_url(product))

        return request.render(
            'unitrade_seller.seller_product_payment_template',
            self._seller_product_payment_context(seller, product),
        )

    @http.route('/unitrade/seller/products/<int:product_id>/edit', type='http', auth='user', website=True, sitemap=False)
    def seller_product_edit(self, product_id, **kwargs):
        """Render the standalone seller product edit app shell."""
        seller = self._dashboard_seller()
        if not seller:
            return self._seller_not_ready_redirect()
        product = self._seller_product_for_edit(seller, product_id)
        if not product:
            return request.redirect('/unitrade/seller/products')

        return request.render(
            'unitrade_seller.seller_product_edit_template',
            self._seller_product_edit_context(seller, product),
        )

    @http.route('/unitrade/seller/products/<int:product_id>/payment/data', type='json', auth='user', website=True, methods=['POST'])
    def seller_product_payment_data(self, product_id, **kwargs):
        seller = self._dashboard_seller()
        if not seller:
            return {
                'success': False,
                'message': self._seller_not_ready_message(),
            }
        product = self._seller_product_for_edit(seller, product_id)
        if not product:
            return {
                'success': False,
                'message': 'Produk tidak ditemukan atau bukan milik toko Anda.',
            }
        status = self._seller_product_listing_status(seller, product)
        if not status.get('can_continue_payment'):
            return {
                'success': False,
                'message': status.get('note') or 'Pembayaran produk ini tidak bisa dilanjutkan.',
                'redirect_url': self._seller_product_detail_url(product),
            }
        payload = self._seller_product_payment_payload(seller, product)
        payload['success'] = True
        return payload

    @http.route('/unitrade/seller/products/new/data', type='json', auth='user', website=True, methods=['POST'])
    def seller_product_create_data(self, **kwargs):
        """Return dynamic data for the seller product creation form."""
        seller = self._dashboard_seller()
        if not seller:
            return {
                'success': False,
                'message': self._seller_not_ready_message(),
                'categories': [],
            }

        return {
            'success': True,
            'seller': {
                'name': seller.name,
                'avatar_url': '/web/image/res.users/%s/avatar_128?unique=%s' % (
                    seller.user_id.id,
                    seller.user_id.write_date or '',
                ),
                'profile_url': '/seller-profile/%s' % self._seller_public_ref(seller),
            },
            'stats': {
                'notification_count': self._seller_dashboard_pending_order_count(seller),
                'unread_chat_count': self._seller_dashboard_chat_payloads(seller)[1],
            },
            'categories': self._seller_product_categories(),
            'max_file_size': 5 * 1024 * 1024,
            'products_url': '/unitrade/seller/products',
            'dashboard_url': '/unitrade/seller/dashboard',
            'payment_url': '',
        }

    @http.route('/unitrade/seller/products/<int:product_id>/edit/data', type='json', auth='user', website=True, methods=['POST'])
    def seller_product_edit_data(self, product_id, **kwargs):
        """Return dynamic data and the existing product values for edit mode."""
        seller = self._dashboard_seller()
        if not seller:
            return {
                'success': False,
                'message': self._seller_not_ready_message(),
            }
        product = self._seller_product_for_edit(seller, product_id)
        if not product:
            return {
                'success': False,
                'message': 'Produk tidak ditemukan atau bukan milik toko Anda.',
            }
        payload = self._seller_product_edit_context(seller, product)
        data = json.loads(payload['product_create_payload_json'])
        data['success'] = True
        return data

    @http.route('/unitrade/seller/products/create', type='json', auth='user', website=True, methods=['POST'])
    def seller_product_create_submit(self, **kwargs):
        """Create a marketplace product for the verified seller."""
        seller = self._dashboard_seller()
        if not seller:
            return {
                'success': False,
                'message': self._seller_not_ready_message(),
            }

        try:
            with request.env.cr.savepoint():
                product = self._create_seller_product(seller, kwargs)
        except ValueError as error:
            return {
                'success': False,
                'message': str(error),
            }
        except Exception as error:
            _logger.exception('Failed to create seller product for user %s', request.env.uid)
            return {
                'success': False,
                'message': str(error) or 'Produk belum bisa dibuat. Coba lagi beberapa saat lagi.',
            }

        currency = request.website.currency_id or request.env.company.currency_id
        product_price = product._unitrade_discounted_price() if hasattr(product, '_unitrade_discounted_price') else product.list_price
        posting_fee, admin_fee, total, fee_policy = self._seller_listing_fee_amounts(currency, product_price)
        if total <= 0:
            self._publish_product_after_listing_paid(product, total)
            if 'x_listing_fee_status' in product._fields:
                product.sudo().write({'x_listing_fee_status': 'not_required'})
            return {
                'success': True,
                'message': 'Produk berhasil dipublikasikan.',
                'product_id': product.id,
                'payment_url': '',
                'redirect_url': '/unitrade/seller/products',
            }

        return {
            'success': True,
            'message': 'Produk tersimpan sebagai draft. Lanjutkan pembayaran agar tampil di katalog.',
            'product_id': product.id,
            'payment_url': '/unitrade/seller/products/%s/payment' % product.id,
            'redirect_url': '/unitrade/seller/products/%s/payment' % product.id,
        }

    @staticmethod
    def _seller_listing_payment_method(method_key):
        methods = {
            'bca_va': ('midtrans', 'bca_va', 'BCA Virtual Account'),
            'mandiri_bill': ('midtrans', 'mandiri_bill', 'Mandiri Bill Payment'),
            'bni_va': ('midtrans', 'bni_va', 'BNI Virtual Account'),
            'bri_va': ('midtrans', 'bri_va', 'BRI Virtual Account'),
            'permata_va': ('midtrans', 'permata_va', 'Permata Virtual Account'),
            'cimb_va': ('midtrans', 'cimb_va', 'CIMB Virtual Account'),
            'gopay': ('midtrans', 'gopay', 'GoPay'),
            'shopeepay': ('midtrans', 'shopeepay', 'ShopeePay'),
            'qris': ('midtrans', 'qris', 'QRIS'),
            'account_balance': ('account_balance', 'Saldo Akun'),
        }
        return methods.get(method_key or '')

    @staticmethod
    def _publish_product_after_listing_paid(product, listing_fee=0.0):
        if hasattr(product, '_unitrade_apply_listing_payment'):
            product._unitrade_apply_listing_payment(
                listing_fee=listing_fee,
                paid_at=fields.Datetime.now(),
            )
            return
        values = {
            'sale_ok': True,
            'website_published': True,
        }
        if 'x_listing_fee' in product._fields:
            values['x_listing_fee'] = listing_fee
        if 'x_listing_activated_at' in product._fields:
            values['x_listing_activated_at'] = fields.Datetime.now()
        if 'x_listing_expires_at' in product._fields:
            values['x_listing_expires_at'] = UnitradeSellerController._seller_listing_valid_until()
        if 'detailed_type' in product._fields:
            values['detailed_type'] = 'consu'
        elif 'type' in product._fields:
            values['type'] = 'consu'
        product.sudo().write(values)

    def _create_seller_listing_payment_intent(self, seller, product, method_key, total, currency):
        if 'unitrade.payment.intent' not in request.env.registry:
            raise ValueError('Modul pembayaran UniTrade belum aktif.')

        method = self._seller_listing_payment_method(method_key)
        if not method:
            raise ValueError('Metode pembayaran tidak valid.')

        balance = self._seller_available_balance(seller, currency)
        if method_key == 'account_balance' and balance < total:
            raise ValueError('Saldo akun belum mencukupi untuk pembayaran posting produk.')

        if method_key != 'account_balance':
            try:
                return request.env['unitrade.payment.intent'].sudo().create_listing_fee_midtrans_payment(
                    seller=seller.sudo(),
                    product=product.sudo(),
                    method_key=method_key,
                    amount=total,
                    currency=currency,
                )
            except UserError as error:
                raise ValueError(error.args[0] if error.args else str(error)) from error

        code = 'account_balance'
        label = 'Saldo Akun'

        PaymentIntent = request.env['unitrade.payment.intent'].sudo()
        existing = PaymentIntent.search([
            ('intent_type', '=', 'listing_fee'),
            ('product_template_id', '=', product.id),
            ('seller_id', '=', seller.id),
            ('state', 'in', ['draft', 'pending']),
        ], order='create_date desc', limit=1)
        if existing:
            return existing

        now_label = fields.Datetime.now().strftime('%Y%m%d%H%M%S')
        intent = PaymentIntent.create({
            'name': 'LIST-%s-%s' % (product.id, now_label),
            'provider': 'midtrans',
            'intent_type': 'listing_fee',
            'state': 'paid',
            'amount': total,
            'currency_id': currency.id,
            'product_template_id': product.id,
            'partner_id': seller.partner_id.id or seller.user_id.partner_id.id,
            'seller_id': seller.id,
            'payment_method_code': code,
            'payment_method_label': label,
            'payment_reference': 'UT-LIST-%s' % product.id,
            'paid_at': fields.Datetime.now() if method_key == 'account_balance' else False,
        })
        intent._set_raw_request({
            'intent_type': 'listing_fee',
            'product_template_id': product.id,
            'seller_id': seller.id,
            'method': method_key,
            'amount': total,
        })
        self._publish_product_after_listing_paid(product, total)
        return intent

    @http.route('/unitrade/seller/products/<int:product_id>/payment/submit', type='json', auth='user', website=True, methods=['POST'])
    def seller_product_payment_submit(self, product_id, **kwargs):
        seller = self._dashboard_seller()
        if not seller:
            return {
                'success': False,
                'message': self._seller_not_ready_message(),
            }
        product = self._seller_product_for_edit(seller, product_id)
        if not product:
            return {
                'success': False,
                'message': 'Produk tidak ditemukan atau bukan milik toko Anda.',
            }
        status = self._seller_product_listing_status(seller, product)
        if not status.get('can_continue_payment'):
            return {
                'success': False,
                'message': status.get('note') or 'Pembayaran produk ini tidak bisa dilanjutkan.',
                'redirect_url': self._seller_product_detail_url(product),
            }
        method_key = kwargs.get('payment_method')
        accepted = bool(kwargs.get('accepted_terms'))
        if not accepted:
            return {
                'success': False,
                'message': 'Setujui syarat dan ketentuan terlebih dahulu.',
            }

        currency = request.website.currency_id or request.env.company.currency_id
        product_price = product._unitrade_discounted_price() if hasattr(product, '_unitrade_discounted_price') else product.list_price
        posting_fee, admin_fee, total, fee_policy = self._seller_listing_fee_amounts(currency, product_price)
        if total <= 0:
            self._publish_product_after_listing_paid(product, total)
            if 'x_listing_fee_status' in product._fields:
                product.sudo().write({'x_listing_fee_status': 'not_required'})
            return {
                'success': True,
                'message': 'Produk berhasil dipublikasikan.',
                'payment_intent_id': 0,
                'payment_status': 'paid',
                'payment_method': '',
                'payment_reference': '',
                'payment_url': '',
                'redirect_url': '/unitrade/seller/products',
                'amount_label': self._format_money(0.0, currency),
                'fees': {
                    'posting_fee_label': self._format_money(posting_fee, currency),
                    'admin_fee_label': self._format_money(admin_fee, currency),
                    'total_label': self._format_money(total, currency),
                    'tier_label': fee_policy['tier_label'],
                    'percent_label': fee_policy['percent_label'],
                },
            }
        try:
            with request.env.cr.savepoint():
                intent = self._create_seller_listing_payment_intent(seller, product, method_key, total, currency)
                product_values = {}
                if 'x_listing_fee' in product._fields:
                    product_values['x_listing_fee'] = total
                if intent.state == 'paid' and 'x_listing_activated_at' in product._fields:
                    product_values['x_listing_activated_at'] = fields.Datetime.now()
                if intent.state == 'paid' and 'x_listing_expires_at' in product._fields:
                    product_values['x_listing_expires_at'] = self._seller_listing_valid_until()
                if product_values:
                    product.sudo().write(product_values)
        except ValueError as error:
            return {
                'success': False,
                'message': str(error),
            }
        except Exception:
            _logger.exception('Failed creating seller listing payment for product %s', product.id)
            return {
                'success': False,
                'message': 'Transaksi pembayaran belum bisa dibuat. Silakan coba lagi.',
            }

        return {
            'success': True,
            'message': 'Transaksi pembayaran berhasil dibuat.',
            'payment_intent_id': intent.id,
            'payment_status': intent.state,
            'payment_method': intent.payment_method_label,
            'payment_reference': intent.payment_reference or intent.name,
            'payment_url': intent.unitrade_public_payment_url(),
            'redirect_url': (
                '/unitrade/payment/success/%s' % intent._unitrade_reference_key()
                if intent.state == 'paid'
                else intent.unitrade_public_payment_url()
            ),
            'amount_label': self._format_money(intent.amount, intent.currency_id),
            'fees': {
                'posting_fee_label': self._format_money(posting_fee, currency),
                'admin_fee_label': self._format_money(admin_fee, currency),
                'total_label': self._format_money(total, currency),
                'tier_label': fee_policy['tier_label'],
                'percent_label': fee_policy['percent_label'],
            },
        }

    @http.route('/unitrade/seller/products/<int:product_id>/update', type='json', auth='user', website=True, methods=['POST'])
    def seller_product_update_submit(self, product_id, **kwargs):
        """Update a marketplace product owned by the current seller."""
        seller = self._dashboard_seller()
        if not seller:
            return {
                'success': False,
                'message': self._seller_not_ready_message(),
            }
        product = self._seller_product_for_edit(seller, product_id)
        if not product:
            return {
                'success': False,
                'message': 'Produk tidak ditemukan atau bukan milik toko Anda.',
            }

        try:
            with request.env.cr.savepoint(flush=False):
                product = self._update_seller_product(seller, product, kwargs)
                product.env.flush_all()
        except (ValueError, UserError, ValidationError) as error:
            request.env.clear()
            return {
                'success': False,
                'message': str(error),
            }
        except Exception:
            request.env.clear()
            _logger.exception('Failed updating seller product %s for seller %s', product_id, seller.id)
            return {
                'success': False,
                'message': 'Produk belum bisa disimpan. Silakan coba lagi.',
            }

        return {
            'success': True,
            'message': 'Perubahan produk berhasil disimpan.',
            'product_id': product.id,
            'redirect_url': '/unitrade/seller/products',
        }

    @http.route('/unitrade/seller/products/<int:product_id>/delete', type='json', auth='user', website=True, methods=['POST'])
    def seller_product_delete_submit(self, product_id, **kwargs):
        """Archive a marketplace product owned by the current seller."""
        seller = self._dashboard_seller()
        if not seller:
            return {
                'success': False,
                'message': self._seller_not_ready_message(),
            }
        product = self._seller_product_for_edit(seller, product_id)
        if not product:
            return {
                'success': False,
                'message': 'Produk tidak ditemukan atau bukan milik toko Anda.',
            }

        try:
            with request.env.cr.savepoint():
                self._archive_seller_product(product)
        except Exception:
            _logger.exception('Failed deleting seller product %s for seller %s', product_id, seller.id)
            return {
                'success': False,
                'message': 'Produk belum bisa dihapus. Silakan coba lagi.',
            }

        return {
            'success': True,
            'message': 'Produk berhasil dihapus.',
            'redirect_url': '/unitrade/seller/products',
        }

    @http.route('/unitrade/seller/products/data', type='json', auth='user', website=True, methods=['POST'])
    def seller_products_data(self, **kwargs):
        """Return seller product rows for the OWL products page."""
        seller = self._dashboard_seller()
        if not seller:
            return {
                'success': False,
                'message': self._seller_not_ready_message(),
                'products': [],
            }
        date_filter = self._seller_products_date_filter(kwargs.get('date_filter'))
        query = self._seller_search_text(kwargs.get('query'))
        page = self._seller_products_page_number(kwargs.get('page'))
        page_size = self._seller_products_page_size(kwargs.get('page_size'))
        page_result = self._seller_products_page_result(
            seller,
            date_filter=date_filter,
            page=page,
            page_size=page_size,
            query=query,
        )

        return {
            'success': True,
            'seller': {
                'name': seller.name,
                'avatar_url': '/web/image/res.users/%s/avatar_128?unique=%s' % (
                    seller.user_id.id,
                    seller.user_id.write_date or '',
                ),
                'profile_url': '/seller-profile/%s' % self._seller_public_ref(seller),
            },
            'stats': {
                'notification_count': self._seller_dashboard_pending_order_count(seller),
                'unread_chat_count': self._seller_dashboard_chat_payloads(seller)[1],
            },
            'products': page_result['products'],
            'pagination': page_result['pagination'],
            'date_filter': date_filter,
            'query': query,
            'page_size': page_result['pagination']['page_size'],
            'add_product_url': self._seller_product_add_url(),
        }

>>>>>>> ca9bf47 (feat : admin fajar anjay sadboy)
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
