from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestNotificationActionUrl(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env.ref('base.user_admin')
        cls.product = cls.env['product.template'].with_context(
            unitrade_skip_marketplace_validation=True,
        ).create({
            'name': 'Notification URL Product',
            'sale_ok': True,
            'website_published': True,
            'x_is_marketplace': True,
            'description_sale': 'Product used by notification URL tests.',
        })

    def _notification(self, **overrides):
        values = {
            'user_id': self.user.id,
            'title': 'Test notification',
            'message': 'Test message',
            'category': 'review',
            'event_code': 'review.new_for_seller',
        }
        values.update(overrides)
        return self.env['unitrade.notification'].create(values)

    def test_review_reference_beats_stale_inbox_action_url(self):
        notification = self._notification(
            reference_model='product.template',
            reference_id=self.product.id,
            action_url='/my/notifications?category=review',
        )

        self.assertEqual(
            notification._get_effective_action_url(),
            '/unitrade/product/%s?tab=reviews#tab-ulasan' % self.product.id,
        )

    def test_review_inbox_action_url_falls_back_without_reference(self):
        notification = self._notification(
            action_url='/my/notifications?category=review',
        )

        self.assertEqual(
            notification._get_effective_action_url(),
            '/my/orders?status=done',
        )
