from odoo import models, fields
import logging

_logger = logging.getLogger(__name__)


class UnitradeNotification(models.Model):
    _name = 'unitrade.notification'
    _description = 'UniTrade System Notification'
    _order = 'create_date desc'

    user_id = fields.Many2one('res.users', string='User', required=True, ondelete='cascade', index=True)
    title = fields.Char(string='Judul', required=True)
    message = fields.Text(string='Pesan')
    notification_type = fields.Selection([
        ('order', 'Pesanan'),
        ('payment', 'Pembayaran'),
        ('delivery', 'Pengiriman'),
        ('chat', 'Chat'),
        ('system', 'Sistem'),
    ], string='Tipe', default='system')
    is_read = fields.Boolean(string='Sudah Dibaca', default=False)
    reference_model = fields.Char(string='Model Referensi')
    reference_id = fields.Integer(string='ID Referensi')

    def action_mark_read(self):
        self.write({'is_read': True})
