import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessDenied, UserError

_logger = logging.getLogger(__name__)


class UnitradeEscrowLedger(models.Model):
    _name = 'unitrade.escrow.ledger'
    _description = 'UniTrade Escrow Ledger'
    _order = 'create_date desc'

    name = fields.Char(required=True, readonly=True, copy=False)
    order_id = fields.Many2one('sale.order', required=True, index=True, ondelete='cascade')
    payment_intent_id = fields.Many2one('unitrade.payment.intent', index=True, ondelete='set null')
    seller_id = fields.Many2one('unitrade.seller', string='Seller', index=True, ondelete='set null')
    buyer_id = fields.Many2one('res.partner', string='Buyer', index=True, ondelete='set null')
    currency_id = fields.Many2one(
        'res.currency',
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    amount_total = fields.Monetary(string='Total Buyer', currency_field='currency_id', required=True)
    amount_platform_fee = fields.Monetary(string='Platform Fee', currency_field='currency_id', required=True)
    amount_gateway_fee = fields.Monetary(string='Gateway Fee', currency_field='currency_id', default=0.0)
    amount_seller = fields.Monetary(string='Seller Amount', currency_field='currency_id', required=True)
    state = fields.Selection([
        ('held', 'Held'),
        ('releasable', 'Releasable'),
        ('released', 'Released'),
        ('disputed', 'Disputed'),
        ('refunded', 'Refunded'),
        ('cancelled', 'Cancelled'),
    ], default='held', required=True, index=True)
    released_at = fields.Datetime(copy=False)
    payout_reference = fields.Char(copy=False)
    xendit_payout_id = fields.Char(string='Legacy Payout ID', copy=False, index=True)
    payout_status = fields.Selection([
        ('draft', 'Draft'),
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('succeeded', 'Succeeded'),
        ('failed', 'Failed'),
    ], default='draft', copy=False)
    payout_requested_at = fields.Datetime(copy=False)
    payout_completed_at = fields.Datetime(copy=False)
    payout_failure_reason = fields.Text(copy=False)
    buyer_confirmed_at = fields.Datetime(string='Buyer Confirmed At', copy=False, readonly=True)
    seller_confirmed_at = fields.Datetime(string='Seller Confirmed At', copy=False, readonly=True)
    completed_at = fields.Datetime(string='Transaction Completed At', copy=False, readonly=True)
    seller_handoff_image = fields.Binary(
        string='Bukti Barang Diserahkan',
        attachment=True,
        copy=False,
        readonly=True,
    )
    seller_handoff_filename = fields.Char(string='Nama File Bukti Seller', copy=False, readonly=True)
    seller_handoff_location = fields.Char(string='Lokasi Penyerahan Seller', copy=False, readonly=True)
    buyer_received_image = fields.Binary(
        string='Bukti Barang Diterima',
        attachment=True,
        copy=False,
        readonly=True,
    )
    buyer_received_filename = fields.Char(string='Nama File Bukti Buyer', copy=False, readonly=True)
    note = fields.Text()

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
                'Escrow ledger: unauthorized %s attempt by uid=%s login=%s',
                action_label, self.env.uid, self.env.user.login,
            )
            raise AccessDenied(_('Aksi ini hanya boleh dilakukan oleh admin UniTrade.'))

    def _audit(self, action, description, severity='info', payload=None):
        """Write an entry to unitrade.admin.audit.log if the model exists."""
        if 'unitrade.admin.audit.log' not in self.env.registry:
            return
        AuditLog = self.env['unitrade.admin.audit.log']
        for ledger in self:
            try:
                AuditLog.sudo().log_action(
                    action,
                    description=description,
                    record=ledger,
                    severity=severity,
                    payload=payload,
                )
            except Exception:  # noqa: BLE001
                _logger.exception('Failed to write escrow audit log: %s', action)

    def _manual_action_reason(self):
        reason = (self.env.context.get('unitrade_manual_reason') or '').strip()
        if not reason:
            raise UserError(_('Alasan aksi manual escrow wajib diisi.'))
        return reason

    def _open_manual_action_wizard(self, action_type, title):
        self._check_admin(action_type)
        if not self:
            raise UserError(_('Pilih minimal satu escrow ledger.'))
        return {
            'type': 'ir.actions.act_window',
            'name': title,
            'res_model': 'unitrade.escrow.manual.action.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_action_type': action_type,
                'default_ledger_ids': [(6, 0, self.ids)],
            },
        }

    def action_open_mark_releasable_wizard(self):
        ledgers = self.filtered(lambda ledger: ledger.state == 'held')
        if not ledgers:
            raise UserError(_('Tidak ada escrow berstatus Held yang bisa ditandai releasable.'))
        return ledgers._open_manual_action_wizard(
            'mark_releasable',
            _('Alasan Tandai Escrow Releasable'),
        )

    def action_open_mark_released_wizard(self):
        ledgers = self.filtered(lambda ledger: ledger.state == 'releasable')
        if not ledgers:
            raise UserError(_('Tidak ada escrow berstatus Releasable yang bisa ditandai released.'))
        return ledgers._open_manual_action_wizard(
            'mark_released',
            _('Alasan Release Manual Escrow'),
        )

    def _seller_from_line(self, line):
        seller = line.product_id.product_tmpl_id.x_seller_id if hasattr(line.product_id.product_tmpl_id, 'x_seller_id') else False
        return seller if seller else False

    def _create_for_order(self, order, payment_intent):
        self = self.sudo()
        existing = self.search([
            ('order_id', '=', order.id),
            ('payment_intent_id', '=', payment_intent.id),
        ])
        if existing:
            return existing

        if hasattr(order, '_unitrade_product_lines_for_checkout'):
            product_lines = order._unitrade_product_lines_for_checkout()
        else:
            fee_product = order._unitrade_service_fee_product() if hasattr(order, '_unitrade_service_fee_product') else self.env['product.product']
            payment_fee_product = order._unitrade_payment_fee_product() if hasattr(order, '_unitrade_payment_fee_product') else self.env['product.product']
            voucher_product = order._unitrade_voucher_discount_product() if hasattr(order, '_unitrade_voucher_discount_product') else self.env['product.product']
            excluded_product_ids = set()
            for excluded_product in (fee_product, payment_fee_product, voucher_product):
                if excluded_product:
                    excluded_product_ids.add(excluded_product.id)
            product_lines = order.order_line.filtered(
                lambda line: not line.display_type and line.product_id and line.product_id.id not in excluded_product_ids
            )
        lines_without_seller = product_lines.filtered(lambda line: not self._seller_from_line(line))
        if lines_without_seller:
            _logger.warning(
                'Skipping %s order line(s) without seller while creating escrow ledger for order %s',
                len(lines_without_seller),
                order.name,
            )
            product_lines = product_lines - lines_without_seller
        if not product_lines:
            _logger.warning('Skipping escrow ledger for order %s: no product lines found', order.name)
            return self.browse()

        amounts = order._unitrade_checkout_amounts(
            sync_fee=False,
            payment_method=payment_intent.payment_method_code,
        ) if hasattr(order, '_unitrade_checkout_amounts') else {
            'item_subtotal': sum(product_lines.mapped('price_subtotal')),
            'service_fee': 0.0,
            'payment_fee': payment_intent.amount_gateway_fee,
        }
        platform_fee_total = order.currency_id.round(amounts.get('service_fee', 0.0))
        gateway_fee_total = order.currency_id.round(payment_intent.amount_gateway_fee or amounts.get('payment_fee', 0.0))
        subtotal_total = order.currency_id.round(sum(product_lines.mapped('price_subtotal')))

        grouped = {}
        for line in product_lines:
            seller = self._seller_from_line(line)
            key = seller.id if seller else 0
            grouped.setdefault(key, {
                'seller': seller,
                'subtotal': 0.0,
            })
            grouped[key]['subtotal'] += line.price_subtotal

        ledgers = self.browse()
        allocated_fee = 0.0
        allocated_gateway_fee = 0.0
        groups = list(grouped.values())
        for index, group in enumerate(groups):
            subtotal = order.currency_id.round(group['subtotal'])
            if index == len(groups) - 1:
                platform_fee = order.currency_id.round(platform_fee_total - allocated_fee)
            elif subtotal_total:
                platform_fee = order.currency_id.round(platform_fee_total * subtotal / subtotal_total)
                allocated_fee += platform_fee
            else:
                platform_fee = 0.0

            if index == len(groups) - 1:
                gateway_fee = order.currency_id.round(gateway_fee_total - allocated_gateway_fee)
            elif subtotal_total:
                gateway_fee = order.currency_id.round(gateway_fee_total * subtotal / subtotal_total)
                allocated_gateway_fee += gateway_fee
            else:
                gateway_fee = 0.0

            amount_total = order.currency_id.round(subtotal + platform_fee + gateway_fee)
            ledger = self.create({
                'name': '%s / %s' % (order.name, group['seller'].display_name if group['seller'] else 'Seller'),
                'order_id': order.id,
                'payment_intent_id': payment_intent.id,
                'seller_id': group['seller'].id if group['seller'] else False,
                'buyer_id': order.partner_id.id,
                'currency_id': order.currency_id.id,
                'amount_total': amount_total,
                'amount_platform_fee': platform_fee,
                'amount_gateway_fee': gateway_fee,
                'amount_seller': subtotal,
                'state': 'held',
            })
            ledgers |= ledger

        return ledgers

    @api.model
    def ensure_for_order(self, order):
        """Return existing ledgers for an order or create them from its active intent."""
        order = order.sudo()
        payment_intent = order.x_payment_intent_id.sudo() if order.x_payment_intent_id else False
        if not payment_intent:
            return self.browse()

        existing = self.sudo().search([
            ('order_id', '=', order.id),
            ('payment_intent_id', '=', payment_intent.id),
        ])
        if existing:
            return existing

        if order.x_payment_status != 'paid' and payment_intent.state != 'paid':
            return self.browse()
        return self._create_for_order(order, payment_intent)

    def _sync_order_escrow_state(self):
        orders = self.sudo().mapped('order_id')
        Ledger = self.env['unitrade.escrow.ledger'].sudo()
        for order in orders:
            ledgers = Ledger.search([('order_id', '=', order.id)])
            states = set(ledgers.mapped('state'))
            if not states:
                state = 'none'
            elif 'disputed' in states:
                state = 'disputed'
            elif 'refunded' in states:
                state = 'refunded'
            elif 'cancelled' in states:
                state = 'cancelled'
            elif states == {'released'}:
                state = 'released'
            elif 'releasable' in states:
                state = 'releasable'
            elif 'held' in states:
                state = 'held'
            else:
                state = 'none'

            values = {'x_escrow_state': state}
            completed_ledgers = ledgers.filtered(
                lambda ledger: (
                    ledger.buyer_confirmed_at
                    and ledger.seller_confirmed_at
                    and ledger.state in ('releasable', 'released')
                )
            )
            all_confirmed = bool(ledgers) and len(completed_ledgers) == len(ledgers)
            if all_confirmed:
                completed_ledgers._unitrade_mark_delivery_delivered()
                values['x_unitrade_order_state'] = 'completed'
                if not order.x_completed_at:
                    values['x_completed_at'] = fields.Datetime.now()
            elif state == 'cancelled':
                values['x_unitrade_order_state'] = 'cancelled'
            elif state == 'refunded':
                values['x_unitrade_order_state'] = 'refunded'
                values['x_payment_status'] = 'refunded'
            elif state == 'disputed':
                values['x_unitrade_order_state'] = 'processing'
            elif state in ('held', 'releasable', 'released') and order.x_payment_status == 'paid':
                values['x_unitrade_order_state'] = 'processing'
            order.sudo().write(values)

    def _mark_releasable_if_fully_confirmed(self):
        now = fields.Datetime.now()
        ready_ledgers = self.sudo().filtered(
            lambda ledger: (
                ledger.state == 'held'
                and ledger.buyer_confirmed_at
                and ledger.seller_confirmed_at
            )
        )
        if ready_ledgers:
            ready_ledgers.write({
                'state': 'releasable',
                'completed_at': now,
            })
        self._sync_order_escrow_state()

    @api.model
    def cron_auto_confirm_buyer_receipt(self):
        raw_hours = self.env['ir.config_parameter'].sudo().get_param(
            'unitrade.escrow.auto_confirm_receipt_hours',
            default='48',
        )
        try:
            timeout_hours = int(float(raw_hours or 48))
        except (TypeError, ValueError):
            timeout_hours = 48
        timeout_hours = max(1, min(timeout_hours, 24 * 14))
        cutoff = fields.Datetime.now() - timedelta(hours=timeout_hours)

        ledgers = self.sudo().search([
            ('state', '=', 'held'),
            ('seller_confirmed_at', '!=', False),
            ('seller_confirmed_at', '<=', cutoff),
            ('buyer_confirmed_at', '=', False),
            ('order_id.x_payment_status', '=', 'paid'),
            ('order_id.x_unitrade_order_state', 'not in', ['cancelled', 'completed']),
        ])
        if not ledgers:
            return True

        now = fields.Datetime.now()
        confirmed_ledgers = self.browse()
        for ledger in ledgers:
            try:
                with self.env.cr.savepoint():
                    ledger.write({
                        'buyer_confirmed_at': now,
                        'buyer_received_filename': _('Dikonfirmasi otomatis setelah 2x24 jam'),
                    })
                    confirmed_ledgers |= ledger
            except Exception:
                _logger.exception('Failed to auto-confirm buyer receipt for escrow ledger %s', ledger.id)

        if confirmed_ledgers:
            confirmed_ledgers._mark_releasable_if_fully_confirmed()
            _logger.info('Auto-confirmed %s UniTrade escrow ledger(s) after buyer receipt timeout.', len(confirmed_ledgers))
        return True

    def _ensure_confirmable(self):
        for ledger in self:
            if ledger.state in ('cancelled', 'refunded', 'disputed', 'released'):
                raise UserError(_('Escrow %s sudah tidak bisa dikonfirmasi.') % (ledger.name or ledger.id))
            if ledger.order_id.x_payment_status != 'paid':
                raise UserError(_('Pesanan %s belum dibayar.') % (ledger.order_id.name or ledger.order_id.id))
            if ledger.order_id.x_unitrade_order_state in ('cancelled', 'completed'):
                raise UserError(_('Pesanan %s sudah tidak bisa dikonfirmasi.') % (ledger.order_id.name or ledger.order_id.id))

    def _prepare_evidence_values(self, field_name, filename_field_name, evidence=False, filename=False):
        self.ensure_one()
        if evidence:
            return {
                field_name: evidence,
                filename_field_name: filename or 'bukti-barang.jpg',
            }
        if not self[field_name]:
            raise UserError(_('Upload foto barang terlebih dahulu.'))
        return {}

    def action_buyer_confirm_received(self, evidence=False, filename=False):
        ledgers = self.sudo().exists()
        ledgers._ensure_confirmable()
        pending = ledgers.filtered(lambda ledger: not ledger.buyer_confirmed_at)
        if pending:
            now = fields.Datetime.now()
            for ledger in pending:
                if not ledger.seller_confirmed_at:
                    raise UserError(_('Penjual harus mengunggah bukti barang diserahkan terlebih dahulu.'))
                values = ledger._prepare_evidence_values(
                    'buyer_received_image',
                    'buyer_received_filename',
                    evidence=evidence,
                    filename=filename,
                )
                values['buyer_confirmed_at'] = now
                ledger.write(values)
        ledgers._mark_releasable_if_fully_confirmed()
        return True

    def action_seller_confirm_handoff(self, evidence=False, filename=False, location=False):
        ledgers = self.sudo().exists()
        ledgers._ensure_confirmable()
        pending = ledgers.filtered(lambda ledger: not ledger.seller_confirmed_at)
        if pending:
            now = fields.Datetime.now()
            for ledger in pending:
                values = ledger._prepare_evidence_values(
                    'seller_handoff_image',
                    'seller_handoff_filename',
                    evidence=evidence,
                    filename=filename,
                )
                if location:
                    values['seller_handoff_location'] = location
                values['seller_confirmed_at'] = now
                ledger.write(values)
            pending._unitrade_mark_delivery_picked_up()
        ledgers._mark_releasable_if_fully_confirmed()
        return True

    def _unitrade_mark_delivery_picked_up(self):
        """Move GoSend delivery out of Pending after seller hands off goods."""
        if 'unitrade.delivery' not in self.env.registry:
            return
        Delivery = self.env['unitrade.delivery'].sudo()
        for order in self.mapped('order_id').sudo():
            if 'x_shipping_method' not in order._fields or order.x_shipping_method != 'gosend':
                continue
            delivery = Delivery.search([('order_id', '=', order.id)], order='create_date desc', limit=1)
            if not delivery and hasattr(order, '_unitrade_create_shipping_delivery'):
                order._unitrade_create_shipping_delivery()
                delivery = Delivery.search([('order_id', '=', order.id)], order='create_date desc', limit=1)
            if delivery and delivery.status == 'pending':
                delivery.write({'status': 'picked_up'})

    def _unitrade_mark_delivery_delivered(self):
        """Complete GoSend delivery when the buyer has confirmed receipt."""
        if 'unitrade.delivery' not in self.env.registry:
            return
        Delivery = self.env['unitrade.delivery'].sudo()
        for order in self.mapped('order_id').sudo():
            if 'x_shipping_method' not in order._fields or order.x_shipping_method != 'gosend':
                continue
            delivery = Delivery.search([('order_id', '=', order.id)], order='create_date desc', limit=1)
            if not delivery and hasattr(order, '_unitrade_create_shipping_delivery'):
                order._unitrade_create_shipping_delivery()
                delivery = Delivery.search([('order_id', '=', order.id)], order='create_date desc', limit=1)
            if delivery and delivery.status != 'delivered':
                delivery.write({'status': 'delivered'})

    def action_mark_releasable(self):
        self._check_admin('mark_releasable')
        reason = self._manual_action_reason()
        ledgers = self.filtered(lambda ledger: ledger.state == 'held')
        ledgers.write({'state': 'releasable'})
        ledgers._sync_order_escrow_state()
        for ledger in ledgers:
            ledger._audit(
                'escrow.mark_releasable',
                _('Escrow %s ditandai releasable oleh %s. Alasan: %s') % (
                    ledger.name, self.env.user.name, reason,
                ),
                severity='info',
                payload={
                    'order_id': ledger.order_id.id,
                    'order_name': ledger.order_id.name,
                    'seller_id': ledger.seller_id.id,
                    'amount_seller': ledger.amount_seller,
                    'reason': reason,
                },
            )
        return True

    def action_mark_released(self):
        self._check_admin('mark_released')
        reason = self._manual_action_reason()
        ledgers = self.filtered(lambda ledger: ledger.state == 'releasable')
        ledgers.write({
            'state': 'released',
            'released_at': fields.Datetime.now(),
        })
        ledgers._sync_order_escrow_state()
        for ledger in ledgers:
            ledger._audit(
                'escrow.release',
                _('Escrow %s direlease manual oleh %s sejumlah %s. Alasan: %s') % (
                    ledger.name, self.env.user.name, ledger.amount_seller, reason,
                ),
                severity='warning',
                payload={
                    'order_id': ledger.order_id.id,
                    'order_name': ledger.order_id.name,
                    'seller_id': ledger.seller_id.id,
                    'amount_seller': ledger.amount_seller,
                    'reason': reason,
                },
            )
        return True

    def action_simulate_seller_payout(self, payout=False):
        """Deprecated compatibility hook: seller payout is admin-managed."""
        raise UserError(_(
            'Payout otomatis/simulasi langsung sudah dinonaktifkan. '
            'Buat request payout manual lalu tandai Paid setelah admin transfer.'
        ))

    def action_create_xendit_payout(self):
        """Deprecated compatibility hook: never call a payout gateway."""
        raise UserError(_(
            'Payout gateway dinonaktifkan untuk seller. Gunakan Buat Payout Manual.'
        ))


    # ------------------------------------------------------------------
    # Manual payout integration (server action target)
    # ------------------------------------------------------------------
    def action_create_seller_payout(self):
        """Server action: create draft payout from selected ledgers (one per seller)."""
        self._check_admin('create_seller_payout')
        if not self:
            raise UserError(_('Pilih minimal satu ledger.'))

        # Validate all ledgers are eligible
        invalid = self.filtered(
            lambda l: l.state != 'releasable' or l.payout_status in ('pending', 'processing', 'succeeded')
        )
        if invalid:
            raise UserError(_(
                'Beberapa ledger tidak releasable atau sudah masuk/diproses payout: %s'
            ) % ', '.join(invalid.mapped('name') or []))

        no_seller = self.filtered(lambda l: not l.seller_id)
        if no_seller:
            raise UserError(_('Ledger %s tidak punya seller. Tidak bisa dibuatkan payout.')
                            % ', '.join(no_seller.mapped('name') or []))

        # Group per seller
        Payout = self.env['unitrade.seller.payout']
        sellers = {}
        for ledger in self:
            sellers.setdefault(ledger.seller_id.id, self.browse())
            sellers[ledger.seller_id.id] |= ledger

        created = self.env['unitrade.seller.payout']
        for seller_id, ledgers in sellers.items():
            # Cek ledger yang sudah masuk payout aktif
            existing = Payout.search([
                ('seller_id', '=', seller_id),
                ('state', 'in', Payout._active_payout_states(include_paid=True)),
                ('ledger_ids', 'in', ledgers.ids),
            ])
            if existing:
                used_ledgers = existing.mapped('ledger_ids') & ledgers
                raise UserError(_(
                    'Ledger berikut sudah masuk payout aktif: %s'
                ) % ', '.join(used_ledgers.mapped('name') or []))

            payout = Payout.create({
                'seller_id': seller_id,
                'state': 'draft',
                'amount': sum(ledgers.mapped('amount_seller')),
                'currency_id': ledgers[:1].currency_id.id or self.env.company.currency_id.id,
                'ledger_ids': [(6, 0, ledgers.ids)],
                'ledger_ids_json': Payout._ledger_ids_json(ledgers),
                **Payout._destination_snapshot_vals(ledgers[:1].seller_id),
            })
            created |= payout

        if len(created) == 1:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'unitrade.seller.payout',
                'res_id': created.id,
                'view_mode': 'form',
                'target': 'current',
            }
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'unitrade.seller.payout',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', created.ids)],
            'target': 'current',
        }
