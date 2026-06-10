import logging

from odoo import _, models
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare

_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _unitrade_service_fee_product(self):
        product = self.env.ref('unitrade_theme.product_unitrade_service_fee', raise_if_not_found=False)
        if product:
            return product.sudo()

        product = self.env['product.product'].sudo().create({
            'name': 'Biaya Layanan UniTrade',
            'detailed_type': 'service',
            'sale_ok': True,
            'purchase_ok': False,
            'list_price': 0.0,
            'taxes_id': [(6, 0, [])],
        })
        self.env['ir.model.data'].sudo().create({
            'module': 'unitrade_theme',
            'name': 'product_unitrade_service_fee',
            'model': 'product.product',
            'res_id': product.id,
            'noupdate': True,
        })
        return product

    def _unitrade_service_fee_amount(self, subtotal):
        self.ensure_one()
        subtotal = subtotal or 0.0
        if subtotal <= 0:
            return 0.0
        if subtotal < 50000:
            fee = 1000
        elif subtotal <= 150000:
            fee = 1500
        elif subtotal <= 500000:
            fee = 2000
        elif subtotal <= 1000000:
            fee = 3000
        else:
            fee = 4000
        return self.currency_id.round(fee)

    def _unitrade_checkout_amounts(self, sync_fee=False):
        self.ensure_one()
        fee_product = self._unitrade_service_fee_product()
        payment_fee_product = self.env.ref('unitrade_payment.product_unitrade_payment_fee', raise_if_not_found=False)
        fee_lines = self.order_line.filtered(lambda line: line.product_id == fee_product)
        payment_fee_lines = self.order_line.filtered(lambda line: payment_fee_product and line.product_id == payment_fee_product)
        product_lines = self.order_line.filtered(
            lambda line: (
                not line.display_type
                and line.product_id
                and line.product_id != fee_product
                and (not payment_fee_product or line.product_id != payment_fee_product)
            )
        )
        if sync_fee and self.state == 'draft':
            stale_fee_lines = fee_lines | payment_fee_lines
            if stale_fee_lines:
                stale_fee_lines.sudo().unlink()
                self.invalidate_recordset(['order_line', 'amount_untaxed', 'amount_tax', 'amount_total'])
                fee_lines = self.order_line.filtered(lambda line: line.product_id == fee_product)
                product_lines = self.order_line.filtered(
                    lambda line: (
                        not line.display_type
                        and line.product_id
                        and line.product_id != fee_product
                        and (not payment_fee_product or line.product_id != payment_fee_product)
                    )
                )

            taxed_lines = product_lines.filtered(lambda line: line.tax_id)
            if taxed_lines:
                taxed_lines.sudo().write({'tax_id': [(6, 0, [])]})
                self.invalidate_recordset(['order_line', 'amount_untaxed', 'amount_tax', 'amount_total'])
                product_lines = self.order_line.filtered(
                    lambda line: (
                        not line.display_type
                        and line.product_id
                        and line.product_id != fee_product
                        and (not payment_fee_product or line.product_id != payment_fee_product)
                    )
                )

        subtotal = sum(product_lines.mapped('price_subtotal'))
        service_fee = self._unitrade_service_fee_amount(subtotal)

        return {
            'service_fee_product_id': fee_product.id,
            'item_subtotal': subtotal,
            'service_fee': service_fee,
            'tax': 0.0,
            'total': subtotal + service_fee,
            'item_quantity': sum(product_lines.mapped('product_uom_qty')),
        }

    def _unitrade_cart_amounts(self, sync_fee=False):
        """Amounts for the cart page before shipping is chosen at checkout."""
        self.ensure_one()
        amounts = dict(self._unitrade_checkout_amounts(sync_fee=sync_fee))
        shipping_cost = self.currency_id.round(amounts.get('shipping_cost') or 0.0)
        if shipping_cost:
            amounts['shipping_cost'] = 0.0
            amounts['total'] = self.currency_id.round(
                max((amounts.get('total') or 0.0) - shipping_cost, 0.0)
            )
        return amounts

    def _unitrade_product_lines_for_checkout(self):
        self.ensure_one()
        fee_product = self._unitrade_service_fee_product()
        payment_fee_product = self.env.ref('unitrade_payment.product_unitrade_payment_fee', raise_if_not_found=False)
        return self.order_line.filtered(
            lambda line: (
                not line.display_type
                and line.product_id
                and line.product_id != fee_product
                and (not payment_fee_product or line.product_id != payment_fee_product)
            )
        )

    def _unitrade_sync_checkout_product_prices(self):
        self.ensure_one()
        if self.state != 'draft':
            return

        currency = self.currency_id
        product_lines = self._unitrade_product_lines_for_checkout()
        empty_lines = product_lines.filtered(lambda line: line.product_uom_qty <= 0)
        if empty_lines:
            empty_lines.sudo().unlink()
            self.invalidate_recordset(['order_line', 'amount_untaxed', 'amount_tax', 'amount_total'])
            product_lines = self._unitrade_product_lines_for_checkout()

        for line in product_lines:
            product = line.product_id.sudo()
            if hasattr(product, '_unitrade_discounted_price'):
                price_unit = currency.round(product._unitrade_discounted_price())
            else:
                price_unit = currency.round(product.lst_price or 0.0)
            values = {}
            if float_compare(line.price_unit, price_unit, precision_rounding=currency.rounding) != 0:
                values['price_unit'] = price_unit
            if line.discount:
                values['discount'] = 0.0
            if line.tax_id:
                values['tax_id'] = [(6, 0, [])]
            if values:
                line.sudo().write(values)

        self.invalidate_recordset(['order_line', 'amount_untaxed', 'amount_tax', 'amount_total'])

    def _unitrade_prepare_checkout_server_state(self):
        """Recalculate cart server-side before checkout/payment intent creation."""
        self.ensure_one()
        if self.state != 'draft':
            return self._unitrade_checkout_amounts(sync_fee=False)

        self._unitrade_sync_checkout_product_prices()
        product_lines = self._unitrade_product_lines_for_checkout()
        if not product_lines:
            raise ValidationError(_('Keranjang masih kosong.'))

        unavailable_lines = product_lines.filtered(lambda line: not line.product_id.sudo().sale_ok)
        if unavailable_lines:
            product_names = ', '.join(unavailable_lines.mapped('product_id.display_name'))
            raise ValidationError(_('Produk berikut sudah tidak tersedia untuk dibeli: %s') % product_names)

        stock_issues = self._unitrade_get_cart_stock_issues()
        if stock_issues:
            raise ValidationError(' '.join(issue['message'] for issue in stock_issues))

        amounts = self._unitrade_checkout_amounts(sync_fee=True)
        if float_compare(amounts.get('item_subtotal', 0.0), 0.0, precision_rounding=self.currency_id.rounding) <= 0:
            raise ValidationError(_('Total produk di keranjang tidak valid.'))
        return amounts

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

    def _unitrade_is_stock_limited_product(self, product):
        self.ensure_one()
        if hasattr(product, '_unitrade_is_stock_limited'):
            return product.sudo()._unitrade_is_stock_limited()
        return product.type == 'product' and not product.allow_out_of_stock_order

    def _unitrade_available_qty(self, product):
        self.ensure_one()
        if hasattr(product, '_unitrade_available_qty'):
            return product.sudo()._unitrade_available_qty(warehouse=self.warehouse_id)
        return product.sudo().with_context(warehouse=self.warehouse_id.id).free_qty

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
                and self._unitrade_is_stock_limited_product(line.product_id)
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

            template = product.product_tmpl_id.sudo()
            if hasattr(template, '_unitrade_is_publicly_available') and not template._unitrade_is_publicly_available():
                issue = {
                    'product_id': product.id,
                    'product_name': product.display_name,
                    'requested_qty': qty_by_product_id.get(product.id, 0.0),
                    'available_qty': 0,
                    'message': 'Produk %s belum aktif atau sudah tidak tersedia.' % product.display_name,
                }
                issues.append(issue)
                issue_by_product_id[product.id] = issue
                continue

            try:
                cart_qty = qty_by_product_id.get(product.id, 0.0)
                available_qty = self._unitrade_available_qty(product)
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
        if not product or not self._unitrade_is_stock_limited_product(product):
            return verified_qty, warning

        other_cart_qty = sum(self.order_line.filtered(
            lambda line: line.product_id.id == product.id and line != order_line
        ).mapped('product_uom_qty'))
        available_qty = self._unitrade_available_qty(product)
        total_cart_qty = other_cart_qty + verified_qty
        precision = product.uom_id.rounding

        if float_compare(total_cart_qty, available_qty, precision_rounding=precision) <= 0:
            if order_line and self._unitrade_is_stock_warning_message(order_line.shop_warning):
                order_line.shop_warning = False
            if self._unitrade_is_stock_warning_message(self.shop_warning):
                self.shop_warning = False
            return verified_qty, warning

        allowed_line_qty = max(available_qty - other_cart_qty, 0)
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
