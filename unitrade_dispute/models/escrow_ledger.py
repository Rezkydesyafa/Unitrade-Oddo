from odoo import fields, models


class UnitradeEscrowLedgerDispute(models.Model):
    _inherit = 'unitrade.escrow.ledger'

    refund_dispute_id = fields.Many2one(
        'unitrade.dispute',
        string='Refund Dispute',
        readonly=True,
        copy=False,
        ondelete='set null',
    )
