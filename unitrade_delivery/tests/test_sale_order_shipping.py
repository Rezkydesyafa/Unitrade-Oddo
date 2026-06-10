from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestSaleOrderShipping(TransactionCase):
    """Test field & logika shipping pada sale.order."""

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Buyer Test'})
        self.order = self.env['sale.order'].create({'partner_id': self.partner.id})

    def test_default_shipping_method_pickup(self):
        self.assertEqual(self.order.x_shipping_method, 'pickup')
        self.assertEqual(self.order.x_shipping_cost, 0.0)

    def test_pickup_cost_zero(self):
        result = self.order._unitrade_compute_shipping_cost('pickup')
        self.assertEqual(result['cost'], 0.0)
        self.assertEqual(result['warning'], '')

    def test_gosend_without_buyer_gps_returns_warning(self):
        # partner tanpa koordinat -> warning, cost 0, dan blocker aktif.
        result = self.order._unitrade_compute_shipping_cost('gosend')
        self.assertEqual(result['cost'], 0.0)
        self.assertTrue(result['warning'])
        self.order.x_shipping_method = 'gosend'
        self.assertTrue(self.order._unitrade_shipping_blocker())

    def test_set_shipping_method_invalid_rejected(self):
        with self.assertRaises(ValidationError):
            self.order._unitrade_set_shipping_method('kurir_reguler')

    def test_set_shipping_method_pickup_syncs_state(self):
        self.order._unitrade_set_shipping_method('pickup')
        self.assertEqual(self.order.x_shipping_method, 'pickup')
        self.assertEqual(self.order.x_shipping_cost, 0.0)
        # Tidak ada shipping fee line untuk ongkir 0.
        self.assertFalse(self.order._unitrade_shipping_fee_lines())

    def test_change_method_blocked_when_not_draft(self):
        # Paksa order keluar dari draft lewat field state.
        self.order.write({'state': 'sent'})
        with self.assertRaises(ValidationError):
            self.order._unitrade_set_shipping_method('gosend')
