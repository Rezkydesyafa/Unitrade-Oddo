from datetime import timedelta

from odoo import SUPERUSER_ID, models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.osv import expression
from odoo.tools.float_utils import float_compare
import logging

_logger = logging.getLogger(__name__)

DIY_DISTRICT_COORDINATES = {
    'yogyakarta': (-7.7956000, 110.3695000),
    'sleman': (-7.7162000, 110.3554000),
    'bantul': (-7.8881000, 110.3288000),
    'kulon_progo': (-7.8267000, 110.1641000),
    'gunungkidul': (-7.9656000, 110.6036000),
}

UNITRADE_LISTING_DURATION_DAYS = 30


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
    x_listing_fee = fields.Monetary(
        string='Biaya Listing',
        currency_field='currency_id',
        default=0.0,
        help='Biaya listing yang ditampilkan pada dashboard penjual UniTrade.',
    )
    x_listing_activated_at = fields.Datetime(
        string='Listing Aktif Sejak',
        help='Waktu produk mulai aktif setelah pembayaran biaya listing berhasil.',
    )
    x_listing_expires_at = fields.Datetime(
        string='Listing Berakhir',
        help='Tanggal berakhir listing. Sistem otomatis menonaktifkan produk setelah tanggal ini.',
    )
    x_unitrade_manual_stock_qty = fields.Float(
        string='Stok Manual UniTrade',
        default=0.0,
        help='Fallback stok untuk produk marketplace lama yang tidak bisa dikonversi menjadi stockable product.',
    )

    # === Operational state for admin ===
    x_listing_status = fields.Selection(
        [
            ('draft', 'Draft'),
            ('fee_pending', 'Menunggu Fee'),
            ('published', 'Terpublikasi'),
            ('rejected', 'Ditolak'),
            ('archived', 'Diarsipkan'),
            ('expired', 'Kadaluarsa'),
        ],
        string='Status Listing',
        compute='_compute_x_listing_status',
        store=True,
        index=True,
    )
    x_listing_fee_status = fields.Selection(
        [
            ('not_required', 'Tidak Wajib'),
            ('unpaid', 'Belum Bayar'),
            ('pending', 'Menunggu Pembayaran'),
            ('paid', 'Lunas'),
            ('failed', 'Gagal'),
            ('waived', 'Diwaiver'),
        ],
        string='Status Fee Listing',
        default='not_required',
        copy=False,
        index=True,
    )
    x_listing_fee_payment_id = fields.Many2one(
        'unitrade.payment.intent',
        string='Pembayaran Fee Listing',
        copy=False,
        readonly=True,
        help='Payment intent yang melunasi fee listing produk ini.',
    )
    x_listing_fee_paid_at = fields.Datetime(
        string='Fee Dibayar Pada',
        copy=False,
        readonly=True,
    )
    x_listing_fee_waived_by_id = fields.Many2one(
        'res.users',
        string='Fee Diwaiver Oleh',
        copy=False,
        readonly=True,
    )
    x_listing_fee_waive_reason = fields.Text(
        string='Alasan Waive Fee',
        copy=False,
    )
    x_listing_rejected_by_id = fields.Many2one(
        'res.users',
        string='Direjeksi Oleh',
        copy=False,
        readonly=True,
    )
    x_listing_rejection_reason = fields.Text(
        string='Alasan Rejeksi',
        copy=False,
    )
    x_unitrade_stock_qty = fields.Float(
        string='Stok UniTrade',
        compute='_compute_unitrade_stock_qty',
        inverse='_inverse_unitrade_stock_qty',
        help='Jumlah stok fisik di warehouse website UniTrade. Mengubah field ini akan membuat inventory adjustment.',
    )
    x_unitrade_free_qty = fields.Float(
        string='Stok Tersedia Checkout',
        compute='_compute_unitrade_stock_qty',
        help='Stok yang masih tersedia untuk dijual, setelah memperhitungkan reservasi.',
    )

    def _unitrade_stock_warehouse(self):
        company = self.env.company
        website = self.env['website'].sudo().search([
            ('company_id', '=', company.id),
        ], limit=1)
        warehouse_id = website._get_warehouse_available() if website else False
        warehouse = self.env['stock.warehouse'].sudo().browse(warehouse_id).exists() if warehouse_id else False
        if not warehouse:
            warehouse = self.env['stock.warehouse'].sudo().search([('company_id', '=', company.id)], limit=1)
        return warehouse

    def _unitrade_discount_percent(self):
        self.ensure_one()
        return max(min(self.x_discount_percent or 0.0, 100.0), 0.0)

    def _unitrade_discounted_price(self):
        self.ensure_one()
        original_price = self.list_price or 0.0
        discount_percent = self._unitrade_discount_percent()
        if not discount_percent or original_price <= 0:
            return original_price
        return original_price * (100.0 - discount_percent) / 100.0

    def _unitrade_price_info(self):
        self.ensure_one()
        discount_percent = self._unitrade_discount_percent()
        original_price = self.list_price or 0.0
        discounted_price = self._unitrade_discounted_price()
        return {
            'original_price': original_price,
            'discounted_price': discounted_price,
            'discount_percent': discount_percent,
            'has_discount': bool(discount_percent and original_price > 0 and discounted_price < original_price),
        }

    @api.model
    def _unitrade_listing_duration_days(self):
        try:
            duration = int(self.env['ir.config_parameter'].sudo().get_param(
                'unitrade.seller.listing_duration_days',
                UNITRADE_LISTING_DURATION_DAYS,
            ) or UNITRADE_LISTING_DURATION_DAYS)
        except (TypeError, ValueError):
            duration = UNITRADE_LISTING_DURATION_DAYS
        return max(1, duration)

    def _unitrade_listing_expiry_from(self, paid_at=False):
        paid_at = fields.Datetime.to_datetime(paid_at) if paid_at else fields.Datetime.now()
        return paid_at + timedelta(days=self._unitrade_listing_duration_days())

    @api.model
    def _unitrade_public_active_domain(self):
        """Canonical public visibility rule for UniTrade marketplace products."""
        domain = [
            ('x_is_marketplace', '=', True),
            ('sale_ok', '=', True),
            ('website_published', '=', True),
        ]
        if 'x_seller_id' not in self._fields or 'x_listing_expires_at' not in self._fields:
            return domain

        now = fields.Datetime.now()
        return expression.AND([
            domain,
            expression.OR([
                [('x_seller_id', '=', False)],
                [
                    ('x_seller_id', '!=', False),
                    ('x_listing_expires_at', '!=', False),
                    ('x_listing_expires_at', '>=', now),
                ],
            ]),
        ])

    def _unitrade_is_publicly_available(self):
        self.ensure_one()
        if not self.x_is_marketplace or not self.sale_ok or not self.website_published:
            return False
        if self.x_seller_id:
            return bool(
                self.x_listing_expires_at
                and self.x_listing_expires_at >= fields.Datetime.now()
                and self._unitrade_has_paid_listing_fee()
            )
        return True

    @api.model
    def _unitrade_paid_listing_product_ids(self, products):
        products = products.exists()
        if not products or 'unitrade.payment.intent' not in self.env.registry:
            return set()
        intents = self.env['unitrade.payment.intent'].sudo().search([
            ('intent_type', '=', 'listing_fee'),
            ('state', '=', 'paid'),
            ('product_template_id', 'in', products.ids),
        ])
        return set(intents.mapped('product_template_id').ids)

    def _unitrade_has_paid_listing_fee(self):
        self.ensure_one()
        if not self.x_seller_id:
            return True
        if 'unitrade.payment.intent' not in self.env.registry:
            return False
        return bool(self.env['unitrade.payment.intent'].sudo().search_count([
            ('intent_type', '=', 'listing_fee'),
            ('state', '=', 'paid'),
            ('product_template_id', '=', self.id),
        ]))

    def _unitrade_apply_listing_payment(self, listing_fee=0.0, paid_at=False):
        paid_at = fields.Datetime.to_datetime(paid_at) if paid_at else fields.Datetime.now()
        values = {
            'sale_ok': True,
            'website_published': True,
            'x_listing_activated_at': paid_at,
            'x_listing_expires_at': self._unitrade_listing_expiry_from(paid_at),
        }
        if 'x_listing_fee' in self._fields:
            values['x_listing_fee'] = listing_fee or 0.0
        self.sudo().write(values)

    def _unitrade_listing_state_payload(self):
        self.ensure_one()
        now = fields.Datetime.now()
        expires_at = self.x_listing_expires_at
        is_published = bool(self.sale_ok and self.website_published)
        if not expires_at:
            if self.x_seller_id:
                return {
                    'is_active': False,
                    'status_label': 'Nonaktif',
                    'label': 'Belum aktif',
                    'expiry_label': 'Belum aktif',
                    'state': 'inactive',
                    'expiry_state': 'inactive',
                    'days_remaining': False,
                    'expires_at': False,
                }
            label = 'Tanpa batas' if is_published else 'Belum aktif'
            return {
                'is_active': is_published,
                'status_label': 'Aktif' if is_published else 'Nonaktif',
                'label': label,
                'expiry_label': label,
                'state': 'neutral' if is_published else 'inactive',
                'expiry_state': 'neutral' if is_published else 'inactive',
                'days_remaining': False,
                'expires_at': False,
            }

        if expires_at < now:
            return {
                'is_active': False,
                'status_label': 'Nonaktif',
                'label': 'Masa aktif habis',
                'expiry_label': 'Masa aktif habis',
                'state': 'expired',
                'expiry_state': 'expired',
                'days_remaining': 0,
                'expires_at': fields.Datetime.to_string(expires_at),
            }

        days_remaining = max(0, int((expires_at.date() - now.date()).days))
        if days_remaining <= 0:
            label = 'Aktif sampai hari ini'
            expiry_state = 'warning'
        else:
            label = 'Sisa %s hari' % days_remaining
            expiry_state = 'warning' if days_remaining <= 3 else 'active'
        return {
            'is_active': is_published,
            'status_label': 'Aktif' if is_published else 'Nonaktif',
            'label': label,
            'expiry_label': label,
            'state': expiry_state,
            'expiry_state': expiry_state,
            'days_remaining': days_remaining,
            'expires_at': fields.Datetime.to_string(expires_at),
        }

    @api.model
    def _unitrade_backfill_listing_expiry_from_paid_intents(self, seller=False):
        if 'unitrade.payment.intent' not in self.env.registry:
            return 0

        domain = [
            ('x_is_marketplace', '=', True),
            ('x_listing_expires_at', '=', False),
            ('x_seller_id', '!=', False),
        ]
        if seller:
            domain.append(('x_seller_id', '=', seller.id))
        products = self.sudo().search(domain)
        if not products:
            return 0

        intents = self.env['unitrade.payment.intent'].sudo().search([
            ('intent_type', '=', 'listing_fee'),
            ('state', '=', 'paid'),
            ('product_template_id', 'in', products.ids),
        ], order='paid_at desc, write_date desc, create_date desc, id desc')
        latest_by_product = {}
        for intent in intents:
            if intent.product_template_id.id not in latest_by_product:
                latest_by_product[intent.product_template_id.id] = intent

        updated = 0
        for product in products:
            intent = latest_by_product.get(product.id)
            if intent:
                paid_at = intent.paid_at or intent.write_date or intent.create_date or fields.Datetime.now()
            else:
                continue
            values = {
                'x_listing_activated_at': paid_at,
                'x_listing_expires_at': product._unitrade_listing_expiry_from(paid_at),
            }
            if intent and not product.x_listing_fee:
                values['x_listing_fee'] = intent.amount
            product.sudo().write(values)
            updated += 1
        return updated

    @api.model
    def _unitrade_deactivate_unpaid_seller_listings(self, seller=False):
        domain = [
            ('x_is_marketplace', '=', True),
            ('x_seller_id', '!=', False),
            '|',
            ('x_listing_expires_at', '!=', False),
            '|',
            ('website_published', '=', True),
            ('sale_ok', '=', True),
        ]
        if seller:
            domain.insert(1, ('x_seller_id', '=', seller.id))
        candidates = self.sudo().with_context(active_test=False).search(domain)
        paid_product_ids = self._unitrade_paid_listing_product_ids(candidates)
        unpaid_products = candidates.filtered(lambda product: product.id not in paid_product_ids)
        if not unpaid_products:
            return 0
        unpaid_products.write({
            'website_published': False,
            'sale_ok': False,
            'x_listing_activated_at': False,
            'x_listing_expires_at': False,
        })
        _logger.info('Deactivated %s unpaid UniTrade seller listing(s).', len(unpaid_products))
        return len(unpaid_products)

    @api.model
    def _unitrade_deactivate_expired_listings(self, seller=False):
        now = fields.Datetime.now()
        domain = [
            ('x_is_marketplace', '=', True),
            ('x_listing_expires_at', '!=', False),
            ('x_listing_expires_at', '<', now),
            '|',
            ('website_published', '=', True),
            ('sale_ok', '=', True),
        ]
        if seller:
            domain.insert(1, ('x_seller_id', '=', seller.id))
        expired_products = self.sudo().search(domain)
        if not expired_products:
            return 0
        expired_products.write({
            'website_published': False,
            'sale_ok': False,
        })
        _logger.info('Deactivated %s expired UniTrade listing(s).', len(expired_products))
        return len(expired_products)

    @api.model
    def _unitrade_reactivate_current_listings(self, seller=False):
        now = fields.Datetime.now()
        domain = [
            ('x_is_marketplace', '=', True),
            ('x_listing_expires_at', '!=', False),
            ('x_listing_expires_at', '>=', now),
            '|',
            ('website_published', '=', False),
            ('sale_ok', '=', False),
        ]
        if seller:
            domain.insert(1, ('x_seller_id', '=', seller.id))
        current_products = self.sudo().search(domain)
        if not current_products:
            return 0
        values = {
            'website_published': True,
            'sale_ok': True,
        }
        current_products.write(values)
        _logger.info('Reactivated %s current UniTrade listing(s).', len(current_products))
        return len(current_products)

    @api.model
    def _unitrade_refresh_listing_states(self, seller=False):
        backfilled = self._unitrade_backfill_listing_expiry_from_paid_intents(seller=seller)
        unpaid_deactivated = self._unitrade_deactivate_unpaid_seller_listings(seller=seller)
        reactivated = self._unitrade_reactivate_current_listings(seller=seller)
        deactivated = self._unitrade_deactivate_expired_listings(seller=seller)
        return {
            'backfilled': backfilled,
            'unpaid_deactivated': unpaid_deactivated,
            'reactivated': reactivated,
            'deactivated': deactivated,
        }

    @api.model
    def _cron_unitrade_deactivate_expired_listings(self):
        result = self._unitrade_refresh_listing_states()
        _logger.info(
            'UniTrade listing expiry cron completed: backfilled=%s unpaid_deactivated=%s reactivated=%s deactivated=%s',
            result.get('backfilled', 0),
            result.get('unpaid_deactivated', 0),
            result.get('reactivated', 0),
            result.get('deactivated', 0),
        )
        return result

    def _unitrade_uses_manual_stock(self):
        self.ensure_one()
        product_type = self.detailed_type if 'detailed_type' in self._fields else self.type
        return bool(self.x_is_marketplace and product_type != 'product')

    @api.depends(
        'product_variant_ids.qty_available',
        'product_variant_ids.free_qty',
        'x_unitrade_manual_stock_qty',
        'detailed_type',
        'type',
        'x_is_marketplace',
    )
    def _compute_unitrade_stock_qty(self):
        warehouse = self._unitrade_stock_warehouse()
        warehouse_id = warehouse.id if warehouse else False
        for record in self:
            if record._unitrade_uses_manual_stock():
                stock_qty = max(record.x_unitrade_manual_stock_qty or 0.0, 0.0)
                record.x_unitrade_stock_qty = stock_qty
                record.x_unitrade_free_qty = stock_qty
                continue
            if not warehouse_id or not record.product_variant_id:
                record.x_unitrade_stock_qty = 0
                record.x_unitrade_free_qty = 0
                continue
            variant = record.product_variant_id.with_context(warehouse=warehouse_id)
            record.x_unitrade_stock_qty = variant.qty_available
            record.x_unitrade_free_qty = variant.free_qty

    def _inverse_unitrade_stock_qty(self):
        warehouse = self._unitrade_stock_warehouse()
        if not warehouse or not warehouse.lot_stock_id:
            raise ValidationError(_('Warehouse stok UniTrade belum tersedia. Pastikan modul Inventory aktif.'))

        StockQuant = self.env['stock.quant'].with_user(SUPERUSER_ID).sudo().with_context(inventory_mode=True)
        for record in self:
            if record.x_unitrade_stock_qty < 0:
                raise ValidationError(_('Stok UniTrade tidak boleh negatif.'))
            if len(record.product_variant_ids) != 1:
                raise ValidationError(_('Stok UniTrade hanya bisa diatur dari form ini untuk produk tanpa varian.'))

            if record._unitrade_uses_manual_stock():
                record.with_context(skip_unitrade_stock_inverse=True).sudo().write({
                    'x_unitrade_manual_stock_qty': record.x_unitrade_stock_qty,
                })
                _logger.info(
                    'UniTrade manual stock adjusted for product %s by %s: %s',
                    record.display_name,
                    self.env.user.name,
                    record.x_unitrade_stock_qty,
                )
                continue

            if record.detailed_type != 'product':
                try:
                    record.with_user(SUPERUSER_ID).with_context(skip_unitrade_stock_inverse=True).write({
                        'detailed_type': 'product',
                    })
                except UserError:
                    record.with_context(skip_unitrade_stock_inverse=True).sudo().write({
                        'x_unitrade_manual_stock_qty': record.x_unitrade_stock_qty,
                    })
                    _logger.warning(
                        'UniTrade product %s cannot be converted to stockable during stock update; using manual stock fallback.',
                        record.id,
                    )
                    continue

            product = record.product_variant_id
            current_qty = product.with_context(warehouse=warehouse.id).qty_available
            rounding = product.uom_id.rounding
            if float_compare(record.x_unitrade_stock_qty, current_qty, precision_rounding=rounding) == 0:
                continue

            quant = StockQuant.create({
                'product_id': product.id,
                'location_id': warehouse.lot_stock_id.id,
                'inventory_quantity': record.x_unitrade_stock_qty,
            })
            quant.action_apply_inventory()
            _logger.info(
                'UniTrade stock adjusted for product %s by %s: %s -> %s',
                record.display_name,
                self.env.user.name,
                current_qty,
                record.x_unitrade_stock_qty,
            )

    @api.model_create_multi
    def create(self, vals_list):
        """Apply marketplace defaults when admins create UniTrade products."""
        for vals in vals_list:
            if vals.get('x_is_marketplace'):
                vals.setdefault('sale_ok', True)
                vals.setdefault('website_published', True)
                if 'detailed_type' in self._fields:
                    vals.setdefault('detailed_type', 'product')
                elif 'type' in self._fields:
                    vals.setdefault('type', 'product')
                if 'allow_out_of_stock_order' in self._fields:
                    vals.setdefault('allow_out_of_stock_order', False)
                self._unitrade_fill_district_coordinates(vals)
        products = super().create(vals_list)
        products._unitrade_autofill_missing_item_coordinates()
        return products

    def write(self, vals):
        if (
            not self.env.context.get('skip_unitrade_stock_inverse')
            and not self.env.context.get('unitrade_preserve_product_type')
            and vals.get('x_is_marketplace')
            and 'detailed_type' in self._fields
            and 'detailed_type' not in vals
        ):
            vals = dict(vals, detailed_type='product')
        if vals.get('x_is_marketplace') and 'allow_out_of_stock_order' in self._fields and 'allow_out_of_stock_order' not in vals:
            vals = dict(vals, allow_out_of_stock_order=False)
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
        if self.env.context.get('unitrade_skip_marketplace_validation'):
            return
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
        if self.env.context.get('unitrade_skip_marketplace_validation'):
            return
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
            'allow_out_of_stock_order': False,
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
        self._unitrade_refresh_listing_states()
        domain = self._unitrade_public_active_domain()

        if keyword:
            domain = expression.AND([domain, ['|',
                ('name', 'ilike', keyword),
                ('description_sale', 'ilike', keyword),
            ]])
        if category_id:
            domain = expression.AND([domain, [('categ_id', 'child_of', int(category_id))]])
        if condition:
            domain = expression.AND([domain, [('x_condition', '=', condition)]])
        if min_price:
            domain = expression.AND([domain, [('list_price', '>=', float(min_price))]])
        if max_price:
            domain = expression.AND([domain, [('list_price', '<=', float(max_price))]])
        if location:
            domain = expression.AND([domain, [('x_seller_location', 'ilike', location)]])

        return self.search(domain, order=sort_by, limit=limit, offset=offset)

    # ------------------------------------------------------------------
    # Listing operational status — admin orchestration
    # ------------------------------------------------------------------
    @api.depends(
        'x_is_marketplace',
        'x_listing_fee_status',
        'x_listing_expires_at',
        'website_published',
        'sale_ok',
        'active',
    )
    def _compute_x_listing_status(self):
        now = fields.Datetime.now()
        for record in self:
            if not record.x_is_marketplace:
                record.x_listing_status = 'draft'
                continue
            if not record.active:
                record.x_listing_status = 'archived'
                continue
            if record.x_listing_fee_status == 'failed':
                record.x_listing_status = 'rejected'
                continue
            if record.x_listing_fee_status in ('unpaid', 'pending'):
                record.x_listing_status = 'fee_pending'
                continue
            # Check expired
            if record.x_listing_expires_at and record.x_listing_expires_at < now:
                record.x_listing_status = 'expired'
                continue
            if record.website_published and record.sale_ok:
                record.x_listing_status = 'published'
                continue
            record.x_listing_status = 'draft'

    def _unitrade_is_admin(self):
        return (
            self.env.user.has_group('unitrade_seller.group_unitrade_admin')
            or self.env.user.has_group('base.group_system')
        )

    def _check_admin(self, action_label):
        if not self._unitrade_is_admin():
            from odoo.exceptions import AccessDenied
            _logger.warning(
                'Product %s: unauthorized %s by uid=%s',
                self.mapped('id') or '-', action_label, self.env.uid,
            )
            raise AccessDenied(_('Aksi ini hanya boleh dilakukan oleh admin UniTrade.'))

    def _audit(self, action, description, severity='info', payload=None):
        if 'unitrade.admin.audit.log' not in self.env.registry:
            return
        AuditLog = self.env['unitrade.admin.audit.log']
        for product in self:
            try:
                AuditLog.sudo().log_action(
                    action,
                    description=description,
                    record=product,
                    severity=severity,
                    payload=payload,
                )
            except Exception:  # noqa: BLE001
                _logger.exception('Failed to write product audit log: %s', action)

    def action_unitrade_waive_listing_fee(self):
        """Open wizard untuk waive fee dengan alasan wajib."""
        self._check_admin('waive_listing_fee')
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Waive Fee Listing'),
            'res_model': 'unitrade.product.waive.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_product_id': self.id},
        }

    def action_unitrade_reject_listing(self):
        """Open wizard untuk reject produk dengan alasan wajib."""
        self._check_admin('reject_listing')
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Reject Listing'),
            'res_model': 'unitrade.product.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_product_id': self.id},
        }

    def action_unitrade_publish_admin(self):
        """Admin manually publish marketplace product."""
        self._check_admin('publish_admin')
        for product in self:
            product.write({
                'x_is_marketplace': True,
                'sale_ok': True,
                'website_published': True,
                'active': True,
            })
            product._audit(
                'product.publish',
                _('Produk %s dipublish manual oleh %s.') % (product.display_name, self.env.user.name),
                severity='info',
                payload={'seller_id': product.x_seller_id.id, 'product_id': product.id},
            )
        return True

    def action_unitrade_unpublish_admin(self):
        """Admin manually unpublish marketplace product."""
        self._check_admin('unpublish_admin')
        for product in self:
            product.write({'website_published': False})
            product._audit(
                'product.unpublish',
                _('Produk %s di-unpublish manual oleh %s.') % (product.display_name, self.env.user.name),
                severity='warning',
                payload={'seller_id': product.x_seller_id.id, 'product_id': product.id},
            )
        return True

    def action_open_listing_fee_payment(self):
        """Open the related payment intent record."""
        self.ensure_one()
        if not self.x_listing_fee_payment_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'unitrade.payment.intent',
            'res_id': self.x_listing_fee_payment_id.id,
            'view_mode': 'form',
        }


