from odoo import fields, models


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
