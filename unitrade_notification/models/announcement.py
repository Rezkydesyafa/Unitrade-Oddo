"""UniTrade system announcement model.

Implements task 15.7 — admin trigger that fires the
``system.announcement`` event via ``unitrade.notification.broadcast``
(Req 5.15, 8.2).

Admins draft an announcement (title + body, optional internal action
URL) on this model and press the ``Publish & Kirim ke Semua User``
button. The button calls :meth:`unitrade.notification.broadcast` with
the canonical "active non-shared users" domain so every real user
account receives one in-app notification (and an email when their
preference allows).

The dispatcher already enforces:

* idempotency — re-pressing the button is safe per user
  (``idempotency_key`` is keyed on ``reference_model`` +
  ``reference_id``, which is this announcement's id);
* preference + critical override — system announcements are
  non-critical, so users who toggled the ``system`` category off do not
  receive an in-app record;
* ``unitrade.notification.broadcast_batch_size`` — honored automatically
  by ``broadcast()``.

The announcement record itself is moved from ``draft`` → ``published``
once and stores the broadcast counters returned by the dispatcher
(useful for admin auditing and the failed-emails view in task 14.1).
"""

import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class UnitradeAnnouncement(models.Model):
    """Admin-only announcement that fans out to all active users."""

    _name = 'unitrade.announcement'
    _description = 'UniTrade System Announcement'
    _order = 'create_date desc, id desc'

    # ------------------------------------------------------------------
    # Fields
    # ------------------------------------------------------------------
    title = fields.Char(
        string='Judul',
        required=True,
        help="Judul pengumuman; menjadi subject email dan title in-app.",
    )
    body = fields.Text(
        string='Isi Pengumuman',
        required=True,
        help="Isi pengumuman yang dibagikan ke semua user aktif.",
    )
    action_url = fields.Char(
        string='Link Aksi',
        help="Opsional. URL internal yang dapat di-klik user dari "
             "notifikasi (mis. /my/orders).",
    )
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('published', 'Dipublish'),
        ],
        string='Status',
        default='draft',
        required=True,
        readonly=True,
        copy=False,
    )
    published_at = fields.Datetime(
        string='Tanggal Publish',
        readonly=True,
        copy=False,
    )
    published_by = fields.Many2one(
        'res.users',
        string='Dipublish oleh',
        readonly=True,
        copy=False,
    )

    # Counters returned by ``broadcast()`` — surfaced for admin audit.
    target_user_count = fields.Integer(
        string='Jumlah User Target',
        readonly=True,
        copy=False,
        help="Jumlah user aktif yang menjadi target broadcast saat "
             "tombol Publish ditekan.",
    )
    emitted_count = fields.Integer(
        string='Notifikasi Terkirim',
        readonly=True,
        copy=False,
    )
    failed_batches = fields.Integer(
        string='Batch Gagal',
        readonly=True,
        copy=False,
    )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_publish_and_broadcast(self):
        """Publish the announcement and fan it out via the dispatcher.

        Calls ``unitrade.notification.broadcast('system.announcement',
        ...)`` exactly as specified by task 15.7 and Req 5.15 / 8.2.
        The dispatcher's idempotency contract guarantees that even if
        the button is pressed twice (or the request is retried), each
        user still receives at most one in-app record per announcement
        ``reference_id``.

        :returns: ``True`` on success.
        :rtype: bool
        :raises odoo.exceptions.UserError: when called on an already
            published announcement (kept as a hard guard so admins
            get an explicit message instead of a silent no-op).
        """
        Notification = self.env['unitrade.notification']

        for announcement in self:
            if announcement.state == 'published':
                # Hard guard: the form view already hides the button via
                # ``invisible="state == 'published'"`` but a programmatic
                # caller (or a stale tab) can still reach this code path.
                raise UserError(
                    "Pengumuman ini sudah dipublish."
                )

            payload = {
                'title_override': announcement.title,
                'message_override': announcement.body,
                'reference_model': announcement._name,
                'reference_id': announcement.id,
            }
            if announcement.action_url:
                payload['action_url'] = announcement.action_url

            _logger.info(
                "unitrade.announcement publish id=%s by user_id=%s",
                announcement.id, self.env.user.id,
            )

            # ``broadcast`` already honors
            # ``unitrade.notification.broadcast_batch_size`` (Req 8.2)
            # and uses the active non-shared users domain by default;
            # we pass it explicitly to make the contract obvious at
            # the call site (matches task 15.7 verbatim).
            result = Notification.broadcast(
                'system.announcement',
                payload=payload,
                user_domain=[
                    ('active', '=', True),
                    ('share', '=', False),
                ],
            )

            announcement.write({
                'state': 'published',
                'published_at': fields.Datetime.now(),
                'published_by': self.env.user.id,
                'target_user_count': result.get('total', 0),
                'emitted_count': result.get('emitted', 0),
                'failed_batches': result.get('failed_batches', 0),
            })

        return True

    # ------------------------------------------------------------------
    # Safety: prevent unlinking a published announcement so the
    # corresponding ``unitrade.notification`` records keep a stable
    # ``reference_id`` for audit / re-render.
    # ------------------------------------------------------------------
    @api.ondelete(at_uninstall=False)
    def _unlink_only_when_draft(self):
        for rec in self:
            if rec.state == 'published':
                raise UserError(
                    "Pengumuman yang sudah dipublish tidak dapat "
                    "dihapus. Buat pengumuman baru bila perlu."
                )
