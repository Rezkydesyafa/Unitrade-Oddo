import logging

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class UnitradeVoucher(models.Model):
    _name = 'unitrade.voucher'
    _description = 'UniTrade Checkout Voucher'
    _order = 'active desc, date_end desc, id desc'

    name = fields.Char(string='Nama Voucher', required=True)
    code = fields.Char(string='Kode Voucher', required=True, index=True)
    active = fields.Boolean(string='Aktif', default=True)
    date_start = fields.Datetime(string='Mulai Berlaku')
    date_end = fields.Datetime(string='Berakhir')
    discount_type = fields.Selection([
        ('fixed', 'Nominal'),
        ('percent', 'Persen'),
    ], string='Tipe Diskon', default='fixed', required=True)
    discount_amount = fields.Monetary(string='Nominal Diskon', currency_field='currency_id')
    discount_percent = fields.Float(string='Persen Diskon')
    min_order_amount = fields.Monetary(string='Minimum Order', currency_field='currency_id')
    usage_limit = fields.Integer(string='Limit Pemakaian Global')
    usage_limit_per_user = fields.Integer(string='Limit Pemakaian per User')
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id.id,
        required=True,
    )

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'Kode voucher harus unik.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code'):
                vals['code'] = self._normalize_code(vals['code'])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('code'):
            vals = dict(vals, code=self._normalize_code(vals['code']))
        return super().write(vals)

    @api.constrains('discount_amount', 'discount_percent', 'min_order_amount', 'usage_limit', 'usage_limit_per_user')
    def _check_values(self):
        for voucher in self:
            if voucher.discount_amount < 0 or voucher.discount_percent < 0 or voucher.min_order_amount < 0:
                raise ValidationError(_('Nilai voucher tidak boleh negatif.'))
            if voucher.discount_type == 'percent' and voucher.discount_percent > 100:
                raise ValidationError(_('Diskon persen tidak boleh lebih dari 100%.'))
            if voucher.usage_limit < 0 or voucher.usage_limit_per_user < 0:
                raise ValidationError(_('Limit pemakaian tidak boleh negatif.'))

    @api.model
    def _normalize_code(self, code):
        return (code or '').strip().upper()

    def _usage_domain(self):
        self.ensure_one()
        return [
            ('x_unitrade_voucher_id', '=', self.id),
            ('state', 'in', ('sale', 'done')),
            ('x_payment_status', 'not in', ('cancelled', 'failed', 'expired')),
        ]

    def _usage_count(self, user=False):
        self.ensure_one()
        domain = self._usage_domain()
        if user:
            domain.append(('partner_id', '=', user.partner_id.id))
        return self.env['sale.order'].sudo().search_count(domain)

    def _validate_for_order(self, order, user=False, subtotal=False):
        self.ensure_one()
        now = fields.Datetime.now()
        subtotal = subtotal if subtotal is not None else order.currency_id.round(
            sum(order._unitrade_product_lines_for_checkout().mapped('price_subtotal'))
        )
        if not self.active:
            raise ValidationError(_('Voucher tidak aktif.'))
        if self.date_start and self.date_start > now:
            raise ValidationError(_('Voucher belum berlaku.'))
        if self.date_end and self.date_end < now:
            raise ValidationError(_('Voucher sudah kedaluwarsa.'))
        if self.min_order_amount and subtotal < self.min_order_amount:
            raise ValidationError(_('Minimum order untuk voucher ini belum terpenuhi.'))
        if self.usage_limit and self._usage_count() >= self.usage_limit:
            raise ValidationError(_('Kuota voucher sudah habis.'))
        if user and self.usage_limit_per_user and self._usage_count(user=user) >= self.usage_limit_per_user:
            raise ValidationError(_('Voucher sudah mencapai batas pemakaian untuk akun Anda.'))
        return True

    def _discount_for_order(self, order, subtotal=False):
        self.ensure_one()
        subtotal = subtotal if subtotal is not None else order.currency_id.round(
            sum(order._unitrade_product_lines_for_checkout().mapped('price_subtotal'))
        )
        if subtotal <= 0:
            return 0.0
        if self.discount_type == 'percent':
            discount = subtotal * (self.discount_percent or 0.0) / 100.0
        else:
            discount = self.discount_amount or 0.0
        return order.currency_id.round(min(discount, subtotal))
