from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestKtmVerificationQueue(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Users = cls.env['res.users'].with_context(no_reset_password=True).sudo()
        cls.Verification = cls.env['unitrade.seller.verification'].sudo()
        cls.Seller = cls.env['unitrade.seller'].sudo()
        cls.admin_group = cls.env.ref('unitrade_seller.group_unitrade_admin')
        cls.base_user_group = cls.env.ref('base.group_user')
        cls.university = cls.env['unitrade.university'].sudo().search([], limit=1)
        if not cls.university:
            cls.university = cls.env['unitrade.university'].sudo().create({
                'name': 'Universitas Test Queue',
            })
        cls.admin = cls.Users.create({
            'name': 'Admin KTM Queue',
            'login': 'admin.ktm.queue@example.test',
            'email': 'admin.ktm.queue@example.test',
            'groups_id': [(6, 0, [cls.base_user_group.id, cls.admin_group.id])],
        })
        cls.stats = cls.env['unitrade.admin.stats'].with_user(cls.admin).with_context(
            unitrade_admin_user_id=cls.admin.id,
        )

    def _new_user(self, name, login):
        return self.Users.create({
            'name': name,
            'login': login,
            'email': login,
            'groups_id': [(6, 0, [self.base_user_group.id])],
        })

    def _new_verification(self, partner, nim, state='manual_review'):
        return self.Verification.create({
            'partner_id': partner.id,
            'university_id': self.university.id,
            'nim_extracted': nim,
            'nim_valid': True,
            'nim_registered': True,
            'student_name': partner.name,
            'name_match_token': 'manual_test',
            'name_confidence': 0.95,
            'confidence_flag': 'high',
            'state': state,
            'review_note': 'Regression test queue',
        })

    def test_queue_reads_verification_directly_and_flags_unmapped_rows(self):
        partner = self.env['res.partner'].sudo().create({
            'name': 'Partner Tanpa User',
            'email': 'unmapped.ktm@example.test',
        })
        verification = self._new_verification(partner, '2411509001')

        queue = self.stats.get_ktm_verification_queue(query='2411509001')
        self.assertEqual(queue['total'], 1)
        self.assertEqual(queue['rows'][0]['id'], verification.id)
        self.assertFalse(queue['rows'][0]['has_user'])
        self.assertTrue(queue['stats']['has_mismatch'])
        self.assertEqual(queue['stats']['unmapped_verifications'], 1)

    def test_approve_registers_seller_and_revoke_removes_seller_flags(self):
        user = self._new_user('Mahasiswa Queue', 'mahasiswa.queue@example.test')
        verification = self._new_verification(user.partner_id, '2411509002')

        queue = self.stats.get_ktm_verification_queue(query='2411509002')
        self.assertEqual(queue['total'], 1)
        self.assertTrue(queue['rows'][0]['has_user'])
        self.assertTrue(queue['rows'][0]['is_pending'])

        approve = self.stats.admin_approve_verification(verification.id)
        self.assertTrue(approve['ok'])

        seller = self.Seller.search([('user_id', '=', user.id)], limit=1)
        self.assertTrue(seller)
        self.assertEqual(seller.status, 'verified')
        self.assertEqual(seller.nim, '2411509002')
        self.assertTrue(user.x_is_seller)
        self.assertEqual(user.x_seller_id, seller)
        self.assertEqual(verification.state, 'approved')

        revoke = self.stats.admin_revoke_seller(seller.id, reason='Regression revoke')
        self.assertTrue(revoke['ok'])
        self.assertEqual(seller.status, 'revoked')
        self.assertFalse(user.x_is_seller)
        self.assertFalse(user.x_seller_id)
