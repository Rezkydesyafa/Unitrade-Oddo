import logging
import json

from odoo import http
from odoo.http import request
from odoo.addons.website_sale.controllers.main import WebsiteSale

_logger = logging.getLogger(__name__)

class UnitradeCheckout(WebsiteSale):
    def _unitrade_checkout_values(self, order, post=None):
        values = self.checkout_values(order, **(post or {}))
        partner = request.env.user.partner_id
        amounts = order._unitrade_checkout_amounts(sync_fee=False)
        values.update({
            'order': order,
            'website_sale_order': order,
            'unitrade_checkout_amounts': amounts,
            'unitrade_service_fee_product_id': amounts['service_fee_product_id'],
            'address_payload_json': json.dumps(self._unitrade_partner_address_payload(partner)),
            'address_summary': self._unitrade_partner_address_summary(partner),
        })
        return values

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

        values = self._unitrade_checkout_values(order, post)
        return request.render("unitrade_theme.unitrade_checkout_page", values)

    @http.route(['/shop/payment'], type='http', auth="public", website=True, sitemap=False)
    def payment(self, **post):
        order = request.website.sale_get_order()
        if not order:
            return request.redirect('/shop')

        values = self._unitrade_checkout_values(order, post)
        return request.render("unitrade_theme.unitrade_checkout_page", values)

    @http.route('/unitrade/checkout/pay', type='http', auth="public", website=True, sitemap=False, methods=['POST'])
    def unitrade_checkout_pay(self, **post):
        order = request.website.sale_get_order()
        if not order or order.state != 'draft':
            return request.redirect('/shop')
        
        # Ensure shipping address exists to pass Odoo's validation
        if not order.partner_shipping_id:
            order.partner_shipping_id = order.partner_id.id

        order._unitrade_checkout_amounts(sync_fee=True)
        selected_payment_method = (post.get('payment_method') or '').strip()
        if selected_payment_method and 'x_payment_method' in order._fields:
            order.sudo().write({'x_payment_method': selected_payment_method})
            
        # Standard Odoo confirm order
        order.action_confirm()
        
        # Ideally this redirects to Midtrans. Since we don't have Midtrans snap here,
        # redirect to the payment finish page.
        return request.redirect('/unitrade/payment/finish')
