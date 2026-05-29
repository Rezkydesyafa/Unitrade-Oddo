from collections import defaultdict
from datetime import datetime, time, timedelta
import base64
import json
import logging
import math
import re
from urllib.parse import quote

import pytz

# pyrefly: ignore [missing-import]
from odoo import SUPERUSER_ID, fields, http
# pyrefly: ignore [missing-import]
from odoo.exceptions import UserError, ValidationError
# pyrefly: ignore [missing-import]
from odoo.http import request
from odoo.osv import expression
from odoo.tools.image import image_data_uri
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
    _HOME_CATEGORY_XMLIDS = (
        'unitrade_product_ext.product_category_unitrade_food',
        'unitrade_product_ext.product_category_unitrade_furniture',
        'unitrade_product_ext.product_category_unitrade_fashion',
        'unitrade_product_ext.product_category_unitrade_electronics',
        'unitrade_product_ext.product_category_unitrade_services',
        'unitrade_product_ext.product_category_unitrade_health_beauty',
        'unitrade_product_ext.product_category_unitrade_hobbies',
        'unitrade_product_ext.product_category_unitrade_other',
    )
    _HOME_CATEGORY_NAMES = (
        'Makanan',
        'Perabotan',
        'Fashion',
        'Elektronik',
        'Jasa',
        'Kesehatan & Kecantikan',
        'Hobi & Koleksi',
        'Lainnya',
    )
    _UUID_PATTERN = re.compile(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
        re.IGNORECASE,
    )

    @staticmethod
    def _seller_public_ref(seller):
        seller._ensure_profile_uuid()
        return _safe_get(seller, 'x_store_slug') or UnitradeSellerController._ensure_seller_store_slug(seller) or seller.x_profile_uuid

    @staticmethod
    def _ensure_seller_store_slug(seller):
        if not seller:
            return ''
        current_slug = _safe_get(seller, 'x_store_slug') or ''
        if current_slug and not UnitradeSellerController._UUID_PATTERN.match(current_slug):
            return current_slug

        Seller = request.env['unitrade.seller'].sudo()
        base_slug = UnitradeSellerController._store_slug(
            seller.name or seller.user_id.name or seller.user_id.login or ('seller-%s' % seller.id)
        ) or ('seller-%s' % seller.id)
        slug = base_slug
        suffix = 2
        while Seller.search_count([('x_store_slug', '=', slug), ('id', '!=', seller.id)]):
            slug = '%s-%s' % (base_slug[:72], suffix)
            suffix += 1
        try:
            seller.sudo().write({'x_store_slug': slug})
        except Exception:
            _logger.exception('Failed ensuring store slug for seller %s', seller.id)
            return current_slug
        return slug

    @staticmethod
    def _seller_phone_value(seller):
        if not seller:
            return ''
        partner = seller.partner_id
        return (
            _safe_get(seller.user_id, 'x_whatsapp')
            or (partner.mobile if partner else '')
            or (partner.phone if partner else '')
            or ''
        ).strip()

    @staticmethod
    def _normalize_whatsapp_phone(value):
        phone = ''.join(ch for ch in (value or '') if ch.isdigit())
        if phone.startswith('0'):
            phone = '62%s' % phone[1:]
        return phone

    @staticmethod
    def _seller_phone_url(seller):
        phone = UnitradeSellerController._normalize_whatsapp_phone(
            UnitradeSellerController._seller_phone_value(seller)
        )
        return 'https://wa.me/%s' % phone if phone else ''

    @staticmethod
    def _get_seller_by_public_ref(profile_ref=None, seller_id=None):
        Seller = request.env['unitrade.seller'].sudo()
        seller = Seller.browse()
        if seller_id:
            seller = Seller.browse(seller_id).exists()
        elif profile_ref:
            seller = Seller.search([('x_store_slug', '=', profile_ref)], limit=1)
            if not seller:
                seller = Seller.search([('x_profile_uuid', '=', profile_ref)], limit=1)
            if not seller and profile_ref.isdigit():
                seller = Seller.browse(int(profile_ref)).exists()

        if seller and UnitradeSellerController._can_view_seller_profile(seller):
            seller._ensure_profile_uuid()
            return seller
        return Seller.browse()

    @staticmethod
    def _can_view_seller_profile(seller):
        if seller.status == 'verified' and _safe_get(seller, 'x_store_active', True):
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
        seller_domain = [('x_seller_id', '=', seller.id)]
        if hasattr(Product, '_unitrade_public_active_domain'):
            domain = expression.AND([seller_domain, Product._unitrade_public_active_domain()])
        else:
            domain = seller_domain + [
                ('x_is_marketplace', '=', True),
                ('sale_ok', '=', True),
                ('website_published', '=', True),
            ]
        if search:
            domain = expression.AND([domain, ['|', ('name', 'ilike', search), ('description_sale', 'ilike', search)]])

        if tab == 'latest':
            order = 'create_date desc'
        elif tab == 'sold' and 'sales_count' in Product._fields:
            order = 'sales_count desc, create_date desc'
        else:
            order = 'website_sequence asc, create_date desc'

        return Product.search(domain, order=order, limit=limit)

    @staticmethod
    def _seller_address(seller):
        partner = seller.partner_id
        if partner:
            province = _safe_get(partner, 'x_unitrade_province') or (partner.state_id.name if partner.state_id else '')
            city = _safe_get(partner, 'x_unitrade_city') or partner.city or ''
            district = _safe_get(partner, 'x_unitrade_district') or ''
            village = _safe_get(partner, 'x_unitrade_village') or ''
            partner_address_parts = [
                partner.street,
                partner.street2,
                village,
                district,
                city,
                province,
                partner.zip,
            ]
            if partner.street and city and partner.zip:
                return ', '.join([part for part in partner_address_parts if part])

        if _safe_get(seller, 'x_store_address_detail'):
            address_parts = [
                _safe_get(seller, 'x_store_address_detail'),
                _safe_get(seller, 'x_store_city'),
                _safe_get(seller, 'x_store_province'),
            ]
            return ', '.join([part for part in address_parts if part])
        if seller.x_profile_address:
            return seller.x_profile_address

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
    def _seller_reviews(products, rating=None, sort='newest', limit=12):
        if not products or 'unitrade.review' not in request.env.registry:
            return request.env['ir.ui.view'].browse()
        domain = [
            ('product_id', 'in', products.ids),
            ('is_visible', '=', True),
        ]
        if rating:
            domain.append(('rating', '=', rating))
        order_map = {
            'newest': 'create_date desc, id desc',
            'oldest': 'create_date asc, id asc',
            'highest': 'rating desc, create_date desc, id desc',
            'lowest': 'rating asc, create_date desc, id desc',
        }
        return request.env['unitrade.review'].sudo().search(domain, order=order_map.get(sort, order_map['newest']), limit=limit)

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
    def _active_review_sort(value):
        return value if value in ('newest', 'oldest', 'highest', 'lowest') else 'newest'

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
    def _dashboard_seller(active_only=True):
        user = request.env.user
        Seller = request.env['unitrade.seller'].sudo()
        domain = [
            ('user_id', '=', user.id),
            ('status', '=', 'verified'),
        ]
        if active_only and 'x_store_active' in Seller._fields:
            domain.append(('x_store_active', '=', True))
        return Seller.search(domain, limit=1)

    def _seller_not_ready_redirect(self):
        seller = self._dashboard_seller(active_only=False)
        if seller and not self._seller_store_is_active(seller):
            return request.redirect('/unitrade/seller/settings?store_inactive=1')
        return request.redirect('/seller-onboarding')

    def _seller_not_ready_message(self):
        seller = self._dashboard_seller(active_only=False)
        if seller and not self._seller_store_is_active(seller):
            return 'Toko sedang nonaktif. Aktifkan kembali di Pengaturan Toko untuk memakai fitur seller.'
        return 'Akun penjual belum terverifikasi.'

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
            if hasattr(Product, '_unitrade_public_active_domain'):
                return expression.AND([domain, Product._unitrade_public_active_domain()])
            domain += [
                ('sale_ok', '=', True),
                ('website_published', '=', True),
            ]
        return domain

    def _refresh_seller_product_listing_states(self, seller):
        Product = request.env['product.template'].sudo()
        expired_payments = self._seller_sync_listing_fee_timeouts(seller=seller)
        if not seller or not hasattr(Product, '_unitrade_refresh_listing_states'):
            return {'backfilled': 0, 'reactivated': 0, 'deactivated': 0, 'expired_payments': expired_payments}
        try:
            result = Product._unitrade_refresh_listing_states(seller=seller.sudo())
            result['expired_payments'] = expired_payments
            return result
        except Exception:
            _logger.exception('Failed refreshing UniTrade listing states for seller %s', seller.id)
            return {'backfilled': 0, 'reactivated': 0, 'deactivated': 0, 'expired_payments': expired_payments}

    def _seller_dashboard_products(self, seller, limit=8):
        self._refresh_seller_product_listing_states(seller)
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
        if hasattr(product, '_unitrade_listing_state_payload'):
            return product._unitrade_listing_state_payload()
        expires_at = _safe_get(product, 'x_listing_expires_at', False)
        if not expires_at:
            is_active = bool(product.sale_ok and product.website_published)
            return {
                'is_active': is_active,
                'status_label': 'Aktif' if is_active else 'Nonaktif',
                'label': 'Tanpa batas' if is_active else 'Belum aktif',
                'expiry_label': 'Tanpa batas' if is_active else 'Belum aktif',
                'state': 'neutral' if is_active else 'inactive',
                'expiry_state': 'neutral' if is_active else 'inactive',
                'days_remaining': False,
            }
        now = fields.Datetime.now()
        if expires_at < now:
            return {
                'is_active': False,
                'status_label': 'Nonaktif',
                'label': 'Masa aktif habis',
                'expiry_label': 'Masa aktif habis',
                'state': 'expired',
                'expiry_state': 'expired',
                'days_remaining': 0,
            }
        days = max(0, int((expires_at.date() - now.date()).days))
        if days <= 0:
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
    def _seller_listing_fee_policy(product_price, currency):
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
        if price <= 0:
            fee = 0.0
            tier_label = 'Harga belum diisi'
        elif price < threshold:
            fee = low_fee
            tier_label = 'Harga < Rp1.000.000'
        else:
            fee = high_fee
            tier_label = 'Harga >= Rp1.000.000'

        return {
            'fee': currency.round(fee),
            'percent': 0.0,
            'percent_label': 'Biaya tetap',
            'tier_label': tier_label,
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
        admin_fee = get_amount('unitrade.seller.posting_admin_fee', 0)
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

    def _seller_dashboard_product_payloads(self, seller):
        payloads = []
        for product in self._seller_dashboard_products(seller):
            expiry = self._listing_expiry(product)
            payloads.append({
                'id': product.id,
                'name': product.name,
                'price_label': self._format_money(
                    product._unitrade_discounted_price() if hasattr(product, '_unitrade_discounted_price') else product.list_price,
                    request.website.currency_id,
                ),
                'image_url': self._seller_product_image_url(product),
                'url': product.website_url or '/unitrade/product/%s' % product.id,
                'listing_fee_label': self._format_money(_safe_get(product, 'x_listing_fee', 0.0), request.website.currency_id),
                'expiry_label': expiry['label'],
                'expiry_state': expiry['state'],
                'stock_label': self._stock_label(product),
                'rating_label': '%.1f' % (_safe_get(product, 'x_average_rating', 0.0) or 0.0),
            })
        return payloads

    def _seller_dashboard_date(self, value=None):
        if value:
            try:
                parsed = fields.Date.to_date(str(value)[:10])
                if parsed:
                    return parsed
            except Exception:
                _logger.debug('Invalid seller dashboard date filter: %s', value)
        return fields.Date.context_today(request.env.user)

    @staticmethod
    def _seller_dashboard_date_mode(value=None):
        return value if value in ('day', 'month', 'all') else 'day'

    @staticmethod
    def _seller_dashboard_orders_period(value=None):
        return value if value in ('weekly', 'monthly') else 'weekly'

    def _seller_dashboard_date_bounds(self, value=None, mode='day'):
        selected_date = self._seller_dashboard_date(value)
        mode = self._seller_dashboard_date_mode(mode)
        if mode == 'all':
            return selected_date, False, False, False

        try:
            user_tz = pytz.timezone(request.env.user.tz or 'UTC')
        except Exception:
            user_tz = pytz.UTC
        start_date = selected_date - timedelta(days=29) if mode == 'month' else selected_date
        local_start = user_tz.localize(datetime.combine(start_date, time.min))
        local_end = local_start + timedelta(days=1)
        if mode == 'month':
            local_end = user_tz.localize(datetime.combine(selected_date, time.min)) + timedelta(days=1)
        return (
            selected_date,
            local_start.astimezone(pytz.UTC).replace(tzinfo=None),
            local_end.astimezone(pytz.UTC).replace(tzinfo=None),
            start_date,
        )

    def _seller_dashboard_date_payload(self, selected_date, mode='day', start_date=False):
        today = fields.Date.context_today(request.env.user)
        mode = self._seller_dashboard_date_mode(mode)
        if mode == 'all':
            label = 'Semua Waktu'
            display_label = 'Semua Waktu'
        elif mode == 'month':
            start = start_date or (selected_date - timedelta(days=29))
            label = '1 Bulan'
            display_label = '%s - %s' % (start.strftime('%d/%m/%Y'), selected_date.strftime('%d/%m/%Y'))
        else:
            label = selected_date.strftime('%d/%m/%Y')
            display_label = label
        return {
            'value': selected_date.isoformat(),
            'mode': mode,
            'label': label,
            'display_label': display_label,
            'today_value': today.isoformat(),
            'is_today': selected_date == today,
        }

    def _seller_dashboard_orders_bounds(self, selected_date, period='weekly'):
        period = self._seller_dashboard_orders_period(period)
        try:
            user_tz = pytz.timezone(request.env.user.tz or 'UTC')
        except Exception:
            user_tz = pytz.UTC
        days = 30 if period == 'monthly' else 7
        start_date = selected_date - timedelta(days=days - 1)
        local_start = user_tz.localize(datetime.combine(start_date, time.min))
        local_end = user_tz.localize(datetime.combine(selected_date, time.min)) + timedelta(days=1)
        return (
            local_start.astimezone(pytz.UTC).replace(tzinfo=None),
            local_end.astimezone(pytz.UTC).replace(tzinfo=None),
        )

    def _seller_dashboard_order_lines(self, seller, limit=None, revenue_only=False, date_start=False, date_end=False, offset=0, extra_domain=None):
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
        if date_start:
            domain.append(('order_id.date_order', '>=', fields.Datetime.to_string(date_start)))
        if date_end:
            domain.append(('order_id.date_order', '<', fields.Datetime.to_string(date_end)))
        if extra_domain:
            domain = expression.AND([domain, extra_domain])
        return SaleOrderLine.search(domain, order='create_date desc, id desc', offset=offset, limit=limit)

    @staticmethod
    def _seller_orders_status_filter(value):
        value = str(value or 'all').strip().lower()
        return value if value in ('all', 'new', 'processing', 'done', 'cancel') else 'all'

    @staticmethod
    def _seller_orders_page_number(value):
        try:
            page = int(value or 1)
        except (TypeError, ValueError):
            page = 1
        return max(1, page)

    @staticmethod
    def _seller_orders_page_size(value):
        try:
            page_size = int(value or 10)
        except (TypeError, ValueError):
            page_size = 10
        return min(max(page_size, 5), 50)

    def _seller_orders_search_domain(self, query):
        query = self._seller_search_text(query)
        if not query:
            return []
        return ['|', '|', '|', '|',
            ('order_id.name', 'ilike', query),
            ('order_id.partner_id.name', 'ilike', query),
            ('order_id.partner_id.email', 'ilike', query),
            ('name', 'ilike', query),
            ('product_id.default_code', 'ilike', query),
        ]

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

    @staticmethod
    def _ledger_for_order_seller(order, seller):
        if 'unitrade.escrow.ledger' not in request.env.registry:
            return request.env['sale.order'].browse()
        return request.env['unitrade.escrow.ledger'].sudo().search([
            ('order_id', '=', order.id),
            ('seller_id', '=', seller.id),
        ], order='create_date desc', limit=1)

    def _order_status_payload(self, order, delivery=False, ledger=False):
        if hasattr(order, 'unitrade_status_payload'):
            status = dict(order.sudo().unitrade_status_payload(ledger=ledger))
            seller_key_map = {
                'unpaid': 'pending',
                'confirmation': 'processing',
                'refund': 'refund',
                'processing': 'processing',
                'done': 'done',
                'cancel': 'cancel',
            }
            status['key'] = seller_key_map.get(status.get('key'), status.get('key') or 'processing')
            return status
        payment_status = _safe_get(order, 'x_payment_status', '') or ''
        unitrade_state = _safe_get(order, 'x_unitrade_order_state', '') or ''
        delivery_status = delivery.status if delivery else ''
        if order.state == 'cancel':
            return {'key': 'cancel', 'label': 'Dibatalkan'}
        if payment_status == 'refunded' or unitrade_state == 'refunded':
            return {'key': 'cancel', 'label': 'Refund'}
        if ledger and ledger.state == 'disputed':
            return {'key': 'refund', 'label': 'Refund review'}
        if unitrade_state == 'completed':
            return {'key': 'done', 'label': 'Selesai'}
        if unitrade_state == 'cancelled':
            return {'key': 'cancel', 'label': 'Dibatalkan'}
        if delivery_status == 'delivered':
            return {'key': 'done', 'label': 'Terkirim'}
        if delivery_status in ('picked_up', 'in_transit'):
            return {'key': 'shipping', 'label': 'Dikirim'}
        if payment_status in ('failed', 'expired'):
            return {'key': 'cancel', 'label': 'Pembayaran gagal'}
        if payment_status == 'pending':
            return {'key': 'pending', 'label': 'Menunggu bayar'}
        if payment_status == 'paid':
            buyer_confirmed = bool(ledger and ledger.buyer_confirmed_at)
            seller_confirmed = bool(ledger and ledger.seller_confirmed_at)
            if seller_confirmed and not buyer_confirmed:
                return {'key': 'processing', 'label': 'Menunggu buyer'}
            if buyer_confirmed and seller_confirmed:
                return {'key': 'done', 'label': 'Selesai'}
            return {'key': 'processing', 'label': 'Perlu diserahkan'}
        if order.state in ('sale', 'done'):
            return {'key': 'processing', 'label': 'Perlu diproses'}
        return {'key': 'pending', 'label': 'Masuk'}

    @staticmethod
    def _unitrade_initials(name):
        return ''.join(
            part[:1].upper()
            for part in (name or 'UT').split()
            if part
        )[:2] or 'UT'

    def _customer_avatar_payload(self, order):
        partner = order.partner_id
        user = request.env['res.users'].sudo().search([
            ('partner_id', '=', partner.id),
        ], limit=1)
        customer_name = partner.name or (user.name if user else '') or 'Pembeli UniTrade'
        user_image = (
            _safe_get(user, 'avatar_128', False)
            or _safe_get(user, 'image_128', False)
            or _safe_get(user, 'image_1920', False)
            or _safe_get(user.partner_id, 'avatar_128', False)
            or _safe_get(user.partner_id, 'image_128', False)
            or _safe_get(user.partner_id, 'image_1920', False)
        ) if user else False
        if user_image:
            return {
                'url': image_data_uri(user_image),
                'initials': self._unitrade_initials(customer_name),
            }
        partner_image = (
            _safe_get(partner, 'avatar_128', False)
            or _safe_get(partner, 'image_128', False)
            or _safe_get(partner, 'image_1920', False)
        ) if partner else False
        if partner_image:
            return {
                'url': image_data_uri(partner_image),
                'initials': self._unitrade_initials(customer_name),
            }
        return {
            'url': '',
            'initials': self._unitrade_initials(customer_name),
        }

    def _customer_avatar_url(self, order):
        return self._customer_avatar_payload(order)['url']

    def _customer_avatar_payloads(self, orders):
        partners = orders.mapped('partner_id')
        users = request.env['res.users'].sudo().search([
            ('partner_id', 'in', partners.ids),
        ]) if partners else request.env['res.users'].browse()
        users_by_partner = {}
        for user in users:
            users_by_partner.setdefault(user.partner_id.id, user)

        payloads = {}
        for order in orders:
            partner = order.partner_id
            user = users_by_partner.get(partner.id)
            customer_name = partner.name or (user.name if user else '') or 'Pembeli UniTrade'
            user_image = (
                _safe_get(user, 'avatar_128', False)
                or _safe_get(user, 'image_128', False)
                or _safe_get(user, 'image_1920', False)
                or _safe_get(user.partner_id, 'avatar_128', False)
                or _safe_get(user.partner_id, 'image_128', False)
                or _safe_get(user.partner_id, 'image_1920', False)
            ) if user else False
            partner_image = (
                _safe_get(partner, 'avatar_128', False)
                or _safe_get(partner, 'image_128', False)
                or _safe_get(partner, 'image_1920', False)
            ) if partner else False
            url = image_data_uri(user_image or partner_image) if (user_image or partner_image) else ''
            payloads[order.id] = {
                'url': url,
                'initials': self._unitrade_initials(customer_name),
            }
        return payloads

    def _seller_orders_related_maps(self, seller, lines, include_conversations=True, include_refunds=True, include_avatars=True):
        orders = lines.mapped('order_id')
        order_ids = orders.ids
        maps = {
            'deliveries': self._delivery_by_order(order_ids),
            'ledgers': {},
            'conversations': {},
            'refunds_by_order': {},
            'refunds_by_ledger': {},
            'avatars': self._customer_avatar_payloads(orders) if include_avatars else {},
        }

        if order_ids and 'unitrade.escrow.ledger' in request.env.registry:
            ledger_records = request.env['unitrade.escrow.ledger'].sudo().search([
                ('order_id', 'in', order_ids),
                ('seller_id', '=', seller.id),
            ], order='create_date desc, id desc')
            for ledger in ledger_records:
                maps['ledgers'].setdefault(ledger.order_id.id, ledger)

        if include_refunds and order_ids and 'unitrade.dispute' in request.env.registry:
            Dispute = request.env['unitrade.dispute'].sudo()
            ledger_ids = [ledger.id for ledger in maps['ledgers'].values()]
            domain = [('order_id', 'in', order_ids)]
            if ledger_ids and 'escrow_ledger_id' in Dispute._fields:
                domain = expression.OR([domain, [('escrow_ledger_id', 'in', ledger_ids)]])
            disputes = Dispute.search(domain, order='create_date desc, id desc')
            for dispute in disputes:
                if 'escrow_ledger_id' in Dispute._fields and dispute.escrow_ledger_id:
                    maps['refunds_by_ledger'].setdefault(dispute.escrow_ledger_id.id, dispute)
                if dispute.order_id:
                    maps['refunds_by_order'].setdefault(dispute.order_id.id, dispute)

        if include_conversations and order_ids and 'unitrade.chat.conversation' in request.env.registry:
            buyer_users = request.env['res.users'].sudo().search([
                ('partner_id', 'in', orders.mapped('partner_id').ids),
            ])
            if buyer_users:
                chat_records = request.env['unitrade.chat.conversation'].sudo().search([
                    ('seller_id', '=', seller.id),
                    ('buyer_user_id', 'in', buyer_users.ids),
                    ('active', '=', True),
                ], order='last_message_date desc, create_date desc, id desc')
                for conversation in chat_records:
                    maps['conversations'].setdefault(conversation.buyer_user_id.partner_id.id, conversation)
        return maps

    def _seller_order_payload_from_line(self, seller, line, related_maps):
        order = line.order_id
        ledger = related_maps['ledgers'].get(order.id)
        raw_status = self._order_status_payload(order, related_maps['deliveries'].get(order.id), ledger=ledger)
        filter_key = self._seller_orders_filter_key(raw_status['key'])
        conversation = related_maps['conversations'].get(order.partner_id.id)
        refund_dispute = (
            related_maps['refunds_by_ledger'].get(ledger.id)
            if ledger else False
        ) or related_maps['refunds_by_order'].get(order.id)
        can_confirm_handoff = bool(
            ledger
            and order.x_payment_status == 'paid'
            and order.x_unitrade_order_state not in ('cancelled', 'completed')
            and not ledger.seller_confirmed_at
            and ledger.state not in ('cancelled', 'refunded', 'disputed', 'released')
        )
        customer_avatar = related_maps['avatars'].get(order.id) or self._customer_avatar_payload(order)
        return {
            'id': line.id,
            'order_id': order.id,
            'order_name': order.name,
            'customer_name': order.partner_id.name or 'Pembeli UniTrade',
            'customer_avatar_url': customer_avatar['url'],
            'customer_initials': customer_avatar['initials'],
            'product_name': line.product_id.product_tmpl_id.name or line.name,
            'product_qty': int(line.product_uom_qty) if float(line.product_uom_qty or 0).is_integer() else line.product_uom_qty,
            'product_image_url': self._seller_product_image_url(line.product_id.product_tmpl_id) if line.product_id else '',
            'total_label': self._format_money(line.price_total, order.currency_id),
            'status_key': filter_key,
            'status_label': raw_status.get('label') or self._seller_orders_status_label(filter_key),
            'date_label': self._format_order_datetime_label(order.date_order),
            'order_status_url': '/unitrade/order/status/%s' % order.id,
            'detail_url': '/unitrade/seller/orders/%s' % order.id,
            'order_detail_url': '/unitrade/seller/orders/%s' % order.id,
            'ledger_id': ledger.id if ledger else 0,
            'buyer_confirmed': bool(ledger and ledger.buyer_confirmed_at),
            'seller_confirmed': bool(ledger and ledger.seller_confirmed_at),
            'seller_evidence': bool(ledger and ledger.seller_handoff_image),
            'can_confirm_handoff': can_confirm_handoff,
            'confirm_handoff_url': '/seller/order/%s/confirm-handoff' % ledger.id if ledger else '',
            'refund_dispute_id': refund_dispute.id if refund_dispute else 0,
            'refund_state': refund_dispute.state if refund_dispute else '',
            'refund_detail_url': self._seller_refund_detail_url(refund_dispute) if refund_dispute else '',
            'can_respond_refund': bool(refund_dispute and refund_dispute.state in ('submitted', 'under_review', 'need_seller_response')),
            'refund_response_url': '/seller/refund/%s/respond' % refund_dispute.id if refund_dispute else '',
            'action_url': '/unitrade/seller/chat?conversation_id=%s' % conversation.id if conversation else '/unitrade/seller/chat',
        }

    def _seller_dashboard_order_payloads(self, seller, limit=6, date_start=False, date_end=False):
        lines = self._seller_dashboard_order_lines(seller, limit=limit, date_start=date_start, date_end=date_end)
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
            ledger = self._ledger_for_order_seller(order, seller)
            status = self._order_status_payload(order, deliveries.get(order.id), ledger=ledger)
            conversation = conversations.get(order.partner_id.id)
            refund_dispute = self._seller_refund_dispute(order, ledger)
            can_confirm_handoff = bool(
                ledger
                and order.x_payment_status == 'paid'
                and order.x_unitrade_order_state not in ('cancelled', 'completed')
                and not ledger.seller_confirmed_at
                and ledger.state not in ('cancelled', 'refunded', 'disputed', 'released')
            )
            customer_avatar = self._customer_avatar_payload(order)
            payloads.append({
                'order_name': order.name,
                'customer_name': order.partner_id.name or 'Pembeli UniTrade',
                'customer_avatar_url': customer_avatar['url'],
                'customer_initials': customer_avatar['initials'],
                'product_name': line.product_id.product_tmpl_id.name,
                'date_label': self._format_datetime_label(order.date_order),
                'total_label': self._format_money(line.price_total, order.currency_id),
                'status_key': status['key'],
                'status_label': status['label'],
                'detail_url': '/unitrade/seller/orders/%s' % order.id,
                'order_detail_url': '/unitrade/seller/orders/%s' % order.id,
                'ledger_id': ledger.id if ledger else 0,
                'buyer_confirmed': bool(ledger and ledger.buyer_confirmed_at),
                'seller_confirmed': bool(ledger and ledger.seller_confirmed_at),
                'seller_evidence': bool(ledger and ledger.seller_handoff_image),
                'can_confirm_handoff': can_confirm_handoff,
                'confirm_handoff_url': '/seller/order/%s/confirm-handoff' % ledger.id if ledger else '',
                'refund_dispute_id': refund_dispute.id if refund_dispute else 0,
                'refund_state': refund_dispute.state if refund_dispute else '',
                'refund_detail_url': self._seller_refund_detail_url(refund_dispute) if refund_dispute else '',
                'can_respond_refund': bool(refund_dispute and refund_dispute.state in ('submitted', 'under_review', 'need_seller_response')),
                'refund_response_url': '/seller/refund/%s/respond' % refund_dispute.id if refund_dispute else '',
                'action_url': '/unitrade/seller/chat?conversation_id=%s' % conversation.id if conversation else '/unitrade/seller/chat',
            })
        return payloads

    @staticmethod
    def _seller_orders_filter_key(status_key):
        if status_key == 'done':
            return 'done'
        if status_key in ('cancel', 'refund'):
            return 'cancel'
        if status_key in ('processing', 'shipping'):
            return 'processing'
        return 'new'

    @staticmethod
    def _seller_orders_status_label(filter_key):
        return {
            'new': 'Baru',
            'processing': 'Diproses',
            'done': 'Selesai',
            'cancel': 'Dibatalkan',
        }.get(filter_key, 'Baru')

    def _seller_orders_payloads(self, seller, query='', status_filter='all', page=1, page_size=10):
        query = self._seller_search_text(query)
        status_filter = self._seller_orders_status_filter(status_filter)
        page = self._seller_orders_page_number(page)
        page_size = self._seller_orders_page_size(page_size)
        lines = self._seller_dashboard_order_lines(
            seller,
            extra_domain=self._seller_orders_search_domain(query),
        )
        related_maps = self._seller_orders_related_maps(seller, lines)
        counts = {
            'all': 0,
            'new': 0,
            'processing': 0,
            'done': 0,
            'cancel': 0,
        }
        filtered_payloads = []
        for line in lines:
            payload = self._seller_order_payload_from_line(seller, line, related_maps)
            filter_key = payload['status_key']
            counts['all'] += 1
            counts[filter_key] += 1
            if status_filter == 'all' or filter_key == status_filter:
                filtered_payloads.append(payload)
        total = len(filtered_payloads)
        total_pages = max(1, int(math.ceil(float(total) / float(page_size)))) if total else 1
        page = min(page, total_pages)
        offset = (page - 1) * page_size
        return {
            'orders': filtered_payloads[offset:offset + page_size],
            'counts': counts,
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
            'status_filter': status_filter,
        }

    def _seller_orders_context(self, seller):
        _, unread_chat_count = self._seller_dashboard_chat_payloads(seller)
        pending_order_count = self._seller_dashboard_pending_order_count(seller)
        return {
            'seller': seller,
            'seller_public_ref': self._seller_public_ref(seller),
            'seller_avatar_url': '/web/image/res.users/%s/avatar_128?unique=%s' % (
                seller.user_id.id,
                seller.user_id.write_date or '',
            ),
            'notification_count': pending_order_count + unread_chat_count,
            'unread_chat_count': unread_chat_count,
            'page_title': 'Pesanan Penjual - UniTrade',
        }

    def _seller_order_lines_for_order(self, seller, order):
        SaleOrderLine = request.env['sale.order.line'].sudo()
        Product = request.env['product.template'].sudo()
        if not seller or not order or 'x_seller_id' not in Product._fields:
            return SaleOrderLine.browse()
        return SaleOrderLine.search([
            ('order_id', '=', order.id),
            ('display_type', '=', False),
            ('product_id', '!=', False),
            ('product_id.product_tmpl_id.x_seller_id', '=', seller.id),
        ], order='id asc')

    @staticmethod
    def _format_datetime_detail_label(value):
        if not value:
            return ''
        try:
            localized = fields.Datetime.context_timestamp(request.env.user, value)
        except Exception:
            localized = value
        return localized.strftime('%d %b %Y, %H:%M')

    @staticmethod
    def _binary_image_uri(value):
        if not value:
            return ''
        try:
            return image_data_uri(value)
        except Exception:
            return ''

    def _seller_order_conversation(self, seller, order):
        if 'unitrade.chat.conversation' not in request.env.registry:
            return request.env['sale.order'].browse()
        buyer_user = request.env['res.users'].sudo().search([
            ('partner_id', '=', order.partner_id.id),
        ], limit=1)
        if not buyer_user:
            return request.env['unitrade.chat.conversation'].sudo().browse()
        return request.env['unitrade.chat.conversation'].sudo().search([
            ('seller_id', '=', seller.id),
            ('buyer_user_id', '=', buyer_user.id),
            ('active', '=', True),
        ], order='last_message_date desc, create_date desc', limit=1)

    @staticmethod
    def _seller_ledger_state_label(state):
        return {
            'held': 'Dana ditahan',
            'releasable': 'Siap dicairkan',
            'released': 'Sudah dicairkan',
            'disputed': 'Sedang ditinjau',
            'refunded': 'Dikembalikan',
            'cancelled': 'Dibatalkan',
        }.get(state or '', 'Belum tersedia')

    @staticmethod
    def _seller_payout_state_label(state):
        return {
            'draft': 'Belum diajukan',
            'pending': 'Menunggu pencairan',
            'processing': 'Diproses',
            'succeeded': 'Berhasil',
            'failed': 'Gagal',
        }.get(state or '', 'Belum diajukan')

    @staticmethod
    def _seller_payment_status_label(state):
        return {
            'pending': 'Menunggu pembayaran',
            'paid': 'Pembayaran berhasil',
            'failed': 'Pembayaran gagal',
            'expired': 'Pembayaran kedaluwarsa',
            'cancelled': 'Pembayaran dibatalkan',
            'refunded': 'Dana dikembalikan',
        }.get(state or '', 'Belum dibayar')

    def _seller_order_detail_payload(self, seller, order):
        lines = self._seller_order_lines_for_order(seller, order)
        deliveries = self._delivery_by_order([order.id])
        ledger = self._ledger_for_order_seller(order, seller)
        raw_status = self._order_status_payload(order, deliveries.get(order.id), ledger=ledger)
        status_key = self._seller_orders_filter_key(raw_status.get('key'))
        refund_dispute = self._seller_refund_dispute(order, ledger)
        conversation = self._seller_order_conversation(seller, order)
        currency = order.currency_id or request.website.currency_id or request.env.company.currency_id
        seller_total = currency.round(sum(lines.mapped('price_total')))
        seller_subtotal = currency.round(sum(lines.mapped('price_subtotal')))
        quantity_total = sum(lines.mapped('product_uom_qty'))
        shipping_partner = order.partner_shipping_id or order.partner_id
        shipping_address = self._partner_address_payload(shipping_partner).get('line') if shipping_partner else ''
        payment_status = _safe_get(order, 'x_payment_status', '') or ''
        unitrade_state = _safe_get(order, 'x_unitrade_order_state', '') or ''
        seller_confirmed = bool(ledger and ledger.seller_confirmed_at)
        buyer_confirmed = bool(ledger and ledger.buyer_confirmed_at)
        payment_done = payment_status in ('paid', 'refunded') or unitrade_state == 'completed'
        order_done = unitrade_state == 'completed'
        can_confirm_handoff = bool(
            ledger
            and payment_status == 'paid'
            and unitrade_state not in ('cancelled', 'completed')
            and not ledger.seller_confirmed_at
            and ledger.state not in ('cancelled', 'refunded', 'disputed', 'released')
        )

        line_values = []
        for line in lines:
            qty = float(line.product_uom_qty or 0.0)
            line_values.append({
                'id': line.id,
                'product_name': line.product_id.product_tmpl_id.name or line.name,
                'description': line.name or '',
                'qty': int(qty) if qty.is_integer() else qty,
                'unit_price_label': self._format_money(line.price_unit, currency),
                'subtotal_label': self._format_money(line.price_total, currency),
                'image_url': self._seller_product_image_url(line.product_id.product_tmpl_id) if line.product_id else '',
            })

        timeline = [
            {
                'label': 'Pembayaran',
                'caption': self._seller_payment_status_label(payment_status),
                'done': payment_done,
                'active': not payment_done and status_key == 'new',
            },
            {
                'label': 'Barang diserahkan',
                'caption': self._format_datetime_detail_label(ledger.seller_confirmed_at) if seller_confirmed else 'Menunggu bukti penjual',
                'done': seller_confirmed,
                'active': payment_done and not seller_confirmed and not order_done,
            },
            {
                'label': 'Barang diterima',
                'caption': self._format_datetime_detail_label(ledger.buyer_confirmed_at) if buyer_confirmed else 'Menunggu konfirmasi pembeli',
                'done': buyer_confirmed,
                'active': seller_confirmed and not buyer_confirmed and not order_done,
            },
            {
                'label': 'Selesai',
                'caption': self._seller_ledger_state_label(ledger.state if ledger else ''),
                'done': bool(order_done or (ledger and ledger.state in ('releasable', 'released'))),
                'active': order_done,
            },
        ]

        chat_url = '/unitrade/seller/chat?conversation_id=%s' % conversation.id if conversation else '/unitrade/seller/chat'
        detail_url = '/unitrade/seller/orders/%s' % order.id
        pending_order_count = self._seller_dashboard_pending_order_count(seller)
        unread_chat_count = self._seller_dashboard_chat_payloads(seller)[1]
        customer_avatar = self._customer_avatar_payload(order)
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
                'incoming_orders': pending_order_count,
                'notification_count': pending_order_count + unread_chat_count,
                'unread_chat_count': unread_chat_count,
            },
            'order': {
                'id': order.id,
                'name': order.name,
                'date_label': self._format_datetime_detail_label(order.date_order),
                'status_key': status_key,
                'status_label': raw_status.get('label') or self._seller_orders_status_label(status_key),
                'payment_status_label': self._seller_payment_status_label(payment_status),
                'customer_name': order.partner_id.name or 'Pembeli UniTrade',
                'customer_avatar_url': customer_avatar['url'],
                'customer_initials': customer_avatar['initials'],
                'customer_email': order.partner_id.email or '',
                'customer_phone': shipping_partner.mobile or shipping_partner.phone or order.partner_id.mobile or order.partner_id.phone or '',
                'shipping_address': shipping_address or 'Alamat belum dilengkapi',
                'seller_total_label': self._format_money(seller_total, currency),
                'seller_subtotal_label': self._format_money(seller_subtotal, currency),
                'order_total_label': self._format_money(order.amount_total, currency),
                'qty_total': int(quantity_total) if float(quantity_total or 0.0).is_integer() else quantity_total,
                'line_count': len(lines),
                'lines': line_values,
                'ledger_id': ledger.id if ledger else 0,
                'ledger_name': ledger.name if ledger else '',
                'ledger_state': ledger.state if ledger else '',
                'ledger_state_label': self._seller_ledger_state_label(ledger.state if ledger else ''),
                'payout_status_label': self._seller_payout_state_label(ledger.payout_status if ledger else ''),
                'amount_seller_label': self._format_money(ledger.amount_seller if ledger else seller_subtotal, currency),
                'amount_total_label': self._format_money(ledger.amount_total if ledger else seller_total, currency),
                'platform_fee_label': self._format_money(ledger.amount_platform_fee if ledger else 0.0, currency),
                'gateway_fee_label': self._format_money(ledger.amount_gateway_fee if ledger else 0.0, currency),
                'buyer_confirmed': buyer_confirmed,
                'seller_confirmed': seller_confirmed,
                'seller_evidence_url': self._binary_image_uri(ledger.seller_handoff_image) if ledger else '',
                'buyer_evidence_url': self._binary_image_uri(ledger.buyer_received_image) if ledger else '',
                'seller_handoff_location': ledger.seller_handoff_location if ledger else '',
                'seller_confirmed_at_label': self._format_datetime_detail_label(ledger.seller_confirmed_at) if ledger else '',
                'buyer_confirmed_at_label': self._format_datetime_detail_label(ledger.buyer_confirmed_at) if ledger else '',
                'can_confirm_handoff': can_confirm_handoff,
                'confirm_handoff_url': '/seller/order/%s/confirm-handoff' % ledger.id if ledger else '',
                'detail_url': detail_url,
                'orders_url': '/unitrade/seller/orders',
                'chat_url': chat_url,
                'refund_detail_url': self._seller_refund_detail_url(refund_dispute) if refund_dispute else '',
                'refund_state_label': dict(refund_dispute._fields['state'].selection).get(refund_dispute.state, refund_dispute.state) if refund_dispute else '',
                'can_respond_refund': bool(refund_dispute and refund_dispute.state in ('submitted', 'under_review', 'need_seller_response')),
            },
            'timeline': timeline,
            'csrf_token': request.csrf_token(),
        }

    def _seller_order_detail_context(self, seller, order):
        payload = self._seller_order_detail_payload(seller, order)
        return {
            'seller': seller,
            'seller_public_ref': self._seller_public_ref(seller),
            'seller_avatar_url': payload['seller']['avatar_url'],
            'notification_count': payload['stats']['notification_count'],
            'unread_chat_count': payload['stats']['unread_chat_count'],
            'seller_order_detail_payload_json': json.dumps(payload),
            'page_title': '%s - Detail Pesanan Seller' % (order.name or 'Detail Pesanan'),
        }

    @staticmethod
    def _seller_refund_dispute(order, ledger=False):
        if 'unitrade.dispute' not in request.env.registry:
            return request.env['sale.order'].browse()
        domain = [('order_id', '=', order.id)]
        if ledger:
            domain.append(('escrow_ledger_id', '=', ledger.id))
        return request.env['unitrade.dispute'].sudo().search(domain, order='create_date desc', limit=1)

    @staticmethod
    def _seller_refund_detail_url(dispute):
        return '/unitrade/seller/refunds/%s' % dispute.id if dispute else ''

    @staticmethod
    def _seller_refunds_status_filter(value):
        value = str(value or 'all').strip().lower()
        return value if value in ('all', 'approved', 'rejected', 'waiting', 'done') else 'all'

    @staticmethod
    def _seller_refunds_page_number(value):
        try:
            page = int(value or 1)
        except (TypeError, ValueError):
            page = 1
        return max(1, page)

    @staticmethod
    def _seller_refunds_page_size(value):
        try:
            page_size = int(value or 6)
        except (TypeError, ValueError):
            page_size = 6
        return min(max(page_size, 5), 25)

    @staticmethod
    def _seller_refunds_date_value(value):
        if not value:
            return ''
        try:
            parsed = fields.Date.to_date(str(value)[:10])
        except Exception:
            parsed = False
        return parsed.isoformat() if parsed else ''

    def _seller_refunds_date_bound(self, value, is_end=False):
        date_value = self._seller_refunds_date_value(value)
        if not date_value:
            return False
        parsed = fields.Date.to_date(date_value)
        try:
            user_tz = pytz.timezone(request.env.user.tz or 'UTC')
        except Exception:
            user_tz = pytz.UTC
        local_start = user_tz.localize(datetime.combine(parsed, time.min))
        if is_end:
            local_start += timedelta(days=1)
        return local_start.astimezone(pytz.UTC).replace(tzinfo=None)

    def _seller_refunds_base_domain(self, seller):
        domain = [('dispute_type', '=', 'refund')]
        seller_domains = [[('seller_id', '=', seller.id)]]
        seller_lines = self._seller_dashboard_order_lines(seller)
        if seller_lines:
            seller_domains.append([
                ('seller_id', '=', False),
                ('order_line_id', 'in', seller_lines.ids),
            ])
            seller_domains.append([
                ('seller_id', '=', False),
                ('order_line_id', '=', False),
                ('order_id', 'in', seller_lines.mapped('order_id').ids),
            ])
        return expression.AND([domain, expression.OR(seller_domains)])

    def _seller_refunds_search_domain(self, query):
        query = self._seller_search_text(query)
        if not query:
            return []
        return ['|', '|', '|', '|', '|',
            ('order_id.name', 'ilike', query),
            ('name', 'ilike', query),
            ('buyer_id.name', 'ilike', query),
            ('buyer_id.email', 'ilike', query),
            ('order_line_id.name', 'ilike', query),
            ('order_line_id.product_id.name', 'ilike', query),
        ]

    @staticmethod
    def _seller_refund_list_status(state):
        if state == 'approved':
            return {'tab_key': 'approved', 'badge_key': 'approved', 'label': 'Setuju'}
        if state == 'resolved':
            return {'tab_key': 'done', 'badge_key': 'done', 'label': 'Selesai'}
        if state == 'rejected':
            return {'tab_key': 'rejected', 'badge_key': 'rejected', 'label': 'Ditolak'}
        if state == 'cancelled':
            return {'tab_key': 'rejected', 'badge_key': 'rejected', 'label': 'Dibatalkan'}
        if state == 'need_buyer_evidence':
            return {'tab_key': 'waiting', 'badge_key': 'waiting', 'label': 'Menunggu Barang'}
        if state == 'need_seller_response':
            return {'tab_key': 'waiting', 'badge_key': 'waiting', 'label': 'Konfirmasi Barang'}
        if state == 'under_review':
            return {'tab_key': 'waiting', 'badge_key': 'waiting', 'label': 'Diproses'}
        if state == 'admin_review_final':
            return {'tab_key': 'waiting', 'badge_key': 'waiting', 'label': 'Review Final Admin'}
        return {'tab_key': 'waiting', 'badge_key': 'new', 'label': 'Baru'}

    @staticmethod
    def _seller_refund_status_label(state):
        return {
            'draft': 'Draft',
            'submitted': 'Menunggu Review',
            'under_review': 'Menunggu Review',
            'admin_review_final': 'Review Final Admin',
            'need_buyer_evidence': 'Menunggu Barang Kembali',
            'need_seller_response': 'Konfirmasi Barang Kembali',
            'approved': 'Disetujui',
            'rejected': 'Ditolak',
            'resolved': 'Selesai',
            'cancelled': 'Dibatalkan',
        }.get(state or '', state or '-')

    @staticmethod
    def _seller_refund_status_key(state):
        if state in ('approved', 'resolved'):
            return 'approved'
        if state == 'rejected':
            return 'rejected'
        if state == 'cancelled':
            return 'cancelled'
        if state in ('submitted', 'under_review', 'need_buyer_evidence', 'need_seller_response', 'admin_review_final'):
            return 'review'
        return 'draft'

    @staticmethod
    def _format_file_size(size):
        try:
            size = float(size or 0)
        except (TypeError, ValueError):
            size = 0.0
        if size >= 1024 * 1024:
            return '%.1f MB' % (size / (1024 * 1024))
        if size >= 1024:
            return '%.0f KB' % (size / 1024)
        return '%s B' % int(size)

    def _seller_refund_dispute_for_seller(self, seller, dispute_id):
        if 'unitrade.dispute' not in request.env.registry:
            return request.env['sale.order'].browse()
        try:
            dispute_id = int(dispute_id or 0)
        except (TypeError, ValueError):
            dispute_id = 0
        dispute = request.env['unitrade.dispute'].sudo().browse(dispute_id).exists()
        if not dispute:
            return request.env['unitrade.dispute'].sudo().browse()
        if dispute.seller_id:
            return dispute if dispute.seller_id.id == seller.id else request.env['unitrade.dispute'].sudo().browse()
        if dispute.order_line_id:
            line_product = dispute.order_line_id.product_id.product_tmpl_id
            line_seller = _safe_get(line_product, 'x_seller_id', False) if line_product else False
            return dispute if line_seller and line_seller.id == seller.id else request.env['unitrade.dispute'].sudo().browse()
        if dispute.order_id and self._seller_order_lines_for_order(seller, dispute.order_id):
            return dispute
        return request.env['unitrade.dispute'].sudo().browse()

    def _seller_refund_line(self, seller, dispute):
        line = dispute.order_line_id
        seller_lines = self._seller_order_lines_for_order(seller, dispute.order_id)
        if line and line in seller_lines:
            return line
        return seller_lines[:1]

    def _seller_refund_list_payload(self, seller, dispute):
        order = dispute.order_id
        line = self._seller_refund_line(seller, dispute)
        product = line.product_id.product_tmpl_id if line and line.product_id else request.env['product.template'].sudo().browse()
        currency = dispute.currency_id or order.currency_id or request.website.currency_id or request.env.company.currency_id
        customer_avatar = self._customer_avatar_payload(order)
        qty = float(line.product_uom_qty or 1.0) if line else 1.0
        amount = line.price_total if line else (dispute.requested_amount or dispute.total_refund_amount or 0.0)
        status = self._seller_refund_list_status(dispute.state)
        return {
            'id': dispute.id,
            'key': 'refund-%s' % dispute.id,
            'order_id': order.id,
            'order_name': order.name or dispute.name,
            'customer_name': order.partner_id.name or dispute.buyer_id.name or 'Pembeli UniTrade',
            'customer_avatar_url': customer_avatar['url'],
            'customer_initials': customer_avatar['initials'],
            'product_name': product.name or (line.name if line else order.name),
            'product_qty': int(qty) if qty.is_integer() else qty,
            'product_image_url': self._seller_product_image_url(product) if product else '',
            'total_label': self._format_money(amount, currency),
            'status_filter_key': status['tab_key'],
            'status_key': status['badge_key'],
            'status_label': status['label'],
            'date_label': self._format_order_datetime_label(dispute.submitted_at or dispute.create_date),
            'detail_url': self._seller_refund_detail_url(dispute),
        }

    def _seller_refunds_payloads(self, seller, query='', status_filter='all', date_from='', date_to='', page=1, page_size=6):
        if 'unitrade.dispute' not in request.env.registry:
            return {
                'refunds': [],
                'counts': {'all': 0, 'approved': 0, 'rejected': 0, 'waiting': 0, 'done': 0},
                'pagination': {
                    'page': 1,
                    'page_size': self._seller_refunds_page_size(page_size),
                    'total': 0,
                    'total_pages': 1,
                    'has_prev': False,
                    'has_next': False,
                    'start': 0,
                    'end': 0,
                },
                'query': self._seller_search_text(query),
                'status_filter': self._seller_refunds_status_filter(status_filter),
                'date_from': self._seller_refunds_date_value(date_from),
                'date_to': self._seller_refunds_date_value(date_to),
            }

        query = self._seller_search_text(query)
        status_filter = self._seller_refunds_status_filter(status_filter)
        page = self._seller_refunds_page_number(page)
        page_size = self._seller_refunds_page_size(page_size)
        date_from_value = self._seller_refunds_date_value(date_from)
        date_to_value = self._seller_refunds_date_value(date_to)
        domain = self._seller_refunds_base_domain(seller)
        search_domain = self._seller_refunds_search_domain(query)
        if search_domain:
            domain = expression.AND([domain, search_domain])
        date_start = self._seller_refunds_date_bound(date_from_value)
        date_end = self._seller_refunds_date_bound(date_to_value, is_end=True)
        if date_start:
            domain = expression.AND([domain, [('create_date', '>=', fields.Datetime.to_string(date_start))]])
        if date_end:
            domain = expression.AND([domain, [('create_date', '<', fields.Datetime.to_string(date_end))]])

        disputes = request.env['unitrade.dispute'].sudo().search(domain, order='create_date desc, id desc')
        counts = {
            'all': 0,
            'approved': 0,
            'rejected': 0,
            'waiting': 0,
            'done': 0,
        }
        filtered_payloads = []
        for dispute in disputes:
            payload = self._seller_refund_list_payload(seller, dispute)
            filter_key = payload['status_filter_key']
            counts['all'] += 1
            if filter_key in counts:
                counts[filter_key] += 1
            if status_filter == 'all' or filter_key == status_filter:
                filtered_payloads.append(payload)

        total = len(filtered_payloads)
        total_pages = max(1, int(math.ceil(float(total) / float(page_size)))) if total else 1
        page = min(page, total_pages)
        offset = (page - 1) * page_size
        return {
            'refunds': filtered_payloads[offset:offset + page_size],
            'counts': counts,
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
            'status_filter': status_filter,
            'date_from': date_from_value,
            'date_to': date_to_value,
        }

    def _seller_refunds_context(self, seller):
        unread_chat_count = self._seller_dashboard_chat_payloads(seller)[1]
        pending_order_count = self._seller_dashboard_pending_order_count(seller)
        return {
            'seller': seller,
            'seller_public_ref': self._seller_public_ref(seller),
            'seller_avatar_url': '/web/image/res.users/%s/avatar_128?unique=%s' % (
                seller.user_id.id,
                seller.user_id.write_date or '',
            ),
            'notification_count': pending_order_count + unread_chat_count,
            'unread_chat_count': unread_chat_count,
            'page_title': 'Refund Seller - UniTrade',
        }

    def _seller_refund_payment_method_label(self, dispute):
        intent = dispute.payment_intent_id or _safe_get(dispute.order_id, 'x_payment_intent_id', False)
        if intent:
            return intent.payment_method_label or intent.payment_method_code or intent.provider or '-'
        return (
            _safe_get(dispute.order_id, 'x_payment_method_label', False)
            or _safe_get(dispute.order_id, 'x_payment_method', False)
            or '-'
        )

    def _seller_refund_evidence_payloads(self, dispute):
        images = []
        allowed = {'image/jpeg', 'image/png', 'image/webp'}
        image_evidence = dispute.evidence_ids.filtered(
            lambda evidence: evidence.attachment_id and (evidence.attachment_id.mimetype or '') in allowed
        )
        for evidence in image_evidence[:3]:
            attachment = evidence.attachment_id.sudo()
            images.append({
                'id': evidence.id,
                'name': attachment.name or 'Bukti Pembeli',
                'type': dict(evidence._fields['evidence_type'].selection).get(evidence.evidence_type, evidence.evidence_type),
                'note': evidence.note or '',
                'url': '/unitrade/refund/evidence/%s/image' % evidence.id,
                'download_url': '/unitrade/refund/evidence/%s/download' % evidence.id,
                'size_label': self._format_file_size(attachment.file_size or 0),
            })
        return images

    def _seller_refund_timeline_payload(self, dispute, ledger=False):
        order = dispute.order_id
        ledger = ledger or dispute.escrow_ledger_id or self._ledger_for_order_seller(order, dispute.seller_id)
        payment_intent = dispute.payment_intent_id or _safe_get(order, 'x_payment_intent_id', False)
        payment_status = _safe_get(order, 'x_payment_status', '') or (payment_intent.state if payment_intent else '')
        payment_done = payment_status in ('paid', 'refunded') or bool(payment_intent and payment_intent.paid_at)
        seller_done = bool(ledger and ledger.seller_confirmed_at)
        buyer_done = bool(ledger and ledger.buyer_confirmed_at)
        final_approved = dispute.state in ('approved', 'resolved')
        final_rejected = dispute.state == 'rejected'
        final_cancelled = dispute.state == 'cancelled'
        review_active = dispute.state in ('submitted', 'under_review')
        timeline_by_key = {item.event_key: item for item in dispute.timeline_ids}
        has_buyer_return = bool(timeline_by_key.get('buyer_return_sent'))
        has_seller_confirmation = bool(timeline_by_key.get('seller_return_confirmed'))
        review_done = (
            final_approved
            or final_rejected
            or final_cancelled
            or dispute.state in ('need_buyer_evidence', 'need_seller_response', 'admin_review_final')
            or bool(dispute.seller_decision_note)
            or has_buyer_return
            or has_seller_confirmation
        )
        buyer_return_done = final_approved or has_buyer_return or dispute.state == 'need_seller_response'
        buyer_return_active = dispute.state == 'need_buyer_evidence'
        seller_confirm_active = dispute.state == 'need_seller_response'
        seller_confirm_done = final_approved or has_seller_confirmation
        admin_review_active = dispute.state == 'admin_review_final' and bool(has_seller_confirmation or dispute.seller_decision_note)

        def caption_for(key, fallback=''):
            event = timeline_by_key.get(key)
            if event and event.event_time:
                return self._format_datetime_detail_label(event.event_time)
            return fallback

        def step(key, label, done=False, active=False, failed=False, caption=''):
            status = 'failed' if failed else 'done' if done else 'current' if active else 'pending'
            return {
                'key': key,
                'label': label,
                'caption': caption,
                'status': status,
                'done': bool(done),
                'active': bool(active),
                'failed': bool(failed),
            }

        payment_caption = (
            self._format_datetime_detail_label(payment_intent.paid_at)
            if payment_intent and payment_intent.paid_at
            else self._seller_payment_status_label(payment_status)
        )
        steps = [
            step('order_created', 'Pesanan Dibuat', done=bool(order.date_order), caption=self._format_datetime_detail_label(order.date_order)),
            step('payment_received', 'Pembayaran Diterima', done=payment_done, active=not payment_done, caption=payment_caption),
            step(
                'seller_handoff',
                'Barang Diserahkan',
                done=seller_done,
                active=payment_done and not seller_done,
                caption=self._format_datetime_detail_label(ledger.seller_confirmed_at) if seller_done else 'Menunggu bukti seller',
            ),
            step(
                'buyer_received',
                'Barang Diterima',
                done=buyer_done,
                active=seller_done and not buyer_done,
                caption=self._format_datetime_detail_label(ledger.buyer_confirmed_at) if buyer_done else 'Menunggu konfirmasi pembeli',
            ),
            step(
                'return_requested',
                'Pengajuan Retur Dibuat',
                done=bool(dispute.submitted_at or dispute.create_date),
                caption=caption_for('return_requested', self._format_datetime_detail_label(dispute.submitted_at or dispute.create_date)),
            ),
            step(
                'seller_review',
                'Menunggu Review Seller',
                done=review_done,
                active=review_active,
                caption=caption_for('seller_review', self._seller_refund_status_label(dispute.state)),
            ),
        ]
        if final_rejected:
            steps.append(step(
                'refund_rejected',
                'Refund Ditolak',
                done=True,
                failed=True,
                caption=caption_for('refund_rejected', dispute.seller_decision_note or 'Ditolak seller'),
            ))
        elif final_cancelled:
            steps.append(step('refund_cancelled', 'Refund Dibatalkan', done=True, failed=True, caption=caption_for('refund_cancelled', 'Dibatalkan')))
        else:
            steps.extend([
                step(
                    'buyer_return_sent',
                    'Barang Dikembalikan Pembeli',
                    done=buyer_return_done,
                    active=buyer_return_active,
                    caption=caption_for('buyer_return_sent', 'Menunggu pembeli mengirim atau menyerahkan barang kembali'),
                ),
                step(
                    'seller_return_confirmed',
                    'Konfirmasi Barang Kembali',
                    done=seller_confirm_done,
                    active=seller_confirm_active,
                    caption=caption_for('seller_return_confirmed', 'Menunggu seller upload foto bukti penerimaan barang'),
                ),
                step(
                    'admin_review',
                    'Review Final Admin',
                    done=final_approved,
                    active=admin_review_active,
                    failed=final_rejected,
                    caption=caption_for('admin_review', 'Menunggu admin/CS meninjau final'),
                ),
                step('refund_processed', 'Refund Diproses', done=final_approved, caption=caption_for('refund_approved', self._seller_refund_status_label(dispute.state))),
                step('refund_completed', 'Refund Selesai', done=final_approved, caption=caption_for('refund_completed', self._format_datetime_detail_label(dispute.resolved_at) if dispute.resolved_at else 'Menunggu keputusan')),
            ])
        return steps

    def _seller_refund_detail_payload(self, seller, dispute):
        order = dispute.order_id
        line = self._seller_refund_line(seller, dispute)
        product = line.product_id.product_tmpl_id if line and line.product_id else request.env['product.template'].sudo().browse()
        ledger = dispute.escrow_ledger_id or self._ledger_for_order_seller(order, seller)
        currency = dispute.currency_id or order.currency_id or request.website.currency_id or request.env.company.currency_id
        buyer_partner = order.partner_id
        shipping_partner = order.partner_shipping_id or buyer_partner
        customer_avatar = self._customer_avatar_payload(order)
        delivery = self._delivery_by_order([order.id]).get(order.id)
        raw_status = self._order_status_payload(order, delivery, ledger=ledger)
        item_amount = line.price_total if line else dispute.requested_amount
        qty = float(line.product_uom_qty or 1.0) if line else 1.0
        attrs = line.product_id.product_template_attribute_value_ids.mapped('name') if line and line.product_id else []
        pending_order_count = self._seller_dashboard_pending_order_count(seller)
        unread_chat_count = self._seller_dashboard_chat_payloads(seller)[1]
        status_key = self._seller_refund_status_key(dispute.state)
        total_refund = dispute.total_refund_amount or dispute.approved_amount or dispute.requested_amount
        can_decide = dispute.state in ('submitted', 'under_review') and not dispute.seller_decided_at
        can_confirm_return = dispute.state == 'need_seller_response'
        can_reject_return = dispute.state == 'need_seller_response'
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
                'incoming_orders': pending_order_count,
                'notification_count': pending_order_count + unread_chat_count,
                'unread_chat_count': unread_chat_count,
            },
            'refund': {
                'id': dispute.id,
                'name': dispute.name,
                'status': dispute.state,
                'status_key': status_key,
                'status_label': self._seller_refund_status_label(dispute.state),
                'reason_label': dict(dispute._fields['reason_code'].selection).get(dispute.reason_code, dispute.reason_code),
                'reason_note': dispute.reason_note or '',
                'seller_note': dispute.seller_decision_note or '',
                'submitted_at_label': self._format_datetime_detail_label(dispute.submitted_at or dispute.create_date),
                'decision_at_label': self._format_datetime_detail_label(dispute.seller_decided_at or dispute.approved_at or dispute.rejected_at),
                'can_decide': can_decide,
                'can_confirm_return': can_confirm_return,
                'can_reject_return': can_reject_return,
                'decision_url': '/unitrade/seller/refunds/%s/decision' % dispute.id,
                'confirm_return_url': '/seller/refund/%s/confirm-return' % dispute.id,
                'chat_url': '/unitrade/seller/refunds/%s/chat' % dispute.id,
            },
            'order': {
                'id': order.id,
                'name': order.name,
                'date_label': self._format_datetime_detail_label(order.date_order),
                'status_label': raw_status.get('label') or self._seller_orders_status_label(self._seller_orders_filter_key(raw_status.get('key'))),
                'payment_method_label': self._seller_refund_payment_method_label(dispute),
                'detail_url': '/unitrade/seller/orders/%s' % order.id,
            },
            'buyer': {
                'name': buyer_partner.name or 'Pembeli UniTrade',
                'email': buyer_partner.email or '',
                'phone': shipping_partner.mobile or shipping_partner.phone or buyer_partner.mobile or buyer_partner.phone or '',
                'avatar_url': customer_avatar['url'],
                'initials': customer_avatar['initials'],
            },
            'product': {
                'name': product.name or (line.name if line else order.name),
                'variant': ', '.join(attrs) if attrs else (line.name if line and line.name != product.name else ''),
                'qty': int(qty) if qty.is_integer() else qty,
                'unit_price_label': self._format_money(line.price_unit if line else item_amount, currency),
                'amount_label': self._format_money(item_amount, currency),
                'image_url': self._seller_product_image_url(product) if product else '',
            },
            'summary': {
                'item_amount_label': self._format_money(item_amount, currency),
                'admin_fee': dispute.refund_admin_fee_amount or 0.0,
                'admin_fee_label': self._format_money(dispute.refund_admin_fee_amount, currency),
                'total_refund_label': self._format_money(total_refund, currency),
            },
            'evidence': self._seller_refund_evidence_payloads(dispute),
            'timeline': self._seller_refund_timeline_payload(dispute, ledger=ledger),
            'csrf_token': request.csrf_token(),
        }

    def _seller_refund_detail_context(self, seller, dispute):
        payload = self._seller_refund_detail_payload(seller, dispute)
        return {
            'seller': seller,
            'seller_public_ref': self._seller_public_ref(seller),
            'seller_avatar_url': payload['seller']['avatar_url'],
            'notification_count': payload['stats']['notification_count'],
            'unread_chat_count': payload['stats']['unread_chat_count'],
            'seller_refund_detail_payload_json': json.dumps(payload),
            'page_title': '%s - Detail Pengembalian Seller' % (dispute.name or 'Detail Pengembalian'),
        }

    def _seller_dashboard_pending_order_count(self, seller, date_start=False, date_end=False):
        lines = self._seller_dashboard_order_lines(seller, date_start=date_start, date_end=date_end)
        related_maps = self._seller_orders_related_maps(
            seller,
            lines,
            include_conversations=False,
            include_refunds=False,
            include_avatars=False,
        )
        count = 0
        for line in lines:
            ledger = related_maps['ledgers'].get(line.order_id.id)
            status = self._order_status_payload(line.order_id, related_maps['deliveries'].get(line.order_id.id), ledger=ledger)
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
                'url': '/unitrade/seller/chat?conversation_id=%s' % conversation.id,
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
            'id': review.id,
            'reviewer_name': review.user_id.name or 'Pengguna',
            'product_name': review.product_id.name,
            'rating': review.rating,
            'comment': review.comment or 'Tidak ada komentar.',
            'date_label': self._format_datetime_label(review.create_date),
        } for review in reviews]

    def _seller_dashboard_refund_payloads(self, seller, limit=4, date_start=False, date_end=False):
        if 'unitrade.dispute' not in request.env.registry:
            return []
        domain = [
            ('seller_id', '=', seller.id),
            ('state', 'in', ['submitted', 'under_review', 'need_buyer_evidence', 'need_seller_response', 'admin_review_final']),
        ]
        if date_start:
            domain.append(('create_date', '>=', fields.Datetime.to_string(date_start)))
        if date_end:
            domain.append(('create_date', '<', fields.Datetime.to_string(date_end)))
        disputes = request.env['unitrade.dispute'].sudo().search(domain, order='create_date desc', limit=limit)
        state_labels = {
            'submitted': 'Baru',
            'under_review': 'Ditinjau',
            'admin_review_final': 'Review final admin',
            'need_buyer_evidence': 'Menunggu barang kembali',
            'need_seller_response': 'Konfirmasi barang kembali',
        }
        return [{
            'id': dispute.id,
            'key': 'refund-%s' % dispute.id,
            'name': dispute.name,
            'buyer_name': dispute.buyer_id.name or 'Pembeli UniTrade',
            'reason': dict(dispute._fields['reason_code'].selection).get(dispute.reason_code, 'Refund'),
            'note': dispute.reason_note or '',
            'amount_label': self._format_money(dispute.requested_amount, dispute.currency_id),
            'state_label': state_labels.get(dispute.state, dispute.state),
            'date_label': self._format_datetime_label(dispute.submitted_at or dispute.create_date),
            'detail_url': self._seller_refund_detail_url(dispute),
            'can_decide': dispute.state in ('submitted', 'under_review') and not dispute.seller_decided_at,
            'approve_url': '/unitrade/seller/refund/%s/approve' % dispute.id,
            'reject_url': '/unitrade/seller/refund/%s/reject' % dispute.id,
        } for dispute in disputes]

    def _seller_dashboard_chart_data(self, seller, selected_date=False):
        daily_revenue = defaultdict(float)
        daily_orders = defaultdict(set)
        if 'unitrade.escrow.ledger' in request.env.registry:
            ledgers = request.env['unitrade.escrow.ledger'].sudo().search([
                ('seller_id', '=', seller.id),
                ('state', 'in', ['releasable', 'released']),
            ])
            for ledger in ledgers:
                effective_date = self._seller_ledger_effective_date(ledger)
                if not effective_date:
                    continue
                day = fields.Datetime.context_timestamp(request.env.user, effective_date).date()
                daily_revenue[day] += ledger.amount_seller
                daily_orders[day].add(ledger.order_id.id)
        else:
            lines = self._seller_dashboard_order_lines(seller, revenue_only=True)
            for line in lines:
                date_order = line.order_id.date_order
                if not date_order:
                    continue
                day = fields.Datetime.context_timestamp(request.env.user, date_order).date()
                daily_revenue[day] += line.price_total
                daily_orders[day].add(line.order_id.id)

        anchor_date = selected_date or fields.Date.context_today(request.env.user)
        weekly_days = [anchor_date - timedelta(days=offset) for offset in range(6, -1, -1)]
        weekly = {
            'labels': [day.strftime('%d/%m') for day in weekly_days],
            'revenue': [round(daily_revenue.get(day, 0.0), 2) for day in weekly_days],
            'orders': [len(daily_orders.get(day, set())) for day in weekly_days],
        }

        monthly_days = [anchor_date - timedelta(days=offset) for offset in range(29, -1, -1)]
        buckets = []
        for start in range(0, len(monthly_days), 5):
            bucket_days = monthly_days[start:start + 5]
            if not bucket_days:
                continue
            buckets.append({
                'label': '%s-%s' % (bucket_days[0].strftime('%d/%m'), bucket_days[-1].strftime('%d/%m')),
                'revenue': round(sum(daily_revenue.get(day, 0.0) for day in bucket_days), 2),
                'orders': sum(len(daily_orders.get(day, set())) for day in bucket_days),
            })
        monthly = {
            'labels': [bucket['label'] for bucket in buckets],
            'revenue': [bucket['revenue'] for bucket in buckets],
            'orders': [bucket['orders'] for bucket in buckets],
        }
        return {'weekly': weekly, 'monthly': monthly}

    def _seller_payout_channel_label(self, seller):
        channel_code = _safe_get(seller, 'x_payout_channel_code') or ''
        if not channel_code:
            return ''
        try:
            selection = dict(seller._fields['x_payout_channel_code'].selection)
        except Exception:
            selection = {}
        return selection.get(channel_code, channel_code.replace('ID_', '').replace('_', ' '))

    def _seller_payout_account_label(self, seller):
        channel = self._seller_payout_channel_label(seller)
        number = _safe_get(seller, 'x_payout_account_number') or ''
        if channel and number:
            return '%s - %s' % (channel, number)
        if channel:
            return channel
        return 'Belum ada rekening'

    def _seller_payout_destination_values(self, seller):
        return {
            'destination_channel_code': _safe_get(seller, 'x_payout_channel_code') or '',
            'destination_channel_label': self._seller_payout_channel_label(seller),
            'destination_account_number': _safe_get(seller, 'x_payout_account_number') or '',
            'destination_account_name': _safe_get(seller, 'x_payout_account_name') or '',
        }

    def _seller_payout_product_line(self, ledger, seller):
        lines = ledger.order_id.order_line.filtered(lambda line: (
            not line.display_type
            and line.product_id
            and getattr(line.product_id.product_tmpl_id, 'x_seller_id', False)
            and line.product_id.product_tmpl_id.x_seller_id.id == seller.id
        ))
        return lines[:1]

    def _seller_payout_evidence_url(self, ledger):
        if ledger and ledger.buyer_received_image:
            return '/web/image/unitrade.escrow.ledger/%s/buyer_received_image' % ledger.id
        return ''

    def _seller_payout_relative_label(self, value):
        if not value:
            return 'Menunggu'
        try:
            localized = fields.Datetime.context_timestamp(request.env.user, value)
            now = fields.Datetime.context_timestamp(request.env.user, fields.Datetime.now())
        except Exception:
            localized = value
            now = fields.Datetime.now()
        delta = now - localized
        minutes = max(0, int(delta.total_seconds() // 60))
        if minutes < 60:
            return '%s menit lalu' % max(1, minutes)
        hours = minutes // 60
        if hours < 24:
            return '%s jam lalu' % hours
        days = hours // 24
        return '%s hari lalu' % days

    def _seller_payout_ledger_payload(self, ledger, seller, currency):
        line = self._seller_payout_product_line(ledger, seller)
        product = line.product_id.product_tmpl_id if line else False
        release_at = self._seller_payout_release_at(ledger)
        is_ready = self._seller_ledger_is_payoutable(ledger)
        return {
            'id': ledger.id,
            'order_id': ledger.order_id.name or ('#%s' % ledger.order_id.id),
            'product_name': product.name if product else (line.name if line else 'Produk UniTrade'),
            'product_image_url': self._seller_product_image_url(product) if product else '/web/static/img/placeholder.png',
            'buyer_name': ledger.buyer_id.name or ledger.order_id.partner_id.name or 'Pembeli UniTrade',
            'evidence_url': self._seller_payout_evidence_url(ledger),
            'amount': ledger.amount_seller,
            'amount_label': self._format_money(ledger.amount_seller, currency),
            'verification_label': self._seller_payout_relative_label(ledger.buyer_confirmed_at or ledger.completed_at),
            'ready': is_ready,
            'ready_label': 'Dana siap dicairkan' if is_ready else 'Menunggu verifikasi',
            'release_at': fields.Datetime.to_string(release_at) if release_at else '',
        }

    def _seller_payout_countdown_payload(self, ledgers):
        now = fields.Datetime.now()
        candidates = []
        for ledger in ledgers:
            if ledger.payout_status in ('pending', 'processing', 'succeeded') or ledger.state == 'released':
                continue
            if ledger.state == 'held' and ledger.seller_confirmed_at and not ledger.buyer_confirmed_at:
                start = ledger.seller_confirmed_at
                target = ledger.seller_confirmed_at + timedelta(hours=self._seller_auto_confirm_hours() + self._seller_payout_release_hours())
            elif ledger.state == 'releasable':
                release_at = self._seller_payout_release_at(ledger)
                if not release_at or release_at <= now:
                    continue
                start = ledger.completed_at or ledger.buyer_confirmed_at or ledger.create_date
                target = release_at
            else:
                continue
            if target and target > now:
                candidates.append((target, start or ledger.create_date, ledger))
        if not candidates:
            return {
                'target_at': '',
                'remaining_label': 'Tidak ada dana tertahan',
                'progress': 100,
                'subtitle': 'Dana siap otomatis setelah pembeli melakukan konfirmasi atau setelah batas auto-complete.',
            }
        target, start, _ledger = sorted(candidates, key=lambda item: item[0])[0]
        total = max(1, (target - start).total_seconds())
        elapsed = max(0, (now - start).total_seconds())
        progress = min(100, max(0, int(round(elapsed * 100 / total))))
        remaining = target - now
        total_minutes = max(0, int(remaining.total_seconds() // 60))
        days = total_minutes // (60 * 24)
        hours = (total_minutes % (60 * 24)) // 60
        minutes = total_minutes % 60
        parts = []
        if days:
            parts.append('%s Hari' % days)
        if hours or days:
            parts.append('%s Jam' % hours)
        parts.append('%s Menit' % minutes)
        return {
            'target_at': fields.Datetime.to_string(target),
            'remaining_label': ' '.join(parts),
            'progress': progress,
            'subtitle': 'Dana akan otomatis tersedia jika pembeli tidak memberikan konfirmasi dalam batas waktu.',
        }

    def _seller_payout_latest_verification(self, seller, ledgers, currency):
        ledger = ledgers[:1]
        if not ledger:
            return {
                'has_data': False,
                'steps': [],
                'evidence_url': '',
            }
        release_at = self._seller_payout_release_at(ledger)
        payment_at = _safe_get(ledger.payment_intent_id, 'paid_at') or ledger.order_id.date_order or ledger.create_date
        steps = [
            {
                'key': 'paid',
                'label': 'Pembayaran diterima',
                'date_label': self._format_datetime_full_label(payment_at),
                'done': True,
            },
            {
                'key': 'buyer_evidence',
                'label': 'Pembeli upload bukti penerimaan',
                'date_label': self._format_datetime_full_label(ledger.buyer_confirmed_at),
                'done': bool(ledger.buyer_confirmed_at),
            },
            {
                'key': 'ready',
                'label': 'Dana siap dicairkan',
                'date_label': self._format_datetime_full_label(release_at),
                'done': self._seller_ledger_is_payoutable(ledger),
            },
        ]
        payload = self._seller_payout_ledger_payload(ledger, seller, currency)
        return {
            'has_data': True,
            'order_id': payload['order_id'],
            'product_name': payload['product_name'],
            'amount_label': payload['amount_label'],
            'evidence_url': payload['evidence_url'],
            'steps': steps,
        }

    def _seller_payout_status_payload(self, state):
        state = state or 'pending'
        return {
            'succeeded': {'label': 'Berhasil', 'class': 'is-success'},
            'processing': {'label': 'Diproses', 'class': 'is-processing'},
            'pending': {'label': 'Diproses', 'class': 'is-processing'},
            'failed': {'label': 'Gagal', 'class': 'is-failed'},
        }.get(state, {'label': state, 'class': 'is-processing'})

    def _seller_sync_payout_record(self, payout):
        if 'unitrade.escrow.ledger' not in request.env.registry:
            return payout
        ledger_ids = payout.ledger_ids_list() if hasattr(payout, 'ledger_ids_list') else []
        if not ledger_ids:
            return payout
        ledgers = request.env['unitrade.escrow.ledger'].sudo().browse(ledger_ids).exists()
        if not ledgers:
            return payout
        statuses = set(ledgers.mapped('payout_status'))
        values = {}
        if 'failed' in statuses:
            values['state'] = 'failed'
            failures = [reason for reason in ledgers.mapped('payout_failure_reason') if reason]
            if failures:
                values['failure_reason'] = failures[0]
        elif statuses and statuses <= {'succeeded'}:
            values['state'] = 'succeeded'
            values['completed_at'] = payout.completed_at or fields.Datetime.now()
        elif statuses & {'processing', 'pending'}:
            values['state'] = 'processing'
        references = [ref for ref in ledgers.mapped('payout_reference') if ref]
        if references and not payout.payout_reference:
            values['payout_reference'] = ', '.join(references[:3])
        if values:
            payout.sudo().write(values)
        return payout

    def _seller_payout_history_payloads(self, seller, currency, limit=8):
        if 'unitrade.seller.payout' not in request.env.registry:
            return []
        payouts = request.env['unitrade.seller.payout'].sudo().search([
            ('seller_id', '=', seller.id),
        ], order='requested_at desc, id desc', limit=limit)
        payloads = []
        for payout in payouts:
            payout = self._seller_sync_payout_record(payout)
            status = self._seller_payout_status_payload(payout.state)
            proof_url = '/web/content/unitrade.seller.payout/%s/proof_file/%s?download=1' % (
                payout.id,
                quote(payout.proof_filename or ('bukti-%s.pdf' % payout.name)),
            ) if payout.proof_file else ''
            payloads.append({
                'id': payout.id,
                'name': payout.name,
                'status_label': status['label'],
                'status_class': status['class'],
                'destination_label': payout.destination_channel_label
                    and '%s - %s' % (payout.destination_channel_label, payout.destination_account_number or '-')
                    or self._seller_payout_account_label(seller),
                'date_label': self._format_datetime_label(payout.requested_at),
                'amount_label': self._format_money(payout.amount, payout.currency_id or currency),
                'proof_url': proof_url,
                'failure_reason': payout.failure_reason or '',
            })
        return payloads

    def _seller_payout_context_payload(self, seller):
        currency = request.website.currency_id or request.env.company.currency_id
        _, unread_chat_count = self._seller_dashboard_chat_payloads(seller)
        pending_order_count = self._seller_dashboard_pending_order_count(seller)
        balance_summary = self._seller_balance_summary(seller, currency)
        ledgers = self._seller_valid_balance_ledgers(seller) if 'unitrade.escrow.ledger' in request.env.registry else request.env['sale.order'].browse()
        ready_ledgers = ledgers.filtered(lambda ledger: self._seller_ledger_is_payoutable(ledger))
        month_start, month_end = self._seller_dashboard_date_bounds(fields.Date.context_today(request.env.user), 'month')[1:3]
        month_ledgers = self._filter_seller_ledgers_by_date(
            ledgers.filtered(lambda ledger: ledger.state in ('releasable', 'released')),
            date_start=month_start,
            date_end=month_end,
        )
        summary = {
            'available_balance': balance_summary['available_balance'],
            'available_balance_label': self._format_money(balance_summary['available_balance'], currency),
            'held_balance': balance_summary.get('held_balance', 0.0),
            'held_balance_label': self._format_money(balance_summary.get('held_balance', 0.0), currency),
            'month_revenue': currency.round(sum(month_ledgers.mapped('amount_seller'))) if month_ledgers else currency.round(0.0),
            'month_revenue_label': self._format_money(sum(month_ledgers.mapped('amount_seller')) if month_ledgers else 0.0, currency),
            'pending_payout_label': self._format_money(balance_summary['pending_payout'], currency),
            'account_label': self._seller_payout_account_label(seller),
            'account_ready': bool(_safe_get(seller, 'x_payout_ready', False)),
            'settings_url': '/unitrade/seller/settings#payout-settings',
            'can_request_payout': bool(balance_summary['available_balance'] > 0 and _safe_get(seller, 'x_payout_ready', False)),
        }
        account_form = {
            'bank_name': _safe_get(seller, 'x_payout_channel_code') or '',
            'account_number': _safe_get(seller, 'x_payout_account_number') or '',
            'account_name': _safe_get(seller, 'x_payout_account_name') or '',
        }
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
                'incoming_orders': pending_order_count,
            },
            'summary': summary,
            'countdown': self._seller_payout_countdown_payload(ledgers),
            'verification': self._seller_payout_latest_verification(seller, ledgers, currency),
            'ready_ledgers': [self._seller_payout_ledger_payload(ledger, seller, currency) for ledger in ready_ledgers[:8]],
            'history': self._seller_payout_history_payloads(seller, currency),
            'bank_options': self._seller_payout_bank_options(seller),
            'account_form': account_form,
            'account_save_url': '/unitrade/seller/payout/account/save',
            'request_url': '/unitrade/seller/payout/request',
            'data_url': '/unitrade/seller/payouts/data',
            'csrf_token': request.csrf_token(),
        }

    def _seller_payout_context(self, seller):
        payload = self._seller_payout_context_payload(seller)
        return {
            'seller': seller,
            'seller_public_ref': self._seller_public_ref(seller),
            'seller_avatar_url': payload['seller']['avatar_url'],
            'notification_count': payload['stats']['notification_count'],
            'unread_chat_count': payload['stats']['unread_chat_count'],
            'seller_payout_payload_json': json.dumps(payload),
            'page_title': 'Pencairan - UniTrade',
        }

    def _seller_dashboard_context(self, seller, selected_date=False, date_mode='day', orders_period='weekly'):
        date_mode = self._seller_dashboard_date_mode(date_mode)
        orders_period = self._seller_dashboard_orders_period(orders_period)
        selected_day, date_start, date_end, start_day = self._seller_dashboard_date_bounds(selected_date, date_mode)
        date_payload = self._seller_dashboard_date_payload(selected_day, date_mode, start_day)
        orders_date_start, orders_date_end = self._seller_dashboard_orders_bounds(selected_day, orders_period)
        self._refresh_seller_product_listing_states(seller)
        all_products = request.env['product.template'].sudo().search(
            self._seller_dashboard_product_domain(seller, active_only=False)
        )
        active_products = request.env['product.template'].sudo().search(
            self._seller_dashboard_product_domain(seller, active_only=True)
        )
        review_summary = self._seller_review_summary(all_products)
        revenue_lines = self._seller_dashboard_order_lines(
            seller,
            revenue_only=True,
            date_start=date_start,
            date_end=date_end,
        )
        currency = request.website.currency_id or request.env.company.currency_id
        balance_summary = self._seller_balance_summary(
            seller,
            currency,
            date_start=date_start,
            date_end=date_end,
        )
        order_payloads = self._seller_dashboard_order_payloads(seller, date_start=orders_date_start, date_end=orders_date_end)
        chat_payloads, unread_chat_count = self._seller_dashboard_chat_payloads(seller)
        pending_order_count = self._seller_dashboard_pending_order_count(seller, date_start=date_start, date_end=date_end)
        global_pending_order_count = self._seller_dashboard_pending_order_count(seller)
        sold_qty = sum(revenue_lines.mapped('product_uom_qty'))
        sold_count = int(sold_qty) if float(sold_qty or 0.0).is_integer() else round(sold_qty, 2)
        chart_data = self._seller_dashboard_chart_data(seller, selected_date=selected_day)
        review_payloads = self._seller_dashboard_review_payloads(all_products)
        refund_payloads = self._seller_dashboard_refund_payloads(seller, date_start=date_start, date_end=date_end)

        dashboard_payload = {
            'seller': {
                'name': seller.name,
                'avatar_url': '/web/image/res.users/%s/avatar_128?unique=%s' % (
                    seller.user_id.id,
                    seller.user_id.write_date or '',
                ),
                'profile_url': '/seller-profile/%s' % self._seller_public_ref(seller),
            },
            'stats': {
                'revenue_label': self._format_money(balance_summary['total_revenue'], currency),
                'available_balance_label': self._format_money(balance_summary['available_balance'], currency),
                'available_balance': balance_summary['available_balance'],
                'payoutable_balance_label': self._format_money(balance_summary['payoutable_balance'], currency),
                'pending_payout_label': self._format_money(balance_summary['pending_payout'], currency),
                'released_balance_label': self._format_money(balance_summary['released_balance'], currency),
                'used_balance_label': self._format_money(balance_summary['used_balance'], currency),
                'payout_ready': bool(_safe_get(seller, 'x_payout_ready', False)),
                'can_request_payout': bool(balance_summary['available_balance'] > 0 and _safe_get(seller, 'x_payout_ready', False)),
                'active_products': len(active_products),
                'incoming_orders': pending_order_count,
                'average_rating': review_summary['rating'] or seller.average_rating or 0.0,
                'review_count': review_summary['review_count'],
                'sold_count': sold_count,
                'unread_chat_count': unread_chat_count,
                'notification_count': global_pending_order_count + unread_chat_count,
            },
            'orders': order_payloads,
            'products': self._seller_dashboard_product_payloads(seller),
            'messages': chat_payloads,
            'reviews': review_payloads,
            'refunds': refund_payloads,
            'chart': chart_data,
            'date_filter': date_payload,
            'orders_period': orders_period,
            'current_date_label': date_payload['label'],
            'csrf_token': request.csrf_token(),
            'add_product_url': self._seller_product_add_url(),
            'data_url': '/unitrade/seller/dashboard/data',
            'payout_request_url': '/unitrade/seller/payout/request',
            'payout_settings_url': '/unitrade/seller/settings#payout-settings',
            'payout_page_url': '/unitrade/seller/payouts',
        }

        return {
            'seller': seller,
            'seller_public_ref': self._seller_public_ref(seller),
            'dashboard_stats': dashboard_payload['stats'],
            'dashboard_products': dashboard_payload['products'],
            'dashboard_orders': order_payloads,
            'dashboard_messages': chat_payloads,
            'dashboard_reviews': review_payloads,
            'dashboard_chart_json': json.dumps(dashboard_payload),
            'dashboard_payload_json': json.dumps(dashboard_payload),
            'dashboard_search_items_json': json.dumps([]),
            'add_product_url': self._seller_product_add_url(),
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
        seller_public_ref = self._seller_public_ref(seller)
        canonical_path = '/seller-profile/%s' % quote(seller_public_ref)
        current_path = request.httprequest.path
        if current_path != canonical_path:
            query_string = request.httprequest.query_string.decode('utf-8')
            return request.redirect('%s%s' % (canonical_path, ('?' + query_string) if query_string else ''))

        search = (kwargs.get('search') or '').strip()
        tab = kwargs.get('tab') or 'home'
        if tab not in self._PROFILE_TABS:
            tab = 'home'
        active_rating = self._active_review_rating(kwargs.get('rating')) if tab == 'reviews' else 0
        active_sort = self._active_review_sort(kwargs.get('sort')) if tab == 'reviews' else 'newest'

        self._refresh_seller_product_listing_states(seller)
        Product = request.env['product.template'].sudo()
        all_products = Product.search(
            expression.AND([
                [('x_seller_id', '=', seller.id)],
                Product._unitrade_public_active_domain()
                if hasattr(Product, '_unitrade_public_active_domain')
                else [('x_is_marketplace', '=', True), ('sale_ok', '=', True), ('website_published', '=', True)],
            ])
        )
        products = self._seller_products(seller, search=search, tab=tab)
        review_summary = self._seller_review_summary(all_products)
        seller_rating = review_summary['rating'] or seller.average_rating or 0.0
        review_star_filters, review_star_display = self._seller_review_star_filters(review_summary, seller_rating, active_rating)
        seller_reviews = self._seller_reviews(all_products, rating=active_rating, sort=active_sort)
        total_sold = int(sum(all_products.mapped('sales_count'))) if all_products and 'sales_count' in all_products._fields else 0
        joined_date = seller.create_date.strftime('%d/%m/%Y') if seller.create_date else ''
        seller_map_lat, seller_map_lng = self._seller_map_coordinates(seller)
        seller_phone = self._seller_phone_value(seller)

        values = {
            'seller': seller,
            'seller_public_ref': seller_public_ref,
            'seller_is_preview': seller.status != 'verified',
            'seller_products': products,
            'seller_all_products': all_products,
            'seller_address': self._seller_address(seller),
            'seller_map_lat': seller_map_lat,
            'seller_map_lng': seller_map_lng,
            'seller_phone_display': seller_phone,
            'seller_phone_url': self._seller_phone_url(seller),
            'seller_rating': seller_rating,
            'seller_review_count': review_summary['review_count'],
            'seller_review_counts': review_summary['counts'],
            'seller_review_star_filters': review_star_filters,
            'seller_review_star_display': review_star_display,
            'seller_review_active_rating': active_rating,
            'seller_review_active_sort': active_sort,
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
        active_sort = self._active_review_sort(kwargs.get('sort')) if tab == 'reviews' else 'newest'

        seller = self._get_seller_by_public_ref(profile_ref=profile_ref)
        if not seller:
            return {
                'success': False,
                'message': 'Seller tidak ditemukan',
                'html': '',
            }

        self._refresh_seller_product_listing_states(seller)
        Product = request.env['product.template'].sudo()
        all_products = Product.search(
            expression.AND([
                [('x_seller_id', '=', seller.id)],
                Product._unitrade_public_active_domain()
                if hasattr(Product, '_unitrade_public_active_domain')
                else [('x_is_marketplace', '=', True), ('sale_ok', '=', True), ('website_published', '=', True)],
            ])
        )
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
                'seller_reviews': self._seller_reviews(all_products, rating=active_rating, sort=active_sort),
                'seller_rating': seller_rating,
                'seller_review_count': review_summary['review_count'],
                'seller_review_counts': review_summary['counts'],
                'seller_review_star_filters': review_star_filters,
                'seller_review_star_display': review_star_display,
                'seller_review_active_rating': active_rating,
                'seller_review_active_sort': active_sort,
                'seller_search': search,
            },
        )
        return {
            'success': True,
            'html': str(html),
            'tab': tab,
            'search': search,
            'rating': active_rating,
            'sort': active_sort,
        }

    @http.route('/unitrade/seller/profile', type='http', auth='user', website=True)
    def my_seller_profile(self, **kwargs):
        """Convenience route for the current user's public seller profile."""
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

        whatsapp = self._seller_phone_value(seller)
        if whatsapp:
            phone = self._normalize_whatsapp_phone(whatsapp)
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
        return request.redirect('/seller-onboarding')

    @http.route('/unitrade/seller/register/submit', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def seller_register_submit(self, **kwargs):
        """Keep the old submit URL from creating a second verification path."""
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
            return self._seller_not_ready_redirect()

        return request.render(
            'unitrade_seller.seller_dashboard_template',
            self._seller_dashboard_context(
                seller,
                selected_date=kwargs.get('date'),
                date_mode=kwargs.get('date_mode'),
                orders_period=kwargs.get('orders_period'),
            ),
        )

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
            return request.redirect('/seller-onboarding')
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
                'message': 'Akun penjual belum ditemukan.',
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
                'message': 'Akun penjual belum ditemukan.',
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
                'message': 'Akun penjual belum ditemukan.',
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
                'message': 'Akun penjual belum ditemukan.',
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
            values['x_listing_expires_at'] = fields.Datetime.now() + timedelta(days=30)
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
            ('payment_method_code', '=', code),
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
        try:
            with request.env.cr.savepoint():
                intent = self._create_seller_listing_payment_intent(seller, product, method_key, total, currency)
                product_values = {}
                if 'x_listing_fee' in product._fields:
                    product_values['x_listing_fee'] = total
                if intent.state == 'paid' and 'x_listing_activated_at' in product._fields:
                    product_values['x_listing_activated_at'] = fields.Datetime.now()
                if intent.state == 'paid' and 'x_listing_expires_at' in product._fields:
                    product_values['x_listing_expires_at'] = fields.Datetime.now() + timedelta(days=30)
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
