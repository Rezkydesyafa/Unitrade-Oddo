from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class UnitradeReview(models.Model):
    _name = 'unitrade.review'
    _description = 'UniTrade Product Review'
    _order = 'create_date desc'
    _rec_name = 'product_id'

    product_id = fields.Many2one('product.template', string='Produk', required=True, ondelete='cascade', index=True)
    user_id = fields.Many2one('res.users', string='Reviewer', required=True, default=lambda self: self.env.uid, index=True)
    order_id = fields.Many2one('sale.order', string='Pesanan', required=True)
    rating = fields.Integer(string='Rating', required=True)
    comment = fields.Text(string='Komentar')
    is_visible = fields.Boolean(string='Tampilkan', default=True)

    _sql_constraints = [
        ('order_unique', 'UNIQUE(order_id, product_id)', 'Anda sudah memberikan ulasan untuk produk ini pada pesanan ini!'),
        ('rating_range', 'CHECK(rating >= 1 AND rating <= 5)', 'Rating harus antara 1-5!'),
    ]

    @api.constrains('order_id')
    def _check_order_done(self):
        for record in self:
            if record.order_id.state != 'sale':
                raise ValidationError(_('Ulasan hanya bisa diberikan untuk pesanan yang sudah selesai.'))
