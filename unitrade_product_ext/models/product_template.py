from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class ProductTemplateUniTrade(models.Model):
    _inherit = 'product.template'

    x_condition = fields.Selection([
        ('new', 'Baru'),
        ('used', 'Bekas'),
    ], string='Kondisi', default='used')

    x_seller_id = fields.Many2one(
        'unitrade.seller',
        string='Penjual',
        index=True,
    )
    x_seller_user_id = fields.Many2one(
        'res.users',
        string='User Penjual',
        related='x_seller_id.user_id',
        store=True,
    )
    x_seller_location = fields.Char(
        string='Lokasi Penjual',
        help='Kota/kabupaten penjual',
    )
    x_seller_latitude = fields.Float(
        string='Latitude', digits=(10, 7),
    )
    x_seller_longitude = fields.Float(
        string='Longitude', digits=(10, 7),
    )
    x_is_marketplace = fields.Boolean(
        string='Produk Marketplace',
        default=False,
        help='Tandai jika produk ini dijual di marketplace UniTrade',
    )

    # === Extended fields for product detail page ===
    x_specification = fields.Html(
        string='Spesifikasi',
        help='Spesifikasi teknis produk',
    )
    x_weight_product = fields.Float(
        string='Berat Produk (gram)',
        help='Berat produk dalam gram',
    )
    x_brand = fields.Char(
        string='Merek',
    )
    x_free_shipping = fields.Boolean(
        string='Gratis Ongkir',
        default=False,
    )

    # === Computed review fields (safe — works even if unitrade_review not installed) ===
    x_review_count = fields.Integer(
        string='Jumlah Review',
        compute='_compute_review_stats',
        store=False,
    )
    x_average_rating = fields.Float(
        string='Rating Rata-rata',
        compute='_compute_review_stats',
        store=False,
    )

    def _compute_review_stats(self):
        """Compute review statistics. Safe if unitrade.review model doesn't exist yet."""
        for product in self:
            try:
                if 'unitrade.review' in self.env:
                    reviews = self.env['unitrade.review'].sudo().search([
                        ('product_id', '=', product.id),
                        ('is_visible', '=', True),
                    ])
                    product.x_review_count = len(reviews)
                    if reviews:
                        product.x_average_rating = round(
                            sum(reviews.mapped('rating')) / len(reviews), 1
                        )
                    else:
                        product.x_average_rating = 0.0
                else:
                    product.x_review_count = 0
                    product.x_average_rating = 0.0
            except Exception:
                product.x_review_count = 0
                product.x_average_rating = 0.0

    @api.model
    def _search_marketplace_products(self, keyword=None, category_id=None,
                                      condition=None, min_price=None,
                                      max_price=None, location=None,
                                      sort_by='create_date desc', limit=20, offset=0):
        """Search marketplace products with filters"""
        domain = [('x_is_marketplace', '=', True), ('sale_ok', '=', True)]

        if keyword:
            domain += ['|',
                ('name', 'ilike', keyword),
                ('description_sale', 'ilike', keyword),
            ]
        if category_id:
            domain.append(('categ_id', '=', int(category_id)))
        if condition:
            domain.append(('x_condition', '=', condition))
        if min_price:
            domain.append(('list_price', '>=', float(min_price)))
        if max_price:
            domain.append(('list_price', '<=', float(max_price)))
        if location:
            domain.append(('x_seller_location', 'ilike', location))

        return self.search(domain, order=sort_by, limit=limit, offset=offset)
