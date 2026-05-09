import logging
import math

from odoo import fields, http
from odoo.http import request
from odoo.addons.website_sale_stock.controllers.main import WebsiteSale

_logger = logging.getLogger(__name__)


class UnitradeWebsiteSaleCart(WebsiteSale):
    _STOCK_WARNING_SESSION_KEY = 'unitrade_cart_stock_warning'
    _PRODUCT_STOCK_WARNING_SESSION_KEY = 'unitrade_product_stock_warning'

    def _unitrade_cart_stock_message(self, issues):
        if not issues:
            return ''
        if len(issues) == 1:
            return issues[0]['message']
        return 'Beberapa produk di keranjang melebihi stok tersedia. Periksa detail stok sebelum checkout.'

    def _unitrade_cart_stock_issue_map(self, issues):
        return {
            issue['product_id']: issue
            for issue in issues
            if issue.get('product_id')
        }

    def _unitrade_current_stock_issues(self):
        order = request.website.sale_get_order()
        if not order:
            return []
        try:
            return order._unitrade_get_cart_stock_issues()
        except Exception:
            _logger.exception('Failed to validate UniTrade cart stock for order %s', order.id)
            return [{
                'product_id': 0,
                'product_name': 'Keranjang',
                'requested_qty': 0,
                'available_qty': 0,
                'message': 'Stok belum dapat divalidasi. Muat ulang keranjang lalu coba lagi.',
            }]

    def _unitrade_number(self, value, default=None):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        return number if math.isfinite(number) else default

    def _unitrade_is_cart_remove_request(self, add_qty=None, set_qty=None):
        return set_qty in (0, '0') and add_qty in (None, '', 0, '0')

    def _unitrade_truthy(self, value):
        return value is True or str(value).lower() in ('1', 'true', 'yes', 'on')

    def _unitrade_product_referrer(self):
        referrer = request.httprequest.referrer or ''
        if '/shop/' not in referrer or '/shop/cart' in referrer:
            return ''
        return referrer

    def _unitrade_product_stock_warning(self, product_id, add_qty=1, set_qty=0, include_cart=True):
        try:
            product = request.env['product.product'].sudo().browse(int(product_id)).exists()
        except (TypeError, ValueError):
            return 'Jumlah produk tidak valid.'
        if not product:
            return 'Jumlah produk tidak valid.'
        if product.type != 'product' or product.allow_out_of_stock_order:
            return ''

        order = request.website.sale_get_order()
        current_qty = 0.0
        if order:
            current_qty = sum(order.order_line.filtered(
                lambda line: line.product_id.id == product.id
            ).mapped('product_uom_qty'))

        if set_qty not in (None, ''):
            requested_qty = self._unitrade_number(set_qty)
        else:
            parsed_add_qty = self._unitrade_number(add_qty)
            if parsed_add_qty is None:
                requested_qty = None
            elif include_cart:
                requested_qty = current_qty + parsed_add_qty
            else:
                requested_qty = parsed_add_qty

        if requested_qty is None:
            return 'Jumlah produk tidak valid.'
        if requested_qty <= 0:
            return ''

        available_qty = max(request.website.sudo()._get_product_available_qty(product.sudo()), 0)
        if requested_qty <= available_qty:
            return ''

        return 'Stok tidak cukup. Stok tersedia hanya %s item.' % (
            self._unitrade_format_qty(max(available_qty, 0)),
        )

    @http.route('/unitrade/product/stock/validate', type='json', auth='public', methods=['POST'], website=True, csrf=False)
    def unitrade_product_stock_validate(self, product_id=None, add_qty=1, include_cart=False, **kwargs):
        warning = self._unitrade_product_stock_warning(
            product_id,
            add_qty=add_qty,
            set_qty=0,
            include_cart=self._unitrade_truthy(include_cart),
        )
        try:
            product = request.env['product.product'].sudo().browse(int(product_id)).exists()
            stock = max(request.website.sudo()._get_product_available_qty(product.sudo()), 0) if product else 0
        except (TypeError, ValueError):
            stock = 0
        return {
            'valid': not bool(warning),
            'message': warning,
            'stock': stock,
        }

    def _unitrade_product_redirect_url(self, product_id, fallback='/shop'):
        try:
            product = request.env['product.product'].sudo().browse(int(product_id)).exists()
        except (TypeError, ValueError):
            return fallback
        if product and product.product_tmpl_id.website_url:
            return product.product_tmpl_id.website_url
        return fallback

    def _unitrade_format_qty(self, qty):
        qty = max(qty or 0, 0)
        if float(qty).is_integer():
            return str(int(qty))
        return ('%.2f' % qty).rstrip('0').rstrip('.')

    def _cart_values(self, **post):
        values = super()._cart_values(**post)
        issues = self._unitrade_current_stock_issues()
        request.session.pop(self._STOCK_WARNING_SESSION_KEY, None)
        values.update({
            'unitrade_cart_stock_issues': issues,
            'unitrade_cart_stock_issues_by_product': self._unitrade_cart_stock_issue_map(issues),
            'unitrade_cart_stock_warning': self._unitrade_cart_stock_message(issues),
        })
        return values

    def _unitrade_render_cart_lines(self, order, issues):
        return request.env['ir.ui.view']._render_template(
            'website_sale.cart_lines',
            {
                'website_sale_order': order,
                'date': fields.Date.today(),
                'suggested_products': order._cart_accessories(),
                'unitrade_cart_stock_issues': issues,
                'unitrade_cart_stock_issues_by_product': self._unitrade_cart_stock_issue_map(issues),
                'unitrade_cart_stock_warning': self._unitrade_cart_stock_message(issues),
            },
        )

    @http.route()
    def cart_update(
        self, product_id, add_qty=1, set_qty=0,
        product_custom_attribute_values=None, no_variant_attribute_values=None,
        express=False, **kwargs
    ):
        product_referrer = self._unitrade_product_referrer()
        is_remove_qty = self._unitrade_is_cart_remove_request(add_qty=add_qty, set_qty=set_qty)
        if not is_remove_qty:
            stock_warning = self._unitrade_product_stock_warning(
                product_id,
                add_qty=add_qty,
                set_qty=set_qty,
                include_cart=not bool(product_referrer),
            )
            if stock_warning:
                request.session[self._PRODUCT_STOCK_WARNING_SESSION_KEY] = stock_warning
                return request.redirect(product_referrer or self._unitrade_product_redirect_url(product_id))

        response = super().cart_update(
            product_id=product_id,
            add_qty=add_qty,
            set_qty=set_qty,
            product_custom_attribute_values=product_custom_attribute_values,
            no_variant_attribute_values=no_variant_attribute_values,
            express=express,
            **kwargs
        )
        issues = self._unitrade_current_stock_issues()
        if issues:
            request.session[self._STOCK_WARNING_SESSION_KEY] = self._unitrade_cart_stock_message(issues)
        else:
            request.session.pop(self._STOCK_WARNING_SESSION_KEY, None)
        return response

    @http.route()
    def cart_update_json(
        self, product_id, line_id=None, add_qty=None, set_qty=None, display=True,
        product_custom_attribute_values=None, no_variant_attribute_values=None, **kw
    ):
        order = request.website.sale_get_order()
        had_stock_warning = bool(order and order._unitrade_has_stock_warning())
        is_remove_qty = self._unitrade_is_cart_remove_request(add_qty=add_qty, set_qty=set_qty)
        if not is_remove_qty:
            stock_warning = self._unitrade_product_stock_warning(product_id, add_qty=add_qty, set_qty=set_qty)
            if stock_warning:
                return {
                    'cart_quantity': order.cart_quantity if order else 0,
                    'warning': stock_warning,
                    'notification_info': {'warning': stock_warning},
                    'cart_ready': False,
                }

        values = super().cart_update_json(
            product_id=product_id,
            line_id=line_id,
            add_qty=add_qty,
            set_qty=set_qty,
            display=display,
            product_custom_attribute_values=product_custom_attribute_values,
            no_variant_attribute_values=no_variant_attribute_values,
            **kw
        )
        issues = self._unitrade_current_stock_issues()
        if issues:
            warning = self._unitrade_cart_stock_message(issues)
            values['warning'] = warning
            values.setdefault('notification_info', {})['warning'] = warning
            values['cart_ready'] = False
            request.session[self._STOCK_WARNING_SESSION_KEY] = warning
        else:
            request.session.pop(self._STOCK_WARNING_SESSION_KEY, None)

        order = request.website.sale_get_order()
        if display and order and (issues or had_stock_warning) and values.get('website_sale.cart_lines'):
            values['website_sale.cart_lines'] = self._unitrade_render_cart_lines(order, issues)
        return values

    @http.route()
    def checkout(self, **post):
        issues = self._unitrade_current_stock_issues()
        if issues:
            request.session[self._STOCK_WARNING_SESSION_KEY] = self._unitrade_cart_stock_message(issues)
            return request.redirect('/shop/cart')
        request.session.pop(self._STOCK_WARNING_SESSION_KEY, None)
        return super().checkout(**post)
