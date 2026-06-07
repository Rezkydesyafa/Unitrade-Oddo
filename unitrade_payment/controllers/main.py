import base64
import hashlib
import io
import json
import logging
from datetime import timedelta
from urllib.parse import quote

import qrcode
import requests

from odoo import _, fields, http
from odoo.http import request
from odoo.tools.image import image_data_uri
from odoo.addons.unitrade_payment.midtrans_methods import MIDTRANS_PAYMENT_METHODS

_logger = logging.getLogger(__name__)


PAYMENT_METHOD_INSTRUCTIONS = {
    'bca_va': [
        {
            'title': 'BCA Mobile / myBCA',
            'open': True,
            'steps': [
                'Buka aplikasi BCA Mobile atau myBCA lalu login.',
                'Pilih menu Transfer Virtual Account.',
                'Masukkan nomor Virtual Account yang tampil di halaman ini.',
                'Pastikan nominal dan nama merchant UniTrade sudah benar, lalu konfirmasi pembayaran.',
            ],
        },
        {
            'title': 'ATM BCA',
            'steps': [
                'Pilih Transaksi Lainnya lalu Transfer.',
                'Pilih ke Rekening BCA Virtual Account.',
                'Masukkan nomor Virtual Account dan ikuti instruksi sampai pembayaran selesai.',
            ],
        },
    ],
    'mandiri_bill': [
        {
            'title': "Livin' by Mandiri",
            'open': True,
            'steps': [
                "Buka aplikasi Livin' by Mandiri dan login.",
                'Pilih menu Bayar, lalu pilih Multipayment.',
                'Masukkan kode perusahaan dan Bill Key yang tampil di halaman ini.',
                'Periksa nominal dan konfirmasi dengan PIN Anda.',
            ],
        },
        {
            'title': 'ATM Mandiri',
            'steps': [
                'Pilih Bayar/Beli lalu Multipayment.',
                'Masukkan kode perusahaan dan Bill Key.',
                'Pastikan detail pembayaran benar, lalu selesaikan transaksi.',
            ],
        },
    ],
    'bni_va': [
        {
            'title': 'BNI Mobile Banking',
            'open': True,
            'steps': [
                'Buka BNI Mobile Banking dan login.',
                'Pilih menu Transfer lalu Virtual Account Billing.',
                'Masukkan nomor Virtual Account.',
                'Periksa detail pembayaran, lalu konfirmasi.',
            ],
        },
        {
            'title': 'ATM BNI',
            'steps': [
                'Pilih Menu Lainnya lalu Transfer.',
                'Pilih Virtual Account Billing.',
                'Masukkan nomor Virtual Account dan selesaikan pembayaran.',
            ],
        },
    ],
    'bri_va': [
        {
            'title': 'BRImo',
            'open': True,
            'steps': [
                'Buka BRImo dan login.',
                'Pilih menu BRIVA.',
                'Masukkan nomor Virtual Account yang tampil di halaman ini.',
                'Periksa nominal, lalu konfirmasi pembayaran.',
            ],
        },
        {
            'title': 'ATM BRI',
            'steps': [
                'Pilih Transaksi Lain lalu Pembayaran.',
                'Pilih BRIVA dan masukkan nomor Virtual Account.',
                'Ikuti instruksi sampai transaksi selesai.',
            ],
        },
    ],
    'qris': [
        {
            'title': 'QRIS',
            'open': True,
            'steps': [
                'Buka aplikasi mobile banking atau e-wallet yang mendukung QRIS.',
                'Pilih menu Scan QR atau Bayar QRIS.',
                'Scan QR yang tampil di halaman ini.',
                'Pastikan nominal pembayaran benar, lalu konfirmasi.',
            ],
        },
    ],
    'gopay': [
        {
            'title': 'GoPay',
            'open': True,
            'steps': [
                'Scan QR yang tampil atau klik tombol lanjut pembayaran jika tersedia.',
                'Buka aplikasi Gojek/GoPay dan konfirmasi pembayaran.',
                'Pastikan nominal pembayaran benar.',
                'Tunggu status UniTrade berubah otomatis setelah Midtrans mengonfirmasi pembayaran.',
            ],
        },
    ],
    'shopeepay': [
        {
            'title': 'ShopeePay',
            'open': True,
            'steps': [
                'Klik tombol lanjut pembayaran jika tersedia.',
                'Login atau buka aplikasi ShopeePay sesuai arahan Midtrans.',
                'Pastikan nominal pembayaran benar, lalu konfirmasi.',
                'Tunggu status UniTrade berubah otomatis setelah Midtrans mengonfirmasi pembayaran.',
            ],
        },
    ],
    'indomaret': [
        {
            'title': 'Indomaret',
            'open': True,
            'steps': [
                'Catat kode pembayaran yang tampil di halaman ini.',
                'Datang ke kasir Indomaret dan sebutkan pembayaran Midtrans.',
                'Berikan kode pembayaran dan pastikan nominalnya benar.',
                'Simpan struk pembayaran sampai status UniTrade berubah.',
            ],
        },
    ],
    'alfamart': [
        {
            'title': 'Alfamart / Alfamidi / Dan+Dan',
            'open': True,
            'steps': [
                'Catat kode pembayaran yang tampil di halaman ini.',
                'Datang ke kasir Alfamart, Alfamidi, atau Dan+Dan.',
                'Berikan kode pembayaran dan pastikan nominalnya benar.',
                'Simpan struk pembayaran sampai status UniTrade berubah.',
            ],
        },
    ],
}


def _payment_method_instructions(key):
    return PAYMENT_METHOD_INSTRUCTIONS.get(key) or [
        {
            'title': 'Selesaikan dari halaman pembayaran',
            'open': True,
            'steps': [
                'Gunakan QR, nomor VA, kode pembayaran, atau tombol lanjut pembayaran yang tersedia.',
                'Selesaikan pembayaran sesuai instruksi dari aplikasi bank/e-wallet.',
                'Tunggu konfirmasi otomatis dari Midtrans ke UniTrade.',
            ],
        },
    ]


PAYMENT_METHOD_UI = {
    key: {
        'title': value['label'],
        'label': value['label'],
        'badge': value.get('badge') or value['channel_code'],
        'logo': value.get('logo') or '',
        'reference_label': value.get('reference_label') or 'Kode Pembayaran',
        'type': value['type'],
        'instructions': _payment_method_instructions(key),
    }
    for key, value in MIDTRANS_PAYMENT_METHODS.items()
}


