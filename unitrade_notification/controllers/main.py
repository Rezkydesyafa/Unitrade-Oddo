# -*- coding: utf-8 -*-
"""HTTP controllers for the UniTrade Notification module.

Routes implemented in this file:

- ``/my/notifications``                 — notification center page (task 11.1)
- ``/my/notifications/unread_count``    — JSON unread counter (task 11.2)
- ``/my/notifications/recent``          — JSON top-5 latest (task 11.2)
- ``/my/notifications/<int:nid>/read``  — mark single as read (task 11.3)
- ``/my/notifications/read_all``        — mark all as read (task 11.3)
- ``/my/notifications/<int:nid>/delete``— delete single (task 11.3)
- ``/my/notifications/settings``        — preference page GET/POST (task 11.4)

Subsequent tasks (11.2, 11.3, 11.4) will add their methods to the
``UnitradeNotificationController`` class defined below. Method ordering
inside the class follows the route ordering above.
"""
import logging

from werkzeug.exceptions import Forbidden, NotFound

from odoo import fields, http
from odoo.http import request

from ..models.event_registry import (
    CRITICAL_CATEGORIES,
    iter_categories,
    iter_channels_for,
)

_logger = logging.getLogger(__name__)


# Allowed category filter values for the notification center page.
# Mirrors ``unitrade.notification.category`` selection plus the synthetic
# ``'all'`` token used to disable the filter.
_ALLOWED_CATEGORIES = (
    'all',
    'order',
    'payment',
    'review',
    'chat',
    'system',
    'account',
    'seller',
)

# Display labels for the category filter (Bahasa Indonesia, per UniTrade UI
# conventions). Order matters — the template renders the tabs in this order.
_CATEGORY_DEFS = [
    {'key': 'all', 'label': 'Semua', 'categories': ()},
    {'key': 'order', 'label': 'Pesanan', 'categories': ('order',)},
    {'key': 'payment', 'label': 'Pembayaran', 'categories': ('payment',)},
    {'key': 'review', 'label': 'Review', 'categories': ('review',)},
    {'key': 'chat', 'label': 'Chat', 'categories': ('chat',)},
    {'key': 'system', 'label': 'Sistem', 'categories': ('system', 'account', 'seller')},
]

_CATEGORY_ICONS = {
    'account': '👤',
    'seller': '🏪',
    'order': '🛍️',
    'payment': '💳',
    'chat': '💬',
    'review': '⭐',
    'system': '🔔',
}

# Page size for the notification center. Kept module-private so future tasks
# (e.g. JSON ``recent`` endpoint) can reuse the same constant if needed.
_PAGE_SIZE = 20


