import base64
import logging
from urllib.parse import quote, urlparse

from odoo import _, fields, http
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

    def _marketplace_block_message(self, feature_label):
        user = request.env.user
        if user._is_public() or not hasattr(user, '_check_unitrade_marketplace_access'):
            return ''
        try:
            user._check_unitrade_marketplace_access(feature_label)
        except UserError as error:
            return error.args[0] if error.args else str(error)
        return ''

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

    @staticmethod
    def _refund_state_label(state):
        return {
            'draft': 'Draft',
            'submitted': 'Pengajuan dikirim',
            'under_review': 'Ditinjau admin/seller',
            'need_buyer_evidence': 'Menunggu barang dikembalikan',
            'need_seller_response': 'Menunggu konfirmasi seller',
            'admin_review_final': 'Menunggu keputusan final admin',
            'approved': 'Pengembalian disetujui',
            'rejected': 'Pengembalian ditolak',
            'resolved': 'Pengembalian selesai',
            'cancelled': 'Pengembalian dibatalkan',
        }.get(state or '', state or '-')

    @staticmethod
    def _refund_state_key(state):
        if state in ('approved', 'resolved'):
            return 'success'
        if state in ('rejected', 'cancelled'):
            return 'danger'
        if state in ('need_buyer_evidence', 'need_seller_response'):
            return 'warning'
        return 'review'

    def _refund_status_notice(self, dispute):
        state = dispute.state
        has_seller_return_confirmation = bool(dispute.evidence_ids.filtered(
            lambda evidence: evidence.evidence_type == 'seller_return_photo' and evidence.attachment_id
        ))
        if state == 'admin_review_final' and dispute.seller_decision_note and not has_seller_return_confirmation:
            return {
                'title': 'Seller menolak pengembalian',
                'body': 'Seller tidak menyetujui pengembalian. Customer Service/admin akan menjadi mediator dan meninjau bukti dari kedua pihak.',
                'tone': 'review',
            }
        if state == 'admin_review_final' and has_seller_return_confirmation:
            return {
                'title': 'Menunggu review final admin',
                'body': 'Seller sudah mengonfirmasi barang kembali. Admin/Customer Service harus meninjau bukti sebelum dana dikembalikan.',
                'tone': 'review',
            }
        if state in ('submitted', 'under_review'):
            return {
                'title': 'Pengembalian sedang diproses',
                'body': 'Pengajuan Anda sudah masuk. Seller dan admin/Customer Service sedang meninjau bukti, deskripsi masalah, dan link video unboxing.',
                'tone': 'review',
            }
        if state == 'need_buyer_evidence':
            return {
                'title': 'Kirim barang kembali ke seller',
                'body': 'Seller menyetujui pengembalian. Kirim atau serahkan barang kembali ke seller, lalu upload foto bukti pengembalian di halaman ini.',
                'tone': 'warning',
            }
        if state == 'need_seller_response':
            return {
                'title': 'Menunggu konfirmasi seller',
                'body': 'Bukti pengembalian barang sudah dikirim. Seller perlu mengonfirmasi penerimaan barang dengan bukti foto sebelum dana dikembalikan.',
                'tone': 'warning',
            }
        if state in ('approved', 'resolved'):
            return {
                'title': 'Pengembalian disetujui',
                'body': 'Barang kembali sudah dikonfirmasi. Dana dikembalikan sesuai hasil peninjauan dan kebijakan UniTrade.',
                'tone': 'success',
            }
        if state == 'rejected':
            return {
                'title': 'Pengembalian ditolak',
                'body': dispute.seller_decision_note or dispute.admin_decision_note or 'Pengajuan tidak disetujui berdasarkan hasil peninjauan.',
                'tone': 'danger',
            }
        return {
            'title': self._refund_state_label(state),
            'body': 'Seluruh proses pengembalian tercatat dan dapat dipantau oleh pembeli, seller, dan admin.',
            'tone': self._refund_state_key(state),
        }

    def _refund_progress_steps(self, dispute):
        state = dispute.state
        final_success = state in ('approved', 'resolved')
        final_failed = state in ('rejected', 'cancelled')
        review_active = state in ('submitted', 'under_review')
        buyer_evidence_active = state == 'need_buyer_evidence'
        seller_confirm_active = state == 'need_seller_response'
        timeline_by_key = {item.event_key: item for item in dispute.timeline_ids}
        has_buyer_return = bool(
            timeline_by_key.get('buyer_return_sent')
            or dispute.evidence_ids.filtered(lambda evidence: evidence.evidence_type == 'buyer_return_photo')
        )
        has_seller_confirmation = bool(
            timeline_by_key.get('seller_return_confirmed')
            or dispute.evidence_ids.filtered(lambda evidence: evidence.evidence_type == 'seller_return_photo')
        )
        seller_rejected = state == 'admin_review_final' and bool(dispute.seller_decision_note) and not has_seller_confirmation
        admin_final_active = state == 'admin_review_final' and bool(
            has_seller_confirmation or seller_rejected
        )

        def step(key, label, caption, status='pending'):
            status_labels = {
                'done': 'Completed',
                'current': 'In Progress',
                'pending': 'Pending',
                'failed': 'Failed',
            }
            return {
                'key': key,
                'label': label,
                'caption': caption,
                'status': status,
                'status_label': status_labels.get(status, status),
            }

        review_done = (
            final_success
            or final_failed
            or state in ('need_buyer_evidence', 'need_seller_response', 'admin_review_final')
            or bool(dispute.seller_decision_note)
            or has_buyer_return
            or has_seller_confirmation
        )
        review_status = 'done' if review_done else 'current' if review_active else 'pending'
        if final_failed:
            review_status = 'done' if (dispute.seller_decision_note or has_buyer_return or has_seller_confirmation) else 'failed'
        admin_final_status = 'done' if final_success else 'failed' if final_failed else 'current' if admin_final_active else 'pending'

        return [
            step(
                'submitted',
                'Pengajuan dikirim',
                'Deskripsi masalah, foto bukti, dan link video unboxing diterima.',
                'done' if dispute.submitted_at or dispute.create_date else 'current',
            ),
            step(
                'review',
                'Review admin/seller',
                'Admin/CS dan seller meninjau bukti pengembalian.',
                review_status,
            ),
            step(
                'return_item',
                'Pengembalian barang',
                'Jika disetujui, pembeli mengirimkan atau menyerahkan barang kembali ke seller.',
                'current' if buyer_evidence_active else 'done' if has_buyer_return or seller_confirm_active or final_success else 'pending',
            ),
            step(
                'seller_confirm',
                'Konfirmasi seller',
                'Seller mengonfirmasi barang kembali dengan bukti foto.',
                'failed' if seller_rejected else 'current' if seller_confirm_active else 'done' if has_seller_confirmation or final_success else 'pending',
            ),
            step(
                'admin_final',
                'Review final admin',
                'Admin/CS wajib meninjau sebelum dana dikembalikan.',
                admin_final_status,
            ),
            step(
                'refund',
                'Dana dikembalikan',
                'Dana dikembalikan ke saldo pembeli setelah proses valid.',
                'done' if final_success else 'failed' if final_failed else 'pending',
            ),
        ]

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
                if evidence_type in ('buyer_photo', 'buyer_return_photo', 'seller_return_photo'):
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

    def _create_dispute_evidence(self, dispute, evidence_items, default_note=False):
        Evidence = request.env['unitrade.dispute.evidence'].sudo()
        Attachment = request.env['ir.attachment'].sudo()
        for item in evidence_items or []:
            attachment_id = item.get('attachment_id') or False
            if not attachment_id and item.get('datas'):
                attachment = Attachment.create({
                    'name': item.get('name') or 'bukti-pengembalian',
                    'datas': item.get('datas'),
                    'mimetype': item.get('mimetype') or False,
                    'res_model': 'unitrade.dispute',
                    'res_id': dispute.id,
                })
                attachment_id = attachment.id
            Evidence.create({
                'dispute_id': dispute.id,
                'submitted_by_id': item.get('submitted_by_id') or request.env.user.id,
                'evidence_type': item.get('evidence_type') or 'other',
                'attachment_id': attachment_id,
                'url': item.get('url') or False,
                'note': item.get('note') or default_note or False,
            })

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

    def _buyer_can_submit_return_evidence(self, dispute):
        partner = request.env.user.partner_id.commercial_partner_id
        return (
            dispute.state == 'need_buyer_evidence'
            and dispute.order_id.partner_id.commercial_partner_id.id == partner.id
        )

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
        block_message = self._marketplace_block_message(_('mengajukan refund'))
        if block_message:
            return request.redirect(self._append_error('/my/orders', 'refund_error', block_message))

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
            block_message = self._marketplace_block_message(_('mengajukan refund'))
            if block_message:
                raise UserError(block_message)

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
            if not drive_url:
                raise UserError(_('Link Google Drive video unboxing wajib diisi.'))
            if not self._is_google_drive_url(drive_url):
                raise UserError(_('Link Google Drive harus menggunakan domain drive.google.com atau docs.google.com.'))
            evidence_items.append({
                'evidence_type': 'google_drive_url',
                'url': drive_url,
                'note': _('Video unboxing melalui Google Drive.'),
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
        can_submit_return_evidence = self._buyer_can_submit_return_evidence(dispute)
        return request.render('unitrade_dispute.unitrade_refund_detail', {
            'dispute': dispute,
            'order': dispute.order_id,
            'payment_intent': dispute.payment_intent_id or dispute.order_id.x_payment_intent_id,
            'is_seller_view': bool(self._current_seller() and dispute.seller_id and dispute.seller_id.id == self._current_seller().id),
            'refund_state_label': self._refund_state_label(dispute.state),
            'refund_state_key': self._refund_state_key(dispute.state),
            'refund_status_notice': self._refund_status_notice(dispute),
            'refund_progress_steps': self._refund_progress_steps(dispute),
            'can_submit_return_evidence': can_submit_return_evidence,
            'return_evidence_url': '/unitrade/order/%s/refund/%s/return-evidence' % (dispute.order_id.id, dispute.id),
        })

    @http.route('/unitrade/order/<int:order_id>/refund/<int:dispute_id>/return-evidence', type='http', auth='user', website=True, methods=['POST'], csrf=True, sitemap=False)
    def buyer_refund_return_evidence(self, order_id, dispute_id, **kwargs):
        dispute = request.env['unitrade.dispute'].sudo().browse(dispute_id).exists()
        if not dispute or dispute.order_id.id != order_id or not self._buyer_can_submit_return_evidence(dispute):
            return request.not_found()
        redirect_url = '/unitrade/order/%s/refund/%s' % (order_id, dispute_id)
        try:
            evidence_items = self._uploaded_evidence(
                'return_evidence',
                'buyer_return_photo',
                max_files=self.PHOTO_MAX_FILES,
                max_bytes=self.PHOTO_MAX_BYTES,
                allowed_mimetypes=self.PHOTO_MIMETYPES,
            )
            if not evidence_items:
                raise UserError(_('Minimal upload 1 foto bukti barang dikembalikan.'))
            note = (kwargs.get('return_note') or '').strip()
            default_note = note or _('Bukti barang dikembalikan oleh pembeli.')
            for item in evidence_items:
                item['note'] = default_note
            with request.env.cr.savepoint():
                self._create_dispute_evidence(dispute, evidence_items, default_note=default_note)
                now = fields.Datetime.now()
                dispute.sudo().write({
                    'state': 'need_seller_response',
                    'review_started_at': dispute.review_started_at or now,
                })
                dispute.sudo()._record_timeline_event(
                    'buyer_return_sent',
                    note=default_note,
                    event_time=now,
                )
                dispute.sudo()._set_order_refund_state('need_seller_response')
            return request.redirect('%s?return_evidence=submitted' % redirect_url)
        except UserError as error:
            message = error.args[0] if error.args else str(error)
            return request.redirect(self._append_error(redirect_url, 'refund_error', message))

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

    @http.route([
        '/seller/refund/<int:dispute_id>/confirm-return',
        '/unitrade/seller/refund/<int:dispute_id>/confirm-return',
    ], type='http', auth='user', website=True, methods=['POST'], csrf=True, sitemap=False)
    def seller_refund_confirm_return(self, dispute_id, **kwargs):
        dispute = request.env['unitrade.dispute'].sudo().browse(dispute_id).exists()
        seller = self._current_seller()
        if not dispute or not seller or not dispute.seller_id or dispute.seller_id.id != seller.id:
            return request.not_found()
        redirect_url = '/unitrade/seller/refunds/%s' % dispute.id
        try:
            if dispute.state != 'need_seller_response':
                raise UserError(_('Konfirmasi barang kembali hanya tersedia setelah pembeli mengirim bukti pengembalian.'))
            evidence_items = self._uploaded_evidence(
                'seller_return_evidence',
                'seller_return_photo',
                max_files=self.PHOTO_MAX_FILES,
                max_bytes=self.PHOTO_MAX_BYTES,
                allowed_mimetypes=self.PHOTO_MIMETYPES,
            )
            if not evidence_items:
                raise UserError(_('Minimal upload 1 foto bukti barang sudah diterima kembali.'))
            note = (kwargs.get('seller_return_note') or '').strip()
            default_note = note or _('Seller mengonfirmasi barang sudah diterima kembali.')
            for item in evidence_items:
                item['note'] = default_note
            with request.env.cr.savepoint():
                self._create_dispute_evidence(dispute, evidence_items, default_note=default_note)
                dispute.sudo()._record_timeline_event(
                    'seller_return_confirmed',
                    note=default_note,
                    event_time=fields.Datetime.now(),
                )
                dispute.with_user(request.env.user).action_seller_approve_refund(note=note)
            return request.redirect('%s?return_confirmed=1' % redirect_url)
        except UserError as error:
            message = error.args[0] if error.args else str(error)
            return request.redirect('%s?seller_error=%s' % (redirect_url, quote(message)))

    @http.route('/seller/refund/<int:dispute_id>/respond', type='http', auth='user', website=True, methods=['POST'], csrf=True, sitemap=False)
    def seller_refund_respond(self, dispute_id, **kwargs):
        dispute = request.env['unitrade.dispute'].sudo().browse(dispute_id).exists()
        seller = self._current_seller()
        if not dispute or not seller or not dispute.seller_id or dispute.seller_id.id != seller.id:
            return request.not_found()
        try:
            block_message = self._marketplace_block_message(_('merespons refund sebagai seller'))
            if block_message:
                raise UserError(block_message)

            if dispute.state == 'need_seller_response':
                raise UserError(_('Gunakan form konfirmasi barang kembali untuk menyelesaikan refund ini.'))
            evidence_items = self._uploaded_evidence('seller_refund_evidence', 'seller_response')
            dispute.with_user(request.env.user).action_seller_respond(
                note=(kwargs.get('seller_response_note') or '').strip(),
                evidence_items=evidence_items,
            )
            return request.redirect('/seller/dashboard?refund_response=1#dashboard-orders')
        except UserError as error:
            message = error.args[0] if error.args else str(error)
            return request.redirect('/seller/dashboard?seller_error=%s#dashboard-orders' % quote(message))
