from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

from odoo.addons.unitrade_delivery.shipping_methods import haversine_km, is_valid_coordinate

_logger = logging.getLogger(__name__)


class UnitradeDelivery(models.Model):
    _name = 'unitrade.delivery'
    _description = 'UniTrade Delivery'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    order_id = fields.Many2one('sale.order', string='Pesanan', required=True, ondelete='cascade', index=True)
    shipping_method = fields.Selection([
        ('pickup', 'Ambil Sendiri / COD'),
        ('gosend', 'GoSend Instant'),
    ], string='Metode Pengiriman', default='gosend')
    seller_id = fields.Many2one('unitrade.seller', string='Penjual', index=True)
    buyer_id = fields.Many2one('res.partner', string='Pembeli', index=True)
    distance_km = fields.Float(string='Jarak (km)', digits=(10, 2))
    tracking_number = fields.Char(string='Nomor Resi')
    status = fields.Selection([
        ('pending', 'Pending'),
        ('picked_up', 'Dijemput'),
        ('in_transit', 'Dalam Pengiriman'),
        ('delivered', 'Terkirim'),
        ('failed', 'Gagal'),
    ], string='Status', default='pending')
    shipping_cost = fields.Float(string='Ongkos Kirim')
    pickup_address = fields.Char(string='Alamat Penjemput')
    pickup_lat = fields.Float(string='Pickup Latitude', digits=(10, 7))
    pickup_lng = fields.Float(string='Pickup Longitude', digits=(10, 7))
    dropoff_address = fields.Char(string='Alamat Tujuan')
    dropoff_lat = fields.Float(string='Dropoff Latitude', digits=(10, 7))
    dropoff_lng = fields.Float(string='Dropoff Longitude', digits=(10, 7))
    driver_name = fields.Char(string='Nama Driver', readonly=True)
    driver_phone = fields.Char(string='HP Driver', readonly=True)

    @api.constrains('tracking_number')
    def _check_tracking_number_length(self):
        for record in self:
            if record.tracking_number and not (1 <= len(record.tracking_number.strip()) <= 50):
                raise ValidationError(_('Nomor resi harus 1 sampai 50 karakter.'))

    @api.model
    def _unitrade_create_for_order(self, order):
        """Buat satu delivery record GoSend untuk order (idempotent)."""
        order = order.sudo()
        existing = self.sudo().search([('order_id', '=', order.id)], limit=1)
        if existing:
            return existing

        seller_lat = seller_lng = False
        seller = False
        if hasattr(order, '_unitrade_seller_coordinates'):
            seller_lat, seller_lng = order._unitrade_seller_coordinates()
        if hasattr(order, '_unitrade_primary_seller'):
            seller = order._unitrade_primary_seller()
        buyer_lat = buyer_lng = False
        if hasattr(order, '_unitrade_buyer_coordinates'):
            buyer_lat, buyer_lng = order._unitrade_buyer_coordinates()

        distance_km = order.x_shipping_distance_km if 'x_shipping_distance_km' in order._fields else 0.0
        if not distance_km and is_valid_coordinate(seller_lat, seller_lng) and is_valid_coordinate(buyer_lat, buyer_lng):
            distance_km = haversine_km(seller_lat, seller_lng, buyer_lat, buyer_lng)

        return self.sudo().create({
            'order_id': order.id,
            'shipping_method': 'gosend',
            'seller_id': seller.id if seller else False,
            'buyer_id': order.partner_id.id,
            'distance_km': distance_km or 0.0,
            'shipping_cost': order.x_shipping_cost if 'x_shipping_cost' in order._fields else 0.0,
            'pickup_lat': seller_lat or 0.0,
            'pickup_lng': seller_lng or 0.0,
            'dropoff_lat': buyer_lat or 0.0,
            'dropoff_lng': buyer_lng or 0.0,
            'dropoff_address': order.partner_id.contact_address or '',
            'status': 'pending',
        })

    def action_calculate_shipping(self):
        """Calculate shipping cost using GPS coordinates"""
        self.ensure_one()
        if not all([self.pickup_lat, self.pickup_lng, self.dropoff_lat, self.dropoff_lng]):
            _logger.warning('GPS coordinates incomplete for delivery %s', self.id)
            return 0.0

        # Distance-based calculation placeholder
        import math
        R = 6371
        dlat = math.radians(self.dropoff_lat - self.pickup_lat)
        dlng = math.radians(self.dropoff_lng - self.pickup_lng)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(self.pickup_lat)) * math.cos(math.radians(self.dropoff_lat)) * math.sin(dlng/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        distance_km = R * c

        # Base rate: Rp 2.500/km (placeholder)
        cost = max(10000, distance_km * 2500)
        self.shipping_cost = cost
        return cost
