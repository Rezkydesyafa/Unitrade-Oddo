from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class UnitradeDelivery(models.Model):
    _name = 'unitrade.delivery'
    _description = 'UniTrade Delivery'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    order_id = fields.Many2one('sale.order', string='Pesanan', required=True, ondelete='cascade', index=True)
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
