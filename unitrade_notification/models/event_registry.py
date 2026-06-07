"""Event registry for the UniTrade Notification System.

This module is the single source of truth for the catalogue of
notification events recognised by ``unitrade.notification.emit``. The
registry is intentionally kept as Python data (instead of an ORM model)
because it represents deployment-time configuration that should be
caught at module load time, is straightforward to monkey-patch in
tests, and never needs to be edited by end users at runtime.

Each entry in :data:`EVENT_REGISTRY` describes one ``event_code`` and is
keyed by that code (e.g. ``'order.confirmed'``). The value is a dict
with the following keys:

``category``
    One of ``account``, ``seller``, ``order``, ``payment``, ``chat``,
    ``review`` or ``system``.

``channels``
    Sequence of delivery channels for the event. Allowed values are
    ``'in_app'`` and ``'email'``.

``template``
    XML id of the ``mail.template`` used to render the email body, or
    ``None`` when the event is in-app only.

``critical``
    ``True`` for transactional events that must always reach the user
    via the in-app channel regardless of preferences (mirrors
    :data:`CRITICAL_CATEGORIES`).

The registered events cover the full event coverage matrix described
in the design document (``§Event_Registry``):

* account: ``account.welcome``, ``account.password_reset``
* seller:  ``seller.application_received``, ``seller.approved``,
           ``seller.rejected``
* order:   ``order.new_for_seller``, ``order.confirmed``,
           ``order.shipped``, ``order.delivered``, ``order.cancelled``
* payment: ``payment.success``, ``payment.pending``,
           ``payment.failed``, ``payment.expired``
* chat:    ``chat.new_message``
* review:  ``review.reminder``, ``review.new_for_seller``
* system:  ``system.announcement``, ``system.customer_ticket_reply``,
           ``system.customer_ticket_status``
"""

import logging

_logger = logging.getLogger(__name__)


#: Categories whose in-app notifications cannot be silenced by user
#: preference. Email channel for these categories *can* still be
#: disabled by the user.
CRITICAL_CATEGORIES = frozenset({'account', 'order', 'payment'})


#: Supported notification channels. Kept as a tuple so callers can rely
#: on a stable order when iterating.
SUPPORTED_CHANNELS = ('in_app', 'email')


#: Master event registry. Order is preserved (Python 3.7+ dict ordering)
#: and is intentionally grouped by category for readability.
EVENT_REGISTRY = {
    # -- account --------------------------------------------------------
    'account.welcome': {
        'category': 'account',
        'channels': ('in_app', 'email'),
        'template': 'unitrade_notification.mail_template_account_welcome',
        'critical': True,
    },
    'account.password_reset': {
        'category': 'account',
        'channels': ('email',),
        'template': 'unitrade_notification.mail_template_account_password_reset',
        'critical': True,
    },
    # -- seller ---------------------------------------------------------
    'seller.application_received': {
        'category': 'seller',
        'channels': ('in_app', 'email'),
        'template': 'unitrade_notification.mail_template_seller_application_received',
        'critical': False,
    },
    'seller.approved': {
        'category': 'seller',
        'channels': ('in_app', 'email'),
        'template': 'unitrade_notification.mail_template_seller_approved',
        'critical': False,
    },
    'seller.rejected': {
        'category': 'seller',
        'channels': ('in_app', 'email'),
        'template': 'unitrade_notification.mail_template_seller_rejected',
        'critical': False,
    },
    # -- order ----------------------------------------------------------
    'order.new_for_seller': {
        'category': 'order',
        'channels': ('in_app', 'email'),
        'template': 'unitrade_notification.mail_template_order_new_for_seller',
        'critical': True,
    },
    'order.confirmed': {
        'category': 'order',
        'channels': ('in_app', 'email'),
        'template': 'unitrade_notification.mail_template_order_confirmed',
        'critical': True,
    },
    'order.shipped': {
        'category': 'order',
        'channels': ('in_app', 'email'),
        'template': 'unitrade_notification.mail_template_order_shipped',
        'critical': True,
    },
    'order.delivered': {
        'category': 'order',
        'channels': ('in_app',),
        'template': None,
        'critical': True,
    },
    'order.cancelled': {
        'category': 'order',
        'channels': ('in_app', 'email'),
        'template': 'unitrade_notification.mail_template_order_cancelled',
        'critical': True,
    },
    # -- payment --------------------------------------------------------
    'payment.success': {
        'category': 'payment',
        'channels': ('in_app', 'email'),
        'template': 'unitrade_notification.mail_template_payment_success',
        'critical': True,
    },
    'payment.pending': {
        'category': 'payment',
        'channels': ('in_app', 'email'),
        'template': 'unitrade_notification.mail_template_payment_pending',
        'critical': True,
    },
    'payment.failed': {
        'category': 'payment',
        'channels': ('in_app', 'email'),
        'template': 'unitrade_notification.mail_template_payment_failed',
        'critical': True,
    },
    'payment.expired': {
        'category': 'payment',
        'channels': ('in_app', 'email'),
        'template': 'unitrade_notification.mail_template_payment_expired',
        'critical': True,
    },
    # -- chat -----------------------------------------------------------
    'chat.new_message': {
        'category': 'chat',
        'channels': ('in_app',),
        'template': None,
        'critical': False,
    },
    # -- review ---------------------------------------------------------
    'review.reminder': {
        'category': 'review',
        'channels': ('in_app',),
        'template': None,
        'critical': False,
    },
    'review.new_for_seller': {
        'category': 'review',
        'channels': ('in_app',),
        'template': None,
        'critical': False,
    },
    # -- system ---------------------------------------------------------
    'system.announcement': {
        'category': 'system',
        'channels': ('in_app', 'email'),
        'template': 'unitrade_notification.mail_template_system_announcement',
        'critical': False,
    },
    'system.customer_ticket_reply': {
        'category': 'system',
        'channels': ('in_app',),
        'template': None,
        'critical': False,
    },
    'system.customer_ticket_status': {
        'category': 'system',
        'channels': ('in_app',),
        'template': None,
        'critical': False,
    },
}


