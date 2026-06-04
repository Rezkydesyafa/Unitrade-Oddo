"""Manual seller payout (batch) model.

Workflow:
1. Admin buka daftar escrow ledger releasable per seller.
2. Klik "Create Payout" → buat record `unitrade.seller.payout` state=draft
   yang ngumpulin semua ledger releasable seller tsb (atau subset pilihan).
3. Admin transfer dana manual ke rekening seller (sesuai tujuan payout
   yang sudah disimpan di unitrade.seller).
4. Admin upload bukti transfer + isi payment reference, klik "Mark Paid".
   Ledger berubah state=released, payout_status=succeeded.
5. Audit log + (optional) email notif ke seller.

Guard:
- Ledger yang state != releasable atau payout_status sudah succeeded
  tidak boleh masuk batch baru.
- 1 ledger hanya boleh terhubung ke 1 payout aktif (draft/ready/paid).
- Mark paid wajib payment_reference atau proof_image.
- Hanya admin UniTrade yang boleh akses.
"""
import logging

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
            ('paid', 'Paid'),
            ('cancelled', 'Cancelled'),
        ],
        ondelete={
            'draft': 'set default',
            'ready': 'set default',
            'paid': 'set default',
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
    @api.depends('seller_id', 'seller_id.write_date')
    def _compute_payout_identity(self):
        for payout in self:
            seller = payout.seller_id
            payout.payout_channel_code = seller['x_payout_channel_code'] if seller and 'x_payout_channel_code' in seller._fields else False
            payout.payout_account_number = seller['x_payout_account_number'] if seller and 'x_payout_account_number' in seller._fields else False
            payout.payout_account_name = seller['x_payout_account_name'] if seller and 'x_payout_account_name' in seller._fields else False
            payout.payout_ready = bool(seller['x_payout_ready']) if seller and 'x_payout_ready' in seller._fields else False

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
            if payout.state == 'cancelled':
                continue
            for ledger in payout.ledger_ids:
                other = self.search([
                    ('id', '!=', payout.id),
                    ('ledger_ids', 'in', ledger.id),
                    ('state', 'in', ('draft', 'ready', 'paid')),
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
                'ready',
                'paid',
                'cancelled',
            }
            if is_manual_batch:
                vals.setdefault('state', 'draft')
                ledger_ids = self._ledger_ids_from_commands(vals.get('ledger_ids'))
                if ledger_ids:
                    ledgers = self.env['unitrade.escrow.ledger'].sudo().browse(ledger_ids).exists()
                    vals.setdefault('amount', sum(ledgers.mapped('amount_seller')) if ledgers else 0.0)
                    if ledgers and not vals.get('currency_id'):
                        vals['currency_id'] = ledgers[:1].currency_id.id or self.env.company.currency_id.id
            if is_manual_batch and vals.get('name', 'New') == 'New':
                vals['name'] = sequence.next_by_code('unitrade.seller.payout') or 'PB%05d' % (self.search_count([]) + 1)
        return super().create(vals_list)

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
            ('payout_status', 'not in', ('succeeded', 'processing')),
        ]
        return domain

    def _get_eligible_ledgers(self, seller):
        Ledger = self.env['unitrade.escrow.ledger'].sudo()
        ledgers = Ledger.search(self._eligible_ledgers_domain(seller))
        # Exclude yang sudah masuk payout aktif
        active_payouts = self.search([
            ('state', 'in', ('draft', 'ready', 'paid')),
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
            ledgers = self._get_eligible_ledgers(payout.seller_id)
            payout.ledger_ids = [(6, 0, ledgers.ids)]
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
            if payout.state != 'ready':
                raise UserError(_('Payout %s harus dalam status Ready.') % payout.name)
            if not (payout.payment_reference or '').strip() and not payout.proof_image:
                raise UserError(_(
                    'Wajib isi Payment Reference atau upload Bukti Transfer sebelum tandai paid.'
                ))

            now = fields.Datetime.now()
            payout.write({
                'state': 'paid',
                'paid_at': now,
                'paid_by_id': self.env.user.id,
            })

            # Update related escrow ledgers
            for ledger in payout.ledger_ids:
                if ledger.state == 'releasable':
                    ledger.sudo().write({
                        'state': 'released',
                        'released_at': now,
                        'payout_status': 'succeeded',
                        'payout_completed_at': now,
                        'payout_reference': payout.payment_reference or payout.name,
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

    def action_cancel(self):
        self._check_admin('cancel')
        for payout in self:
            if payout.state == 'paid':
                raise UserError(_('Payout %s sudah PAID. Tidak bisa dibatalkan.') % payout.name)
            if payout.state == 'cancelled':
                continue
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
        })
        return {
            'id': payout.id,
            'name': payout.name,
            'amount': payout.total_amount,
            'ledger_count': payout.ledger_count,
        }
