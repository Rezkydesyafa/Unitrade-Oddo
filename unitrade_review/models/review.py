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
    rating = fields.Integer(string='Rating', required=True, default=5)
    comment = fields.Text(string='Komentar')
    review_image = fields.Image(
        string='Gambar Ulasan',
        max_width=1920,
        max_height=1920,
        help='Gambar opsional yang diunggah bersama ulasan produk.',
    )
    review_image_mimetype = fields.Char(string='Tipe Gambar', readonly=True)
    review_image_2 = fields.Image(
        string='Gambar Ulasan 2',
        max_width=1920,
        max_height=1920,
        help='Gambar opsional kedua yang diunggah bersama ulasan produk.',
    )
    review_image_2_mimetype = fields.Char(string='Tipe Gambar 2', readonly=True)
    review_image_3 = fields.Image(
        string='Gambar Ulasan 3',
        max_width=1920,
        max_height=1920,
        help='Gambar opsional ketiga yang diunggah bersama ulasan produk.',
    )
    review_image_3_mimetype = fields.Char(string='Tipe Gambar 3', readonly=True)
    review_tags = fields.Char(string='Tag Ulasan')
    is_visible = fields.Boolean(string='Tampilkan', default=True)

    _sql_constraints = [
        ('order_unique', 'UNIQUE(order_id, product_id)', 'Anda sudah memberikan ulasan untuk produk ini pada pesanan ini!'),
        ('rating_range', 'CHECK(rating >= 1 AND rating <= 5)', 'Rating harus antara 1-5!'),
    ]

    @api.model
    def _unitrade_refresh_product_review_stats(self, products):
        products = products.exists()
        if not products:
            return

        Review = self.sudo()
        for product in products.sudo():
            visible_reviews = Review.search([
                ('product_id', '=', product.id),
                ('is_visible', '=', True),
            ])
            review_count = len(visible_reviews)
            average_rating = (
                round(sum(visible_reviews.mapped('rating')) / review_count, 1)
                if review_count else 0.0
            )
            product.write({
                'x_average_rating': average_rating,
                'x_review_count': review_count,
            })

    def init(self):
        reviews = self.sudo().search([('product_id', '!=', False)])
        self._unitrade_refresh_product_review_stats(reviews.mapped('product_id'))

    @api.model_create_multi
    def create(self, vals_list):
        reviews = super().create(vals_list)
        self._unitrade_refresh_product_review_stats(reviews.mapped('product_id'))
        return reviews

    def write(self, vals):
        products_before = self.mapped('product_id')
        result = super().write(vals)
        if {'product_id', 'rating', 'is_visible'}.intersection(vals):
            self._unitrade_refresh_product_review_stats(products_before | self.mapped('product_id'))
        return result

    def unlink(self):
        products = self.mapped('product_id')
        result = super().unlink()
        self._unitrade_refresh_product_review_stats(products)
        return result

    @api.onchange('product_id', 'user_id')
    def _onchange_review_order_domain(self):
        domain = [('state', '=', 'done')]
        if self.user_id:
            domain.append(('partner_id', '=', self.user_id.partner_id.id))
        if self.product_id:
            domain.append(('order_line.product_id.product_tmpl_id', '=', self.product_id.id))
        if self.order_id and self.order_id not in self.env['sale.order'].search(domain):
            self.order_id = False
        return {'domain': {'order_id': domain}}

    @api.constrains('order_id')
    def _check_order_done(self):
        for record in self:
            if record.order_id.state not in ('sale', 'done'):
                raise ValidationError(_('Ulasan hanya bisa diberikan untuk pesanan yang sudah selesai.'))

    def action_save_review(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Tersimpan'),
                'message': _('Ulasan produk berhasil disimpan.'),
                'type': 'success',
                'sticky': False,
            },
        }