class UnitradePaymentController(http.Controller):
    def _get_midtrans_param(self, key_name, default=''):
        return request.env['ir.config_parameter'].sudo().get_param(key_name, default=default)

    def _get_xendit_param(self, key_name, default=''):
        return request.env['ir.config_parameter'].sudo().get_param(key_name, default=default)

    def _payment_provider_expiry_minutes(self, intent):
        config = request.env['ir.config_parameter'].sudo()
        if intent.provider == 'midtrans':
            raw = config.get_param('unitrade.midtrans.payment_expiry_minutes', '30')
            fallback = 30
            minimum = 15
        elif intent.provider == 'xendit':
            raw = config.get_param('unitrade.xendit.payment_expiry_minutes', '30')
            fallback = 30
            minimum = 5
        else:
            raw = '30'
            fallback = 30
            minimum = 1
        try:
            minutes = int(raw)
        except (TypeError, ValueError):
            minutes = fallback
        return max(minimum, min(minutes, 1440))

    def _payment_effective_expires_at(self, intent):
        dates = []
        if intent.expires_at:
            dates.append(intent.expires_at)
        if intent.create_date and intent.provider in ('midtrans', 'xendit'):
            dates.append(intent.create_date + timedelta(minutes=self._payment_provider_expiry_minutes(intent)))
        return min(dates) if dates else False

    def _sync_payment_timeout(self, intent):
        if not intent or intent.state != 'pending':
            return intent
        expires_at = self._payment_effective_expires_at(intent)
        if not expires_at or expires_at > fields.Datetime.now():
            return intent
        minutes = self._payment_provider_expiry_minutes(intent)
        intent.sudo().write({
            'state': 'expired',
            'error_message': _('Waktu pembayaran %s menit sudah habis.') % minutes,
        })
        if intent.intent_type == 'listing_fee' and hasattr(intent, '_archive_unpaid_listing_fee_products'):
            intent._archive_unpaid_listing_fee_products()
        order = intent.sale_order_id.sudo()
        if order and order.x_payment_status == 'pending':
            order.write({'x_payment_status': 'expired'})
        return intent

    def _json_response(self, payload, status=200):
        return request.make_response(
            json.dumps(payload, ensure_ascii=False),
            headers=[('Content-Type', 'application/json')],
            status=status,
        )

    def _check_marketplace_access(self, feature_label):
        user = request.env.user
        if not user._is_public() and hasattr(user, '_check_unitrade_marketplace_access'):
            user._check_unitrade_marketplace_access(feature_label)

    def _payment_intent_by_reference(self, reference):
        if not reference:
            return request.env['unitrade.payment.intent'].sudo().browse()
        intent = request.env['unitrade.payment.intent'].sudo().search([
            ('provider', '=', 'midtrans'),
            '|',
            ('midtrans_order_id', '=', reference),
            ('midtrans_transaction_id', '=', reference),
        ], limit=1)
        if intent:
            return intent
        return request.env['unitrade.payment.intent'].sudo().search([
            ('provider', 'in', ('midtrans', 'xendit')),
            '|',
            ('name', '=', reference),
            ('xendit_reference_id', '=', reference),
        ], limit=1)

    def _intent_reference_key(self, intent):
        return intent.midtrans_order_id or intent.xendit_reference_id or intent.name

    def _payment_reference(self, intent):
        return intent.payment_reference or self._intent_reference_key(intent)

    def _payment_has_direct_reference(self, intent):
        reference = intent.payment_reference or ''
        return bool(reference and reference != self._intent_reference_key(intent) and not intent.qr_string)

    def _payment_qr_content(self, intent):
        return intent.qr_string or ''

    def _payment_qr_src(self, intent):
        if self._payment_qr_content(intent):
            qr_value = self._payment_qr_content(intent)
            if str(qr_value).startswith(('http://', 'https://')):
                return qr_value
            return '/unitrade/payment/qr/%s.svg' % self._intent_reference_key(intent)
        return False

    def _order_status_url(self, order):
        if not order:
            return '/my/orders'
        token = ''
        try:
            token = order.sudo()._portal_ensure_token()
        except Exception:
            _logger.exception('Failed to build UniTrade order status token for order %s', order.id)
        url = '/unitrade/order/status/%s' % order.id
        if token:
            url += '?access_token=%s' % quote(token)
        return url

    def _append_query(self, url, **params):
        clean_params = [
            '%s=%s' % (quote(str(key)), quote(str(value)))
            for key, value in params.items()
            if value not in (None, False, '')
        ]
        if not clean_params:
            return url
        return url + ('&' if '?' in url else '?') + '&'.join(clean_params)

    def _read_evidence_upload(self, field_name, label):
        upload = request.httprequest.files.get(field_name)
        if not upload or not getattr(upload, 'filename', ''):
            raise UserError(_('Upload foto %s terlebih dahulu.') % label)

        data = upload.read()
        if not data:
            raise UserError(_('File foto %s kosong atau tidak terbaca.') % label)
        if len(data) > 5 * 1024 * 1024:
            raise UserError(_('Ukuran foto %s maksimal 5 MB.') % label)

        content_type = (getattr(upload, 'content_type', '') or '').split(';', 1)[0].lower()
        allowed_types = {'image/jpeg', 'image/png', 'image/webp'}
        if content_type and content_type not in allowed_types:
            raise UserError(_('Format foto %s harus JPG, PNG, atau WebP.') % label)

        return base64.b64encode(data).decode('ascii'), upload.filename

    def _binary_image_data_uri(self, image, default=''):
        if not image:
            return default
        try:
            return image_data_uri(image.encode() if isinstance(image, str) else image)
        except Exception:
            _logger.exception('Failed to build image data URI for order status page.')
            return default

    def _order_status_seller_value(self, seller):
        seller = seller.sudo()
        avatar_image = (
            seller.x_avatar_128
            or (seller.user_id.avatar_128 if seller.user_id else False)
            or (seller.partner_id.image_128 if seller.partner_id else False)
        )
        public_ref = seller.x_store_slug or seller.x_profile_uuid or str(seller.id)
        location = ', '.join(part for part in [
            seller.x_store_city or '',
            seller.x_store_province or '',
        ] if part)
        return {
            'id': seller.id,
            'name': seller.name or seller.user_id.name or _('Penjual UniTrade'),
            'avatar_url': self._binary_image_data_uri(avatar_image, '/web/static/img/user_menu_avatar.png'),
            'description': seller.x_profile_description or seller.x_payout_note or '',
            'location': location,
            'address': seller.x_store_address_detail or seller.x_profile_address or '',
            'profile_url': '/seller-profile/%s' % quote(str(public_ref)),
            'chat_url': '/seller-profile/%s/chat' % quote(str(public_ref)),
            'active': bool(seller.x_store_active),
        }

    def _order_status_fallback_seller_value(self, product_lines):
        product_template = product_lines[:1].product_id.product_tmpl_id if product_lines else False
        name = ''
        location = ''
        if product_template:
            name = getattr(product_template, 'x_seller_name', '') or ''
            location = getattr(product_template, 'x_seller_location', '') or ''
        return {
            'id': 0,
            'name': name or _('Penjual UniTrade'),
            'avatar_url': '/web/static/img/user_menu_avatar.png',
            'description': '',
            'location': location,
            'address': '',
            'profile_url': '#',
            'chat_url': '#',
            'active': True,
        }

    def _payment_method_meta(self, intent):
        return PAYMENT_METHOD_UI.get(intent.payment_method_code or '', {
            'title': intent.payment_method_label or 'Midtrans',
            'label': intent.payment_method_label or 'Midtrans',
            'badge': intent.midtrans_bank or intent.midtrans_payment_type or intent.xendit_channel_code or 'MIDTRANS',
            'logo': '',
            'reference_label': 'Kode Pembayaran',
            'type': '',
            'instructions': [],
        })

    def _payment_status_copy(self, status, intent=None):
        if intent and intent.intent_type == 'listing_fee':
            if status == 'paid':
                return {
                    'title': 'Pembayaran Berhasil',
                    'copy': 'Pembayaran fee upload sudah dikonfirmasi. Produk Anda sudah aktif di katalog.',
                    'message': 'Pembayaran fee upload sudah dikonfirmasi. Produk Anda sudah aktif di katalog.',
                    'tone': 'success',
                }
            if status == 'expired':
                return {
                    'title': 'Pembayaran Kedaluwarsa',
                    'copy': 'Waktu pembayaran fee upload sudah habis. Buat transaksi baru dari halaman barang.',
                    'message': 'Waktu pembayaran fee upload sudah habis. Buat transaksi baru dari halaman barang.',
                    'tone': 'danger',
                }
            if status in ('failed', 'cancelled'):
                return {
                    'title': 'Pembayaran Gagal',
                    'copy': 'Pembayaran fee upload gagal atau dibatalkan. Produk belum aktif di katalog.',
                    'message': 'Pembayaran fee upload gagal atau dibatalkan. Produk belum aktif di katalog.',
                    'tone': 'danger',
                }
            return {
                'title': 'Menunggu Pembayaran',
                'copy': 'Selesaikan pembayaran agar produk aktif di katalog selama 30 hari.',
                'message': 'Selesaikan pembayaran agar produk aktif di katalog selama 30 hari.',
                'tone': 'warning',
            }
        if status == 'paid':
            return {
                'title': 'Pembayaran Berhasil',
                'copy': 'Pembayaran sudah dikonfirmasi. Pesanan Anda sedang diproses penjual.',
                'message': 'Pembayaran sudah dikonfirmasi. Pesanan Anda sedang diproses penjual.',
                'tone': 'success',
            }
        if status == 'expired':
            return {
                'title': 'Pembayaran Kedaluwarsa',
                'copy': 'Waktu pembayaran sudah habis. Silakan kembali ke checkout untuk membuat pembayaran baru.',
                'message': 'Waktu pembayaran sudah habis. Silakan kembali ke checkout untuk membuat pembayaran baru.',
                'tone': 'danger',
            }
        if status in ('failed', 'cancelled'):
            return {
                'title': 'Pembayaran Gagal',
                'copy': 'Pembayaran gagal atau dibatalkan. Pesanan belum diproses, silakan coba metode lain dari checkout.',
                'message': 'Pembayaran gagal atau dibatalkan. Pesanan belum diproses, silakan coba metode lain dari checkout.',
                'tone': 'danger',
            }
        return {
            'title': 'Menunggu Pembayaran',
            'copy': 'Selesaikan pembayaran sebelum waktu habis untuk memproses pesanan Anda.',
            'message': 'Selesaikan pembayaran sebelum waktu habis untuk memproses pesanan Anda.',
            'tone': 'warning',
        }

    def _format_money(self, amount, currency):
        amount = int(round(amount or 0.0))
        symbol = currency.symbol or currency.name or 'Rp'
        return '%s %s' % (symbol, format(amount, ',').replace(',', '.'))

    def _payment_product_lines(self, order):
        excluded_product_ids = set()
        if hasattr(order, '_unitrade_service_fee_product'):
            service_fee_product = order._unitrade_service_fee_product()
            if service_fee_product:
                excluded_product_ids.add(service_fee_product.id)
        if hasattr(order, '_unitrade_payment_fee_product'):
            payment_fee_product = order._unitrade_payment_fee_product()
            if payment_fee_product:
                excluded_product_ids.add(payment_fee_product.id)
        if hasattr(order, '_unitrade_voucher_discount_product'):
            voucher_product = order._unitrade_voucher_discount_product()
            if voucher_product:
                excluded_product_ids.add(voucher_product.id)
        return order.order_line.filtered(
            lambda line: (
                not line.display_type
                and line.product_id
                and line.product_id.id not in excluded_product_ids
            )
        )

    def _success_seller_values(self, order):
        product_lines = self._payment_product_lines(order)
        seller = False
        product = False
        for line in product_lines:
            product = line.product_id.product_tmpl_id
            if 'x_seller_id' in product._fields and product.x_seller_id:
                seller = product.x_seller_id.sudo()
                break
        if not seller:
            return {
                'name': 'Penjual UniTrade',
                'avatar_url': '/web/static/img/user_menu_avatar.png',
                'rating': 'Belum ada ulasan',
                'chat_url': '#',
            }

        review_count = 0
        average_rating = 0.0
        try:
            Review = request.env['unitrade.review'].sudo()
            seller_products = request.env['product.template'].sudo().search([('x_seller_id', '=', seller.id)])
            reviews = Review.search([
                ('product_id', 'in', seller_products.ids),
                ('is_visible', '=', True),
            ])
            review_count = len(reviews)
            average_rating = round(sum(reviews.mapped('rating')) / review_count, 1) if review_count else 0.0
        except Exception:
            _logger.exception('Failed to calculate success page seller rating for seller %s', seller.id)

        seller_ref = seller.x_profile_uuid or seller.id
        chat_url = '/seller-profile/%s/chat' % seller_ref
        if product:
            chat_url += '?product_id=%s' % product.id
        avatar_image = (
            seller.x_avatar_128
            or (seller.user_id.avatar_128 if seller.user_id else False)
            or (seller.partner_id.image_128 if seller.partner_id else False)
        )
        return {
            'name': seller.name or 'Penjual UniTrade',
            'avatar_url': self._binary_image_data_uri(avatar_image, '/web/static/img/user_menu_avatar.png'),
            'rating': ('%.1f (%s Ulasan)' % (average_rating, review_count)) if review_count else 'Belum ada ulasan',
            'chat_url': chat_url,
        }

    def _success_recommended_products(self, order, limit=6):
        Product = request.env['product.template'].sudo()
        excluded_ids = self._payment_product_lines(order).mapped('product_id.product_tmpl_id').ids
        domain = (
            Product._unitrade_public_active_domain()
            if hasattr(Product, '_unitrade_public_active_domain')
            else [('sale_ok', '=', True), ('website_published', '=', True)]
        )
        if excluded_ids:
            domain = expression.AND([domain, [('id', 'not in', excluded_ids)]])
        try:
            return Product.search(domain, order='create_date desc', limit=limit)
        except Exception:
            _logger.exception('Failed to load success page product recommendations for order %s', order.id)
            return Product.browse()

    def _listing_fee_status_url(self, intent):
        return '/unitrade/seller/products'

    def _listing_fee_product_image_url(self, product):
        if not product:
            return '/web/static/img/placeholder.png'
        return self._binary_image_data_uri(
            product.image_512 or product.image_1920 or product.image_128,
            '/web/static/img/placeholder.png',
        )

    def _listing_fee_payment_lines(self, intent):
        product = intent.product_template_id.sudo()
        product_name = product.display_name or product.name if product else _('Produk UniTrade')
        return [{
            'name': product_name or _('Produk UniTrade'),
            'seller_name': intent.seller_id.name or _('Toko Anda'),
            'price': self._format_money(intent.amount, intent.currency_id),
            'image_url': self._listing_fee_product_image_url(product),
        }]

    def _listing_fee_success_page_values(self, intent):
        product = intent.product_template_id.sudo()
        product_url = product.website_url or ('/shop/product/%s' % product.id) if product else '/unitrade/seller/products'
        product_name = product.display_name or product.name if product else _('Produk UniTrade')
        return {
            'payment_intent': intent,
            'order': request.env['sale.order'].sudo().browse(),
            'success_transaction_id': intent.midtrans_transaction_id or intent.midtrans_order_id or intent.name,
            'success_title': 'Produk Berhasil Diposting!',
            'success_next_title': 'Produk Sudah Aktif',
            'success_next_copy': 'Fee upload sudah dibayar. Produk Anda sekarang tampil di katalog UniTrade selama masa aktif listing.',
            'success_seller': False,
            'success_context_card': {
                'name': product_name or _('Produk UniTrade'),
                'meta': 'Aktif selama 30 hari sejak pembayaran berhasil',
                'image_url': self._listing_fee_product_image_url(product),
                'action_url': product_url,
                'action_label': 'Lihat Produk',
            },
            'success_steps': [
                {'label': 'Produk tampil di katalog dan halaman toko'},
                {'label': 'Pantau chat dan pesanan dari dashboard seller'},
                {'label': 'Perpanjang listing jika masa aktif sudah habis'},
            ],
            'success_primary_url': '/unitrade/seller/products',
            'success_primary_label': 'Lihat Daftar Barang',
            'success_secondary_url': '/unitrade/seller/dashboard',
            'success_secondary_label': 'Dashboard Seller',
            'success_recommended_products': request.env['product.template'].sudo().browse(),
            'status_url': '/unitrade/seller/products',
        }

    def _success_page_values(self, intent):
        intent = intent.sudo()
        if intent.intent_type == 'listing_fee':
            return self._listing_fee_success_page_values(intent)
        order = intent.sale_order_id.sudo()
        status_url = '/my/orders'
        try:
            status_url = self._order_status_url(order)
        except Exception:
            _logger.exception('Failed to build portal URL for paid order %s', order.id)
        return {
            'payment_intent': intent,
            'order': order,
            'success_transaction_id': intent.midtrans_transaction_id or intent.midtrans_order_id or intent.xendit_latest_payment_id or intent.xendit_reference_id or intent.name,
            'success_title': 'Pembayaran Berhasil!',
            'success_next_title': 'Langkah Selanjutnya',
            'success_next_copy': 'Transaksi kamu sudah aman. Sekarang tunggu prosesnya hingga selesai.',
            'success_seller': self._success_seller_values(order),
            'success_context_card': False,
            'success_steps': [
                {'label': 'Tunggu barang diproses'},
                {'label': 'Cek kondisi barang langsung'},
                {'label': 'Konfirmasi pesanan selesai di aplikasi'},
            ],
            'success_primary_url': status_url,
            'success_primary_label': 'Lihat Status Pesanan',
            'success_secondary_url': '/',
            'success_secondary_label': 'Kembali ke Beranda',
            'success_recommended_products': self._success_recommended_products(order),
            'status_url': status_url,
        }

    def _payment_page_values(self, intent):
        intent = intent.sudo()
        order = intent.sale_order_id.sudo()
        method_meta = self._payment_method_meta(intent)
        status_copy = self._payment_status_copy(intent.state, intent=intent)
        payment_reference = self._payment_reference(intent)
        payment_url = intent.payment_url or intent.deeplink_url
        is_listing_fee = intent.intent_type == 'listing_fee'
        order_status_url = self._listing_fee_status_url(intent) if is_listing_fee else self._order_status_url(order)
        if intent.state in ('expired', 'failed', 'cancelled') and is_listing_fee:
            primary_url = '/unitrade/seller/products'
            primary_label = 'Kembali ke Barang'
        elif intent.state in ('expired', 'failed', 'cancelled'):
            primary_url = '/shop/checkout'
            primary_label = 'Kembali ke Checkout'
        elif intent.state == 'paid' and is_listing_fee:
            primary_url = order_status_url
            primary_label = 'Lihat Daftar Barang'
        elif intent.state == 'paid':
            primary_url = order_status_url
            primary_label = 'Lihat Status Pesanan'
        else:
            primary_url = order_status_url
            primary_label = 'Cek Status Posting' if is_listing_fee else 'Cek Status Pembayaran'
        expires_at = self._payment_effective_expires_at(intent)
        expires_in_seconds = 0
        if expires_at and intent.state == 'pending':
            expires_in_seconds = max(0, int((expires_at - fields.Datetime.now()).total_seconds()))
        payment_lines = self._listing_fee_payment_lines(intent) if is_listing_fee else [{
            'name': line.product_id.product_tmpl_id.display_name,
            'seller_name': (
                line.product_id.product_tmpl_id.x_seller_id.name
                if 'x_seller_id' in line.product_id.product_tmpl_id._fields and line.product_id.product_tmpl_id.x_seller_id
                else 'Penjual UniTrade'
            ),
            'price': self._format_money(line.price_subtotal, order.currency_id),
            'image_url': '/web/image/product.template/%s/image_512' % line.product_id.product_tmpl_id.id,
        } for line in self._payment_product_lines(order)]
        return {
            'payment_intent': intent,
            'order': order,
            'page_title': status_copy['title'],
            'payment_method_meta': method_meta,
            'payment_status': intent.state,
            'payment_status_content': status_copy,
            'payment_status_title': status_copy['title'],
            'payment_status_copy': status_copy['copy'],
            'payment_status_tone': status_copy['tone'],
            'payment_total': self._format_money(intent.amount, intent.currency_id),
            'payment_reference': payment_reference,
            'payment_reference_raw': payment_reference,
            'payment_has_direct_reference': self._payment_has_direct_reference(intent),
            'payment_qr_src': self._payment_qr_src(intent),
            'payment_url': payment_url,
            'payment_status_url': '/unitrade/payment/status/%s' % self._intent_reference_key(intent),
            'payment_expired_iso': expires_at.isoformat() if expires_at else '',
            'payment_expires_at': expires_at.isoformat() if expires_at else '',
            'payment_expires_in_seconds': expires_in_seconds,
            'payment_primary_url': primary_url,
            'payment_primary_label': primary_label,
            'payment_secondary_url': '/unitrade/seller/dashboard' if is_listing_fee else '/',
            'payment_secondary_label': 'Dashboard Seller' if is_listing_fee else 'Kembali ke Beranda',
            'payment_lines_title': 'Detail Posting Produk' if is_listing_fee else 'Detail Pesanan',
            'payment_lines': payment_lines,
            'status_url': order_status_url,
        }

    def _payment_status_payload(self, intent):
        status_copy = self._payment_status_copy(intent.state, intent=intent)
        method_meta = self._payment_method_meta(intent)
        reference = self._payment_reference(intent)
        expires_at = self._payment_effective_expires_at(intent)
        is_listing_fee = intent.intent_type == 'listing_fee'
        status_url = self._listing_fee_status_url(intent) if is_listing_fee else self._order_status_url(intent.sale_order_id.sudo())
        if is_listing_fee and intent.state in ('expired', 'failed', 'cancelled'):
            primary_label = 'Kembali ke Barang'
            primary_url = '/unitrade/seller/products'
        elif is_listing_fee:
            primary_label = 'Lihat Daftar Barang'
            primary_url = status_url
        elif intent.state in ('expired', 'failed', 'cancelled'):
            primary_label = 'Kembali ke Checkout'
            primary_url = '/shop/checkout'
        else:
            primary_label = 'Lihat Pesanan'
            primary_url = status_url
        return {
            'status': intent.state,
            'title': status_copy['title'],
            'copy': status_copy['copy'],
            'message': status_copy['message'],
            'tone': status_copy['tone'],
            'reference_label': method_meta.get('reference_label') if self._payment_has_direct_reference(intent) else 'Order ID Midtrans',
            'reference': reference,
            'reference_raw': reference,
            'has_direct_reference': self._payment_has_direct_reference(intent),
            'qr_image_url': self._payment_qr_src(intent),
            'payment_url': intent.payment_url or intent.deeplink_url,
            'expires_at': expires_at.isoformat() if expires_at else '',
            'order_url': status_url,
            'primary_label': primary_label,
            'primary_url': primary_url,
            'success_url': '/unitrade/payment/success/%s' % self._intent_reference_key(intent),
        }

    def _can_view_order_status(self, order, access_token=None):
        if not order:
            return False
        if access_token and order.sudo().access_token and access_token == order.sudo().access_token:
            return True
        user = request.env.user
        if user._is_public():
            return False
        if user.has_group('sales_team.group_sale_manager') or user.has_group('base.group_system'):
            return True
        return order.partner_id.commercial_partner_id == user.partner_id.commercial_partner_id

    def _seller_order_detail_redirect(self, order):
        if not order or 'unitrade.seller' not in request.env.registry:
            return ''
        user = request.env.user
        if user._is_public():
            return ''
        seller = request.env['unitrade.seller'].sudo().search([
            ('user_id', '=', user.id),
            ('status', '=', 'verified'),
        ], limit=1)
        Product = request.env['product.template'].sudo()
        if not seller or 'x_seller_id' not in Product._fields:
            return ''
        seller_line = request.env['sale.order.line'].sudo().search([
            ('order_id', '=', order.id),
            ('display_type', '=', False),
            ('product_id', '!=', False),
            ('product_id.product_tmpl_id.x_seller_id', '=', seller.id),
        ], limit=1)
        return '/unitrade/seller/orders/%s' % order.id if seller_line else ''

    def _order_status_refund_records(self, order):
        if not order or 'unitrade.dispute' not in request.env.registry:
            return request.env['sale.order'].browse()
        return request.env['unitrade.dispute'].sudo().search([('order_id', '=', order.id)], order='create_date desc')

    def _order_status_refund_detail_url(self, order, dispute=False):
        if not order or not dispute:
            return ''
        return '/unitrade/order/%s/refund/%s' % (order.id, dispute.id)

    def _order_status_refund_progress_steps(self, order, dispute):
        order = order.sudo()
        dispute = dispute.sudo()
        timeline_by_key = {item.event_key: item for item in dispute.timeline_ids}
        refund_url = self._order_status_refund_detail_url(order, dispute)
        state = dispute.state
        final_success = state in ('approved', 'resolved') or order.x_escrow_state == 'refunded'
        final_failed = state in ('rejected', 'cancelled')
        has_buyer_return = bool(
            timeline_by_key.get('buyer_return_sent')
            or dispute.evidence_ids.filtered(lambda evidence: evidence.evidence_type == 'buyer_return_photo')
        )
        has_seller_confirmation = bool(
            timeline_by_key.get('seller_return_confirmed')
            or dispute.evidence_ids.filtered(lambda evidence: evidence.evidence_type == 'seller_return_photo')
        )
        review_done = (
            final_success
            or final_failed
            or state in ('need_buyer_evidence', 'need_seller_response')
            or bool(dispute.seller_decision_note)
            or has_buyer_return
            or has_seller_confirmation
        )
        review_active = state in ('submitted', 'under_review') and not review_done
        return_active = state == 'need_buyer_evidence'
        seller_confirm_active = state == 'need_seller_response'
        admin_final_active = state == 'admin_review_final' and bool(dispute.seller_decision_note or has_seller_confirmation)

        def step(key, label, done=False, active=False, failed=False, status='Pending', url=False):
            return {
                'key': key,
                'label': label,
                'status': status,
                'done': bool(done),
                'active': bool(active),
                'failed': bool(failed),
                'url': url or '',
            }

        return [
            step(
                'payment',
                'Pembayaran berhasil',
                done=order.x_payment_status in ('paid', 'refunded') or bool(dispute.payment_intent_id.paid_at),
                status='Completed',
            ),
            step(
                'refund_submitted',
                'Pengembalian diajukan',
                done=bool(dispute.submitted_at or dispute.create_date),
                status='Completed',
                url=refund_url,
            ),
            step(
                'refund_review',
                'Review admin/seller',
                done=review_done,
                active=review_active,
                failed=final_failed and not (dispute.seller_decision_note or has_buyer_return or has_seller_confirmation),
                status='Completed' if review_done else 'In Progress' if review_active else 'Pending',
                url=refund_url,
            ),
            step(
                'return_item',
                'Barang dikembalikan',
                done=has_buyer_return or has_seller_confirmation or final_success,
                active=return_active,
                status='Completed' if has_buyer_return or has_seller_confirmation or final_success else 'In Progress' if return_active else 'Pending',
                url=refund_url,
            ),
            step(
                'admin_final',
                'Review final admin',
                done=final_success,
                active=admin_final_active,
                failed=final_failed,
                status='Completed' if final_success else 'Ditolak' if final_failed else 'In Progress' if admin_final_active else 'Pending',
                url=refund_url,
            ),
            step(
                'refund_done',
                'Refund selesai',
                done=final_success,
                failed=final_failed,
                status='Completed' if final_success else 'Ditolak' if final_failed else 'Pending',
                url=refund_url,
            ),
        ]

    def _order_status_progress_steps(self, order, ledgers=False, refund_disputes=False):
        order = order.sudo()
        ledgers = ledgers or request.env['unitrade.escrow.ledger'].sudo().search([('order_id', '=', order.id)])
        if refund_disputes is False:
            refund_disputes = self._order_status_refund_records(order)
        latest_refund = refund_disputes[:1] if refund_disputes else False
        if latest_refund:
            return self._order_status_refund_progress_steps(order, latest_refund)
        ledger_count = len(ledgers)
        buyer_confirmed_count = len(ledgers.filtered(lambda ledger: ledger.buyer_confirmed_at))
        seller_confirmed_count = len(ledgers.filtered(lambda ledger: ledger.seller_confirmed_at))
        all_seller_confirmed = bool(ledgers) and seller_confirmed_count == ledger_count
        all_buyer_confirmed = bool(ledgers) and buyer_confirmed_count == ledger_count
        all_ledgers_confirmed = bool(ledgers) and all_seller_confirmed and all_buyer_confirmed

        is_cancelled = (
            order.state == 'cancel'
            or order.x_payment_status in ('failed', 'expired', 'cancelled')
            or order.x_unitrade_order_state == 'cancelled'
            or order.x_escrow_state == 'cancelled'
        )
        is_refunded = (
            order.x_payment_status == 'refunded'
            or order.x_unitrade_order_state == 'refunded'
            or order.x_escrow_state == 'refunded'
        )
        payment_done = order.x_payment_status in ('paid', 'refunded') or order.x_unitrade_order_state in ('processing', 'completed', 'refunded')
        if ledgers:
            order_done = all_ledgers_confirmed and (
                order.x_unitrade_order_state == 'completed'
                or order.x_escrow_state in ('releasable', 'released')
                or all(ledger.state in ('releasable', 'released') for ledger in ledgers)
            )
        else:
            order_done = order.x_unitrade_order_state == 'completed'

        def step(key, label, done=False, active=False, status='Pending'):
            return {
                'key': key,
                'label': label,
                'status': status,
                'done': bool(done),
                'active': bool(active),
            }

        if is_cancelled:
            return [
                step('payment', 'Pembayaran berhasil', active=True, status='Dibatalkan'),
                step('seller_handoff', 'Barang diserahkan'),
                step('buyer_received', 'Barang diterima'),
                step('completed', 'Selesai'),
            ]

        return [
            step(
                'payment',
                'Pembayaran berhasil',
                done=payment_done,
                active=not payment_done and not is_refunded,
                status='Completed' if payment_done else 'Pending',
            ),
            step(
                'seller_handoff',
                'Barang diserahkan',
                done=all_seller_confirmed,
                active=payment_done and not all_seller_confirmed and not is_refunded,
                status='Completed' if all_seller_confirmed else ('In Progress' if payment_done and not is_refunded else 'Pending'),
            ),
            step(
                'buyer_received',
                'Barang diterima',
                done=all_buyer_confirmed,
                active=all_seller_confirmed and not all_buyer_confirmed and not is_refunded,
                status='Completed' if all_buyer_confirmed else ('In Progress' if all_seller_confirmed and not is_refunded else 'Pending'),
            ),
            step(
                'completed',
                'Selesai',
                done=order_done,
                active=all_buyer_confirmed and not order_done and not is_refunded,
                status='Completed' if order_done else ('Refund' if is_refunded else 'Pending'),
            ),
        ]

    def _order_status_values(self, order):
        order = order.sudo()
        intent = order.x_payment_intent_id.sudo() if order.x_payment_intent_id else request.env['unitrade.payment.intent'].sudo().search([
            ('sale_order_id', '=', order.id),
            ('provider', 'in', ('midtrans', 'xendit')),
        ], order='create_date desc', limit=1)
        ledgers = request.env['unitrade.escrow.ledger'].sudo().search([('order_id', '=', order.id)])
        product_lines = self._payment_product_lines(order)
        try:
            amounts = order._unitrade_checkout_amounts(
                sync_fee=False,
                payment_method=intent.payment_method_code if intent else None,
            )
        except Exception:
            _logger.exception('Failed to build order status amounts for order %s', order.id)
            amounts = {
                'item_subtotal': sum(product_lines.mapped('price_subtotal')),
                'service_fee': 0.0,
                'payment_fee': intent.amount_gateway_fee if intent else 0.0,
                'total': intent.amount if intent else order.amount_total,
                'item_quantity': sum(product_lines.mapped('product_uom_qty')),
            }
        status_map = {
            'pending': ('Menunggu Pembayaran', 'Pembayaran belum dikonfirmasi oleh Midtrans.'),
            'paid': ('Diproses', 'Pembayaran berhasil. Penjual akan menyerahkan barang dan mengunggah bukti terlebih dahulu.'),
            'failed': ('Gagal', 'Pembayaran gagal. Silakan buat pembayaran baru dari checkout.'),
            'expired': ('Kedaluwarsa', 'Waktu pembayaran sudah habis.'),
            'cancelled': ('Dibatalkan', 'Pembayaran dibatalkan.'),
            'refunded': ('Pengembalian', 'Dana dikembalikan ke pembeli.'),
        }
        payment_title, payment_copy = status_map.get(order.x_payment_status or 'pending', status_map['pending'])
        if hasattr(order, 'unitrade_status_payload'):
            status_payload = order.unitrade_status_payload(ledger=ledgers[:1])
            payment_title = status_payload.get('label') or payment_title
            payment_copy = status_payload.get('note') or payment_copy
        escrow_state = order.x_escrow_state or 'none'
        process_map = {
            'none': ('Menunggu Pembayaran', 'Pesanan mulai diproses setelah pembayaran dikonfirmasi.'),
            'held': ('Diproses', 'Penjual sedang menyiapkan serah barang. Buyer bisa menyelesaikan setelah seller mengunggah bukti.'),
            'releasable': ('Menunggu Konfirmasi', 'Serah terima barang sudah dikonfirmasi oleh seller dan menunggu buyer.'),
            'released': ('Selesai', 'Transaksi sudah selesai.'),
            'disputed': ('Perlu Ditinjau', 'Transaksi sedang ditinjau oleh UniTrade.'),
            'refunded': ('Pengembalian', 'Pembayaran dikembalikan ke pembeli.'),
            'cancelled': ('Dibatalkan', 'Pesanan dibatalkan.'),
        }
        process_title, process_copy = process_map.get(escrow_state, process_map['none'])
        line_values = [{
            'name': line.product_id.product_tmpl_id.display_name,
            'qty': int(line.product_uom_qty or 0),
            'price': self._format_money(line.price_subtotal, order.currency_id),
            'image_url': '/web/image/product.template/%s/image_512' % line.product_id.product_tmpl_id.id,
        } for line in product_lines]
        seller_records = request.env['unitrade.seller'].sudo().browse()
        if 'unitrade.seller' in request.env.registry:
            seller_records |= ledgers.mapped('seller_id').sudo()
            if intent and intent.seller_id:
                seller_records |= intent.seller_id.sudo()
            for line in product_lines:
                product_template = line.product_id.product_tmpl_id
                if 'x_seller_id' in product_template._fields and product_template.x_seller_id:
                    seller_records |= product_template.x_seller_id.sudo()
                if (
                    not getattr(product_template, 'x_seller_id', False)
                    and product_template.create_uid
                    and 'x_seller_id' in product_template.create_uid._fields
                    and product_template.create_uid.x_seller_id
                ):
                    seller_records |= product_template.create_uid.x_seller_id.sudo()
        seller_records = request.env['unitrade.seller'].sudo().browse(list(dict.fromkeys(seller_records.ids)))
        seller_values = [self._order_status_seller_value(seller) for seller in seller_records]
        if not seller_values:
            seller_values = [self._order_status_fallback_seller_value(product_lines)]
        seller_by_id = {seller.get('id'): seller for seller in seller_values}
        ledger_values = [{
            'id': ledger.id,
            'name': ledger.name,
            'seller': seller_by_id.get(ledger.seller_id.id, {}) if ledger.seller_id else {},
            'buyer_confirmed': bool(ledger.buyer_confirmed_at),
            'seller_confirmed': bool(ledger.seller_confirmed_at),
            'buyer_evidence': bool(ledger.buyer_received_image),
            'seller_evidence': bool(ledger.seller_handoff_image),
            'buyer_evidence_url': self._binary_image_data_uri(ledger.buyer_received_image),
            'seller_evidence_url': self._binary_image_data_uri(ledger.seller_handoff_image),
            'buyer_filename': ledger.buyer_received_filename or '',
            'seller_filename': ledger.seller_handoff_filename or '',
            'seller_location': ledger.seller_handoff_location or '',
            'buyer_confirmed_at': fields.Datetime.to_string(ledger.buyer_confirmed_at) if ledger.buyer_confirmed_at else '',
            'seller_confirmed_at': fields.Datetime.to_string(ledger.seller_confirmed_at) if ledger.seller_confirmed_at else '',
            'completed': bool(ledger.completed_at),
        } for ledger in ledgers]
        buyer_confirmed_count = len(ledgers.filtered(lambda ledger: ledger.buyer_confirmed_at))
        seller_confirmed_count = len(ledgers.filtered(lambda ledger: ledger.seller_confirmed_at))
        all_ledgers_confirmed = bool(ledgers) and buyer_confirmed_count == len(ledgers) and seller_confirmed_count == len(ledgers)
        can_confirm_received = (
            order.x_payment_status == 'paid'
            and order.x_unitrade_order_state not in ('cancelled', 'completed')
            and order.x_escrow_state not in ('disputed', 'refunded', 'cancelled')
            and bool(ledgers)
            and seller_confirmed_count == len(ledgers)
            and buyer_confirmed_count < len(ledgers)
        )
        cancel_blocker = order._unitrade_direct_cancel_blocker() if hasattr(order, '_unitrade_direct_cancel_blocker') else _('Pembatalan tidak tersedia.')
        can_cancel = not bool(cancel_blocker)
        refund_disputes = self._order_status_refund_records(order)
        active_refund = refund_disputes[:0] if refund_disputes else request.env['sale.order'].browse()
        can_refund = False
        refund_detail_url = ''
        if refund_disputes:
            Dispute = request.env['unitrade.dispute'].sudo()
            active_refund = refund_disputes.filtered(lambda dispute: dispute.state in Dispute.ACTIVE_STATES)[:1]
            if refund_disputes:
                refund_detail_url = self._order_status_refund_detail_url(order, refund_disputes[0])
        elif (
            not request.env.user._is_public()
            and hasattr(order, '_unitrade_refund_blocker')
            and order.partner_id.commercial_partner_id == request.env.user.partner_id.commercial_partner_id
        ):
            can_refund = not bool(order._unitrade_refund_blocker(partner=request.env.user.partner_id))
        refund_values = [{
            'name': dispute.name,
            'state': dispute.state,
            'state_label': dict(dispute._fields['state'].selection).get(dispute.state, dispute.state),
            'reason': dict(dispute._fields['reason_code'].selection).get(dispute.reason_code, dispute.reason_code),
            'requested_amount': self._format_money(dispute.requested_amount, dispute.currency_id),
            'approved_amount': self._format_money(dispute.approved_amount, dispute.currency_id) if dispute.approved_amount else '',
            'submitted_at': dispute.submitted_at,
            'decision_note': dispute.admin_decision_note or '',
            'evidence_count': len(dispute.evidence_ids),
            'url': self._order_status_refund_detail_url(order, dispute),
        } for dispute in refund_disputes]
        progress_steps = self._order_status_progress_steps(order, ledgers=ledgers, refund_disputes=refund_disputes)
        return {
            'order': order,
            'payment_intent': intent,
            'order_status_payment_title': payment_title,
            'order_status_payment_copy': payment_copy,
            'order_status_process_title': process_title,
            'order_status_process_copy': process_copy,
            'order_status_ledgers': ledger_values,
            'order_status_sellers': seller_values,
            'order_status_lines': line_values,
            'order_status_amounts': amounts,
            'order_status_total': self._format_money(intent.amount if intent else amounts.get('total'), order.currency_id),
            'order_status_subtotal': self._format_money(amounts.get('item_subtotal'), order.currency_id),
            'order_status_service_fee': self._format_money(amounts.get('service_fee'), order.currency_id),
            'order_status_payment_fee': self._format_money(amounts.get('payment_fee'), order.currency_id),
            'order_status_voucher_discount': self._format_money(amounts.get('voucher_discount'), order.currency_id),
            'order_status_voucher_code': amounts.get('voucher_name') or amounts.get('voucher_code') or '',
            'order_status_progress_steps': progress_steps,
            'order_status_progress_count': len(progress_steps),
            'order_status_buyer_confirmed_count': buyer_confirmed_count,
            'order_status_seller_confirmed_count': seller_confirmed_count,
            'order_status_ledger_count': len(ledgers),
            'order_status_can_confirm_received': can_confirm_received,
            'order_status_can_cancel': can_cancel,
            'order_status_refunds': refund_values,
            'order_status_active_refund': active_refund,
            'order_status_can_refund': can_refund,
            'order_status_refund_detail_url': refund_detail_url,
            'order_status_access_token': request.params.get('access_token') or '',
            'order_status_cancel_blocker': cancel_blocker or '',
            'order_status_confirm_received_url': '/unitrade/order/%s/confirm-received' % order.id,
            'order_status_cancel_url': '/unitrade/order/%s/cancel' % order.id,
        }

    def _midtrans_event_key(self, payload, payload_hash):
        transaction_id = payload.get('transaction_id')
        order_id = payload.get('order_id')
        status = payload.get('transaction_status') or payload.get('status_code')
        return '%s:%s:%s' % (order_id or transaction_id or payload_hash, transaction_id or '', status or ''), transaction_id

    def _validate_midtrans_signature(self, payload):
        server_key = self._get_midtrans_param('unitrade.midtrans.server_key')
        if not server_key:
            _logger.warning('Midtrans server key is not configured.')
            return False
        signature = payload.get('signature_key')
        if not signature:
            _logger.warning('Midtrans webhook missing signature_key.')
            return False
        raw = '%s%s%s%s' % (
            payload.get('order_id') or '',
            payload.get('status_code') or '',
            payload.get('gross_amount') or '',
            server_key,
        )
        expected = hashlib.sha512(raw.encode('utf-8')).hexdigest()
        return str(signature).lower() == expected.lower()

    def _normalize_midtrans_status(self, payload):
        status = str(payload.get('transaction_status') or '').lower()
        fraud_status = str(payload.get('fraud_status') or '').lower()
        if status == 'settlement':
            return 'paid'
        if status == 'capture' and fraud_status in ('accept', ''):
            return 'paid'
        if status == 'pending':
            return 'pending'
        if status == 'expire':
            return 'expired'
        if status in ('deny', 'cancel', 'failure'):
            return 'failed'
        return 'pending'

    def _find_midtrans_intent_from_payload(self, payload):
        order_id = payload.get('order_id')
        transaction_id = payload.get('transaction_id')
        intent_env = request.env['unitrade.payment.intent'].sudo()
        if order_id:
            intent = intent_env.search([('provider', '=', 'midtrans'), ('midtrans_order_id', '=', order_id)], limit=1)
            if intent:
                return intent
            intent = intent_env.search([('provider', '=', 'midtrans'), ('name', '=', order_id)], limit=1)
            if intent:
                return intent
        if transaction_id:
            intent = intent_env.search([('provider', '=', 'midtrans'), ('midtrans_transaction_id', '=', transaction_id)], limit=1)
            if intent:
                return intent
        return intent_env.browse()

    def _midtrans_payload_amount(self, payload):
        amount = payload.get('gross_amount')
        if amount is None:
            return False
        try:
            return int(round(float(amount)))
        except (TypeError, ValueError):
            return False

    def _update_midtrans_intent_payment_details(self, intent, payload):
        if intent.sale_order_id:
            details = intent.sale_order_id._midtrans_extract_payment_details(payload)
        elif hasattr(intent, '_midtrans_extract_payment_details'):
            details = intent._midtrans_extract_payment_details(payload)
        else:
            details = {}
        write_values = {}
        if payload.get('transaction_id') and not intent.midtrans_transaction_id:
            write_values['midtrans_transaction_id'] = payload['transaction_id']
        if payload.get('payment_type') and not intent.midtrans_payment_type:
            write_values['midtrans_payment_type'] = payload['payment_type']
        if details.get('payment_reference') and not intent.payment_reference:
            write_values['payment_reference'] = details['payment_reference']
        if details.get('qr_string') and not intent.qr_string:
            write_values['qr_string'] = details['qr_string']
        if details.get('payment_url') and not intent.payment_url:
            write_values['payment_url'] = details['payment_url']
        if details.get('deeplink_url') and not intent.deeplink_url:
            write_values['deeplink_url'] = details['deeplink_url']
        if details.get('actions') and not intent.midtrans_actions:
            write_values['midtrans_actions'] = json.dumps(details.get('actions') or [], ensure_ascii=False, indent=2)
        if write_values:
            intent.write(write_values)

    def _sync_listing_fee_intent_status(self, intent, status, payload, extra_values=None):
        if intent.intent_type != 'listing_fee':
            return False
        write_values = {
            'state': status if status in ('paid', 'expired', 'failed') else 'pending',
            'raw_response': json.dumps(payload, ensure_ascii=False, indent=2),
        }
        if status == 'paid' and not intent.paid_at:
            write_values['paid_at'] = fields.Datetime.now()
        if extra_values:
            write_values.update(extra_values)
        intent.sudo().write(write_values)
        if write_values['state'] in ('expired', 'failed', 'cancelled') and hasattr(intent, '_archive_unpaid_listing_fee_products'):
            intent._archive_unpaid_listing_fee_products()
        return True

    def _midtrans_status_url(self, intent):
        order = intent.sale_order_id.sudo()
        base_url = order._midtrans_api_base_url() if order else intent._midtrans_api_base_url()
        return '%s/v2/%s/status' % (base_url.rstrip('/'), quote(intent.midtrans_order_id or intent.name or ''))

    def _fetch_midtrans_status(self, intent):
        server_key = self._get_midtrans_param('unitrade.midtrans.server_key')
        if not server_key or intent.provider != 'midtrans' or not (intent.midtrans_order_id or intent.name):
            return False
        response = requests.get(
            self._midtrans_status_url(intent),
            headers={'Accept': 'application/json'},
            auth=(server_key, ''),
            timeout=20,
        )
        try:
            payload = response.json()
        except ValueError:
            payload = {'raw_response': response.text}
        if response.status_code >= 400:
            _logger.warning(
                'Midtrans status sync failed for intent %s: %s %s',
                intent.name,
                response.status_code,
                payload,
            )
            return False
        return payload

    def _sync_midtrans_status_from_api(self, intent):
        intent = intent.sudo()
        if intent.provider != 'midtrans' or intent.state != 'pending':
            return intent
        try:
            payload = self._fetch_midtrans_status(intent)
            if not payload:
                return intent
            self._update_midtrans_intent_payment_details(intent, payload)
            status = self._normalize_midtrans_status(payload)
            if self._sync_listing_fee_intent_status(intent, status, payload, {
                'midtrans_transaction_id': payload.get('transaction_id') or intent.midtrans_transaction_id,
                'midtrans_payment_type': payload.get('payment_type') or intent.midtrans_payment_type,
            }):
                return intent
            if status == 'paid':
                intent.sale_order_id.sudo()._unitrade_mark_midtrans_paid(intent.sudo(), payload)
            elif status in ('expired', 'failed'):
                intent.sudo().write({
                    'state': status,
                    'raw_response': json.dumps(payload, ensure_ascii=False, indent=2),
                    'midtrans_transaction_id': payload.get('transaction_id') or intent.midtrans_transaction_id,
                    'midtrans_payment_type': payload.get('payment_type') or intent.midtrans_payment_type,
                })
                intent.sale_order_id.sudo().write({
                    'x_payment_status': 'expired' if status == 'expired' else 'failed',
                    'x_unitrade_order_state': 'payment_pending',
                    'x_midtrans_transaction_id': payload.get('transaction_id') or intent.midtrans_transaction_id,
                    'x_midtrans_payment_type': payload.get('payment_type') or intent.midtrans_payment_type,
                })
            elif payload:
                intent.sudo().write({'raw_response': json.dumps(payload, ensure_ascii=False, indent=2)})
        except Exception:
            _logger.exception('Failed to sync Midtrans status for intent %s', intent.name)
        return intent

    @http.route('/unitrade/payment/midtrans/webhook', type='http', auth='none', csrf=False, methods=['POST'])
    def midtrans_webhook(self, **kwargs):
        body = request.httprequest.get_data() or b''
        payload_hash = hashlib.sha256(body).hexdigest()
        try:
            payload = json.loads(body.decode('utf-8') or '{}')
        except ValueError:
            return self._json_response({'status': 'error', 'message': 'invalid json'}, status=400)

        if not self._validate_midtrans_signature(payload):
            return self._json_response({'status': 'error', 'message': 'invalid signature'}, status=401)

        request_key, request_id = self._midtrans_event_key(payload, payload_hash)
        event_key = 'midtrans:%s' % request_key
        event_env = request.env['unitrade.payment.event'].sudo()
        existing_event = event_env.search([('event_key', '=', event_key)], limit=1)
        if existing_event and existing_event.state == 'processed':
            return self._json_response({'status': 'ok', 'duplicate': True})

        event = existing_event or event_env.create({
            'name': event_key,
            'provider': 'midtrans',
            'event_key': event_key,
            'request_id': request_id,
            'payload_hash': payload_hash,
            'payload_json': json.dumps(payload, ensure_ascii=False, indent=2),
            'state': 'received',
        })

        try:
            intent = self._find_midtrans_intent_from_payload(payload)
            if not intent:
                event.write({'state': 'failed', 'error_message': 'No matching payment intent.'})
                return self._json_response({'status': 'error', 'message': 'intent not found'}, status=404)

            event.write({
                'payment_intent_id': intent.id,
                'order_id': intent.sale_order_id.id or False,
            })
            self._update_midtrans_intent_payment_details(intent, payload)
            payload_amount = self._midtrans_payload_amount(payload)
            if payload_amount and payload_amount != int(round(intent.amount)):
                event.write({
                    'state': 'failed',
                    'error_message': 'Amount mismatch: webhook=%s intent=%s' % (payload_amount, int(round(intent.amount))),
                })
                return self._json_response({'status': 'error', 'message': 'amount mismatch'}, status=400)

            status = self._normalize_midtrans_status(payload)
            if self._sync_listing_fee_intent_status(intent, status, payload, {
                'midtrans_transaction_id': payload.get('transaction_id') or intent.midtrans_transaction_id,
                'midtrans_payment_type': payload.get('payment_type') or intent.midtrans_payment_type,
            }):
                event.write({'state': 'processed', 'error_message': False})
                return self._json_response({'status': 'ok'})
            if status == 'paid':
                intent.sale_order_id.sudo()._unitrade_mark_midtrans_paid(intent.sudo(), payload)
            elif status in ('expired', 'failed'):
                intent.sudo().write({
                    'state': status,
                    'raw_response': json.dumps(payload, ensure_ascii=False, indent=2),
                    'midtrans_transaction_id': payload.get('transaction_id') or intent.midtrans_transaction_id,
                    'midtrans_payment_type': payload.get('payment_type') or intent.midtrans_payment_type,
                })
                intent.sale_order_id.sudo().write({
                    'x_payment_status': 'expired' if status == 'expired' else 'failed',
                    'x_unitrade_order_state': 'payment_pending',
                    'x_midtrans_transaction_id': payload.get('transaction_id') or intent.midtrans_transaction_id,
                    'x_midtrans_payment_type': payload.get('payment_type') or intent.midtrans_payment_type,
                })
            else:
                intent.sudo().write({
                    'state': 'pending',
                    'raw_response': json.dumps(payload, ensure_ascii=False, indent=2),
                })

            event.write({'state': 'processed', 'error_message': False})
            return self._json_response({'status': 'ok'})
        except Exception as error:
            _logger.exception('Failed to process Midtrans webhook %s', event_key)
            event.write({'state': 'failed', 'error_message': str(error)})
            return self._json_response({'status': 'error', 'message': str(error)}, status=500)

    def _xendit_event_key(self, payload, payload_hash):
        headers = request.httprequest.headers
        request_id = (
            headers.get('webhook-id')
            or headers.get('x-callback-id')
            or headers.get('x-request-id')
            or headers.get('X-CALLBACK-ID')
        )
        data = payload.get('data') if isinstance(payload, dict) else {}
        if not request_id and isinstance(data, dict):
            request_id = data.get('id') or data.get('payment_id') or data.get('payment_request_id')
        if not request_id and isinstance(payload, dict):
            request_id = payload.get('id') or payload.get('event')
        return request_id or payload_hash, request_id

    def _validate_xendit_token(self):
        configured_token = self._get_xendit_param('unitrade.xendit.webhook_token')
        incoming_token = request.httprequest.headers.get('x-callback-token')
        if not configured_token:
            _logger.warning('Xendit webhook token is not configured.')
            return False
        return incoming_token == configured_token

    def _normalize_payment_status(self, payload):
        data = payload.get('data') if isinstance(payload, dict) else {}
        if not isinstance(data, dict):
            data = payload
        event = str(payload.get('event') or payload.get('type') or '').upper() if isinstance(payload, dict) else ''
        status = str(data.get('status') or payload.get('status') or '').upper() if isinstance(payload, dict) else ''
        signal = '%s %s' % (event, status)
        if any(token in signal for token in ('SUCCEEDED', 'SUCCESSFUL', 'PAID', 'COMPLETED', 'CAPTURED')):
            return 'paid'
        if any(token in signal for token in ('EXPIRED',)):
            return 'expired'
        if any(token in signal for token in ('FAILED', 'CANCELLED', 'CANCELED', 'VOIDED')):
            return 'failed'
        return 'pending'

    def _find_xendit_intent_from_payload(self, payload):
        data = payload.get('data') if isinstance(payload, dict) else {}
        if not isinstance(data, dict):
            data = payload
        payment_request = data.get('payment_request') or payload.get('payment_request') or {}
        latest_payment = data.get('latest_payment') or payload.get('latest_payment') or {}
        reference_id = (
            data.get('reference_id')
            or payload.get('reference_id')
            or payment_request.get('reference_id')
        )
        payment_request_id = (
            data.get('payment_request_id')
            or data.get('payment_request')
            or payment_request.get('id')
            or payload.get('payment_request_id')
        )
        latest_payment_id = (
            data.get('payment_id')
            or data.get('id')
            or latest_payment.get('id')
            or payload.get('payment_id')
        )
        intent_env = request.env['unitrade.payment.intent'].sudo()
        if reference_id:
            intent = intent_env.search([('provider', '=', 'xendit'), ('xendit_reference_id', '=', reference_id)], limit=1)
            if intent:
                return intent
        if payment_request_id and isinstance(payment_request_id, str):
            intent = intent_env.search([('provider', '=', 'xendit'), ('xendit_payment_request_id', '=', payment_request_id)], limit=1)
            if intent:
                return intent
        if latest_payment_id:
            intent = intent_env.search([('provider', '=', 'xendit'), ('xendit_latest_payment_id', '=', latest_payment_id)], limit=1)
            if intent:
                return intent
        return intent_env.browse()

    def _payload_amount(self, payload):
        data = payload.get('data') if isinstance(payload, dict) else {}
        if not isinstance(data, dict):
            data = payload
        payment_request = data.get('payment_request') or payload.get('payment_request') or {}
        for key in ('amount', 'request_amount', 'paid_amount'):
            if data.get(key) is not None:
                return int(round(float(data.get(key))))
            if payload.get(key) is not None:
                return int(round(float(payload.get(key))))
            if payment_request.get(key) is not None:
                return int(round(float(payment_request.get(key))))
        return False

    def _update_intent_payment_details(self, intent, payload):
        data = payload.get('data') if isinstance(payload, dict) else {}
        if not isinstance(data, dict):
            data = payload
        details = intent.sale_order_id._xendit_extract_payment_details(data) if intent.sale_order_id else {}
        write_values = {}
        if details.get('payment_reference') and not intent.payment_reference:
            write_values['payment_reference'] = details['payment_reference']
        if details.get('qr_string') and not intent.qr_string:
            write_values['qr_string'] = details['qr_string']
        if details.get('payment_url') and not intent.payment_url:
            write_values['payment_url'] = details['payment_url']
        if details.get('deeplink_url') and not intent.deeplink_url:
            write_values['deeplink_url'] = details['deeplink_url']
        if details.get('latest_payment_id') and not intent.xendit_latest_payment_id:
            write_values['xendit_latest_payment_id'] = details['latest_payment_id']
        if write_values:
            intent.write(write_values)

    def _is_payout_payload(self, payload):
        event = str(payload.get('event') or payload.get('type') or '').lower() if isinstance(payload, dict) else ''
        data = payload.get('data') if isinstance(payload, dict) else {}
        if not isinstance(data, dict):
            data = {}
        return (
            'payout' in event
            or data.get('payout_id')
            or (data.get('channel_code') and str(data.get('reference_id') or '').startswith('UTP'))
        )

    def _handle_xendit_payout_webhook(self, payload):
        data = payload.get('data') if isinstance(payload, dict) else {}
        if not isinstance(data, dict):
            data = payload
        payout_id = data.get('id') or data.get('payout_id')
        reference = data.get('reference_id')
        ledger_env = request.env['unitrade.escrow.ledger'].sudo()
        ledger = ledger_env.browse()
        if payout_id:
            ledger = ledger_env.search([('xendit_payout_id', '=', payout_id)], limit=1)
        if not ledger and reference:
            ledger = ledger_env.search([('payout_reference', '=', reference)], limit=1)
        if not ledger:
            return False

        status = str(data.get('status') or '').lower()
        if status in ('succeeded', 'completed'):
            ledger.write({
                'state': 'released',
                'payout_status': 'succeeded',
                'released_at': fields.Datetime.now(),
                'payout_completed_at': fields.Datetime.now(),
                'payout_failure_reason': False,
            })
        elif status in ('failed', 'reversed', 'cancelled', 'canceled'):
            ledger.write({
                'payout_status': 'failed',
                'payout_failure_reason': data.get('failure_reason') or data.get('failure_code') or json.dumps(data, ensure_ascii=False),
            })
        elif status:
            ledger.write({'payout_status': 'processing'})
        ledger._sync_order_escrow_state()
        return ledger

    @http.route('/unitrade/payment/xendit/webhook', type='http', auth='none', csrf=False, methods=['POST'])
    def xendit_webhook(self, **kwargs):
        body = request.httprequest.get_data() or b''
        payload_hash = hashlib.sha256(body).hexdigest()
        if not self._validate_xendit_token():
            return self._json_response({'status': 'error', 'message': 'invalid token'}, status=401)

        try:
            payload = json.loads(body.decode('utf-8') or '{}')
        except ValueError:
            return self._json_response({'status': 'error', 'message': 'invalid json'}, status=400)

        request_key, request_id = self._xendit_event_key(payload, payload_hash)
        event_key = 'xendit:%s' % request_key
        event_env = request.env['unitrade.payment.event'].sudo()
        existing_event = event_env.search([('event_key', '=', event_key)], limit=1)
        if existing_event and existing_event.state == 'processed':
            return self._json_response({'status': 'ok', 'duplicate': True})

        event = existing_event or event_env.create({
            'name': event_key,
            'provider': 'xendit',
            'event_key': event_key,
            'request_id': request_id,
            'payload_hash': payload_hash,
            'payload_json': json.dumps(payload, ensure_ascii=False, indent=2),
            'state': 'received',
        })

        try:
            if self._is_payout_payload(payload):
                ledger = self._handle_xendit_payout_webhook(payload)
                event.write({
                    'state': 'processed',
                    'error_message': False if ledger else 'No matching payout ledger.',
                })
                return self._json_response({'status': 'ok'})

            intent = self._find_xendit_intent_from_payload(payload)
            if not intent:
                event.write({'state': 'failed', 'error_message': 'No matching payment intent.'})
                return self._json_response({'status': 'error', 'message': 'intent not found'}, status=404)

            event.write({
                'payment_intent_id': intent.id,
                'order_id': intent.sale_order_id.id or False,
            })
            self._update_intent_payment_details(intent, payload)
            status = self._normalize_payment_status(payload)
            payload_amount = self._payload_amount(payload)
            if payload_amount and payload_amount != int(round(intent.amount)):
                event.write({
                    'state': 'failed',
                    'error_message': 'Amount mismatch: webhook=%s intent=%s' % (payload_amount, int(round(intent.amount))),
                })
                return self._json_response({'status': 'error', 'message': 'amount mismatch'}, status=400)

            if self._sync_listing_fee_intent_status(intent, status, payload):
                event.write({'state': 'processed', 'error_message': False})
                return self._json_response({'status': 'ok'})
            if status == 'paid':
                intent.sale_order_id.sudo()._unitrade_mark_xendit_paid(intent.sudo(), payload)
            elif status in ('expired', 'failed'):
                intent.sudo().write({
                    'state': status,
                    'raw_response': json.dumps(payload, ensure_ascii=False, indent=2),
                })
                intent.sale_order_id.sudo().write({
                    'x_payment_status': 'expired' if status == 'expired' else 'failed',
                    'x_unitrade_order_state': 'payment_pending',
                })
            else:
                intent.sudo().write({
                    'state': 'pending',
                    'raw_response': json.dumps(payload, ensure_ascii=False, indent=2),
                })

            event.write({'state': 'processed', 'error_message': False})
            return self._json_response({'status': 'ok'})
        except Exception as error:
            _logger.exception('Failed to process Xendit webhook %s', event_key)
            event.write({'state': 'failed', 'error_message': str(error)})
            return self._json_response({'status': 'error', 'message': str(error)}, status=500)

    @http.route('/unitrade/payment/instructions/<string:reference>', type='http', auth='public', website=True, sitemap=False)
    def payment_instructions(self, reference, **kwargs):
        intent = self._payment_intent_by_reference(reference)
        if not intent:
            return request.not_found()
        intent = self._sync_payment_timeout(intent)
        if intent.state == 'paid':
            return request.redirect('/unitrade/payment/success/%s' % self._intent_reference_key(intent))
        return request.render('unitrade_payment.unitrade_payment_instructions', self._payment_page_values(intent))

    @http.route('/unitrade/payment/success/<string:reference>', type='http', auth='public', website=True, sitemap=False)
    def payment_success(self, reference, **kwargs):
        intent = self._payment_intent_by_reference(reference)
        if not intent:
            return request.not_found()
        if intent.state != 'paid':
            return request.redirect('/unitrade/payment/instructions/%s' % self._intent_reference_key(intent))
        return request.render('unitrade_payment.unitrade_payment_success', self._success_page_values(intent))

    @http.route('/unitrade/order/status/<int:order_id>', type='http', auth='public', website=True, sitemap=False)
    def unitrade_order_status(self, order_id, access_token=None, **kwargs):
        order = request.env['sale.order'].sudo().browse(order_id).exists()
        if not order:
            return request.not_found()
        if not self._can_view_order_status(order, access_token=access_token):
            if request.env.user._is_public():
                redirect_url = quote(request.httprequest.full_path or '/unitrade/order/status/%s' % order_id)
                return request.redirect('/web/login?redirect=%s' % redirect_url)
            seller_detail_url = self._seller_order_detail_redirect(order)
            if seller_detail_url:
                return request.redirect(seller_detail_url)
            return request.not_found()
        return request.render('unitrade_payment.unitrade_order_status', self._order_status_values(order))

    @http.route('/unitrade/order/status/<int:order_id>/data', type='json', auth='public', website=True, methods=['POST'])
    def unitrade_order_status_data(self, order_id, access_token=None, **kwargs):
        order = request.env['sale.order'].sudo().browse(order_id).exists()
        token = access_token or kwargs.get('access_token') or request.params.get('access_token')
        if not order or not self._can_view_order_status(order, access_token=token):
            return {
                'success': False,
                'message': 'Status pesanan tidak tersedia.',
            }
        ledgers = request.env['unitrade.escrow.ledger'].sudo().search([('order_id', '=', order.id)])
        refund_disputes = self._order_status_refund_records(order)
        latest_refund = refund_disputes[:1] if refund_disputes else False
        progress_steps = self._order_status_progress_steps(order, ledgers=ledgers, refund_disputes=refund_disputes)
        can_refund = False
        if (
            not latest_refund
            and not request.env.user._is_public()
            and hasattr(order, '_unitrade_refund_blocker')
            and order.partner_id.commercial_partner_id == request.env.user.partner_id.commercial_partner_id
        ):
            can_refund = not bool(order._unitrade_refund_blocker(partner=request.env.user.partner_id))
        return {
            'success': True,
            'progress_steps': progress_steps,
            'progress_count': len(progress_steps),
            'refund_detail_url': self._order_status_refund_detail_url(order, latest_refund) if latest_refund else '',
            'refund_create_url': '/unitrade/order/%s/refund/new' % order.id,
            'has_refund': bool(latest_refund),
            'can_refund': can_refund,
            'payment_status': order.x_payment_status or '',
            'escrow_state': order.x_escrow_state or '',
            'unitrade_state': order.x_unitrade_order_state or '',
            'seller_confirmed_count': len(ledgers.filtered(lambda ledger: ledger.seller_confirmed_at)),
            'buyer_confirmed_count': len(ledgers.filtered(lambda ledger: ledger.buyer_confirmed_at)),
            'ledger_count': len(ledgers),
            'updated_at': fields.Datetime.to_string(fields.Datetime.now()),
        }

    @http.route('/unitrade/order/<int:order_id>/confirm-received', type='http', auth='user', website=True, methods=['POST'], csrf=True, sitemap=False)
    def unitrade_order_confirm_received(self, order_id, **kwargs):
        order = request.env['sale.order'].sudo().browse(order_id).exists()
        if not order:
            return request.not_found()
        status_url = self._order_status_url(order)
        try:
            self._check_marketplace_access(_('mengonfirmasi penerimaan barang'))
            ledger = False
            ledger_id = int(kwargs.get('ledger_id') or 0)
            if ledger_id:
                ledger = request.env['unitrade.escrow.ledger'].sudo().browse(ledger_id).exists()
            evidence, filename = self._read_evidence_upload('buyer_evidence', 'barang diterima')
            order.action_unitrade_buyer_confirm_received(
                partner=request.env.user.partner_id,
                ledger=ledger,
                evidence=evidence,
                filename=filename,
            )
            return request.redirect(self._append_query(status_url, order_notice='buyer_confirmed'))
        except UserError as error:
            return request.redirect(self._append_query(status_url, order_error=error.args[0] if error.args else str(error)))

    @http.route('/unitrade/order/<int:order_id>/cancel', type='http', auth='user', website=True, methods=['POST'], csrf=True, sitemap=False)
    def unitrade_order_cancel(self, order_id, **kwargs):
        order = request.env['sale.order'].sudo().browse(order_id).exists()
        if not order:
            return request.not_found()
        status_url = self._order_status_url(order)
        try:
            self._check_marketplace_access(_('membatalkan pesanan'))
            order.action_unitrade_cancel_by_buyer(
                partner=request.env.user.partner_id,
                reason=(kwargs.get('reason') or '').strip(),
            )
            return request.redirect('/my/orders?status=cancel')
        except UserError as error:
            return request.redirect(self._append_query(status_url, order_error=error.args[0] if error.args else str(error)))

    @http.route('/seller/order/<int:ledger_id>/confirm-handoff', type='http', auth='user', website=True, methods=['POST'], csrf=True, sitemap=False)
    def seller_order_confirm_handoff(self, ledger_id, **kwargs):
        if 'unitrade.seller' not in request.env.registry or 'unitrade.escrow.ledger' not in request.env.registry:
            return request.not_found()
        return_url_value = kwargs.get('return_url') or ''
        return_url = return_url_value if return_url_value in (
            '/unitrade/seller/orders',
            '/seller/orders',
            '/my/seller/orders',
        ) else ''
        seller = request.env['unitrade.seller'].sudo().search([
            ('user_id', '=', request.env.user.id),
            ('status', '=', 'verified'),
        ], limit=1)
        ledger = request.env['unitrade.escrow.ledger'].sudo().browse(ledger_id).exists()
        if not seller or not ledger or ledger.seller_id.id != seller.id:
            return request.not_found()
        if not return_url and return_url_value == '/unitrade/seller/orders/%s' % ledger.order_id.id:
            return_url = return_url_value
        try:
            self._check_marketplace_access(_('mengonfirmasi serah terima seller'))
            evidence, filename = self._read_evidence_upload('seller_evidence', 'barang diserahkan')
            ledger.action_seller_confirm_handoff(
                evidence=evidence,
                filename=filename,
                location=(kwargs.get('seller_handoff_location') or '').strip(),
            )
            if return_url:
                return request.redirect(self._append_query(return_url, seller_confirmed=1))
            return request.redirect('/seller/dashboard?seller_confirmed=1#dashboard-orders')
        except UserError as error:
            if return_url:
                return request.redirect(self._append_query(return_url, seller_error=error.args[0] if error.args else str(error)))
            return request.redirect('/seller/dashboard?seller_error=%s#dashboard-orders' % quote(error.args[0] if error.args else str(error)))

    @http.route('/unitrade/payment/status/<string:reference>', type='http', auth='public', website=True, sitemap=False)
    def payment_status(self, reference, **kwargs):
        intent = self._payment_intent_by_reference(reference)
        if not intent:
            return self._json_response({'status': 'not_found'}, status=404)
        if intent.provider == 'midtrans' and intent.state == 'pending':
            intent = self._sync_midtrans_status_from_api(intent)
        intent = self._sync_payment_timeout(intent)
        return self._json_response(self._payment_status_payload(intent))

    @http.route('/unitrade/payment/qr/<string:reference>.svg', type='http', auth='public', website=True, sitemap=False)
    def payment_qr(self, reference, **kwargs):
        intent = self._payment_intent_by_reference(reference)
        if not intent or not intent.qr_string:
            return request.not_found()
        image = qrcode.make(
            intent.qr_string,
            image_factory=qrcode.image.svg.SvgPathImage,
            box_size=12,
            border=2,
        )
        stream = io.BytesIO()
        image.save(stream)
        return request.make_response(
            stream.getvalue(),
            headers=[
                ('Content-Type', 'image/svg+xml'),
                ('Cache-Control', 'no-store'),
            ],
        )

    @http.route('/unitrade/payment/finish', type='http', auth='public', website=True, sitemap=False)
    def payment_finish(self, **kwargs):
        reference = kwargs.get('reference_id') or kwargs.get('order_id') or kwargs.get('transaction_id') or kwargs.get('external_id') or kwargs.get('invoice_id')
        if reference:
            intent = self._payment_intent_by_reference(reference)
            if intent:
                return request.redirect('/unitrade/payment/instructions/%s' % self._intent_reference_key(intent))
        order_id = request.session.get('sale_last_order_id')
        if order_id:
            order = request.env['sale.order'].sudo().browse(order_id)
            if order.exists() and order.x_payment_intent_id:
                return request.redirect('/unitrade/payment/instructions/%s' % self._intent_reference_key(order.x_payment_intent_id))
        return request.redirect('/shop')
