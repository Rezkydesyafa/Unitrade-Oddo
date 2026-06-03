"""Chat notification hooks for the UniTrade Notification System.

Task 15.5 — wire ``chat.new_message`` emissions to the dispatcher
whenever a new ``unitrade.chat.message`` row is created. The hook lives
in this module (rather than in ``unitrade_chat``) because
``unitrade_notification`` already declares ``unitrade_chat`` in its
manifest ``depends`` and adding the reverse dependency would create an
import cycle.

Grouping window
---------------
Repeated messages in the same conversation targeting the same recipient
within a 10-minute window collapse to **one**
``unitrade.notification`` record (Req 5.12 / Property 9). This is
implemented by feeding the dispatcher a deterministic
``idempotency_discriminator`` derived from the conversation id and
``floor(now_epoch / 600)``: every message in the same bucket produces
the same key, and the dispatcher's
``UNIQUE(user_id, idempotency_key)`` constraint absorbs the duplicates.
Once the bucket rolls over (10 minutes elapsed), the next message
produces a fresh notification.

Skipped cases
-------------
* ``message_type == 'system'`` — auto-generated welcome banners and
  bookkeeping rows do not warrant a bell ping.
* Sender == recipient — defensive only (``_other_user`` never returns
  the author for a buyer↔seller pair), but the check is cheap.
* No resolvable recipient — happens for sellers without a backing
  ``res.users``; we silently skip rather than crash the chat write.

Failure handling
----------------
Any exception raised by the dispatcher (``unitrade.notification.emit``)
is caught and logged at ``WARNING`` level with the message id and
stacktrace. A failed bell ping must never break the chat flow.
"""

import logging
import time

from odoo import api, models

_logger = logging.getLogger(__name__)


# 10-minute grouping window expressed in seconds. Property 9 ties the
# constant to the design document; keep both in sync.
_CHAT_GROUP_WINDOW_SECONDS = 600


class UnitradeChatMessageNotificationHook(models.Model):
    """Inherit ``unitrade.chat.message`` to emit ``chat.new_message``.

    The hook only adds behaviour to ``create``; no new fields and no
    new storage. Inheritance is via the standard ``_inherit`` form so
    the underlying table is unchanged.
    """

    _inherit = 'unitrade.chat.message'

    @api.model_create_multi
    def create(self, vals_list):
        messages = super().create(vals_list)
        for message in messages:
            try:
                self._unitrade_notification_emit_chat(message)
            except Exception:
                # Defensive: chat must never break because of a
                # notification failure. We log with stacktrace so
                # admins can investigate.
                _logger.warning(
                    "chat.new_message emit failed for message_id=%s",
                    message.id,
                    exc_info=True,
                )
        return messages

    def _unitrade_notification_emit_chat(self, message):
        """Emit ``chat.new_message`` for the recipient of ``message``.

        Skips system / self-addressed messages and routes to the
        dispatcher with a 10-minute idempotency discriminator so
        repeated emissions within the window collapse to one record.
        """
        # Read under sudo so the hook works regardless of which side
        # of the conversation triggered the write (buyer vs seller).
        message_su = message.sudo()

        # System messages (welcome banners, admin notices) don't
        # deserve a bell ping.
        if message_su.message_type == 'system':
            return

        conversation = message_su.conversation_id
        if not conversation:
            return

        author = message_su.author_user_id
        if not author:
            return

        recipient = conversation._other_user(author)
        if (
            not recipient
            or not recipient.id
            or recipient.id == author.id
        ):
            return

        # 10-minute bucket. Re-emits for the same
        # ``(conversation, recipient)`` pair in the same window collapse
        # via the dispatcher's idempotency key.
        bucket = int(time.time() // _CHAT_GROUP_WINDOW_SECONDS)
        discriminator = '%s:%s' % (conversation.id, bucket)

        author_name = author.name or 'pengguna'

        Notification = self.env['unitrade.notification'].sudo()
        Notification.emit(
            recipient.id,
            'chat.new_message',
            payload={
                'reference_model': 'unitrade.chat.conversation',
                'reference_id': conversation.id,
                'action_url': '/unitrade/chat?conversation_id=%s' % conversation.id,
                'title_override': 'Pesan baru dari %s' % author_name,
            },
            idempotency_discriminator=discriminator,
        )
