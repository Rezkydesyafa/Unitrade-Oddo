"""Wizards for UniTrade product admin actions: waive fee, reject listing."""
import logging

from odoo import _, api, fields, models
from odoo.exceptions import AccessDenied, UserError, ValidationError

_logger = logging.getLogger(__name__)


def _check_admin(env, action_label):
    user = env.user
    is_admin = (
        user.has_group('unitrade_seller.group_unitrade_admin')
        or user.has_group('base.group_system')
    )
    if not is_admin:
        _logger.warning(
            'Product wizard: unauthorized %s by uid=%s', action_label, env.uid,
        )
        raise AccessDenied(_('Aksi ini hanya boleh dilakukan oleh admin UniTrade.'))


def _audit(env, action, description, record=None, severity='info', payload=None):
    if 'unitrade.admin.audit.log' not in env.registry:
        return
    try:
        env['unitrade.admin.audit.log'].sudo().log_action(
            action,
            description=description,
            record=record,
            severity=severity,
            payload=payload,
        )
    except Exception:  # noqa: BLE001
        _logger.exception('Failed to write audit log: %s', action)


class UnitradeProductWaiveWizard(models.TransientModel):
    _name = 'unitrade.product.waive.wizard'
    _description = 'Waive Listing Fee Wizard'

    product_id = fields.Many2one(
        'product.template',
        string='Produk',
        required=True,
        readonly=True,
    )
    product_seller_id = fields.Many2one(
        related='product_id.x_seller_id',
        string='Seller',
        readonly=True,
    )
    current_fee_status = fields.Selection(
        related='product_id.x_listing_fee_status',
        string='Status Fee Sekarang',
        readonly=True,
    )
    reason = fields.Text(
        string='Alasan Waive',
        required=True,
        help='Alasan kenapa fee listing produk ini dibebaskan. Wajib diisi.',
    )
    publish_after = fields.Boolean(
        string='Auto-Publish Setelah Waive',
        default=True,
        help='Centang jika produk langsung dipublikasikan setelah fee diwaiver.',
    )

    @api.constrains('reason')
    def _check_reason(self):
        for record in self:
            if not (record.reason or '').strip():
                raise ValidationError(_('Alasan waive wajib diisi.'))

    def action_confirm(self):
        _check_admin(self.env, 'waive_listing_fee')
        self.ensure_one()
        product = self.product_id
        if not product.exists():
            raise UserError(_('Produk tidak ditemukan.'))

        now = fields.Datetime.now()
        product.sudo().write({
            'x_listing_fee_status': 'waived',
            'x_listing_fee_waived_by_id': self.env.user.id,
            'x_listing_fee_waive_reason': self.reason.strip(),
            'x_listing_fee_paid_at': now,
        })
        if self.publish_after:
            product.sudo().write({
                'x_is_marketplace': True,
                'sale_ok': True,
                'website_published': True,
                'active': True,
            })
        if hasattr(product, 'message_post'):
            product.sudo().message_post(
                body=_('Fee listing diwaiver oleh %s. Alasan: %s') % (
                    self.env.user.name, self.reason.strip(),
                ),
                subtype_xmlid='mail.mt_note',
            )
        _audit(
            self.env,
            'product.fee.waive',
            description=_('Fee listing produk %s diwaiver oleh %s. Alasan: %s') % (
                product.display_name, self.env.user.name, self.reason.strip(),
            ),
            record=product,
            severity='warning',
            payload={
                'product_id': product.id,
                'seller_id': product.x_seller_id.id,
                'reason': self.reason.strip(),
                'published_after': self.publish_after,
            },
        )
        return {'type': 'ir.actions.act_window_close'}


class UnitradeProductRejectWizard(models.TransientModel):
    _name = 'unitrade.product.reject.wizard'
    _description = 'Reject Marketplace Listing Wizard'

    product_id = fields.Many2one(
        'product.template',
        string='Produk',
        required=True,
        readonly=True,
    )
    product_seller_id = fields.Many2one(
        related='product_id.x_seller_id',
        string='Seller',
        readonly=True,
    )
    reason = fields.Text(
        string='Alasan Rejeksi',
        required=True,
        help='Alasan kenapa produk ini ditolak listing-nya.',
    )

    @api.constrains('reason')
    def _check_reason(self):
        for record in self:
            if not (record.reason or '').strip():
                raise ValidationError(_('Alasan rejeksi wajib diisi.'))

    def action_confirm(self):
        _check_admin(self.env, 'reject_listing')
        self.ensure_one()
        product = self.product_id
        if not product.exists():
            raise UserError(_('Produk tidak ditemukan.'))
        product.sudo().write({
            'website_published': False,
            'sale_ok': False,
            'x_listing_fee_status': 'failed',
            'x_listing_activated_at': False,
            'x_listing_expires_at': False,
            'x_listing_rejected_by_id': self.env.user.id,
            'x_listing_rejection_reason': self.reason.strip(),
        })
        if hasattr(product, 'message_post'):
            product.sudo().message_post(
                body=_('Listing direjeksi oleh %s. Alasan: %s') % (
                    self.env.user.name, self.reason.strip(),
                ),
                subtype_xmlid='mail.mt_note',
            )
        _audit(
            self.env,
            'product.listing.reject',
            description=_('Listing produk %s ditolak oleh %s. Alasan: %s') % (
                product.display_name, self.env.user.name, self.reason.strip(),
            ),
            record=product,
            severity='critical',
            payload={
                'product_id': product.id,
                'seller_id': product.x_seller_id.id,
                'reason': self.reason.strip(),
            },
        )
        return {'type': 'ir.actions.act_window_close'}
