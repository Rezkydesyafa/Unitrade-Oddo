import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.addons.unitrade_payment.xendit_methods import XENDIT_PAYMENT_METHODS
from odoo.addons.unitrade_payment.midtrans_methods import MIDTRANS_PAYMENT_METHODS, midtrans_method_enabled

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

    def _listing_fee_expires_at(self):
        config = self.env['ir.config_parameter'].sudo()
        try:
            days = int(float(config.get_param('unitrade.seller.listing_fee.validity_days', 30) or 30))
        except (TypeError, ValueError):
            days = 30
        return fields.Datetime.now() + timedelta(days=max(1, days))

    def _publish_listing_fee_product(self):
        for intent in self.sudo():
            product = intent.product_template_id
            if intent.intent_type != 'listing_fee' or intent.state != 'paid' or not product:
                continue
            paid_at = intent.paid_at or fields.Datetime.now()
            if hasattr(product, '_unitrade_apply_listing_payment'):
                product._unitrade_apply_listing_payment(
                    listing_fee=intent.amount,
                    paid_at=paid_at,
                    payment_intent=intent,
                    fee_status='paid',
                )
                _logger.info('Published listing fee product %s after payment intent %s paid', product.id, intent.id)
                continue
            values = {
                'sale_ok': True,
                'website_published': True,
            }
            if 'x_listing_fee' in product._fields:
                values['x_listing_fee'] = intent.amount
            if 'x_listing_activated_at' in product._fields:
                values['x_listing_activated_at'] = paid_at
            if 'x_listing_expires_at' in product._fields:
                values['x_listing_expires_at'] = intent._listing_fee_expires_at()
            if 'detailed_type' in product._fields:
                values['detailed_type'] = 'consu'
            elif 'type' in product._fields:
                values['type'] = 'consu'
            if 'x_listing_fee_status' in product._fields:
                values['x_listing_fee_status'] = 'paid'
            if 'x_listing_fee_payment_id' in product._fields:
                values['x_listing_fee_payment_id'] = intent.id
            if 'x_listing_fee_paid_at' in product._fields:
                values['x_listing_fee_paid_at'] = paid_at
            product.sudo().write(values)
            _logger.info('Published listing fee product %s after payment intent %s paid', product.id, intent.id)

    def _archive_unpaid_listing_fee_products(self):
        PaymentIntent = self.env['unitrade.payment.intent'].sudo()
        products = self.sudo().mapped('product_template_id').exists()
        for product in products:
            if (
                'x_listing_fee_status' in product._fields
                and product.x_listing_fee_status in ('paid', 'waived', 'not_required')
            ):
                continue
            paid_intent = PaymentIntent.search([
                ('intent_type', '=', 'listing_fee'),
                ('product_template_id', '=', product.id),
                ('state', '=', 'paid'),
            ], limit=1)
            if paid_intent:
                continue
            latest_intent = PaymentIntent.search([
                ('intent_type', '=', 'listing_fee'),
                ('product_template_id', '=', product.id),
            ], order='create_date desc, id desc', limit=1)
            if latest_intent.state not in ('expired', 'failed', 'cancelled'):
                continue
            values = {
                'sale_ok': False,
                'website_published': False,
            }
            if 'active' in product._fields:
                values['active'] = False
            product.with_context(active_test=False).sudo().write(values)
            _logger.info('Archived unpaid listing fee product %s after intent %s expired', product.id, latest_intent.id)

    @api.model
    def _unitrade_expire_stale_listing_fee_intents(self, seller=False, product=False):
        now = fields.Datetime.now()
        domain = [
            ('intent_type', '=', 'listing_fee'),
            ('state', '=', 'pending'),
            ('expires_at', '!=', False),
            ('expires_at', '<=', now),
        ]
        if seller:
            domain.append(('seller_id', '=', seller.id))
        if product:
            domain.append(('product_template_id', '=', product.id))
        intents = self.sudo().search(domain)
        if not intents:
            return 0
        intents.write({
            'state': 'expired',
            'error_message': _('Waktu pembayaran listing sudah habis.'),
        })
        intents._archive_unpaid_listing_fee_products()
        return len(intents)

    @api.model
    def _cron_unitrade_expire_stale_listing_fee_intents(self):
        expired_count = self._unitrade_expire_stale_listing_fee_intents()
        _logger.info('UniTrade listing fee expiry cron completed: expired=%s', expired_count)
        return expired_count

    def _mark_listing_fee_pending(self):
        """Sync product fee status when intent moves to pending/failed/expired states."""
        for intent in self.sudo():
            product = intent.product_template_id
            if intent.intent_type != 'listing_fee' or not product:
                continue
            if 'x_listing_fee_status' not in product._fields:
                continue
            new_status = None
            if intent.state == 'pending':
                new_status = 'pending'
            elif intent.state in ('failed', 'expired', 'cancelled'):
                new_status = 'failed'
            if new_status and product.x_listing_fee_status not in ('paid', 'waived', 'not_required'):
                product.sudo().write({'x_listing_fee_status': new_status})

    def write(self, vals):
        result = super().write(vals)
        if vals.get('state') == 'paid':
            self._publish_listing_fee_product()
        elif 'state' in vals and vals.get('state') in ('pending', 'failed', 'expired', 'cancelled'):
            self._mark_listing_fee_pending()
        return result

    @api.model_create_multi
    def create(self, vals_list):
        intents = super().create(vals_list)
        intents.filtered(lambda intent: intent.state == 'paid')._publish_listing_fee_product()
        intents.filtered(
            lambda intent: intent.state in ('pending', 'failed', 'expired', 'cancelled')
        )._mark_listing_fee_pending()
        return intents

    def _set_raw_request(self, payload):
        for intent in self:
            intent.raw_request = json.dumps(payload, ensure_ascii=False, indent=2)

    def _set_raw_response(self, payload):
        for intent in self:
            intent.raw_response = json.dumps(payload, ensure_ascii=False, indent=2)

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

    def _midtrans_expiry_at(self):
        return fields.Datetime.now() + timedelta(minutes=self._midtrans_payment_expiry_minutes())

    def _midtrans_order_time(self):
        jakarta_tz = timezone(timedelta(hours=7))
        return datetime.now(jakarta_tz).strftime('%Y-%m-%d %H:%M:%S +0700')

    def _midtrans_payment_method(self, payment_method):
        method_key = payment_method if payment_method in MIDTRANS_PAYMENT_METHODS else ''
        if not method_key:
            raise UserError(_('Metode pembayaran tidak valid.'))
        method = dict(MIDTRANS_PAYMENT_METHODS[method_key])
        config = self.env['ir.config_parameter'].sudo()
        if not midtrans_method_enabled(config, method_key, method):
            raise UserError(_('Metode pembayaran %s belum aktif di konfigurasi Midtrans.') % method['label'])
        if method['type'] == 'CARD':
            raise UserError(_('Kartu belum diaktifkan karena harus memakai tokenisasi client-side agar tetap aman.'))
        return method_key, method

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

    def _listing_fee_midtrans_order_id(self, product):
        return ('UTL%s%s' % (product.id, uuid.uuid4().hex[:14])).upper()[:50]

    def _listing_fee_customer_payload(self, seller):
        partner = seller.partner_id or seller.user_id.partner_id
        phone = (partner.mobile or partner.phone or '').replace('+', '').replace(' ', '').replace('-', '') if partner else ''
        payload = {
            'first_name': ((partner.name if partner else '') or seller.name or 'UniTrade Seller')[:255],
        }
        if partner and partner.email:
            payload['email'] = partner.email
        if phone:
            payload['phone'] = phone
        return payload

    def _listing_fee_items_payload(self, product, amount):
        return [{
            'id': ('listing-fee-%s' % product.id)[:50],
            'price': int(round(amount or 0.0)),
            'quantity': 1,
            'name': ('Biaya Upload Produk %s' % (product.name or 'UniTrade'))[:50],
        }]

    def _listing_fee_midtrans_payload(self, seller, product, method, amount, order_id, finish_url):
        payload = {
            'payment_type': method['payment_type'],
            'transaction_details': {
                'order_id': order_id,
                'gross_amount': int(round(amount or 0.0)),
            },
            'customer_details': self._listing_fee_customer_payload(seller),
            'item_details': self._listing_fee_items_payload(product, amount),
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

    @api.model
    def create_listing_fee_midtrans_payment(self, seller, product, method_key, amount, currency):
        server_key = self._get_midtrans_param('unitrade.midtrans.server_key')
        if not server_key:
            raise UserError(_('Konfigurasi Midtrans belum lengkap. Isi Server Key di System Parameters.'))

        method_key, method = self._midtrans_payment_method(method_key)
        total_amount = int(round(amount or 0.0))
        if total_amount <= 0:
            raise UserError(_('Total pembayaran tidak valid.'))

        now = fields.Datetime.now()
        stale_intents = self.sudo().search([
            ('intent_type', '=', 'listing_fee'),
            ('product_template_id', '=', product.id),
            ('seller_id', '=', seller.id),
            ('provider', '=', 'midtrans'),
            ('state', '=', 'pending'),
            '|',
            ('amount', '!=', total_amount),
            ('payment_method_code', '!=', method_key),
        ])
        expired_intents = self.sudo().search([
            ('intent_type', '=', 'listing_fee'),
            ('product_template_id', '=', product.id),
            ('seller_id', '=', seller.id),
            ('provider', '=', 'midtrans'),
            ('state', '=', 'pending'),
            ('expires_at', '!=', False),
            ('expires_at', '<=', now),
        ])
        (stale_intents | expired_intents).write({
            'state': 'expired',
            'error_message': _('Superseded by a newer listing fee payment attempt.'),
        })

        existing = self.sudo().search([
            ('intent_type', '=', 'listing_fee'),
            ('product_template_id', '=', product.id),
            ('seller_id', '=', seller.id),
            ('provider', '=', 'midtrans'),
            ('state', '=', 'pending'),
            ('amount', '=', total_amount),
            ('payment_method_code', '=', method_key),
            ('midtrans_order_id', '!=', False),
            '|',
            ('expires_at', '=', False),
            ('expires_at', '>', now),
        ], order='create_date desc', limit=1)
        if existing:
            return existing

        partner = seller.partner_id or seller.user_id.partner_id
        order_id = self._listing_fee_midtrans_order_id(product)
        expires_at = self._midtrans_expiry_at()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '').rstrip('/')
        finish_url = '%s/unitrade/payment/finish?reference_id=%s' % (base_url, order_id)
        payload = self._listing_fee_midtrans_payload(seller, product, method, total_amount, order_id, finish_url)
        intent = self.sudo().create({
            'name': order_id,
            'provider': 'midtrans',
            'intent_type': 'listing_fee',
            'state': 'draft',
            'amount': total_amount,
            'currency_id': currency.id,
            'product_template_id': product.id,
            'partner_id': partner.id if partner else False,
            'seller_id': seller.id,
            'payment_method_code': method_key,
            'payment_method_label': method['label'],
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
            _logger.info('Midtrans listing fee payment created for product %s reference %s', product.id, order_id)
            return intent
        except UserError:
            raise
        except requests.RequestException as error:
            intent.write({'state': 'failed', 'error_message': str(error)})
            _logger.exception('Midtrans listing fee request failed for product %s', product.id)
            raise UserError(_('Gagal menghubungi Midtrans. Coba lagi beberapa saat lagi.')) from error

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
        if not self.sale_order_id and self.intent_type != 'listing_fee':
            raise UserError(_('Payment intent ini belum terhubung ke sale order.'))

    def action_simulate_midtrans_paid(self):
        for intent in self.sudo():
            intent._ensure_simulatable()
            intent.action_seed_sandbox_payment_details()
            payload = intent._sandbox_payload('SUCCEEDED')
            if intent.intent_type == 'listing_fee':
                intent.write({
                    'state': 'paid',
                    'paid_at': fields.Datetime.now(),
                    'raw_response': json.dumps(payload, ensure_ascii=False, indent=2),
                })
            elif intent.provider == 'midtrans':
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
            if intent.sale_order_id:
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
            if intent.sale_order_id:
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