# ---------------------------------------------------------------------------
# Self-check on module import: catches misconfigured entries early so a
# bad deploy fails at module load instead of mid-emit.
# ---------------------------------------------------------------------------

def _validate_registry():
    """Sanity-check :data:`EVENT_REGISTRY` at import time.

    Raises ``AssertionError`` (which Odoo turns into a registry load
    failure) if any entry is malformed.
    """
    allowed_categories = {
        'account', 'seller', 'order', 'payment', 'chat', 'review', 'system',
    }
    required_keys = {'category', 'channels', 'template', 'critical'}

    for code, entry in EVENT_REGISTRY.items():
        assert isinstance(code, str) and code, (
            "EVENT_REGISTRY key must be a non-empty string, got %r" % (code,)
        )
        assert required_keys.issubset(entry.keys()), (
            "EVENT_REGISTRY[%r] missing keys %s"
            % (code, required_keys - set(entry.keys()))
        )
        assert entry['category'] in allowed_categories, (
            "EVENT_REGISTRY[%r] has invalid category %r"
            % (code, entry['category'])
        )
        channels = entry['channels']
        assert channels and all(c in SUPPORTED_CHANNELS for c in channels), (
            "EVENT_REGISTRY[%r] has invalid channels %r"
            % (code, channels)
        )
        assert isinstance(entry['critical'], bool), (
            "EVENT_REGISTRY[%r].critical must be bool" % (code,)
        )
        # Cross-check: critical flag must agree with CRITICAL_CATEGORIES.
        assert entry['critical'] == (entry['category'] in CRITICAL_CATEGORIES), (
            "EVENT_REGISTRY[%r] critical=%r inconsistent with category %r"
            % (code, entry['critical'], entry['category'])
        )
        # Email channel implies a template; in-app only events may omit.
        if 'email' in channels:
            assert entry['template'], (
                "EVENT_REGISTRY[%r] declares email channel without template"
                % (code,)
            )


_validate_registry()


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_entry(code):
    """Return the registry entry for ``code`` or ``None`` if unknown.

    A ``None`` return is the canonical signal for "unknown event"; the
    dispatcher uses it to refuse the emission and log a warning rather
    than letting an unbound code reach the database.
    """
    if not isinstance(code, str):
        return None
    return EVENT_REGISTRY.get(code)


def is_known(code):
    """Return ``True`` if ``code`` is a registered event code."""
    return isinstance(code, str) and code in EVENT_REGISTRY


def iter_categories():
    """Yield each distinct category present in the registry.

    Order is the order in which categories first appear in
    :data:`EVENT_REGISTRY`, which mirrors the grouping in the design
    document (account, seller, order, payment, chat, review, system).
    """
    seen = set()
    for entry in EVENT_REGISTRY.values():
        category = entry['category']
        if category not in seen:
            seen.add(category)
            yield category


def iter_channels_for(category):
    """Yield each distinct channel used by events in ``category``.

    Useful for the preference seeder which needs to know which
    ``(category, channel)`` rows to create. If ``category`` is unknown
    the iterator yields nothing and a debug log entry is emitted.
    """
    seen = set()
    found_category = False
    for entry in EVENT_REGISTRY.values():
        if entry['category'] != category:
            continue
        found_category = True
        for channel in entry['channels']:
            if channel not in seen:
                seen.add(channel)
                yield channel
    if not found_category:
        _logger.debug(
            "iter_channels_for: unknown notification category %r", category,
        )
