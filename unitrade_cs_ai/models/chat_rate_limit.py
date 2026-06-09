from odoo import fields, models


class ChatRateLimitCsAi(models.Model):
    _inherit = 'unitrade.chat.rate.limit'

    action = fields.Selection(
        selection_add=[('cs_ai', 'CS AI Message')],
        ondelete={'cs_ai': 'cascade'},
    )
