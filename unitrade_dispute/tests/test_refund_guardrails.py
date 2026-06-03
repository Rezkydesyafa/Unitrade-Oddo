import base64

from odoo.exceptions import UserError
from odoo import fields
from odoo.tests.common import TransactionCase, tagged, new_test_user


TINY_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


@tagged("standard", "at_install")
class TestRefundGuardrails(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].sudo().create({
            "name": "Buyer Refund Test",
            "email": "buyer-refund@test.local",
        })
        cls.admin_user = cls.env.ref("base.user_admin")
        cls.seller_user = new_test_user(cls.env, login="refund_seller_user", groups="base.group_portal")
        cls.seller = cls.env["unitrade.seller"].sudo().create({
            "user_id": cls.seller_user.id,
            "nim": "12345678",
            "status": "verified",
        })
        cls.order = cls.env["sale.order"].sudo().create({
            "partner_id": cls.partner.id,
            "partner_invoice_id": cls.partner.id,
            "partner_shipping_id": cls.partner.id,
        })
        cls.dispute_base_vals = {
            "order_id": cls.order.id,
            "buyer_id": cls.partner.id,
            "seller_id": cls.seller.id,
            "reason_code": "not_as_described",
            "reason_note": "Barang tidak sesuai dengan deskripsi.",
            "requested_amount": 125000.0,
            "currency_id": cls.order.currency_id.id,
            "dispute_type": "refund",
        }

    def _create_dispute(self, **extra):
        vals = dict(self.dispute_base_vals)
        vals.update(extra)
        return self.env["unitrade.dispute"].sudo().create(vals)

    def _add_evidence(self, dispute, evidence_type):
        attachment = self.env["ir.attachment"].sudo().create({
            "name": "%s.png" % evidence_type,
            "datas": base64.b64encode(base64.b64decode(TINY_PNG)).decode(),
            "mimetype": "image/png",
            "res_model": "unitrade.dispute",
            "res_id": dispute.id,
        })
        return self.env["unitrade.dispute.evidence"].sudo().create({
            "dispute_id": dispute.id,
            "submitted_by_id": self.admin_user.id,
            "evidence_type": evidence_type,
            "attachment_id": attachment.id,
        })

    def test_admin_cannot_approve_before_final_admin_state(self):
        dispute = self._create_dispute(state="under_review", admin_decision_note="Catatan admin sudah cukup panjang.")
        with self.assertRaises(UserError):
            dispute.with_user(self.admin_user).action_approve_refund()

    def test_admin_note_minimum_length_required(self):
        dispute = self._create_dispute(state="admin_review_final", admin_decision_note="pendek")
        with self.assertRaises(UserError):
            dispute.with_user(self.admin_user).action_reject_refund()

    def test_admin_final_approval_requires_buyer_and_seller_return_evidence(self):
        dispute = self._create_dispute(state="admin_review_final", admin_decision_note="Catatan admin final valid.")
        self._add_evidence(dispute, "buyer_return_photo")
        with self.assertRaises(UserError):
            dispute.with_user(self.admin_user).action_approve_refund()

    def test_admin_final_approval_writes_audit_snapshot(self):
        dispute = self._create_dispute(state="admin_review_final", admin_decision_note="Catatan admin final valid untuk approve.")
        self._add_evidence(dispute, "buyer_return_photo")
        self._add_evidence(dispute, "seller_return_photo")
        dispute.with_user(self.admin_user).action_approve_refund()
        dispute.invalidate_recordset([
            "state",
            "final_decision_user_id",
            "final_decision_role",
            "final_decision_at",
            "final_decision_snapshot",
        ])
        self.assertEqual(dispute.state, "approved")
        self.assertEqual(dispute.final_decision_user_id, self.admin_user)
        self.assertEqual(dispute.final_decision_role, "admin")
        self.assertTrue(dispute.final_decision_at)
        self.assertIn('"decision": "approve"', dispute.final_decision_snapshot or "")

    def test_seller_reject_routes_to_admin_final_review(self):
        dispute = self._create_dispute(state="submitted")
        dispute.with_user(self.seller_user).action_seller_reject_refund(
            note="Seller tidak setuju karena bukti tidak lengkap."
        )
        dispute.invalidate_recordset(["state", "seller_decision_user_id", "seller_decision_note"])
        self.assertEqual(dispute.state, "admin_review_final")
        self.assertEqual(dispute.seller_decision_user_id, self.seller_user)
        self.assertTrue(dispute.seller_decision_note)
        self.assertEqual(dispute.order_id.x_refund_state, "admin_review_final")

    def test_seller_can_reject_after_buyer_return_evidence(self):
        dispute = self._create_dispute(
            state="need_seller_response",
            seller_decision_user_id=self.seller_user.id,
            seller_decided_at=fields.Datetime.now(),
            seller_decision_note="Seller awalnya menyetujui pengembalian.",
        )
        self._add_evidence(dispute, "buyer_return_photo")
        dispute.with_user(self.seller_user).action_seller_reject_refund(
            note="Barang yang dikembalikan tidak sesuai dengan bukti pembeli."
        )
        dispute.invalidate_recordset(["state", "seller_decision_note"])
        self.assertEqual(dispute.state, "admin_review_final")
        self.assertEqual(
            dispute.seller_decision_note,
            "Barang yang dikembalikan tidak sesuai dengan bukti pembeli.",
        )
        self.assertEqual(dispute.order_id.x_refund_state, "admin_review_final")
