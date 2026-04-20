from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class SaleOrderUniTrade(models.Model):
    _inherit = 'sale.order'

    x_midtrans_transaction_id = fields.Char(string='Midtrans Transaction ID', readonly=True, copy=False)
    x_midtrans_snap_token = fields.Char(string='Snap Token', readonly=True, copy=False)
    x_payment_status = fields.Selection([
        ('pending', 'Menunggu Pembayaran'),
        ('paid', 'Dibayar'),
        ('failed', 'Gagal'),
        ('expired', 'Kadaluarsa'),
        ('refunded', 'Refund'),
    ], string='Status Pembayaran', default='pending', tracking=True)
    x_payment_method = fields.Char(string='Metode Pembayaran', readonly=True)
    x_paid_at = fields.Datetime(string='Waktu Pembayaran', readonly=True)

    def _get_midtrans_key(self, key_name):
        return self.env['ir.config_parameter'].sudo().get_param(key_name, default='')

    def action_create_midtrans_transaction(self):
        """Create Midtrans Snap transaction"""
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

            param = {
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
            }

            transaction = snap.create_transaction(param)
            self.write({
                'x_midtrans_snap_token': transaction['token'],
                'x_midtrans_transaction_id': self.name,
            })
            _logger.info('Midtrans transaction created for order %s', self.name)
            return transaction

        except ImportError:
            _logger.warning('midtransclient not installed. pip install midtransclient')
            return False
        except Exception as e:
            _logger.error('Midtrans error for order %s: %s', self.name, str(e))
            return False