class ProductProductUniTrade(models.Model):
    _inherit = 'product.product'

    def _unitrade_discount_percent(self):
        self.ensure_one()
        return self.product_tmpl_id._unitrade_discount_percent()

    def _unitrade_discounted_price(self):
        self.ensure_one()
        original_price = self.lst_price or self.list_price or 0.0
        discount_percent = self._unitrade_discount_percent()
        if not discount_percent or original_price <= 0:
            return original_price
        return original_price * (100.0 - discount_percent) / 100.0

    def _unitrade_price_info(self):
        self.ensure_one()
        discount_percent = self._unitrade_discount_percent()
        original_price = self.lst_price or self.list_price or 0.0
        discounted_price = self._unitrade_discounted_price()
        return {
            'original_price': original_price,
            'discounted_price': discounted_price,
            'discount_percent': discount_percent,
            'has_discount': bool(discount_percent and original_price > 0 and discounted_price < original_price),
        }

    def _unitrade_is_stock_limited(self):
        self.ensure_one()
        if self.type == 'product':
            return not self.allow_out_of_stock_order
        template = self.product_tmpl_id
        return bool(
            hasattr(template, '_unitrade_uses_manual_stock')
            and template._unitrade_uses_manual_stock()
        )

    def _unitrade_available_qty(self, warehouse=False):
        self.ensure_one()
        if self.type == 'product':
            product = self.sudo()
            warehouse_id = getattr(warehouse, 'id', warehouse) if warehouse else False
            if warehouse_id:
                product = product.with_context(warehouse=warehouse_id)
            return product.free_qty
        template = self.product_tmpl_id.sudo()
        if hasattr(template, '_unitrade_uses_manual_stock') and template._unitrade_uses_manual_stock():
            return max(template.x_unitrade_manual_stock_qty or 0.0, 0.0)
        return 0.0


class ProductImageUniTrade(models.Model):
    _inherit = 'product.image'

    @api.model_create_multi
    def create(self, vals_list):
        images = super().create(vals_list)
        if not self.env.context.get('unitrade_skip_marketplace_validation'):
            images.mapped('product_tmpl_id')._unitrade_check_image_count()
        return images

    def write(self, vals):
        result = super().write(vals)
        if not self.env.context.get('unitrade_skip_marketplace_validation'):
            self.mapped('product_tmpl_id')._unitrade_check_image_count()
        return result

    def unlink(self):
        templates = self.mapped('product_tmpl_id')
        result = super().unlink()
        if not self.env.context.get('unitrade_skip_marketplace_validation'):
            templates._unitrade_check_image_count()
        return result
