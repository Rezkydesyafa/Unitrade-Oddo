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
    x_seller_name = fields.Char(
        string='Nama Penjual',
        related='x_seller_id.name',
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
    x_item_district = fields.Selection([
        ('yogyakarta', 'Kota Yogyakarta'),
        ('sleman', 'Sleman'),
        ('bantul', 'Bantul'),
        ('kulon_progo', 'Kulon Progo'),
        ('gunungkidul', 'Gunungkidul'),
    ], string='Kabupaten/Kota Barang', index=True)
    x_item_province = fields.Selection([
        ('diy', 'DI Yogyakarta'),
        ('other', 'Lainnya'),
    ], string='Provinsi Barang', default='diy', index=True)
    x_item_latitude = fields.Float(
        string='Latitude Barang', digits=(10, 7),
    )
    x_item_longitude = fields.Float(
        string='Longitude Barang', digits=(10, 7),
    )
    x_is_marketplace = fields.Boolean(
        string='Produk Marketplace',
        default=False,
        help='Tandai jika produk ini dijual di marketplace UniTrade',
    )
    x_specification = fields.Html(
        string='Spesifikasi',
        help='Detail spesifikasi produk',
    )
    x_average_rating = fields.Float(
        string='Rata-rata Rating',
        digits=(3, 2),
        default=0.0,
    )
    x_review_count = fields.Integer(
        string='Jumlah Review',
        default=0,
    )
    x_brand = fields.Char(
        string='Merek',
    )
    x_weight_product = fields.Float(
        string='Berat Produk (gram)',
        digits=(10, 2),
        default=0.0,
    )
    x_free_shipping = fields.Boolean(
        string='Gratis Ongkir',
        default=False,
    )
    x_discount_percent = fields.Float(
        string='Diskon (%)',
        digits=(5, 2),
        default=0.0,
    )

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
