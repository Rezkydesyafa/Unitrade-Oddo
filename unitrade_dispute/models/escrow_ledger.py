from odoo import fields, models


class UnitradeEscrowLedgerDispute(models.Model):
    _inherit = 'unitrade.escrow.ledger'

    refund_dispute_id = fields.Many2one('unitrade.dispute', string='Refund Case', copy=False, readonly=True)
