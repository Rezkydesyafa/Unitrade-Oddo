import base64
import logging
from urllib.parse import quote, urlparse

from odoo import _, http
from odoo.exceptions import UserError
from odoo.http import Stream, request

_logger = logging.getLogger(__name__)


class UnitradeDisputeController(http.Controller):
    PHOTO_MAX_FILES = 3
    PHOTO_MAX_BYTES = 2 * 1024 * 1024
    VIDEO_MAX_BYTES = 10 * 1024 * 1024
    PHOTO_MIMETYPES = {'image/jpeg', 'image/png', 'image/webp'}
    VIDEO_MIMETYPES = {'video/mp4', 'video/webm'}

    @staticmethod
    def _format_money(amount, currency):
        symbol = currency.symbol or 'Rp'
        formatted = ('{:,.0f}'.format(amount or 0.0)).replace(',', '.')
        if currency.position == 'after':
            return '%s %s' % (formatted, symbol)
        return '%s %s' % (symbol, formatted)

    def _append_error(self, url, key, message):
        separator = '&' if '?' in url else '?'
        return '%s%s%s=%s' % (url, separator, key, quote(message or ''))

    def _refund_create_url(self, order_id, ledger_id=False, line_id=False):
        params = []
        if ledger_id:
            params.append('ledger_id=%s' % ledger_id)
        if line_id:
            params.append('order_line_id=%s' % line_id)
        suffix = ('?' + '&'.join(params)) if params else ''
        return '/unitrade/order/%s/refund/new%s' % (order_id, suffix)

    def _max_upload_bytes(self):
        raw = request.env['ir.config_parameter'].sudo().get_param('unitrade.refund.max_upload_mb', '25')
        try:
            megabytes = int(raw)
        except (TypeError, ValueError):
            megabytes = 25
        return max(1, min(megabytes, 100)) * 1024 * 1024

    @staticmethod
    def _is_google_drive_url(url):
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

    def _uploaded_evidence(self, field_name, evidence_type, max_files=False, max_bytes=False, allowed_mimetypes=False):
        evidence = []
        files = request.httprequest.files.getlist(field_name)
        if not files:
            return evidence
        uploads = [upload for upload in files if upload and (upload.filename or '')]
        if max_files and len(uploads) > max_files:
            raise UserError(_('Maksimal upload %s file untuk bukti pengembalian ini.') % max_files)
        limit_bytes = max_bytes or self._max_upload_bytes()
        for upload in files:
            filename = upload.filename or ''
            if not filename:
                continue
            mimetype = upload.mimetype or ''
            if allowed_mimetypes and mimetype not in allowed_mimetypes:
                raise UserError(_('Format file %s belum didukung.') % filename)
            payload = upload.read()
            if not payload:
                continue
            if len(payload) > limit_bytes:
                if evidence_type == 'buyer_photo':
                    raise UserError(_('Foto bukti %s melebihi 2 MB. Maksimal 3 foto, 2 MB per foto.') % filename)
                if evidence_type == 'unboxing_video':
                    raise UserError(_('Video unboxing %s melebihi 10 MB. Upload ke Google Drive lalu isi link Google Drive.') % filename)
                raise UserError(_('Ukuran file %s melebihi batas upload pengembalian.') % filename)
            evidence.append({
                'evidence_type': evidence_type,
                'name': filename,
                'mimetype': mimetype or False,
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

    @staticmethod
    def _can_view_order(order):
        partner = request.env.user.partner_id.commercial_partner_id
        return order.partner_id.commercial_partner_id.id == partner.id

    def _refund_context_records(self, order, kwargs):
        ledger = False
        ledger_id = int(kwargs.get('ledger_id') or 0)
        if ledger_id and 'unitrade.escrow.ledger' in request.env.registry:
            ledger = request.env['unitrade.escrow.ledger'].sudo().browse(ledger_id).exists()
            if not ledger or ledger.order_id.id != order.id:
                ledger = False

        line = False
        line_id = int(kwargs.get('order_line_id') or 0)
        if line_id:
            line = request.env['sale.order.line'].sudo().browse(line_id).exists()
            if not line or line.order_id.id != order.id:
                line = False
        if not line:
            line = order.order_line.filtered(lambda order_line: not order_line.display_type and order_line.product_id)[:1]
        return ledger, line

    @http.route('/unitrade/order/<int:order_id>/refund/new', type='http', auth='user', website=True, methods=['GET'], sitemap=False)
    def buyer_refund_create_page(self, order_id, **kwargs):
        order = request.env['sale.order'].sudo().browse(order_id).exists()
        if not order or not self._can_view_order(order):
            return request.not_found()

        ledger, line = self._refund_context_records(order, kwargs)
        active_refund = order._unitrade_active_refund_dispute(ledger=ledger) if hasattr(order, '_unitrade_active_refund_dispute') else False
        if active_refund:
            return request.redirect('/unitrade/order/%s/refund/%s' % (order.id, active_refund.id))

        blocker = order._unitrade_refund_blocker(partner=request.env.user.partner_id, ledger=ledger) if hasattr(order, '_unitrade_refund_blocker') else False
        if blocker:
            return request.redirect(self._append_error('/my/orders', 'refund_error', str(blocker)))

        product = line.product_id.product_tmpl_id if line and line.product_id else False
        seller = ledger.seller_id if ledger and ledger.seller_id else False
        if not seller and product and 'x_seller_id' in product._fields:
            seller = product.x_seller_id
        amount = order._unitrade_refund_requested_amount(ledger=ledger, order_line=line) if hasattr(order, '_unitrade_refund_requested_amount') else (line.price_subtotal if line else order.amount_total)
        return request.render('unitrade_dispute.unitrade_refund_create', {
            'order': order,
            'ledger': ledger,
            'order_line': line,
            'product_name': product.display_name if product else order.name,
            'seller_name': seller.name if seller else (order.user_id.name or 'Penjual UniTrade'),
            'refund_amount': self._format_money(amount, order.currency_id),
        })

    @http.route('/unitrade/order/<int:order_id>/refund', type='http', auth='user', website=True, methods=['POST'], csrf=True, sitemap=False)
    def buyer_create_refund(self, order_id, **kwargs):
        order = request.env['sale.order'].sudo().browse(order_id).exists()
        if not order:
            return request.not_found()

        ledger_id = int(kwargs.get('ledger_id') or 0)
        line_id = int(kwargs.get('order_line_id') or 0)
        redirect_url = self._refund_create_url(order.id, ledger_id=ledger_id, line_id=line_id)
        try:
            ledger = False
            if ledger_id:
                ledger = request.env['unitrade.escrow.ledger'].sudo().browse(ledger_id).exists()
            line = False
            if line_id:
                line = request.env['sale.order.line'].sudo().browse(line_id).exists()
                if not line or line.order_id.id != order.id:
                    line = False

            evidence_items = []
            photo_items = self._uploaded_evidence(
                'refund_evidence',
                'buyer_photo',
                max_files=self.PHOTO_MAX_FILES,
                max_bytes=self.PHOTO_MAX_BYTES,
                allowed_mimetypes=self.PHOTO_MIMETYPES,
            )
            if not photo_items:
                raise UserError(_('Minimal upload 1 foto bukti pengembalian.'))
            evidence_items.extend(photo_items)
            unboxing_items = self._uploaded_evidence(
                'unboxing_video',
                'unboxing_video',
                max_files=1,
                max_bytes=self.VIDEO_MAX_BYTES,
                allowed_mimetypes=self.VIDEO_MIMETYPES,
            )
            evidence_items.extend(unboxing_items)

            drive_url = (kwargs.get('google_drive_url') or '').strip()
            if drive_url:
                if not self._is_google_drive_url(drive_url):
                    raise UserError(_('Link Google Drive harus menggunakan domain drive.google.com atau docs.google.com.'))
                evidence_items.append({
                    'evidence_type': 'google_drive_url',
                    'url': drive_url,
                    'note': _('Bukti tambahan melalui Google Drive.'),
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
        filename = (attachment.name or 'bukti-pengembalian').replace('"', '')
        headers = [
            ('Content-Type', attachment.mimetype or 'application/octet-stream'),
            ('Content-Disposition', 'attachment; filename="%s"' % filename),
        ]
        return request.make_response(payload, headers=headers)

    @http.route('/unitrade/refund/evidence/<int:evidence_id>/image', type='http', auth='user', website=True, methods=['GET'], sitemap=False)
    def refund_evidence_image(self, evidence_id, **kwargs):
        evidence = request.env['unitrade.dispute.evidence'].sudo().browse(evidence_id).exists()
        if not evidence or not evidence.attachment_id or not self._can_view_dispute(evidence.dispute_id):
            return request.not_found()
        attachment = evidence.attachment_id.sudo()
        if (attachment.mimetype or '') not in self.PHOTO_MIMETYPES:
            return request.not_found()
        return Stream.from_attachment(attachment).get_response(as_attachment=False)

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
