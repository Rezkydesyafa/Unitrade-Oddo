import copy
import hashlib
import logging
import re
import traceback
from datetime import timedelta
from urllib.parse import urlparse

from psycopg2 import IntegrityError

from odoo import _, api, fields, models, tools

from .event_registry import CRITICAL_CATEGORIES, EVENT_REGISTRY

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Backward-compatibility map: new ``category`` -> legacy ``notification_type``
# ---------------------------------------------------------------------------
#
# The legacy ``notification_type`` column predates the 7-category
# taxonomy and is preserved so existing views, reports, and integrations
# (e.g. ``views/template.xml`` in earlier modules) keep working. The
# table mirrors the design document (§unitrade.notification – extended):
#
#   order   -> order        payment -> payment       chat    -> chat
#   system  -> system       account -> system        seller  -> system
#   review  -> system
#
# Whenever the caller provides an explicit ``notification_type`` it wins
# (caller-preserved) so admin/data XML can pin a specific legacy type.
_CATEGORY_TO_LEGACY_TYPE = {
    'order': 'order',
    'payment': 'payment',
    'chat': 'chat',
    'system': 'system',
    'account': 'system',
    'seller': 'system',
    'review': 'system',
}

_SELLER_ONLY_EVENT_CODES = frozenset({
    'order.new_for_seller',
    'review.new_for_seller',
})


# ---------------------------------------------------------------------------
# Default Indonesian title/message per event_code.
# ---------------------------------------------------------------------------
#
# These provide sensible defaults rendered by ``_render_title_and_message``
# when the caller does not supply ``payload['title_override']`` /
# ``payload['message_override']``. Strings are intentionally short so they
# fit the navbar dropdown and the mobile notification center; richer copy
# (resi number, rejection reason, etc.) is meant to be passed by the caller
# as an override.
#
# All event codes registered in :mod:`event_registry` are covered.
_DEFAULT_TITLES = {
    'account.welcome': 'Selamat datang di UniTrade!',
    'account.password_reset': 'Password berhasil direset',
    'seller.application_received': 'Pengajuan seller diterima',
    'seller.approved': 'Pengajuan seller disetujui',
    'seller.rejected': 'Pengajuan seller belum disetujui',
    'order.new_for_seller': 'Pesanan baru',
    'order.confirmed': 'Pesanan dikonfirmasi',
    'order.shipped': 'Pesanan dikirim',
    'order.delivered': 'Pesanan diterima',
    'order.cancelled': 'Pesanan dibatalkan',
    'payment.success': 'Pembayaran berhasil',
    'payment.pending': 'Pembayaran menunggu',
    'payment.failed': 'Pembayaran gagal',
    'payment.expired': 'Pembayaran kedaluwarsa',
    'chat.new_message': 'Pesan baru',
    'review.reminder': 'Beri review pesananmu',
    'review.new_for_seller': 'Review baru',
    'system.announcement': 'Pengumuman UniTrade',
    'system.customer_ticket_reply': 'Balasan Customer Service',
    'system.customer_ticket_status': 'Status tiket bantuan berubah',
}

_DEFAULT_MESSAGES = {
    'account.welcome': 'Akun kamu sudah aktif.',
    'account.password_reset': 'Password kamu telah diperbarui.',
    'seller.application_received': 'Tim akan review dalam 1×24 jam.',
    'seller.approved': 'Selamat, kamu sekarang seller terverifikasi.',
    'seller.rejected': 'Lihat detail untuk pengajuan ulang.',
    'order.new_for_seller': 'Ada pesanan baru menunggu konfirmasi.',
    'order.confirmed': 'Pesanan kamu sudah dikonfirmasi.',
    'order.shipped': 'Pesanan kamu sedang dalam pengiriman.',
    'order.delivered': 'Pesanan sudah sampai tujuan.',
    'order.cancelled': 'Pesanan kamu telah dibatalkan.',
    'payment.success': 'Pembayaran sudah kami terima.',
    'payment.pending': 'Selesaikan pembayaran sebelum batas waktu.',
    'payment.failed': 'Silakan coba metode pembayaran lain.',
    'payment.expired': 'Batas waktu pembayaran sudah lewat.',
    'chat.new_message': 'Kamu mendapat pesan baru.',
    'review.reminder': 'Bantu seller dengan ulasan kamu.',
    'review.new_for_seller': 'Pelanggan memberikan review baru.',
    'system.announcement': 'Ada pengumuman baru dari tim UniTrade.',
    'system.customer_ticket_reply': 'Customer Service membalas tiket bantuan kamu.',
    'system.customer_ticket_status': 'Lihat detail tiket untuk informasi terbaru.',
}


# ---------------------------------------------------------------------------
# Sensitive payload keys stripped before rendering / persistence.
# ---------------------------------------------------------------------------
#
# Matched case-insensitively on the *exact* lowercased dict key — this is
# more predictable than a substring match (which would also strip benign
# fields such as ``user_password_hint``). Common variants and synonyms
# are listed explicitly so callers don't have to remember an exhaustive
# blocklist.
_SENSITIVE_KEYS = frozenset({
    'password',
    'password_hash',
    'password_reset_token',
    'api_key',
    'midtrans_server_key',
    'secret',
    'private_key',
    'token',
    'authorization',
    'cookie',
    'session_id',
    'csrf_token',
})


