from odoo import api, fields, models, _


class UnitradeAdminSettings(models.TransientModel):
    """UniTrade marketplace configuration.

    All values are persisted in ``ir.config_parameter`` (auto-magic
    via the ``config_parameter`` argument) so they are read-safe in
    sudo() context across the codebase.
    """

    _inherit = 'res.config.settings'

    # ===== Listing fee =====
    unitrade_listing_fee_enabled = fields.Boolean(
        string='Aktifkan Fee Upload Produk',
        config_parameter='unitrade.seller.listing_fee.enabled',
        default=True,
    )
    unitrade_listing_fee_threshold = fields.Integer(
        string='Batas Harga Fee (Rp)',
        config_parameter='unitrade.seller.listing_fee.threshold',
        default=1000000,
        help='Harga produk di bawah nilai ini memakai fee rendah.',
    )
    unitrade_listing_fee_low_amount = fields.Integer(
        string='Fee Produk di Bawah Batas (Rp)',
        config_parameter='unitrade.seller.listing_fee.low_amount',
        default=2000,
    )
    unitrade_listing_fee_high_amount = fields.Integer(
        string='Fee Produk di Atas/Sama Batas (Rp)',
        config_parameter='unitrade.seller.listing_fee.high_amount',
        default=5000,
    )
    unitrade_listing_fee_validity_days = fields.Integer(
        string='Masa Berlaku Listing (hari)',
        config_parameter='unitrade.seller.listing_fee.validity_days',
        default=30,
    )
    unitrade_posting_admin_fee = fields.Integer(
        string='Admin Fee Tambahan (Rp)',
        config_parameter='unitrade.seller.posting_admin_fee',
        default=0,
        help='Biaya tambahan opsional di luar fee listing bertingkat.',
    )

    # ===== Checkout / escrow timing =====
    unitrade_cancel_window_minutes = fields.Integer(
        string='Cancel Window (menit)',
        config_parameter='unitrade.cancel_window_minutes',
        default=10,
        help='Buyer dapat membatalkan order otomatis dalam window ini.',
    )
    unitrade_auto_complete_hours = fields.Integer(
        string='Auto Complete (jam)',
        config_parameter='unitrade.auto_complete_hours',
        default=24,
        help='Order otomatis selesai setelah seller upload bukti.',
    )
    unitrade_refund_window_days = fields.Integer(
        string='Window Refund (hari)',
        config_parameter='unitrade.refund_window_days',
        default=2,
    )
    unitrade_dispute_response_hours = fields.Integer(
        string='Window Respons Dispute (jam)',
        config_parameter='unitrade.dispute_response_hours',
        default=48,
    )

    # ===== Payout =====
    unitrade_payout_mode = fields.Selection(
        [('manual', 'Manual'), ('auto', 'Auto (belum aktif)')],
        string='Mode Payout',
        config_parameter='unitrade.payout.mode',
        default='manual',
    )
    unitrade_payout_min = fields.Integer(
        string='Minimum Payout (Rp)',
        config_parameter='unitrade.payout.min',
        default=50000,
    )
    unitrade_payout_fee = fields.Integer(
        string='Fee Payout (Rp)',
        config_parameter='unitrade.payout.fee',
        default=2500,
    )
    unitrade_payout_instructions = fields.Text(
        string='Instruksi Payout',
        config_parameter='unitrade.payout.instructions',
    )

    # ===== Legal / policy =====
    unitrade_terms_url = fields.Char(
        string='URL Syarat Transaksi',
        config_parameter='unitrade.legal.terms_url',
    )
    unitrade_refund_policy_url = fields.Char(
        string='URL Kebijakan Refund',
        config_parameter='unitrade.legal.refund_url',
    )
    unitrade_protection_label = fields.Char(
        string='Label Proteksi (copy)',
        config_parameter='unitrade.legal.protection_label',
        default='Transaksi terlindungi escrow UniTrade',
    )

    # ===== Integrations =====
    unitrade_midtrans_server_key = fields.Char(
        string='Midtrans Server Key',
        config_parameter='unitrade.midtrans.server_key',
    )
    unitrade_midtrans_client_key = fields.Char(
        string='Midtrans Client Key',
        config_parameter='unitrade.midtrans.client_key',
    )
    unitrade_midtrans_is_production = fields.Boolean(
        string='Midtrans Production Mode',
        config_parameter='unitrade.midtrans.is_production',
        default=False,
    )
    unitrade_mapbox_token = fields.Char(
        string='Mapbox Access Token',
        config_parameter='unitrade.mapbox.token',
    )
    unitrade_gosend_credential = fields.Char(
        string='GoSend Credential',
        config_parameter='unitrade.gosend.credential',
    )

    # ===== Notifications =====
    unitrade_notify_pending_threshold = fields.Integer(
        string='Notif Pending KTM (jumlah)',
        config_parameter='unitrade.notify.ktm_threshold',
        default=5,
        help='Notifikasi admin saat pending KTM mencapai jumlah ini.',
    )
    unitrade_notify_overdue_minutes = fields.Integer(
        string='Order Tertunda (menit)',
        config_parameter='unitrade.notify.overdue_minutes',
        default=60,
    )

    # Field UniTrade yang dilacak untuk audit log + mapping ke config_parameter
    UNITRADE_AUDITED_PARAMS = {
        'unitrade_listing_fee_enabled': 'unitrade.seller.listing_fee.enabled',
        'unitrade_listing_fee_threshold': 'unitrade.seller.listing_fee.threshold',
        'unitrade_listing_fee_low_amount': 'unitrade.seller.listing_fee.low_amount',
        'unitrade_listing_fee_high_amount': 'unitrade.seller.listing_fee.high_amount',
        'unitrade_listing_fee_validity_days': 'unitrade.seller.listing_fee.validity_days',
        'unitrade_posting_admin_fee': 'unitrade.seller.posting_admin_fee',
        'unitrade_cancel_window_minutes': 'unitrade.cancel_window_minutes',
        'unitrade_auto_complete_hours': 'unitrade.auto_complete_hours',
        'unitrade_refund_window_days': 'unitrade.refund_window_days',
        'unitrade_dispute_response_hours': 'unitrade.dispute_response_hours',
        'unitrade_payout_mode': 'unitrade.payout.mode',
        'unitrade_payout_min': 'unitrade.payout.min',
        'unitrade_payout_fee': 'unitrade.payout.fee',
        'unitrade_payout_instructions': 'unitrade.payout.instructions',
        'unitrade_terms_url': 'unitrade.legal.terms_url',
        'unitrade_refund_policy_url': 'unitrade.legal.refund_url',
        'unitrade_protection_label': 'unitrade.legal.protection_label',
        'unitrade_midtrans_server_key': 'unitrade.midtrans.server_key',
        'unitrade_midtrans_client_key': 'unitrade.midtrans.client_key',
        'unitrade_midtrans_is_production': 'unitrade.midtrans.is_production',
        'unitrade_mapbox_token': 'unitrade.mapbox.token',
        'unitrade_gosend_credential': 'unitrade.gosend.credential',
        'unitrade_notify_pending_threshold': 'unitrade.notify.ktm_threshold',
        'unitrade_notify_overdue_minutes': 'unitrade.notify.overdue_minutes',
    }

    SECRET_FIELDS = {
        'unitrade_midtrans_server_key',
        'unitrade_midtrans_client_key',
        'unitrade_mapbox_token',
        'unitrade_gosend_credential',
    }

    def _redact(self, field_name, value):
        if field_name in self.SECRET_FIELDS and value:
            return '***'
        return value

    def _unitrade_settings_snapshot(self):
        """Read current value of all audited fields from ir.config_parameter."""
        ICP = self.env['ir.config_parameter'].sudo()
        snapshot = {}
        for field_name, param_key in self.UNITRADE_AUDITED_PARAMS.items():
            snapshot[field_name] = ICP.get_param(param_key, default='')
        return snapshot

    def set_values(self):
        """Override to write an audit log entry when admin updates settings."""
        before = self._unitrade_settings_snapshot()
        result = super().set_values()
        after = self._unitrade_settings_snapshot()

        changed = {}
        for key in self.UNITRADE_AUDITED_PARAMS:
            old = before.get(key)
            new = after.get(key)
            if old != new:
                changed[key] = {
                    'before': self._redact(key, old),
                    'after': self._redact(key, new),
                }

        if changed and 'unitrade.admin.audit.log' in self.env.registry:
            try:
                self.env['unitrade.admin.audit.log'].sudo().log_action(
                    'settings.update',
                    description=_('Settings UniTrade diubah oleh %s. Field: %s') % (
                        self.env.user.name,
                        ', '.join(sorted(changed.keys())),
                    ),
                    severity='warning',
                    payload={'changes': changed, 'user_id': self.env.uid},
                )
            except Exception:  # noqa: BLE001
                import logging
                logging.getLogger(__name__).exception('Failed to write settings audit log')
        return result
