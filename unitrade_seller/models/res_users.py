from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging
import random
import string
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)


class ResUsersUniTrade(models.Model):
    _inherit = 'res.users'

    # === OTP Fields ===
    x_otp_code = fields.Char(
        string='OTP Code',
        copy=False,
    )
    x_otp_expiry = fields.Datetime(
        string='OTP Expiry',
        copy=False,
    )
    x_otp_attempts = fields.Integer(
        string='OTP Attempts',
        default=0,
        copy=False,
    )
    x_is_email_verified = fields.Boolean(
        string='Email Terverifikasi',
        default=False,
        copy=False,
    )

    # === Seller Fields ===
    x_is_seller = fields.Boolean(
        string='Penjual Terverifikasi',
        default=False,
        copy=False,
    )
    x_seller_id = fields.Many2one(
        'unitrade.seller',
        string='Seller Profile',
        copy=False,
    )

    # === Additional Profile Fields ===
    x_whatsapp = fields.Char(
        string='No. WhatsApp',
    )
    x_gender = fields.Selection([
        ('male', 'Laki-laki'),
        ('female', 'Perempuan'),
    ], string='Jenis Kelamin')
    x_birth_date = fields.Date(
        string='Tanggal Lahir',
    )

    def _generate_otp(self):
        """Generate 6-digit OTP code"""
        return ''.join(random.choices(string.digits, k=6))

    def action_send_otp(self):
        """Send OTP verification email"""
        self.ensure_one()

        # Rate limiting: max 3 attempts per 5 minutes
        if self.x_otp_attempts >= 3:
            if self.x_otp_expiry and self.x_otp_expiry > fields.Datetime.now():
                raise ValidationError(
                    _('Terlalu banyak percobaan. Silakan coba lagi dalam 5 menit.')
                )
            else:
                # Reset attempts after expiry
                self.x_otp_attempts = 0

        otp_code = self._generate_otp()
        expiry = datetime.now() + timedelta(minutes=5)

        self.write({
            'x_otp_code': otp_code,
            'x_otp_expiry': expiry,
            'x_otp_attempts': self.x_otp_attempts + 1,
        })

        # Send OTP via email
        template = self.env.ref(
            'unitrade_seller.mail_template_otp',
            raise_if_not_found=False,
        )
        if template:
            template.send_mail(self.id, force_send=True)
            _logger.info('OTP sent to user %s (%s)', self.name, self.email)
        else:
            _logger.warning('OTP mail template not found')

        return True

    def action_verify_otp(self, otp_input):
        """Verify OTP code submitted by user"""
        self.ensure_one()

        if not self.x_otp_code:
            raise ValidationError(_('Belum ada OTP yang dikirim. Kirim OTP terlebih dahulu.'))

        if self.x_otp_expiry and self.x_otp_expiry < fields.Datetime.now():
            raise ValidationError(_('Kode OTP sudah kadaluarsa. Kirim ulang OTP.'))

        if self.x_otp_code != otp_input:
            raise ValidationError(_('Kode OTP tidak valid. Silakan coba lagi.'))

        # OTP verified
        self.write({
            'x_is_email_verified': True,
            'x_otp_code': False,
            'x_otp_expiry': False,
            'x_otp_attempts': 0,
        })

        _logger.info('Email verified for user %s', self.name)
        return True
