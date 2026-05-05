from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)

DIY_DISTRICT_COORDINATES = {
    'yogyakarta': (-7.7956000, 110.3695000),
    'sleman': (-7.7162000, 110.3554000),
    'bantul': (-7.8881000, 110.3288000),
    'kulon_progo': (-7.8267000, 110.1641000),
    'gunungkidul': (-7.9656000, 110.6036000),
}


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

    @api.model_create_multi
    def create(self, vals_list):
        """Apply marketplace defaults when admins create UniTrade products."""
        for vals in vals_list:
            if vals.get('x_is_marketplace'):
                vals.setdefault('sale_ok', True)
                vals.setdefault('website_published', True)
                if 'detailed_type' in self._fields:
                    vals.setdefault('detailed_type', 'consu')
                elif 'type' in self._fields:
                    vals.setdefault('type', 'consu')
                self._unitrade_fill_district_coordinates(vals)
        products = super().create(vals_list)
        products._unitrade_autofill_missing_item_coordinates()
        return products

    def write(self, vals):
        result = super().write(vals)
        if {
            'x_is_marketplace',
            'x_item_district',
            'x_item_latitude',
            'x_item_longitude',
        }.intersection(vals):
            self._unitrade_autofill_missing_item_coordinates()
        return result

    @api.constrains(
        'x_is_marketplace',
        'image_1920',
        'product_template_image_ids',
        'x_seller_location',
        'x_item_province',
        'x_item_district',
        'description_sale',
    )
    def _check_unitrade_required_product_data(self):
        """Validate the minimum product data needed by the UniTrade frontend."""
        for record in self:
            if not record.x_is_marketplace:
                continue

            missing = []
            if not record.image_1920:
                missing.append(_('Gambar Utama'))
            if not record.x_seller_location:
                missing.append(_('Lokasi Penjual'))
            if not record.x_item_province:
                missing.append(_('Provinsi Barang'))
            if not record.x_item_district:
                missing.append(_('Kabupaten/Kota Barang'))
            if not record.description_sale or not record.description_sale.strip():
                missing.append(_('Deskripsi'))

            if missing:
                raise ValidationError(
                    _('Lengkapi data wajib produk UniTrade: %s.') % ', '.join(missing)
                )

            record._unitrade_check_image_count()

    def _unitrade_check_image_count(self):
        """Require 2-6 total product images, including the main image."""
        for record in self:
            if not record.x_is_marketplace:
                continue

            main_count = 1 if record.image_1920 else 0
            gallery_count = len(record.product_template_image_ids.filtered('image_1920'))
            total_images = main_count + gallery_count

            if total_images < 2 or total_images > 6:
                raise ValidationError(_(
                    'Produk UniTrade wajib memiliki total 2 sampai 6 gambar, '
                    'termasuk gambar utama. Saat ini ada %s gambar.'
                ) % total_images)

    @api.model
    def _unitrade_fill_district_coordinates(self, vals):
        district = vals.get('x_item_district')
        if not district or district not in DIY_DISTRICT_COORDINATES:
            return

        lat, lng = DIY_DISTRICT_COORDINATES[district]
        if not vals.get('x_item_latitude'):
            vals['x_item_latitude'] = lat
        if not vals.get('x_item_longitude'):
            vals['x_item_longitude'] = lng

    def _unitrade_autofill_missing_item_coordinates(self):
        """Use district center coordinates when GPS coordinates are empty or invalid."""
        for record in self:
            if not record.x_is_marketplace or not record.x_item_district:
                continue
            coordinates = DIY_DISTRICT_COORDINATES.get(record.x_item_district)
            if not coordinates:
                continue
            lat, lng = coordinates
            vals = {}
            if not record.x_item_latitude:
                vals['x_item_latitude'] = lat
            if not record.x_item_longitude:
                vals['x_item_longitude'] = lng
            if vals:
                super(ProductTemplateUniTrade, record).write(vals)

    @api.onchange('x_seller_id')
    def _onchange_x_seller_id_unitrade(self):
        """Prefill product location from the selected seller when possible."""
        for record in self:
            seller = record.x_seller_id
            if not seller:
                continue

            partner = seller.partner_id
            if partner and not record.x_seller_location:
                location_parts = [part for part in [partner.city, partner.state_id.name] if part]
                record.x_seller_location = ', '.join(location_parts) or partner.contact_address

    @api.onchange('x_item_district')
    def _onchange_x_item_district_unitrade(self):
        """Prefill item map coordinates from the selected district."""
        for record in self:
            coordinates = DIY_DISTRICT_COORDINATES.get(record.x_item_district)
            if not coordinates:
                continue
            lat, lng = coordinates
            if not record.x_item_latitude:
                record.x_item_latitude = lat
            if not record.x_item_longitude:
                record.x_item_longitude = lng

    def action_unitrade_publish(self):
        """Publish selected products in the UniTrade marketplace."""
        self.write({
            'x_is_marketplace': True,
            'sale_ok': True,
            'website_published': True,
        })
        _logger.info('Published %s UniTrade product(s) by %s', len(self), self.env.user.name)

    def action_unitrade_unpublish(self):
        """Hide selected products from the website while keeping them manageable in UniTrade."""
        self.write({
            'website_published': False,
        })
        _logger.info('Unpublished %s UniTrade product(s) by %s', len(self), self.env.user.name)

    @api.model
    def _search_marketplace_products(self, keyword=None, category_id=None,
                                      condition=None, min_price=None,
                                      max_price=None, location=None,
                                      sort_by='create_date desc', limit=20, offset=0):
        """Search marketplace products with filters"""
        domain = [
            ('x_is_marketplace', '=', True),
            ('sale_ok', '=', True),
            ('website_published', '=', True),
        ]

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


class ProductImageUniTrade(models.Model):
    _inherit = 'product.image'

    @api.model_create_multi
    def create(self, vals_list):
        images = super().create(vals_list)
        images.mapped('product_tmpl_id')._unitrade_check_image_count()
        return images

    def write(self, vals):
        result = super().write(vals)
        self.mapped('product_tmpl_id')._unitrade_check_image_count()
        return result

    def unlink(self):
        templates = self.mapped('product_tmpl_id')
        result = super().unlink()
        templates._unitrade_check_image_count()
        return result
