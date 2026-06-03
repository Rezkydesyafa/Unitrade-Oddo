from odoo import models, fields, api, _
from odoo.exceptions import AccessDenied, UserError, ValidationError
import logging

from .unitrade_audit import log_admin_action

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

    # === Admin Moderation Fields ===
    x_unitrade_is_blocked = fields.Boolean(
        string='Akun Diblokir',
        default=False,
        copy=False,
        help='Jika aktif, user tidak bisa login, transaksi, chat, maupun upload produk.',
    )
    x_unitrade_block_reason = fields.Text(
        string='Alasan Blokir',
        copy=False,
    )
    x_unitrade_blocked_at = fields.Datetime(
        string='Tanggal Diblokir',
        copy=False,
        readonly=True,
    )
    x_unitrade_blocked_by = fields.Many2one(
        'res.users',
        string='Diblokir Oleh',
        copy=False,
        readonly=True,
    )
    x_unitrade_admin_note = fields.Text(
        string='Catatan Internal Admin',
        help='Catatan internal admin tentang user ini. Tidak tampil ke user.',
    )

    # === Computed Counters (admin stats) ===
    x_unitrade_seller_status = fields.Selection(
        selection=[
            ('none', 'Non-Penjual'),
            ('draft', 'Draft'),
            ('pending', 'Menunggu Verifikasi'),
            ('verified', 'Terverifikasi'),
            ('rejected', 'Ditolak'),
            ('revoked', 'Verifikasi Dicabut'),
        ],
        string='Status Seller',
        compute='_compute_unitrade_seller_status',
        store=False,
    )
    x_unitrade_product_count = fields.Integer(
        string='Jumlah Produk',
        compute='_compute_unitrade_user_stats',
        store=False,
    )
    x_unitrade_order_count = fields.Integer(
        string='Jumlah Transaksi',
        compute='_compute_unitrade_user_stats',
        store=False,
    )
    x_unitrade_report_count = fields.Integer(
        string='Jumlah Laporan',
        compute='_compute_unitrade_user_stats',
        store=False,
    )

    def _compute_unitrade_seller_status(self):
        Seller = self.env['unitrade.seller'].sudo()
        for user in self:
            seller = user.x_seller_id or Seller.search(
                [('user_id', '=', user.id)],
                limit=1,
                order='create_date desc',
            )
            user.x_unitrade_seller_status = seller.status if seller else 'none'

    def _compute_unitrade_user_stats(self):
        Product = self.env['product.template'].sudo()
        Order = self.env['sale.order'].sudo()
        has_chat_report = 'unitrade.chat.report' in self.env.registry

        for user in self:
            # Product count (via seller link)
            product_count = 0
            if 'x_seller_id' in Product._fields and user.x_seller_id:
                product_count = Product.search_count([('x_seller_id', '=', user.x_seller_id.id)])
            user.x_unitrade_product_count = product_count

            # Order count as buyer
            order_count = 0
            if user.partner_id:
                order_count = Order.search_count([
                    ('partner_id', '=', user.partner_id.id),
                    ('state', 'in', ('sale', 'done')),
                ])
            user.x_unitrade_order_count = order_count

            # Report count (chat reports filed against user)
            report_count = 0
            if has_chat_report:
                report_count = self.env['unitrade.chat.report'].sudo().search_count(
                    [('reported_user_id', '=', user.id)]
                )
            user.x_unitrade_report_count = report_count

    # === Admin actions ===
    def _unitrade_is_admin(self):
        return self.env.user.has_group('unitrade_seller.group_unitrade_admin') \
            or self.env.user.has_group('base.group_system')

    def _unitrade_is_marketplace_blocked(self):
        self.ensure_one()
        return bool(self.sudo().x_unitrade_is_blocked)

    def _unitrade_block_message(self, feature_label=None):
        self.ensure_one()
        if feature_label:
            message = _('Akun Anda sedang diblokir oleh admin UniTrade sehingga tidak dapat %s.') % feature_label
        else:
            message = _('Akun Anda sedang diblokir oleh admin UniTrade.')
        reason = (self.sudo().x_unitrade_block_reason or '').strip()
        if reason:
            message = _('%s Alasan: %s') % (message, reason)
        return message

    def _check_unitrade_marketplace_access(self, feature_label=None):
        self.ensure_one()
        if self._unitrade_is_marketplace_blocked():
            raise UserError(self._unitrade_block_message(feature_label))
        return True

    def _unitrade_marketplace_block_payload(self, feature_label=None):
        self.ensure_one()
        if not self._unitrade_is_marketplace_blocked():
            return {}
        return {
            'success': False,
            'error': 'account_blocked',
            'message': self._unitrade_block_message(feature_label),
        }

    def action_unitrade_block(self):
        """Open wizard to block the selected users with a required reason."""
        self.ensure_one()
        if not self._unitrade_is_admin():
            raise AccessDenied(_('Hanya admin UniTrade yang dapat memblokir user.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Blokir Akun'),
            'res_model': 'unitrade.user.block.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_user_id': self.id,
                'default_mode': 'block',
            },
        }

    def action_unitrade_unblock(self):
        """Unblock the selected user."""
        self.ensure_one()
        if not self._unitrade_is_admin():
            raise AccessDenied(_('Hanya admin UniTrade yang dapat membuka blokir user.'))

        if not self.x_unitrade_is_blocked:
            raise ValidationError(_('User ini tidak dalam status diblokir.'))

        actor = self.env.user.name
        self.sudo().write({
            'x_unitrade_is_blocked': False,
            'x_unitrade_block_reason': False,
            'x_unitrade_blocked_at': False,
            'x_unitrade_blocked_by': False,
        })

        # Also reset chat-level block if exists
        if 'x_unitrade_chat_blocked' in self._fields and self.x_unitrade_chat_blocked:
            self.sudo().write({
                'x_unitrade_chat_blocked': False,
                'x_unitrade_chat_block_reason': False,
            })

        self._unitrade_audit_note(
            _('Akun %s dibuka blokirnya oleh %s.') % (self.name, actor)
        )
        log_admin_action(
            self.env,
            'user.unblock',
            description=_('Akun %s dibuka blokirnya oleh %s.') % (self.name, actor),
            record=self,
            severity='warning',
            payload={'user_id': self.id, 'login': self.login},
        )
        _logger.info('UniTrade user unblocked: id=%s by=%s', self.id, actor)
        return True

    def _unitrade_apply_block(self, reason):
        """Internal helper: mark user as blocked with reason."""
        self.ensure_one()
        reason = (reason or '').strip()
        if not reason:
            raise ValidationError(_('Alasan blokir wajib diisi.'))

        now = fields.Datetime.now()
        actor = self.env.user

        self.sudo().write({
            'x_unitrade_is_blocked': True,
            'x_unitrade_block_reason': reason,
            'x_unitrade_blocked_at': now,
            'x_unitrade_blocked_by': actor.id,
        })

        # Cascade block to chat if module available
        if 'x_unitrade_chat_blocked' in self._fields:
            self.sudo().write({
                'x_unitrade_chat_blocked': True,
                'x_unitrade_chat_block_reason': reason[:120],
            })

        self._unitrade_audit_note(
            _('Akun %s diblokir oleh %s. Alasan: %s') % (self.name, actor.name, reason)
        )
        log_admin_action(
            self.env,
            'user.block',
            description=_('Akun %s diblokir oleh %s. Alasan: %s') % (self.name, actor.name, reason),
            record=self,
            severity='critical',
            payload={'user_id': self.id, 'login': self.login, 'reason': reason},
        )
        _logger.info(
            'UniTrade user blocked: id=%s by=%s reason=%s',
            self.id, actor.name, reason,
        )
        return True

    def _unitrade_audit_note(self, body):
        """Write an audit note on the seller chatter if exists, else on partner chatter."""
        self.ensure_one()
        if self.x_seller_id:
            self.x_seller_id.sudo().message_post(
                body=body,
                subtype_xmlid='mail.mt_note',
            )
            return
        partner = self.partner_id
        if partner and hasattr(partner, 'message_post'):
            partner.sudo().message_post(
                body=body,
                subtype_xmlid='mail.mt_note',
            )

    # Note: blocking prevents authentication via _check_credentials override.
    # The user record remains active (not archived) so admins can always find
    # them in lists and reopen the block with full context.

    def _check_credentials(self, password, env):
        """Prevent blocked UniTrade users from authenticating."""
        result = super()._check_credentials(password, env)
        if self.x_unitrade_is_blocked:
            _logger.warning(
                'Blocked UniTrade user attempted login: uid=%s login=%s',
                self.id, self.login,
            )
            raise AccessDenied(_('Akun Anda telah diblokir oleh admin UniTrade.'))
        return result

    def action_send_otp(self):
        """Send OTP verification email using unitrade.otp as the source of truth."""
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

        otp_record = self.env['unitrade.otp'].sudo().generate_otp(
            self.id,
            self.email or self.login,
            purpose='account_verification',
        )

        self.write({
            'x_otp_code': otp_record.code,
            'x_otp_expiry': otp_record.expires_at,
            'x_otp_attempts': self.x_otp_attempts + 1,
        })

        # Send OTP via email
        template = self.env.ref(
            'unitrade_seller.mail_template_otp',
            raise_if_not_found=False,
        )
        if template:
            template.sudo().send_mail(self.id, force_send=True)
            _logger.info('OTP sent to user %s (%s)', self.name, self.email)
            self.write({'x_otp_code': False})
        else:
            _logger.warning('OTP mail template not found')
            self.write({'x_otp_code': False})

        return True

    def action_verify_otp(self, otp_input):
        """Verify OTP code submitted by user using unitrade.otp."""
        self.ensure_one()

        if not otp_input:
            raise ValidationError(_('Belum ada OTP yang dikirim. Kirim OTP terlebih dahulu.'))

        if self.x_otp_expiry and self.x_otp_expiry < fields.Datetime.now():
            raise ValidationError(_('Kode OTP sudah kadaluarsa. Kirim ulang OTP.'))

        if not self.env['unitrade.otp'].sudo().verify_otp(
            self.id,
            otp_input,
            purpose='account_verification',
        ):
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
