from odoo import fields, models


class UnitradePaymentEvent(models.Model):
    _name = 'unitrade.payment.event'
    _description = 'UniTrade Payment Event'
    _order = 'create_date desc'

    name = fields.Char(required=True, readonly=True, copy=False)
    provider = fields.Selection([
        ('xendit', 'Xendit'),
        ('doku', 'DOKU'),
        ('midtrans', 'Midtrans'),
    ], default='midtrans', required=True)
    event_key = fields.Char(required=True, index=True, copy=False)
    request_id = fields.Char(index=True, copy=False)
    payload_hash = fields.Char(index=True, copy=False)
    payload_json = fields.Text(copy=False)
    state = fields.Selection([
        ('received', 'Received'),
        ('processed', 'Processed'),
        ('duplicate', 'Duplicate'),
        ('failed', 'Failed'),
    ], default='received', required=True, index=True)
    payment_intent_id = fields.Many2one('unitrade.payment.intent', ondelete='set null')
    order_id = fields.Many2one('sale.order', ondelete='set null')
    error_message = fields.Text(copy=False)

    _sql_constraints = [
        ('event_key_unique', 'unique(event_key)', 'Event pembayaran sudah pernah diproses.'),
    ]
