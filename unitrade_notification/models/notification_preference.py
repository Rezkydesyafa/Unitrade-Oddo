"""User-level notification preferences for the UniTrade Notification System.

This module hosts ``unitrade.notification.preference``, a
``(user_id, category, channel)`` record keyed table that tells the
dispatcher whether a given user wants to receive notifications for a
specific category on a specific channel.

Effective preference resolution rule (mirrors design §Notification_Preference):

    effective_enabled(user, category, channel) :=
        if category in CRITICAL_CATEGORIES and channel == 'in_app':
            True   # cannot be disabled
        else:
            record = pref.search([(user_id, category, channel)], limit=1)
            record.enabled if record else True   # default-on if missing

The seeder :meth:`_ensure_default_preferences` is *idempotent* (Property 3):
calling it more than once for the same user does not create duplicates and
does not modify already-existing rows.
"""

from odoo import api, fields, models
import logging

from .event_registry import (
    CRITICAL_CATEGORIES,
    EVENT_REGISTRY,
    iter_categories,
    iter_channels_for,
)

_logger = logging.getLogger(__name__)


# Selection definition kept in lock-step with ``unitrade.notification.category``
# so a mismatch between the two surfaces immediately at module load.
_CATEGORY_SELECTION = [
    ('account', 'Akun'),
    ('seller', 'Seller'),
    ('order', 'Pesanan'),
    ('payment', 'Pembayaran'),
    ('chat', 'Chat'),
    ('review', 'Review'),
    ('system', 'Sistem'),
]


_CHANNEL_SELECTION = [
    ('in_app', 'In-App'),
    ('email', 'Email'),
]


class UnitradeNotificationPreference(models.Model):
    _name = 'unitrade.notification.preference'
    _description = 'UniTrade Notification Preference'
    _rec_name = 'category'

    # ------------------------------------------------------------------
    # Fields
    # ------------------------------------------------------------------
    user_id = fields.Many2one(
        'res.users',
        string='User',
        required=True,
        index=True,
        ondelete='cascade',
    )
    category = fields.Selection(
        _CATEGORY_SELECTION,
        string='Kategori',
        required=True,
    )
    channel = fields.Selection(
        _CHANNEL_SELECTION,
        string='Channel',
        required=True,
    )
    enabled = fields.Boolean(
        string='Aktif',
        default=True,
        help="When False, the dispatcher skips emissions on this "
             "(category, channel) pair. In-app notifications for "
             "critical categories (account, order, payment) override "
             "this flag and are always delivered.",
    )

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------
    _sql_constraints = [
        (
            'uniq_user_cat_chan',
            'UNIQUE(user_id, category, channel)',
            'Preferensi unik per (user, kategori, channel).',
        ),
    ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @api.model
    def _ensure_default_preferences(self, user_id):
        """Idempotently seed default preferences for ``user_id``.

        For every ``(category, channel)`` pair derived from
        :data:`EVENT_REGISTRY` we ensure exactly one preference row
        exists with ``enabled=True``. Already-existing rows are left
        untouched (their ``enabled`` value is preserved), so calling
        this method any number of additional times is a no-op.

        :param user_id: ``res.users`` id to seed preferences for.
        :return: recordset of all preferences belonging to ``user_id``
            after seeding.
        """
        if not user_id:
            return self.browse()

        # Build the canonical (category, channel) set from the registry
        # so adding a new event automatically widens the preference grid
        # without code changes here.
        desired_pairs = []
        for category in iter_categories():
            for channel in iter_channels_for(category):
                desired_pairs.append((category, channel))

        # Single round-trip read of existing rows for this user.
        existing = self.search([('user_id', '=', user_id)])
        existing_pairs = {(p.category, p.channel) for p in existing}

        missing = [
            {
                'user_id': user_id,
                'category': category,
                'channel': channel,
                'enabled': True,
            }
            for (category, channel) in desired_pairs
            if (category, channel) not in existing_pairs
        ]

        created = self.browse()
        if missing:
            created = self.create(missing)
            _logger.info(
                "Seeded %d default notification preference(s) for user_id=%s",
                len(created), user_id,
            )
        else:
            _logger.debug(
                "No default notification preferences to seed for user_id=%s",
                user_id,
            )

        return existing | created

    @api.model
    def is_enabled(self, user_id, category, channel):
        """Return the effective preference for ``(user_id, category, channel)``.

        Resolution order:

        1. Critical override: if ``category`` is in
           :data:`CRITICAL_CATEGORIES` and ``channel == 'in_app'`` the
           method returns ``True`` regardless of any stored row.
        2. Look up the row; if found return its ``enabled`` value.
        3. Default-on: if no row exists return ``True``.

        Inputs that do not identify a real preference (missing
        ``user_id``, unknown ``category``/``channel``, etc.) fall back
        to ``True`` to keep the dispatcher fail-open: a misconfigured
        caller should not silently swallow a notification.
        """
        # Critical-category override is checked first so a missing row
        # for a critical (category, in_app) pair still returns True.
        if channel == 'in_app' and category in CRITICAL_CATEGORIES:
            return True

        if not user_id:
            return True

        record = self.sudo().search(
            [
                ('user_id', '=', user_id),
                ('category', '=', category),
                ('channel', '=', channel),
            ],
            limit=1,
        )
        if record:
            return bool(record.enabled)

        # Sanity log when the dispatcher asks about a category/channel
        # that does not correspond to any registered event. We still
        # default-on so the emission goes through and surfaces upstream.
        if not any(
            entry['category'] == category and channel in entry['channels']
            for entry in EVENT_REGISTRY.values()
        ):
            _logger.debug(
                "is_enabled: no event uses category=%r channel=%r; "
                "defaulting to True",
                category, channel,
            )
        return True
