import logging

from odoo import _, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.unitrade_delivery.shipping_methods import (
    DEFAULT_SHIPPING_METHOD,
    SHIPPING_METHODS,
    gosend_rate_for_distance,
    haversine_km,
    is_valid_coordinate,
)

_logger = logging.getLogger(__name__)


class SaleOrderShipping(models.Model):
    _inherit = 'sale.order'

    x_shipping_method = fields.Selection(
        [
            ('pickup', 'Ambil Sendiri / COD'),
            ('gosend', 'GoSend Instant'),
        ],
        string='Metode Pengiriman',
        default=DEFAULT_SHIPPING_METHOD,
        copy=False,
    )
    x_shipping_cost = fields.Monetary(
        string='Ongkos Kirim',
        currency_field='currency_id',
        default=0.0,
        copy=False,
    )
    x_shipping_distance_km = fields.Float(
        string='Jarak Pengiriman (km)',
        digits=(10, 2),
        copy=False,
    )
    x_shipping_gps_warning = fields.Char(
        string='Peringatan GPS Pengiriman',
        copy=False,
    )

    # ------------------------------------------------------------------
    # Sumber koordinat GPS
    # ------------------------------------------------------------------
    def _unitrade_seller_coordinates(self):
        """Kembalikan (lat, lng) penjual dari product line checkout pertama yang valid.

        Prioritas: x_seller_latitude/longitude, fallback x_item_latitude/longitude.
        Kembalikan (False, False) bila tidak ada koordinat valid.
        """
        self.ensure_one()
        if hasattr(self, '_unitrade_product_lines_for_checkout'):
            product_lines = self._unitrade_product_lines_for_checkout()
        else:
            product_lines = self.order_line.filtered(
                lambda line: not line.display_type and line.product_id
            )
        for line in product_lines:
            template = line.product_id.product_tmpl_id.sudo()
            lat = template.x_seller_latitude if 'x_seller_latitude' in template._fields else False
            lng = template.x_seller_longitude if 'x_seller_longitude' in template._fields else False
            if is_valid_coordinate(lat, lng):
                return lat, lng
            lat = template.x_item_latitude if 'x_item_latitude' in template._fields else False
            lng = template.x_item_longitude if 'x_item_longitude' in template._fields else False
            if is_valid_coordinate(lat, lng):
                return lat, lng
        return False, False

    def _unitrade_buyer_coordinates(self):
        """Kembalikan (lat, lng) alamat pembeli dari partner_id."""
        self.ensure_one()
        partner = self.partner_id.sudo()
        lat = partner.x_unitrade_latitude if 'x_unitrade_latitude' in partner._fields else False
        lng = partner.x_unitrade_longitude if 'x_unitrade_longitude' in partner._fields else False
        return lat, lng

    # ------------------------------------------------------------------
    # Rate engine pesanan & validasi GPS
    # ------------------------------------------------------------------
    def _unitrade_compute_shipping_cost(self, shipping_method=None):
        """Hitung ongkir untuk metode pengiriman tertentu.

        Kembalikan dict {cost, distance_km, warning}. Tidak melempar error;
        GPS tidak valid menghasilkan cost 0 dengan warning terisi.
        """
        self.ensure_one()
        method = shipping_method or self.x_shipping_method or DEFAULT_SHIPPING_METHOD
        if method not in SHIPPING_METHODS:
            method = DEFAULT_SHIPPING_METHOD

        if method == 'pickup':
            return {'cost': 0.0, 'distance_km': 0.0, 'warning': ''}

        seller_lat, seller_lng = self._unitrade_seller_coordinates()
        buyer_lat, buyer_lng = self._unitrade_buyer_coordinates()

        if not is_valid_coordinate(buyer_lat, buyer_lng):
            return {
                'cost': 0.0,
                'distance_km': 0.0,
                'warning': _(
                    'Alamat Anda belum memiliki titik koordinat GPS. '
                    'Lengkapi koordinat alamat untuk memakai GoSend, atau pilih Ambil Sendiri.'
                ),
            }
        if not is_valid_coordinate(seller_lat, seller_lng):
            return {
                'cost': 0.0,
                'distance_km': 0.0,
                'warning': _(
                    'Lokasi penjual belum memiliki titik koordinat GPS, '
                    'sehingga ongkir GoSend belum bisa dihitung. Pilih Ambil Sendiri untuk sementara.'
                ),
            }

        distance_km = haversine_km(seller_lat, seller_lng, buyer_lat, buyer_lng)
        cost = gosend_rate_for_distance(distance_km)
        return {'cost': float(cost), 'distance_km': distance_km, 'warning': ''}

    def _unitrade_shipping_blocker(self):
        """Pesan blokir bila order tidak boleh lanjut ke pembayaran karena pengiriman.

        Kembalikan string pesan bila terblokir, selain itu False.
        """
        self.ensure_one()
        if (self.x_shipping_method or DEFAULT_SHIPPING_METHOD) != 'gosend':
            return False
        result = self._unitrade_compute_shipping_cost('gosend')
        if result.get('warning'):
            return result['warning']
        return False

    # ------------------------------------------------------------------
    # Sinkronisasi state shipping & fee line
    # ------------------------------------------------------------------
    def _unitrade_shipping_fee_product(self):
        """product.product untuk shipping fee line."""
        product = self.env.ref(
            'unitrade_delivery.product_unitrade_shipping_fee',
            raise_if_not_found=False,
        )
        return product.sudo() if product else self.env['product.product']

    def _unitrade_shipping_fee_lines(self):
        self.ensure_one()
        shipping_product = self._unitrade_shipping_fee_product()
        if not shipping_product:
            return self.env['sale.order.line']
        return self.order_line.filtered(lambda line: line.product_id == shipping_product)

    def _unitrade_sync_shipping_fee_line(self, amount):
        """Sinkronkan shipping fee line dengan nilai ongkir (pola fee line lain)."""
        self.ensure_one()
        shipping_product = self._unitrade_shipping_fee_product()
        if not shipping_product:
            return
        fee_lines = self._unitrade_shipping_fee_lines()
        amount = self.currency_id.round(amount or 0.0)
        method_label = SHIPPING_METHODS.get(
            self.x_shipping_method or DEFAULT_SHIPPING_METHOD, {}
        ).get('label', 'Pengiriman')
        if amount > 0:
            values = {
                'order_id': self.id,
                'product_id': shipping_product.id,
                'product_uom_qty': 1.0,
                'price_unit': amount,
                'name': _('Ongkir %s') % method_label,
                'tax_id': [(6, 0, [])],
            }
            if fee_lines:
                fee_lines[0].sudo().write({
                    'product_uom_qty': 1.0,
                    'price_unit': amount,
                    'name': values['name'],
                    'tax_id': [(6, 0, [])],
                })
                stale_lines = fee_lines - fee_lines[0]
                if stale_lines:
                    stale_lines.sudo().unlink()
            else:
                self.env['sale.order.line'].sudo().create(values)
        elif fee_lines:
            fee_lines.sudo().unlink()

    def _unitrade_sync_shipping_state(self, shipping_method=None):
        """Set field shipping + sinkronkan fee line. Hanya pada state draft."""
        self.ensure_one()
        if self.state != 'draft':
            return {
                'cost': self.x_shipping_cost,
                'distance_km': self.x_shipping_distance_km,
                'warning': self.x_shipping_gps_warning or '',
            }
        method = shipping_method or self.x_shipping_method or DEFAULT_SHIPPING_METHOD
        if method not in SHIPPING_METHODS:
            method = DEFAULT_SHIPPING_METHOD
        result = self._unitrade_compute_shipping_cost(method)
        self.sudo().write({
            'x_shipping_method': method,
            'x_shipping_cost': result['cost'],
            'x_shipping_distance_km': result['distance_km'],
            'x_shipping_gps_warning': result['warning'],
        })
        self._unitrade_sync_shipping_fee_line(result['cost'])
        self.invalidate_recordset(['order_line', 'amount_untaxed', 'amount_tax', 'amount_total'])
        return result

    def _unitrade_set_shipping_method(self, shipping_method):
        """Validasi & simpan metode pengiriman, lalu hitung ulang ongkir."""
        self.ensure_one()
        method = (shipping_method or '').strip()
        if method not in SHIPPING_METHODS:
            raise ValidationError(_('Metode pengiriman tidak valid.'))
        if self.state != 'draft':
            raise ValidationError(_('Metode pengiriman hanya bisa diubah sebelum pembayaran dibuat.'))
        return self._unitrade_sync_shipping_state(method)

    def _unitrade_shipping_method_options(self):
        """Daftar metode pengiriman untuk template checkout."""
        self.ensure_one()
        options = []
        for key, method in sorted(SHIPPING_METHODS.items(), key=lambda item: item[1].get('sequence', 999)):
            options.append({
                'key': key,
                'label': method['label'],
                'description': method['description'],
                'logo': method.get('logo', ''),
                'requires_gps': method.get('requires_gps', False),
            })
        return options