class UnitradeNotification(models.Model):
    _name = 'unitrade.notification'
    _description = 'UniTrade System Notification'
    # Unread first for admin/user inboxes; ``id desc`` is the deterministic
    # tie-breaker used by list query invariants.
    _order = 'is_read asc, create_date desc, id desc'

    # ------------------------------------------------------------------
    # Identity / addressing
    # ------------------------------------------------------------------
    user_id = fields.Many2one(
        'res.users',
        string='User',
        required=True,
        ondelete='cascade',
        index=True,
    )
    audience = fields.Selection(
        [
            ('user', 'User'),
            ('admin', 'Admin'),
        ],
        string='Audience',
        required=True,
        default='user',
        index=True,
    )
    recipient_scope = fields.Selection(
        [
            ('user', 'User'),
            ('seller', 'Seller'),
        ],
        string='Scope Penerima',
        compute='_compute_recipient_scope',
        store=True,
        default='user',
        index=True,
        help="Separates buyer/user notifications from seller-dashboard "
             "notifications for the same res.users account.",
    )
    title = fields.Char(string='Judul', required=True)
    message = fields.Text(string='Pesan')

    # ------------------------------------------------------------------
    # Taxonomy
    # ------------------------------------------------------------------
    category = fields.Selection(
        [
            ('account', 'Akun'),
            ('seller', 'Seller'),
            ('order', 'Pesanan'),
            ('payment', 'Pembayaran'),
            ('chat', 'Chat'),
            ('review', 'Review'),
            ('system', 'Sistem'),
        ],
        string='Kategori',
        required=True,
        index=True,
    )
    event_code = fields.Char(
        string='Kode Event',
        required=True,
        index=True,
        help="Stable identifier of the originating event "
             "(e.g. 'order.confirmed'). Must exist in EVENT_REGISTRY.",
    )

    # Legacy 5-value column. Populated automatically from ``category``
    # via the ``create`` override below, but callers may still pass an
    # explicit value (used by existing data XML and earlier callers).
    notification_type = fields.Selection(
        [
            ('order', 'Pesanan'),
            ('payment', 'Pembayaran'),
            ('delivery', 'Pengiriman'),
            ('chat', 'Chat'),
            ('moderation', 'Moderasi'),
            ('refund', 'Refund'),
            ('payout', 'Payout'),
            ('system', 'Sistem'),
        ],
        string='Tipe (legacy)',
        default='system',
        help="Backward-compatible coarse type derived from `category`.",
    )
    priority = fields.Selection(
        [
            ('info', 'Info'),
            ('warning', 'Warning'),
            ('urgent', 'Urgent'),
            ('critical', 'Critical'),
        ],
        string='Prioritas',
        default='info',
        index=True,
    )

    # ------------------------------------------------------------------
    # Reference to the originating business object
    # ------------------------------------------------------------------
    reference_model = fields.Char(string='Model Referensi')
    reference_id = fields.Integer(string='ID Referensi')
    action_url = fields.Char(
        string='Action URL',
        help="Optional URL the bell/center will redirect the user to "
             "when the notification is clicked. Validated by the "
             "dispatcher against the configured allow-list.",
    )
    target_model = fields.Char(string='Target Model', index=True)
    target_id = fields.Integer(string='Target ID', index=True)
    target_url = fields.Char(string='Target URL')
    action_xmlid = fields.Char(string='Action XMLID')
    dedupe_key = fields.Char(string='Dedupe Key', copy=False, index=True)

    # ------------------------------------------------------------------
    # Read state
    # ------------------------------------------------------------------
    is_read = fields.Boolean(
        string='Sudah Dibaca',
        default=False,
        index=True,
    )
    read_at = fields.Datetime(string='Dibaca pada', copy=False)
    read_by_id = fields.Many2one(
        'res.users',
        string='Dibaca Oleh',
        readonly=True,
        copy=False,
    )

    # ------------------------------------------------------------------
    # Idempotency
    # ------------------------------------------------------------------
    idempotency_key = fields.Char(
        string='Idempotency Key',
        index=True,
        help="Deterministic key derived from "
             "(event_code, reference_model, reference_id, discriminator). "
             "Combined with `user_id` it forms a UNIQUE constraint that "
             "prevents duplicate emissions on retries / webhook replay.",
    )

    # ------------------------------------------------------------------
    # Email lifecycle
    # ------------------------------------------------------------------
    email_state = fields.Selection(
        [
            ('not_applicable', 'Not Applicable'),
            ('pending', 'Pending'),
            ('sent', 'Sent'),
            ('failed', 'Failed'),
        ],
        string='Status Email',
        default='not_applicable',
    )
    email_error = fields.Text(string='Error Email')
    mail_message_id = fields.Many2one(
        'mail.mail',
        string='Antrean Email',
        ondelete='set null',
        help="Reference to the queued mail.mail record (set after the "
             "dispatcher hands the message off to Odoo's mail worker).",
    )

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------
    _sql_constraints = [
        (
            'uniq_user_idempotency',
            'UNIQUE(user_id, idempotency_key)',
            'Notifikasi duplikat untuk user yang sama tidak diperbolehkan.',
        ),
        (
            'unitrade_notification_dedupe_unique',
            'UNIQUE(user_id, audience, dedupe_key)',
            'Notifikasi dengan dedupe key yang sama sudah ada untuk user ini.',
        ),
    ]

    # ------------------------------------------------------------------
    # Composite indexes
    # ------------------------------------------------------------------
    def init(self):
        """Create composite indexes that single-column ``index=True``
        cannot express.

        * ``unitrade_notif_user_isread_idx`` accelerates the unread
          counter query (``user_id``, ``is_read``) used by the bell
          polling endpoint (Req 9.3).
        * ``unitrade_notif_user_cat_date_idx`` accelerates the
          notification center filter+sort query
          (``user_id``, ``category``, ``create_date``) (Req 9.2).
        """
        tools.create_index(
            self._cr,
            'unitrade_notif_user_isread_idx',
            self._table,
            ['user_id', 'is_read'],
        )
        tools.create_index(
            self._cr,
            'unitrade_notif_user_cat_date_idx',
            self._table,
            ['user_id', 'category', 'create_date'],
        )

    # ------------------------------------------------------------------
    # Scope resolution
    # ------------------------------------------------------------------
    @api.depends(
        'audience',
        'user_id',
        'event_code',
        'reference_model',
        'reference_id',
        'action_url',
        'target_model',
        'target_id',
        'target_url',
    )
    def _compute_recipient_scope(self):
        for record in self:
            record.recipient_scope = (
                'seller' if record._is_seller_scoped_notification() else 'user'
            )

    @api.model
    def _notification_scope_domain(self, scope='user'):
        scope = 'seller' if scope == 'seller' else 'user'
        return [
            ('audience', '=', 'user'),
            ('recipient_scope', '=', scope),
        ]

    def _is_seller_scoped_notification(self):
        """Return true when this user notification belongs in seller UI."""
        self.ensure_one()
        if self.audience != 'user':
            return False
        if self.event_code in _SELLER_ONLY_EVENT_CODES:
            return True
        if (
            self._is_seller_url(self.action_url)
            or self._is_seller_url(self.target_url)
        ):
            return True

        reference_model = self.reference_model or self.target_model
        reference_id = self.reference_id or self.target_id
        if not reference_model or not reference_id:
            return False

        try:
            record = self.env[reference_model].sudo().browse(reference_id).exists()
        except KeyError:
            return False
        if not record:
            return False

        if reference_model == 'sale.order':
            return self._is_recipient_seller_for_order(record)
        if reference_model == 'unitrade.dispute':
            seller_user = record.seller_id.user_id if record.seller_id else False
            return bool(seller_user and seller_user.id == self.user_id.id)
        if reference_model == 'unitrade.chat.conversation':
            seller_user = (
                record.seller_user_id
                if hasattr(record, 'seller_user_id') else False
            )
            return bool(seller_user and seller_user.id == self.user_id.id)
        if reference_model == 'unitrade.review':
            return self._product_belongs_to_recipient_seller(record.product_id)
        if reference_model == 'product.template':
            return self._product_belongs_to_recipient_seller(record)
        if reference_model == 'product.product':
            return self._product_belongs_to_recipient_seller(record.product_tmpl_id)
        return False

    @staticmethod
    def _is_seller_url(url):
        return bool((url or '').strip().startswith('/unitrade/seller/'))

    def _product_belongs_to_recipient_seller(self, product):
        self.ensure_one()
        if not product:
            return False
        product = product.sudo().exists()
        if not product or not self.user_id:
            return False
        seller_user = (
            product.x_seller_user_id
            if 'x_seller_user_id' in product._fields else False
        )
        if seller_user and seller_user.id:
            return seller_user.id == self.user_id.id
        seller = product.x_seller_id if 'x_seller_id' in product._fields else False
        return bool(
            seller
            and seller.user_id
            and seller.user_id.id == self.user_id.id
        )

    # ------------------------------------------------------------------
    # ORM overrides
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        """Auto-populate the legacy ``notification_type`` from the new
        ``category`` whenever the caller did not pin one explicitly.

        Caller-supplied ``notification_type`` values are preserved
        verbatim so existing data XML and pre-existing callers keep
        their original behaviour (Req 1.7 / Property 2).
        """
        for vals in vals_list:
            if vals.get('target_model') and not vals.get('reference_model'):
                vals['reference_model'] = vals['target_model']
            if vals.get('target_id') and not vals.get('reference_id'):
                vals['reference_id'] = vals['target_id']
            if vals.get('target_url') and not vals.get('action_url'):
                vals['action_url'] = vals['target_url']
            if vals.get('dedupe_key') and not vals.get('idempotency_key'):
                vals['idempotency_key'] = vals['dedupe_key']
            vals.setdefault('category', 'system')
            vals.setdefault('event_code', 'system.announcement')
            # Only auto-fill when the caller did not provide a value at
            # all. ``False`` / empty string is treated as "not provided"
            # because Odoo sometimes serialises missing Selection values
            # that way.
            explicit_type = vals.get('notification_type')
            if explicit_type:
                continue
            category = vals.get('category')
            mapped = _CATEGORY_TO_LEGACY_TYPE.get(category)
            if mapped:
                vals['notification_type'] = mapped
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        if vals.get('target_model') and not vals.get('reference_model'):
            vals['reference_model'] = vals['target_model']
        if vals.get('target_id') and not vals.get('reference_id'):
            vals['reference_id'] = vals['target_id']
        if vals.get('target_url') and not vals.get('action_url'):
            vals['action_url'] = vals['target_url']
        if vals.get('dedupe_key') and not vals.get('idempotency_key'):
            vals['idempotency_key'] = vals['dedupe_key']
        return super().write(vals)

    # ------------------------------------------------------------------
    # User-facing actions
    # ------------------------------------------------------------------
    def action_mark_read(self):
        """Mark the current recordset as read.

        Only records whose ``is_read`` is currently ``False`` are
        updated, and ``read_at`` is set to ``now()`` on the first
        transition (Property 6 — Mark-as-Read Invariants). Records that
        are already read are left untouched so subsequent invocations
        do not overwrite their original ``read_at`` timestamp, keeping
        the operation idempotent in time as well as in state.
        """
        unread = self.filtered(lambda r: not r.is_read)
        if unread:
            unread.write({
                'is_read': True,
                'read_at': fields.Datetime.now(),
                'read_by_id': self.env.user.id,
            })

    # ------------------------------------------------------------------
    # Dispatcher helpers (task 6.1)
    # ------------------------------------------------------------------
    #
    # The helpers below are pure utility methods consumed by ``emit``
    # (implemented in task 7.1). They are exposed on the model so they
    # can be unit-tested in isolation, monkey-patched in fixtures, and
    # referenced from QWeb / mail.template expressions where useful
    # (e.g. ``${object._get_email_from()}``).

    @api.model
    def _build_idempotency_key(self, event_code, payload, discriminator=None):
        """Compute the deterministic idempotency key for an emission.

        The key is a SHA-1 hex digest over the pipe-joined parts:
        ``event_code | reference_model | reference_id | discriminator``.

        Combined with ``user_id`` it forms the unique constraint
        ``uniq_user_idempotency`` and makes ``emit()`` safe to retry
        (Req 1.4 / Property 1).

        :param str event_code: Stable event identifier.
        :param dict|None payload: Caller payload; ``reference_model``
            and ``reference_id`` are read from it when present.
        :param str|None discriminator: Optional extra discriminator
            (e.g. a 10-minute window bucket for chat grouping).
        :returns: 40-character hex digest.
        :rtype: str
        """
        safe_payload = payload or {}
        parts = [
            str(event_code or ''),
            str(safe_payload.get('reference_model') or ''),
            str(safe_payload.get('reference_id') or ''),
            str(discriminator or ''),
        ]
        key_input = '|'.join(parts)
        return hashlib.sha1(key_input.encode('utf-8')).hexdigest()

    @api.model
    def _validate_action_url(self, url):
        """Sanitise an ``action_url`` against the configured allow-list.

        Rules (Req 7.4):

        * Empty / falsy → returns ``False`` silently (the field is
          simply left unset, no warning is logged).
        * Relative path starting with ``/`` → returned unchanged. This
          is the common case for in-platform redirects such as
          ``/my/orders/42``.
        * ``javascript:`` scheme (case-insensitive) → returns ``False``
          with a warning. Defends against accidentally crafted XSS-ish
          URLs in payload data.
        * Any other URL must use the ``https`` scheme **and** match an
          entry in ``unitrade.notification.allowed_url_prefixes``.
          Allow-list entries are comma-separated and may be either:

          - a path prefix starting with ``/`` (matches when the URL
            itself begins with that prefix; useful when the parameter
            still holds the bootstrap default ``'/'``)
          - a hostname (matches when the URL's ``netloc`` equals the
            entry verbatim)

        Disallowed values are returned as ``False``; the dispatcher
        keeps the rest of the record but logs a warning so admins can
        notice misconfigured callers.

        :param url: Value to validate (anything truthy is coerced to
            ``str`` before parsing).
        :returns: The original URL when accepted, ``False`` otherwise.
        """
        if not url:
            return False

        url_str = str(url)

        # Relative path — always allowed (in-platform redirect).
        if url_str.startswith('/'):
            return url_str

        # javascript: pseudo-scheme — never allowed.
        # ``startswith`` with the lowered prefix catches odd-cased
        # variants like ``JavaScript:``.
        if url_str.lower().startswith('javascript:'):
            _logger.warning(
                "Notification action_url rejected (javascript: scheme): %r",
                url_str,
            )
            return False

        # Anything else must be parseable and use https.
        try:
            parsed = urlparse(url_str)
        except ValueError:
            _logger.warning(
                "Notification action_url rejected (malformed): %r", url_str,
            )
            return False

        if parsed.scheme != 'https' or not parsed.netloc:
            _logger.warning(
                "Notification action_url rejected (non-https or malformed): %r",
                url_str,
            )
            return False

        # Resolve the configured allow-list. ``sudo`` is required because
        # ``ir.config_parameter`` is admin-only; this method is invoked
        # from the dispatcher which already runs in trusted context.
        raw = self.env['ir.config_parameter'].sudo().get_param(
            'unitrade.notification.allowed_url_prefixes', default='/'
        ) or ''
        entries = [e.strip() for e in raw.split(',') if e.strip()]

        netloc = parsed.netloc
        for entry in entries:
            if entry.startswith('/'):
                # Path-prefix entry — only matches relative URLs, which
                # were already accepted above. Skip for absolute URLs.
                continue
            if entry == netloc:
                return url_str

        _logger.warning(
            "Notification action_url rejected (host %r not in allow-list): %r",
            netloc, url_str,
        )
        return False

    def _get_email_from(self):
        """Resolve the ``email_from`` address for outgoing notifications.

        Reads ``ir.config_parameter`` ``unitrade.notification.email_from``
        first (Req 6.5 / 8.1); falls back to ``self.env.company.email``.
        Returns the resolved string or ``False`` if neither is set —
        callers / mail templates are expected to handle a missing value
        gracefully.

        Implemented as an instance method so it can be invoked from
        QWeb mail.template expressions via ``${object._get_email_from()}``
        without requiring ``@api.model`` decoration.
        """
        param = self.env['ir.config_parameter'].sudo().get_param(
            'unitrade.notification.email_from'
        )
        if param:
            return param
        return self.env.company.email or False

    def _get_effective_action_url(self):
        """Return the best click target for this notification.

        Prefer a route derived from the referenced business record so older
        notifications with legacy URLs keep navigating to the current
        UniTrade pages. Stored ``action_url`` is still respected when no
        stronger project-specific target can be derived.
        """
        self.ensure_one()
        if self._is_buyer_review_reminder():
            return self._review_orders_action_url()

        resolved_url = self._resolve_reference_action_url()
        if resolved_url:
            return resolved_url

        review_url = self._normalize_review_product_action_url(self.action_url)
        if review_url:
            return review_url

        legacy_url = self._normalize_legacy_action_url(self.action_url)
        if legacy_url:
            return legacy_url

        if self._is_notification_center_url(self.action_url):
            return self._default_category_action_url()

        if self.action_url:
            return self.action_url

        return self._default_category_action_url()

    def _resolve_reference_action_url(self):
        """Resolve a notification target from ``reference_model``/``id``."""
        self.ensure_one()
        reference_model = self.reference_model or self.target_model
        reference_id = self.reference_id or self.target_id
        if not reference_model or not reference_id:
            return False

        try:
            Model = self.env[reference_model].sudo()
        except KeyError:
            return False

        record = Model.browse(reference_id).exists()
        if not record:
            return False

        if reference_model == 'sale.order':
            if self.category == 'review':
                return self._resolve_review_product_action_url()
            return self._resolve_order_action_url(record)

        if reference_model == 'unitrade.dispute':
            return self._resolve_refund_action_url(record)

        if reference_model == 'unitrade.chat.conversation':
            return self._resolve_chat_action_url(record)

        if reference_model in (
            'unitrade.review',
            'product.template',
            'product.product',
        ):
            return self._resolve_review_product_action_url()

        if reference_model == 'unitrade.seller':
            if self.event_code == 'seller.approved':
                return '/unitrade/seller/dashboard'
            return '/seller-onboarding'

        return False

    def _resolve_order_action_url(self, order):
        """Return buyer/seller order page for the notification recipient."""
        self.ensure_one()
        if not order:
            return False
        if self._is_recipient_seller_for_order(order):
            return '/unitrade/seller/orders/%s' % order.id
        return '/unitrade/order/status/%s' % order.id

    def _is_recipient_seller_for_order(self, order):
        self.ensure_one()
        if not order or not self.user_id:
            return False
        try:
            if hasattr(order, '_unitrade_seller_user_ids'):
                return self.user_id.id in order._unitrade_seller_user_ids()
        except Exception:
            _logger.debug(
                "Failed to resolve seller recipient for order notification %s",
                self.id,
                exc_info=True,
            )
        for line in order.order_line:
            product = line.product_id
            tmpl = product.product_tmpl_id if product else False
            seller = getattr(tmpl, 'x_seller_id', False) if tmpl else False
            if seller and seller.user_id and seller.user_id.id == self.user_id.id:
                return True
        return False

    def _resolve_refund_action_url(self, dispute):
        """Return buyer/seller refund status page for the recipient."""
        self.ensure_one()
        if not dispute:
            return False
        seller_user = dispute.seller_id.user_id if dispute.seller_id else False
        if seller_user and seller_user.id == self.user_id.id:
            return '/unitrade/seller/refunds/%s' % dispute.id
        if dispute.order_id:
            return '/unitrade/order/%s/refund/%s' % (
                dispute.order_id.id,
                dispute.id,
            )
        return False

    def _resolve_chat_action_url(self, conversation):
        """Return the buyer or seller chat page for the recipient."""
        self.ensure_one()
        if not conversation:
            return False
        if (
            conversation.seller_user_id
            and conversation.seller_user_id.id == self.user_id.id
        ):
            return '/unitrade/seller/chat?conversation_id=%s' % conversation.id
        return '/unitrade/chat?conversation_id=%s' % conversation.id

    def _normalize_legacy_action_url(self, url):
        """Map older notification URLs to current project routes."""
        self.ensure_one()
        url = (url or '').strip()
        if not url:
            return False

        match = re.match(r'^/my/orders/(\d+)(?:[/?#].*)?$', url)
        if match:
            order = self.env['sale.order'].sudo().browse(int(match.group(1))).exists()
            if order:
                return self._resolve_order_action_url(order)
            return '/unitrade/order/status/%s' % match.group(1)

        match = re.match(r'^/(?:my/)?seller/orders/(\d+)(?:[/?#].*)?$', url)
        if match:
            return '/unitrade/seller/orders/%s' % match.group(1)

        match = re.match(r'^/(?:my/)?seller/refunds/(\d+)(?:[/?#].*)?$', url)
        if match:
            return '/unitrade/seller/refunds/%s' % match.group(1)

        return False

    def _is_notification_center_url(self, url):
        """Return true when a stored URL only points back to the inbox."""
        self.ensure_one()
        url = (url or '').strip()
        if not url:
            return False
        parsed = urlparse(url)
        return (parsed.path or url) == '/my/notifications'

    def _normalize_review_product_action_url(self, url):
        """Map stored review product URLs to a clickable product detail."""
        self.ensure_one()
        if self.category != 'review':
            return False

        parsed = urlparse((url or '').strip())
        path = parsed.path or (url or '').strip()
        match = re.match(r'^/unitrade/product/(\d+)(?:[/?#].*)?$', path)
        if not match:
            return False

        product = self.env['product.template'].sudo().browse(
            int(match.group(1))
        ).exists()
        if not product:
            return False

        product = self._review_public_product(product)
        if product and product.exists():
            return self._review_product_action_url(product)
        return False

    def _default_category_action_url(self):
        """Fallback target when a notification has no usable reference."""
        self.ensure_one()
        if self.category == 'account':
            return '/my/account'
        if self.category == 'seller':
            return (
                '/unitrade/seller/dashboard'
                if self.event_code == 'seller.approved'
                else '/seller-onboarding'
            )
        if self.category == 'order':
            return '/my/orders'
        if self.category == 'payment':
            return '/my/orders?status=unpaid'
        if self.category == 'chat':
            return '/unitrade/chat'
        if self.category == 'review':
            return self._review_orders_action_url()
        return '/my/notifications'

    def _resolve_review_product_action_url(self):
        """Resolve ``/unitrade/product/<id>`` for review notifications."""
        self.ensure_one()
        reference_model = self.reference_model or self.target_model
        reference_id = self.reference_id or self.target_id
        if (
            self.category != 'review'
            or not reference_model
            or not reference_id
        ):
            return False

        try:
            Model = self.env[reference_model].sudo()
        except KeyError:
            return False

        record = Model.browse(reference_id).exists()
        if not record:
            return False

        product = self.env['product.template'].sudo().browse()
        if reference_model == 'unitrade.review':
            product = record.product_id
        elif reference_model == 'product.template':
            product = record
        elif reference_model == 'product.product':
            product = record.product_tmpl_id
        elif reference_model == 'sale.order':
            review = self.env['unitrade.review'].sudo().search([
                ('order_id', '=', record.id),
                ('product_id', '!=', False),
            ], limit=1)
            if review:
                product = review.product_id
            else:
                order_line = record.order_line.filtered(
                    lambda line: (
                        line.product_id and line.product_id.product_tmpl_id
                    )
                )[:1]
                if order_line:
                    product = order_line.product_id.product_tmpl_id

        if product and product.exists():
            product = self._review_public_product(product)
        if product and product.exists():
            return self._review_product_action_url(product)
        return False

    def _is_buyer_review_reminder(self):
        self.ensure_one()
        return self.category == 'review' and (
            self.event_code == 'review.reminder'
            or self.recipient_scope == 'user'
        )

    def _review_orders_action_url(self):
        return '/my/orders?status=done&tab=reviews#tab-ulasan'

    def _review_public_product(self, product):
        """Return a clickable marketplace product for review notifications."""
        product = product.exists()
        if not product:
            return product

        is_available = (
            product._unitrade_is_publicly_available()
            if hasattr(product, '_unitrade_is_publicly_available')
            else bool(product.active and product.sale_ok and product.website_published)
        )
        if is_available:
            return product

        replacement = self.env['product.template'].sudo().search([
            ('id', '!=', product.id),
            ('name', '=', product.name),
            ('active', '=', True),
            ('sale_ok', '=', True),
            ('website_published', '=', True),
        ], order='id desc', limit=1)
        if replacement and hasattr(replacement, '_unitrade_is_publicly_available'):
            return replacement if replacement._unitrade_is_publicly_available() else product
        return replacement or product

    def _review_product_action_url(self, product):
        """Return product detail URL with review tab opened."""
        product.ensure_one()
        return '/unitrade/product/%s?tab=reviews#tab-ulasan' % product.id

    @api.model
    def _render_title_and_message(self, event_code, payload):
        """Compute ``(title, message)`` for an emission.

        The base text comes from :data:`_DEFAULT_TITLES` and
        :data:`_DEFAULT_MESSAGES`; ``payload['title_override']`` and
        ``payload['message_override']`` (when truthy) take precedence so
        callers can customise without re-declaring a registry entry.

        Unknown ``event_code`` values yield empty defaults — the
        dispatcher rejects unknown codes upstream so this branch only
        triggers under direct unit-test usage.

        :returns: 2-tuple ``(title, message)`` of strings.
        """
        safe_payload = payload or {}

        title = safe_payload.get('title_override') \
            or _DEFAULT_TITLES.get(event_code, '')
        message = safe_payload.get('message_override') \
            or _DEFAULT_MESSAGES.get(event_code, '')

        return title, message

    @api.model
    def _scrub_payload(self, payload):
        """Return a deep copy of ``payload`` with sensitive keys removed.

        Sensitive keys (defined in :data:`_SENSITIVE_KEYS`) are matched
        on the lowercased exact key, so ``Authorization``, ``TOKEN``,
        and ``Password`` are all stripped while benign fields like
        ``password_hint`` are kept intact (Req 7.2).

        Recursion walks nested ``dict`` and ``list``/``tuple``
        structures so secrets cannot hide inside embedded payloads
        (e.g. webhook bodies). The original input is *not* mutated.

        :param payload: Arbitrary JSON-serialisable payload (typically
            a dict, but lists / scalars are passed through unchanged
            with the same recursive treatment).
        :returns: A scrubbed deep copy.
        """
        if payload is None:
            return None

        # ``deepcopy`` first so the recursive walk below cannot mutate
        # the caller's data even if the structure contains shared
        # subtrees (a possibility for hand-crafted test payloads).
        cloned = copy.deepcopy(payload)
        return self._scrub_value(cloned)

    @api.model
    def _scrub_value(self, value):
        """Recursive helper for :meth:`_scrub_payload`.

        Walks dicts/lists/tuples in place (the caller has already deep-
        copied the structure). Returns the scrubbed value so the public
        method can use it for non-dict roots too.
        """
        if isinstance(value, dict):
            for key in list(value.keys()):
                # Compare on a string-coerced lowercased key so callers
                # using non-string keys don't crash the scrubber.
                if isinstance(key, str) and key.lower() in _SENSITIVE_KEYS:
                    del value[key]
                    continue
                value[key] = self._scrub_value(value[key])
            return value
        if isinstance(value, list):
            for idx, item in enumerate(value):
                value[idx] = self._scrub_value(item)
            return value
        if isinstance(value, tuple):
            return tuple(self._scrub_value(item) for item in value)
        return value

    # ------------------------------------------------------------------
    # Public dispatcher API (task 7.1)
    # ------------------------------------------------------------------
    @api.model
    def emit(self, user_id, event_code, payload=None, channels=None,
             idempotency_discriminator=None):
        """Emit one notification for one user.

        This is the single public entry point used by all caller modules
        (account / seller / order / payment / chat / review / system) to
        produce a notification. It is *idempotent*: re-emitting the same
        ``(user_id, event_code, reference_model, reference_id,
        discriminator)`` tuple returns the existing record instead of
        creating a duplicate (Req 1.4 / 1.5 / 1.6 / Property 1).

        Steps performed:

        1. Validate ``event_code`` against :data:`EVENT_REGISTRY`. An
           unknown code is rejected with a ``ValueError`` and a
           ``WARNING`` log entry; no row is written (Req 7.3 /
           Property 15).
        2. Scrub the payload of sensitive keys (Req 7.2 / Property 14).
        3. Compute the deterministic idempotency key and search for an
           existing record. If one exists, return it tagged ``duplicate``.
        4. Resolve effective channels: caller override ``channels``
           wins, otherwise we use the registry default. The category is
           always forced from the registry so callers cannot
           accidentally cross-wire it.
        5. For each channel, consult
           :meth:`unitrade.notification.preference.is_enabled`. Critical
           categories override an in_app opt-out (Req 2.5 /
           Property 4); email opt-outs are honoured for every category.
        6. If both channels end up disabled the call is a no-op and we
           log a ``skipped`` outcome.
        7. Render title / message and validate the action_url (Req 7.4 /
           Property 16). A rejected URL becomes ``False`` on the record
           but does not abort the emission.
        8. ``create()`` the record inside a savepoint. A
           ``UNIQUE(user_id, idempotency_key)`` race (pgcode 23505) is
           caught and resolved by re-fetching the winner (Property 1).
        9. Log the outcome at INFO level with ``user_id``,
           ``event_code``, and ``result ∈ {created, skipped, duplicate}``
           (Req 8.3 / Property 17).
        10. When the registry lists the ``'email'`` channel and the
            user has the email preference enabled, hand the freshly
            created record to :meth:`_send_email_via_template` so the
            ``mail.mail`` row is enqueued asynchronously and
            ``email_state`` advances to ``'sent'`` (or ``'failed'``
            with the captured stacktrace).

        :param int user_id: Target ``res.users`` id.
        :param str event_code: Event identifier; must exist in
            :data:`EVENT_REGISTRY`.
        :param dict|None payload: Caller-supplied context. Recognised
            keys: ``reference_model``, ``reference_id``, ``action_url``,
            ``title_override``, ``message_override``.
        :param list[str]|None channels: Optional override of the
            registry channels (subset of ``['in_app', 'email']``).
        :param str|None idempotency_discriminator: Extra discriminator
            appended to the idempotency key (used e.g. by chat grouping).
        :returns: The created, pre-existing, or empty recordset.
        :rtype: :class:`unitrade.notification`
        :raises ValueError: If ``event_code`` is not registered or
            ``user_id`` is missing.
        """
        # 1. Validate event_code -------------------------------------------------
        entry = EVENT_REGISTRY.get(event_code)
        if entry is None:
            _logger.warning(
                "unitrade.notification.emit: unknown event_code=%r "
                "(user_id=%s); rejecting",
                event_code, user_id,
            )
            raise ValueError(
                "Unknown notification event_code: %r" % (event_code,)
            )

        # 2. Validate user -------------------------------------------------------
        if not user_id:
            raise ValueError("emit requires a user_id")

        # 3. Scrub payload once so all downstream consumers see the safe copy.
        safe_payload = self._scrub_payload(payload) if payload else {}
        action_url = self._validate_action_url(safe_payload.get('action_url'))

        # 4. Compute idempotency key --------------------------------------------
        idempotency_key = self._build_idempotency_key(
            event_code, safe_payload, idempotency_discriminator,
        )

        # 5. Optimistic existence check (avoids a savepoint when possible).
        # ``sudo`` because the dispatcher may legitimately emit to other
        # users (e.g. seller notification triggered by a buyer action),
        # and the per-user ir.rule would otherwise hide the existing
        # record from the search.
        Notification = self.sudo()
        existing = Notification.search(
            [
                ('user_id', '=', user_id),
                ('idempotency_key', '=', idempotency_key),
            ],
            limit=1,
        )
        if existing:
            if action_url and existing.action_url != action_url:
                existing.write({'action_url': action_url})
            _logger.info(
                "unitrade.notification.emit user_id=%s event_code=%s "
                "result=duplicate id=%s",
                user_id, event_code, existing.id,
            )
            return existing

        # 6. Resolve effective channels -----------------------------------------
        if channels is not None:
            effective_channels = set(channels)
        else:
            effective_channels = set(entry['channels'])
        category = entry['category']  # always forced from registry
        is_critical_category = category in CRITICAL_CATEGORIES

        # 7. Preference check ---------------------------------------------------
        Pref = self.env['unitrade.notification.preference'].sudo()
        in_app_in_scope = 'in_app' in effective_channels
        email_in_scope = 'email' in effective_channels

        in_app_enabled = in_app_in_scope and (
            is_critical_category
            or Pref.is_enabled(user_id, category, 'in_app')
        )
        email_enabled = email_in_scope and Pref.is_enabled(
            user_id, category, 'email',
        )

        # 8. If everything is disabled the emission is a no-op.
        if not in_app_enabled and not email_enabled:
            _logger.info(
                "unitrade.notification.emit user_id=%s event_code=%s "
                "result=skipped",
                user_id, event_code,
            )
            return self.browse()

        # 9. Render content -----------------------------------------------------
        title, message = self._render_title_and_message(event_code, safe_payload)

        # 10. Seed email_state. The actual ``mail.mail`` enqueue happens
        # in task 7.3 (``_send_email_via_template``); leaving the state
        # at ``pending`` here gives that helper a stable starting point
        # without forcing emit() to know about templates yet.
        if email_enabled and entry.get('template'):
            email_state = 'pending'
        else:
            email_state = 'not_applicable'

        vals = {
            'user_id': user_id,
            'title': title,
            'message': message,
            'category': category,
            'event_code': event_code,
            'reference_model': safe_payload.get('reference_model') or False,
            'reference_id': safe_payload.get('reference_id') or 0,
            'action_url': action_url or False,
            'idempotency_key': idempotency_key,
            'email_state': email_state,
        }

        # 11. Optimistic create with savepoint to absorb UNIQUE collisions
        # caused by concurrent emit() calls (webhook retry storms,
        # parallel workers, etc.). pgcode 23505 = unique_violation.
        try:
            with self.env.cr.savepoint():
                record = Notification.create(vals)
        except IntegrityError as exc:
            if getattr(exc, 'pgcode', None) != '23505':
                raise
            winner = Notification.search(
                [
                    ('user_id', '=', user_id),
                    ('idempotency_key', '=', idempotency_key),
                ],
                limit=1,
            )
            _logger.info(
                "unitrade.notification.emit user_id=%s event_code=%s "
                "result=duplicate id=%s (race resolved)",
                user_id, event_code, winner.id if winner else None,
            )
            return winner

        # 12. Email enqueue (task 7.3). The helper internally honours
        # the email channel preference and the registry's ``channels``
        # tuple — we only call it when the seeded ``email_state`` is
        # ``pending`` (i.e. email is in scope and the template exists)
        # to avoid a redundant lookup. The helper catches its own
        # exceptions and persists the failure on the record; the
        # surrounding try/except is purely defensive so an unexpected
        # bug in the helper can never abort emit()'s success path —
        # in-app delivery has already happened (Req 9.5 / Property 19).
        if email_state == 'pending':
            try:
                record._send_email_via_template(entry['template'])
            except Exception:  # pylint: disable=broad-except
                _logger.warning(
                    "unitrade.notification.emit: email enqueue failed "
                    "id=%s event_code=%s",
                    record.id, event_code, exc_info=True,
                )

        _logger.info(
            "unitrade.notification.emit user_id=%s event_code=%s "
            "result=created id=%s",
            user_id, event_code, record.id,
        )
        return record

    # ------------------------------------------------------------------
    # 7.2 broadcast
    # ------------------------------------------------------------------
    @api.model
    def broadcast(self, event_code, payload=None, user_domain=None,
                  batch_size=None):
        """Emit the same event to many users in batches.

        Used primarily for ``system.announcement`` (Req 5.15). Internally
        reuses :meth:`emit` so each user receives the same idempotency,
        preference, and validation guarantees.

        Resilience model (Req 5.15 / 8.2):
        * Per-user ``try/except`` so one failing user never wastes the
          rest of the batch.
        * Per-batch ``try/except`` so a catastrophic batch-level error
          does not abort the whole run.

        :param str event_code: Event code (must exist in the registry).
        :param dict|None payload: Payload forwarded to :meth:`emit`.
        :param list|None user_domain: Optional ``res.users`` domain.
            Defaults to active non-shared users.
        :param int|None batch_size: Override for the per-batch user
            count; falls back to ``ir.config_parameter``
            ``unitrade.notification.broadcast_batch_size`` (default 200).
        :returns: ``{'emitted': int, 'failed_batches': int,
            'total': int}``.
        :rtype: dict
        """
        # 1. Resolve batch size (caller > config > 200) ------------------
        if batch_size is None:
            raw = self.env['ir.config_parameter'].sudo().get_param(
                'unitrade.notification.broadcast_batch_size',
                default='200',
            )
            try:
                batch_size = int(raw)
            except (TypeError, ValueError):
                batch_size = 200
        batch_size = max(1, int(batch_size))

        # 2. Resolve target user domain ----------------------------------
        domain = list(user_domain) if user_domain else [
            ('active', '=', True),
            ('share', '=', False),
        ]
        Users = self.env['res.users'].sudo()
        user_ids = Users.search(domain).ids

        total = len(user_ids)
        emitted = 0
        failed_batches = 0

        _logger.info(
            "unitrade.notification.broadcast event_code=%s users=%d "
            "batch_size=%d",
            event_code, total, batch_size,
        )

        # 3. Iterate in batches with two layers of fault isolation -------
        for batch_idx, start in enumerate(range(0, total, batch_size)):
            batch = user_ids[start:start + batch_size]
            try:
                for uid in batch:
                    try:
                        self.emit(uid, event_code, payload=payload)
                        emitted += 1
                    except Exception:  # noqa: BLE001
                        _logger.warning(
                            "unitrade.notification.broadcast user_id=%s "
                            "event_code=%s emit failed; continuing",
                            uid, event_code, exc_info=True,
                        )
            except Exception:  # noqa: BLE001
                failed_batches += 1
                _logger.warning(
                    "unitrade.notification.broadcast batch %d "
                    "(start=%d size=%d) failed for event_code=%s; "
                    "continuing with next batch",
                    batch_idx, start, len(batch), event_code,
                    exc_info=True,
                )

        _logger.info(
            "unitrade.notification.broadcast event_code=%s done: "
            "emitted=%d failed_batches=%d total=%d",
            event_code, emitted, failed_batches, total,
        )
        return {
            'emitted': emitted,
            'failed_batches': failed_batches,
            'total': total,
        }

    # ------------------------------------------------------------------
    # 7.3 Email lifecycle and bulk read
    # ------------------------------------------------------------------
    def _send_email_via_template(self, template_xmlid):
        """Enqueue the configured ``mail.template`` for ``self``.

        Operates on a single notification record (``self.ensure_one()``)
        and is the only place in the dispatcher that talks to the
        ``mail.mail`` queue. Behaviour matches the design's email
        lifecycle state machine (Req 6.6 / 8.4 / Property 11):

        * If the originating event's registry entry does not list the
          ``'email'`` channel, the call is a no-op and ``email_state``
          is set to ``'not_applicable'``. This guards callers (notably
          ``action_retry_email``) from accidentally enqueueing email
          for in-app-only events such as ``order.delivered``.
        * If the user's email preference for the record's category is
          disabled, the call is also a no-op (``not_applicable``);
          critical-category overrides apply only to the in-app channel
          (Req 2.5).
        * If ``template_xmlid`` cannot be resolved, ``email_state`` is
          set to ``'failed'`` with an explanatory ``email_error``.
        * Otherwise ``template.send_mail(self.id, force_send=False)``
          is invoked inside a try/except. On success the returned
          ``mail.mail`` id is persisted into ``mail_message_id`` and
          ``email_state`` flips to ``'sent'``. On exception the
          stacktrace is captured into ``email_error`` and
          ``email_state`` flips to ``'failed'`` (Req 8.4).

        Email sending is asynchronous (``force_send=False``); the
        actual SMTP delivery happens in the Odoo mail worker so the
        emit/HTTP path is never blocked (Req 9.5 / Property 19).
        """
        self.ensure_one()

        # Channel-scope guard. ``order.delivered``, ``chat.new_message``,
        # ``review.*`` etc. live entirely in-app; a misconfigured
        # caller asking us to send their email is a quiet no-op.
        entry = EVENT_REGISTRY.get(self.event_code)
        if not entry or 'email' not in entry.get('channels', ()):
            self.write({
                'email_state': 'not_applicable',
                'email_error': False,
            })
            return

        # Preference guard. Critical-category override only applies to
        # the in_app channel (Req 2.5); email is always opt-out-able.
        Pref = self.env['unitrade.notification.preference'].sudo()
        if not Pref.is_enabled(self.user_id.id, self.category, 'email'):
            self.write({
                'email_state': 'not_applicable',
                'email_error': False,
            })
            return

        template = self.env.ref(template_xmlid, raise_if_not_found=False)
        if not template:
            _logger.warning(
                "unitrade.notification._send_email_via_template: "
                "missing template xmlid=%r id=%s event_code=%s",
                template_xmlid, self.id, self.event_code,
            )
            self.write({
                'email_state': 'failed',
                'email_error': "Mail template not found: %s" % (
                    template_xmlid,
                ),
            })
            return

        # Seed ``pending`` so concurrent observers (admin retry view,
        # background workers) can see the record is mid-flight even
        # when ``send_mail`` blocks on a slow SMTP handshake.
        if self.email_state != 'pending':
            self.write({'email_state': 'pending'})

        try:
            mail_id = template.sudo().send_mail(
                self.id, force_send=False,
            )
        except Exception:  # pylint: disable=broad-except
            tb = traceback.format_exc()
            _logger.warning(
                "unitrade.notification._send_email_via_template: "
                "send_mail raised id=%s event_code=%s",
                self.id, self.event_code, exc_info=True,
            )
            self.write({
                'email_state': 'failed',
                'email_error': tb,
            })
            return

        self.write({
            'email_state': 'sent',
            'mail_message_id': mail_id or False,
            'email_error': False,
        })
        _logger.info(
            "unitrade.notification._send_email_via_template "
            "id=%s event_code=%s mail_id=%s result=sent",
            self.id, self.event_code, mail_id,
        )

    def action_retry_email(self):
        """Backend button: re-enqueue email for the selected records.

        Drives the admin "Failed Emails" view (Req 8.5). Iterates the
        recordset and calls :meth:`_send_email_via_template` for every
        record whose ``email_state`` is *not* ``'sent'``. Records
        already in the ``'sent'`` terminal state are skipped so the
        operation never regresses a successful delivery
        (Req 6.6 / Property 11 — the state machine only moves forward).

        For records whose registry entry has no email template (e.g.
        ``order.delivered`` got accidentally surfaced in the failed
        list), ``email_state`` is moved to ``'not_applicable'`` rather
        than re-attempted.
        """
        for record in self:
            if record.email_state == 'sent':
                # Never regress sent → pending/failed.
                continue

            entry = EVENT_REGISTRY.get(record.event_code)
            template_xmlid = entry.get('template') if entry else None
            if not entry or not template_xmlid:
                _logger.info(
                    "unitrade.notification.action_retry_email: "
                    "no email template for id=%s event_code=%s; "
                    "marking not_applicable",
                    record.id, record.event_code,
                )
                record.write({
                    'email_state': 'not_applicable',
                    'email_error': False,
                })
                continue

            record._send_email_via_template(template_xmlid)
        return True

    @api.model
    def mark_all_as_read(self, user_id, recipient_scope=None):
        """Bulk mark every unread notification of ``user_id`` as read.

        Idempotent (Req 10.3 / Property 6 — Mark-as-Read Invariants):
        a second call with no new emissions matches an empty recordset
        and writes nothing. ``read_at`` is set to ``now()`` on the
        records that actually transition, so already-read records keep
        their original timestamp.

        :param int user_id: Owner of the notifications to mark.
        :returns: Number of records updated by this call.
        :rtype: int
        """
        if not user_id:
            return 0
        domain = [
            ('user_id', '=', user_id),
            ('is_read', '=', False),
        ]
        if recipient_scope:
            domain += self._notification_scope_domain(recipient_scope)
        records = self.sudo().search(domain)
        if not records:
            return 0
        records.write({
            'is_read': True,
            'read_at': fields.Datetime.now(),
        })
        return len(records)

    # ------------------------------------------------------------------
    # 9.3 Retention GC cron
    # ------------------------------------------------------------------
    @api.model
    def _gc_old_notifications(self):
        """Daily retention sweep — deletes read notifications older than
        the configured retention window.

        Threshold is read from ``ir.config_parameter``
        ``unitrade.notification.retention_days`` (default 180). Only
        records with ``is_read=True`` are removed; unread notifications
        are kept indefinitely (Req 9.4).

        Called by ``ir_cron_unitrade_notification_retention``.

        :returns: Number of deleted records (handy for tests).
        :rtype: int
        """
        raw = self.env['ir.config_parameter'].sudo().get_param(
            'unitrade.notification.retention_days', default='180',
        )
        try:
            days = int(raw)
        except (TypeError, ValueError):
            days = 180
        days = max(1, days)

        cutoff = fields.Datetime.now() - timedelta(days=days)
        candidates = self.sudo().search([
            ('is_read', '=', True),
            ('create_date', '<', cutoff),
        ])
        deleted = len(candidates)
        if candidates:
            candidates.unlink()
        _logger.info(
            "unitrade.notification._gc_old_notifications deleted=%d "
            "cutoff=%s threshold_days=%d",
            deleted, cutoff, days,
        )
        return deleted

    # ------------------------------------------------------------------
    # 9.4 Review reminder cron
    # ------------------------------------------------------------------
    @api.model
    def _cron_emit_review_reminders(self):
        """Hourly cron — emits ``review.reminder`` to buyers whose
        delivered orders have not been reviewed within 24 hours.

        Idempotency is provided by the dispatcher's ``idempotency_key``
        derived from ``(event_code='review.reminder', reference_model,
        reference_id)`` — re-running this cron produces no duplicate
        records for the same ``(buyer, order)`` pair (Req 5.13 /
        Property 10).

        The implementation is defensive: schemas vary across the
        ``unitrade_order`` / ``unitrade_review`` modules, so any missing
        field/model is logged at WARNING and the cron returns cleanly
        rather than aborting the daily/hourly run.

        :returns: Number of reminders emitted (handy for tests).
        :rtype: int
        """
        SaleOrder = self.env.get('sale.order')
        if SaleOrder is None:
            _logger.warning(
                "_cron_emit_review_reminders: sale.order model "
                "unavailable; skipping",
            )
            return 0

        cutoff = fields.Datetime.now() - timedelta(hours=24)

        # Build the candidate domain conservatively. Different UniTrade
        # modules may use different field names (state vs delivery_state,
        # delivered_at vs date_done). We attempt a generic ``state`` match
        # and rely on the dispatcher's idempotency to absorb misfires.
        try:
            candidates = SaleOrder.sudo().search([
                ('state', 'in', ['done', 'delivered', 'sale']),
                ('write_date', '<', cutoff),
            ])
        except Exception:  # pylint: disable=broad-except
            _logger.warning(
                "_cron_emit_review_reminders: candidate search failed; "
                "skipping",
                exc_info=True,
            )
            return 0

        Review = self.env.get('unitrade.review')
        Notification = self.sudo()
        emitted = 0

        for order in candidates:
            partner = order.partner_id
            if not partner or not partner.user_ids:
                continue
            # Pick the first portal user attached to the partner; this is
            # the standard mapping in UniTrade where one buyer has one
            # ``res.users`` linked via ``res.partner.user_ids``.
            buyer = partner.user_ids[:1]
            if not buyer:
                continue

            # Skip if a review for this order already exists.
            if Review is not None:
                try:
                    already = Review.sudo().search_count([
                        ('order_id', '=', order.id),
                        ('user_id', '=', buyer.id),
                    ])
                    if already:
                        continue
                except Exception:  # pylint: disable=broad-except
                    # Schema mismatch — fall through to emit; idempotency
                    # absorbs replay safely.
                    _logger.debug(
                        "_cron_emit_review_reminders: review check "
                        "failed for order_id=%s; emitting anyway",
                        order.id,
                    )

            try:
                result = Notification.emit(
                    buyer.id,
                    'review.reminder',
                    payload={
                        'reference_model': 'sale.order',
                        'reference_id': order.id,
                        'action_url': Notification._review_orders_action_url(),
                    },
                )
                if result:
                    emitted += 1
            except Exception:  # pylint: disable=broad-except
                _logger.warning(
                    "_cron_emit_review_reminders: emit failed for "
                    "buyer_id=%s order_id=%s",
                    buyer.id, order.id, exc_info=True,
                )

        _logger.info(
            "unitrade.notification._cron_emit_review_reminders "
            "emitted=%d candidates=%d",
            emitted, len(candidates),
        )
        return emitted

    def action_mark_unread(self):
        self.write({
            'is_read': False,
            'read_at': False,
            'read_by_id': False,
        })

    @api.model
    def create_admin_notification(
        self,
        title,
        message='',
        priority='info',
        notification_type='system',
        target_model='',
        target_id=0,
        target_url='',
        action_xmlid='',
        dedupe_key='',
        user_id=False,
    ):
        """Create or update one persistent admin notification.

        The dashboard may call this repeatedly from live task domains, so
        ``dedupe_key`` keeps the inbox clean while still refreshing changed
        counts/messages.
        """
        user_id = user_id or self.env.user.id
        values = {
            'user_id': user_id,
            'audience': 'admin',
            'title': title,
            'message': message or False,
            'priority': priority if priority in ('info', 'warning', 'urgent', 'critical') else 'info',
            'notification_type': notification_type or 'system',
            'target_model': target_model or False,
            'target_id': int(target_id or 0),
            'target_url': target_url or False,
            'action_xmlid': action_xmlid or False,
            'dedupe_key': dedupe_key or False,
        }

        existing = self.sudo().search([
            ('audience', '=', 'admin'),
            ('user_id', '=', user_id),
            ('dedupe_key', '=', dedupe_key),
        ], limit=1) if dedupe_key else self.browse()
        if existing:
            changed = any(existing[field] != values[field] for field in (
                'title',
                'message',
                'priority',
                'notification_type',
                'target_model',
                'target_id',
                'target_url',
                'action_xmlid',
            ))
            if changed:
                values.update({
                    'is_read': False,
                    'read_at': False,
                    'read_by_id': False,
                })
                existing.write(values)
            return existing
        return self.sudo().create(values)

    def _target_url(self):
        self.ensure_one()
        if self.target_url:
            return self.target_url
        if self.action_xmlid:
            return '/odoo/action-%s' % self.action_xmlid
        if self.target_model and self.target_id:
            return '/odoo?model=%s&id=%s' % (self.target_model, self.target_id)
        return '/unitrade/admin/notifications'

    def _admin_payload(self):
        self.ensure_one()
        level = self.priority
        if level == 'critical':
            level = 'urgent'
        return {
            'id': self.id,
            'dedupe_key': self.dedupe_key or str(self.id),
            'level': level,
            'priority': self.priority,
            'title': self.title,
            'message': self.message or '',
            'time_label': self._humanize_time(self.create_date),
            'target_url': self._target_url(),
            'is_read': bool(self.is_read),
            'notification_type': self.notification_type,
        }

    @staticmethod
    def _humanize_time(dt):
        if not dt:
            return ''
        try:
            now = fields.Datetime.now()
            delta = now - dt
            seconds = int(delta.total_seconds())
            if seconds < 60:
                return 'Baru saja'
            minutes = seconds // 60
            if minutes < 60:
                return '%s menit lalu' % minutes
            hours = minutes // 60
            if hours < 24:
                return '%s jam lalu' % hours
            days = hours // 24
            if days < 7:
                return '%s hari lalu' % days
            return dt.strftime('%d %b %Y')
        except Exception:
            _logger.exception('Failed humanizing notification time')
            return ''