class UnitradeNotificationController(http.Controller):
    """HTTP controller exposing the user-facing notification routes."""

    @staticmethod
    def _ui_category(category):
        """Map backend notification categories to the Figma tab set."""
        return 'system' if category in ('account', 'seller') else (category or 'system')

    @staticmethod
    def _ui_category_domain(category):
        for item in _CATEGORY_DEFS:
            if item['key'] == category:
                return item['categories']
        return ()

    @staticmethod
    def _notification_time_label(value):
        if not value:
            return ''
        try:
            localized = fields.Datetime.context_timestamp(request.env.user, value)
            now = fields.Datetime.context_timestamp(request.env.user, fields.Datetime.now())
        except Exception:
            localized = value
            now = fields.Datetime.now()
        minutes = max(0, int((now - localized).total_seconds() // 60))
        if minutes < 1:
            return 'Baru saja'
        if minutes < 60:
            return '%s menit yang lalu' % minutes
        hours = minutes // 60
        if hours < 24:
            return '%s jam yang lalu' % hours
        days = (now.date() - localized.date()).days
        if days == 1:
            return 'Kemarin'
        if days < 7:
            return '%s hari yang lalu' % days
        return localized.strftime('%d %b %Y')

    def _notification_base_domain(self, Notification, user, scope='user'):
        return [('user_id', '=', user.id)] + Notification._notification_scope_domain(scope)

    def _notification_tab_counts(self, Notification, user, scope='user'):
        rows = Notification.read_group(
            self._notification_base_domain(Notification, user, scope),
            ['category'],
            ['category'],
        )
        raw_counts = {
            row.get('category'): row.get('category_count', 0)
            for row in rows
        }
        total = sum(raw_counts.values())
        tabs = []
        for item in _CATEGORY_DEFS:
            if item['key'] == 'all':
                count = total
            else:
                count = sum(raw_counts.get(category, 0) for category in item['categories'])
            tabs.append({
                'key': item['key'],
                'label': item['label'],
                'count': count,
            })
        return tabs

    # Categories that, for the buyer/user notification center, must always
    # link straight to the buyer orders list (Req: user redirect logic).
    _USER_ORDER_REDIRECT_CATEGORIES = ('order', 'payment')

    # Canonical buyer orders route. Kept relative so it works on every
    # environment; in production this resolves to
    # ``https://unitrade.web.id/my/orders``.
    _USER_ORDERS_URL = '/my/orders'

    def _notification_item_action_url(self, notif, scope='user'):
        """Resolve the click target for a notification row.

        The buyer notification center (``/my/notifications``, ``scope='user'``)
        forces every ``order``/``payment`` notification to ``/my/orders`` so
        users never land on a seller route or an unrelated page. Seller-scope
        rows keep the model-derived target so their redirect logic stays
        independent (Req: separate user/seller redirect logic).
        """
        if (
            scope == 'user'
            and (notif.category or 'system') in self._USER_ORDER_REDIRECT_CATEGORIES
        ):
            return self._USER_ORDERS_URL
        return notif._get_effective_action_url()

    def _notification_item_payload(self, notif, scope='user'):
        category = notif.category or 'system'
        action_url = self._notification_item_action_url(notif, scope=scope)
        return {
            'id': notif.id,
            'title': notif.title or 'Notifikasi UniTrade',
            'message': notif.message or '',
            'category': category,
            'ui_category': self._ui_category(category),
            'category_label': dict(notif._fields['category'].selection).get(category, category),
            'icon': _CATEGORY_ICONS.get(category, '🔔'),
            'action_url': action_url or '',
            'is_read': bool(notif.is_read),
            'time_label': self._notification_time_label(notif.create_date),
        }

    def _current_seller(self):
        user = request.env.user
        if user._is_public():
            return request.env['unitrade.seller'].sudo().browse()
        Seller = request.env['unitrade.seller'].sudo()
        domain = [
            ('user_id', '=', user.id),
            ('status', '=', 'verified'),
        ]
        if 'x_store_active' in Seller._fields:
            domain.append(('x_store_active', '=', True))
        return Seller.search(domain, limit=1)

    def _render_notification_center(
        self,
        page=1,
        category='all',
        scope='user',
        center_url='/my/notifications',
        read_all_url='/my/notifications/read_all',
        title='Notifikasi',
        empty_message='Aktivitas pesanan, pembayaran, review, chat, dan sistem akan muncul di sini.',
    ):
        user = request.env.user

        try:
            page = int(page)
        except (TypeError, ValueError):
            page = 1
        page = max(1, page)

        if category not in _ALLOWED_CATEGORIES:
            category = 'all'
        category = self._ui_category(category)

        Notification = request.env['unitrade.notification'].sudo()
        domain = self._notification_base_domain(Notification, user, scope)
        if category != 'all':
            category_domain = self._ui_category_domain(category)
            if len(category_domain) == 1:
                domain.append(('category', '=', category_domain[0]))
            elif category_domain:
                domain.append(('category', 'in', category_domain))

        total = Notification.search_count(domain)
        unread_count = Notification.search_count(
            self._notification_base_domain(Notification, user, scope) + [
                ('is_read', '=', False),
            ]
        )
        categories = self._notification_tab_counts(Notification, user, scope)

        pager = request.website.pager(
            url=center_url,
            total=total,
            page=page,
            step=_PAGE_SIZE,
            url_args={'category': category},
        )

        records = Notification.search(
            domain,
            order='create_date desc, id desc',
            limit=_PAGE_SIZE,
            offset=pager['offset'],
        )

        _logger.debug(
            "notification_center served: user_id=%s page=%s category=%s scope=%s count=%s",
            user.id, page, category, scope, len(records),
        )

        values = {
            'notifications': records,
            'notification_items': [
                self._notification_item_payload(record, scope=scope) for record in records
            ],
            'page': page,
            'category': category,
            'total': total,
            'unread_count': unread_count,
            'pager': pager,
            'categories': categories,
            'notification_scope': scope,
            'notification_center_url': center_url,
            'notification_read_all_url': read_all_url,
            'notification_page_title': title,
            'notification_empty_message': empty_message,
        }
        return request.render(
            'unitrade_notification.notification_center_page', values,
        )

    # ------------------------------------------------------------------
    # 11.1 Notification center page
    # ------------------------------------------------------------------
    @http.route('/my/notifications', type='http', auth='user', website=True)
    def notification_center(self, page=1, category='all', **kwargs):
        """Render the notification center page for the current user.

        Query params:
            page:     1-based page index (coerced to >=1 on bad input)
            category: one of ``_ALLOWED_CATEGORIES``; falls back to ``'all'``
        """
        user = request.env.user

        # Public users have no notifications; bounce them through login so
        # they return to the same page after authenticating.
        if user._is_public():
            return request.redirect('/web/login?redirect=/my/notifications')

        return self._render_notification_center(
            page=page,
            category=category,
            scope='user',
            center_url='/my/notifications',
            read_all_url='/my/notifications/read_all',
            title='Notifikasi',
        )

    @http.route('/unitrade/seller/notifications', type='http', auth='user', website=True)
    def seller_notification_center(self, page=1, category='all', **kwargs):
        user = request.env.user
        if user._is_public():
            return request.redirect(
                '/web/login?redirect=/unitrade/seller/notifications'
            )
        if not self._current_seller():
            return request.redirect('/seller-onboarding')

        return self._render_notification_center(
            page=page,
            category=category,
            scope='seller',
            center_url='/unitrade/seller/notifications',
            read_all_url='/unitrade/seller/notifications/read_all',
            title='Notifikasi Penjual',
            empty_message='Aktivitas pesanan, ulasan, pembayaran, refund, dan chat penjual akan muncul di sini.',
        )

    # ------------------------------------------------------------------
    # 11.2 Unread count + recent JSON endpoints (added in task 11.2)
    # ------------------------------------------------------------------
    def _unread_count_for_scope(self, scope):
        user = request.env.user
        if user._is_public():
            return 0
        Notification = request.env['unitrade.notification'].sudo()
        return Notification.search_count(
            self._notification_base_domain(Notification, user, scope) + [
                ('is_read', '=', False),
            ]
        )

    @http.route('/my/notifications/unread_count', type='json', auth='user')
    def unread_count(self, **kwargs):
        """Return the unread notification count for the current user.

        Designed for the OWL bell's 60-second polling loop (Req 4.6).
        Always returns a dict so the JS-RPC unwrap of ``data.result`` has
        a stable shape; on the rare path where the user is somehow public
        we still return ``{'count': 0}`` rather than 401, since the bell
        component should fail closed.

        The search runs under the user's own identity, so the per-user
        ``unitrade_notification_user_rule`` ir.rule already constrains
        results to ``user_id = self.env.user.id``. The explicit
        ``('user_id', '=', user.id)`` clause is defense-in-depth and
        keeps the SQL plan tight via the
        ``unitrade_notif_user_isread_idx`` composite index (Req 9.1).
        """
        user = request.env.user
        if user._is_public():
            return {'count': 0}
        count = self._unread_count_for_scope('user')
        _logger.debug(
            "unread_count: user_id=%s count=%s",
            user.id, count,
        )
        return {'count': count}

    @http.route('/unitrade/seller/notifications/unread_count', type='json', auth='user')
    def seller_unread_count(self, **kwargs):
        user = request.env.user
        if user._is_public() or not self._current_seller():
            return {'count': 0}
        count = self._unread_count_for_scope('seller')
        _logger.debug(
            "seller_unread_count: user_id=%s count=%s",
            user.id, count,
        )
        return {'count': count}

    def _recent_for_scope(self, scope):
        user = request.env.user
        if user._is_public():
            return []
        Notification = request.env['unitrade.notification'].sudo()
        records = Notification.search(
            self._notification_base_domain(Notification, user, scope),
            order='create_date desc, id desc',
            limit=5,
        )
        return [
            {
                'id': r.id,
                'title': r.title or '',
                'message': r.message or '',
                'action_url': r._get_effective_action_url(),
                'is_read': bool(r.is_read),
                'create_date': (
                    fields.Datetime.to_string(r.create_date)
                    if r.create_date else False
                ),
                'category': r.category or '',
            }
            for r in records
        ]

    @http.route('/my/notifications/recent', type='json', auth='user')
    def recent(self, **kwargs):
        """Return the 5 most recent notifications for the current user.

        Used by the bell dropdown's lazy-load on open (Req 4.4). Date is
        serialized via ``fields.Datetime.to_string`` so JSON consumers
        (OWL component + tests) get an ISO-friendly string.

        Same defense-in-depth rationale as :meth:`unread_count`: the
        explicit ``user_id`` clause complements the ir.rule and lets
        Postgres use the user-scoped composite index.
        """
        user = request.env.user
        if user._is_public():
            return []
        payload = self._recent_for_scope('user')
        _logger.debug(
            "recent: user_id=%s returned=%s",
            user.id, len(payload),
        )
        return payload

    @http.route('/unitrade/seller/notifications/recent', type='json', auth='user')
    def seller_recent(self, **kwargs):
        user = request.env.user
        if user._is_public() or not self._current_seller():
            return []
        payload = self._recent_for_scope('seller')
        _logger.debug(
            "seller_recent: user_id=%s returned=%s",
            user.id, len(payload),
        )
        return payload

    # ------------------------------------------------------------------
    # 11.3 Mark-read / mark-all / delete JSON endpoints (added in task 11.3)
    # ------------------------------------------------------------------
    def _fetch_owned(self, nid):
        """Browse a notification record and enforce ownership.

        Returns the recordset on success. Raises ``werkzeug.exceptions.NotFound``
        when the record does not exist, and ``werkzeug.exceptions.Forbidden``
        when the record belongs to a different user (and the current user is
        not in the admin group).

        We ``sudo()`` the browse so the lookup itself is not silently filtered
        by the per-user ``ir.rule``; the explicit ownership comparison below
        is what enforces access. Admins (``unitrade_seller.group_unitrade_admin``
        or ``base.group_system``) are allowed to operate on any record so the
        admin retry view (task 14.1) can reuse these endpoints if needed.
        """
        user = request.env.user
        record = request.env['unitrade.notification'].sudo().browse(nid).exists()
        if not record:
            raise NotFound()
        is_admin = (
            user.has_group('unitrade_seller.group_unitrade_admin')
            or user.has_group('base.group_system')
        )
        if record.user_id.id != user.id and not is_admin:
            _logger.warning(
                "Forbidden notification access attempt: nid=%s by user_id=%s",
                nid, user.id,
            )
            raise Forbidden()
        return record

    @http.route('/my/notifications/<int:nid>/read', type='json', auth='user')
    def mark_read(self, nid, **kwargs):
        """Mark a single notification as read after ownership check.

        Returns ``{'ok': True}`` on success. Errors propagate as standard
        werkzeug exceptions (404 unknown id, 403 ownership mismatch) which
        Odoo's JSON-RPC layer serializes for the OWL bell client.
        """
        record = self._fetch_owned(nid)
        record.action_mark_read()
        _logger.debug(
            "/my/notifications/%s/read user_id=%s",
            nid, request.env.user.id,
        )
        return {'ok': True}

    @http.route('/my/notifications/read_all', type='json', auth='user')
    def mark_all_read(self, **kwargs):
        """Mark every unread notification of the current user as read.

        Delegates to ``unitrade.notification.mark_all_as_read`` (Req 3.4)
        which is idempotent — a second call writes nothing and still
        succeeds. Returns ``{'ok': True, 'updated': <int>}`` so callers
        can refresh badge state without an extra round-trip.
        """
        user = request.env.user
        if user._is_public():
            return {'ok': False, 'updated': 0}
        updated = request.env['unitrade.notification'].mark_all_as_read(
            user.id,
            recipient_scope='user',
        )
        _logger.debug(
            "/my/notifications/read_all user_id=%s updated=%s",
            user.id, updated,
        )
        return {'ok': True, 'updated': updated}

    @http.route('/unitrade/seller/notifications/read_all', type='json', auth='user')
    def seller_mark_all_read(self, **kwargs):
        user = request.env.user
        if user._is_public() or not self._current_seller():
            return {'ok': False, 'updated': 0}
        updated = request.env['unitrade.notification'].mark_all_as_read(
            user.id,
            recipient_scope='seller',
        )
        _logger.debug(
            "/unitrade/seller/notifications/read_all user_id=%s updated=%s",
            user.id, updated,
        )
        return {'ok': True, 'updated': updated}

    @http.route('/my/notifications/<int:nid>/delete', type='json', auth='user')
    def delete_notification(self, nid, **kwargs):
        """Delete a single notification after ownership check (Req 3.5, 3.6)."""
        record = self._fetch_owned(nid)
        record.unlink()
        _logger.debug(
            "/my/notifications/%s/delete user_id=%s",
            nid, request.env.user.id,
        )
        return {'ok': True}

    # ------------------------------------------------------------------
    # 11.4 Notification settings page (added in task 11.4)
    # ------------------------------------------------------------------
    @http.route(
        '/my/notifications/settings',
        type='http',
        auth='user',
        website=True,
        methods=['GET', 'POST'],
        csrf=True,
    )
    def notification_settings(self, **kwargs):
        """Render and persist the user's notification preferences.

        GET behaviour (Req 2.2):
            * Triggers ``_ensure_default_preferences(user.id)`` so the
              grid is fully populated even on first visit.
            * Builds a ``preferences_grid`` matching the contract of
              ``unitrade_notification.notification_settings_page``: one
              row per (category, [in_app, email]) pair derived from the
              event registry, with ``in_app_locked`` set for critical
              categories.
            * Surfaces the ``saved=1`` query flag so the success flash
              banner appears after a redirect from POST.

        POST behaviour (Req 2.3):
            * Form fields are keyed ``pref_<id>_id`` (hidden, the source
              of truth for "which preferences are in scope") and
              ``pref_<id>_enabled`` (checkbox; absent when unchecked).
              Disabled checkboxes for critical-category in_app rows
              cannot be submitted by browsers, so the template emits a
              hidden ``pref_<id>_enabled=1`` companion that we accept
              as the canonical value.
            * We constrain the search to ``user_id = self``, so a forged
              request that lists preference ids belonging to other
              users cannot toggle them.
            * After persistence we redirect to ``?saved=1`` (PRG) so a
              browser refresh does not resubmit the form.
        """
        user = request.env.user
        if user._is_public():
            return request.redirect(
                '/web/login?redirect=/my/notifications/settings'
            )

        Pref = request.env['unitrade.notification.preference'].sudo()

        if request.httprequest.method == 'POST':
            # Hidden ``pref_<id>_id`` companions define the scope. We
            # parse them out of request.params so a malformed key (e.g.
            # ``pref_abc_id``) is silently skipped instead of 500ing.
            scope_ids = set()
            for key in request.params.keys():
                if key.startswith('pref_') and key.endswith('_id'):
                    try:
                        pref_id = int(key[len('pref_'):-len('_id')])
                    except ValueError:
                        continue
                    scope_ids.add(pref_id)

            updated = 0
            if scope_ids:
                preferences = Pref.search([
                    ('id', 'in', list(scope_ids)),
                    ('user_id', '=', user.id),
                ])
                for pref in preferences:
                    enabled_key = 'pref_%s_enabled' % pref.id
                    pref.write({'enabled': enabled_key in request.params})
                updated = len(preferences)

            _logger.info(
                "notification_settings POST user_id=%s updated=%s",
                user.id, updated,
            )
            return request.redirect('/my/notifications/settings?saved=1')

        # ---------------- GET path ----------------
        Pref._ensure_default_preferences(user.id)

        # Reload after ensuring defaults so the grid sees freshly seeded
        # rows. Sudo is fine here: we explicitly filter by ``user.id``.
        user_prefs = Pref.search([('user_id', '=', user.id)])
        by_pair = {(p.category, p.channel): p for p in user_prefs}

        category_labels = dict(
            request.env['unitrade.notification']._fields['category'].selection
        )

        preferences_grid = []
        for category in iter_categories():
            channels = list(iter_channels_for(category))
            preferences_grid.append({
                'category': category,
                'category_label': category_labels.get(category, category),
                'in_app': (
                    by_pair.get((category, 'in_app'))
                    if 'in_app' in channels else None
                ),
                'email': (
                    by_pair.get((category, 'email'))
                    if 'email' in channels else None
                ),
                'in_app_locked': category in CRITICAL_CATEGORIES,
            })

        values = {
            'preferences_grid': preferences_grid,
            'saved': bool(kwargs.get('saved')),
        }
        return request.render(
            'unitrade_notification.notification_settings_page', values,
        )
