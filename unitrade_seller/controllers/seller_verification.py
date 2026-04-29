# -*- coding: utf-8 -*-
from odoo import http, fields
from odoo.http import request
import logging
import json
import base64
import os

_logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


class SellerVerificationController(http.Controller):
    """Controller for seller KTM verification flow."""

    @http.route('/seller-verification', type='http', auth='user', website=True, sitemap=False)
    def seller_verification_page(self, **kw):
        """
        GET /seller-verification
        Render the seller verification page with partner and verification context.
        """
        try:
            partner = request.env.user.partner_id
            verification = request.env['unitrade.seller.verification'].sudo().search([
                ('partner_id', '=', partner.id),
            ], limit=1, order='create_date desc')

            values = {
                'partner': partner,
                'verification': verification or False,
            }
            return request.render('unitrade_theme.seller_verification', values)

        except Exception as e:
            _logger.exception('Error rendering seller verification page: %s', e)
            return request.render('unitrade_theme.seller_verification', {
                'partner': request.env.user.partner_id,
                'verification': False,
            })

    @http.route(
        '/seller-verification/submit',
        type='http', auth='user', website=True, methods=['POST'], csrf=True,
    )
    def seller_verification_submit(self, **kw):
        """
        POST /seller-verification/submit
        AJAX form submission handler. Runs OCR pipeline and returns JSON
        with full debug info for frontend popup display.
        """
        try:
            partner = request.env.user.partner_id
            ktm_file = kw.get('ktm_file')

            # --- File Validation ---
            if not ktm_file:
                return self._json_response({
                    'status': 'error',
                    'message': 'File KTM wajib diunggah.',
                })

            filename = ktm_file.filename or ''
            ext = os.path.splitext(filename)[1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                return self._json_response({
                    'status': 'error',
                    'message': f'Format file tidak didukung ({ext}). Gunakan JPG atau PNG.',
                })

            file_bytes = ktm_file.read()
            if len(file_bytes) > MAX_FILE_SIZE:
                size_mb = len(file_bytes) / (1024 * 1024)
                return self._json_response({
                    'status': 'error',
                    'message': f'Ukuran file terlalu besar ({size_mb:.1f} MB). Maksimal 5 MB.',
                })

            # --- Step 1: Encode and save as ir.attachment ---
            file_b64 = base64.b64encode(file_bytes)

            attachment = request.env['ir.attachment'].sudo().create({
                'name': filename,
                'datas': file_b64,
                'res_model': 'res.partner',
                'res_id': partner.id,
                'type': 'binary',
            })

            # --- Step 2: Run OCR Pipeline ---
            from ..services.ocr_service import KTMOCRService
            ocr_result = KTMOCRService.process_ktm(
                env=request.env,
                image_bytes=file_bytes,
            )

            verification_status = ocr_result.get('verification_status', 'rejected')
            _logger.info(
                '[CONTROLLER] OCR result for %s: status=%s, nim=%s, name=%s, reason=%s',
                partner.name,
                verification_status,
                ocr_result.get('nim'),
                ocr_result.get('name_detected'),
                ocr_result.get('reason'),
            )

            # --- Step 3: Handle "no KTM keywords" → invalid_image popup ---
            if verification_status == 'invalid_image':
                return self._json_response({
                    'status': 'invalid_image',
                    'message': 'Gambar Tidak Sesuai, coba lagi',
                    'ocr_text': ocr_result.get('ocr_text', '')[:300],
                    'nim': None,
                    'name': None,
                    'found': False,
                    'reason': ocr_result.get('reason', ''),
                })

            # --- Step 4: Handle "no name detected" → no_name popup ---
            if verification_status == 'no_name':
                return self._json_response({
                    'status': 'no_name',
                    'message': 'Pastikan upload foto KTM',
                    'ocr_text': ocr_result.get('ocr_text', '')[:300],
                    'nim': ocr_result.get('nim'),
                    'name': None,
                    'found': False,
                    'reason': ocr_result.get('reason', ''),
                })

            # --- Step 5: Create or update verification record ---
            existing = request.env['unitrade.seller.verification'].sudo().search([
                ('partner_id', '=', partner.id),
            ], limit=1)

            vals = {
                'partner_id': partner.id,
                'ktm_image': file_b64,
                'ktm_filename': filename,
                'attachment_id': attachment.id,
                'ocr_raw_text': ocr_result.get('ocr_text', ''),
                'nim_extracted': ocr_result.get('nim'),
                'nim_valid': bool(ocr_result.get('nim')),
                'nim_registered': ocr_result.get('nim_registered', False),
                'state': 'approved' if verification_status == 'approved' else 'rejected',
            }

            if existing:
                existing.sudo().write(vals)
            else:
                request.env['unitrade.seller.verification'].sudo().create(vals)

            # --- Step 6: Return JSON with debug info ---
            if verification_status == 'approved':
                # Mark user as verified seller
                user = request.env.user
                user.sudo().write({'x_is_seller': True})

                # Create or update unitrade.seller record
                nim = ocr_result.get('nim') or ocr_result.get('student_nim') or ''
                seller = request.env['unitrade.seller'].sudo().search([
                    ('user_id', '=', user.id),
                ], limit=1)

                seller_vals = {
                    'user_id': user.id,
                    'nim': nim or 'PENDING',
                    'ktm_image': file_b64,
                    'ktm_filename': filename,
                    'ocr_result': ocr_result.get('ocr_text', ''),
                    'ocr_confidence': 100.0,
                    'ocr_nim_match': bool(nim),
                    'ocr_name_match': True,
                    'status': 'verified',
                    'verified_date': fields.Datetime.now(),
                }

                if seller:
                    seller.sudo().write(seller_vals)
                    _logger.info('[CONTROLLER] Updated seller record %s for %s', seller.id, partner.name)
                else:
                    seller = request.env['unitrade.seller'].sudo().create(seller_vals)
                    user.sudo().write({'x_seller_id': seller.id})
                    _logger.info('[CONTROLLER] Created seller record %s for %s', seller.id, partner.name)

                return self._json_response({
                    'status': 'approved',
                    'message': 'Verifikasi Berhasil ✅',
                    'ocr_text': ocr_result.get('ocr_text', '')[:300],
                    'nim': ocr_result.get('nim', ''),
                    'name': ocr_result.get('name_detected', ''),
                    'student_name': ocr_result.get('student_name', ''),
                    'found': True,
                    'reason': ocr_result.get('reason', ''),
                })
            else:
                return self._json_response({
                    'status': 'rejected',
                    'message': 'Pengajuan Ditolak ❌\nPastikan Anda mahasiswa UNISA',
                    'ocr_text': ocr_result.get('ocr_text', '')[:300],
                    'nim': ocr_result.get('nim', ''),
                    'name': ocr_result.get('name_detected', ''),
                    'found': False,
                    'reason': ocr_result.get('reason', ''),
                })

        except Exception as e:
            _logger.exception('KTM verification failed: %s', e)
            return self._json_response({
                'status': 'error',
                'message': f'Terjadi kesalahan saat memproses KTM: {str(e)}',
                'ocr_text': '',
                'nim': None,
                'name': None,
                'found': False,
                'reason': f'exception: {str(e)}',
            })

    @http.route(
        '/unitrade/seller/verification-status',
        type='json', auth='user', methods=['POST'],
    )
    def verification_status(self, **kw):
        """JSON-RPC endpoint to check current verification status."""
        try:
            partner = request.env.user.partner_id
            record = request.env['unitrade.seller.verification'].sudo().search([
                ('partner_id', '=', partner.id),
            ], limit=1, order='create_date desc')

            if not record:
                return {'state': False, 'nim_extracted': False}

            return {
                'state': record.state,
                'nim_extracted': record.nim_extracted or '',
            }

        except Exception as e:
            _logger.exception('Error fetching verification status: %s', e)
            return {'state': 'error', 'nim_extracted': ''}

    @staticmethod
    def _json_response(data):
        """Helper to return a proper JSON HTTP response."""
        return request.make_response(
            json.dumps(data),
            headers=[('Content-Type', 'application/json')],
        )
