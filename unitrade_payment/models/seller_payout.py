"""Seller payout batch model.

Flow utama seller:
1. Ledger releasable masuk saldo available seller.
2. Seller klik Ajukan Pencairan -> payout state=requested dan ledger
   payout_status=requested.
3. Cron memproses request setelah timer konfigurasi selesai.
4. Payout berubah processing lalu paid; ledger berubah released dan
   payout_status=paid.

Guard:
- Ledger yang state != releasable atau payout_status aktif/selesai tidak boleh
  masuk batch baru.
- 1 ledger hanya boleh terhubung ke 1 payout aktif.
- Payout manual admin state=ready tetap wajib payment_reference/proof_image.
- Hanya admin UniTrade yang boleh aksi admin.
"""
import json
import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessDenied, UserError, ValidationError

_logger = logging.getLogger(__name__)


class UnitradeSellerPayout(models.Model):
    _name = 'unitrade.seller.payout'
    _inherit = ['unitrade.seller.payout', 'mail.thread', 'mail.activity.mixin']
    _description = 'UniTrade Manual Seller Payout Batch'
    _order = 'requested_at desc, id desc'
    _rec_name = 'name'

    name = fields.Char(
        string='Reference',
        required=True,
        readonly=True,
        copy=False,
        default='New',
    )
    state = fields.Selection(
        selection_add=[
            ('draft', 'Draft'),
            ('ready', 'Ready to Pay'),
            ('cancelled', 'Cancelled'),
        ],
        ondelete={
            'draft': 'set default',
            'ready': 'set default',
            'cancelled': 'set default',
        },
        tracking=True,
    )

    seller_id = fields.Many2one(
        'unitrade.seller',
        string='Seller',
        required=True,
        index=True,
        ondelete='restrict',
    )
    seller_user_id = fields.Many2one(
        related='seller_id.user_id',
        string='User Seller',
        store=False,
    )
    payout_channel_code = fields.Char(
        string='Channel',
        compute='_compute_payout_identity',
        store=False,
    )
    payout_account_number = fields.Char(
        string='Nomor Rekening / HP',
        compute='_compute_payout_identity',
        store=False,
    )
    payout_account_name = fields.Char(
        string='Nama Pemilik',
        compute='_compute_payout_identity',
        store=False,
    )
    payout_ready = fields.Boolean(
        string='Data Payout Lengkap',
        compute='_compute_payout_identity',
        store=False,
    )

    ledger_ids = fields.Many2many(
        'unitrade.escrow.ledger',
        'unitrade_seller_payout_ledger_rel',
        'payout_id',
        'ledger_id',
        string='Escrow Ledgers',
    )
    ledger_count = fields.Integer(
        string='Jumlah Ledger',
        compute='_compute_totals',
        store=True,
    )
    total_amount = fields.Monetary(
        string='Total Payout',
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        required=True,
        default=lambda self: self.env.company.currency_id,
    )

    payment_reference = fields.Char(
        string='Payment Reference',
        copy=False,
        help='Nomor transaksi bank / referensi transfer manual.',
    )
    proof_image = fields.Binary(
        string='Bukti Transfer',
        attachment=True,
        copy=False,
    )
    proof_filename = fields.Char(string='Nama File Bukti', copy=False)
    note = fields.Text(string='Catatan')

    created_by_id = fields.Many2one(
        'res.users',
        string='Dibuat Oleh',
        default=lambda self: self.env.user,
        readonly=True,
        copy=False,
    )
    paid_by_id = fields.Many2one(
        'res.users',
        string='Ditandai Paid Oleh',
        readonly=True,
        copy=False,
    )
    paid_at = fields.Datetime(string='Tanggal Paid', readonly=True, copy=False)
    cancelled_at = fields.Datetime(string='Tanggal Cancel', readonly=True, copy=False)
    cancel_reason = fields.Char(string='Alasan Cancel', copy=False)

    # ------------------------------------------------------------------
    # Compute / constrains
    # ------------------------------------------------------------------
    @api.depends(
        'seller_id',
        'seller_id.write_date',
        'destination_channel_code',
        'destination_channel_label',
        'destination_account_number',
        'destination_account_name',
    )
    def _compute_payout_identity(self):
        for payout in self:
            seller = payout.seller_id
            payout.payout_channel_code = (
                payout.destination_channel_label
                or payout.destination_channel_code
                or (seller['x_payout_channel_code'] if seller and 'x_payout_channel_code' in seller._fields else False)
            )
            payout.payout_account_number = (
                payout.destination_account_number
                or (seller['x_payout_account_number'] if seller and 'x_payout_account_number' in seller._fields else False)
            )
            payout.payout_account_name = (
                payout.destination_account_name
                or (seller['x_payout_account_name'] if seller and 'x_payout_account_name' in seller._fields else False)
            )
            payout.payout_ready = bool(
                payout.payout_channel_code
                and payout.payout_account_number
                and payout.payout_account_name
            )

    @api.depends('ledger_ids', 'ledger_ids.amount_seller')
    def _compute_totals(self):
        for payout in self:
            payout.ledger_count = len(payout.ledger_ids)
            payout.total_amount = sum(payout.ledger_ids.mapped('amount_seller'))

    @api.constrains('ledger_ids', 'seller_id')
    def _check_ledger_seller(self):
        for payout in self:
            if not payout.ledger_ids:
                continue
            wrong = payout.ledger_ids.filtered(
                lambda l: l.seller_id and l.seller_id.id != payout.seller_id.id
            )
            if wrong:
                raise ValidationError(_(
                    'Ledger %s bukan milik seller %s. Tidak bisa dimasukkan ke payout.'
                ) % (', '.join(wrong.mapped('name') or []), payout.seller_id.display_name))

    @api.constrains('ledger_ids', 'state')
    def _check_no_double_payout(self):
        """Pastikan ledger tidak terhubung ke payout aktif lain."""
        for payout in self:
            if payout.state in ('cancelled', 'failed'):
                continue
            for ledger in payout.ledger_ids:
                other = self.search([
                    ('id', '!=', payout.id),
                    ('ledger_ids', 'in', ledger.id),
                    ('state', 'in', payout._active_payout_states(include_paid=True)),
                ], limit=1)
                if other:
                    raise ValidationError(_(
                        'Ledger %s sudah terdaftar di payout %s (status %s). '
                        'Tidak bisa dimasukkan ke payout lain.'
                    ) % (ledger.name, other.name, other.state))

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env['ir.sequence'].sudo()
        for vals in vals_list:
            is_manual_batch = bool(vals.get('ledger_ids')) or vals.get('state') in {
                'draft',
                'requested',
                'ready',
                'processing',
                'cancelled',
            }
            if is_manual_batch:
                vals.setdefault('state', 'draft')
                seller = self.env['unitrade.seller'].sudo().browse(vals.get('seller_id')).exists() if vals.get('seller_id') else False
                if seller:
                    vals.update(self._missing_destination_snapshot_vals(vals, seller))
                ledger_ids = self._ledger_ids_from_commands(vals.get('ledger_ids'))
                if ledger_ids:
                    ledgers = self.env['unitrade.escrow.ledger'].sudo().browse(ledger_ids).exists()
                    self._validate_ledgers_for_payout(ledgers, seller=seller, current_payout=False)
                    vals.setdefault('amount', sum(ledgers.mapped('amount_seller')) if ledgers else 0.0)
                    if ledgers and not vals.get('currency_id'):
                        vals['currency_id'] = ledgers[:1].currency_id.id or self.env.company.currency_id.id
                    vals.setdefault('ledger_ids_json', self._ledger_ids_json(ledgers))
            if is_manual_batch and vals.get('name', 'New') == 'New':
                vals['name'] = sequence.next_by_code('unitrade.seller.payout') or 'PB%05d' % (self.search_count([]) + 1)
        records = super().create(vals_list)
        records.filtered(lambda payout: payout.state in ('draft', 'ready', 'requested', 'processing') and payout.ledger_ids)._reserve_ledgers()
        return records

    def write(self, vals):
        old_ledgers_by_payout = {
            payout.id: payout.ledger_ids
            for payout in self
            if 'ledger_ids' in vals or 'state' in vals
        }
        result = super().write(vals)
        for payout in self:
            old_ledgers = old_ledgers_by_payout.get(payout.id)
            if old_ledgers is not None:
                removed = old_ledgers - payout.ledger_ids
                if removed:
                    payout._release_reserved_ledgers(removed)
            if payout.state in ('draft', 'ready', 'requested', 'processing') and payout.ledger_ids:
                payout._reserve_ledgers()
            elif payout.state == 'cancelled' and payout.ledger_ids:
                payout._release_reserved_ledgers(payout.ledger_ids)
        return result

    @staticmethod
    def _ledger_ids_from_commands(commands):
        ledger_ids = []
        for command in commands or []:
            if not isinstance(command, (list, tuple)) or not command:
                continue
            opcode = command[0]
            if opcode == 6 and len(command) >= 3:
                ledger_ids.extend(command[2] or [])
            elif opcode == 4 and len(command) >= 2:
                ledger_ids.append(command[1])
        return [int(ledger_id) for ledger_id in ledger_ids if ledger_id]

    @staticmethod
    def _ledger_ids_json(ledgers):
        return json.dumps([int(ledger_id) for ledger_id in ledgers.ids])

    @api.model
    def _active_payout_states(self, include_paid=False):
        states = ['draft', 'ready', 'requested', 'pending', 'processing']
        if include_paid:
            states += ['paid', 'succeeded']
        return tuple(states)

    @api.model
    def _seller_channel_label(self, seller):
        if not seller or 'x_payout_channel_code' not in seller._fields:
            return ''
        selection = dict(seller._fields['x_payout_channel_code'].selection)
        code = seller.x_payout_channel_code or ''
        return selection.get(code, code)

    @api.model
    def _destination_snapshot_vals(self, seller):
        return {
            'destination_channel_code': seller.x_payout_channel_code if 'x_payout_channel_code' in seller._fields else '',
            'destination_channel_label': self._seller_channel_label(seller),
            'destination_account_number': seller.x_payout_account_number if 'x_payout_account_number' in seller._fields else '',
            'destination_account_name': seller.x_payout_account_name if 'x_payout_account_name' in seller._fields else '',
        }

    @api.model
    def _missing_destination_snapshot_vals(self, vals, seller):
        snapshot = self._destination_snapshot_vals(seller)
        return {
            key: value
            for key, value in snapshot.items()
            if not vals.get(key)
        }

    def _reservation_reference_values(self):
        self.ensure_one()
        values = [self.name]
        if self.payment_reference:
            values.append(self.payment_reference)
        return [value for value in values if value]

    def _is_reserved_by_current_payout(self, ledger):
        self.ensure_one()
        return (
            ledger.payout_status in ('requested', 'pending', 'processing')
            and ledger.payout_reference in self._reservation_reference_values()
        )

    def _active_dispute_for_ledgers(self, ledgers):
        if 'unitrade.dispute' not in self.env.registry or not ledgers:
            return False
        Dispute = self.env['unitrade.dispute'].sudo()
        active_states = getattr(Dispute, 'ACTIVE_STATES', (
            'submitted',
            'under_review',
            'need_buyer_evidence',
            'need_seller_response',
            'admin_review_final',
        ))
        domain = [
            ('state', 'in', list(active_states)),
            '|',
            ('escrow_ledger_id', 'in', ledgers.ids),
            ('order_id', 'in', ledgers.mapped('order_id').ids),
        ]
        return Dispute.search(domain, limit=1)

    def _validate_ledgers_for_payout(self, ledgers, seller=False, current_payout=False, allow_current_reservation=False):
        ledgers = ledgers.sudo().exists()
        if not ledgers:
            raise UserError(_('Payout belum punya ledger yang valid.'))
        seller = seller or (current_payout.seller_id if current_payout else False)

        wrong_seller = ledgers.filtered(lambda ledger: not ledger.seller_id or (seller and ledger.seller_id.id != seller.id))
        if wrong_seller:
            raise UserError(_('Ledger payout harus berasal dari seller yang sama: %s') % ', '.join(wrong_seller.mapped('name') or []))

        invalid_state = ledgers.filtered(lambda ledger: ledger.state != 'releasable')
        if invalid_state:
            raise UserError(_('Ledger harus berstatus releasable sebelum payout: %s') % ', '.join(invalid_state.mapped('name') or []))

        active_statuses = ('requested', 'pending', 'processing')
        done_statuses = ('paid', 'succeeded')
        invalid_payout_status = self.env['unitrade.escrow.ledger'].sudo().browse()
        for ledger in ledgers:
            if ledger.payout_status in done_statuses:
                invalid_payout_status |= ledger
            elif ledger.payout_status in active_statuses:
                if not (
                    allow_current_reservation
                    and current_payout
                    and current_payout._is_reserved_by_current_payout(ledger)
                ):
                    invalid_payout_status |= ledger
        if invalid_payout_status:
            raise UserError(_('Ledger sudah sedang/done payout: %s') % ', '.join(invalid_payout_status.mapped('name') or []))

        if 'x_payment_status' in self.env['sale.order']._fields:
            unpaid_orders = ledgers.filtered(lambda ledger: ledger.order_id.x_payment_status != 'paid')
            if unpaid_orders:
                raise UserError(_('Order ledger harus sudah paid sebelum payout: %s') % ', '.join(unpaid_orders.mapped('order_id.name') or []))

        active_dispute = self._active_dispute_for_ledgers(ledgers)
        if active_dispute:
            raise UserError(_('Payout diblokir karena ada refund/dispute aktif: %s') % (active_dispute.name or active_dispute.id))

        other_payout = self.sudo().search([
            ('id', '!=', current_payout.id if current_payout else 0),
            ('ledger_ids', 'in', ledgers.ids),
            ('state', 'in', self._active_payout_states(include_paid=True)),
        ], limit=1)
        if other_payout:
            raise UserError(_('Ledger sudah masuk payout %s.') % other_payout.name)
        return True

    def _reserve_ledgers(self):
        now = fields.Datetime.now()
        for payout in self.sudo():
            if payout.state not in ('draft', 'ready', 'requested', 'processing') or not payout.ledger_ids:
                continue
            payout._validate_ledgers_for_payout(
                payout.ledger_ids,
                seller=payout.seller_id,
                current_payout=payout,
                allow_current_reservation=True,
            )
            payout_status = 'processing' if payout.state == 'processing' else 'requested'
            payout.ledger_ids.write({
                'payout_status': payout_status,
                'payout_requested_at': payout.requested_at or now,
                'payout_reference': payout.name,
                'payout_failure_reason': False,
            })
        return True

    def _release_reserved_ledgers(self, ledgers):
        for payout in self.sudo():
            reserved = ledgers.sudo().filtered(lambda ledger: (
                ledger.payout_status in ('requested', 'pending', 'processing')
                and ledger.payout_reference in payout._reservation_reference_values()
            ))
            if reserved:
                reserved.write({
                    'payout_status': 'available',
                    'payout_requested_at': False,
                    'payout_reference': False,
                    'payout_failure_reason': False,
                })
        return True

    @api.model
    def _unitrade_repair_empty_amounts(self):
        if 'amount' not in self._fields:
            return True
        payouts = self.sudo().search([('amount', '=', False)])
        repaired = 0
        for payout in payouts:
            amount = 0.0
            if 'total_amount' in payout._fields and payout.total_amount:
                amount = payout.total_amount
            elif 'ledger_ids' in payout._fields and payout.ledger_ids:
                amount = sum(payout.ledger_ids.mapped('amount_seller'))
            values = {'amount': amount}
            if 'currency_id' in payout._fields and not payout.currency_id:
                values['currency_id'] = self.env.company.currency_id.id
            try:
                with self.env.cr.savepoint():
                    payout.write(values)
                    repaired += 1
            except Exception:
                _logger.exception('Failed repairing empty amount on seller payout %s', payout.id)
        if repaired:
            _logger.info('Repaired amount on %s seller payout record(s).', repaired)
        return True

    # ------------------------------------------------------------------
    # Security & audit helpers
    # ------------------------------------------------------------------
    def _is_unitrade_admin(self):
        user = self.env.user
        return (
            user.has_group('unitrade_seller.group_unitrade_admin')
            or user.has_group('base.group_system')
        )

    def _check_admin(self, action_label):
        if not self._is_unitrade_admin():
            _logger.warning(
                'Seller payout: unauthorized %s attempt by uid=%s',
                action_label, self.env.uid,
            )
            raise AccessDenied(_('Aksi payout ini hanya boleh dilakukan oleh admin UniTrade.'))

    def _audit(self, action, description, severity='info', payload=None):
        if 'unitrade.admin.audit.log' not in self.env.registry:
            return
        AuditLog = self.env['unitrade.admin.audit.log']
        for payout in self:
            try:
                AuditLog.sudo().log_action(
                    action,
                    description=description,
                    record=payout,
                    severity=severity,
                    payload=payload,
                )
            except Exception:  # noqa: BLE001
                _logger.exception('Failed to write payout audit log: %s', action)

    # ------------------------------------------------------------------
    # Helpers — collect releasable ledgers per seller
    # ------------------------------------------------------------------
    @api.model
    def _eligible_ledgers_domain(self, seller):
        """Ledger eligible untuk payout: releasable, tidak dispute, payout belum success."""
        domain = [
            ('seller_id', '=', seller.id),
            ('state', '=', 'releasable'),
            ('payout_status', 'not in', ('requested', 'pending', 'processing', 'paid', 'succeeded')),
        ]
        return domain

    def _get_eligible_ledgers(self, seller):
        Ledger = self.env['unitrade.escrow.ledger'].sudo()
        ledgers = Ledger.search(self._eligible_ledgers_domain(seller))
        # Exclude yang sudah masuk payout aktif
        active_payouts = self.search([
            ('state', 'in', self._active_payout_states(include_paid=True)),
            ('seller_id', '=', seller.id),
        ])
        already_in_payout = active_payouts.mapped('ledger_ids').ids
        return ledgers.filtered(lambda l: l.id not in already_in_payout)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_recompute_ledgers(self):
        """Refresh draft ledger list dari ledger eligible terbaru."""
        self._check_admin('recompute_ledgers')
        for payout in self:
            if payout.state != 'draft':
                raise UserError(_('Hanya payout draft yang bisa di-refresh.'))
            payout._release_reserved_ledgers(payout.ledger_ids)
            ledgers = self._get_eligible_ledgers(payout.seller_id)
            payout.ledger_ids = [(6, 0, ledgers.ids)]
            if 'ledger_ids_json' in payout._fields:
                payout.ledger_ids_json = self._ledger_ids_json(ledgers)
            payout._reserve_ledgers()
        return True

    def action_mark_ready(self):
        self._check_admin('mark_ready')
        for payout in self:
            if payout.state != 'draft':
                raise UserError(_('Payout %s bukan draft.') % payout.name)
            if not payout.ledger_ids:
                raise UserError(_('Payout %s belum punya ledger. Tambahkan ledger dulu.') % payout.name)
            if not payout.payout_ready:
                raise UserError(_(
                    'Data payout seller %s belum lengkap (channel/no rek/nama pemilik). '
                    'Lengkapi dulu di profil seller.'
                ) % payout.seller_id.display_name)
            payout._validate_ledgers_for_payout(
                payout.ledger_ids,
                seller=payout.seller_id,
                current_payout=payout,
                allow_current_reservation=True,
            )
            payout._reserve_ledgers()
            payout.write({'state': 'ready'})
            payout._audit(
                'payout.ready',
                _('Payout %s ditandai siap bayar oleh %s. Total: Rp %s untuk %s ledger.') % (
                    payout.name, self.env.user.name,
                    self._format_idr(payout.total_amount), payout.ledger_count,
                ),
                severity='info',
                payload={
                    'seller_id': payout.seller_id.id,
                    'amount': payout.total_amount,
                    'ledger_count': payout.ledger_count,
                },
            )
        return True

    def action_mark_paid(self):
        self._check_admin('mark_paid')
        for payout in self:
            if payout.state not in ('ready', 'processing'):
                raise UserError(_('Payout %s harus dalam status Ready atau Processing.') % payout.name)
            if payout.state == 'ready' and not (payout.payment_reference or '').strip() and not payout.proof_image:
                raise UserError(_(
                    'Wajib isi Payment Reference atau upload Bukti Transfer sebelum tandai paid.'
                ))
            if payout.state == 'processing' and not (payout.payment_reference or '').strip():
                payout.write({'payment_reference': 'AUTO-%s' % (payout.name or payout.id)})
            payout._validate_ledgers_for_payout(
                payout.ledger_ids,
                seller=payout.seller_id,
                current_payout=payout,
                allow_current_reservation=True,
            )

            now = fields.Datetime.now()
            payout.write({
                'state': 'paid',
                'paid_at': now,
                'completed_at': now,
                'paid_by_id': self.env.user.id,
            })

            # Update related escrow ledgers
            for ledger in payout.ledger_ids:
                ledger.sudo().write({
                    'state': 'released',
                    'released_at': now,
                    'payout_status': 'paid',
                    'payout_completed_at': now,
                    'payout_reference': payout.payment_reference or payout.name,
                    'payout_failure_reason': False,
                })
            payout.ledger_ids._sync_order_escrow_state()

            payout._audit(
                'payout.paid',
                _('Payout %s ditandai PAID oleh %s. Ref: %s. Total: Rp %s ke %s (%s).') % (
                    payout.name,
                    self.env.user.name,
                    payout.payment_reference or '-',
                    self._format_idr(payout.total_amount),
                    payout.payout_account_name or '-',
                    payout.payout_account_number or '-',
                ),
                severity='critical',
                payload={
                    'seller_id': payout.seller_id.id,
                    'amount': payout.total_amount,
                    'ledger_ids': payout.ledger_ids.ids,
                    'payment_reference': payout.payment_reference or '',
                    'channel': payout.payout_channel_code or '',
                    'account_number': payout.payout_account_number or '',
                },
            )

            # Notify seller via chatter (mail.thread on seller record)
            if payout.seller_id and hasattr(payout.seller_id, 'message_post'):
                try:
                    payout.seller_id.sudo().message_post(
                        body=_(
                            'Payout %s sebesar Rp %s telah ditransfer ke rekening kamu.<br/>'
                            'Reference: %s<br/>'
                            'Tanggal: %s'
                        ) % (
                            payout.name,
                            self._format_idr(payout.total_amount),
                            payout.payment_reference or '-',
                            now.strftime('%d %b %Y %H:%M'),
                        ),
                        subtype_xmlid='mail.mt_note',
                    )
                except Exception:  # noqa: BLE001
                    _logger.exception('Failed to post payout notification to seller %s', payout.seller_id.id)
        return True

    @api.model
    def _payout_processing_delay_hours(self):
        raw_hours = self.env['ir.config_parameter'].sudo().get_param(
            'unitrade.seller.payout_processing_hours',
            default='24',
        )
        try:
            hours = int(float(raw_hours or 24))
        except (TypeError, ValueError):
            hours = 24
        return max(0, min(hours, 24 * 7))

    @api.model
    def cron_process_requested_payouts(self, limit=50):
        """Complete seller-requested payouts only after the request timer has elapsed."""
        delay_hours = self._payout_processing_delay_hours()
        cutoff = fields.Datetime.now() - timedelta(hours=delay_hours)
        payouts = self.sudo().search([
            ('state', '=', 'requested'),
            ('requested_at', '!=', False),
            ('requested_at', '<=', cutoff),
        ], order='requested_at asc, id asc', limit=limit)
        processed = 0
        for payout in payouts:
            try:
                with self.env.cr.savepoint():
                    payout._validate_ledgers_for_payout(
                        payout.ledger_ids,
                        seller=payout.seller_id,
                        current_payout=payout,
                        allow_current_reservation=True,
                    )
                    now = fields.Datetime.now()
                    payout.write({
                        'state': 'processing',
                        'processed_at': now,
                        'payment_reference': payout.payment_reference or 'AUTO-%s' % (payout.name or payout.id),
                    })
                    payout._reserve_ledgers()
                    payout.action_mark_paid()
                    processed += 1
            except Exception:
                _logger.exception('Failed processing seller payout request %s', payout.id)
        if processed:
            _logger.info('Processed %s UniTrade seller payout request(s).', processed)
        return True

    def action_cancel(self):
        self._check_admin('cancel')
        for payout in self:
            if payout.state == 'paid':
                raise UserError(_('Payout %s sudah PAID. Tidak bisa dibatalkan.') % payout.name)
            if payout.state == 'cancelled':
                continue
            payout._release_reserved_ledgers(payout.ledger_ids)
            payout.write({
                'state': 'cancelled',
                'cancelled_at': fields.Datetime.now(),
            })
            payout._audit(
                'payout.cancel',
                _('Payout %s dibatalkan oleh %s. Alasan: %s') % (
                    payout.name, self.env.user.name, payout.cancel_reason or '-',
                ),
                severity='warning',
                payload={
                    'seller_id': payout.seller_id.id,
                    'amount': payout.total_amount,
                    'reason': payout.cancel_reason or '',
                },
            )
        return True

    def action_open_seller(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'unitrade.seller',
            'res_id': self.seller_id.id,
            'view_mode': 'form',
        }

    @staticmethod
    def _format_idr(value):
        n = int(round(float(value or 0)))
        return f'{n:,}'.replace(',', '.')

    @api.model
    def create_payout_for_seller(self, seller_id):
        """Helper RPC: buat payout draft dengan semua ledger releasable seller."""
        self._check_admin('create_payout_for_seller')
        seller = self.env['unitrade.seller'].sudo().browse(int(seller_id))
        if not seller.exists():
            raise UserError(_('Seller tidak ditemukan.'))
        ledgers = self._get_eligible_ledgers(seller)
        if not ledgers:
            raise UserError(_(
                'Seller %s tidak punya ledger releasable yang bisa dipayout saat ini.'
            ) % seller.display_name)
        payout = self.create({
            'seller_id': seller.id,
            'state': 'draft',
            'amount': sum(ledgers.mapped('amount_seller')),
            'currency_id': ledgers[:1].currency_id.id or self.env.company.currency_id.id,
            'ledger_ids': [(6, 0, ledgers.ids)],
            'ledger_ids_json': self._ledger_ids_json(ledgers),
            **self._destination_snapshot_vals(seller),
        })
        return {
            'id': payout.id,
            'name': payout.name,
            'amount': payout.total_amount,
            'ledger_count': payout.ledger_count,
        }
