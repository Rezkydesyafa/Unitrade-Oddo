import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare
from odoo.addons.unitrade_payment.xendit_methods import (
    XENDIT_PAYMENT_METHODS,
    xendit_method_enabled,
    xendit_method_fee,
)
from odoo.addons.unitrade_payment.midtrans_methods import (
    MIDTRANS_PAYMENT_METHODS,
    midtrans_method_enabled,
    midtrans_method_fee,
)

_logger = logging.getLogger(__name__)


class SaleOrderUniTrade(models.Model):
    _inherit = 'sale.order'

    x_payment_intent_id = fields.Many2one(
        'unitrade.payment.intent',
        string='Payment Intent',
        copy=False,
        readonly=True,
        ondelete='set null',
    )
    x_payment_provider = fields.Selection([
        ('xendit', 'Xendit'),
        ('doku', 'DOKU'),
        ('midtrans', 'Midtrans'),
    ], string='Provider Pembayaran', default='midtrans', readonly=True, copy=False)
    x_midtrans_order_id = fields.Char(string='Midtrans Order ID', readonly=True, copy=False)
    x_midtrans_transaction_id = fields.Char(string='Midtrans Transaction ID', readonly=True, copy=False)
    x_midtrans_payment_type = fields.Char(string='Midtrans Payment Type', readonly=True, copy=False)
    x_midtrans_snap_token = fields.Char(string='Snap Token', readonly=True, copy=False)
    x_doku_invoice_number = fields.Char(string='DOKU Invoice', readonly=True, copy=False)
    x_doku_payment_url = fields.Char(string='DOKU Payment URL', readonly=True, copy=False)
    x_doku_token_id = fields.Char(string='DOKU Token', readonly=True, copy=False)
    x_doku_request_id = fields.Char(string='DOKU Request ID', readonly=True, copy=False)
    x_xendit_reference_id = fields.Char(string='Xendit Reference', readonly=True, copy=False)
    x_xendit_payment_request_id = fields.Char(string='Xendit Payment Request', readonly=True, copy=False)
    x_xendit_payment_url = fields.Char(string='Xendit Payment URL', readonly=True, copy=False)
    x_xendit_channel_code = fields.Char(string='Xendit Channel', readonly=True, copy=False)
    x_payment_status = fields.Selection([
        ('pending', 'Menunggu Pembayaran'),
        ('paid', 'Dibayar'),
        ('failed', 'Gagal'),
        ('expired', 'Kadaluarsa'),
        ('cancelled', 'Dibatalkan'),
        ('refunded', 'Refund'),
    ], string='Status Pembayaran', default='pending', tracking=True)
    x_payment_method = fields.Char(string='Metode Pembayaran', readonly=True)
    x_paid_at = fields.Datetime(string='Waktu Pembayaran', readonly=True)
    x_completed_at = fields.Datetime(string='Waktu Selesai UniTrade', readonly=True, copy=False)
    x_escrow_state = fields.Selection([
        ('none', 'Belum Ada'),
        ('held', 'Held'),
        ('releasable', 'Releasable'),
        ('released', 'Released'),
        ('disputed', 'Disputed'),
        ('refunded', 'Refunded'),
        ('cancelled', 'Cancelled'),
    ], string='Status Escrow', default='none', tracking=True, readonly=True, copy=False)
    x_unitrade_order_state = fields.Selection([
        ('cart', 'Cart'),
        ('payment_pending', 'Menunggu Pembayaran'),
        ('paid_escrow', 'Dana Ditahan'),
        ('processing', 'Diproses'),
        ('completed', 'Selesai'),
        ('cancelled', 'Dibatalkan'),
        ('refunded', 'Refund'),
    ], string='Status UniTrade', default='cart', tracking=True, readonly=True, copy=False)
    x_cancel_deadline_at = fields.Datetime(string='Batas Cancel Langsung', readonly=True, copy=False)
    x_cancelled_by_id = fields.Many2one('res.users', string='Dibatalkan Oleh', readonly=True, copy=False)
    x_cancelled_at = fields.Datetime(string='Waktu Pembatalan', readonly=True, copy=False)
    x_cancel_reason = fields.Text(string='Alasan Pembatalan', readonly=True, copy=False)
    x_unitrade_voucher_id = fields.Many2one('unitrade.voucher', string='Voucher UniTrade', readonly=True, copy=False)
    x_unitrade_voucher_code = fields.Char(string='Kode Voucher UniTrade', readonly=True, copy=False)
    x_unitrade_voucher_name = fields.Char(string='Nama Voucher UniTrade', readonly=True, copy=False)
    x_unitrade_voucher_discount = fields.Monetary(
        string='Diskon Voucher UniTrade',
        currency_field='currency_id',
        readonly=True,
        copy=False,
    )

    def _get_midtrans_key(self, key_name):
        return self.env['ir.config_parameter'].sudo().get_param(key_name, default='')

    def _get_midtrans_param(self, key_name, default=''):
        return self.env['ir.config_parameter'].sudo().get_param(key_name, default=default)

    def _midtrans_api_base_url(self):
        is_production = str(self._get_midtrans_param('unitrade.midtrans.is_production', 'False')).lower() in ('true', '1', 'yes', 'y')
        return 'https://api.midtrans.com' if is_production else 'https://api.sandbox.midtrans.com'

    def _midtrans_payment_expiry_minutes(self):
        raw = self._get_midtrans_param('unitrade.midtrans.payment_expiry_minutes', '30')
        try:
            minutes = int(raw)
        except (TypeError, ValueError):
            minutes = 30
        return max(15, min(minutes, 1440))

    def _get_xendit_param(self, key_name, default=''):
        return self.env['ir.config_parameter'].sudo().get_param(key_name, default=default)

    def _xendit_api_base_url(self):
        return 'https://api.xendit.co'

    def _xendit_payment_expiry_minutes(self):
        raw = self._get_xendit_param('unitrade.xendit.payment_expiry_minutes', '30')
        try:
            minutes = int(raw)
        except (TypeError, ValueError):
            minutes = 30
        return max(5, min(minutes, 1440))

    def _unitrade_cancel_window_minutes(self):
        raw = self.env['ir.config_parameter'].sudo().get_param('unitrade.order.cancel_window_minutes', '30')
        try:
            minutes = int(raw)
        except (TypeError, ValueError):
            minutes = 30
        return max(1, min(minutes, 1440))

    def _unitrade_new_cancel_deadline(self):
        return fields.Datetime.now() + timedelta(minutes=self._unitrade_cancel_window_minutes())

    def _unitrade_payment_pending_cancel_deadline(self):
        self.ensure_one()
        intent = self.x_payment_intent_id.sudo() if self.x_payment_intent_id else False
        if (
            intent
            and intent.state in ('draft', 'pending')
            and self.x_payment_status == 'pending'
            and self.x_unitrade_order_state == 'payment_pending'
            and intent.create_date
        ):
            return intent.create_date + timedelta(minutes=self._unitrade_cancel_window_minutes())
        return self.x_cancel_deadline_at

    def _unitrade_escrow_ledgers(self):
        self.ensure_one()
        if 'unitrade.escrow.ledger' not in self.env.registry:
            return self.env['sale.order'].browse()
        return self.env['unitrade.escrow.ledger'].sudo().search([('order_id', '=', self.id)])

    def _unitrade_marketplace_order_lines(self):
        self.ensure_one()
        return self.order_line.sudo().filtered(
            lambda line: (
                not line.display_type
                and line.product_id
                and line.product_id.product_tmpl_id
                and 'x_is_marketplace' in line.product_id.product_tmpl_id._fields
                and line.product_id.product_tmpl_id.x_is_marketplace
                and 'x_seller_id' in line.product_id.product_tmpl_id._fields
                and line.product_id.product_tmpl_id.x_seller_id
            )
        )

    def _unitrade_repair_payment_intent(self):
        self.ensure_one()
        PaymentIntent = self.env['unitrade.payment.intent'].sudo()
        intent = self.x_payment_intent_id.sudo() if self.x_payment_intent_id else PaymentIntent.browse()
        if not intent:
            intent = PaymentIntent.search([
                ('sale_order_id', '=', self.id),
                ('intent_type', '=', 'order_checkout'),
                ('state', '=', 'paid'),
            ], order='create_date desc, id desc', limit=1)
        if intent:
            if not self.x_payment_intent_id:
                self.sudo().write({'x_payment_intent_id': intent.id})
            return intent

        primary_seller = self._unitrade_primary_seller() if hasattr(self, '_unitrade_primary_seller') else False
        intent = PaymentIntent.create({
            'name': 'REPAIR-%s-%s' % (self.name or self.id, self.id),
            'provider': self.x_payment_provider or 'midtrans',
            'intent_type': 'order_checkout',
            'state': 'paid',
            'amount': self.amount_total,
            'currency_id': self.currency_id.id,
            'sale_order_id': self.id,
            'partner_id': self.partner_id.id,
            'seller_id': primary_seller.id if primary_seller else False,
            'payment_method_code': 'data_repair',
            'payment_method_label': _('Data repair'),
            'paid_at': self.x_paid_at or self.date_order or fields.Datetime.now(),
            'raw_response': json.dumps({
                'source': 'unitrade_payment.data_repair',
                'reason': 'Backfill paid marketplace order without escrow ledger.',
            }, ensure_ascii=False),
        })
        self.sudo().write({'x_payment_intent_id': intent.id})
        return intent

    @api.model
    def _unitrade_backfill_missing_escrow_ledgers(self, limit=None):
        if 'unitrade.escrow.ledger' not in self.env.registry or 'unitrade.payment.intent' not in self.env.registry:
            return True

        Order = self.sudo()
        Ledger = self.env['unitrade.escrow.ledger'].sudo()
        orders = Order.search([
            ('x_payment_status', '=', 'paid'),
            ('state', 'in', ('sale', 'done')),
        ], order='id asc', limit=limit)

        repaired = 0
        for order in orders:
            if Ledger.search_count([('order_id', '=', order.id)]):
                continue
            if not order._unitrade_marketplace_order_lines():
                continue
            try:
                with self.env.cr.savepoint():
                    intent = order._unitrade_repair_payment_intent()
                    ledgers = Ledger._create_for_order(order, intent)
                    if order.x_unitrade_order_state == 'completed' and ledgers:
                        completed_at = order.x_completed_at or order.x_paid_at or order.date_order or fields.Datetime.now()
                        ledgers.write({
                            'state': 'releasable',
                            'seller_confirmed_at': completed_at,
                            'buyer_confirmed_at': completed_at,
                            'completed_at': completed_at,
                            'seller_handoff_filename': _('Direkonsiliasi dari data order lama'),
                            'buyer_received_filename': _('Direkonsiliasi dari data order lama'),
                        })
                    if ledgers:
                        ledgers._sync_order_escrow_state()
                        repaired += len(ledgers)
            except Exception:
                _logger.exception('Failed to backfill UniTrade escrow ledger for order %s', order.name)

        if repaired:
            _logger.info('Backfilled %s missing UniTrade escrow ledger(s).', repaired)
        return True

    def unitrade_status_payload(self, ledger=False):
        """Centralized UniTrade order status labels matching the analysis document."""
        self.ensure_one()
        if self.state == 'cancel':
            return {'key': 'cancel', 'label': _('Dibatalkan')}
        payment_status = self.x_payment_status or ''
        unitrade_state = self.x_unitrade_order_state or ''
        if payment_status == 'refunded' or unitrade_state == 'refunded':
            return {'key': 'refund', 'label': _('Pengembalian')}
        if payment_status in ('failed', 'expired', 'cancelled') or unitrade_state == 'cancelled':
            return {'key': 'cancel', 'label': _('Dibatalkan')}
        if 'unitrade.dispute' in self.env.registry:
            refund_domain = [
                ('order_id', '=', self.id),
                ('state', 'in', self.env['unitrade.dispute'].ACTIVE_STATES),
            ]
            if ledger:
                refund_domain.append(('escrow_ledger_id', '=', ledger.id))
            if self.env['unitrade.dispute'].sudo().search(refund_domain, limit=1):
                return {
                    'key': 'refund',
                    'label': _('Pengembalian'),
                    'note': _('Pengajuan refund sedang ditinjau UniTrade.'),
                    'can_confirm_received': False,
                    'can_cancel_order': False,
                }
        if payment_status in ('pending', '') and self.state not in ('sale', 'done'):
            cancel_blocker = self._unitrade_direct_cancel_blocker() if hasattr(self, '_unitrade_direct_cancel_blocker') else True
            return {
                'key': 'unpaid',
                'label': _('Menunggu Pembayaran'),
                'note': _('Selesaikan pembayaran atau batalkan pesanan jika tidak jadi membayar.'),
                'can_cancel_order': not bool(cancel_blocker),
            }
        if unitrade_state == 'completed':
            return {'key': 'done', 'label': _('Selesai')}
        if payment_status == 'paid':
            buyer_confirmed = bool(ledger and ledger.buyer_confirmed_at)
            seller_confirmed = bool(ledger and ledger.seller_confirmed_at)
            if seller_confirmed and not buyer_confirmed:
                return {
                    'key': 'confirmation',
                    'label': _('Menunggu Konfirmasi'),
                    'note': _('Penjual sudah menyerahkan barang. Konfirmasi setelah barang diterima.'),
                    'can_confirm_received': bool(ledger),
                    'can_cancel_order': False,
                }
            cancel_blocker = self._unitrade_direct_cancel_blocker() if hasattr(self, '_unitrade_direct_cancel_blocker') else True
            return {
                'key': 'processing',
                'label': _('Diproses'),
                'note': _('Menunggu penjual menyerahkan barang dan mengunggah bukti.'),
                'can_confirm_received': False,
                'can_cancel_order': not bool(cancel_blocker),
            }
        if self.state in ('sale', 'done'):
            return {'key': 'done', 'label': _('Selesai')}
        return {'key': 'unpaid', 'label': _('Menunggu Pembayaran')}

    def _unitrade_validate_buyer_partner(self, partner):
        self.ensure_one()
        if not partner:
            return
        if self.partner_id.commercial_partner_id != partner.commercial_partner_id:
            raise UserError(_('Anda tidak memiliki akses ke pesanan ini.'))

    def action_unitrade_buyer_confirm_received(self, partner=None, ledger=False, evidence=False, filename=False):
        for order in self.sudo():
            order._unitrade_validate_buyer_partner(partner)
            if order.x_unitrade_order_state in ('cancelled', 'completed') or order.state == 'cancel':
                raise UserError(_('Pesanan ini sudah tidak bisa dikonfirmasi.'))
            if order.x_payment_status != 'paid':
                raise UserError(_('Pesanan hanya bisa diselesaikan setelah pembayaran berhasil.'))

            ledgers = order._unitrade_escrow_ledgers()
            if ledger:
                ledger = ledger.sudo().exists()
                if not ledger or ledger.order_id.id != order.id:
                    raise UserError(_('Data escrow pesanan tidak valid.'))
                ledgers = ledger
            if not ledgers:
                raise UserError(_('Escrow pesanan belum tersedia.'))
            ledgers.action_buyer_confirm_received(evidence=evidence, filename=filename)
        return True

    def _unitrade_direct_cancel_blocker(self):
        self.ensure_one()
        now = fields.Datetime.now()
        cancel_deadline = self._unitrade_payment_pending_cancel_deadline()
        if self.x_unitrade_order_state == 'completed':
            return _('Pesanan sudah selesai dan tidak bisa dibatalkan langsung.')
        if self.x_unitrade_order_state == 'cancelled' or self.state == 'cancel':
            return _('Pesanan sudah dibatalkan.')
        if self.x_payment_status not in ('pending', 'paid'):
            return _('Pesanan dengan status pembayaran ini tidak bisa dibatalkan langsung.')
        if not cancel_deadline:
            return _('Batas pembatalan langsung belum tersedia.')
        if cancel_deadline <= now:
            return _('Batas pembatalan langsung 30 menit sudah lewat.')
        ledgers = self._unitrade_escrow_ledgers()
        if ledgers.filtered(lambda ledger: ledger.seller_confirmed_at):
            return _('Penjual sudah mengonfirmasi serah barang, pembatalan langsung tidak tersedia.')
        return False

    def action_unitrade_cancel_by_buyer(self, partner=None, reason=''):
        for order in self.sudo():
            order._unitrade_validate_buyer_partner(partner)
            blocker = order._unitrade_direct_cancel_blocker()
            if blocker:
                raise UserError(blocker)

            now = fields.Datetime.now()
            ledgers = order._unitrade_escrow_ledgers()
            if ledgers:
                ledgers.filtered(lambda ledger: ledger.state in ('held', 'releasable')).write({'state': 'cancelled'})

            pending_intents = self.env['unitrade.payment.intent'].sudo().search([
                ('sale_order_id', '=', order.id),
                ('provider', 'in', ('midtrans', 'xendit')),
                ('state', 'in', ('draft', 'pending')),
            ])
            if pending_intents:
                pending_intents.write({
                    'state': 'cancelled',
                    'error_message': _('Dibatalkan pembeli dalam window 30 menit.'),
                })

            write_values = {
                'x_unitrade_order_state': 'cancelled',
                'x_escrow_state': 'cancelled',
                'x_cancelled_by_id': self.env.user.id,
                'x_cancelled_at': now,
                'x_cancel_reason': reason or _('Dibatalkan pembeli dalam window 30 menit.'),
            }
            if order.x_payment_status != 'paid':
                write_values['x_payment_status'] = 'cancelled'

            try:
                if order.state not in ('cancel', 'done'):
                    order.action_cancel()
            except Exception:
                _logger.exception('Failed to cancel sale order %s through action_cancel', order.name)
                raise
            order.write(write_values)
            if ledgers:
                ledgers._sync_order_escrow_state()
        return True

    def _unitrade_payment_fee_product(self):
        product = self.env.ref('unitrade_payment.product_unitrade_payment_fee', raise_if_not_found=False)
        if product:
            return product.sudo()

        product = self.env['product.product'].sudo().create({
            'name': 'Biaya Payment',
            'detailed_type': 'service',
            'sale_ok': True,
            'purchase_ok': False,
            'list_price': 0.0,
            'taxes_id': [(6, 0, [])],
        })
        self.env['ir.model.data'].sudo().create({
            'module': 'unitrade_payment',
            'name': 'product_unitrade_payment_fee',
            'model': 'product.product',
            'res_id': product.id,
            'noupdate': True,
        })
        return product

    def _unitrade_voucher_discount_product(self):
        product = self.env.ref('unitrade_payment.product_unitrade_voucher_discount', raise_if_not_found=False)
        if product:
            return product.sudo()
        product = self.env['product.product'].sudo().create({
            'name': 'UniTrade Voucher Discount',
            'detailed_type': 'service',
            'sale_ok': False,
            'purchase_ok': False,
            'list_price': 0.0,
            'taxes_id': [(6, 0, [])],
        })
        self.env['ir.model.data'].sudo().create({
            'module': 'unitrade_payment',
            'name': 'product_unitrade_voucher_discount',
            'model': 'product.product',
            'res_id': product.id,
            'noupdate': True,
        })
        return product

    def _unitrade_voucher_lines(self):
        self.ensure_one()
        voucher_product = self._unitrade_voucher_discount_product()
        return self.order_line.filtered(lambda line: voucher_product and line.product_id == voucher_product)

    def _unitrade_midtrans_checkout_methods(self, base_amount=None):
        self.ensure_one()
        config = self.env['ir.config_parameter'].sudo()
        grouped = {}
        base = base_amount
        if base is None:
            try:
                base = self._unitrade_checkout_amounts(sync_fee=False).get('item_subtotal', 0.0)
                base += self._unitrade_checkout_amounts(sync_fee=False).get('service_fee', 0.0)
            except Exception:
                base = self.amount_total

        for key, method in sorted(MIDTRANS_PAYMENT_METHODS.items(), key=lambda item: item[1].get('sequence', 999)):
            enabled = midtrans_method_enabled(config, key, method)
            fee = midtrans_method_fee(config, key, method, base)
            item = {
                'key': key,
                'label': method['label'],
                'group': method['group'],
                'channel_code': method['channel_code'],
                'type': method['type'],
                'logo': method.get('logo'),
                'enabled': enabled and method['type'] != 'CARD',
                'disabled_reason': method.get('disabled_reason') or _('Channel belum aktif di konfigurasi Midtrans.'),
                'sequence': method.get('sequence', 999),
                'fee': fee,
            }
            grouped.setdefault(method['group'], []).append(item)
        group_priority = {
            'E-Wallet & QRIS': 10,
            'Transfer Virtual Account': 20,
        }
        return [
            {'name': name, 'methods': methods}
            for name, methods in sorted(
                grouped.items(),
                key=lambda item: (group_priority.get(item[0], 90), item[0]),
            )
        ]

    def _unitrade_xendit_checkout_methods(self, base_amount=None):
        """Backward-compatible hook used by the existing checkout controller/template."""
        return self._unitrade_midtrans_checkout_methods(base_amount=base_amount)

    def _unitrade_payment_fee_amount(self, payment_method, base_amount):
        method = MIDTRANS_PAYMENT_METHODS.get(payment_method or 'bca_va') or MIDTRANS_PAYMENT_METHODS['bca_va']
        config = self.env['ir.config_parameter'].sudo()
        return self.currency_id.round(midtrans_method_fee(config, payment_method or 'bca_va', method, base_amount))

    def _unitrade_shipping_fee_product_safe(self):
        """Return shipping fee product if unitrade_delivery is installed, else empty."""
        if hasattr(self, '_unitrade_shipping_fee_product'):
            return self._unitrade_shipping_fee_product()
        product = self.env.ref('unitrade_delivery.product_unitrade_shipping_fee', raise_if_not_found=False)
        return product.sudo() if product else self.env['product.product']

    def _unitrade_product_lines_for_checkout(self):
        self.ensure_one()
        service_fee_product = self._unitrade_service_fee_product() if hasattr(self, '_unitrade_service_fee_product') else self.env['product.product']
        payment_fee_product = self._unitrade_payment_fee_product()
        voucher_product = self._unitrade_voucher_discount_product()
        shipping_fee_product = self._unitrade_shipping_fee_product_safe()
        return self.order_line.filtered(
            lambda line: (
                not line.display_type
                and line.product_id
                and line.product_id != service_fee_product
                and line.product_id != payment_fee_product
                and line.product_id != voucher_product
                and (not shipping_fee_product or line.product_id != shipping_fee_product)
            )
        )

    def _unitrade_clear_voucher_lines(self):
        for order in self.sudo():
            voucher_lines = order._unitrade_voucher_lines()
            if voucher_lines:
                voucher_lines.unlink()
        return True

    def _unitrade_sync_voucher_line(self, amount):
        self.ensure_one()
        voucher_product = self._unitrade_voucher_discount_product()
        voucher_lines = self._unitrade_voucher_lines()
        if not voucher_product:
            return
        amount = self.currency_id.round(amount or 0.0)
        if amount > 0:
            values = {
                'order_id': self.id,
                'product_id': voucher_product.id,
                'product_uom_qty': 1.0,
                'price_unit': -amount,
                'name': self.x_unitrade_voucher_name or self.x_unitrade_voucher_code or voucher_product.display_name,
                'tax_id': [(6, 0, [])],
            }
            if voucher_lines:
                voucher_lines[0].sudo().write({
                    'product_uom_qty': 1.0,
                    'price_unit': -amount,
                    'name': values['name'],
                    'tax_id': [(6, 0, [])],
                })
                stale_lines = voucher_lines - voucher_lines[0]
                if stale_lines:
                    stale_lines.sudo().unlink()
            else:
                self.env['sale.order.line'].sudo().create(values)
        else:
            self._unitrade_clear_voucher_lines()

    def _unitrade_voucher_buyer_user(self):
        self.ensure_one()
        portal_users = self.partner_id.user_ids.filtered(lambda user: not user.has_group('base.group_user'))
        return portal_users[:1] or self.env.user

    def _unitrade_apply_voucher_code(self, code):
        self.ensure_one()
        if self.state != 'draft':
            raise ValidationError(_('Voucher hanya bisa diterapkan sebelum pembayaran dibuat.'))
        normalized = self.env['unitrade.voucher']._normalize_code(code)
        if not normalized:
            raise ValidationError(_('Masukkan kode voucher.'))
        voucher = self.env['unitrade.voucher'].sudo().search([('code', '=', normalized)], limit=1)
        if not voucher:
            raise ValidationError(_('Kode voucher tidak ditemukan.'))
        if hasattr(self, '_unitrade_sync_checkout_product_prices'):
            self._unitrade_sync_checkout_product_prices()
        product_lines = self._unitrade_product_lines_for_checkout()
        subtotal = self.currency_id.round(sum(product_lines.mapped('price_subtotal')))
        voucher._validate_for_order(self, user=self._unitrade_voucher_buyer_user(), subtotal=subtotal)
        discount = voucher._discount_for_order(self, subtotal=subtotal)
        if discount <= 0:
            raise ValidationError(_('Voucher tidak menghasilkan diskon untuk keranjang ini.'))
        self.sudo().write({
            'x_unitrade_voucher_id': voucher.id,
            'x_unitrade_voucher_code': normalized,
            'x_unitrade_voucher_name': voucher.name or normalized,
            'x_unitrade_voucher_discount': discount,
        })
        self._unitrade_sync_voucher_line(discount)
        self.invalidate_recordset(['order_line', 'amount_untaxed', 'amount_tax', 'amount_total'])
        return self._unitrade_checkout_amounts(sync_fee=False)

    def _unitrade_remove_voucher(self):
        for order in self.sudo():
            order.write({
                'x_unitrade_voucher_id': False,
                'x_unitrade_voucher_code': False,
                'x_unitrade_voucher_name': False,
                'x_unitrade_voucher_discount': 0.0,
            })
            order._unitrade_clear_voucher_lines()
            order.invalidate_recordset(['order_line', 'amount_untaxed', 'amount_tax', 'amount_total'])
        return True

    def _unitrade_checkout_amounts(self, sync_fee=False, payment_method=None):
        self.ensure_one()
        service_fee_product = self._unitrade_service_fee_product() if hasattr(self, '_unitrade_service_fee_product') else self.env['product.product']
        payment_fee_product = self._unitrade_payment_fee_product()
        voucher_product = self._unitrade_voucher_discount_product()
        service_fee_lines = self.order_line.filtered(lambda line: line.product_id == service_fee_product)
        payment_fee_lines = self.order_line.filtered(lambda line: line.product_id == payment_fee_product)
        voucher_lines = self.order_line.filtered(lambda line: line.product_id == voucher_product)
        product_lines = self._unitrade_product_lines_for_checkout()

        if sync_fee and self.state == 'draft':
            fee_lines = service_fee_lines | payment_fee_lines
            if fee_lines:
                fee_lines.sudo().unlink()
                self.invalidate_recordset(['order_line', 'amount_untaxed', 'amount_tax', 'amount_total'])
                service_fee_lines = self.order_line.filtered(lambda line: line.product_id == service_fee_product)
                payment_fee_lines = self.order_line.filtered(lambda line: line.product_id == payment_fee_product)
                voucher_lines = self.order_line.filtered(lambda line: line.product_id == voucher_product)
                product_lines = self._unitrade_product_lines_for_checkout()

            taxed_lines = product_lines.filtered(lambda line: line.tax_id)
            if taxed_lines:
                taxed_lines.sudo().write({'tax_id': [(6, 0, [])]})
                self.invalidate_recordset(['order_line', 'amount_untaxed', 'amount_tax', 'amount_total'])
                product_lines = self._unitrade_product_lines_for_checkout()

        subtotal = self.currency_id.round(sum(product_lines.mapped('price_subtotal')))
        service_fee = self._unitrade_service_fee_amount(subtotal) if hasattr(self, '_unitrade_service_fee_amount') else 0.0
        voucher_discount = 0.0
        if self.x_unitrade_voucher_id:
            try:
                self.x_unitrade_voucher_id.sudo()._validate_for_order(
                    self,
                    user=self._unitrade_voucher_buyer_user(),
                    subtotal=subtotal,
                )
                voucher_discount = self.x_unitrade_voucher_id.sudo()._discount_for_order(self, subtotal=subtotal)
                # Backfill voucher name for orders applied before this field existed
                if not self.x_unitrade_voucher_name:
                    voucher_name = self.x_unitrade_voucher_id.sudo().name or self.x_unitrade_voucher_code or ''
                    if voucher_name:
                        self.sudo().write({'x_unitrade_voucher_name': voucher_name})
            except ValidationError:
                if sync_fee and self.state == 'draft':
                    self._unitrade_remove_voucher()
                    voucher_lines = self.env['sale.order.line'].browse()
                voucher_discount = 0.0
        elif voucher_lines and sync_fee and self.state == 'draft':
            voucher_lines.sudo().unlink()
            voucher_lines = self.env['sale.order.line'].browse()

        if sync_fee and self.state == 'draft':
            self.sudo().write({'x_unitrade_voucher_discount': voucher_discount})
            self._unitrade_sync_voucher_line(voucher_discount)

        payment_base = self.currency_id.round(max(subtotal + service_fee - voucher_discount, 0.0))
        payment_fee = self._unitrade_payment_fee_amount(payment_method, payment_base) if payment_method else 0.0

        shipping_cost = 0.0
        shipping_method = 'pickup'
        shipping_fee_product = self._unitrade_shipping_fee_product_safe()
        if 'x_shipping_method' in self._fields:
            shipping_method = self.x_shipping_method or 'pickup'
            shipping_cost = self.currency_id.round(self.x_shipping_cost or 0.0)

        return {
            'service_fee_product_id': service_fee_product.id if service_fee_product else False,
            'payment_fee_product_id': payment_fee_product.id if payment_fee_product else False,
            'voucher_discount_product_id': voucher_product.id if voucher_product else False,
            'shipping_fee_product_id': shipping_fee_product.id if shipping_fee_product else False,
            'item_subtotal': subtotal,
            'service_fee': service_fee,
            'payment_fee': payment_fee,
            'shipping_cost': shipping_cost,
            'shipping_method': shipping_method,
            'voucher_discount': voucher_discount,
            'voucher_code': self.x_unitrade_voucher_code or '',
            'voucher_name': self.x_unitrade_voucher_name or self.x_unitrade_voucher_code or '',
            'tax': 0.0,
            'total': self.currency_id.round(max(subtotal + service_fee + payment_fee + shipping_cost - voucher_discount, 0.0)),
            'item_quantity': sum(product_lines.mapped('product_uom_qty')),
        }

    def _unitrade_sync_fee_line(self, product, fee_lines, amount, fallback_name):
        self.ensure_one()
        if not product:
            return
        if amount:
            values = {
                'order_id': self.id,
                'product_id': product.id,
                'product_uom_qty': 1.0,
                'price_unit': amount,
                'name': product.display_name or fallback_name,
                'tax_id': [(6, 0, [])],
            }
            if fee_lines:
                fee_lines[0].sudo().write({
                    'product_uom_qty': 1.0,
                    'price_unit': amount,
                    'tax_id': [(6, 0, [])],
                })
                stale_lines = fee_lines - fee_lines[0]
                if stale_lines:
                    stale_lines.sudo().unlink()
            else:
                self.env['sale.order.line'].sudo().create(values)
        elif fee_lines:
            fee_lines.sudo().unlink()

    def _unitrade_prepare_checkout_server_state(self, payment_method=None):
        self.ensure_one()
        if self.state != 'draft':
            return self._unitrade_checkout_amounts(sync_fee=False, payment_method=payment_method)

        if hasattr(self, '_unitrade_sync_checkout_product_prices'):
            self._unitrade_sync_checkout_product_prices()
        product_lines = self._unitrade_product_lines_for_checkout()
        if not product_lines:
            raise ValidationError(_('Keranjang masih kosong.'))

        unavailable_lines = product_lines.filtered(lambda line: not line.product_id.sudo().sale_ok)
        if unavailable_lines:
            raise ValidationError(
                _('Produk berikut sudah tidak tersedia untuk dibeli: %s')
                % ', '.join(unavailable_lines.mapped('product_id.display_name'))
            )

        if hasattr(self, '_unitrade_get_cart_stock_issues'):
            stock_issues = self._unitrade_get_cart_stock_issues()
            if stock_issues:
                raise ValidationError(' '.join(issue['message'] for issue in stock_issues))

        if hasattr(self, '_unitrade_sync_shipping_state'):
            self._unitrade_sync_shipping_state()
        amounts = self._unitrade_checkout_amounts(sync_fee=True, payment_method=payment_method)
        if float_compare(amounts.get('item_subtotal', 0.0), 0.0, precision_rounding=self.currency_id.rounding) <= 0:
            raise ValidationError(_('Total produk di keranjang tidak valid.'))
        return amounts

    def _unitrade_primary_seller(self):
        self.ensure_one()
        for line in self._unitrade_product_lines_for_checkout():
            product_tmpl = line.product_id.product_tmpl_id
            seller = product_tmpl.x_seller_id if hasattr(product_tmpl, 'x_seller_id') else False
            if seller:
                return seller
        return False

    def _unitrade_checkout_cart_fingerprint(self, amounts):
        self.ensure_one()
        line_payload = []
        for line in self._unitrade_product_lines_for_checkout().sorted(lambda item: item.id):
            line_payload.append({
                'product_id': line.product_id.id,
                'qty': round(line.product_uom_qty or 0.0, 6),
                'uom_id': line.product_uom.id,
                'price_unit': round(line.price_unit or 0.0, 2),
                'subtotal': round(line.price_subtotal or 0.0, 2),
            })
        payload = {
            'currency_id': self.currency_id.id,
            'service_fee': int(round(amounts.get('service_fee', 0.0))),
            'payment_fee': int(round(amounts.get('payment_fee', 0.0))),
            'shipping_method': amounts.get('shipping_method') or 'pickup',
            'shipping_cost': int(round(amounts.get('shipping_cost', 0.0))),
            'voucher_code': amounts.get('voucher_code') or '',
            'voucher_discount': int(round(amounts.get('voucher_discount', 0.0))),
            'total': int(round(amounts.get('total', self.amount_total))),
            'lines': line_payload,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
        ).hexdigest()

    def _unitrade_lock_payment_order_row(self):
        self.ensure_one()
        self.env.cr.execute('SELECT id FROM sale_order WHERE id = %s FOR UPDATE', [self.id])

    def _midtrans_payment_method(self, payment_method):
        method_key = payment_method if payment_method in MIDTRANS_PAYMENT_METHODS else 'bca_va'
        method = dict(MIDTRANS_PAYMENT_METHODS[method_key])
        config = self.env['ir.config_parameter'].sudo()
        if not midtrans_method_enabled(config, method_key, method):
            raise UserError(_('Metode pembayaran %s belum aktif di konfigurasi Midtrans.') % method['label'])
        if method['type'] == 'CARD':
            raise UserError(_('Kartu belum diaktifkan karena harus memakai tokenisasi client-side agar tetap aman.'))
        return method_key, method

    def _midtrans_order_id(self):
        self.ensure_one()
        return ('UTM%s%s' % (self.id, uuid.uuid4().hex[:14])).upper()[:50]

    def _midtrans_expiry_at(self):
        return fields.Datetime.now() + timedelta(minutes=self._midtrans_payment_expiry_minutes())

    def _midtrans_order_time(self):
        jakarta_tz = timezone(timedelta(hours=7))
        return datetime.now(jakarta_tz).strftime('%Y-%m-%d %H:%M:%S +0700')

    def _midtrans_currency_code(self):
        self.ensure_one()
        return (self.currency_id.name or 'IDR').upper()

    def _midtrans_customer_payload(self):
        self.ensure_one()
        partner = self.partner_id
        phone = (partner.mobile or partner.phone or '').replace('+', '').replace(' ', '').replace('-', '')
        payload = {
            'first_name': (partner.name or 'UniTrade Buyer')[:255],
        }
        if partner.email:
            payload['email'] = partner.email
        if phone:
            payload['phone'] = phone
        return payload

    def _midtrans_items_payload(self, amounts):
        self.ensure_one()
        items = []
        for line in self._unitrade_product_lines_for_checkout():
            qty = int(line.product_uom_qty or 1)
            name = (line.product_id.display_name or line.name or 'Produk UniTrade')[:45]
            if qty > 1:
                name = ('%s x%s' % (name, qty))[:50]
            items.append({
                'id': str(line.product_id.id)[:50],
                'price': int(round(line.price_subtotal)),
                'quantity': 1,
                'name': name,
            })
        if amounts.get('service_fee'):
            items.append({
                'id': 'unitrade-service-fee',
                'price': int(round(amounts['service_fee'])),
                'quantity': 1,
                'name': 'Biaya Layanan UniTrade',
            })
        if amounts.get('payment_fee'):
            items.append({
                'id': 'unitrade-payment-fee',
                'price': int(round(amounts['payment_fee'])),
                'quantity': 1,
                'name': 'Biaya Payment',
            })
        if amounts.get('shipping_cost'):
            shipping_labels = {'pickup': 'Ambil Sendiri / COD', 'gosend': 'GoSend Instant'}
            shipping_label = shipping_labels.get(amounts.get('shipping_method') or 'pickup', 'Pengiriman')
            items.append({
                'id': 'unitrade-shipping-fee',
                'price': int(round(amounts['shipping_cost'])),
                'quantity': 1,
                'name': ('Ongkir %s' % shipping_label)[:50],
            })
        if amounts.get('voucher_discount'):
            items.append({
                'id': 'unitrade-voucher',
                'price': -int(round(amounts['voucher_discount'])),
                'quantity': 1,
                'name': ('Voucher %s' % (amounts.get('voucher_code') or '')).strip()[:50],
            })
        return items

    def _midtrans_charge_payload(self, method, amounts, total_amount, order_id, finish_url):
        payload = {
            'payment_type': method['payment_type'],
            'transaction_details': {
                'order_id': order_id,
                'gross_amount': total_amount,
            },
            'customer_details': self._midtrans_customer_payload(),
            'item_details': self._midtrans_items_payload(amounts),
            'custom_expiry': {
                'order_time': self._midtrans_order_time(),
                'expiry_duration': self._midtrans_payment_expiry_minutes(),
                'unit': 'minute',
            },
        }
        if method['payment_type'] == 'bank_transfer':
            payload['bank_transfer'] = {'bank': method['bank']}
        elif method['payment_type'] == 'echannel':
            payload['echannel'] = {
                'bill_info1': 'Payment',
                'bill_info2': 'UniTrade',
            }
        elif method['payment_type'] == 'qris':
            payload['qris'] = {'acquirer': 'gopay'}
        elif method['payment_type'] == 'gopay':
            payload['gopay'] = {
                'enable_callback': True,
                'callback_url': finish_url,
            }
        elif method['payment_type'] == 'shopeepay':
            payload['shopeepay'] = {'callback_url': finish_url}
        elif method['payment_type'] == 'cstore':
            payload['cstore'] = {
                'store': method['store'],
                'message': 'UniTrade',
            }
        return payload

    def _midtrans_send_charge_request(self, server_key, payload):
        response = requests.post(
            self._midtrans_api_base_url().rstrip('/') + '/v2/charge',
            data=json.dumps(payload, separators=(',', ':'), ensure_ascii=False).encode('utf-8'),
            headers={
                'Accept': 'application/json',
                'Content-Type': 'application/json',
            },
            auth=(server_key, ''),
            timeout=30,
        )
        try:
            response_payload = response.json()
        except ValueError:
            response_payload = {'raw_response': response.text}
        return response.status_code, response_payload, response.text

    def _midtrans_error_message(self, response_payload, response_text=''):
        message = response_payload.get('status_message') or response_payload.get('message') or response_payload.get('error_messages') or response_text
        if isinstance(message, (list, tuple)):
            return '; '.join(str(item) for item in message if item)
        if isinstance(message, dict):
            return json.dumps(message, ensure_ascii=False)
        return str(message or _('Midtrans menolak request pembayaran.'))

    def _parse_midtrans_datetime(self, value):
        if not value:
            return False
        value = str(value).strip()
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S %z'):
            try:
                parsed = datetime.strptime(value, fmt)
                if parsed.tzinfo:
                    parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
                else:
                    jakarta_tz = timezone(timedelta(hours=7))
                    parsed = parsed.replace(tzinfo=jakarta_tz).astimezone(timezone.utc).replace(tzinfo=None)
                return parsed
            except ValueError:
                continue
        return False

    def _midtrans_response_actions(self, response_payload):
        actions = response_payload.get('actions') or []
        if isinstance(actions, dict):
            actions = [actions]
        return actions

    def _midtrans_extract_payment_details(self, response_payload):
        actions = self._midtrans_response_actions(response_payload)
        reference = False
        qr_image_url = False
        payment_url = False
        deeplink_url = False
        biller_code = response_payload.get('biller_code')
        bill_key = response_payload.get('bill_key')
        payment_code = response_payload.get('payment_code')

        va_numbers = response_payload.get('va_numbers') or []
        if va_numbers and isinstance(va_numbers, list):
            reference = va_numbers[0].get('va_number')
        reference = (
            reference
            or response_payload.get('permata_va_number')
            or payment_code
            or response_payload.get('order_id')
        )
        if biller_code and bill_key:
            reference = '%s / %s' % (biller_code, bill_key)

        for action in actions:
            name = str(action.get('name') or action.get('type') or '').lower()
            url = action.get('url')
            if name == 'generate-qr-code' and url:
                qr_image_url = url
            elif name in ('deeplink-redirect', 'mobile-deeplink-redirect') and url:
                deeplink_url = url
            elif name in ('redirect', 'web-redirect', 'checkout-redirect') and url:
                payment_url = url

        return {
            'transaction_id': response_payload.get('transaction_id'),
            'payment_type': response_payload.get('payment_type'),
            'payment_reference': reference,
            'qr_string': qr_image_url or response_payload.get('qr_string'),
            'payment_url': payment_url,
            'deeplink_url': deeplink_url,
            'expires_at': self._parse_midtrans_datetime(response_payload.get('expiry_time')),
            'actions': actions,
        }

    def _unitrade_cancel_stale_midtrans_intents(self, total_amount, method_key, cart_fingerprint):
        self.ensure_one()
        pending_intents = self.env['unitrade.payment.intent'].sudo().search([
            ('sale_order_id', '=', self.id),
            ('provider', '=', 'midtrans'),
            ('state', '=', 'pending'),
        ])
        if not pending_intents:
            return pending_intents

        now = fields.Datetime.now()
        expired_intents = pending_intents.filtered(lambda intent: intent.expires_at and intent.expires_at <= now)
        if expired_intents:
            expired_intents.write({
                'state': 'expired',
                'error_message': _('Expired before a new checkout attempt.'),
            })

        active_candidates = pending_intents - expired_intents
        stale_intents = active_candidates.filtered(
            lambda intent: (
                int(round(intent.amount or 0.0)) != int(total_amount)
                or (intent.payment_method_code or '') != (method_key or '')
                or (intent.cart_fingerprint or '') != (cart_fingerprint or '')
                or not intent.midtrans_order_id
            )
        )
        if stale_intents:
            stale_intents.write({
                'state': 'cancelled',
                'error_message': _('Superseded because the cart content, amount, or payment method changed.'),
            })

        inactive_intents = expired_intents | stale_intents
        if self.x_payment_intent_id and self.x_payment_intent_id in inactive_intents:
            self.sudo().write({
                'x_payment_intent_id': False,
                'x_midtrans_order_id': False,
                'x_midtrans_transaction_id': False,
                'x_midtrans_payment_type': False,
            })
        return pending_intents - inactive_intents

    def action_create_midtrans_payment(self, payment_method=None):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Pesanan ini sudah tidak bisa dibayar dari checkout.'))

        self._unitrade_lock_payment_order_row()

        server_key = self._get_midtrans_param('unitrade.midtrans.server_key')
        if not server_key:
            raise UserError(_('Konfigurasi Midtrans belum lengkap. Isi Server Key di System Parameters.'))

        method_key, method = self._midtrans_payment_method(payment_method)
        amounts = self._unitrade_prepare_checkout_server_state(method_key)
        total_amount = int(round(amounts.get('total', self.amount_total)))
        if total_amount <= 0:
            raise UserError(_('Total pembayaran tidak valid.'))

        cart_fingerprint = self._unitrade_checkout_cart_fingerprint(amounts)
        self._unitrade_cancel_stale_midtrans_intents(total_amount, method_key, cart_fingerprint)
        existing_intent = self.env['unitrade.payment.intent'].sudo().search([
            ('sale_order_id', '=', self.id),
            ('provider', '=', 'midtrans'),
            ('state', '=', 'pending'),
            ('amount', '=', total_amount),
            ('payment_method_code', '=', method_key),
            ('cart_fingerprint', '=', cart_fingerprint),
            ('midtrans_order_id', '!=', False),
            '|',
            ('expires_at', '=', False),
            ('expires_at', '>', fields.Datetime.now()),
        ], order='create_date desc', limit=1)
        if existing_intent:
            self._write_midtrans_order_state(existing_intent, method)
            existing_intent.action_send_payment_invoice_email()
            return {
                'payment_url': self.get_base_url().rstrip('/') + '/unitrade/payment/instructions/%s' % existing_intent.midtrans_order_id,
                'payment_intent': existing_intent,
            }

        order_id = self._midtrans_order_id()
        expires_at = self._midtrans_expiry_at()
        finish_url = self.get_base_url().rstrip('/') + '/unitrade/payment/finish?reference_id=%s' % order_id
        payload = self._midtrans_charge_payload(method, amounts, total_amount, order_id, finish_url)
        intent = self.env['unitrade.payment.intent'].sudo().create({
            'name': order_id,
            'provider': 'midtrans',
            'intent_type': 'order_checkout',
            'state': 'draft',
            'amount': total_amount,
            'amount_gateway_fee': amounts.get('payment_fee', 0.0),
            'currency_id': self.currency_id.id,
            'sale_order_id': self.id,
            'partner_id': self.partner_id.id,
            'seller_id': self._unitrade_primary_seller().id if self._unitrade_primary_seller() else False,
            'payment_method_code': method_key,
            'payment_method_label': method['label'],
            'cart_fingerprint': cart_fingerprint,
            'midtrans_order_id': order_id,
            'midtrans_payment_type': method['payment_type'],
            'midtrans_bank': method.get('bank') or method.get('store') or '',
            'expires_at': expires_at,
        })
        intent._set_raw_request(payload)

        try:
            status_code, response_payload, response_text = self._midtrans_send_charge_request(server_key, payload)
            intent._set_raw_response(response_payload)
            if status_code >= 400:
                message = self._midtrans_error_message(response_payload, response_text)
                intent.write({'state': 'failed', 'error_message': str(message)})
                raise UserError(_('Midtrans menolak request pembayaran: %s') % message)

            payment_details = self._midtrans_extract_payment_details(response_payload)
            response_expires_at = payment_details.get('expires_at')
            intent_expires_at = min(
                [date for date in (response_expires_at, expires_at) if date],
                default=expires_at,
            )
            intent.write({
                'state': 'pending',
                'midtrans_transaction_id': payment_details.get('transaction_id'),
                'midtrans_payment_type': payment_details.get('payment_type') or method['payment_type'],
                'payment_reference': payment_details.get('payment_reference'),
                'qr_string': payment_details.get('qr_string'),
                'payment_url': payment_details.get('payment_url'),
                'deeplink_url': payment_details.get('deeplink_url'),
                'expires_at': intent_expires_at,
                'midtrans_actions': json.dumps(payment_details.get('actions') or [], ensure_ascii=False, indent=2),
            })
            self._write_midtrans_order_state(intent, method)
            intent.action_send_payment_invoice_email()
            _logger.info('Midtrans Core payment created for order %s reference %s', self.name, order_id)
            return {
                'payment_url': self.get_base_url().rstrip('/') + '/unitrade/payment/instructions/%s' % order_id,
                'payment_intent': intent,
            }
        except UserError:
            raise
        except requests.RequestException as error:
            intent.write({'state': 'failed', 'error_message': str(error)})
            _logger.exception('Midtrans payment request failed for order %s', self.name)
            raise UserError(_('Gagal menghubungi Midtrans. Coba lagi beberapa saat lagi.')) from error

    def _write_midtrans_order_state(self, intent, method):
        self.ensure_one()
        values = {
            'x_payment_provider': 'midtrans',
            'x_payment_status': 'pending',
            'x_unitrade_order_state': 'payment_pending',
            'x_payment_method': intent.payment_method_label or method.get('label'),
            'x_payment_intent_id': intent.id,
            'x_midtrans_order_id': intent.midtrans_order_id,
            'x_midtrans_transaction_id': intent.midtrans_transaction_id,
            'x_midtrans_payment_type': intent.midtrans_payment_type,
            'x_escrow_state': 'none',
        }
        cancel_deadline = self._unitrade_new_cancel_deadline()
        if intent.expires_at:
            cancel_deadline = min(cancel_deadline, intent.expires_at)
        values['x_cancel_deadline_at'] = cancel_deadline
        self.sudo().write(values)

    def _unitrade_mark_midtrans_paid(self, intent, payload):
        self.ensure_one()
        paid_at = fields.Datetime.now()
        values = {
            'x_payment_provider': 'midtrans',
            'x_payment_status': 'paid',
            'x_unitrade_order_state': 'processing',
            'x_escrow_state': 'held',
            'x_payment_method': intent.payment_method_label or self.x_payment_method,
            'x_payment_intent_id': intent.id,
            'x_midtrans_order_id': intent.midtrans_order_id,
            'x_midtrans_transaction_id': intent.midtrans_transaction_id or payload.get('transaction_id'),
            'x_midtrans_payment_type': intent.midtrans_payment_type or payload.get('payment_type'),
            'x_paid_at': paid_at,
        }
        if not self.x_cancel_deadline_at:
            values['x_cancel_deadline_at'] = paid_at + timedelta(minutes=self._unitrade_cancel_window_minutes())
        self.sudo().write(values)
        if intent.state != 'paid':
            intent.sudo().write({
                'state': 'paid',
                'paid_at': paid_at,
                'midtrans_transaction_id': payload.get('transaction_id') or intent.midtrans_transaction_id,
                'midtrans_payment_type': payload.get('payment_type') or intent.midtrans_payment_type,
                'raw_response': json.dumps(payload, ensure_ascii=False, indent=2),
            })
        if self.state == 'draft':
            self.sudo().action_confirm()
        ledgers = self.env['unitrade.escrow.ledger'].sudo()._create_for_order(self.sudo(), intent.sudo())
        if ledgers:
            self.sudo().write({'x_escrow_state': 'held'})
        self._unitrade_create_shipping_delivery()
        intent.action_send_payment_success_email()
        return ledgers

    def _unitrade_create_shipping_delivery(self):
        """Buat delivery record untuk order GoSend yang sudah dibayar (idempotent)."""
        self.ensure_one()
        if 'x_shipping_method' not in self._fields or self.x_shipping_method != 'gosend':
            return
        if 'unitrade.delivery' not in self.env.registry:
            return
        Delivery = self.env['unitrade.delivery'].sudo()
        if not hasattr(Delivery, '_unitrade_create_for_order'):
            return
        try:
            Delivery._unitrade_create_for_order(self.sudo())
        except Exception:
            _logger.exception('Failed to create UniTrade delivery record for order %s', self.name)
        method_key = payment_method if payment_method in XENDIT_PAYMENT_METHODS else 'bca_va'
        method = dict(XENDIT_PAYMENT_METHODS[method_key])
        config = self.env['ir.config_parameter'].sudo()
        if not xendit_method_enabled(config, method_key, method):
            raise UserError(_('Metode pembayaran %s belum aktif di konfigurasi Xendit.') % method['label'])
        if method['type'] == 'CARD':
            raise UserError(_('Kartu belum diaktifkan karena harus memakai Xendit component/PCI-safe flow.'))
        return method_key, method

    def _xendit_reference_id(self):
        self.ensure_one()
        return ('UTX%s%s' % (self.id, uuid.uuid4().hex[:16])).upper()[:36]

    def _xendit_expiry_at(self):
        return fields.Datetime.now() + timedelta(minutes=self._xendit_payment_expiry_minutes())

    def _xendit_datetime_to_iso(self, value):
        if not value:
            return False
        return value.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z')

    def _parse_xendit_datetime(self, value):
        if not value:
            return False
        try:
            parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        except ValueError:
            return False
        if parsed.tzinfo:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed

    def _xendit_customer_payload(self):
        self.ensure_one()
        partner = self.partner_id
        phone = (partner.mobile or partner.phone or '').replace('+', '').replace(' ', '').replace('-', '')
        payload = {
            'reference_id': 'partner-%s' % partner.id,
            'type': 'INDIVIDUAL',
            'individual_detail': {
                'given_names': partner.name or 'UniTrade Buyer',
            },
        }
        if partner.email:
            payload['email'] = partner.email
        if phone:
            payload['mobile_number'] = phone if phone.startswith('0') else phone
        return payload

    def _xendit_currency_code(self):
        self.ensure_one()
        return (self.currency_id.name or 'IDR').upper()

    def _xendit_items_payload(self, amounts):
        self.ensure_one()
        currency = self._xendit_currency_code()
        items = []
        for line in self._unitrade_product_lines_for_checkout():
            items.append({
                'type': 'PHYSICAL_PRODUCT',
                'name': (line.product_id.display_name or line.name or 'Produk UniTrade')[:255],
                'quantity': int(line.product_uom_qty or 1),
                'reference_id': str(line.product_id.id),
                'net_unit_amount': int(round(line.price_unit)),
                'currency': currency,
                'category': 'Marketplace',
                'url': self.get_base_url().rstrip('/'),
            })
        if amounts.get('service_fee'):
            items.append({
                'type': 'FEE',
                'name': 'Biaya Layanan UniTrade',
                'quantity': 1,
                'reference_id': 'unitrade-service-fee',
                'net_unit_amount': int(round(amounts['service_fee'])),
                'currency': currency,
                'category': 'Fee',
            })
        if amounts.get('payment_fee'):
            items.append({
                'type': 'FEE',
                'name': 'Biaya Payment',
                'quantity': 1,
                'reference_id': 'unitrade-payment-fee',
                'net_unit_amount': int(round(amounts['payment_fee'])),
                'currency': currency,
                'category': 'Fee',
            })
        if amounts.get('voucher_discount'):
            items.append({
                'type': 'DISCOUNT',
                'name': ('Voucher %s' % (amounts.get('voucher_code') or '')).strip()[:255],
                'quantity': 1,
                'reference_id': 'unitrade-voucher',
                'net_unit_amount': -int(round(amounts['voucher_discount'])),
                'currency': currency,
                'category': 'Discount',
            })
        return items

    def _xendit_channel_properties(self, method, finish_url, expires_at):
        channel_properties = {}
        if method['type'] == 'VIRTUAL_ACCOUNT':
            channel_properties.update({
                'customer_name': (self.partner_id.name or 'UniTrade Buyer')[:255],
                'display_name': (self.partner_id.name or 'UniTrade Buyer')[:255],
                'expires_at': self._xendit_datetime_to_iso(expires_at),
            })
        elif method['type'] == 'EWALLET':
            channel_properties.update({
                'success_return_url': finish_url,
                'failure_return_url': finish_url,
            })
            phone = (self.partner_id.mobile or self.partner_id.phone or '').replace('+', '').replace(' ', '').replace('-', '')
            if phone and method['channel_code'] == 'OVO':
                channel_properties['mobile_number'] = phone

        return channel_properties

    def _xendit_payment_request_payload(self, method, amounts, total_amount, reference_id, finish_url, expires_at):
        return {
            'reference_id': reference_id,
            'type': 'PAY',
            'country': 'ID',
            'currency': self._xendit_currency_code(),
            'request_amount': total_amount,
            'capture_method': 'AUTOMATIC',
            'channel_code': method['channel_code'],
            'channel_properties': self._xendit_channel_properties(method, finish_url, expires_at),
            'items': self._xendit_items_payload(amounts),
            'description': _('Pembayaran UniTrade %s') % (self.name or reference_id),
            'metadata': {
                'sale_order_id': self.id,
                'sale_order_name': self.name,
                'buyer_id': self.partner_id.id,
                'provider': 'unitrade',
                'item_subtotal': int(round(amounts.get('item_subtotal', 0.0))),
                'service_fee': int(round(amounts.get('service_fee', 0.0))),
                'payment_fee': int(round(amounts.get('payment_fee', 0.0))),
            },
        }

    def _xendit_send_payment_request(self, secret_key, payload, idempotency_key):
        response = requests.post(
            self._xendit_api_base_url().rstrip('/') + '/v3/payment_requests',
            data=json.dumps(payload, separators=(',', ':'), ensure_ascii=False).encode('utf-8'),
            headers={
                'Content-Type': 'application/json',
                'api-version': '2024-11-11',
                'Idempotency-key': idempotency_key,
            },
            auth=(secret_key, ''),
            timeout=30,
        )
        try:
            response_payload = response.json()
        except ValueError:
            response_payload = {'raw_response': response.text}
        return response.status_code, response_payload, response.text

    def _xendit_error_message(self, response_payload, response_text=''):
        message = response_payload.get('message') or response_payload.get('error') or response_payload.get('error_code') or response_text
        errors = response_payload.get('errors') or response_payload.get('details')
        if errors:
            if isinstance(errors, (list, tuple)):
                detail = '; '.join(
                    json.dumps(item, ensure_ascii=False) if isinstance(item, dict) else str(item)
                    for item in errors
                    if item
                )
            elif isinstance(errors, dict):
                detail = json.dumps(errors, ensure_ascii=False)
            else:
                detail = str(errors)
            if detail:
                message = '%s: %s' % (message or _('Validasi Xendit gagal'), detail)
        if isinstance(message, (list, tuple)):
            return '; '.join(str(item) for item in message if item)
        if isinstance(message, dict):
            return json.dumps(message, ensure_ascii=False)
        return str(message or _('Xendit menolak request pembayaran.'))

    def _xendit_response_actions(self, response_payload):
        payment_method = response_payload.get('payment_method') or {}
        latest_payment = response_payload.get('latest_payment') or {}
        actions = (
            response_payload.get('actions')
            or latest_payment.get('actions')
            or payment_method.get('actions')
            or []
        )
        if isinstance(actions, dict):
            actions = [actions]
        return actions

    def _xendit_extract_payment_details(self, response_payload):
        payment_method = response_payload.get('payment_method') or {}
        latest_payment = response_payload.get('latest_payment') or {}
        actions = self._xendit_response_actions(response_payload)
        reference = (
            response_payload.get('payment_reference')
            or response_payload.get('payment_code')
            or payment_method.get('virtual_account_number')
            or payment_method.get('account_number')
            or payment_method.get('payment_code')
            or latest_payment.get('payment_code')
            or response_payload.get('reference_id')
        )
        qr_string = response_payload.get('qr_string') or payment_method.get('qr_string') or latest_payment.get('qr_string')
        payment_url = response_payload.get('payment_url') or response_payload.get('checkout_url')
        deeplink_url = response_payload.get('deeplink_url')

        for action in actions:
            action_type = str(action.get('descriptor') or action.get('type') or action.get('action') or action.get('name') or '').upper()
            value = action.get('value') or action.get('url') or action.get('qr_string') or action.get('descriptor')
            if action_type in ('QR_STRING', 'QR_CODE', 'QR_CODE_STRING', 'GENERATE_QR_CODE') and value:
                qr_string = value
            elif action_type in ('VIRTUAL_ACCOUNT_NUMBER', 'PAYMENT_CODE', 'ACCOUNT_NUMBER', 'RETAIL_OUTLET_CODE') and value:
                reference = value
            elif action_type in ('WEB_URL', 'CHECKOUT_URL', 'AUTHORIZATION_URL', 'REDIRECT_URL') and value:
                payment_url = value
            elif action_type in ('DEEPLINK_URL', 'MOBILE_DEEPLINK_URL') and value:
                deeplink_url = value

        return {
            'payment_request_id': response_payload.get('id') or response_payload.get('payment_request_id'),
            'latest_payment_id': latest_payment.get('id') or response_payload.get('latest_payment_id'),
            'payment_reference': reference,
            'qr_string': qr_string,
            'payment_url': payment_url,
            'deeplink_url': deeplink_url,
            'expires_at': self._parse_xendit_datetime(
                response_payload.get('expires_at')
                or payment_method.get('expires_at')
                or latest_payment.get('expires_at')
            ),
            'actions': actions,
        }

    def _unitrade_cancel_stale_xendit_intents(self, total_amount, method_key, cart_fingerprint):
        self.ensure_one()
        pending_intents = self.env['unitrade.payment.intent'].sudo().search([
            ('sale_order_id', '=', self.id),
            ('provider', '=', 'xendit'),
            ('state', '=', 'pending'),
        ])
        if not pending_intents:
            return pending_intents

        now = fields.Datetime.now()
        expired_intents = pending_intents.filtered(lambda intent: intent.expires_at and intent.expires_at <= now)
        if expired_intents:
            expired_intents.write({
                'state': 'expired',
                'error_message': _('Expired before a new checkout attempt.'),
            })

        active_candidates = pending_intents - expired_intents
        stale_intents = active_candidates.filtered(
            lambda intent: (
                int(round(intent.amount or 0.0)) != int(total_amount)
                or (intent.payment_method_code or '') != (method_key or '')
                or (intent.cart_fingerprint or '') != (cart_fingerprint or '')
                or not intent.xendit_payment_request_id
            )
        )
        if stale_intents:
            stale_intents.write({
                'state': 'cancelled',
                'error_message': _('Superseded because the cart content, amount, or payment method changed.'),
            })

        inactive_intents = expired_intents | stale_intents
        if self.x_payment_intent_id and self.x_payment_intent_id in inactive_intents:
            self.sudo().write({
                'x_payment_intent_id': False,
                'x_xendit_reference_id': False,
                'x_xendit_payment_request_id': False,
                'x_xendit_payment_url': False,
                'x_xendit_channel_code': False,
            })
        return pending_intents - inactive_intents

    def action_create_xendit_payment(self, payment_method=None):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Pesanan ini sudah tidak bisa dibayar dari checkout.'))

        self._unitrade_lock_payment_order_row()

        secret_key = self._get_xendit_param('unitrade.xendit.secret_key')
        if not secret_key:
            raise UserError(_('Konfigurasi Xendit belum lengkap. Isi Secret Key di System Parameters.'))

        method_key, method = self._xendit_payment_method(payment_method)
        amounts = self._unitrade_prepare_checkout_server_state(method_key)
        total_amount = int(round(amounts.get('total', self.amount_total)))
        if total_amount <= 0:
            raise UserError(_('Total pembayaran tidak valid.'))

        cart_fingerprint = self._unitrade_checkout_cart_fingerprint(amounts)
        self._unitrade_cancel_stale_xendit_intents(total_amount, method_key, cart_fingerprint)
        existing_intent = self.env['unitrade.payment.intent'].sudo().search([
            ('sale_order_id', '=', self.id),
            ('provider', '=', 'xendit'),
            ('state', '=', 'pending'),
            ('amount', '=', total_amount),
            ('payment_method_code', '=', method_key),
            ('cart_fingerprint', '=', cart_fingerprint),
            ('xendit_payment_request_id', '!=', False),
            '|',
            ('expires_at', '=', False),
            ('expires_at', '>', fields.Datetime.now()),
        ], order='create_date desc', limit=1)
        if existing_intent:
            self._write_xendit_order_state(existing_intent, method)
            existing_intent.action_send_payment_invoice_email()
            return {
                'payment_url': existing_intent.payment_url or existing_intent.deeplink_url or (
                    self.get_base_url().rstrip('/') + '/unitrade/payment/instructions/%s' % existing_intent.xendit_reference_id
                ),
                'payment_intent': existing_intent,
            }

        reference_id = self._xendit_reference_id()
        expires_at = self._xendit_expiry_at()
        finish_url = self.get_base_url().rstrip('/') + '/unitrade/payment/instructions/%s' % reference_id
        payload = self._xendit_payment_request_payload(method, amounts, total_amount, reference_id, finish_url, expires_at)
        intent = self.env['unitrade.payment.intent'].sudo().create({
            'name': reference_id,
            'provider': 'xendit',
            'intent_type': 'order_checkout',
            'state': 'draft',
            'amount': total_amount,
            'amount_gateway_fee': amounts.get('payment_fee', 0.0),
            'currency_id': self.currency_id.id,
            'sale_order_id': self.id,
            'partner_id': self.partner_id.id,
            'seller_id': self._unitrade_primary_seller().id if self._unitrade_primary_seller() else False,
            'payment_method_code': method_key,
            'payment_method_label': method['label'],
            'cart_fingerprint': cart_fingerprint,
            'xendit_reference_id': reference_id,
            'xendit_channel_code': method['channel_code'],
            'expires_at': expires_at,
        })
        intent._set_raw_request(payload)

        try:
            status_code, response_payload, response_text = self._xendit_send_payment_request(
                secret_key,
                payload,
                'unitrade-payment-%s' % reference_id,
            )
            intent._set_raw_response(response_payload)
            if status_code >= 400:
                message = self._xendit_error_message(response_payload, response_text)
                intent.write({'state': 'failed', 'error_message': str(message)})
                raise UserError(_('Xendit menolak request pembayaran: %s') % message)

            payment_details = self._xendit_extract_payment_details(response_payload)
            intent.write({
                'state': 'pending',
                'xendit_payment_request_id': payment_details.get('payment_request_id'),
                'xendit_latest_payment_id': payment_details.get('latest_payment_id'),
                'payment_reference': payment_details.get('payment_reference'),
                'qr_string': payment_details.get('qr_string'),
                'payment_url': payment_details.get('payment_url'),
                'deeplink_url': payment_details.get('deeplink_url'),
                'expires_at': payment_details.get('expires_at') or expires_at,
                'xendit_actions': json.dumps(payment_details.get('actions') or [], ensure_ascii=False, indent=2),
            })
            self._write_xendit_order_state(intent, method)
            intent.action_send_payment_invoice_email()
            _logger.info('Xendit payment request created for order %s reference %s', self.name, reference_id)
            return {
                'payment_url': intent.payment_url or intent.deeplink_url or finish_url,
                'payment_intent': intent,
            }
        except UserError:
            raise
        except requests.RequestException as error:
            intent.write({'state': 'failed', 'error_message': str(error)})
            _logger.exception('Xendit payment request failed for order %s', self.name)
            raise UserError(_('Gagal menghubungi Xendit. Coba lagi beberapa saat lagi.')) from error

    def _write_xendit_order_state(self, intent, method):
        self.ensure_one()
        values = {
            'x_payment_provider': 'xendit',
            'x_payment_status': 'pending',
            'x_unitrade_order_state': 'payment_pending',
            'x_payment_method': intent.payment_method_label or method.get('label'),
            'x_payment_intent_id': intent.id,
            'x_xendit_reference_id': intent.xendit_reference_id,
            'x_xendit_payment_request_id': intent.xendit_payment_request_id,
            'x_xendit_payment_url': intent.payment_url or intent.deeplink_url,
            'x_xendit_channel_code': intent.xendit_channel_code,
            'x_escrow_state': 'none',
        }
        cancel_deadline = self._unitrade_new_cancel_deadline()
        if intent.expires_at:
            cancel_deadline = min(cancel_deadline, intent.expires_at)
        values['x_cancel_deadline_at'] = cancel_deadline
        self.sudo().write(values)

    def _unitrade_mark_xendit_paid(self, intent, payload):
        self.ensure_one()
        paid_at = fields.Datetime.now()
        values = {
            'x_payment_provider': 'xendit',
            'x_payment_status': 'paid',
            'x_unitrade_order_state': 'processing',
            'x_escrow_state': 'held',
            'x_payment_method': intent.payment_method_label or self.x_payment_method,
            'x_payment_intent_id': intent.id,
            'x_xendit_reference_id': intent.xendit_reference_id,
            'x_xendit_payment_request_id': intent.xendit_payment_request_id,
            'x_xendit_payment_url': intent.payment_url or intent.deeplink_url,
            'x_xendit_channel_code': intent.xendit_channel_code,
            'x_paid_at': paid_at,
        }
        if not self.x_cancel_deadline_at:
            values['x_cancel_deadline_at'] = paid_at + timedelta(minutes=self._unitrade_cancel_window_minutes())
        self.sudo().write(values)
        if intent.state != 'paid':
            intent.sudo().write({
                'state': 'paid',
                'paid_at': paid_at,
                'raw_response': json.dumps(payload, ensure_ascii=False, indent=2),
            })
        if self.state == 'draft':
            self.sudo().action_confirm()
        ledgers = self.env['unitrade.escrow.ledger'].sudo()._create_for_order(self.sudo(), intent.sudo())
        if ledgers:
            self.sudo().write({'x_escrow_state': 'held'})
        self._unitrade_create_shipping_delivery()
        intent.action_send_payment_success_email()
        return ledgers

    def action_unitrade_cleanup_draft_fee_lines(self):
        orders = self.sudo().filtered(lambda order: order.state == 'draft')
        if not orders:
            orders = self.env['sale.order'].sudo().search([('state', '=', 'draft')])

        product_ids = []
        service_fee_product = self.env.ref('unitrade_theme.product_unitrade_service_fee', raise_if_not_found=False)
        payment_fee_product = self.env.ref('unitrade_payment.product_unitrade_payment_fee', raise_if_not_found=False)
        voucher_product = self.env.ref('unitrade_payment.product_unitrade_voucher_discount', raise_if_not_found=False)
        if service_fee_product:
            product_ids.append(service_fee_product.id)
        if payment_fee_product:
            product_ids.append(payment_fee_product.id)
        if voucher_product:
            product_ids.append(voucher_product.id)

        if not product_ids or not orders:
            removed_count = 0
        else:
            fee_lines = self.env['sale.order.line'].sudo().search([
                ('order_id', 'in', orders.ids),
                ('order_id.state', '=', 'draft'),
                ('product_id', 'in', product_ids),
            ])
            removed_count = len(fee_lines)
            fee_lines.unlink()
            orders.invalidate_recordset(['order_line', 'amount_untaxed', 'amount_tax', 'amount_total'])

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('UniTrade Cart Cleanup'),
                'message': _('Berhasil membersihkan %s fee line lama dari cart draft.') % removed_count,
                'type': 'success',
                'sticky': False,
            },
        }

    def action_create_doku_checkout(self, payment_method=None):
        raise UserError(_('DOKU sudah tidak menjadi flow aktif. Gunakan Midtrans checkout.'))

    def action_create_midtrans_transaction(self):
        """Create Midtrans Snap transaction for legacy compatibility."""
        self.ensure_one()
        server_key = self._get_midtrans_key('unitrade.midtrans.server_key')
        is_production = self._get_midtrans_key('unitrade.midtrans.is_production') == 'True'

        if not server_key:
            _logger.error('Midtrans server key not configured')
            return False

        try:
            import midtransclient
            snap = midtransclient.Snap(
                is_production=is_production,
                server_key=server_key,
            )
            transaction = snap.create_transaction({
                'transaction_details': {
                    'order_id': self.name,
                    'gross_amount': int(self.amount_total),
                },
                'customer_details': {
                    'first_name': self.partner_id.name,
                    'email': self.partner_id.email,
                    'phone': self.partner_id.phone or '',
                },
                'callbacks': {
                    'finish': '/unitrade/payment/finish',
                },
            })
            self.write({
                'x_midtrans_snap_token': transaction['token'],
                'x_midtrans_transaction_id': self.name,
            })
            _logger.info('Midtrans transaction created for order %s', self.name)
            return transaction
        except ImportError:
            _logger.warning('midtransclient not installed. pip install midtransclient')
            return False
        except Exception as error:
            _logger.error('Midtrans error for order %s: %s', self.name, str(error))
            return False
