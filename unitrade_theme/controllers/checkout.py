import logging
import json

from odoo import http, _
from odoo.http import request
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

class UnitradeCheckout(WebsiteSale):
    def _unitrade_format_money(self, amount, currency):
        symbol = currency.symbol or 'Rp'
        formatted = ('{:,.0f}'.format(amount or 0.0)).replace(',', '.')
        if currency.position == 'after':
            return '%s %s' % (formatted, symbol)
        return '%s %s' % (symbol, formatted)

    def _unitrade_voucher_payload(self, order, amounts, message='', success=True):
        currency = order.currency_id
        return {
            'success': success,
            'message': message,
            'voucher_code': amounts.get('voucher_code') or '',
            'voucher_name': amounts.get('voucher_name') or amounts.get('voucher_code') or '',
            'voucher_discount': amounts.get('voucher_discount') or 0.0,
            'voucher_discount_label': self._unitrade_format_money(amounts.get('voucher_discount') or 0.0, currency),
            'total': amounts.get('total') or 0.0,
            'total_label': self._unitrade_format_money(amounts.get('total') or 0.0, currency),
            'payment_fee': amounts.get('payment_fee') or 0.0,
            'payment_fee_label': self._unitrade_format_money(amounts.get('payment_fee') or 0.0, currency),
        }

    def _unitrade_checkout_address_message(self):
        return 'Tambahkan alamat terlebih dahulu sebelum melanjutkan pembayaran.'

    def _unitrade_marketplace_block_message(self, feature_label):
        user = request.env.user
        if user._is_public() or not hasattr(user, '_check_unitrade_marketplace_access'):
            return ''
        try:
            user._check_unitrade_marketplace_access(feature_label)
        except UserError as error:
            return error.args[0] if error.args else str(error)
        return ''

    def _unitrade_partner_has_checkout_address(self, partner):
        summary = self._unitrade_partner_address_summary(partner)
        return bool(summary.get('has_address'))

    def _unitrade_prepare_checkout_or_error(self, order, post=None):
        post = dict(post or {})
        payment_method = (post.get('payment_method') or 'bca_va').strip()
        try:
            if hasattr(order, '_unitrade_prepare_checkout_server_state'):
                try:
                    order.sudo()._unitrade_prepare_checkout_server_state(payment_method)
                except TypeError:
                    order.sudo()._unitrade_prepare_checkout_server_state()
        except (UserError, ValidationError) as error:
            post['checkout_error_message'] = error.args[0] if error.args else str(error)
        return post

    def _unitrade_checkout_values(self, order, post=None):
        post = dict(post or {})
        values = self.checkout_values(order, **(post or {}))
        partner = request.env.user.partner_id
        selected_payment_method = (post.get('payment_method') or 'bca_va').strip()
        try:
            amounts = order._unitrade_checkout_amounts(sync_fee=False, payment_method=selected_payment_method)
        except TypeError:
            amounts = order._unitrade_checkout_amounts(sync_fee=False)
        payment_base_amount = max(
            amounts.get('item_subtotal', 0.0)
            + amounts.get('service_fee', 0.0)
            - amounts.get('voucher_discount', 0.0),
            0.0,
        )
        payment_method_groups = (
            order._unitrade_midtrans_checkout_methods(payment_base_amount)
            if hasattr(order, '_unitrade_midtrans_checkout_methods')
            else order._unitrade_xendit_checkout_methods(payment_base_amount)
            if hasattr(order, '_unitrade_xendit_checkout_methods')
            else []
        )
        selected_payment_method_data = {}
        for group in payment_method_groups:
            for method in group.get('methods', []):
                if method.get('key') == selected_payment_method:
                    selected_payment_method_data = method
                    break
            if selected_payment_method_data:
                break
        values.update({
            'order': order,
            'website_sale_order': order,
            'unitrade_checkout_amounts': amounts,
            'unitrade_service_fee_product_id': amounts['service_fee_product_id'],
            'unitrade_payment_fee_product_id': amounts.get('payment_fee_product_id'),
            'unitrade_voucher_discount_product_id': amounts.get('voucher_discount_product_id'),
            'unitrade_shipping_fee_product_id': amounts.get('shipping_fee_product_id'),
            'unitrade_shipping_methods': order._unitrade_shipping_method_options() if hasattr(order, '_unitrade_shipping_method_options') else [],
            'unitrade_selected_shipping_method': order.x_shipping_method if 'x_shipping_method' in order._fields else 'pickup',
            'unitrade_shipping_cost': amounts.get('shipping_cost', 0.0),
            'unitrade_shipping_gps_warning': order.x_shipping_gps_warning if 'x_shipping_gps_warning' in order._fields else '',
            'unitrade_selected_payment_method': selected_payment_method,
            'unitrade_selected_payment_method_data': selected_payment_method_data,
            'unitrade_payment_method_groups': payment_method_groups,
            'address_payload_json': json.dumps(self._unitrade_partner_address_payload(partner)),
            'address_summary': self._unitrade_partner_address_summary(partner),
            'checkout_address_missing': not self._unitrade_partner_has_checkout_address(partner),
            'checkout_address_missing_message': self._unitrade_checkout_address_message(),
            'checkout_error_message': (post or {}).get('checkout_error_message'),
        })
        return values

    def _unitrade_shipping_payload(self, order, amounts, message='', success=True):
        currency = order.currency_id
        return {
            'success': success,
            'message': message,
            'shipping_method': amounts.get('shipping_method') or 'pickup',
            'shipping_cost': amounts.get('shipping_cost') or 0.0,
            'shipping_cost_label': self._unitrade_format_money(amounts.get('shipping_cost') or 0.0, currency),
            'payment_fee': amounts.get('payment_fee') or 0.0,
            'payment_fee_label': self._unitrade_format_money(amounts.get('payment_fee') or 0.0, currency),
            'total': amounts.get('total') or 0.0,
            'total_label': self._unitrade_format_money(amounts.get('total') or 0.0, currency),
            'gps_warning': order.x_shipping_gps_warning if 'x_shipping_gps_warning' in order._fields else '',
        }

    @http.route('/unitrade/checkout/shipping/select', type='json', auth='public', website=True, methods=['POST'])
    def unitrade_checkout_shipping_select(self, shipping_method=None, payment_method=None, **kwargs):
        order = request.website.sale_get_order()
        if not order or order.state != 'draft':
            return {'success': False, 'message': _('Keranjang tidak tersedia.')}
        if not request.env.user._is_public() and order.partner_id.commercial_partner_id != request.env.user.partner_id.commercial_partner_id:
            return {'success': False, 'message': _('Anda tidak memiliki akses ke keranjang ini.')}
        block_message = self._unitrade_marketplace_block_message(_('memilih metode pengiriman'))
        if block_message:
            return {'success': False, 'message': block_message}
        if not hasattr(order, '_unitrade_set_shipping_method'):
            return {'success': False, 'message': _('Modul pengiriman belum tersedia.')}
        try:
            order.sudo()._unitrade_set_shipping_method(shipping_method)
            try:
                amounts = order.sudo()._unitrade_checkout_amounts(sync_fee=False, payment_method=(payment_method or 'bca_va'))
            except TypeError:
                amounts = order.sudo()._unitrade_checkout_amounts(sync_fee=False)
            return self._unitrade_shipping_payload(order, amounts, _('Metode pengiriman diperbarui.'))
        except (UserError, ValidationError) as error:
            return {'success': False, 'message': error.args[0] if error.args else str(error)}
        except Exception:
            _logger.exception('Failed selecting shipping method for order %s', order.name)
            return {'success': False, 'message': _('Metode pengiriman belum bisa diperbarui. Coba lagi.')}

    @http.route('/unitrade/checkout/voucher/apply', type='json', auth='public', website=True, methods=['POST'])
    def unitrade_checkout_voucher_apply(self, code=None, payment_method=None, **kwargs):
        order = request.website.sale_get_order()
        if not order or order.state != 'draft':
            return {'success': False, 'message': _('Keranjang tidak tersedia.')}
        if not request.env.user._is_public() and order.partner_id.commercial_partner_id != request.env.user.partner_id.commercial_partner_id:
            return {'success': False, 'message': _('Anda tidak memiliki akses ke keranjang ini.')}
        block_message = self._unitrade_marketplace_block_message(_('menggunakan voucher checkout'))
        if block_message:
            return {'success': False, 'message': block_message}
        try:
            order.sudo()._unitrade_apply_voucher_code(code)
            try:
                amounts = order.sudo()._unitrade_checkout_amounts(sync_fee=False, payment_method=(payment_method or 'bca_va'))
            except TypeError:
                amounts = order.sudo()._unitrade_checkout_amounts(sync_fee=False)
            return self._unitrade_voucher_payload(order, amounts, _('Voucher berhasil diterapkan.'))
        except (UserError, ValidationError) as error:
            return {'success': False, 'message': error.args[0] if error.args else str(error)}
        except Exception:
            _logger.exception('Failed applying voucher to order %s', order.name)
            return {'success': False, 'message': _('Voucher belum bisa diterapkan. Coba lagi.')}

    @http.route('/unitrade/checkout/voucher/remove', type='json', auth='public', website=True, methods=['POST'])
    def unitrade_checkout_voucher_remove(self, payment_method=None, **kwargs):
        order = request.website.sale_get_order()
        if not order or order.state != 'draft':
            return {'success': False, 'message': _('Keranjang tidak tersedia.')}
        if not request.env.user._is_public() and order.partner_id.commercial_partner_id != request.env.user.partner_id.commercial_partner_id:
            return {'success': False, 'message': _('Anda tidak memiliki akses ke keranjang ini.')}
        block_message = self._unitrade_marketplace_block_message(_('menggunakan voucher checkout'))
        if block_message:
            return {'success': False, 'message': block_message}
        try:
            order.sudo()._unitrade_remove_voucher()
            try:
                amounts = order.sudo()._unitrade_checkout_amounts(sync_fee=False, payment_method=(payment_method or 'bca_va'))
            except TypeError:
                amounts = order.sudo()._unitrade_checkout_amounts(sync_fee=False)
            return self._unitrade_voucher_payload(order, amounts, _('Voucher dihapus.'))
        except Exception:
            _logger.exception('Failed removing voucher from order %s', order.name)
            return {'success': False, 'message': _('Voucher belum bisa dihapus. Coba lagi.')}

    def _unitrade_partner_address_payload(self, partner):
        return {
            'label': partner.x_unitrade_address_label or 'home',
            'province': partner.x_unitrade_province or partner.state_id.name or '',
            'city': partner.x_unitrade_city or partner.city or '',
            'district': partner.x_unitrade_district or '',
            'village': partner.x_unitrade_village or '',
            'zip': partner.zip or '',
            'street': partner.street or '',
            'street2': partner.street2 or '',
            'latitude': partner.x_unitrade_latitude or 0,
            'longitude': partner.x_unitrade_longitude or 0,
            'place_id': partner.x_unitrade_mapbox_place_id or '',
        }

    def _unitrade_partner_address_summary(self, partner):
        address = self._unitrade_partner_address_payload(partner)
        has_address = bool(address['street'] and address['city'] and address['zip'])
        line_parts = [
            address['street'],
            address['street2'],
            address['village'],
            address['district'],
            address['city'],
            address['province'],
            address['zip'],
        ]
        return {
            'has_address': has_address,
            'label': self._unitrade_address_label_text(address['label']),
            'line': ', '.join([part for part in line_parts if part]),
            'coordinates': '%.6f, %.6f' % (address['latitude'], address['longitude'])
            if has_address and address['latitude'] and address['longitude'] else '',
        }

    def _unitrade_address_label_text(self, label):
        return {
            'home': 'Rumah',
            'office': 'Kantor',
            'school': 'Sekolah',
            'other': 'Lainnya',
        }.get(label or 'home', 'Rumah')

    @http.route(['/shop/checkout', '/shop/address'], type='http', auth="public", website=True, sitemap=False)
    def checkout(self, **post):
        order = request.website.sale_get_order()
        if not order:
            return request.redirect('/shop')

        request.session['sale_last_order_id'] = order.id
        redirection = self.checkout_redirection(order)
        if redirection:
            return redirection

        if post.get('xhr'):
            return 'ok'

        block_message = self._unitrade_marketplace_block_message(_('melanjutkan checkout'))
        if block_message:
            post = {
                **post,
                'checkout_error_message': block_message,
            }

        post = self._unitrade_prepare_checkout_or_error(order, post)
        values = self._unitrade_checkout_values(order, post)
        return request.render("unitrade_theme.unitrade_checkout_page", values)

    @http.route(['/shop/payment'], type='http', auth="public", website=True, sitemap=False)
    def payment(self, **post):
        order = request.website.sale_get_order()
        if not order:
            return request.redirect('/shop')

        block_message = self._unitrade_marketplace_block_message(_('melanjutkan checkout'))
        if block_message:
            post = {
                **post,
                'checkout_error_message': block_message,
            }

        post = self._unitrade_prepare_checkout_or_error(order, post)
        values = self._unitrade_checkout_values(order, post)
        return request.render("unitrade_theme.unitrade_checkout_page", values)

    @http.route('/unitrade/checkout/pay', type='http', auth="public", website=True, sitemap=False, methods=['POST'])
    def unitrade_checkout_pay(self, **post):
        order = request.website.sale_get_order()
        if not order or order.state != 'draft':
            return request.redirect('/shop')

        block_message = self._unitrade_marketplace_block_message(_('membuat pembayaran checkout'))
        if block_message:
            values = self._unitrade_checkout_values(order, {
                **post,
                'checkout_error_message': block_message,
            })
            return request.render("unitrade_theme.unitrade_checkout_page", values)
        
        # Ensure shipping address exists to pass Odoo's validation
        if not order.partner_shipping_id:
            order.partner_shipping_id = order.partner_id.id

        selected_payment_method = (post.get('payment_method') or '').strip()
        partner = request.env.user.partner_id
        if not self._unitrade_partner_has_checkout_address(partner):
            values = self._unitrade_checkout_values(order, {
                **post,
                'checkout_error_message': self._unitrade_checkout_address_message(),
            })
            return request.render("unitrade_theme.unitrade_checkout_page", values)

        if hasattr(order, '_unitrade_shipping_blocker'):
            shipping_blocker = order.sudo()._unitrade_shipping_blocker()
            if shipping_blocker:
                values = self._unitrade_checkout_values(order, {
                    **post,
                    'checkout_error_message': shipping_blocker,
                })
                return request.render("unitrade_theme.unitrade_checkout_page", values)

        try:
            payment_result = order.sudo().action_create_midtrans_payment(selected_payment_method)
        except (UserError, ValidationError) as error:
            values = self._unitrade_checkout_values(order, {
                **post,
                'checkout_error_message': error.args[0] if error.args else str(error),
            })
            return request.render("unitrade_theme.unitrade_checkout_page", values)
        except Exception:
            _logger.exception('Failed to create Midtrans checkout for order %s', order.name)
            values = self._unitrade_checkout_values(order, {
                **post,
                'checkout_error_message': 'Checkout Midtrans belum bisa dibuat. Coba lagi beberapa saat lagi.',
            })
            return request.render("unitrade_theme.unitrade_checkout_page", values)

        payment_url = payment_result.get('payment_url') if payment_result else False
        if not payment_url:
            values = self._unitrade_checkout_values(order, {
                **post,
                'checkout_error_message': 'Midtrans tidak mengembalikan data pembayaran.',
            })
            return request.render("unitrade_theme.unitrade_checkout_page", values)

        request.session['sale_last_order_id'] = order.id
        payment_intent = payment_result.get('payment_intent') if payment_result else False
        if payment_intent and (payment_intent.midtrans_order_id or payment_intent.xendit_reference_id):
            return request.redirect('/unitrade/payment/instructions/%s' % (payment_intent.midtrans_order_id or payment_intent.xendit_reference_id))
        return request.redirect(payment_url)
