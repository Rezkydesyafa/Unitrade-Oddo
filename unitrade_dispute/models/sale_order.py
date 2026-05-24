from urllib.parse import urlparse

from odoo import _, fields, models
from odoo.exceptions import UserError


class SaleOrderUniTradeDispute(models.Model):
    _inherit = 'sale.order'

    x_refund_dispute_id = fields.Many2one('unitrade.dispute', string='Refund Case', readonly=True, copy=False)
    x_refund_state = fields.Selection([
        ('none', 'Tidak Ada'),
        ('submitted', 'Diajukan'),
        ('under_review', 'Ditinjau'),
        ('need_buyer_evidence', 'Butuh Bukti Buyer'),
        ('need_seller_response', 'Butuh Respons Seller'),
        ('approved', 'Disetujui'),
        ('rejected', 'Ditolak'),
        ('cancelled', 'Dibatalkan'),
    ], default='none', readonly=True, copy=False)
    x_refunded_at = fields.Datetime(string='Waktu Refund', readonly=True, copy=False)

    def _unitrade_refund_disputes(self):
        self.ensure_one()
        return self.env['unitrade.dispute'].sudo().search([('order_id', '=', self.id)])

    def _unitrade_active_refund_dispute(self, ledger=False):
        self.ensure_one()
        domain = [
            ('order_id', '=', self.id),
            ('state', 'in', self.env['unitrade.dispute'].ACTIVE_STATES),
        ]
        if ledger:
            domain.append(('escrow_ledger_id', '=', ledger.id))
        return self.env['unitrade.dispute'].sudo().search(domain, order='create_date desc', limit=1)

    def _unitrade_refund_case_for_ledger(self, ledger=False):
        self.ensure_one()
        domain = [('order_id', '=', self.id)]
        if ledger:
            domain.append(('escrow_ledger_id', '=', ledger.id))
        return self.env['unitrade.dispute'].sudo().search(domain, order='create_date desc', limit=1)

    def _unitrade_direct_cancel_blocker(self):
        blocker = super()._unitrade_direct_cancel_blocker()
        if blocker:
            return blocker
        self.ensure_one()
        if self.x_escrow_state == 'disputed' or self._unitrade_active_refund_dispute():
            return _('Refund sedang diproses, pesanan tidak bisa dibatalkan langsung.')
        return False

    def _unitrade_refund_blocker(self, partner=None, ledger=False):
        self.ensure_one()
        if partner:
            self._unitrade_validate_buyer_partner(partner)
        if self.x_payment_status != 'paid':
            return _('Refund hanya tersedia setelah pembayaran berhasil.')
        if self.x_unitrade_order_state != 'processing':
            return _('Refund hanya tersedia saat pesanan masih diproses.')
        if self.x_escrow_state not in ('held', 'disputed'):
            return _('Refund tidak tersedia untuk status transaksi ini.')
        if self.state == 'cancel':
            return _('Pesanan sudah dibatalkan.')
        if ledger:
            ledger = ledger.sudo().exists()
            if not ledger or ledger.order_id.id != self.id:
                return _('Data escrow pesanan tidak valid.')
            if ledger.state in ('released', 'refunded', 'cancelled', 'releasable'):
                return _('Refund tidak tersedia untuk escrow yang sudah selesai.')
            if ledger.payout_status == 'succeeded':
                return _('Refund tidak tersedia karena payout seller sudah selesai.')
        if self._unitrade_active_refund_dispute(ledger=ledger):
            return _('Refund untuk pesanan ini sedang diproses.')
        return False

    def _unitrade_refund_requested_amount(self, ledger=False, order_line=False):
        self.ensure_one()
        if ledger:
            return ledger.currency_id.round(ledger.amount_seller or ledger.amount_total)
        if order_line:
            return self.currency_id.round(order_line.price_subtotal)
        return self.currency_id.round(self.amount_total)

    @staticmethod
    def _unitrade_is_google_drive_url(url):
        try:
            parsed = urlparse(url or '')
        except ValueError:
            return False
        host = (parsed.netloc or '').lower()
        return parsed.scheme in ('http', 'https') and (
            host == 'drive.google.com'
            or host.endswith('.drive.google.com')
            or host == 'docs.google.com'
            or host.endswith('.docs.google.com')
        )

    def action_unitrade_create_refund(
        self,
        partner=None,
        ledger=False,
        order_line=False,
        reason_code='other',
        reason_note='',
        requested_amount=False,
        evidence_items=None,
    ):
        evidence_items = evidence_items or []
        for order in self.sudo():
            blocker = order._unitrade_refund_blocker(partner=partner, ledger=ledger)
            if blocker:
                raise UserError(blocker)
            reason_note = (reason_note or '').strip()
            if len(reason_note) < 20:
                raise UserError(_('Catatan pengembalian minimal 20 karakter.'))
            if not evidence_items:
                raise UserError(_('Minimal upload 1 foto bukti pengembalian.'))
            has_photo = any(
                item.get('evidence_type') == 'buyer_photo' and (item.get('datas') or item.get('attachment_id'))
                for item in evidence_items
            )
            if not has_photo:
                raise UserError(_('Minimal upload 1 foto bukti pengembalian.'))
            drive_urls = [
                item.get('url')
                for item in evidence_items
                if item.get('evidence_type') == 'google_drive_url' and item.get('url')
            ]
            if any(url and not self._unitrade_is_google_drive_url(url) for url in drive_urls):
                raise UserError(_('Link Google Drive harus menggunakan domain drive.google.com atau docs.google.com.'))

            ledger = ledger.sudo() if ledger else order._unitrade_escrow_ledgers()[:1]
            amount = requested_amount or order._unitrade_refund_requested_amount(ledger=ledger, order_line=order_line)
            dispute = self.env['unitrade.dispute'].sudo().create({
                'dispute_type': 'refund',
                'state': 'draft',
                'order_id': order.id,
                'order_line_id': order_line.id if order_line else False,
                'payment_intent_id': order.x_payment_intent_id.id if order.x_payment_intent_id else False,
                'escrow_ledger_id': ledger.id if ledger else False,
                'buyer_id': order.partner_id.id,
                'seller_id': ledger.seller_id.id if ledger and ledger.seller_id else False,
                'reason_code': reason_code,
                'reason_note': reason_note,
                'requested_amount': amount,
                'currency_id': order.currency_id.id,
            })
            for item in evidence_items:
                attachment_id = item.get('attachment_id') or False
                if not attachment_id and item.get('datas'):
                    attachment = self.env['ir.attachment'].sudo().create({
                        'name': item.get('name') or 'bukti-pengembalian',
                        'datas': item.get('datas'),
                        'mimetype': item.get('mimetype') or False,
                        'res_model': 'unitrade.dispute',
                        'res_id': dispute.id,
                    })
                    attachment_id = attachment.id
                self.env['unitrade.dispute.evidence'].sudo().create({
                    'dispute_id': dispute.id,
                    'submitted_by_id': item.get('submitted_by_id') or self.env.user.id,
                    'evidence_type': item.get('evidence_type') or 'other',
                    'attachment_id': attachment_id,
                    'url': item.get('url') or False,
                    'note': item.get('note') or False,
                })
            dispute.action_submit()
        return dispute
