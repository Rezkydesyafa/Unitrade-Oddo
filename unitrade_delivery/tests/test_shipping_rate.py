from odoo.tests.common import TransactionCase

from odoo.addons.unitrade_delivery.shipping_methods import (
    GOSEND_RATE_TABLE,
    gosend_rate_for_distance,
    haversine_km,
    is_valid_coordinate,
)


class TestShippingRate(TransactionCase):
    """Unit test untuk rate engine pengiriman (fungsi murni)."""

    def test_gosend_rate_boundaries(self):
        # Tier inklusif batas atas, tidak tumpang tindih.
        self.assertEqual(gosend_rate_for_distance(0), 12000)
        self.assertEqual(gosend_rate_for_distance(3.0), 12000)
        self.assertEqual(gosend_rate_for_distance(3.01), 18000)
        self.assertEqual(gosend_rate_for_distance(8.0), 18000)
        self.assertEqual(gosend_rate_for_distance(8.01), 25000)
        self.assertEqual(gosend_rate_for_distance(15.0), 25000)
        self.assertEqual(gosend_rate_for_distance(15.01), 35000)
        self.assertEqual(gosend_rate_for_distance(25.0), 35000)
        self.assertEqual(gosend_rate_for_distance(25.01), 45000)
        self.assertEqual(gosend_rate_for_distance(100), 45000)

    def test_gosend_rate_negative_treated_as_zero(self):
        self.assertEqual(gosend_rate_for_distance(-5), 12000)

    def test_rate_table_last_tier_unbounded(self):
        self.assertIsNone(GOSEND_RATE_TABLE[-1][0])

    def test_is_valid_coordinate(self):
        # Yogyakarta valid.
        self.assertTrue(is_valid_coordinate(-7.7956, 110.3695))
        # 0/0 dan kosong tidak valid.
        self.assertFalse(is_valid_coordinate(0, 0))
        self.assertFalse(is_valid_coordinate(0.0, 110.3695))
        self.assertFalse(is_valid_coordinate(-7.7956, 0.0))
        self.assertFalse(is_valid_coordinate(False, False))
        self.assertFalse(is_valid_coordinate('', ''))
        self.assertFalse(is_valid_coordinate(None, None))
        # Di luar rentang valid.
        self.assertFalse(is_valid_coordinate(95.0, 110.0))
        self.assertFalse(is_valid_coordinate(-7.79, 200.0))

    def test_haversine_distance(self):
        # Tugu Yogyakarta -> Kampus UNISA (kira-kira beberapa km).
        distance = haversine_km(-7.7829, 110.3671, -7.7461, 110.3486)
        self.assertGreater(distance, 0)
        self.assertLess(distance, 20)
        # Titik identik berjarak 0.
        self.assertEqual(haversine_km(-7.78, 110.36, -7.78, 110.36), 0.0)
