from collections import defaultdict
from datetime import timedelta
import base64
import json
import math
import logging
import re
from urllib.parse import quote

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
        return _safe_get(seller, 'x_store_slug') or seller.x_profile_uuid

    @staticmethod
    def _get_seller_by_public_ref(profile_ref=None, seller_id=None):
        Seller = request.env['unitrade.seller'].sudo()
        seller = Seller.browse()
        found_by_uuid = False
        if seller_id:
            seller = Seller.browse(seller_id).exists()
        elif profile_ref:
            seller = Seller.search([('x_store_slug', '=', profile_ref)], limit=1)
            if not seller:
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
        if _safe_get(seller, 'x_store_address_detail'):
            address_parts = [
                _safe_get(seller, 'x_store_address_detail'),
                _safe_get(seller, 'x_store_city'),
                _safe_get(seller, 'x_store_province'),
            ]
            return ', '.join([part for part in address_parts if part])
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

    def _seller_product_expiry_label(self, product):
        expires_at = _safe_get(product, 'x_listing_expires_at', False)
        if not expires_at:
            return 'Tanpa batas'
        now = fields.Datetime.now()
        if expires_at < now:
            return 'Expired'
        days = max(0, int(math.ceil((expires_at - now).total_seconds() / 86400.0)))
        return 'Hari ini' if days <= 0 else '%s hari' % days

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

    def _seller_product_categories(self):
        categories = request.env['product.category'].sudo().search([], order='complete_name asc, name asc')
        return [{
            'id': category.id,
            'name': category.name,
            'label': category.complete_name or category.name,
        } for category in categories]

    def _seller_products_page_payloads(self, seller, limit=40):
        Product = request.env['product.template'].sudo()
        products = Product.search(
            self._seller_dashboard_product_domain(seller, active_only=False),
            order='write_date desc, create_date desc, id desc',
            limit=limit,
        )
        payloads = []
        for product in products:
            condition = self._seller_product_condition(product)
            stock_qty = _safe_get(product, 'x_unitrade_free_qty', False)
            if stock_qty is False:
                variant = product.product_variant_id or product.product_variant_ids[:1]
                stock_qty = variant.free_qty if variant and 'free_qty' in variant._fields else 0
            try:
                stock_qty = float(stock_qty or 0)
            except (TypeError, ValueError):
                stock_qty = 0
            stock_label = int(stock_qty) if stock_qty.is_integer() else stock_qty
            payloads.append({
                'id': product.id,
                'product_code': product.default_code or ('UT%05d' % product.id),
                'image_url': '/web/image/product.template/%s/image_256?unique=%s' % (
                    product.id,
                    product.write_date or '',
                ),
                'name': product.name or 'Produk UniTrade',
                'date_label': self._format_product_datetime_label(product.write_date or product.create_date),
                'stock_label': stock_label,
                'condition_key': condition['key'],
                'condition_label': condition['label'],
                'edit_url': self._seller_product_edit_url(product),
                'detail_url': product.website_url or '/unitrade/product/%s' % product.id,
                'expiry_label': self._seller_product_expiry_label(product),
            })
        return payloads

    def _seller_products_page_context(self, seller):
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
            'products': self._seller_products_page_payloads(seller),
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
            'subtitle': "Here's what's happening with your store today",
            'submit_label': 'Post',
            'data_url': '/unitrade/seller/products/new/data',
            'submit_url': '/unitrade/seller/products/create',
            'delete_url': '',
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
    def _store_slug(value):
        slug = re.sub(r'[^a-z0-9-]+', '-', (value or '').strip().lower())
        slug = re.sub(r'-+', '-', slug).strip('-')
        return slug[:80]

    def _seller_settings_payload(self, seller):
        _, unread_chat_count = self._seller_dashboard_chat_payloads(seller)
        pending_order_count = self._seller_dashboard_pending_order_count(seller)
        partner = seller.partner_id
        province = _safe_get(seller, 'x_store_province') or (partner.state_id.name if partner and partner.state_id else '')
        city = _safe_get(seller, 'x_store_city') or (partner.city if partner else '')
        address_detail = _safe_get(seller, 'x_store_address_detail') or seller.x_profile_address or (partner.street if partner else '')
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
                'province': province,
                'city': city,
                'address_detail': address_detail,
                'bank_name': _safe_get(seller, 'x_payout_channel_code') or '',
                'account_number': _safe_get(seller, 'x_payout_account_number') or '',
                'account_name': _safe_get(seller, 'x_payout_account_name') or '',
                'store_active': bool(_safe_get(seller, 'x_store_active', True)),
                'delete_requested': bool(_safe_get(seller, 'x_delete_requested', False)),
            },
            'bank_options': [
                {'value': '', 'label': 'Pilih bank'},
                {'value': 'ID_BCA', 'label': 'BCA'},
                {'value': 'ID_MANDIRI', 'label': 'Mandiri'},
                {'value': 'ID_BNI', 'label': 'BNI'},
                {'value': 'ID_BRI', 'label': 'BRI'},
                {'value': 'OVO', 'label': 'OVO'},
                {'value': 'DANA', 'label': 'DANA'},
            ],
            'data_url': '/unitrade/seller/settings/data',
            'update_url': '/unitrade/seller/settings/update',
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

        province = (values.get('province') or '').strip()
        city = (values.get('city') or '').strip()
        address_detail = (values.get('address_detail') or '').strip()
        seller_values = {
            'x_store_slug': slug,
            'x_profile_description': (values.get('description') or '').strip(),
            'x_store_province': province,
            'x_store_city': city,
            'x_store_address_detail': address_detail,
            'x_profile_address': ', '.join([part for part in [address_detail, city, province] if part]),
            'x_payout_channel_code': values.get('bank_name') or False,
            'x_payout_account_number': (values.get('account_number') or '').strip(),
            'x_payout_account_name': (values.get('account_name') or '').strip(),
            'x_store_active': bool(values.get('store_active', True)),
        }
        seller.write(seller_values)

        partner_values = {}
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
        return seller

    def _seller_product_for_edit(self, seller, product_id):
        product = request.env['product.template'].sudo().browse(int(product_id or 0)).exists()
        if not product or _safe_get(product, 'x_seller_id') != seller:
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
            'price': product.list_price or 0.0,
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

    def _create_seller_product(self, seller, payload):
        name = (payload.get('name') or '').strip()
        description = (payload.get('description') or '').strip()
        category_id = int(payload.get('category_id') or 0)
        price = float(payload.get('price') or 0)
        discount_price_raw = payload.get('discount_price')
        discount_price = float(discount_price_raw or 0)
        stock = float(payload.get('stock') or 0)
        images = self._clean_product_image_payloads(payload.get('images') or [])

        if not name:
            raise ValueError('Nama produk wajib diisi.')
        if not description:
            raise ValueError('Deskripsi produk wajib diisi.')
        if not category_id:
            raise ValueError('Kategori produk wajib dipilih.')
        if price < 0:
            raise ValueError('Harga tidak boleh negatif.')
        if discount_price < 0:
            raise ValueError('Harga diskon tidak boleh negatif.')
        if discount_price and discount_price >= price:
            raise ValueError('Harga diskon harus lebih kecil dari harga normal.')
        if stock < 0:
            raise ValueError('Stok produk tidak boleh negatif.')

        category = request.env['product.category'].sudo().browse(category_id).exists()
        if not category:
            raise ValueError('Kategori produk tidak ditemukan.')

        Product = request.env['product.template'].sudo()
        ProductImage = request.env['product.image'].sudo()
        Attachment = request.env['ir.attachment'].sudo()

        discount_percent = 0.0
        if discount_price and price:
            discount_percent = max(0.0, min(100.0, (price - discount_price) / price * 100.0))

        district = self._seller_default_district(seller)
        seller_location = self._seller_address(seller)
        product_values = {
            'name': name,
            'description_sale': description,
            'list_price': price,
            'categ_id': category.id,
            'sale_ok': True,
            'website_published': True,
            'image_1920': images[0]['datas'],
            'x_seller_id': seller.id,
            'x_seller_location': seller_location,
            'x_item_province': 'diy',
            'x_item_district': district,
            'x_condition': 'used',
            'x_discount_percent': discount_percent,
        }
        if 'detailed_type' in Product._fields:
            product_values['detailed_type'] = 'product'
        elif 'type' in Product._fields:
            product_values['type'] = 'product'
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
        product.write({'x_is_marketplace': True})
        if 'x_unitrade_stock_qty' in product._fields:
            product.write({'x_unitrade_stock_qty': stock})

        _logger.info('Seller %s created UniTrade product %s', seller.id, product.id)
        return product

    def _update_seller_product(self, seller, product, payload):
        name = (payload.get('name') or '').strip()
        description = (payload.get('description') or '').strip()
        category_id = int(payload.get('category_id') or 0)
        price = float(payload.get('price') or 0)
        discount_price_raw = payload.get('discount_price')
        discount_price = float(discount_price_raw or 0)
        stock = float(payload.get('stock') or 0)
        images = self._clean_product_edit_image_payloads(product, payload.get('images') or [])

        if not name:
            raise ValueError('Nama produk wajib diisi.')
        if not description:
            raise ValueError('Deskripsi produk wajib diisi.')
        if not category_id:
            raise ValueError('Kategori produk wajib dipilih.')
        if price < 0:
            raise ValueError('Harga tidak boleh negatif.')
        if discount_price < 0:
            raise ValueError('Harga diskon tidak boleh negatif.')
        if discount_price and discount_price >= price:
            raise ValueError('Harga diskon harus lebih kecil dari harga normal.')
        if stock < 0:
            raise ValueError('Stok produk tidak boleh negatif.')

        category = request.env['product.category'].sudo().browse(category_id).exists()
        if not category:
            raise ValueError('Kategori produk tidak ditemukan.')

        discount_percent = 0.0
        if discount_price and price:
            discount_percent = max(0.0, min(100.0, (price - discount_price) / price * 100.0))

        was_marketplace = bool(_safe_get(product, 'x_is_marketplace', False))
        product.write({'x_is_marketplace': False})
        product.product_template_image_ids.unlink()
        product.write({
            'name': name,
            'description_sale': description,
            'list_price': price,
            'categ_id': category.id,
            'image_1920': images[0]['datas'],
            'sale_ok': True,
            'website_published': True,
            'x_discount_percent': discount_percent,
        })
        ProductImage = request.env['product.image'].sudo()
        for image in images[1:]:
            ProductImage.create({
                'name': image['name'],
                'product_tmpl_id': product.id,
                'image_1920': image['datas'],
            })
        if was_marketplace:
            product.write({'x_is_marketplace': True})
        if 'x_unitrade_stock_qty' in product._fields:
            product.write({'x_unitrade_stock_qty': stock})

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

    @staticmethod
    def _ledger_for_order_seller(order, seller):
        if 'unitrade.escrow.ledger' not in request.env.registry:
            return request.env['sale.order'].browse()
        return request.env['unitrade.escrow.ledger'].sudo().search([
            ('order_id', '=', order.id),
            ('seller_id', '=', seller.id),
        ], order='create_date desc', limit=1)

    def _order_status_payload(self, order, delivery=False, ledger=False):
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
            payloads.append({
                'order_name': order.name,
                'customer_name': order.partner_id.name or 'Pembeli UniTrade',
                'customer_avatar_url': self._customer_avatar_url(order),
                'product_name': line.product_id.product_tmpl_id.name,
                'date_label': self._format_datetime_label(order.date_order),
                'total_label': self._format_money(line.price_total, order.currency_id),
                'status_key': status['key'],
                'status_label': status['label'],
                'ledger_id': ledger.id if ledger else 0,
                'buyer_confirmed': bool(ledger and ledger.buyer_confirmed_at),
                'seller_confirmed': bool(ledger and ledger.seller_confirmed_at),
                'seller_evidence': bool(ledger and ledger.seller_handoff_image),
                'can_confirm_handoff': can_confirm_handoff,
                'confirm_handoff_url': '/seller/order/%s/confirm-handoff' % ledger.id if ledger else '',
                'refund_dispute_id': refund_dispute.id if refund_dispute else 0,
                'refund_state': refund_dispute.state if refund_dispute else '',
                'refund_detail_url': '/unitrade/order/%s/refund/%s' % (order.id, refund_dispute.id) if refund_dispute else '',
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

    def _seller_orders_payloads(self, seller):
        lines = self._seller_dashboard_order_lines(seller)
        deliveries = self._delivery_by_order(lines.mapped('order_id').ids)
        payloads = []
        counts = {
            'all': 0,
            'new': 0,
            'processing': 0,
            'done': 0,
            'cancel': 0,
        }

        for line in lines:
            order = line.order_id
            ledger = self._ledger_for_order_seller(order, seller)
            raw_status = self._order_status_payload(order, deliveries.get(order.id), ledger=ledger)
            filter_key = self._seller_orders_filter_key(raw_status['key'])
            counts['all'] += 1
            counts[filter_key] += 1

            payloads.append({
                'id': line.id,
                'order_id': order.id,
                'order_name': order.name,
                'customer_name': order.partner_id.name or 'Pembeli UniTrade',
                'customer_avatar_url': self._customer_avatar_url(order),
                'product_name': line.product_id.product_tmpl_id.name or line.name,
                'product_qty': int(line.product_uom_qty) if float(line.product_uom_qty or 0).is_integer() else line.product_uom_qty,
                'product_image_url': '/web/image/product.product/%s/image_128' % line.product_id.id if line.product_id else '',
                'total_label': self._format_money(line.price_total, order.currency_id),
                'status_key': filter_key,
                'status_label': self._seller_orders_status_label(filter_key),
                'date_label': self._format_order_datetime_label(order.date_order),
                'order_status_url': '/unitrade/order/status/%s' % order.id,
                'action_url': '/unitrade/seller/chat',
            })

        return {
            'orders': payloads,
            'counts': counts,
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

    @staticmethod
    def _seller_refund_dispute(order, ledger=False):
        if 'unitrade.dispute' not in request.env.registry:
            return request.env['sale.order'].browse()
        domain = [('order_id', '=', order.id)]
        if ledger:
            domain.append(('escrow_ledger_id', '=', ledger.id))
        return request.env['unitrade.dispute'].sudo().search(domain, order='create_date desc', limit=1)

    def _seller_dashboard_pending_order_count(self, seller):
        lines = self._seller_dashboard_order_lines(seller)
        deliveries = self._delivery_by_order(lines.mapped('order_id').ids)
        count = 0
        for line in lines:
            ledger = self._ledger_for_order_seller(line.order_id, seller)
            status = self._order_status_payload(line.order_id, deliveries.get(line.order_id.id), ledger=ledger)
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
            'reviewer_name': review.user_id.name or 'Pengguna',
            'product_name': review.product_id.name,
            'rating': review.rating,
            'comment': review.comment or 'Tidak ada komentar.',
            'date_label': self._format_datetime_label(review.create_date),
        } for review in reviews]

    def _seller_dashboard_refund_payloads(self, seller, limit=4):
        if 'unitrade.dispute' not in request.env.registry:
            return []
        disputes = request.env['unitrade.dispute'].sudo().search([
            ('seller_id', '=', seller.id),
            ('state', 'in', ['submitted', 'under_review', 'need_buyer_evidence', 'need_seller_response']),
        ], order='create_date desc', limit=limit)
        state_labels = {
            'submitted': 'Baru',
            'under_review': 'Ditinjau',
            'need_buyer_evidence': 'Butuh bukti pembeli',
            'need_seller_response': 'Butuh respons seller',
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
            'detail_url': '/unitrade/order/%s/refund/%s' % (dispute.order_id.id, dispute.id),
            'approve_url': '/unitrade/seller/refund/%s/approve' % dispute.id,
            'reject_url': '/unitrade/seller/refund/%s/reject' % dispute.id,
        } for dispute in disputes]

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
            'orders': order_payloads,
            'products': self._seller_dashboard_product_payloads(seller),
            'messages': chat_payloads,
            'reviews': self._seller_dashboard_review_payloads(all_products),
            'refunds': self._seller_dashboard_refund_payloads(seller),
            'chart': chart_data,
            'current_date_label': fields.Date.context_today(request.env.user).strftime('%d/%m/%Y'),
            'csrf_token': request.csrf_token(),
            'add_product_url': self._seller_product_add_url(),
        }

        return {
            'seller': seller,
            'seller_public_ref': self._seller_public_ref(seller),
            'dashboard_stats': dashboard_payload['stats'],
            'dashboard_products': dashboard_payload['products'],
            'dashboard_orders': order_payloads,
            'dashboard_messages': chat_payloads,
            'dashboard_reviews': self._seller_dashboard_review_payloads(all_products),
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
            return request.redirect('/seller-onboarding')

        return request.render(
            'unitrade_seller.seller_dashboard_template',
            self._seller_dashboard_context(seller),
        )

    @http.route([
        '/unitrade/seller/orders',
        '/seller/orders',
        '/my/seller/orders',
    ], type='http', auth='user', website=True, sitemap=False)
    def seller_orders(self, **kwargs):
        """Render the standalone seller orders app shell."""
        seller = self._dashboard_seller()
        if not seller:
            return request.redirect('/seller-onboarding')

        return request.render(
            'unitrade_seller.seller_orders_template',
            self._seller_orders_context(seller),
        )

    @http.route('/unitrade/seller/orders/data', type='json', auth='user', website=True, methods=['POST'])
    def seller_orders_data(self, **kwargs):
        """Return seller order rows for the OWL orders page."""
        seller = self._dashboard_seller()
        if not seller:
            return {
                'success': False,
                'message': 'Akun penjual belum terverifikasi.',
                'orders': [],
                'counts': {},
            }

        payload = self._seller_orders_payloads(seller)
        chat_payloads, unread_chat_count = self._seller_dashboard_chat_payloads(seller)
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
        }

    @http.route('/unitrade/seller/refund/<int:dispute_id>/approve', type='http', auth='user', website=True, methods=['POST'], csrf=True, sitemap=False)
    def seller_refund_approve(self, dispute_id, **kwargs):
        seller = self._dashboard_seller()
        if not seller or 'unitrade.dispute' not in request.env.registry:
            return request.not_found()
        dispute = request.env['unitrade.dispute'].sudo().browse(dispute_id).exists()
        if not dispute or not dispute.seller_id or dispute.seller_id.id != seller.id:
            return request.not_found()
        try:
            dispute.with_user(request.env.user).action_approve_refund()
            return request.redirect('/unitrade/seller/dashboard?refund_approved=1#dashboard-refunds')
        except Exception as error:
            _logger.exception('Seller refund approve failed for dispute %s', dispute_id)
            return request.redirect('/unitrade/seller/dashboard?seller_error=%s#dashboard-refunds' % quote(str(error)))

    @http.route('/unitrade/seller/refund/<int:dispute_id>/reject', type='http', auth='user', website=True, methods=['POST'], csrf=True, sitemap=False)
    def seller_refund_reject(self, dispute_id, **kwargs):
        seller = self._dashboard_seller()
        if not seller or 'unitrade.dispute' not in request.env.registry:
            return request.not_found()
        dispute = request.env['unitrade.dispute'].sudo().browse(dispute_id).exists()
        if not dispute or not dispute.seller_id or dispute.seller_id.id != seller.id:
            return request.not_found()
        try:
            dispute.with_user(request.env.user).action_reject_refund()
            return request.redirect('/unitrade/seller/dashboard?refund_rejected=1#dashboard-refunds')
        except Exception as error:
            _logger.exception('Seller refund reject failed for dispute %s', dispute_id)
            return request.redirect('/unitrade/seller/dashboard?seller_error=%s#dashboard-refunds' % quote(str(error)))

    @http.route([
        '/unitrade/seller/products',
        '/seller/products',
        '/my/seller/products',
    ], type='http', auth='user', website=True, sitemap=False)
    def seller_products(self, **kwargs):
        """Render the standalone seller products app shell."""
        seller = self._dashboard_seller()
        if not seller:
            return request.redirect('/seller-onboarding')

        return request.render(
            'unitrade_seller.seller_products_template',
            self._seller_products_page_context(seller),
        )

    @http.route([
        '/unitrade/seller/settings',
        '/seller/settings',
        '/my/seller/settings',
    ], type='http', auth='user', website=True, sitemap=False)
    def seller_settings(self, **kwargs):
        """Render the standalone seller store settings app shell."""
        seller = self._dashboard_seller()
        if not seller:
            return request.redirect('/seller-onboarding')
        return request.render(
            'unitrade_seller.seller_settings_template',
            self._seller_settings_context(seller),
        )

    @http.route('/unitrade/seller/settings/data', type='json', auth='user', website=True, methods=['POST'])
    def seller_settings_data(self, **kwargs):
        """Return current settings for the logged-in seller only."""
        seller = self._dashboard_seller()
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
        seller = self._dashboard_seller()
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
        seller = self._dashboard_seller()
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
        seller = self._dashboard_seller()
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
            return request.redirect('/seller-onboarding')

        return request.render(
            'unitrade_seller.seller_product_create_template',
            self._seller_product_create_context(seller),
        )

    @http.route('/unitrade/seller/products/<int:product_id>/edit', type='http', auth='user', website=True, sitemap=False)
    def seller_product_edit(self, product_id, **kwargs):
        """Render the standalone seller product edit app shell."""
        seller = self._dashboard_seller()
        if not seller:
            return request.redirect('/seller-onboarding')
        product = self._seller_product_for_edit(seller, product_id)
        if not product:
            return request.redirect('/unitrade/seller/products')

        return request.render(
            'unitrade_seller.seller_product_edit_template',
            self._seller_product_edit_context(seller, product),
        )

    @http.route('/unitrade/seller/products/new/data', type='json', auth='user', website=True, methods=['POST'])
    def seller_product_create_data(self, **kwargs):
        """Return dynamic data for the seller product creation form."""
        seller = self._dashboard_seller()
        if not seller:
            return {
                'success': False,
                'message': 'Akun penjual belum terverifikasi.',
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
        }

    @http.route('/unitrade/seller/products/<int:product_id>/edit/data', type='json', auth='user', website=True, methods=['POST'])
    def seller_product_edit_data(self, product_id, **kwargs):
        """Return dynamic data and the existing product values for edit mode."""
        seller = self._dashboard_seller()
        if not seller:
            return {
                'success': False,
                'message': 'Akun penjual belum ditemukan.',
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
                'message': 'Akun penjual belum terverifikasi.',
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
            'message': 'Produk berhasil diposting.',
            'product_id': product.id,
            'redirect_url': '/unitrade/seller/products',
        }

    @http.route('/unitrade/seller/products/<int:product_id>/update', type='json', auth='user', website=True, methods=['POST'])
    def seller_product_update_submit(self, product_id, **kwargs):
        """Update a marketplace product owned by the current seller."""
        seller = self._dashboard_seller()
        if not seller:
            return {
                'success': False,
                'message': 'Akun penjual belum ditemukan.',
            }
        product = self._seller_product_for_edit(seller, product_id)
        if not product:
            return {
                'success': False,
                'message': 'Produk tidak ditemukan atau bukan milik toko Anda.',
            }

        try:
            with request.env.cr.savepoint():
                product = self._update_seller_product(seller, product, kwargs)
        except ValueError as error:
            return {
                'success': False,
                'message': str(error),
            }
        except Exception:
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
                'message': 'Akun penjual belum ditemukan.',
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
                'message': 'Akun penjual belum terverifikasi.',
                'products': [],
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
            'products': self._seller_products_page_payloads(seller),
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
