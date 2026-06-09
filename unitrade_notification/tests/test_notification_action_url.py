from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestNotificationActionUrl(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env['res.users'].create({
            'name': 'Notification Scope User',
            'login': 'unitrade_notification_scope_user',
            'email': 'unitrade_notification_scope_user@example.com',
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
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
            '/unitrade/seller/products/%s' % self.product.id,
        )

    def test_review_inbox_action_url_falls_back_without_reference(self):
        notification = self._notification(
            event_code='review.reminder',
            action_url='/my/notifications?category=review',
        )

        self.assertEqual(
            notification._get_effective_action_url(),
            '/my/orders?status=done&tab=reviews#tab-ulasan',
        )

    def test_seller_review_inbox_action_url_falls_back_to_product_list(self):
        notification = self._notification(
            event_code='review.new_for_seller',
            action_url='/unitrade/seller/notifications?category=review',
        )

        self.assertEqual(
            notification._get_effective_action_url(),
            '/unitrade/seller/products',
        )

    def test_buyer_review_reminder_opens_my_orders_review_filter(self):
        notification = self._notification(
            event_code='review.reminder',
            reference_model='product.template',
            reference_id=self.product.id,
            action_url='/unitrade/product/%s?tab=reviews#tab-ulasan' % self.product.id,
        )

        self.assertEqual(
            notification._get_effective_action_url(),
            '/my/orders?status=done&tab=reviews#tab-ulasan',
        )

    def test_legacy_buyer_review_product_url_opens_my_orders(self):
        notification = self._notification(
            event_code='review.reminder',
            action_url='/unitrade/product/%s?tab=reviews#tab-ulasan' % self.product.id,
        )

        self.assertEqual(
            notification._get_effective_action_url(),
            '/my/orders?status=done&tab=reviews#tab-ulasan',
        )

    def test_review_user_and_seller_scopes_are_separate(self):
        buyer_review = self._notification(
            event_code='review.reminder',
        )
        seller_review = self._notification(
            event_code='review.new_for_seller',
        )

        self.assertEqual(buyer_review.recipient_scope, 'user')
        self.assertEqual(seller_review.recipient_scope, 'seller')

        Notification = self.env['unitrade.notification']
        self.assertIn(
            buyer_review,
            Notification.search(
                [('user_id', '=', self.user.id)]
                + Notification._notification_scope_domain('user')
            ),
        )
        self.assertIn(
            seller_review,
            Notification.search(
                [('user_id', '=', self.user.id)]
                + Notification._notification_scope_domain('seller')
            ),
        )

    def test_user_mark_all_does_not_read_seller_notifications(self):
        buyer_review = self._notification(
            event_code='review.reminder',
        )
        seller_review = self._notification(
            event_code='review.new_for_seller',
        )

        updated = self.env['unitrade.notification'].mark_all_as_read(
            self.user.id,
            recipient_scope='user',
        )

        self.assertGreaterEqual(updated, 1)
        self.assertTrue(
            self.env['unitrade.notification'].browse(buyer_review.id).is_read
        )
        self.assertFalse(
            self.env['unitrade.notification'].browse(seller_review.id).is_read
        )

    def test_explicit_user_scope_beats_seller_order_inference(self):
        order = self.env['sale.order'].create({
            'partner_id': self.user.partner_id.id,
        })
        notification = self._notification(
            category='payment',
            event_code='payment.success',
            reference_model='sale.order',
            reference_id=order.id,
            recipient_scope_hint='user',
            action_url='/unitrade/order/status/%s' % order.id,
        )

        self.assertEqual(notification.recipient_scope, 'user')
        self.assertEqual(
            notification._get_effective_action_url(),
            '/my/orders/%s' % order.id,
        )

    def test_explicit_seller_scope_routes_order_to_seller_dashboard(self):
        order = self.env['sale.order'].create({
            'partner_id': self.user.partner_id.id,
        })
        notification = self._notification(
            category='order',
            event_code='order.new_for_seller',
            reference_model='sale.order',
            reference_id=order.id,
            recipient_scope_hint='seller',
            action_url='/unitrade/seller/orders/%s' % order.id,
        )

        self.assertEqual(notification.recipient_scope, 'seller')
        self.assertEqual(
            notification._get_effective_action_url(),
            '/unitrade/seller/orders/%s' % order.id,
        )

    def test_user_payment_legacy_seller_order_url_opens_buyer_order(self):
        order = self.env['sale.order'].create({
            'partner_id': self.user.partner_id.id,
        })
        notification = self._notification(
            category='payment',
            event_code='payment.success',
            recipient_scope_hint='user',
            action_url='/unitrade/seller/orders/%s' % order.id,
        )

        self.assertEqual(notification.recipient_scope, 'user')
        self.assertEqual(
            notification._get_effective_action_url(),
            '/my/orders/%s' % order.id,
        )

    def test_user_order_legacy_seller_order_url_opens_buyer_order(self):
        order = self.env['sale.order'].create({
            'partner_id': self.user.partner_id.id,
        })
        notification = self._notification(
            category='order',
            event_code='order.confirmed',
            recipient_scope_hint='user',
            action_url='/unitrade/seller/orders/%s' % order.id,
        )

        self.assertEqual(notification.recipient_scope, 'user')
        self.assertEqual(
            notification._get_effective_action_url(),
            '/my/orders/%s' % order.id,
        )

    def test_user_payment_absolute_seller_order_url_opens_buyer_order(self):
        order = self.env['sale.order'].create({
            'partner_id': self.user.partner_id.id,
        })
        notification = self._notification(
            category='payment',
            event_code='payment.success',
            recipient_scope_hint='user',
            action_url='https://unitrade.web.id/unitrade/seller/orders/%s' % order.id,
        )

        self.assertEqual(notification.recipient_scope, 'user')
        self.assertEqual(
            notification._get_effective_action_url(),
            '/my/orders/%s' % order.id,
        )

    def test_user_payment_seller_order_list_url_falls_back_to_my_orders(self):
        notification = self._notification(
            category='payment',
            event_code='payment.pending',
            recipient_scope_hint='user',
            action_url='/unitrade/seller/orders',
        )

        self.assertEqual(notification.recipient_scope, 'user')
        self.assertEqual(
            notification._get_effective_action_url(),
            '/my/orders',
        )
