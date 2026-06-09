from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestCsSession(TransactionCase):

    def setUp(self):
        super().setUp()
        self.user = self.env['res.users'].create({
            'name': 'CS Buyer',
            'login': 'cs_buyer_test',
            'email': 'cs_buyer_test@example.com',
        })
        self.Session = self.env['unitrade.cs.session']
        # Nonaktifkan panggilan AI nyata di seluruh test ini.
        patcher = patch(
            'odoo.addons.unitrade_cs_ai.models.cs_ai_service.UnitradeCsAiService.generate_reply',
            return_value='Jawaban AI tiruan.',
        )
        self.addCleanup(patcher.stop)
        patcher.start()

    def _new_session(self):
        return self.Session.with_user(self.user).get_or_create_active()

    def test_new_session_ai_active(self):
        session = self._new_session()
        self.assertEqual(session.state, 'ai_active')
        # Ada pesan sapaan.
        self.assertTrue(session.message_ids)

    def test_get_or_create_reuses_active(self):
        s1 = self._new_session()
        s2 = self.Session.with_user(self.user).get_or_create_active()
        self.assertEqual(s1.id, s2.id)

    def test_user_message_triggers_ai(self):
        session = self._new_session()
        result = session.with_user(self.user).post_user_message('Halo')
        self.assertEqual(result['user_message'].author_type, 'user')
        self.assertTrue(result['ai_message'])
        self.assertEqual(result['ai_message'].author_type, 'ai')

    def test_escalation_sets_state_and_ticket(self):
        session = self._new_session()
        session.with_user(self.user).post_user_message('Saya ada masalah refund')
        session.with_user(self.user).escalate_to_admin()
        self.assertEqual(session.state, 'waiting_admin')
        self.assertTrue(session.ticket_id)
        self.assertTrue(session.ticket_id.ai_handled)
        self.assertTrue(session.escalated_at)

    def test_escalation_idempotent_no_duplicate_ticket(self):
        session = self._new_session()
        session.with_user(self.user).escalate_to_admin()
        ticket_id = session.ticket_id.id
        session.with_user(self.user).escalate_to_admin()
        self.assertEqual(session.ticket_id.id, ticket_id)

    def test_no_ai_when_waiting_admin(self):
        session = self._new_session()
        session.with_user(self.user).escalate_to_admin()
        with patch(
            'odoo.addons.unitrade_cs_ai.models.cs_ai_service.UnitradeCsAiService.generate_reply'
        ) as mocked:
            result = session.with_user(self.user).post_user_message('Masih menunggu')
            mocked.assert_not_called()
        self.assertFalse(result['ai_message'])

    def test_closed_session_rejects_message(self):
        session = self._new_session()
        session.close_session()
        self.assertEqual(session.state, 'closed')
        with self.assertRaises(UserError):
            session.with_user(self.user).post_user_message('Halo lagi')
