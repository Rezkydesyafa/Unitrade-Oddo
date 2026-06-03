from odoo import fields, models


class UnitradePaymentEvent(models.Model):
    _name = 'unitrade.payment.event'
    _description = 'UniTrade Payment Event'
    _order = 'create_date desc'

    name = fields.Char(required=True, index=True)
    provider = fields.Selection([
        ('xendit', 'Xendit'),
        ('doku', 'DOKU'),
        ('midtrans', 'Midtrans'),
    ], default='midtrans', required=True, index=True)
    state = fields.Selection([
        ('received', 'Received'),
        ('processed', 'Processed'),
        ('failed', 'Failed'),
    ], default='received', required=True, index=True)
    event_key = fields.Char(index=True)
    request_id = fields.Char(index=True)
    payload_hash = fields.Char(index=True)
    payload_json = fields.Text()
    payment_intent_id = fields.Many2one('unitrade.payment.intent', index=True, ondelete='set null')
    order_id = fields.Many2one('sale.order', index=True, ondelete='set null')
    error_message = fields.Text()

    _sql_constraints = [
        ('event_key_unique', 'unique(event_key)', 'Payment event key must be unique.'),
    ]
