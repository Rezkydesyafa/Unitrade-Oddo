"""Unified admin audit log.

Centralised log for every critical admin action across UniTrade modules.
Other models call :meth:`UnitradeAdminAuditLog.log_action` to write a row.
"""
import logging

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class UnitradeAdminAuditLog(models.Model):
    _name = 'unitrade.admin.audit.log'
    _description = 'UniTrade Admin Audit Log'
    _order = 'create_date desc'
    _rec_name = 'action'

    action = fields.Char(
        string='Action',
        required=True,
        index=True,
        help='Short identifier of the action, e.g. "user.block", "dispute.resolve"',
    )
    description = fields.Text(string='Deskripsi')
    user_id = fields.Many2one(
        'res.users',
        string='Aktor',
        required=True,
        default=lambda self: self.env.user,
        readonly=True,
    )
    res_model = fields.Char(string='Model Terkait', index=True)
    res_id = fields.Integer(string='ID Record Terkait', index=True)
    res_name = fields.Char(string='Nama Record')
    severity = fields.Selection(
        [('info', 'Info'), ('warning', 'Warning'), ('critical', 'Critical')],
        default='info',
        string='Severity',
        required=True,
        index=True,
    )
    payload = fields.Text(
        string='Payload',
        help='JSON snapshot opsional untuk membantu rekonstruksi state.',
    )

    @api.model
    def log_action(self, action, description='', record=None, severity='info', payload=None):
        """Helper to write an audit entry. Safe to call from anywhere with sudo."""
        try:
            vals = {
                'action': action,
                'description': description or '',
                'severity': severity or 'info',
            }
            if record is not None and getattr(record, '_name', None):
                vals['res_model'] = record._name
                vals['res_id'] = record.id
                vals['res_name'] = record.display_name
            if payload is not None:
                if isinstance(payload, (dict, list)):
                    import json
                    payload = json.dumps(payload, default=str)
                vals['payload'] = str(payload)[:8000]
            self.sudo().create(vals)
        except Exception:  # noqa: BLE001
            _logger.exception('Failed to write audit log: %s', action)
