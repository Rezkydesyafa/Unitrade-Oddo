from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging
import re
import base64
from datetime import datetime

_logger = logging.getLogger(__name__)


class UnitradeSeller(models.Model):
    _name = 'unitrade.seller'
    _description = 'UniTrade Seller Profile'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    # === Basic Info ===
    name = fields.Char(
        string='Nama Penjual',
        related='user_id.name',
        store=True,
        readonly=True,
    )
    user_id = fields.Many2one(
        'res.users',
        string='User Account',
        required=True,
        ondelete='cascade',
        index=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
        related='user_id.partner_id',
        store=True,
        readonly=True,
    )

    # === KTM Verification ===
    nim = fields.Char(
        string='Nomor Induk Mahasiswa (NIM)',
        required=True,
        index=True,
    )
    ktm_image = fields.Binary(
        string='Foto KTM',
        attachment=True,
    )
    ktm_filename = fields.Char(
        string='Nama File KTM',
    )
    ocr_result = fields.Text(
        string='Hasil OCR',
        readonly=True,
    )
    ocr_confidence = fields.Float(
        string='OCR Confidence Score (%)',
        readonly=True,
        default=0.0,
    )
    ocr_nim_match = fields.Boolean(
        string='NIM Match',
        readonly=True,
        default=False,
    )
    ocr_name_match = fields.Boolean(
        string='Name Match',
        readonly=True,
        default=False,
    )

    # === Status ===
    status = fields.Selection([
        ('draft', 'Draft'),
        ('pending', 'Menunggu Verifikasi'),
        ('verified', 'Terverifikasi'),
        ('rejected', 'Ditolak'),
    ], string='Status Verifikasi',
        default='draft',
        tracking=True,
        index=True,
    )
    rejection_reason = fields.Text(
        string='Alasan Penolakan',
    )
    verified_date = fields.Datetime(
        string='Tanggal Verifikasi',
        readonly=True,
    )
    verified_by = fields.Many2one(
        'res.users',
        string='Diverifikasi Oleh',
        readonly=True,
    )

    # === Stats ===
    total_products = fields.Integer(
        string='Total Produk',
        compute='_compute_seller_stats',
        store=False,
    )
    total_orders = fields.Integer(
        string='Total Pesanan',
        compute='_compute_seller_stats',
        store=False,
    )
    total_revenue = fields.Float(
        string='Total Pendapatan',
        compute='_compute_seller_stats',
        store=False,
    )
    average_rating = fields.Float(
        string='Rating Rata-rata',
        compute='_compute_seller_stats',
        store=False,
    )

    # === Constraints ===
    _sql_constraints = [
        ('user_unique', 'UNIQUE(user_id)', 'Setiap user hanya bisa memiliki satu akun penjual!'),
        ('nim_unique', 'UNIQUE(nim)', 'NIM ini sudah terdaftar sebagai penjual!'),
    ]

    @api.constrains('nim')
    def _check_nim_format(self):
        """Validate NIM format for UNISA Yogyakarta"""
        for record in self:
            if record.nim:
                # Adjust regex pattern to match UNISA NIM format
                if not re.match(r'^\d{8,15}$', record.nim):
                    raise ValidationError(
                        _('Format NIM tidak valid. NIM harus berupa 8-15 digit angka.')
                    )

    @api.constrains('ktm_image')
    def _check_ktm_file_size(self):
        """Validate KTM image file size (max 5MB)"""
        for record in self:
            if record.ktm_image:
                file_size = len(base64.b64decode(record.ktm_image))
                if file_size > 5 * 1024 * 1024:  # 5MB
                    raise ValidationError(
                        _('Ukuran file KTM maksimal 5MB. File Anda: %.2f MB') % (file_size / 1024 / 1024)
                    )

    def _compute_seller_stats(self):
        """Compute seller statistics"""
        for record in self:
            # Products count
            products = self.env['product.template'].sudo().search_count([
                ('x_seller_id', '=', record.id)
            ]) if 'x_seller_id' in self.env['product.template']._fields else 0

            record.total_products = products
            record.total_orders = 0  # Will be computed when order module is ready
            record.total_revenue = 0.0
            record.average_rating = 0.0

    # === Actions ===
    def action_submit_verification(self):
        """Submit seller for KTM verification"""
        self.ensure_one()
        if not self.ktm_image:
            raise ValidationError(_('Upload foto KTM terlebih dahulu!'))
        if not self.nim:
            raise ValidationError(_('Isi NIM terlebih dahulu!'))

        self.write({'status': 'pending'})

        # Attempt OCR verification
        self._run_ocr_verification()

        # Send notification email
        template = self.env.ref(
            'unitrade_seller.mail_template_seller_pending',
            raise_if_not_found=False,
        )
        if template:
            template.send_mail(self.id, force_send=True)

        _logger.info('Seller %s submitted for verification (NIM: %s)', self.name, self.nim)

    def _run_ocr_verification(self):
        """Run PaddleOCR on KTM image to extract and verify text"""
        self.ensure_one()
        try:
            from paddleocr import PaddleOCR
            from PIL import Image
            import io
            import numpy as np

            # Decode base64 image
            image_data = base64.b64decode(self.ktm_image)
            image = Image.open(io.BytesIO(image_data))

            # Convert to numpy array for PaddleOCR
            img_array = np.array(image)

            # Initialize PaddleOCR
            ocr = PaddleOCR(use_angle_cls=True, lang='id', show_log=False)
            result = ocr.ocr(img_array, cls=True)

            # Extract text and confidence
            extracted_texts = []
            total_confidence = 0.0
            count = 0

            if result and result[0]:
                for line in result[0]:
                    text = line[1][0]
                    confidence = line[1][1]
                    extracted_texts.append(f'{text} ({confidence:.2%})')
                    total_confidence += confidence
                    count += 1

            ocr_text = '\n'.join(extracted_texts)
            avg_confidence = (total_confidence / count * 100) if count > 0 else 0

            # Check NIM match
            all_text = ' '.join([line[1][0] for line in result[0]] if result and result[0] else [])
            nim_match = self.nim in all_text

            # Check name match (fuzzy)
            user_name = self.user_id.name.upper()
            name_match = any(
                word in all_text.upper()
                for word in user_name.split()
                if len(word) > 2
            )

            self.write({
                'ocr_result': ocr_text,
                'ocr_confidence': avg_confidence,
                'ocr_nim_match': nim_match,
                'ocr_name_match': name_match,
            })

            # Auto-verify if confidence >= 70% and both match
            if avg_confidence >= 70 and nim_match and name_match:
                _logger.info(
                    'Auto-verification passed for seller %s (confidence: %.1f%%)',
                    self.name, avg_confidence,
                )
            else:
                _logger.info(
                    'Manual review required for seller %s (confidence: %.1f%%, NIM match: %s, Name match: %s)',
                    self.name, avg_confidence, nim_match, name_match,
                )

        except ImportError:
            _logger.warning(
                'PaddleOCR not installed. Skipping OCR verification for seller %s. '
                'Install with: pip install paddleocr paddlepaddle',
                self.name,
            )
            self.write({
                'ocr_result': 'PaddleOCR belum terinstall. Verifikasi manual diperlukan.',
                'ocr_confidence': 0.0,
            })
        except Exception as e:
            _logger.error('OCR verification failed for seller %s: %s', self.name, str(e))
            self.write({
                'ocr_result': f'Error: {str(e)}',
                'ocr_confidence': 0.0,
            })

    def action_verify(self):
        """Admin approves seller verification"""
        self.ensure_one()
        self.write({
            'status': 'verified',
            'verified_date': fields.Datetime.now(),
            'verified_by': self.env.uid,
        })

        # Update user flags
        self.user_id.write({
            'x_is_seller': True,
            'x_seller_id': self.id,
        })

        # Send notification
        template = self.env.ref(
            'unitrade_seller.mail_template_seller_verified',
            raise_if_not_found=False,
        )
        if template:
            template.send_mail(self.id, force_send=True)

        _logger.info('Seller %s verified by %s', self.name, self.env.user.name)

    def action_reject(self):
        """Admin rejects seller verification"""
        self.ensure_one()
        if not self.rejection_reason:
            raise ValidationError(_('Isi alasan penolakan terlebih dahulu!'))

        self.write({'status': 'rejected'})

        # Send notification
        template = self.env.ref(
            'unitrade_seller.mail_template_seller_rejected',
            raise_if_not_found=False,
        )
        if template:
            template.send_mail(self.id, force_send=True)

        _logger.info('Seller %s rejected by %s. Reason: %s', self.name, self.env.user.name, self.rejection_reason)

    def action_reset_to_draft(self):
        """Reset seller back to draft status"""
        self.ensure_one()
        self.write({
            'status': 'draft',
            'rejection_reason': False,
        })
