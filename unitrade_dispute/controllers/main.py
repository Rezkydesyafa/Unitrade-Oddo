import base64
import logging
from urllib.parse import quote

from odoo import _, http
from odoo.exceptions import UserError
from odoo.http import request

_logger = logging.getLogger(__name__)


class UnitradeDisputeController(http.Controller):

    def _append_error(self, url, key, message):
        separator = '&' if '?' in url else '?'
        return '%s%s%s=%s' % (url, separator, key, quote(message or ''))

    def _max_upload_bytes(self):
        raw = request.env['ir.config_parameter'].sudo().get_param('unitrade.refund.max_upload_mb', '25')
        try:
            megabytes = int(raw)
        except (TypeError, ValueError):
            megabytes = 25
        return max(1, min(megabytes, 100)) * 1024 * 1024

    def _uploaded_evidence(self, field_name, evidence_type):
        evidence = []
        files = request.httprequest.files.getlist(field_name)
        if not files:
            return evidence
        max_bytes = self._max_upload_bytes()
        for upload in files:
            filename = upload.filename or ''
            if not filename:
                continue
            payload = upload.read()
            if not payload:
                continue
            if len(payload) > max_bytes:
                raise UserError(_('Ukuran file %s melebihi batas upload refund.') % filename)
            evidence.append({
                'evidence_type': evidence_type,
                'name': filename,
                'mimetype': upload.mimetype or False,
                'datas': base64.b64encode(payload).decode('ascii'),
                'submitted_by_id': request.env.user.id,
            })
        return evidence

    def _current_seller(self):
        if 'unitrade.seller' not in request.env.registry:
            return request.env['sale.order'].browse()
        return request.env['unitrade.seller'].sudo().search([
            ('user_id', '=', request.env.user.id),
            ('status', '=', 'verified'),
        ], limit=1)

    def _can_view_dispute(self, dispute):
        user = request.env.user
        if user.has_group('sales_team.group_sale_manager') or user.has_group('base.group_system'):
            return True
        partner = user.partner_id.commercial_partner_id
        if dispute.order_id.partner_id.commercial_partner_id == partner:
            return True
        seller = self._current_seller()
        return bool(seller and dispute.seller_id and dispute.seller_id.id == seller.id)

    @http.route('/unitrade/order/<int:order_id>/refund', type='http', auth='user', website=True, methods=['POST'], csrf=True, sitemap=False)
    def buyer_create_refund(self, order_id, **kwargs):
        order = request.env['sale.order'].sudo().browse(order_id).exists()
        if not order:
            return request.not_found()

        redirect_url = '/my/orders'
        try:
            ledger = False
            ledger_id = int(kwargs.get('ledger_id') or 0)
            if ledger_id:
                ledger = request.env['unitrade.escrow.ledger'].sudo().browse(ledger_id).exists()
            line = False
            line_id = int(kwargs.get('order_line_id') or 0)
            if line_id:
                line = request.env['sale.order.line'].sudo().browse(line_id).exists()
                if not line or line.order_id.id != order.id:
                    line = False

            evidence_items = []
            evidence_items.extend(self._uploaded_evidence('refund_evidence', 'buyer_photo'))
            evidence_items.extend(self._uploaded_evidence('unboxing_video', 'unboxing_video'))

            drive_url = (kwargs.get('google_drive_url') or '').strip()
            if drive_url:
                evidence_items.append({
                    'evidence_type': 'google_drive_url',
                    'url': drive_url,
                    'submitted_by_id': request.env.user.id,
                })

            dispute = order.action_unitrade_create_refund(
                partner=request.env.user.partner_id,
                ledger=ledger,
                order_line=line,
                reason_code=kwargs.get('reason_code') or 'other',
                reason_note=kwargs.get('reason_note') or '',
                evidence_items=evidence_items,
            )
            _logger.info('Buyer %s created refund dispute %s for order %s', request.env.user.id, dispute.name, order.name)
            return request.redirect('/unitrade/order/%s/refund/%s?refund=submitted' % (order.id, dispute.id))
        except UserError as error:
            message = error.args[0] if error.args else str(error)
            return request.redirect(self._append_error(redirect_url, 'refund_error', message))

    @http.route('/unitrade/order/<int:order_id>/refund/<int:dispute_id>', type='http', auth='user', website=True, methods=['GET'], sitemap=False)
    def buyer_refund_detail(self, order_id, dispute_id, **kwargs):
        dispute = request.env['unitrade.dispute'].sudo().browse(dispute_id).exists()
        if not dispute or dispute.order_id.id != order_id:
            return request.not_found()
        if not self._can_view_dispute(dispute):
            return request.not_found()
        return request.render('unitrade_dispute.unitrade_refund_detail', {
            'dispute': dispute,
            'order': dispute.order_id,
            'payment_intent': dispute.payment_intent_id or dispute.order_id.x_payment_intent_id,
            'is_seller_view': bool(self._current_seller() and dispute.seller_id and dispute.seller_id.id == self._current_seller().id),
        })

    @http.route('/unitrade/refund/evidence/<int:evidence_id>/download', type='http', auth='user', website=True, methods=['GET'], sitemap=False)
    def refund_evidence_download(self, evidence_id, **kwargs):
        evidence = request.env['unitrade.dispute.evidence'].sudo().browse(evidence_id).exists()
        if not evidence or not evidence.attachment_id or not self._can_view_dispute(evidence.dispute_id):
            return request.not_found()
        attachment = evidence.attachment_id.sudo()
        payload = base64.b64decode(attachment.datas or b'')
        filename = (attachment.name or 'bukti-refund').replace('"', '')
        headers = [
            ('Content-Type', attachment.mimetype or 'application/octet-stream'),
            ('Content-Disposition', 'attachment; filename="%s"' % filename),
        ]
        return request.make_response(payload, headers=headers)

    @http.route('/seller/refund/<int:dispute_id>/respond', type='http', auth='user', website=True, methods=['POST'], csrf=True, sitemap=False)
    def seller_refund_respond(self, dispute_id, **kwargs):
        dispute = request.env['unitrade.dispute'].sudo().browse(dispute_id).exists()
        seller = self._current_seller()
        if not dispute or not seller or not dispute.seller_id or dispute.seller_id.id != seller.id:
            return request.not_found()
        try:
            evidence_items = self._uploaded_evidence('seller_refund_evidence', 'seller_response')
            dispute.with_user(request.env.user).action_seller_respond(
                note=(kwargs.get('seller_response_note') or '').strip(),
                evidence_items=evidence_items,
            )
            return request.redirect('/seller/dashboard?refund_response=1#dashboard-orders')
        except UserError as error:
            message = error.args[0] if error.args else str(error)
            return request.redirect('/seller/dashboard?seller_error=%s#dashboard-orders' % quote(message))
