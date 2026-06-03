from odoo import models, fields, api
import logging

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
    x_payment_provider = fields.Selection(
        [
            ('midtrans', 'Midtrans'),
            ('xendit', 'Xendit'),
            ('doku', 'DOKU'),
        ],
        string='Payment Provider',
        compute='_compute_unitrade_payment_provider',
    )
    x_midtrans_transaction_id = fields.Char(string='Midtrans Transaction ID', readonly=True, copy=False)
    x_midtrans_snap_token = fields.Char(string='Snap Token', readonly=True, copy=False)
    x_midtrans_payment_type = fields.Char(string='Midtrans Payment Type', readonly=True, copy=False)
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
    x_completed_at = fields.Datetime(string='Waktu Selesai', readonly=True, copy=False)
    x_escrow_state = fields.Selection([
        ('none', 'No Escrow'),
        ('held', 'Held'),
        ('releasable', 'Releasable'),
        ('released', 'Released'),
        ('disputed', 'Disputed'),
        ('refunded', 'Refunded'),
        ('cancelled', 'Cancelled'),
    ], string='Escrow State', default='none', tracking=True, copy=False)
    x_unitrade_order_state = fields.Selection([
        ('cart', 'Cart'),
        ('payment_pending', 'Menunggu Pembayaran'),
        ('paid_escrow', 'Dana Ditahan'),
        ('processing', 'Diproses'),
        ('completed', 'Selesai'),
        ('cancelled', 'Dibatalkan'),
        ('refunded', 'Refund'),
    ], string='Status UniTrade', default='cart', tracking=True, copy=False)
    x_midtrans_order_id = fields.Char(
        string='Midtrans Order ID',
        compute='_compute_unitrade_midtrans_order_id',
        store=False,
    )
    x_xendit_reference_id = fields.Char(
        string='Xendit Reference ID',
        compute='_compute_unitrade_xendit_fields',
        store=False,
    )
    x_xendit_payment_request_id = fields.Char(
        string='Xendit Payment Request ID',
        compute='_compute_unitrade_xendit_fields',
        store=False,
    )
    x_xendit_payment_url = fields.Char(
        string='Xendit Payment URL',
        compute='_compute_unitrade_xendit_fields',
        store=False,
    )
    x_xendit_channel_code = fields.Char(
        string='Xendit Channel',
        compute='_compute_unitrade_xendit_fields',
        store=False,
    )
    x_cancel_deadline_at = fields.Datetime(string='Cancel Deadline', copy=False)
    x_cancelled_by_id = fields.Many2one('res.users', string='Cancelled By', copy=False)
    x_cancelled_at = fields.Datetime(string='Cancelled At', copy=False)
    x_cancel_reason = fields.Text(string='Cancel Reason', copy=False)

    @api.depends('x_payment_intent_id.provider', 'x_midtrans_transaction_id')
    def _compute_unitrade_payment_provider(self):
        for order in self:
            if order.x_payment_intent_id:
                order.x_payment_provider = order.x_payment_intent_id.provider
            elif order.x_midtrans_transaction_id:
                order.x_payment_provider = 'midtrans'
            else:
                order.x_payment_provider = False

    @api.depends('x_payment_intent_id.midtrans_order_id', 'x_midtrans_transaction_id', 'name')
    def _compute_unitrade_midtrans_order_id(self):
        for order in self:
            order.x_midtrans_order_id = (
                order.x_payment_intent_id.midtrans_order_id
                if order.x_payment_intent_id and order.x_payment_intent_id.midtrans_order_id
                else order.x_midtrans_transaction_id or order.name
            )

    @api.depends(
        'x_payment_intent_id.xendit_reference_id',
        'x_payment_intent_id.xendit_payment_request_id',
        'x_payment_intent_id.payment_url',
        'x_payment_intent_id.xendit_channel_code',
    )
    def _compute_unitrade_xendit_fields(self):
        for order in self:
            intent = order.x_payment_intent_id
            order.x_xendit_reference_id = intent.xendit_reference_id if intent else False
            order.x_xendit_payment_request_id = intent.xendit_payment_request_id if intent else False
            order.x_xendit_payment_url = intent.payment_url if intent else False
            order.x_xendit_channel_code = intent.xendit_channel_code if intent else False

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
