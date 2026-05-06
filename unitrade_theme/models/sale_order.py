import logging

from odoo import _, models
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _unitrade_is_stock_warning_message(self, message):
        message = message or ''
        return any(marker in message for marker in (
            'Stok tidak cukup',
            'You ask for',
            'Some products became unavailable',
            'The item has not been added',
        ))

    def _unitrade_has_stock_warning(self):
        self.ensure_one()
        if self._unitrade_is_stock_warning_message(self.shop_warning):
            return True
        return any(
            self._unitrade_is_stock_warning_message(line.shop_warning)
            for line in self.order_line
        )

    def _unitrade_format_stock_qty(self, quantity):
        self.ensure_one()
        quantity = quantity or 0
        if float(quantity).is_integer():
            return str(int(quantity))
        return ('%.2f' % quantity).rstrip('0').rstrip('.')

    def _unitrade_stock_message(self, product, requested_qty, available_qty):
        self.ensure_one()
        return _(
            'Stok tidak cukup untuk %(product_name)s. Diminta %(requested_qty)s, tersedia %(available_qty)s.',
            product_name=product.display_name,
            requested_qty=self._unitrade_format_stock_qty(requested_qty),
            available_qty=self._unitrade_format_stock_qty(max(available_qty, 0)),
        )

    def _unitrade_get_cart_stock_issues(self):
        """Return stock issues for the current cart using the website warehouse."""
        self.ensure_one()
        issues = []
        issue_by_product_id = {}
        checked_product_ids = set()
        stock_lines = self.order_line.filtered(
            lambda line: (
                not line.display_type
                and line.product_id
                and line.product_id.type == 'product'
                and not line.product_id.allow_out_of_stock_order
            )
        )
        line_by_product_id = {}
        qty_by_product_id = {}
        for line in stock_lines:
            product_id = line.product_id.id
            line_by_product_id.setdefault(product_id, line)
            qty_by_product_id[product_id] = qty_by_product_id.get(product_id, 0.0) + line.product_uom_qty

        for line in stock_lines:
            product = line.product_id
            if product.id in checked_product_ids:
                continue
            checked_product_ids.add(product.id)

            try:
                cart_qty = qty_by_product_id.get(product.id, 0.0)
                available_qty = product.sudo().with_context(warehouse=self.warehouse_id.id).free_qty
            except Exception:
                _logger.exception('Failed to read realtime stock for product %s in cart %s', product.id, self.id)
                available_qty = 0.0
                cart_qty = qty_by_product_id.get(product.id, 0.0)

            precision = line.product_uom.rounding or product.uom_id.rounding
            if float_compare(cart_qty, available_qty, precision_rounding=precision) > 0:
                issue = {
                    'product_id': product.id,
                    'product_name': product.display_name,
                    'requested_qty': cart_qty,
                    'available_qty': max(available_qty, 0),
                    'message': self._unitrade_stock_message(product, cart_qty, available_qty),
                }
                issues.append(issue)
                issue_by_product_id[product.id] = issue

        for product_id, line in line_by_product_id.items():
            issue = issue_by_product_id.get(product_id)
            if issue:
                if line.shop_warning != issue['message']:
                    line.shop_warning = issue['message']
            elif self._unitrade_is_stock_warning_message(line.shop_warning):
                line.shop_warning = False

        if self._unitrade_is_stock_warning_message(self.shop_warning):
            self.shop_warning = False

        return issues

    def _verify_updated_quantity(self, order_line, product_id, new_qty, **kwargs):
        verified_qty, warning = super()._verify_updated_quantity(order_line, product_id, new_qty, **kwargs)
        self.ensure_one()

        product = self.env['product.product'].browse(product_id).exists()
        if not product or product.type != 'product' or product.allow_out_of_stock_order:
            return verified_qty, warning

        product_qty_in_cart, available_qty = self._get_cart_and_free_qty(product, line=order_line)
        old_qty = order_line.product_uom_qty if order_line else 0
        added_qty = verified_qty - old_qty
        total_cart_qty = product_qty_in_cart + added_qty
        precision = product.uom_id.rounding

        if float_compare(total_cart_qty, available_qty, precision_rounding=precision) <= 0:
            if order_line and self._unitrade_is_stock_warning_message(order_line.shop_warning):
                order_line.shop_warning = False
            if self._unitrade_is_stock_warning_message(self.shop_warning):
                self.shop_warning = False
            return verified_qty, warning

        allowed_line_qty = max(available_qty - (product_qty_in_cart - old_qty), 0)
        message = self._unitrade_stock_message(product, total_cart_qty, available_qty)
        if order_line:
            order_line.shop_warning = message
        else:
            self.shop_warning = message
        return allowed_line_qty, message

    def _is_cart_ready(self):
        for order in self:
            if not super(SaleOrder, order)._is_cart_ready():
                return False
            if order._unitrade_get_cart_stock_issues():
                return False
        return True

    def _check_cart_is_ready_to_be_paid(self):
        for order in self:
            issues = order._unitrade_get_cart_stock_issues()
            if issues:
                raise ValidationError(' '.join(issue['message'] for issue in issues))
        return super()._check_cart_is_ready_to_be_paid()


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _set_shop_warning_stock(self, desired_qty, new_qty):
        self.ensure_one()
        message = self.order_id._unitrade_stock_message(self.product_id, desired_qty, new_qty)
        self.shop_warning = message
        return message
