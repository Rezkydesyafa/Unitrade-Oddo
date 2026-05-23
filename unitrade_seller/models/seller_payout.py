import json
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class UnitradeSellerPayout(models.Model):
    _name = 'unitrade.seller.payout'
    _description = 'UniTrade Seller Payout Request'
    _order = 'requested_at desc, id desc'

    name = fields.Char(string='Nomor Pencairan', default='New', required=True, readonly=True, copy=False)
    seller_id = fields.Many2one('unitrade.seller', string='Seller', required=True, index=True, ondelete='cascade')
    user_id = fields.Many2one('res.users', string='User', related='seller_id.user_id', store=True, index=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True, default=lambda self: self.env.company.currency_id)
    amount = fields.Monetary(string='Nominal', currency_field='currency_id', required=True)
    state = fields.Selection([
        ('pending', 'Diproses'),
        ('processing', 'Diproses'),
        ('succeeded', 'Berhasil'),
        ('failed', 'Gagal'),
    ], string='Status', default='pending', required=True, index=True)
    destination_channel_code = fields.Char(string='Kode Bank / Channel')
    destination_channel_label = fields.Char(string='Rekening Tujuan')
    destination_account_number = fields.Char(string='Nomor Rekening / HP')
    destination_account_name = fields.Char(string='Nama Pemilik Rekening')
    ledger_ids_json = fields.Text(string='Escrow Ledger IDs JSON', default='[]', copy=False)
    payout_reference = fields.Char(string='Referensi Pencairan', copy=False, index=True)
    requested_at = fields.Datetime(string='Diminta Pada', default=fields.Datetime.now, required=True, index=True)
    processed_at = fields.Datetime(string='Diproses Pada', copy=False)
    completed_at = fields.Datetime(string='Selesai Pada', copy=False)
    failure_reason = fields.Text(string='Alasan Gagal', copy=False)
    proof_file = fields.Binary(string='Bukti Transfer', attachment=True, copy=False)
    proof_filename = fields.Char(string='Nama File Bukti', copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if record.name == 'New':
                record.name = 'WD-%05d' % record.id
        return records

    def ledger_ids_list(self):
        self.ensure_one()
        try:
            values = json.loads(self.ledger_ids_json or '[]')
        except (TypeError, ValueError):
            _logger.warning('Invalid ledger_ids_json on payout %s', self.id)
            return []
        return [int(value) for value in values if str(value).isdigit()]
