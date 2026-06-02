from odoo import models, fields, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class UnitradeUserBlockWizard(models.TransientModel):
    """Wizard to block a UniTrade user account with a required reason."""

    _name = 'unitrade.user.block.wizard'
    _description = 'UniTrade Blokir User Wizard'

    user_id = fields.Many2one(
        'res.users',
        string='User',
        required=True,
        readonly=True,
    )
    user_name = fields.Char(
        string='Nama User',
        related='user_id.name',
        readonly=True,
    )
    user_login = fields.Char(
        string='Email / Login',
        related='user_id.login',
        readonly=True,
    )
    user_is_seller = fields.Boolean(
        string='Seller Terverifikasi?',
        related='user_id.x_is_seller',
        readonly=True,
    )
    reason_category = fields.Selection(
        selection=[
            ('fraud', 'Dugaan Penipuan'),
            ('policy', 'Pelanggaran Kebijakan'),
            ('spam', 'Spam / Penyalahgunaan'),
            ('chat_abuse', 'Pelecehan di Chat'),
            ('fake_ktm', 'KTM Palsu / Identitas Tidak Valid'),
            ('other', 'Lainnya'),
        ],
        string='Kategori Alasan',
        required=True,
        default='policy',
    )
    reason_detail = fields.Text(
        string='Detail Alasan',
        required=True,
        help='Wajib diisi. Alasan ini akan dicatat di audit log.',
    )
    revoke_seller = fields.Boolean(
        string='Cabut juga verifikasi seller',
        default=True,
        help='Jika aktif dan user adalah seller terverifikasi, verifikasi seller akan ikut dicabut.',
    )

    def _combined_reason(self):
        self.ensure_one()
        label = dict(self._fields['reason_category'].selection).get(
            self.reason_category, self.reason_category
        )
        return '[%s] %s' % (label, (self.reason_detail or '').strip())

    def action_confirm_block(self):
        """Apply block to the selected user."""
        self.ensure_one()

        if not self.reason_detail or not self.reason_detail.strip():
            raise ValidationError(_('Detail alasan blokir wajib diisi.'))

        user = self.user_id
        reason = self._combined_reason()

        # Apply block
        user._unitrade_apply_block(reason)

        # Optionally revoke seller verification
        if self.revoke_seller and user.x_seller_id and user.x_seller_id.status == 'verified':
            user.x_seller_id.sudo().write({'revoke_reason': reason})
            user.x_seller_id.action_revoke_seller_verification()

        # Return to the user form to reflect updated state
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'res.users',
            'res_id': user.id,
            'view_mode': 'form',
            'target': 'current',
        }
