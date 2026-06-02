import json
import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessDenied, AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)


class UnitradeDispute(models.Model):
    _name = 'unitrade.dispute'
    _description = 'UniTrade Refund Dispute'
    _order = 'create_date desc'

    ACTIVE_STATES = ('submitted', 'under_review', 'need_buyer_evidence', 'need_seller_response', 'admin_review_final')
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
        ('admin_review_final', 'Admin Final Review'),
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
    refund_admin_fee_amount = fields.Monetary(
        string='Refund Admin Fee',
        currency_field='currency_id',
        default=0.0,
        copy=False,
    )
    total_refund_amount = fields.Monetary(
        string='Total Refund',
        currency_field='currency_id',
        compute='_compute_total_refund_amount',
        store=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    admin_id = fields.Many2one('res.users', string='Admin Penengah', copy=False)
    admin_decision_note = fields.Text(copy=False)
    seller_decision_note = fields.Text(string='Seller Note', copy=False)
    seller_decision_user_id = fields.Many2one('res.users', string='Seller Decision User', copy=False)
    seller_decided_at = fields.Datetime(copy=False)
    submitted_at = fields.Datetime(copy=False)
    review_started_at = fields.Datetime(copy=False)
    approved_at = fields.Datetime(copy=False)
    rejected_at = fields.Datetime(copy=False)
    resolved_at = fields.Datetime(copy=False)
    final_decision_user_id = fields.Many2one('res.users', string='Final Decision By', copy=False, readonly=True)
    final_decision_role = fields.Selection([
        ('admin', 'Admin/CS'),
        ('seller', 'Seller'),
        ('system', 'System'),
    ], string='Final Decision Role', copy=False, readonly=True)
    final_decision_at = fields.Datetime(string='Final Decision At', copy=False, readonly=True)
    final_decision_snapshot = fields.Text(string='Final Decision Snapshot', copy=False, readonly=True)
    evidence_ids = fields.One2many('unitrade.dispute.evidence', 'dispute_id', string='Evidence')
    timeline_ids = fields.One2many('unitrade.dispute.timeline', 'dispute_id', string='Timeline')

    # SLA deadlines
    buyer_response_deadline_at = fields.Datetime(
        string='Deadline Bukti Buyer',
        copy=False,
        help='Buyer harus melengkapi bukti tambahan sebelum deadline ini.',
    )
    seller_response_deadline_at = fields.Datetime(
        string='Deadline Respons Seller',
        copy=False,
        help='Seller harus memberikan respons sebelum deadline ini.',
    )
    decision_deadline_at = fields.Datetime(
        string='Deadline Keputusan',
        copy=False,
        help='Admin harus memutuskan kasus ini sebelum deadline.',
    )
    is_overdue = fields.Boolean(
        string='Lewat SLA',
        compute='_compute_is_overdue',
        store=False,
        search='_search_is_overdue',
    )

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env['ir.sequence'].sudo()
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = sequence.next_by_code('unitrade.dispute.refund') or 'RFD'
        return super().create(vals_list)

    @api.depends('requested_amount', 'approved_amount', 'refund_admin_fee_amount')
    def _compute_total_refund_amount(self):
        for dispute in self:
            base_amount = dispute.approved_amount or dispute.requested_amount or 0.0
            admin_fee = dispute.refund_admin_fee_amount or 0.0
            dispute.total_refund_amount = max(base_amount - admin_fee, 0.0)

    @api.constrains('requested_amount', 'approved_amount', 'refund_admin_fee_amount')
    def _check_amounts(self):
        for dispute in self:
            if dispute.requested_amount <= 0:
                raise ValidationError(_('Nominal refund harus lebih dari 0.'))
            if dispute.approved_amount and dispute.approved_amount < 0:
                raise ValidationError(_('Nominal refund disetujui tidak boleh negatif.'))
            if dispute.approved_amount and dispute.approved_amount > dispute.requested_amount:
                raise ValidationError(_('Nominal refund disetujui tidak boleh melebihi nominal pengajuan.'))
            if dispute.refund_admin_fee_amount < 0:
                raise ValidationError(_('Biaya admin refund tidak boleh negatif.'))
            if dispute.refund_admin_fee_amount and dispute.refund_admin_fee_amount > dispute.requested_amount:
                raise ValidationError(_('Biaya admin refund tidak boleh melebihi nominal pengajuan.'))

    def _record_timeline_event(self, event_key, note=False, status='done', event_time=False):
        labels = dict(self.env['unitrade.dispute.timeline']._fields['event_key'].selection)
        sequences = {
            'order_created': 10,
            'payment_received': 20,
            'seller_handoff': 30,
            'buyer_received': 40,
            'return_requested': 50,
            'seller_review': 60,
            'seller_response': 65,
            'buyer_return_sent': 66,
            'seller_return_confirmed': 68,
            'admin_review_started': 69,
            'admin_review': 69,
            'refund_approved': 70,
            'refund_rejected': 70,
            'refund_completed': 80,
            'refund_cancelled': 80,
        }
        Timeline = self.env['unitrade.dispute.timeline'].sudo()
        now = event_time or fields.Datetime.now()
        for dispute in self.sudo():
            values = {
                'label': labels.get(event_key, event_key),
                'status': status,
                'event_time': now,
                'sequence': sequences.get(event_key, 100),
                'note': note or False,
            }
            timeline = Timeline.search([
                ('dispute_id', '=', dispute.id),
                ('event_key', '=', event_key),
            ], limit=1)
            if timeline:
                timeline.write(values)
            else:
                values.update({
                    'dispute_id': dispute.id,
                    'event_key': event_key,
                })
                Timeline.create(values)

    def _check_seller_decision_access(self):
        for dispute in self.sudo():
            seller_user = dispute.seller_id.sudo().user_id if dispute.seller_id else False
            if not seller_user or seller_user.id != self.env.user.id:
                raise AccessError(_('Anda hanya bisa mengambil keputusan untuk refund dari toko Anda.'))
        return True

    # ------------------------------------------------------------------
    # Security & audit helpers
    # ------------------------------------------------------------------
    def _is_unitrade_admin(self):
        """Return True only when current user is allowed to act as admin/CS."""
        user = self.env.user
        return (
            user.has_group('unitrade_seller.group_unitrade_admin')
            or user.has_group('base.group_system')
        )

    def _check_admin(self, action_label):
        """Raise AccessDenied when called by non-admin user."""
        if not self._is_unitrade_admin():
            _logger.warning(
                'Refund dispute %s: unauthorized %s attempt by uid=%s login=%s',
                self.mapped('name') or '-', action_label, self.env.uid, self.env.user.login,
            )
            raise AccessDenied(_('Aksi ini hanya boleh dilakukan oleh admin UniTrade.'))

    def _audit(self, action, description, severity='info', payload=None):
        """Write an audit entry when unitrade_admin module is installed.

        The dispute module does NOT depend on unitrade_admin, so we look up
        the model dynamically. When unitrade_admin is not installed, audit
        recording becomes a no-op and we still keep the existing chatter
        and python logging.
        """
        if 'unitrade.admin.audit.log' not in self.env.registry:
            return
        AuditLog = self.env['unitrade.admin.audit.log']
        for dispute in self:
            try:
                AuditLog.sudo().log_action(
                    action,
                    description=description,
                    record=dispute,
                    severity=severity,
                    payload=payload,
                )
            except Exception:  # noqa: BLE001
                _logger.exception('Failed to write dispute audit log: %s', action)

    # ------------------------------------------------------------------
    # SLA helpers (compute overdue based on deadline fields)
    # ------------------------------------------------------------------
    @api.depends('state', 'buyer_response_deadline_at', 'seller_response_deadline_at', 'decision_deadline_at')
    def _compute_is_overdue(self):
        now = fields.Datetime.now()
        for dispute in self:
            overdue = False
            if dispute.state in self.ACTIVE_STATES:
                if dispute.state == 'need_buyer_evidence' and dispute.buyer_response_deadline_at and dispute.buyer_response_deadline_at < now:
                    overdue = True
                elif dispute.state == 'need_seller_response' and dispute.seller_response_deadline_at and dispute.seller_response_deadline_at < now:
                    overdue = True
                elif dispute.state in ('submitted', 'under_review') and dispute.decision_deadline_at and dispute.decision_deadline_at < now:
                    overdue = True
            dispute.is_overdue = overdue

    def _search_is_overdue(self, operator, value):
        """Allow filtering overdue disputes from the search view."""
        if operator not in ('=', '!='):
            return [('id', '=', 0)]
        now = fields.Datetime.now()
        # Active + overdue per state
        overdue_ids = self.search([
            ('state', 'in', list(self.ACTIVE_STATES)),
        ]).filtered(lambda d: (
            (d.state == 'need_buyer_evidence' and d.buyer_response_deadline_at and d.buyer_response_deadline_at < now)
            or (d.state == 'need_seller_response' and d.seller_response_deadline_at and d.seller_response_deadline_at < now)
            or (d.state in ('submitted', 'under_review') and d.decision_deadline_at and d.decision_deadline_at < now)
        )).ids
        if (operator == '=' and value) or (operator == '!=' and not value):
            return [('id', 'in', overdue_ids or [0])]
        return [('id', 'not in', overdue_ids or [0])]

    def _hours_param(self, key, default):
        try:
            value = int(float(self.env['ir.config_parameter'].sudo().get_param(key, default=str(default))))
        except (TypeError, ValueError):
            value = default
        return max(1, value)

    def _set_buyer_evidence_deadline(self):
        hours = self._hours_param('unitrade.refund.buyer_evidence_hours', 48)
        self.write({'buyer_response_deadline_at': fields.Datetime.now() + timedelta(hours=hours)})

    def _set_seller_response_deadline(self):
        hours = self._hours_param('unitrade.dispute_response_hours', 48)
        self.write({'seller_response_deadline_at': fields.Datetime.now() + timedelta(hours=hours)})

    def _set_decision_deadline(self):
        hours = self._hours_param('unitrade.refund.decision_hours', 72)
        self.write({'decision_deadline_at': fields.Datetime.now() + timedelta(hours=hours)})

    # ------------------------------------------------------------------
    # Evidence policy enforcement
    # ------------------------------------------------------------------
    REASONS_REQUIRING_EVIDENCE = (
        'damaged',
        'not_as_described',
        'wrong_item',
        'seller_no_handoff',
    )

    EVIDENCE_TYPES_ACCEPTED = (
        'buyer_photo',
        'unboxing_video',
        'packing_video',
        'google_drive_url',
        'other',
    )

    def _has_minimum_evidence(self):
        """Check whether the dispute meets evidence policy.

        Policy:
        - Reason `seller_no_handoff` does not require physical evidence
          (because there is no item to inspect). Buyer testimony note
          is sufficient.
        - Other reasons (`damaged`, `not_as_described`, `wrong_item`)
          require at least one buyer evidence: photo, unboxing video,
          packing video, or Google Drive link.
        """
        self.ensure_one()
        if self.reason_code not in self.REASONS_REQUIRING_EVIDENCE:
            return True
        if self.reason_code == 'seller_no_handoff':
            return True
        evidences = self.evidence_ids.filtered(
            lambda e: e.evidence_type in self.EVIDENCE_TYPES_ACCEPTED
            and (e.attachment_id or (e.url or '').strip())
        )
        return bool(evidences)

    def _check_evidence_policy(self):
        for dispute in self:
            if not dispute._has_minimum_evidence():
                raise UserError(_(
                    'Refund %s belum memenuhi syarat bukti minimum. '
                    'Alasan "%s" wajib disertai foto, video unboxing, video packing, '
                    'atau link Google Drive sebagai bukti.'
                ) % (dispute.name, dispute.reason_code))

    def _check_decision_note(self):
        for dispute in self:
            if not (dispute.admin_decision_note or '').strip():
                raise UserError(_(
                    'Catatan keputusan admin (decision note) wajib diisi sebelum '
                    'memutuskan refund %s.'
                ) % dispute.name)

    def _check_ready_for_decision(self, action_label):
        for dispute in self:
            if dispute.state != 'under_review':
                raise UserError(_(
                    'Refund %s harus ditangani admin penengah terlebih dahulu. '
                    'Klik "Jadi Penengah" dan pastikan status case menjadi Under Review '
                    'sebelum %s.'
                ) % (dispute.name, action_label))
            if not dispute.admin_id:
                raise UserError(_(
                    'Refund %s belum memiliki admin penengah. Klik "Jadi Penengah" '
                    'sebelum memberi keputusan.'
                ) % dispute.name)

    def _send_party_template(self, xml_id, force_send=True):
        """Send mail template to buyer/seller. No-op if template not found."""
        template = self.env.ref(xml_id, raise_if_not_found=False)
        if not template:
            return
        for dispute in self:
            try:
                template.sudo().send_mail(dispute.id, force_send=force_send)
            except Exception:  # noqa: BLE001
                _logger.exception('Failed to send dispute mail %s for %s', xml_id, dispute.name)

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

    def _require_admin_decision_note(self):
        for dispute in self.sudo():
            note = (dispute.admin_decision_note or '').strip()
            if len(note) < 10:
                raise UserError(_('Catatan keputusan admin minimal 10 karakter.'))

    def _require_refund_final_state(self):
        for dispute in self.sudo():
            if dispute.state != 'admin_review_final':
                raise UserError(_('Refund case %s belum masuk tahap review final admin.') % dispute.name)

    def _validate_refund_final_evidence(self):
        for dispute in self.sudo():
            if dispute.reason_code == 'seller_no_handoff':
                continue
            has_buyer_return = bool(dispute.evidence_ids.filtered(
                lambda evidence: evidence.evidence_type == 'buyer_return_photo' and evidence.attachment_id
            ))
            has_seller_return = bool(dispute.evidence_ids.filtered(
                lambda evidence: evidence.evidence_type == 'seller_return_photo' and evidence.attachment_id
            ))
            if not has_buyer_return or not has_seller_return:
                raise UserError(_('Bukti pengembalian buyer dan konfirmasi seller wajib lengkap sebelum refund diputuskan.'))

    def _final_decision_snapshot(self, decision, approved_amount=False):
        self.ensure_one()
        evidences = self.evidence_ids
        attachment_evidence = evidences.filtered(lambda evidence: evidence.attachment_id)
        snapshot = {
            'decision': decision,
            'case': self.name,
            'state_before': self.state,
            'order_id': self.order_id.id,
            'reason_code': self.reason_code,
            'requested_amount': self.requested_amount,
            'approved_amount': approved_amount or self.approved_amount or 0.0,
            'admin_fee': self.refund_admin_fee_amount or 0.0,
            'total_refund_amount': self.total_refund_amount or 0.0,
            'buyer_return_evidence_count': len(evidences.filtered(lambda evidence: evidence.evidence_type == 'buyer_return_photo')),
            'seller_return_evidence_count': len(evidences.filtered(lambda evidence: evidence.evidence_type == 'seller_return_photo')),
            'attachment_evidence_count': len(attachment_evidence),
            'evidence_ids': evidences.ids,
            'admin_decision_note': (self.admin_decision_note or '').strip(),
        }
        return json.dumps(snapshot, ensure_ascii=False, sort_keys=True)

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
            dispute._record_timeline_event('return_requested', event_time=dispute.submitted_at or now)
            dispute._set_decision_deadline()
        self._hold_escrow_for_review()
        self._set_order_refund_state('submitted')
        for dispute in self:
            dispute._send_party_template('unitrade_dispute.mail_template_dispute_submitted')
            dispute._audit(
                'dispute.submit',
                _('Refund %s diajukan oleh buyer.') % dispute.name,
            )
        return True

    def action_start_review(self):
        self._check_admin('start_review')
        now = fields.Datetime.now()
        for dispute in self.sudo():
            has_seller_return_confirmation = dispute.evidence_ids.filtered(
                lambda evidence: evidence.evidence_type == 'seller_return_photo' and evidence.attachment_id
            )
            next_state = 'admin_review_final' if (has_seller_return_confirmation or dispute.seller_decision_note) else 'under_review'
            dispute.write({
                'state': next_state,
                'review_started_at': now,
                'admin_id': self.env.user.id,
            })
            if has_seller_return_confirmation or dispute.seller_decision_note:
                dispute._record_timeline_event(
                    'admin_review_started',
                    note=_('Admin/CS mulai meninjau keputusan final refund.'),
                    status='current',
                    event_time=now,
                )
                dispute._record_timeline_event(
                    'admin_review',
                    note=_('Admin/CS mulai meninjau pengembalian.'),
                    status='current',
                    event_time=now,
                )
            else:
                dispute._record_timeline_event('seller_review', event_time=now)
            dispute._set_order_refund_state(next_state)
            dispute._audit(
                'dispute.review.start',
                _('Refund %s mulai direview oleh %s.') % (dispute.name, self.env.user.name),
            )
        return True

    def action_need_buyer_evidence(self):
        self._check_admin('need_buyer_evidence')
        self._check_ready_for_decision(_('meminta bukti buyer'))
        self.sudo().write({
            'state': 'need_buyer_evidence',
            'admin_id': self.env.user.id,
        })
        for dispute in self:
            dispute._set_buyer_evidence_deadline()
            dispute._send_party_template('unitrade_dispute.mail_template_dispute_need_buyer_evidence')
        self._set_order_refund_state('need_buyer_evidence')
        for dispute in self:
            dispute._audit(
                'dispute.need_buyer_evidence',
                _('Refund %s meminta tambahan bukti dari buyer.') % dispute.name,
            )
        return True

    def action_need_seller_response(self):
        self._check_admin('need_seller_response')
        self._check_ready_for_decision(_('meminta respons seller'))
        self.sudo().write({
            'state': 'need_seller_response',
            'admin_id': self.env.user.id,
        })
        self._record_timeline_event('seller_review')
        for dispute in self:
            dispute._set_seller_response_deadline()
            dispute._send_party_template('unitrade_dispute.mail_template_dispute_need_seller_response')
        self._set_order_refund_state('need_seller_response')
        for dispute in self:
            dispute._audit(
                'dispute.need_seller_response',
                _('Refund %s meminta respons dari seller.') % dispute.name,
            )
        return True

    def action_approve_refund(self):
        self._check_admin('approve_refund')
        self._require_refund_final_state()
        self._require_admin_decision_note()
        self._check_evidence_policy()
        self._validate_refund_final_evidence()
        now = fields.Datetime.now()
        for dispute in self.sudo():
            if dispute.state in ('cancelled', 'rejected', 'resolved'):
                raise UserError(_('Refund case %s sudah tidak bisa di-approve.') % dispute.name)
            approved_amount = dispute.approved_amount or dispute.total_refund_amount or dispute.requested_amount
            snapshot = dispute._final_decision_snapshot('approve', approved_amount=approved_amount)
            ledger = dispute.escrow_ledger_id
            order = dispute.order_id
            intent = dispute.payment_intent_id or order.x_payment_intent_id
            dispute.write({
                'state': 'approved',
                'approved_amount': approved_amount,
                'approved_at': now,
                'resolved_at': now,
                'admin_id': self.env.user.id,
                'final_decision_user_id': self.env.user.id,
                'final_decision_role': 'admin',
                'final_decision_at': now,
                'final_decision_snapshot': snapshot,
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
            dispute._record_timeline_event(
                'admin_review',
                note=dispute.admin_decision_note or _('Admin/CS menyetujui pengembalian.'),
                status='done',
                event_time=now,
            )
            dispute._record_timeline_event('refund_approved', event_time=now)
            dispute._record_timeline_event('refund_completed', event_time=now)
            dispute._send_party_template('unitrade_dispute.mail_template_dispute_approved')
            dispute._audit(
                'dispute.approve',
                _('Refund %s disetujui oleh %s sebesar %s.') % (
                    dispute.name, self.env.user.name, approved_amount,
                ),
                severity='warning',
                payload={
                    'order_id': order.id,
                    'order_name': order.name,
                    'amount_requested': dispute.requested_amount,
                    'amount_approved': approved_amount,
                    'decision_note': dispute.admin_decision_note or '',
                },
            )
            _logger.info('Refund dispute %s approved by user %s', dispute.name, self.env.user.id)
        return True

    def action_reject_refund(self):
        self._check_admin('reject_refund')
        self._require_refund_final_state()
        self._require_admin_decision_note()
        now = fields.Datetime.now()
        for dispute in self.sudo():
            if dispute.state in ('approved', 'cancelled', 'resolved'):
                raise UserError(_('Refund case %s sudah tidak bisa ditolak.') % dispute.name)
            snapshot = dispute._final_decision_snapshot('reject')
            ledger = dispute.escrow_ledger_id
            dispute.write({
                'state': 'rejected',
                'rejected_at': now,
                'resolved_at': now,
                'admin_id': self.env.user.id,
                'final_decision_user_id': self.env.user.id,
                'final_decision_role': 'admin',
                'final_decision_at': now,
                'final_decision_snapshot': snapshot,
            })
            if ledger and ledger.state == 'disputed':
                ledger.write({'state': 'held'})
                ledger._sync_order_escrow_state()
            dispute.order_id.sudo().write({
                'x_refund_dispute_id': dispute.id,
                'x_refund_state': 'rejected',
                'x_escrow_state': 'held',
            })
            dispute._record_timeline_event(
                'admin_review',
                note=dispute.admin_decision_note or dispute.seller_decision_note or _('Admin/CS menolak pengembalian.'),
                status='failed',
                event_time=now,
            )
            dispute._record_timeline_event('refund_rejected', note=dispute.seller_decision_note, status='failed', event_time=now)
            dispute._send_party_template('unitrade_dispute.mail_template_dispute_rejected')
            dispute._audit(
                'dispute.reject',
                _('Refund %s ditolak oleh %s.') % (dispute.name, self.env.user.name),
                severity='warning',
                payload={
                    'order_id': dispute.order_id.id,
                    'order_name': dispute.order_id.name,
                    'amount_requested': dispute.requested_amount,
                    'decision_note': dispute.admin_decision_note or '',
                },
            )
            _logger.info('Refund dispute %s rejected by user %s', dispute.name, self.env.user.id)
        return True

    def action_seller_approve_refund(self, note=''):
        self._check_seller_decision_access()
        now = fields.Datetime.now()
        note = (note or '').strip()
        for dispute in self.sudo():
            if dispute.state in ('submitted', 'under_review'):
                dispute.write({
                    'state': 'need_buyer_evidence',
                    'seller_decision_note': note,
                    'seller_decision_user_id': self.env.user.id,
                    'seller_decided_at': now,
                })
                dispute._record_timeline_event(
                    'seller_review',
                    note=note or _('Seller menyetujui pengembalian. Menunggu pembeli mengirimkan barang kembali.'),
                    event_time=now,
                )
                dispute._set_order_refund_state('need_buyer_evidence')
                continue
            if dispute.state == 'need_seller_response':
                has_return_confirmation = dispute.evidence_ids.filtered(
                    lambda evidence: evidence.evidence_type == 'seller_return_photo' and evidence.attachment_id
                )
                if not has_return_confirmation:
                    raise UserError(_('Upload foto bukti barang sudah diterima kembali sebelum memproses refund.'))
                dispute.write({
                    'state': 'admin_review_final',
                    'seller_decision_note': note or dispute.seller_decision_note,
                    'seller_decision_user_id': self.env.user.id,
                    'seller_decided_at': now,
                    'review_started_at': dispute.review_started_at or now,
                })
                dispute._record_timeline_event(
                    'seller_return_confirmed',
                    note=note or _('Seller mengonfirmasi barang sudah diterima kembali. Menunggu review final admin/CS.'),
                    event_time=now,
                )
                dispute._record_timeline_event(
                    'admin_review',
                    note=_('Menunggu admin/CS meninjau bukti pengembalian sebelum dana dikembalikan.'),
                    status='current',
                    event_time=now,
                )
                dispute._record_timeline_event(
                    'admin_review_started',
                    note=_('Seller selesai konfirmasi barang kembali. Menunggu review final admin/CS.'),
                    status='current',
                    event_time=now,
                )
                dispute._set_order_refund_state('admin_review_final')
                continue
            if dispute.state == 'need_buyer_evidence':
                raise UserError(_('Menunggu pembeli mengirimkan bukti pengembalian barang.'))
            if dispute.state in self.FINAL_STATES:
                raise UserError(_('Refund case ini sudah selesai.'))
        return True

    def action_seller_reject_refund(self, note=''):
        self._check_seller_decision_access()
        note = (note or '').strip()
        if not note:
            raise UserError(_('Catatan Seller wajib diisi sebelum menolak refund.'))
        now = fields.Datetime.now()
        for dispute in self.sudo():
            if dispute.state in self.FINAL_STATES:
                raise UserError(_('Refund case ini sudah selesai.'))
            dispute.write({
                'state': 'admin_review_final',
                'seller_decision_note': note,
                'seller_decision_user_id': self.env.user.id,
                'seller_decided_at': now,
                'review_started_at': dispute.review_started_at or now,
            })
            dispute._record_timeline_event(
                'seller_response',
                note=_('Seller tidak setuju: %s') % note,
                event_time=now,
            )
            dispute._record_timeline_event(
                'admin_review_started',
                note=_('Pengajuan masuk ke review final admin/CS karena seller menolak refund.'),
                status='current',
                event_time=now,
            )
            dispute._record_timeline_event(
                'admin_review',
                note=_('Menunggu admin/CS menengahi pengajuan yang tidak disetujui seller.'),
                status='current',
                event_time=now,
            )
            dispute._set_order_refund_state('admin_review_final')
        return True

    def action_cancel(self):
        self._check_admin('cancel')
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
            dispute._record_timeline_event('refund_cancelled', status='failed')
            dispute._audit(
                'dispute.cancel',
                _('Refund %s dibatalkan oleh %s.') % (dispute.name, self.env.user.name),
                severity='info',
            )
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
                'state': 'admin_review_final',
                'review_started_at': dispute.review_started_at or now,
            })
            dispute._record_timeline_event('seller_response', note=note, event_time=now)
            dispute._record_timeline_event(
                'admin_review_started',
                note=_('Respons seller diterima. Menunggu review final admin/CS.'),
                status='current',
                event_time=now,
            )
            dispute._record_timeline_event(
                'admin_review',
                note=_('Menunggu admin/CS meninjau respons seller.'),
                status='current',
                event_time=now,
            )
        self._set_order_refund_state('admin_review_final')
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
        ('buyer_return_photo', 'Buyer Return Photo'),
        ('seller_return_photo', 'Seller Return Photo'),
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


class UnitradeDisputeTimeline(models.Model):
    _name = 'unitrade.dispute.timeline'
    _description = 'UniTrade Dispute Timeline'
    _order = 'sequence asc, event_time asc, id asc'

    dispute_id = fields.Many2one('unitrade.dispute', required=True, index=True, ondelete='cascade')
    event_key = fields.Selection([
        ('order_created', 'Pesanan Dibuat'),
        ('payment_received', 'Pembayaran Diterima'),
        ('seller_handoff', 'Barang Diserahkan'),
        ('buyer_received', 'Barang Diterima'),
        ('return_requested', 'Pengajuan Retur Dibuat'),
        ('seller_review', 'Menunggu Review Seller'),
        ('seller_response', 'Respons Seller Dikirim'),
        ('buyer_return_sent', 'Barang Dikembalikan Buyer'),
        ('seller_return_confirmed', 'Barang Kembali Dikonfirmasi Seller'),
        ('admin_review_started', 'Review Final Admin Dimulai'),
        ('admin_review', 'Review Final Admin/CS'),
        ('refund_approved', 'Refund Disetujui'),
        ('refund_rejected', 'Refund Ditolak'),
        ('refund_completed', 'Refund Selesai'),
        ('refund_cancelled', 'Refund Dibatalkan'),
    ], required=True, index=True)
    label = fields.Char(required=True)
    status = fields.Selection([
        ('done', 'Done'),
        ('current', 'Current'),
        ('pending', 'Pending'),
        ('failed', 'Failed'),
    ], default='done', required=True)
    event_time = fields.Datetime(default=fields.Datetime.now, required=True)
    note = fields.Text()
    sequence = fields.Integer(default=100, index=True)

    _sql_constraints = [
        (
            'unitrade_dispute_timeline_unique_event',
            'unique(dispute_id, event_key)',
            'Timeline event sudah tercatat untuk refund ini.',
        ),
    ]
