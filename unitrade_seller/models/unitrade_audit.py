"""Optional bridge to unitrade.admin.audit.log.

unitrade_seller does NOT depend on unitrade_admin (admin depends on
seller, not the other way). This helper looks up the audit log model
at runtime so that audit recording is a no-op when unitrade_admin is
not installed yet.
"""
import logging

_logger = logging.getLogger(__name__)


def log_admin_action(env, action, description='', record=None, severity='info', payload=None):
    """Write an audit entry if unitrade.admin.audit.log is installed."""
    if 'unitrade.admin.audit.log' not in env.registry:
        return
    try:
        env['unitrade.admin.audit.log'].sudo().log_action(
            action,
            description=description,
            record=record,
            severity=severity,
            payload=payload,
        )
    except Exception:  # noqa: BLE001
        _logger.exception('Failed to write seller audit log: %s', action)
