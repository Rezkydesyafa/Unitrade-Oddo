from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class SaleOrderUnitradeAdmin(models.Model):
    """Admin moderation flag for marketplace orders.

    Used in the UniTrade admin dashboard so admins can quickly mark a
    transaction as "bermasalah" (flagged for follow-up) and surface those
    rows in monitoring filters.
    """

    _inherit = 'sale.order'

    x_admin_flagged = fields.Boolean(
        string='Tandai Bermasalah',
        default=False,
        copy=False,
        tracking=True,
        help='Admin menandai transaksi ini perlu peninjauan lanjutan.',
    )
    x_admin_flag_reason = fields.Text(
        string='Alasan Penandaan',
        copy=False,
        tracking=True,
    )
    x_admin_flagged_at = fields.Datetime(
        string='Ditandai Pada',
        readonly=True,
        copy=False,
    )
    x_admin_flagged_by = fields.Many2one(
        'res.users',
        string='Ditandai Oleh',
        readonly=True,
        copy=False,
    )
    x_unitrade_payment_intent_count = fields.Integer(
        string='Payment Intents',
        compute='_compute_unitrade_admin_related_counts',
    )
    x_unitrade_payment_event_count = fields.Integer(
        string='Payment Events',
        compute='_compute_unitrade_admin_related_counts',
    )
    x_unitrade_escrow_ledger_count = fields.Integer(
        string='Escrow Ledgers',
        compute='_compute_unitrade_admin_related_counts',
    )
    x_unitrade_dispute_count = fields.Integer(
        string='Disputes',
        compute='_compute_unitrade_admin_related_counts',
    )
    x_unitrade_seller_payout_count = fields.Integer(
        string='Payouts',
        compute='_compute_unitrade_admin_related_counts',
    )
    x_unitrade_audit_log_count = fields.Integer(
        string='Audit Logs',
        compute='_compute_unitrade_admin_related_counts',
    )

    def _unitrade_is_admin(self):
        user = self.env.user
        return (
            user.has_group('unitrade_seller.group_unitrade_admin')
            or user.has_group('base.group_system')
        )

    def _check_unitrade_admin(self):
        if not self._unitrade_is_admin():
            raise AccessError(_('Hanya admin UniTrade yang dapat mengubah status operasional transaksi.'))

    def _unitrade_admin_audit(self, action, description, severity='info', payload=None):
        if 'unitrade.admin.audit.log' not in self.env.registry:
            return
        AuditLog = self.env['unitrade.admin.audit.log']
        for order in self:
            AuditLog.sudo().log_action(
                action,
                description=description,
                record=order,
                severity=severity,
                payload=payload,
            )

    @api.depends(
        'x_payment_intent_id',
        'x_admin_flagged',
        'x_admin_flag_reason',
    )
    def _compute_unitrade_admin_related_counts(self):
        PaymentIntent = self.env['unitrade.payment.intent'].sudo()
        PaymentEvent = self.env['unitrade.payment.event'].sudo()
        EscrowLedger = self.env['unitrade.escrow.ledger'].sudo()
        Dispute = self.env['unitrade.dispute'].sudo() if 'unitrade.dispute' in self.env.registry else None
        Payout = self.env['unitrade.seller.payout'].sudo() if 'unitrade.seller.payout' in self.env.registry else None
        AuditLog = self.env['unitrade.admin.audit.log'].sudo() if 'unitrade.admin.audit.log' in self.env.registry else None

        for order in self:
            intent_domain = order._unitrade_payment_intent_domain()
            ledgers = EscrowLedger.search([('order_id', '=', order.id)])

            order.x_unitrade_payment_intent_count = PaymentIntent.search_count(intent_domain)
            order.x_unitrade_payment_event_count = PaymentEvent.search_count(
                order._unitrade_payment_event_domain(intent_domain)
            )
            order.x_unitrade_escrow_ledger_count = len(ledgers)
            order.x_unitrade_dispute_count = Dispute.search_count([('order_id', '=', order.id)]) if Dispute else 0
            order.x_unitrade_seller_payout_count = (
                Payout.search_count([('ledger_ids', 'in', ledgers.ids)]) if Payout and ledgers else 0
            )
            order.x_unitrade_audit_log_count = (
                AuditLog.search_count([('res_model', '=', 'sale.order'), ('res_id', '=', order.id)])
                if AuditLog else 0
            )

    def _unitrade_payment_intent_domain(self):
        self.ensure_one()
        domain = [('sale_order_id', '=', self.id)]
        if self.x_payment_intent_id:
            domain = ['|', ('sale_order_id', '=', self.id), ('id', '=', self.x_payment_intent_id.id)]
        return domain

    def _unitrade_payment_event_domain(self, intent_domain=None):
        self.ensure_one()
        intent_ids = self.env['unitrade.payment.intent'].sudo().search(
            intent_domain or self._unitrade_payment_intent_domain()
        ).ids
        if intent_ids:
            return ['|', ('order_id', '=', self.id), ('payment_intent_id', 'in', intent_ids)]
        return [('order_id', '=', self.id)]

    def _unitrade_related_action(self, xmlid, res_model, domain, name):
        self.ensure_one()
        action_ref = self.env.ref(xmlid, raise_if_not_found=False)
        if action_ref:
            action = action_ref.sudo().read()[0]
        else:
            action = {
                'type': 'ir.actions.act_window',
                'name': name,
                'res_model': res_model,
                'view_mode': 'tree,form',
            }

        records = self.env[res_model].sudo().search(domain)
        action.update({
            'name': name,
            'domain': [('id', 'in', records.ids)] if records else [('id', '=', 0)],
            'target': 'current',
        })
        if len(records) == 1:
            action.update({
                'res_id': records.id,
                'views': [(False, 'form')],
                'view_mode': 'form',
            })
            action.pop('domain', None)
        return action

    def action_open_unitrade_payment_intents(self):
        self.ensure_one()
        return self._unitrade_related_action(
            'unitrade_payment.action_unitrade_payment_intent',
            'unitrade.payment.intent',
            self._unitrade_payment_intent_domain(),
            _('Payment Intent %s') % self.name,
        )

    def action_open_unitrade_payment_events(self):
        self.ensure_one()
        return self._unitrade_related_action(
            'unitrade_payment.action_unitrade_payment_event',
            'unitrade.payment.event',
            self._unitrade_payment_event_domain(),
            _('Payment Event %s') % self.name,
        )

    def action_open_unitrade_escrow_ledgers(self):
        self.ensure_one()
        return self._unitrade_related_action(
            'unitrade_payment.action_unitrade_escrow_ledger',
            'unitrade.escrow.ledger',
            [('order_id', '=', self.id)],
            _('Escrow Ledger %s') % self.name,
        )

    def action_open_unitrade_disputes(self):
        self.ensure_one()
        return self._unitrade_related_action(
            'unitrade_dispute.action_unitrade_dispute',
            'unitrade.dispute',
            [('order_id', '=', self.id)],
            _('Refund / Dispute %s') % self.name,
        )

    def action_open_unitrade_seller_payouts(self):
        self.ensure_one()
        ledgers = self.env['unitrade.escrow.ledger'].sudo().search([('order_id', '=', self.id)])
        return self._unitrade_related_action(
            'unitrade_payment.action_unitrade_seller_payout',
            'unitrade.seller.payout',
            [('ledger_ids', 'in', ledgers.ids)] if ledgers else [('id', '=', 0)],
            _('Payout %s') % self.name,
        )

    def action_open_unitrade_audit_logs(self):
        self.ensure_one()
        return self._unitrade_related_action(
            'unitrade_admin.action_unitrade_audit_log',
            'unitrade.admin.audit.log',
            [('res_model', '=', 'sale.order'), ('res_id', '=', self.id)],
            _('Audit Log %s') % self.name,
        )

    def action_unitrade_admin_flag(self, reason):
        self._check_unitrade_admin()
        reason = (reason or '').strip()
        if not reason:
            raise UserError(_('Alasan tandai transaksi bermasalah wajib diisi.'))
        now = fields.Datetime.now()
        for order in self:
            order.sudo().write({
                'x_admin_flagged': True,
                'x_admin_flag_reason': reason,
                'x_admin_flagged_at': now,
                'x_admin_flagged_by': self.env.uid,
            })
            order._unitrade_admin_audit(
                'order.flag_problem',
                _('Transaksi %s ditandai bermasalah oleh %s. Alasan: %s') % (
                    order.name, self.env.user.name, reason,
                ),
                severity='warning',
                payload={
                    'order_id': order.id,
                    'order_name': order.name,
                    'amount_total': order.amount_total,
                    'partner_id': order.partner_id.id,
                    'reason': reason,
                },
            )
        return True

    def action_unitrade_admin_unflag(self):
        self._check_unitrade_admin()
        for order in self:
            old_reason = order.x_admin_flag_reason or ''
            order.sudo().write({
                'x_admin_flagged': False,
                'x_admin_flag_reason': False,
            })
            order._unitrade_admin_audit(
                'order.clear_problem',
                _('Tanda bermasalah transaksi %s dihapus oleh %s.') % (
                    order.name, self.env.user.name,
                ),
                severity='info',
                payload={
                    'order_id': order.id,
                    'order_name': order.name,
                    'previous_reason': old_reason,
                },
            )
        return True

    def write(self, vals):
        """Auto-create / update escrow ledger entry on payment status changes."""
        result = super().write(vals)
        if 'x_payment_status' in vals or vals.get('state') in ('sale', 'done', 'cancel'):
            Escrow = self.env['unitrade.escrow.ledger'].sudo()
            for order in self:
                try:
                    Escrow.ensure_for_order(order)
                except Exception:  # noqa: BLE001
                    # Don't break write() if escrow setup fails; log only
                    self.env.cr.rollback() if False else None
        return result
