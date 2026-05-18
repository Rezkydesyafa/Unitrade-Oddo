import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class UnitradeDispute(models.Model):
    _name = 'unitrade.dispute'
    _description = 'UniTrade Refund Dispute'
    _order = 'create_date desc'

    ACTIVE_STATES = ('submitted', 'under_review', 'need_buyer_evidence', 'need_seller_response')
    FINAL_STATES = ('approved', 'rejected', 'resolved', 'cancelled')

    name = fields.Char(required=True, readonly=True, copy=False, default='New')
    dispute_type = fields.Selection([
        ('refund', 'Refund'),
    ], default='refund', required=True, readonly=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('under_review', 'Under Review'),
        ('need_buyer_evidence', 'Need Buyer Evidence'),
        ('need_seller_response', 'Need Seller Response'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('resolved', 'Resolved'),
        ('cancelled', 'Cancelled'),
    ], default='draft', required=True, index=True)
    order_id = fields.Many2one('sale.order', required=True, index=True, ondelete='cascade')
    order_line_id = fields.Many2one('sale.order.line', index=True, ondelete='set null')
    payment_intent_id = fields.Many2one('unitrade.payment.intent', index=True, ondelete='set null')
    escrow_ledger_id = fields.Many2one('unitrade.escrow.ledger', string='Escrow Ledger', index=True, ondelete='set null')
    buyer_id = fields.Many2one('res.partner', string='Buyer', required=True, index=True, ondelete='restrict')
    seller_id = fields.Many2one('unitrade.seller', string='Seller', index=True, ondelete='set null')
    reason_code = fields.Selection([
        ('seller_no_handoff', 'Seller tidak menyerahkan barang'),
        ('not_as_described', 'Barang tidak sesuai deskripsi'),
        ('damaged', 'Barang rusak/tidak berfungsi'),
        ('wrong_item', 'Salah barang'),
        ('other', 'Lainnya'),
    ], required=True)
    reason_note = fields.Text(required=True)
    requested_amount = fields.Monetary(currency_field='currency_id', required=True)
    approved_amount = fields.Monetary(currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency',
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    admin_id = fields.Many2one('res.users', string='Admin/CS', copy=False)
    admin_decision_note = fields.Text(copy=False)
    submitted_at = fields.Datetime(copy=False)
    review_started_at = fields.Datetime(copy=False)
    approved_at = fields.Datetime(copy=False)
    rejected_at = fields.Datetime(copy=False)
    resolved_at = fields.Datetime(copy=False)
    evidence_ids = fields.One2many('unitrade.dispute.evidence', 'dispute_id', string='Evidence')

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env['ir.sequence'].sudo()
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = sequence.next_by_code('unitrade.dispute.refund') or 'RFD'
        return super().create(vals_list)

    @api.constrains('requested_amount', 'approved_amount')
    def _check_amounts(self):
        for dispute in self:
            if dispute.requested_amount <= 0:
                raise ValidationError(_('Nominal refund harus lebih dari 0.'))
            if dispute.approved_amount and dispute.approved_amount < 0:
                raise ValidationError(_('Nominal refund disetujui tidak boleh negatif.'))
            if dispute.approved_amount and dispute.approved_amount > dispute.requested_amount:
                raise ValidationError(_('Nominal refund disetujui tidak boleh melebihi nominal pengajuan.'))

    def _set_order_refund_state(self, state):
        for dispute in self.sudo():
            order = dispute.order_id.sudo()
            values = {
                'x_refund_dispute_id': dispute.id,
                'x_refund_state': state,
            }
            if state == 'approved':
                values['x_refunded_at'] = fields.Datetime.now()
            order.write(values)

    def _hold_escrow_for_review(self):
        for dispute in self.sudo():
            ledger = dispute.escrow_ledger_id
            if ledger and ledger.state not in ('refunded', 'released', 'cancelled'):
                ledger.write({
                    'state': 'disputed',
                    'refund_dispute_id': dispute.id,
                })
                ledger._sync_order_escrow_state()
            dispute.order_id.sudo().write({
                'x_escrow_state': 'disputed',
                'x_refund_dispute_id': dispute.id,
                'x_refund_state': dispute.state,
            })

    def action_submit(self):
        now = fields.Datetime.now()
        for dispute in self.sudo():
            if dispute.state not in ('draft', 'submitted'):
                continue
            dispute.write({
                'state': 'submitted',
                'submitted_at': dispute.submitted_at or now,
            })
        self._hold_escrow_for_review()
        self._set_order_refund_state('submitted')
        return True

    def action_start_review(self):
        now = fields.Datetime.now()
        self.sudo().write({
            'state': 'under_review',
            'review_started_at': now,
            'admin_id': self.env.user.id,
        })
        self._set_order_refund_state('under_review')
        return True

    def action_need_buyer_evidence(self):
        self.sudo().write({
            'state': 'need_buyer_evidence',
            'admin_id': self.env.user.id,
        })
        self._set_order_refund_state('need_buyer_evidence')
        return True

    def action_need_seller_response(self):
        self.sudo().write({
            'state': 'need_seller_response',
            'admin_id': self.env.user.id,
        })
        self._set_order_refund_state('need_seller_response')
        return True

    def action_approve_refund(self):
        now = fields.Datetime.now()
        for dispute in self.sudo():
            if dispute.state in ('cancelled', 'rejected', 'resolved'):
                raise UserError(_('Refund case %s sudah tidak bisa di-approve.') % dispute.name)
            approved_amount = dispute.approved_amount or dispute.requested_amount
            ledger = dispute.escrow_ledger_id
            order = dispute.order_id
            intent = dispute.payment_intent_id or order.x_payment_intent_id
            dispute.write({
                'state': 'approved',
                'approved_amount': approved_amount,
                'approved_at': now,
                'resolved_at': now,
                'admin_id': self.env.user.id,
            })
            if ledger:
                ledger.write({
                    'state': 'refunded',
                    'refund_dispute_id': dispute.id,
                })
            if intent:
                intent.sudo().write({'state': 'refunded'})
            order.sudo().write({
                'x_payment_status': 'refunded',
                'x_unitrade_order_state': 'refunded',
                'x_escrow_state': 'refunded',
                'x_refund_dispute_id': dispute.id,
                'x_refund_state': 'approved',
                'x_refunded_at': now,
            })
            if ledger:
                ledger._sync_order_escrow_state()
            _logger.info('Refund dispute %s approved by user %s', dispute.name, self.env.user.id)
        return True

    def action_reject_refund(self):
        now = fields.Datetime.now()
        for dispute in self.sudo():
            if dispute.state in ('approved', 'cancelled', 'resolved'):
                raise UserError(_('Refund case %s sudah tidak bisa ditolak.') % dispute.name)
            ledger = dispute.escrow_ledger_id
            dispute.write({
                'state': 'rejected',
                'rejected_at': now,
                'resolved_at': now,
                'admin_id': self.env.user.id,
            })
            if ledger and ledger.state == 'disputed':
                ledger.write({'state': 'held'})
                ledger._sync_order_escrow_state()
            dispute.order_id.sudo().write({
                'x_refund_dispute_id': dispute.id,
                'x_refund_state': 'rejected',
                'x_escrow_state': 'held',
            })
            _logger.info('Refund dispute %s rejected by user %s', dispute.name, self.env.user.id)
        return True

    def action_cancel(self):
        for dispute in self.sudo():
            if dispute.state in ('approved', 'rejected', 'resolved'):
                raise UserError(_('Refund case yang sudah selesai tidak bisa dibatalkan.'))
            ledger = dispute.escrow_ledger_id
            dispute.write({'state': 'cancelled'})
            if ledger and ledger.state == 'disputed':
                ledger.write({'state': 'held'})
                ledger._sync_order_escrow_state()
            dispute.order_id.sudo().write({
                'x_refund_state': 'cancelled',
                'x_escrow_state': 'held',
            })
        return True

    def action_seller_respond(self, note='', evidence_items=None):
        evidence_items = evidence_items or []
        now = fields.Datetime.now()
        for dispute in self.sudo():
            if dispute.state in self.FINAL_STATES:
                raise UserError(_('Refund case ini sudah selesai.'))
            if not evidence_items and not note:
                raise UserError(_('Seller wajib menambahkan catatan atau bukti.'))
            for item in evidence_items:
                attachment_id = item.get('attachment_id') or False
                if not attachment_id and item.get('datas'):
                    attachment = self.env['ir.attachment'].sudo().create({
                        'name': item.get('name') or 'bukti-respons-seller',
                        'datas': item.get('datas'),
                        'mimetype': item.get('mimetype') or False,
                        'res_model': 'unitrade.dispute',
                        'res_id': dispute.id,
                    })
                    attachment_id = attachment.id
                self.env['unitrade.dispute.evidence'].sudo().create({
                    'dispute_id': dispute.id,
                    'submitted_by_id': item.get('submitted_by_id') or self.env.user.id,
                    'evidence_type': item.get('evidence_type') or 'seller_response',
                    'attachment_id': attachment_id,
                    'url': item.get('url') or False,
                    'note': item.get('note') or note or False,
                })
            if note and not evidence_items:
                self.env['unitrade.dispute.evidence'].sudo().create({
                    'dispute_id': dispute.id,
                    'submitted_by_id': self.env.user.id,
                    'evidence_type': 'seller_response',
                    'note': note,
                })
            dispute.write({
                'state': 'under_review',
                'review_started_at': dispute.review_started_at or now,
            })
        self._set_order_refund_state('under_review')
        return True

    def action_open_related_order(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': self.order_id.id,
            'view_mode': 'form',
        }


class UnitradeDisputeEvidence(models.Model):
    _name = 'unitrade.dispute.evidence'
    _description = 'UniTrade Dispute Evidence'
    _order = 'create_date desc'

    dispute_id = fields.Many2one('unitrade.dispute', required=True, index=True, ondelete='cascade')
    submitted_by_id = fields.Many2one('res.users', string='Submitted By', index=True, ondelete='set null')
    evidence_type = fields.Selection([
        ('buyer_photo', 'Buyer Photo'),
        ('unboxing_video', 'Unboxing Video'),
        ('packing_video', 'Packing Video'),
        ('seller_response', 'Seller Response'),
        ('google_drive_url', 'Google Drive URL'),
        ('other', 'Other'),
    ], default='other', required=True)
    attachment_id = fields.Many2one('ir.attachment', string='Attachment', ondelete='set null')
    url = fields.Char()
    note = fields.Text()
    created_at = fields.Datetime(default=fields.Datetime.now, readonly=True)

    def action_open_attachment(self):
        self.ensure_one()
        if not self.attachment_id:
            raise UserError(_('Evidence ini tidak memiliki attachment.'))
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % self.attachment_id.id,
            'target': 'self',
        }
