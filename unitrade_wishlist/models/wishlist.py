from odoo import models, fields
import logging

_logger = logging.getLogger(__name__)


class UnitradeWishlist(models.Model):
    _name = 'unitrade.wishlist'
    _description = 'UniTrade Wishlist'
    _order = 'create_date desc'

    user_id = fields.Many2one('res.users', string='User', required=True, ondelete='cascade', index=True)
    product_id = fields.Many2one('product.template', string='Produk', required=True, ondelete='cascade', index=True)

    _sql_constraints = [
        ('user_product_unique', 'UNIQUE(user_id, product_id)', 'Produk sudah ada di wishlist!'),
    ]
