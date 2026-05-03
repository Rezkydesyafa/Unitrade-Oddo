from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging
import re
import base64
import uuid
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
    x_avatar_128 = fields.Image(
        string='Avatar',
        related='user_id.avatar_128',
        readonly=True,
    )
    x_profile_description = fields.Text(
        string='Tentang Penjual',
        default=(
            'Mahasiswa aktif yang menjual makanan ringan dan produk buatan sendiri, '
            'melayani COD area kampus.'
        ),
        help='Deskripsi singkat yang tampil pada halaman profil penjual.',
    )
    x_profile_location = fields.Char(
        string='Lokasi Profil',
        compute='_compute_profile_location',
        store=False,
    )
    x_profile_address = fields.Text(
        string='Alamat Profil Publik',
        help='Alamat singkat yang tampil di sidebar profil penjual.',
    )
    x_profile_latitude = fields.Float(
        string='Latitude Profil Publik',
        digits=(10, 7),
        default=-7.7162,
        help='Latitude lokasi penjual untuk map di profil publik.',
    )
    x_profile_longitude = fields.Float(
        string='Longitude Profil Publik',
        digits=(10, 7),
        default=110.3554,
        help='Longitude lokasi penjual untuk map di profil publik.',
    )
    x_profile_uuid = fields.Char(
        string='Public Profile UUID',
        default=lambda self: str(uuid.uuid4()),
        copy=False,
        index=True,
        readonly=True,
        help='Public identifier for seller profile URLs.',
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
    total_sold = fields.Integer(
        string='Total Produk Terjual',
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
        ('profile_uuid_unique', 'UNIQUE(x_profile_uuid)', 'UUID profil penjual harus unik!'),
    ]

    def init(self):
        """Backfill UUIDs for seller records created before the public profile route existed."""
        self.env.cr.execute("""
            SELECT id
              FROM unitrade_seller
             WHERE x_profile_uuid IS NULL
                OR x_profile_uuid = ''
                OR x_profile_uuid IN (
                    SELECT x_profile_uuid
                      FROM unitrade_seller
                     WHERE x_profile_uuid IS NOT NULL
                       AND x_profile_uuid != ''
                     GROUP BY x_profile_uuid
                    HAVING COUNT(*) > 1
                )
        """)
        for seller_id, in self.env.cr.fetchall():
            self.env.cr.execute(
                "UPDATE unitrade_seller SET x_profile_uuid = %s WHERE id = %s",
                (str(uuid.uuid4()), seller_id),
            )

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
            Product = self.env['product.template'].sudo()
            products = Product.search([
                ('x_seller_id', '=', record.id)
            ]) if 'x_seller_id' in Product._fields else Product.browse()

            if products and 'unitrade.review' in self.env.registry:
                reviews = self.env['unitrade.review'].sudo().search([
                    ('product_id', 'in', products.ids),
                    ('is_visible', '=', True),
                ])
            else:
                reviews = []

            sale_count = 0
            if products and 'sales_count' in Product._fields:
                sale_count = int(sum(products.mapped('sales_count')))

            record.total_products = len(products)
            record.total_orders = sale_count
            record.total_sold = sale_count
            record.total_revenue = 0.0
            record.average_rating = (
                round(sum(reviews.mapped('rating')) / len(reviews), 1)
                if reviews
                else 0.0
            )

    def _compute_profile_location(self):
        """Build a compact public location label from the linked partner."""
        for record in self:
            partner = record.partner_id
            if not partner:
                record.x_profile_location = 'Yogyakarta'
                continue

            location_parts = [
                part for part in [partner.city, partner.state_id.name]
                if part
            ]
            record.x_profile_location = ', '.join(location_parts) or 'Yogyakarta'

    def _ensure_profile_uuid(self):
        """Ensure existing sellers have a public UUID before rendering public links."""
        for record in self.sudo():
            if not record.x_profile_uuid:
                record.write({'x_profile_uuid': str(uuid.uuid4())})
        return self

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
