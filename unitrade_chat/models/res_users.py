import uuid

from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    x_unitrade_chat_bus_token = fields.Char(
        string='UniTrade Chat Bus Token',
        copy=False,
        readonly=True,
        default=lambda self: str(uuid.uuid4()),
    )
    x_unitrade_chat_last_seen = fields.Datetime(
        string='UniTrade Chat Last Seen',
        copy=False,
    )
    x_unitrade_chat_blocked = fields.Boolean(
        string='UniTrade Chat Blocked',
        default=False,
        copy=False,
    )
    x_unitrade_chat_block_reason = fields.Char(
        string='UniTrade Chat Block Reason',
        copy=False,
    )

    def _unitrade_chat_bus_target(self):
        self.ensure_one()
        if not self.x_unitrade_chat_bus_token:
            self.sudo().write({'x_unitrade_chat_bus_token': str(uuid.uuid4())})
        return 'unitrade_chat_user_%s' % self.x_unitrade_chat_bus_token
