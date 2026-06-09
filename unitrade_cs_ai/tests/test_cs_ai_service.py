from unittest.mock import MagicMock, patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestCsAiService(TransactionCase):

    def setUp(self):
        super().setUp()
        self.user = self.env['res.users'].create({
            'name': 'CS AI User',
            'login': 'cs_ai_user_test',
            'email': 'cs_ai_user_test@example.com',
        })
        self.service = self.env['unitrade.cs.ai.service']
        self.config = self.env['ir.config_parameter'].sudo()
        self.config.set_param('unitrade.cs.ai_enabled', 'True')
        self.config.set_param('unitrade.gemini.api_key', 'TEST_KEY')
        self.session = self.env['unitrade.cs.session'].sudo().create({
            'user_id': self.user.id,
            'state': 'ai_active',
        })

    def _fake_response(self, status_code=200, text='', payload=None):
        resp = MagicMock()
        resp.status_code = status_code
        resp.text = text
        resp.json.return_value = payload or {}
        return resp

    def test_no_api_key_raises(self):
        self.config.set_param('unitrade.gemini.api_key', '')
        with self.assertRaises(UserError):
            self.service.generate_reply(self.session, 'Halo')

    def test_success_returns_text(self):
        payload = {'candidates': [{'content': {'parts': [{'text': 'Halo, ada yang bisa dibantu?'}]}}]}
        with patch('odoo.addons.unitrade_cs_ai.models.cs_ai_service.requests.post',
                   return_value=self._fake_response(200, payload=payload)):
            reply = self.service.generate_reply(self.session, 'Halo')
        self.assertEqual(reply, 'Halo, ada yang bisa dibantu?')

    def test_rate_limit_error_raises(self):
        with patch('odoo.addons.unitrade_cs_ai.models.cs_ai_service.requests.post',
                   return_value=self._fake_response(429, text='quota')):
            with self.assertRaises(UserError):
                self.service.generate_reply(self.session, 'Halo')

    def test_ai_failure_keeps_user_message(self):
        # post_user_message harus tetap menyimpan pesan user walau AI gagal.
        with patch('odoo.addons.unitrade_cs_ai.models.cs_ai_service.requests.post',
                   side_effect=Exception('network down')):
            result = self.session.with_user(self.user).post_user_message('Tolong bantu')
        self.assertEqual(result['user_message'].author_type, 'user')
        # ai_message tetap dibuat sebagai pesan fallback (author_type ai).
        self.assertTrue(result['ai_message'])
        self.assertEqual(result['ai_message'].author_type, 'ai')
        user_messages = self.session.message_ids.filtered(lambda m: m.author_type == 'user')
        self.assertTrue(user_messages)

    def test_context_limited_to_five(self):
        for i in range(8):
            self.env['unitrade.cs.session.message'].sudo().create({
                'session_id': self.session.id,
                'author_type': 'user',
                'body': 'pesan %s' % i,
            })
        contents = self.service._build_contents(self.session, 'pesan terbaru')
        self.assertLessEqual(len(contents), 6)  # 5 history + kemungkinan 1 pesan baru
