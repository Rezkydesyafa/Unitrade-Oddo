# -*- coding: utf-8 -*-
from odoo import _, http, fields
from odoo.exceptions import UserError
from odoo.http import request
from odoo.addons.unitrade_theme.controllers.controllers import UnitradeAuthSignup
import logging
import json
import base64
import os
import io
from datetime import timedelta

_logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
MIN_IMAGE_WIDTH = 600
MIN_IMAGE_HEIGHT = 350
UPLOAD_RATE_LIMIT = 10
UPLOAD_RATE_WINDOW_MINUTES = 15


class SellerVerificationController(http.Controller):
    """Controller for seller KTM verification flow."""

    @staticmethod
    def _verified_seller_for_current_user():
        return request.env['unitrade.seller'].sudo().search([
            ('user_id', '=', request.env.uid),
            ('status', '=', 'verified'),
        ], limit=1)

    @staticmethod
    def _seller_contact_value(user):
        return (user.email or user.partner_id.email or user.login or '').strip()

    @staticmethod
    def _seller_otp_verified():
        return bool(request.session.get('seller_onboarding_otp_verified'))

    @staticmethod
    def _marketplace_block_message(feature_label=None):
        user = request.env.user
        if user._is_public() or not hasattr(user, '_check_unitrade_marketplace_access'):
            return ''
        try:
            user._check_unitrade_marketplace_access(feature_label or _('mendaftar sebagai seller'))
        except UserError as error:
            return error.args[0] if error.args else str(error)
        return ''

    @staticmethod
    def _rejection_message(reason):
        messages = {
            'nim_not_extracted': 'NIM belum terbaca otomatis. Pengajuan masuk review manual admin, Anda tidak perlu upload ulang.',
            'name_token_not_matched': 'Nama tidak cocok. Pastikan KTM yang diupload adalah milik Anda dan nama pada KTM terlihat jelas.',
            'name_token_low_confidence': 'Nama pada KTM kurang jelas. Pengajuan masuk ke review manual admin, Anda tidak perlu upload ulang.',
            'account_name_mismatch': 'Nama akun Anda belum cocok dengan nama pada KTM. Pengajuan masuk review manual admin untuk memastikan KTM ini milik Anda.',
            'nim_not_in_db': 'NIM belum cocok otomatis dengan database mahasiswa. Pengajuan masuk review manual admin, Anda tidak perlu upload ulang.',
            'nim_already_used': 'NIM sudah digunakan oleh akun penjual lain.',
            'ocr_empty': 'Gambar yang Anda input bukan KTM atau tidak terbaca. Upload foto Kartu Tanda Mahasiswa asli yang jelas.',
            'no_ktm_keywords': 'Gambar yang Anda input bukan KTM. Pastikan upload foto Kartu Tanda Mahasiswa yang benar.',
            'image_too_small': 'Resolusi foto terlalu kecil. Upload foto KTM yang lebih jelas.',
            'vision_api_failed': 'Sistem OCR sedang bermasalah. Pengajuan Anda kami simpan dan akan direview manual oleh admin.',
        }
        if reason and reason.startswith('vision_api_failed'):
            return messages['vision_api_failed']
        return messages.get(reason, 'Pengajuan ditolak. Pastikan NIM dan nama pada KTM sesuai data mahasiswa UNISA.')

    REVIEW_REASONS_KEEP_OPEN = {
        'nim_not_extracted', 'nim_not_in_db', 'name_token_low_confidence',
        'account_name_mismatch',
    }

    @staticmethod
    def _check_upload_rate_limit(verification):
        now = fields.Datetime.now()
        window_start = verification.upload_window_start if verification else False
        if window_start and now - window_start < timedelta(minutes=UPLOAD_RATE_WINDOW_MINUTES):
            if verification.upload_attempt_count >= UPLOAD_RATE_LIMIT:
                return False
            verification.sudo().write({
                'upload_attempt_count': verification.upload_attempt_count + 1,
            })
            return True

        if verification:
            verification.sudo().write({
                'upload_window_start': now,
                'upload_attempt_count': 1,
            })
        return True

    @staticmethod
    def _image_dimensions(file_bytes):
        try:
            from PIL import Image
            image = Image.open(io.BytesIO(file_bytes))
            image.verify()
            return image.size
        except ImportError:
            _logger.warning('Pillow is not available; skipping KTM image dimension validation.')
            return None, None
        except Exception:
            return 0, 0

    @http.route('/seller-onboarding', type='http', auth='user', website=True, sitemap=False)
    def seller_onboarding_page(self, **kw):
        """Render the seller onboarding page before OTP and KTM upload."""
        if self._marketplace_block_message(_('mendaftar sebagai seller')):
            return request.redirect('/my/profile?unitrade_blocked=1')
        if self._verified_seller_for_current_user():
            return request.redirect('/unitrade/seller/dashboard')

        error_message = ''
        if kw.get('error') == 'otp_rate_limit':
            error_message = 'Terlalu banyak permintaan OTP. Coba lagi dalam 10 menit.'

        return request.render('unitrade_seller.seller_onboarding_template', {
            'page_title': 'Mulai Berjualan - UniTrade',
            'error_message': error_message,
        })

    @http.route('/seller-onboarding/start', type='http', auth='user', website=True, methods=['POST'], csrf=True, sitemap=False)
    def seller_onboarding_start(self, **kw):
        """Start a fresh seller OTP challenge, then continue to the shared OTP page."""
        if self._marketplace_block_message(_('mendaftar sebagai seller')):
            return request.redirect('/my/profile?unitrade_blocked=1')
        if self._verified_seller_for_current_user():
            return request.redirect('/unitrade/seller/dashboard')

        user = request.env.user.sudo()
        request.session.pop('seller_onboarding_otp_verified', None)
        contact = self._seller_contact_value(user)
        otp_limit = request.env['unitrade.otp'].sudo().rate_limit_status(
            user.id,
            purpose='seller_onboarding',
            window_minutes=10,
            max_attempts=3,
        )
        if not otp_limit['allowed']:
            return request.redirect('/seller-onboarding?error=otp_rate_limit')

        return UnitradeAuthSignup()._generate_and_redirect_otp(
            user,
            contact,
            purpose='seller_onboarding',
        )

    @http.route('/seller-verification', type='http', auth='user', website=True, sitemap=False)
    def seller_verification_page(self, **kw):
        """
        GET /seller-verification
        Render the seller verification page with partner and verification context.
        """
        try:
            if self._marketplace_block_message(_('mengupload verifikasi seller')):
                return request.redirect('/my/profile?unitrade_blocked=1')
            if self._verified_seller_for_current_user():
                return request.redirect('/unitrade/seller/dashboard')
            if not self._seller_otp_verified():
                return request.redirect('/seller-onboarding')

            partner = request.env.user.partner_id
            verification = request.env['unitrade.seller.verification'].sudo().search([
                ('partner_id', '=', partner.id),
            ], limit=1, order='create_date desc')
            universities = request.env['unitrade.university'].sudo().search([
                ('active', '=', True),
            ], order='sequence, name')

            values = {
                'partner': partner,
                'verification': verification or False,
                'universities': universities,
            }
            return request.render('unitrade_theme.seller_verification', values)

        except Exception as e:
            _logger.exception('Error rendering seller verification page: %s', e)
            return request.render('unitrade_theme.seller_verification', {
                'partner': request.env.user.partner_id,
                'verification': False,
                'universities': request.env['unitrade.university'].sudo().search([
                    ('active', '=', True),
                ], order='sequence, name'),
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
            block_message = self._marketplace_block_message(_('mengupload verifikasi seller'))
            if block_message:
                return self._json_response({
                    'status': 'blocked',
                    'message': block_message,
                    'redirect_url': '/my/profile?unitrade_blocked=1',
                })

            if not self._seller_otp_verified():
                return self._json_response({
                    'status': 'otp_required',
                    'message': 'Verifikasi OTP diperlukan sebelum upload KTM.',
                    'redirect_url': '/seller-onboarding',
                })

            partner = request.env.user.partner_id
            ktm_file = kw.get('ktm_file')
            Verification = request.env['unitrade.seller.verification'].sudo()
            existing = Verification.search([
                ('partner_id', '=', partner.id),
            ], limit=1)
            university = request.env['unitrade.university'].sudo().browse()
            university_id = kw.get('university_id')
            university_other = (kw.get('university_other') or '').strip()
            if university_id:
                try:
                    university = request.env['unitrade.university'].sudo().browse(int(university_id)).exists()
                except (TypeError, ValueError):
                    university = request.env['unitrade.university'].sudo().browse()

            if university and not university.active:
                university = request.env['unitrade.university'].sudo().browse()

            if not university and not university_other:
                return self._json_response({
                    'status': 'error',
                    'message': 'Pilih universitas atau isi universitas lainnya terlebih dahulu.',
                    'reason': 'university_required',
                })

            if not self._check_upload_rate_limit(existing):
                retry_minutes = UPLOAD_RATE_WINDOW_MINUTES
                if existing and existing.upload_window_start:
                    elapsed = fields.Datetime.now() - existing.upload_window_start
                    remaining = timedelta(minutes=UPLOAD_RATE_WINDOW_MINUTES) - elapsed
                    retry_minutes = max(1, int(remaining.total_seconds() // 60) + 1)
                return self._json_response({
                    'status': 'rate_limited',
                    'message': f'Terlalu banyak percobaan upload KTM. Coba lagi dalam {retry_minutes} menit.',
                    'reason': 'upload_rate_limited',
                    'retry_minutes': retry_minutes,
                })

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

            image_width, image_height = self._image_dimensions(file_bytes)
            if image_width is not None and (image_width < MIN_IMAGE_WIDTH or image_height < MIN_IMAGE_HEIGHT):
                return self._json_response({
                    'status': 'invalid_image',
                    'message': self._rejection_message('image_too_small'),
                    'reason': 'image_too_small',
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
                account_name=partner.name or '',
            )

            verification_status = ocr_result.get('verification_status', 'rejected')
            nim = ocr_result.get('nim') or ocr_result.get('student_nim') or ''
            duplicate_seller = request.env['unitrade.seller'].sudo().browse()
            if verification_status in ('approved', 'manual_review') and nim:
                duplicate_seller = request.env['unitrade.seller'].sudo().search([
                    ('nim', '=', nim),
                    ('status', '=', 'verified'),
                    ('user_id', '!=', request.env.uid),
                ], limit=1)
                if duplicate_seller:
                    verification_status = 'rejected'
                    ocr_result['verification_status'] = 'rejected'
                    ocr_result['reason'] = 'nim_already_used'
                    _logger.info(
                        '[CONTROLLER] Seller verification rejected for user %s: NIM %s already used by seller %s',
                        request.env.uid,
                        nim,
                        duplicate_seller.id,
                    )
            _logger.info(
                '[CONTROLLER] OCR result for %s: status=%s, nim=%s, name=%s, reason=%s',
                partner.name,
                verification_status,
                ocr_result.get('nim'),
                ocr_result.get('name_detected'),
                ocr_result.get('reason'),
            )

            reason = ocr_result.get('reason', '')
            rejected_message = self._rejection_message(reason)
            is_system_error = bool(reason and str(reason).startswith('vision_api_failed'))
            if is_system_error:
                verification_status = 'manual_review'
                ocr_result['verification_status'] = 'manual_review'
            record_state = {
                'approved': 'approved',
                'manual_review': 'manual_review',
            }.get(verification_status, 'rejected')

            review_note_value = False
            if record_state == 'manual_review':
                if is_system_error:
                    review_note_value = f'[SYSTEM ERROR - Vision API] {ocr_result.get("ocr_text", "")[:200]}'
                else:
                    review_note_value = f'[Perlu cek admin: {reason or "manual_review"}] {rejected_message}'

            vals = {
                'partner_id': partner.id,
                'university_id': university.id if university else False,
                'university_other': False if university else university_other,
                'ktm_image': file_b64,
                'ktm_filename': filename,
                'attachment_id': attachment.id,
                'ocr_raw_text': ocr_result.get('ocr_text', ''),
                'nim_extracted': ocr_result.get('nim'),
                'nim_valid': bool(ocr_result.get('nim')),
                'nim_registered': ocr_result.get('nim_registered', False),
                'student_name': ocr_result.get('student_name') or '',
                'name_match_token': ocr_result.get('name_match_token') or '',
                'name_confidence': ocr_result.get('name_match_score') or 0.0,
                'confidence_flag': 'high' if (ocr_result.get('name_match_score') or 0.0) >= 0.9 else 'low',
                'duplicate_seller_id': duplicate_seller.id if duplicate_seller else False,
                'duplicate_warning': bool(duplicate_seller),
                'image_width': image_width or 0,
                'image_height': image_height or 0,
                'rejection_reason': rejected_message if record_state == 'rejected' else False,
                'review_note': review_note_value,
                'state': record_state,
            }

            if existing:
                verification = existing
                verification.sudo().write(vals)
            else:
                vals.update({
                    'upload_window_start': fields.Datetime.now(),
                    'upload_attempt_count': 1,
                })
                verification = Verification.create(vals)

            # --- Step 6: Return JSON with debug info ---
            if verification_status == 'approved':
                # Mark user as verified seller
                user = request.env.user

                # Create or update unitrade.seller record
                seller = request.env['unitrade.seller'].sudo().search([
                    ('user_id', '=', user.id),
                ], limit=1)

                seller_vals = {
                    'user_id': user.id,
                    'university_id': university.id if university else False,
                    'university_other': False if university else university_other,
                    'nim': nim or 'PENDING',
                    'ktm_image': file_b64,
                    'ktm_filename': filename,
                    'ocr_result': ocr_result.get('ocr_text', ''),
                    'ocr_confidence': 100.0,
                    'ocr_nim_match': bool(nim),
                    'ocr_name_match': True,
                    'ocr_student_name': ocr_result.get('student_name') or '',
                    'ocr_name_match_token': ocr_result.get('name_match_token') or '',
                    'status': 'verified',
                    'rejection_reason': False,
                    'revoke_reason': False,
                    'revoked_date': False,
                    'revoked_by': False,
                    'report_state': 'none',
                    'report_admin_note': False,
                    'verified_date': fields.Datetime.now(),
                    'verified_by': request.env.uid,
                }

                if seller:
                    seller.sudo().write(seller_vals)
                    _logger.info('[CONTROLLER] Updated seller record %s for %s', seller.id, partner.name)
                else:
                    seller = request.env['unitrade.seller'].sudo().create(seller_vals)
                    _logger.info('[CONTROLLER] Created seller record %s for %s', seller.id, partner.name)

                user.sudo().write({
                    'x_is_seller': True,
                    'x_seller_id': seller.id,
                })
                template = request.env.ref(
                    'unitrade_seller.mail_template_seller_verified',
                    raise_if_not_found=False,
                )
                if template:
                    template.sudo().send_mail(seller.id, force_send=True)
                request.session.pop('seller_onboarding_otp_verified', None)

                return self._json_response({
                    'status': 'approved',
                    'message': 'Verifikasi berhasil. Akun Anda sekarang sudah menjadi penjual.',
                    'ocr_text': ocr_result.get('ocr_text', '')[:300],
                    'nim': ocr_result.get('nim', ''),
                    'name': ocr_result.get('name_detected', ''),
                    'student_name': ocr_result.get('student_name', ''),
                    'found': True,
                    'reason': ocr_result.get('reason', ''),
                })

            if verification_status == 'manual_review':
                verification._send_verification_template('unitrade_seller.mail_template_seller_verification_manual_review')
                review_messages = {
                    'name_token_low_confidence': 'KTM berhasil dikirim. Nama pada KTM kurang jelas sehingga perlu dicek admin.',
                    'account_name_mismatch': 'KTM berhasil dikirim. Nama akun Anda belum cocok dengan KTM, admin akan memastikan KTM ini milik Anda.',
                    'nim_not_in_db': 'KTM berhasil dikirim. NIM belum cocok otomatis dengan database, admin akan memverifikasi manual.',
                    'nim_not_extracted': 'KTM berhasil dikirim. NIM belum terbaca otomatis, admin akan memverifikasi manual.',
                }
                manual_message = review_messages.get(reason, 'KTM berhasil dikirim dan masuk review manual admin.')
                if is_system_error:
                    manual_message = 'KTM berhasil dikirim. Sistem OCR sedang sibuk, admin akan memverifikasi manual.'
                return self._json_response({
                    'status': 'manual_review',
                    'message': manual_message,
                    'ocr_text': ocr_result.get('ocr_text', '')[:300],
                    'nim': ocr_result.get('nim', ''),
                    'name': ocr_result.get('name_detected', ''),
                    'student_name': ocr_result.get('student_name', ''),
                    'found': True,
                    'reason': ocr_result.get('reason', ''),
                })

            verification._send_verification_template('unitrade_seller.mail_template_seller_verification_rejected')
            return self._json_response({
                'status': 'invalid_image' if verification_status == 'invalid_image' else 'rejected',
                'message': rejected_message,
                'ocr_text': ocr_result.get('ocr_text', '')[:300],
                'nim': ocr_result.get('nim', ''),
                'name': ocr_result.get('name_detected', ''),
                'found': False,
                'reason': reason,
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
            block_message = self._marketplace_block_message(_('mengakses verifikasi seller'))
            if block_message:
                return {'state': 'blocked', 'nim_extracted': False, 'reason': block_message}

            partner = request.env.user.partner_id
            record = request.env['unitrade.seller.verification'].sudo().search([
                ('partner_id', '=', partner.id),
            ], limit=1, order='create_date desc')

            if not record:
                return {'state': False, 'nim_extracted': False}

            return {
                'state': record.state,
                'nim_extracted': record.nim_extracted or '',
                'reason': record.rejection_reason or record.review_note or '',
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
