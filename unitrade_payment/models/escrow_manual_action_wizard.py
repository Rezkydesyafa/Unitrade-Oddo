from odoo import _, fields, models
from odoo.exceptions import UserError


class UnitradeEscrowManualActionWizard(models.TransientModel):
    _name = 'unitrade.escrow.manual.action.wizard'
    _description = 'UniTrade Escrow Manual Action Reason Wizard'

    action_type = fields.Selection([
        ('mark_releasable', 'Tandai Releasable'),
        ('mark_released', 'Tandai Released Manual'),
    ], required=True)
    ledger_ids = fields.Many2many(
        'unitrade.escrow.ledger',
        'unitrade_escrow_manual_action_wizard_rel',
        'wizard_id',
        'ledger_id',
        string='Escrow Ledgers',
        required=True,
    )
    reason = fields.Text(string='Alasan', required=True)

    def action_confirm(self):
        self.ensure_one()
        reason = (self.reason or '').strip()
        if not reason:
            raise UserError(_('Alasan wajib diisi.'))
        ledgers = self.ledger_ids.with_context(unitrade_manual_reason=reason)
        if self.action_type == 'mark_releasable':
            ledgers.action_mark_releasable()
            return {'type': 'ir.actions.act_window_close'}
        if self.action_type == 'mark_released':
            ledgers.action_mark_released()
            return {'type': 'ir.actions.act_window_close'}
        raise UserError(_('Aksi escrow tidak dikenali.'))
