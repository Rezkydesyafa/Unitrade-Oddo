"""``res.users`` overrides that wire account-level notification events.

Task 15.1 of the UniTrade Notification System spec asks that the
following events flow through the dispatcher with stable idempotency
keys (Req 5.1, 5.2):

* ``account.welcome`` — emitted right after a new ``res.users`` row is
  created and active. This catches both signup-via-token (the standard
  ``auth_signup`` flow used by the ``/web/signup`` controller) and
  admin-created users; ``welcome`` is benign so the broader trigger
  is intentional.
* ``account.password_reset`` — emitted right after the stock
  :meth:`res.users.action_reset_password` finishes preparing a fresh
  signup token and queueing the reset email. Because the registry
  declares only the ``email`` channel for this code, the dispatcher
  enqueues a confirmation email and skips the in-app row entirely.

The wiring is *deliberately* placed inside the ``unitrade_notification``
module — there is no ``unitrade_account`` module in this workspace, and
adding a Python file to the dispatcher's own module keeps the caller
side co-located with the dispatcher and avoids touching unrelated
modules. This matches the design's "single source of truth" principle
where every notification flows through ``unitrade.notification.emit``.

Idempotency_discriminator
-------------------------

Both emit calls supply a stable discriminator so the SHA-1 idempotency
key remains stable across retries:

* welcome → ``user.create_date`` ISO string. Two re-runs of the same
  install / fixture against the same DB would not double-emit because
  the create_date never changes once persisted.
* password_reset → ``user.signup_token`` (delegated from ``res.partner``
  via ``auth_signup``). Each new reset request rotates the token, so a
  fresh notification is produced per reset cycle while accidental
  re-invocations within the same cycle collapse to the existing record.

Failure isolation
-----------------

Both call sites wrap the emit in ``try/except Exception`` so a
notification failure can never abort user creation or the password
reset flow. The exception is logged at WARNING with the user_id for
operator triage; the dispatcher itself already isolates email failures
on the record (``email_state='failed'``) so this catch is purely
defensive.
"""

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    # ------------------------------------------------------------------
    # account.welcome
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        """Emit ``account.welcome`` after each new active, non-shared user.

        ``share=True`` (portal/public) and inactive users are skipped:
        portal accounts created on the fly during ``/shop`` checkout
        and the sentinel public user must not receive a welcome email,
        and inactive accounts have not yet been activated by the user.

        The discriminator is the freshly stored ``create_date`` (ISO
        format) which is stable across re-runs of the same fixture
        against the same DB row, keeping the idempotency key — and
        therefore the resulting notification record — unique per user.
        """
        users = super().create(vals_list)

        Notification = self.env['unitrade.notification'].sudo()
        for user in users:
            # Skip portal / public / inactive users — see docstring.
            if user.share or not user.active:
                continue
            try:
                discriminator = (
                    user.create_date.isoformat()
                    if user.create_date else None
                )
                Notification.emit(
                    user.id,
                    'account.welcome',
                    payload={
                        'reference_model': 'res.users',
                        'reference_id': user.id,
                        'recipient_scope': 'user',
                    },
                    idempotency_discriminator=discriminator,
                )
            except Exception:  # pylint: disable=broad-except
                # Notification failure must never abort user creation.
                _logger.warning(
                    "account.welcome emit failed for user_id=%s",
                    user.id, exc_info=True,
                )
        return users

    # ------------------------------------------------------------------
    # account.password_reset
    # ------------------------------------------------------------------
    def action_reset_password(self):
        """Emit ``account.password_reset`` after the stock reset flow.

        The base implementation lives in ``auth_signup`` and:

        1. Calls ``partner.signup_prepare(signup_type='reset', ...)``
           which rotates the signup token on the partner record.
        2. Renders and queues the reset email via ``mail.template``.

        We hook *after* the super-call so a fresh ``signup_token`` is
        guaranteed to be present on each user, and we use that token
        as the idempotency discriminator. Because the token rotates
        per reset cycle, each new request gets its own notification
        record while accidental double-invocations within the same
        cycle collapse via the ``UNIQUE(user_id, idempotency_key)``
        constraint enforced by the dispatcher.

        ``signup_token`` is exposed on ``res.users`` via the standard
        ``auth_signup`` field delegation from ``res.partner``; if it is
        somehow unavailable (e.g. the partner is missing or the field
        was not yet rotated), we fall back to a timestamp so the emit
        still succeeds — at the cost of allowing a rare duplicate.
        """
        result = super().action_reset_password()

        Notification = self.env['unitrade.notification'].sudo()
        for user in self:
            try:
                discriminator = (
                    user.signup_token
                    or fields.Datetime.now().isoformat()
                )
                Notification.emit(
                    user.id,
                    'account.password_reset',
                    payload={
                        'reference_model': 'res.users',
                        'reference_id': user.id,
                        'recipient_scope': 'user',
                    },
                    idempotency_discriminator=discriminator,
                )
            except Exception:  # pylint: disable=broad-except
                # Reset flow continues even if the confirmation
                # notification cannot be enqueued.
                _logger.warning(
                    "account.password_reset emit failed for user_id=%s",
                    user.id, exc_info=True,
                )
        return result
