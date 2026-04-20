from odoo import http
from odoo.http import request
import logging
import hashlib
import json

_logger = logging.getLogger(__name__)


class UnitradePaymentController(http.Controller):

    @http.route('/unitrade/payment/webhook', type='json', auth='none', csrf=False, methods=['POST'])
    def payment_webhook(self, **kwargs):
        """Handle Midtrans payment notification webhook"""
        data = request.jsonrequest
        _logger.info('Midtrans webhook received: %s', json.dumps(data))

        order_id = data.get('order_id')
        transaction_status = data.get('transaction_status')
        fraud_status = data.get('fraud_status', 'accept')
        signature_key = data.get('signature_key')

        # Verify signature
        server_key = request.env['ir.config_parameter'].sudo().get_param(
            'unitrade.midtrans.server_key', ''
        )
        status_code = data.get('status_code', '')
        gross_amount = data.get('gross_amount', '')

        expected_sig = hashlib.sha512(
            f"{order_id}{status_code}{gross_amount}{server_key}".encode()
        ).hexdigest()

        if signature_key != expected_sig:
            _logger.warning('Invalid Midtrans signature for order %s', order_id)
            return {'status': 'error', 'message': 'Invalid signature'}

        # Find and update order
        order = request.env['sale.order'].sudo().search([('name', '=', order_id)], limit=1)
        if not order:
            _logger.error('Order not found: %s', order_id)
            return {'status': 'error', 'message': 'Order not found'}

        if transaction_status in ('capture', 'settlement'):
            if fraud_status == 'accept':
                order.write({
                    'x_payment_status': 'paid',
                    'x_payment_method': data.get('payment_type', ''),
                    'x_paid_at': data.get('settlement_time'),
                })
                order.action_confirm()
                _logger.info('Order %s paid successfully', order_id)
        elif transaction_status in ('deny', 'cancel'):
            order.write({'x_payment_status': 'failed'})
        elif transaction_status == 'expire':
            order.write({'x_payment_status': 'expired'})
        elif transaction_status == 'pending':
            order.write({'x_payment_status': 'pending'})

        return {'status': 'ok'}

    @http.route('/unitrade/payment/finish', type='http', auth='public', website=True)
    def payment_finish(self, **kwargs):
        """Payment finish redirect page"""
        values = {'page_title': 'Pembayaran — UniTrade'}
        return request.render('unitrade_payment.payment_finish_template', values)
