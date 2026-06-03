from odoo import fields, models


class SaleOrderUnitradeDispute(models.Model):
    _inherit = 'sale.order'

    x_refund_dispute_id = fields.Many2one(
        'unitrade.dispute',
        string='Refund Dispute',
        readonly=True,
        copy=False,
        ondelete='set null',
    )
    x_refund_state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('under_review', 'Under Review'),
        ('need_buyer_evidence', 'Need Buyer Evidence'),
        ('need_seller_response', 'Need Seller Response'),
        ('admin_review_final', 'Admin Final Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('resolved', 'Resolved'),
        ('cancelled', 'Cancelled'),
    ], string='Refund State', readonly=True, copy=False)
    x_refunded_at = fields.Datetime(string='Refunded At', readonly=True, copy=False)
