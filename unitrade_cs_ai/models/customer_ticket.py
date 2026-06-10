from odoo import fields, models


class CustomerTicketCsAi(models.Model):
    _inherit = 'unitrade.customer.ticket'

    cs_session_id = fields.Many2one(
        'unitrade.cs.session',
        string='Sesi CS AI',
        index=True,
        ondelete='set null',
        copy=False,
    )
    ai_handled = fields.Boolean(string='Pernah Ditangani AI', default=False, copy=False)
    escalated_at = fields.Datetime(string='Waktu Eskalasi', copy=False)
