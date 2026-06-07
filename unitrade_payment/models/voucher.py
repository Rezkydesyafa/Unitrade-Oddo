import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class UnitradeVoucher(models.Model):
    _name = 'unitrade.voucher'
    _description = 'UniTrade Voucher'
    _order = 'create_date desc'

    active = fields.Boolean(default=True)
    code = fields.Char(required=True, index=True)
    name = fields.Char(required=True)
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    discount_type = fields.Selection([
        ('fixed', 'Fixed Amount'),
        ('percent', 'Percentage'),
    ], default='fixed', required=True)
    discount_amount = fields.Monetary(currency_field='currency_id')
    discount_percent = fields.Float()
    min_order_amount = fields.Monetary(currency_field='currency_id')
    date_start = fields.Datetime()
    date_end = fields.Datetime()
    usage_limit = fields.Integer(default=0)
    usage_limit_per_user = fields.Integer(default=0)

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'Voucher code must be unique.'),
    ]

    @api.model
    def _normalize_code(self, code):
        """Return the canonical voucher code used by admin and checkout."""
        value = str(code or '').strip().upper()
        return re.sub(r'\s+', '', value)

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if values.get('code'):
                values['code'] = self._normalize_code(values.get('code'))
        return super().create(vals_list)

    def write(self, values):
        if values.get('code'):
            values = dict(values)
            values['code'] = self._normalize_code(values.get('code'))
        return super().write(values)

    @api.constrains('code', 'discount_type', 'discount_amount', 'discount_percent', 'date_start', 'date_end')
    def _check_voucher_values(self):
        for voucher in self:
            if not voucher._normalize_code(voucher.code):
                raise ValidationError(_('Kode voucher wajib diisi.'))
            if voucher.discount_type == 'fixed' and voucher.discount_amount <= 0:
                raise ValidationError(_('Nominal diskon wajib lebih dari 0.'))
            if voucher.discount_type == 'percent' and (
                voucher.discount_percent <= 0 or voucher.discount_percent > 100
            ):
                raise ValidationError(_('Diskon persen harus di antara 0 sampai 100.'))
            if voucher.date_start and voucher.date_end and voucher.date_end < voucher.date_start:
                raise ValidationError(_('Tanggal berakhir tidak boleh lebih awal dari tanggal mulai.'))

    def _redeemed_order_domain(self, user=False, exclude_order=False):
        self.ensure_one()
        domain = [
            ('x_unitrade_voucher_id', '=', self.id),
            ('state', 'in', ('sale', 'done')),
        ]
        Order = self.env['sale.order']
        if 'x_payment_status' in Order._fields:
            domain.append(('x_payment_status', 'not in', ('cancelled', 'failed', 'expired')))
        if exclude_order:
            domain.append(('id', '!=', exclude_order.id))
        if user and getattr(user, 'partner_id', False):
            domain.append(('partner_id', 'child_of', user.partner_id.commercial_partner_id.id))
        return domain

    def _usage_count(self, exclude_order=False):
        self.ensure_one()
        return self.env['sale.order'].sudo().search_count(
            self._redeemed_order_domain(exclude_order=exclude_order)
        )

    def _usage_count_for_user(self, user, exclude_order=False):
        self.ensure_one()
        if not user or not getattr(user, 'partner_id', False):
            return 0
        return self.env['sale.order'].sudo().search_count(
            self._redeemed_order_domain(user=user, exclude_order=exclude_order)
        )

    def _validate_for_order(self, order, user=False, subtotal=None):
        self.ensure_one()
        order = order.sudo()
        now = fields.Datetime.now()
        subtotal = order.currency_id.round(subtotal if subtotal is not None else order.amount_untaxed)

        if not self.active:
            raise ValidationError(_('Voucher ini sedang nonaktif.'))
        if self.date_start and self.date_start > now:
            raise ValidationError(_('Voucher belum mulai berlaku.'))
        if self.date_end and self.date_end < now:
            raise ValidationError(_('Voucher sudah kedaluwarsa.'))
        if self.min_order_amount and subtotal < self.min_order_amount:
            raise ValidationError(_('Minimum order untuk voucher ini belum terpenuhi.'))
        if self.usage_limit and self._usage_count(exclude_order=order) >= self.usage_limit:
            raise ValidationError(_('Kuota voucher sudah habis.'))
        if (
            self.usage_limit_per_user
            and user
            and self._usage_count_for_user(user, exclude_order=order) >= self.usage_limit_per_user
        ):
            raise ValidationError(_('Limit pemakaian voucher untuk akun Anda sudah habis.'))
        return True

    def _discount_for_order(self, order, subtotal=None):
        self.ensure_one()
        currency = order.currency_id
        subtotal = currency.round(subtotal if subtotal is not None else order.amount_untaxed)
        if subtotal <= 0:
            return 0.0
        if self.discount_type == 'percent':
            discount = subtotal * (self.discount_percent or 0.0) / 100.0
        else:
            discount = self.discount_amount or 0.0
        return currency.round(min(max(discount, 0.0), subtotal))
