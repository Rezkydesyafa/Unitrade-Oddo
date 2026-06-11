import base64
from datetime import datetime
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged, new_test_user
from odoo.addons.unitrade_chat.controllers.main import UnitradeChatController


TINY_PNG = base64.b64encode(
    base64.b64decode(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII='
    )
).decode()


@tagged('standard', 'at_install')
class TestUnitradeChat(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.buyer = new_test_user(cls.env, login='chat_buyer', groups='base.group_portal')
        cls.other = new_test_user(cls.env, login='chat_other', groups='base.group_portal')
        cls.seller_user = new_test_user(cls.env, login='chat_seller', groups='base.group_portal')
        cls.seller = cls.env['unitrade.seller'].sudo().create({
            'user_id': cls.seller_user.id,
            'nim': '123456789',
            'status': 'verified',
        })

    def test_open_reuses_conversation(self):
        Chat = self.env['unitrade.chat.conversation'].with_user(self.buyer)
        first = Chat.open_for_seller(seller_id=self.seller.id)
        second = Chat.open_for_seller(seller_id=self.seller.id)
        self.assertEqual(first.id, second.id)
        self.assertEqual(first.buyer_user_id, self.buyer)
        self.assertEqual(first.seller_id, self.seller)

    def test_create_reuses_buyer_seller_room_even_with_product(self):
        Chat = self.env['unitrade.chat.conversation'].sudo()
        product = self.env['product.template'].sudo().create({
            'name': 'Chat Product',
            'list_price': 15000,
            'sale_ok': True,
        })
        first = Chat.create({
            'buyer_user_id': self.buyer.id,
            'seller_id': self.seller.id,
        })
        second = Chat.create({
            'buyer_user_id': self.buyer.id,
            'seller_id': self.seller.id,
            'product_id': product.id,
        })
        self.assertEqual(first.id, second.id)

    def test_non_participant_cannot_access(self):
        conversation = self.env['unitrade.chat.conversation'].with_user(self.buyer).open_for_seller(
            seller_id=self.seller.id,
        )
        with self.assertRaises(AccessError):
            conversation.with_user(self.other)._check_participant(self.other)

    def test_seller_cannot_chat_with_self(self):
        with self.assertRaises(UserError):
            self.env['unitrade.chat.conversation'].with_user(self.seller_user).open_for_seller(
                seller_id=self.seller.id,
            )

    def test_send_text_updates_history(self):
        conversation = self.env['unitrade.chat.conversation'].with_user(self.buyer).open_for_seller(
            seller_id=self.seller.id,
        )
        message = self.env['unitrade.chat.message'].with_user(self.buyer).create_from_controller(
            conversation,
            {'message_type': 'text', 'body': 'Halo, masih ada?'},
        )
        conversation.invalidate_recordset(['last_message_body', 'seller_unread_count'])
        self.assertEqual(message.body, 'Halo, masih ada?')
        self.assertEqual(conversation.last_message_body, 'Halo, masih ada?')
        self.assertEqual(conversation.seller_unread_count, 1)

    def test_message_payload_side_is_based_on_viewer(self):
        conversation = self.env['unitrade.chat.conversation'].with_user(self.buyer).open_for_seller(
            seller_id=self.seller.id,
        )
        buyer_message = self.env['unitrade.chat.message'].with_user(self.buyer).create_from_controller(
            conversation,
            {'message_type': 'text', 'body': 'Halo seller'},
        )
        seller_message = self.env['unitrade.chat.message'].with_user(self.seller_user).create_from_controller(
            conversation,
            {'message_type': 'text', 'body': 'Halo buyer'},
        )

        self.assertTrue(buyer_message._message_payload(self.buyer)['is_mine'])
        self.assertFalse(buyer_message._message_payload(self.seller_user)['is_mine'])
        self.assertTrue(seller_message._message_payload(self.seller_user)['is_mine'])
        self.assertFalse(seller_message._message_payload(self.buyer)['is_mine'])

    def test_message_payload_time_uses_wib(self):
        conversation = self.env['unitrade.chat.conversation'].with_user(self.buyer).open_for_seller(
            seller_id=self.seller.id,
        )
        message = self.env['unitrade.chat.message'].with_user(self.buyer).create_from_controller(
            conversation,
            {'message_type': 'text', 'body': 'Cek waktu WIB'},
        )
        fixed_utc = datetime(2026, 6, 11, 9, 23, 0)
        self.env.cr.execute(
            'UPDATE unitrade_chat_message SET create_date = %s WHERE id = %s',
            [fixed_utc, message.id],
        )
        message.invalidate_recordset(['create_date'])

        payload = message._message_payload(self.buyer)

        self.assertEqual(payload['time'], '16:23 WIB')
        self.assertEqual(payload['date'], '11 Juni 2026')

    def test_message_is_not_read_until_receiver_marks_visible_message(self):
        conversation = self.env['unitrade.chat.conversation'].sudo().create({
            'buyer_user_id': self.buyer.id,
            'seller_id': self.seller.id,
        })
        buyer_message = self.env['unitrade.chat.message'].with_user(self.buyer).create_from_controller(
            conversation,
            {'message_type': 'text', 'body': 'Halo seller'},
        )
        self.assertTrue(buyer_message.delivered_at)
        self.assertFalse(buyer_message.read_at)

        self.assertFalse(conversation.with_user(self.buyer).mark_read(self.buyer, last_seen_message_id=buyer_message.id))
        buyer_message.invalidate_recordset(['read_at'])
        self.assertFalse(buyer_message.read_at)

        self.assertFalse(conversation.with_user(self.seller_user).mark_read(self.seller_user))
        buyer_message.invalidate_recordset(['read_at'])
        self.assertFalse(buyer_message.read_at)

        self.assertTrue(conversation.with_user(self.seller_user).mark_read(
            self.seller_user,
            last_seen_message_id=buyer_message.id,
        ))
        buyer_message.invalidate_recordset(['read_at'])
        self.assertTrue(buyer_message.read_at)

    def test_read_receipt_does_not_mark_sender_own_messages(self):
        conversation = self.env['unitrade.chat.conversation'].sudo().create({
            'buyer_user_id': self.buyer.id,
            'seller_id': self.seller.id,
        })
        buyer_message = self.env['unitrade.chat.message'].with_user(self.buyer).create_from_controller(
            conversation,
            {'message_type': 'text', 'body': 'Halo seller'},
        )
        seller_message = self.env['unitrade.chat.message'].with_user(self.seller_user).create_from_controller(
            conversation,
            {'message_type': 'text', 'body': 'Halo buyer'},
        )

        conversation.with_user(self.seller_user).mark_read(self.seller_user, last_seen_message_id=seller_message.id)
        buyer_message.invalidate_recordset(['read_at'])
        seller_message.invalidate_recordset(['read_at'])
        self.assertTrue(buyer_message.read_at)
        self.assertFalse(seller_message.read_at)

    def test_invalid_image_rejected(self):
        conversation = self.env['unitrade.chat.conversation'].with_user(self.buyer).open_for_seller(
            seller_id=self.seller.id,
        )
        with self.assertRaises(ValidationError):
            self.env['unitrade.chat.message'].with_user(self.buyer).create_from_controller(
                conversation,
                {
                    'message_type': 'image',
                    'image_data': 'bad',
                    'filename': 'bad.txt',
                    'mimetype': 'text/plain',
                },
            )

    def test_report_requires_valid_reason_and_photo(self):
        conversation = self.env['unitrade.chat.conversation'].with_user(self.buyer).open_for_seller(
            seller_id=self.seller.id,
        )
        with self.assertRaises(ValidationError):
            self.env['unitrade.chat.report'].with_user(self.buyer).create_from_controller(
                conversation,
                {'reason': '   '},
            )
        with self.assertRaises(ValidationError):
            self.env['unitrade.chat.report'].with_user(self.buyer).create_from_controller(
                conversation,
                {
                    'reason': 'spam',
                    'proof_image_data': 'bad',
                    'proof_filename': 'bad.txt',
                    'proof_mimetype': 'text/plain',
                },
            )

    def test_report_accepts_up_to_three_proof_images(self):
        conversation = self.env['unitrade.chat.conversation'].with_user(self.buyer).open_for_seller(
            seller_id=self.seller.id,
        )
        proof = {
            'data': 'data:image/png;base64,%s' % TINY_PNG,
            'filename': 'proof.png',
            'mimetype': 'image/png',
        }
        report = self.env['unitrade.chat.report'].with_user(self.buyer).create_from_controller(
            conversation,
            {
                'reason': 'Produk mencurigakan',
                'proof_images': [proof, proof, proof],
            },
        )
        self.assertEqual(len(report.proof_attachment_ids), 3)

        with self.assertRaises(ValidationError):
            self.env['unitrade.chat.report'].with_user(self.buyer).create_from_controller(
                conversation,
                {
                    'reason': 'Terlalu banyak bukti',
                    'proof_images': [proof, proof, proof, proof],
                },
            )


class FakeResponse:

    def __init__(self, content=b'', status_code=200, headers=None):
        self.content = content
        self.status_code = status_code
        self.headers = dict(headers or [])


class FakeWebsiteOrder:

    def __init__(self):
        self.cart_quantity = 0

    def _cart_update(self, product_id=None, add_qty=0, **kwargs):
        self.cart_quantity += add_qty or 0
        return {'quantity': self.cart_quantity}


class FakeWebsite:

    def __init__(self):
        self.order = FakeWebsiteOrder()

    def sale_get_order(self, force_create=False):
        return self.order


class FakeRequest:

    def __init__(self, env):
        self.env = env
        self.website = FakeWebsite()

    def make_response(self, content, headers=None):
        return FakeResponse(content=content, headers=headers)

    def redirect(self, url):
        return FakeResponse(content=url.encode(), status_code=302, headers=[('Location', url)])

    def not_found(self):
        return FakeResponse(status_code=404)


@tagged('standard', 'at_install')
class TestUnitradeChatControllers(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_param('ir_attachment.location', 'db')
        cls.buyer = new_test_user(cls.env, login='chat_http_buyer', groups='base.group_portal')
        cls.seller_user = new_test_user(cls.env, login='chat_http_seller', groups='base.group_portal')
        cls.seller_user.write({'image_128': TINY_PNG})
        cls.seller = cls.env['unitrade.seller'].sudo().create({
            'user_id': cls.seller_user.id,
            'nim': '987654321',
            'status': 'verified',
        })
        Product = cls.env['product.template'].sudo()
        product_vals = {
            'name': 'HTTP Chat Product',
            'list_price': 32000,
            'sale_ok': True,
            'description_sale': 'Produk untuk test controller chat.',
        }
        if 'website_published' in Product._fields:
            product_vals['website_published'] = True
        if 'x_is_marketplace' in Product._fields:
            product_vals['x_is_marketplace'] = True
            product_vals.update({
                'image_1920': TINY_PNG,
                'product_template_image_ids': [(0, 0, {
                    'name': 'HTTP Chat Product Gallery',
                    'image_1920': TINY_PNG,
                })],
                'x_seller_location': 'Yogyakarta',
                'x_item_province': 'diy',
                'x_item_district': 'sleman',
            })
        if 'x_seller_id' in Product._fields:
            product_vals['x_seller_id'] = cls.seller.id
        cls.product = Product.create(product_vals)
        cls.conversation = cls.env['unitrade.chat.conversation'].with_user(cls.buyer).open_for_seller(
            seller_id=cls.seller.id,
            product_id=cls.product.id,
        )

    def test_avatar_route_returns_counterpart_profile_image(self):
        fake_request = FakeRequest(self.env(user=self.buyer.id))
        with patch('odoo.addons.unitrade_chat.controllers.main.request', fake_request):
            controller = UnitradeChatController()
            response = controller.avatar.__wrapped__(controller, self.seller_user.id)
        self.assertEqual(response.status_code, 200)
        self.assertIn('image/', response.headers.get('Content-Type', ''))
        self.assertTrue(response.content)

    def test_report_submit_valid(self):
        fake_request = FakeRequest(self.env(user=self.buyer.id))
        with patch('odoo.addons.unitrade_chat.controllers.main.request', fake_request):
            result = UnitradeChatController().report_user(
                conversation_id=self.conversation.id,
                reason='spam',
                proof_image_data='data:image/png;base64,%s' % TINY_PNG,
                proof_filename='proof.png',
                proof_mimetype='image/png',
            )
        self.assertTrue(result['success'])
        report = self.env['unitrade.chat.report'].sudo().browse(result['report_id'])
        self.assertTrue(report.exists())
        self.assertEqual(report.reporter_user_id, self.buyer)

    def test_product_card_cart_action(self):
        fake_request = FakeRequest(self.env(user=self.buyer.id))
        with patch('odoo.addons.unitrade_chat.controllers.main.request', fake_request):
            result = UnitradeChatController().add_product_to_cart(
                conversation_id=self.conversation.id,
                product_id=self.product.id,
                checkout=False,
            )
        self.assertTrue(result['success'])
        self.assertGreaterEqual(result['cart_quantity'], 1)
