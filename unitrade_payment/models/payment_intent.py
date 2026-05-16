import hashlib
import json
import logging

from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.addons.unitrade_payment.xendit_methods import XENDIT_PAYMENT_METHODS
from odoo.addons.unitrade_payment.midtrans_methods import MIDTRANS_PAYMENT_METHODS

_logger = logging.getLogger(__name__)


class UnitradePaymentIntent(models.Model):
    _name = 'unitrade.payment.intent'
    _description = 'UniTrade Payment Intent'
    _order = 'create_date desc'

    name = fields.Char(required=True, readonly=True, copy=False)
    provider = fields.Selection([
        ('xendit', 'Xendit'),
        ('doku', 'DOKU'),
        ('midtrans', 'Midtrans'),
    ], default='midtrans', required=True, readonly=True)
    intent_type = fields.Selection([
        ('order_checkout', 'Order Checkout'),
        ('listing_fee', 'Listing Fee'),
    ], default='order_checkout', required=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
    ], default='draft', required=True, index=True)
    amount = fields.Monetary(currency_field='currency_id', required=True)
    currency_id = fields.Many2one(
        'res.currency',
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    sale_order_id = fields.Many2one('sale.order', string='Sale Order', index=True, ondelete='set null')
    product_template_id = fields.Many2one('product.template', string='Product', ondelete='set null')
    partner_id = fields.Many2one('res.partner', string='Buyer', index=True, ondelete='set null')
    seller_id = fields.Many2one('unitrade.seller', string='Seller', index=True, ondelete='set null')
    payment_method_code = fields.Char()
    payment_method_label = fields.Char()
    cart_fingerprint = fields.Char(index=True, copy=False)
    payment_reference = fields.Char(copy=False)
    payment_url = fields.Char(copy=False)
    deeplink_url = fields.Char(copy=False)
    qr_string = fields.Text(copy=False)
    expires_at = fields.Datetime(copy=False)
    amount_gateway_fee = fields.Monetary(string='Gateway Fee', currency_field='currency_id', copy=False)
    xendit_reference_id = fields.Char(index=True, copy=False)
    xendit_payment_request_id = fields.Char(index=True, copy=False)
    xendit_latest_payment_id = fields.Char(index=True, copy=False)
    xendit_channel_code = fields.Char(index=True, copy=False)
    xendit_actions = fields.Text(copy=False)
    midtrans_order_id = fields.Char(index=True, copy=False)
    midtrans_transaction_id = fields.Char(index=True, copy=False)
    midtrans_payment_type = fields.Char(index=True, copy=False)
    midtrans_bank = fields.Char(index=True, copy=False)
    midtrans_actions = fields.Text(copy=False)
    doku_invoice_number = fields.Char(index=True, copy=False)
    doku_payment_url = fields.Char(copy=False)
    doku_token_id = fields.Char(copy=False)
    doku_request_id = fields.Char(copy=False)
    doku_expired_at = fields.Datetime(copy=False)
    raw_request = fields.Text(copy=False)
    raw_response = fields.Text(copy=False)
    error_message = fields.Text(copy=False)
    paid_at = fields.Datetime(copy=False)
    invoice_email_sent_at = fields.Datetime(copy=False)
    paid_email_sent_at = fields.Datetime(copy=False)

    _sql_constraints = [
        ('xendit_reference_unique', 'unique(xendit_reference_id)', 'Reference Xendit harus unik.'),
        ('midtrans_order_unique', 'unique(midtrans_order_id)', 'Order ID Midtrans harus unik.'),
        ('doku_invoice_unique', 'unique(doku_invoice_number)', 'Invoice DOKU harus unik.'),
    ]

    def _set_raw_request(self, payload):
        for intent in self:
            intent.raw_request = json.dumps(payload, ensure_ascii=False, indent=2)

    def _set_raw_response(self, payload):
        for intent in self:
            intent.raw_response = json.dumps(payload, ensure_ascii=False, indent=2)

    def _unitrade_reference_key(self):
        self.ensure_one()
        return self.midtrans_order_id or self.xendit_reference_id or self.name

    def _unitrade_public_payment_url(self):
        self.ensure_one()
        order = self.sale_order_id
        base_url = order.get_base_url() if order else self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        return '%s/unitrade/payment/instructions/%s' % (
            (base_url or '').rstrip('/'),
            self._unitrade_reference_key(),
        )

    def unitrade_public_payment_url(self):
        self.ensure_one()
        return self._unitrade_public_payment_url()

    def _unitrade_send_template_once(self, template_xmlid, sent_field):
        for intent in self.sudo():
            if intent[sent_field] or not intent.partner_id.email:
                continue
            template = self.env.ref(template_xmlid, raise_if_not_found=False)
            if not template:
                continue
            try:
                template.sudo().send_mail(intent.id, force_send=True, raise_exception=False)
                intent.write({sent_field: fields.Datetime.now()})
            except Exception:
                intent._logger_exception(template_xmlid)

    def _logger_exception(self, template_xmlid):
        self.ensure_one()
        _logger.exception(
            'Failed to send payment email template %s for intent %s',
            template_xmlid,
            self.name,
        )

    def action_send_payment_invoice_email(self):
        self._unitrade_send_template_once(
            'unitrade_payment.mail_template_payment_invoice',
            'invoice_email_sent_at',
        )

    def action_send_payment_success_email(self):
        self._unitrade_send_template_once(
            'unitrade_payment.mail_template_payment_success',
            'paid_email_sent_at',
        )

    def _sandbox_instruction_payload(self):
        self.ensure_one()
        method = (
            MIDTRANS_PAYMENT_METHODS.get(self.payment_method_code or '')
            if self.provider == 'midtrans'
            else XENDIT_PAYMENT_METHODS.get(self.payment_method_code or '')
        ) or {}
        channel_type = method.get('type')
        reference = self.payment_reference
        qr_string = self.qr_string
        payment_url = self.payment_url
        deeplink_url = self.deeplink_url
        actions = []

        if channel_type in ('VIRTUAL_ACCOUNT', 'BANK_TRANSFER', 'PERMATA'):
            reference = reference or ('8808%s' % str(self.id).zfill(12))[:16]
            actions.append({
                'type': 'VIRTUAL_ACCOUNT_NUMBER',
                'descriptor': 'VIRTUAL_ACCOUNT_NUMBER',
                'value': reference,
            })
        elif channel_type in ('QR_CODE', 'QRIS', 'GOPAY'):
            qr_string = qr_string or ('UNITRADE-MIDTRANS-SANDBOX-QRIS-%s' % (self.midtrans_order_id or self.xendit_reference_id or self.name))
            actions.append({
                'type': 'QR_STRING',
                'descriptor': 'QR_STRING',
                'value': qr_string,
            })
        elif channel_type in ('EWALLET', 'SHOPEEPAY', 'CSTORE'):
            payment_url = payment_url or '/unitrade/payment/instructions/%s?sandbox=1' % (self.midtrans_order_id or self.xendit_reference_id or self.name)
            actions.append({
                'type': 'WEB_URL',
                'descriptor': 'WEB_URL',
                'value': payment_url,
            })
        elif channel_type == 'ECHANNEL':
            reference = reference or '70012 / %s' % str(self.id).zfill(12)
        else:
            reference = reference or (self.midtrans_order_id or self.xendit_reference_id or self.name)

        return {
            'payment_reference': reference,
            'qr_string': qr_string,
            'payment_url': payment_url,
            'deeplink_url': deeplink_url,
            'actions': actions,
        }

    def action_seed_sandbox_payment_details(self):
        for intent in self.sudo():
            if intent.provider not in ('midtrans', 'xendit'):
                continue
            details = intent._sandbox_instruction_payload()
            write_values = {
                'payment_reference': details.get('payment_reference'),
                'qr_string': details.get('qr_string'),
                'payment_url': details.get('payment_url'),
                'deeplink_url': details.get('deeplink_url'),
            }
            if intent.provider == 'midtrans':
                write_values['midtrans_actions'] = json.dumps(details.get('actions') or [], ensure_ascii=False, indent=2)
            else:
                write_values['xendit_actions'] = json.dumps(details.get('actions') or [], ensure_ascii=False, indent=2)
            intent.write(write_values)
            payload = intent._sandbox_payload('PENDING', extra={
                'sandbox_seed': True,
                'actions': details.get('actions') or [],
                'payment_reference': details.get('payment_reference'),
                'qr_string': details.get('qr_string'),
                'payment_url': details.get('payment_url'),
                'deeplink_url': details.get('deeplink_url'),
            })
            intent._set_raw_response(payload)
            intent._record_sandbox_event('seed', payload)
        return self._sandbox_notification(_('Data sandbox pembayaran sudah dibuat.'))

    def _sandbox_payload(self, status, extra=None):
        self.ensure_one()
        is_midtrans = self.provider == 'midtrans'
        transaction_status = {
            'SUCCEEDED': 'settlement',
            'PENDING': 'pending',
            'EXPIRED': 'expire',
            'FAILED': 'deny',
        }.get(status, 'pending')
        data = {
            'id': self.midtrans_transaction_id or self.xendit_latest_payment_id or ('sandbox-payment-%s' % self.id),
            'status': status,
            'transaction_status': transaction_status,
            'order_id': self.midtrans_order_id or self.xendit_reference_id or self.name,
            'reference_id': self.midtrans_order_id or self.xendit_reference_id or self.name,
            'payment_request_id': self.xendit_payment_request_id or ('sandbox-request-%s' % self.id),
            'amount': int(round(self.amount or 0.0)),
            'gross_amount': '%.2f' % (self.amount or 0.0),
            'status_code': '200' if transaction_status in ('settlement', 'capture') else '201',
            'currency': self.currency_id.name or 'IDR',
            'channel_code': self.midtrans_bank or self.xendit_channel_code,
            'payment_type': self.midtrans_payment_type or self.payment_method_code,
            'payment_method': {
                'type': self.payment_method_code,
                'reusability': 'ONE_TIME_USE',
            },
            'metadata': {
                'simulated_by_unitrade': True,
                'sale_order_id': self.sale_order_id.id,
            },
        }
        if self.payment_reference:
            data['payment_code'] = self.payment_reference
            data['account_number'] = self.payment_reference
        if self.qr_string:
            data['qr_string'] = self.qr_string
        if self.payment_url:
            data['payment_url'] = self.payment_url
        if self.deeplink_url:
            data['deeplink_url'] = self.deeplink_url
        if extra:
            data.update(extra)
        if is_midtrans:
            return data
        return {
            'event': 'payment.succeeded' if status == 'SUCCEEDED' else 'payment.%s' % status.lower(),
            'created': fields.Datetime.now().isoformat(),
            'data': data,
        }

    def _record_sandbox_event(self, suffix, payload):
        self.ensure_one()
        payload_json = json.dumps(payload, ensure_ascii=False, indent=2)
        payload_hash = hashlib.sha256(payload_json.encode('utf-8')).hexdigest()
        event_stamp = fields.Datetime.now().strftime('%Y%m%d%H%M%S%f')
        return self.env['unitrade.payment.event'].sudo().create({
            'name': 'sandbox:%s:%s' % (self.name, suffix),
            'provider': self.provider,
            'event_key': 'sandbox:%s:%s:%s' % (self.id, suffix, event_stamp),
            'request_id': 'sandbox-%s-%s' % (suffix, self.id),
            'payload_hash': payload_hash,
            'payload_json': payload_json,
            'payment_intent_id': self.id,
            'order_id': self.sale_order_id.id,
            'state': 'processed',
        })

    def _sandbox_notification(self, message):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('UniTrade Sandbox'),
                'message': message,
                'type': 'success',
                'sticky': False,
            },
        }

    def _ensure_simulatable(self):
        self.ensure_one()
        if self.provider not in ('midtrans', 'xendit'):
            raise UserError(_('Simulator hanya tersedia untuk payment intent Midtrans/Xendit.'))
        if not self.sale_order_id:
            raise UserError(_('Payment intent ini belum terhubung ke sale order.'))

    def action_simulate_midtrans_paid(self):
        for intent in self.sudo():
            intent._ensure_simulatable()
            intent.action_seed_sandbox_payment_details()
            payload = intent._sandbox_payload('SUCCEEDED')
            if intent.provider == 'midtrans':
                intent.sale_order_id.sudo()._unitrade_mark_midtrans_paid(intent, payload)
            else:
                intent.sale_order_id.sudo()._unitrade_mark_xendit_paid(intent, payload)
            intent._record_sandbox_event('paid', payload)
        return self._sandbox_notification(_('Webhook paid berhasil disimulasikan.'))

    def action_simulate_midtrans_expired(self):
        for intent in self.sudo():
            intent._ensure_simulatable()
            payload = intent._sandbox_payload('EXPIRED')
            intent.write({
                'state': 'expired',
                'raw_response': json.dumps(payload, ensure_ascii=False, indent=2),
                'error_message': _('Simulated expired notification.'),
            })
            intent.sale_order_id.sudo().write({
                'x_payment_status': 'expired',
                'x_unitrade_order_state': 'payment_pending',
            })
            intent._record_sandbox_event('expired', payload)
        return self._sandbox_notification(_('Webhook expired berhasil disimulasikan.'))

    def action_simulate_midtrans_failed(self):
        for intent in self.sudo():
            intent._ensure_simulatable()
            payload = intent._sandbox_payload('FAILED')
            intent.write({
                'state': 'failed',
                'raw_response': json.dumps(payload, ensure_ascii=False, indent=2),
                'error_message': _('Simulated failed notification.'),
            })
            intent.sale_order_id.sudo().write({
                'x_payment_status': 'failed',
                'x_unitrade_order_state': 'payment_pending',
            })
            intent._record_sandbox_event('failed', payload)
        return self._sandbox_notification(_('Webhook failed berhasil disimulasikan.'))

    def action_simulate_xendit_paid(self):
        return self.action_simulate_midtrans_paid()

    def action_simulate_xendit_expired(self):
        return self.action_simulate_midtrans_expired()

    def action_simulate_xendit_failed(self):
        return self.action_simulate_midtrans_failed()
