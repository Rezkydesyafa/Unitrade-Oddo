from odoo import models


class SaleOrderLineUniTrade(models.Model):
    _inherit = 'sale.order.line'

    # XML ids of internal "synthetic" products that must never be shown as
    # cart product rows (they are summarised separately in the order summary).
    _UNITRADE_HIDDEN_CART_PRODUCT_XMLIDS = (
        'unitrade_delivery.product_unitrade_shipping_fee',
        'unitrade_payment.product_unitrade_voucher_discount',
        'unitrade_payment.product_unitrade_payment_fee',
        'unitrade_theme.product_unitrade_service_fee',
    )

    def _show_in_cart(self):
        self.ensure_one()
        for xmlid in self._UNITRADE_HIDDEN_CART_PRODUCT_XMLIDS:
            hidden_product = self.env.ref(xmlid, raise_if_not_found=False)
            if hidden_product and self.product_id == hidden_product:
                return False
        return super()._show_in_cart()
