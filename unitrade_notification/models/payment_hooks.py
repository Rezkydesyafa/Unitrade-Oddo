"""Payment-event notification hooks (Task 15.4).

This module wires Midtrans payment lifecycle transitions in the
``unitrade_payment`` module into the notification dispatcher
(:class:`unitrade.notification`'s ``emit``).

Why inherit ``unitrade.payment.intent`` from inside
``unitrade_notification`` and not the other way around?

* ``unitrade_notification.__manifest__.py`` already declares
  ``unitrade_payment`` as a dependency, so the module load order is
  guaranteed (notification loads after payment).
* Modifying ``unitrade_payment`` directly would invert the dependency
  arrow and create a circular dependency, since the payment module
  must remain installable on its own (the marketplace ships with
  ``unitrade_payment`` even when ``unitrade_notification`` is not
  active).

Why hook on ``write()`` rather than the controller or
``unitrade.payment.event`` row creation?

* The Midtrans webhook handler in
  ``unitrade_payment/controllers/main.py`` always funnels a normalized
  status through
  ``intent.sale_order_id._unitrade_mark_midtrans_paid()`` (success
  case) or ``intent.sudo().write({'state': ...})`` (every other
  case). Both ultimately call ``write`` on ``unitrade.payment.intent``,
  so a single override here covers webhook delivery, manual admin
  actions (``action_simulate_midtrans_paid`` / ``..._expired`` /
  ``..._failed``), and the Midtrans status-pull cron.
* ``unitrade.payment.event`` rows are written *before* the intent
  state changes (and even on duplicates / failed signature checks),
  so hooking there would either fire too early or fire on entries
  that never actually mutate the intent.

State → ``event_code`` mapping (Req 5.11):

    paid       → payment.success
    pending    → payment.pending
    failed     → payment.failed
    expired    → payment.expired

The webhook controller's ``_normalize_midtrans_status`` already folds
all Midtrans statuses (``settlement``/``capture`` → ``paid``,
``deny``/``cancel``/``failure`` → ``failed``, ``expire`` →
``expired``) into the four ORM states above, so we only need to map
those four here.

Seller-side order alerts are emitted by ``sale.order.action_confirm``
as ``order.new_for_seller`` after successful checkout payment. Payment
events in this hook are buyer/user notifications only, so they never
pollute the seller dashboard inbox.

Listing-fee intents (``intent_type == 'listing_fee'``) are out of
scope — they have no ``sale_order_id`` and therefore no buyer/seller
relation in the marketplace sense. The buyer/seller notification
contract only applies to order-checkout payments.
"""

import logging

from odoo import models

_logger = logging.getLogger(__name__)


# Mapping from the post-write ``state`` value on
# ``unitrade.payment.intent`` to a registered notification
# ``event_code``. Only the four states that actually correspond to a
# Midtrans transaction outcome are mapped; ``draft`` / ``cancelled`` /
# ``refunded`` are intentionally absent so unrelated administrative
# state changes do not produce notifications.
_STATE_TO_EVENT_CODE = {
    'paid': 'payment.success',
    'pending': 'payment.pending',
    'failed': 'payment.failed',
    'expired': 'payment.expired',
}


class UnitradePaymentIntentNotificationHooks(models.Model):
    """Inherit ``unitrade.payment.intent`` to emit notifications on
    state transitions triggered by the Midtrans webhook.
    """

    _inherit = 'unitrade.payment.intent'

    # ------------------------------------------------------------------
    # ORM override
    # ------------------------------------------------------------------
    def write(self, vals):
        """Capture pre-write states so we can detect transitions, run
        the standard ``write``, then dispatch notifications.

        We only react when ``state`` is in the write payload — every
        Midtrans webhook update carries the state field, and skipping
        this branch when state is unchanged keeps the hot path (e.g.
        seeding ``midtrans_actions``) free of search overhead.

        Notifications are emitted *after* ``super().write`` so the
        record is already in its target state when downstream code
        (mail templates, action_url lookups) runs.
        """
        # Snapshot pre-write state for transition detection. The
        # ``state`` field is only inspected per-record, so a dict keyed
        # by id keeps the loop O(n).
        old_states = {}
        if 'state' in vals:
            for record in self:
                old_states[record.id] = record.state

        result = super().write(vals)

        if 'state' in vals and old_states:
            for record in self:
                old_state = old_states.get(record.id)
                new_state = record.state
                if old_state == new_state:
                    # No-op write (rare — Odoo can re-write the same
                    # value during reload). Skip so we don't fire
                    # duplicate emit() calls for a transition that
                    # never actually happened.
                    continue
                event_code = _STATE_TO_EVENT_CODE.get(new_state)
                if not event_code:
                    continue
                # Wrap the entire emit pipeline in a try/except: we do
                # not want a notification failure (e.g. mail server
                # down, registry mismatch) to roll back the intent
                # state update or the webhook response.
                try:
                    record._unitrade_emit_payment_notifications(event_code)
                except Exception:  # pragma: no cover — defensive
                    _logger.exception(
                        "Failed to emit payment notifications for "
                        "intent_id=%s event_code=%s",
                        record.id, event_code,
                    )

        return result

    # ------------------------------------------------------------------
    # Emission helpers
    # ------------------------------------------------------------------
    def _unitrade_emit_payment_notifications(self, event_code):
        """Emit a buyer notification for a single intent that just transitioned to a
        terminal Midtrans state.

        :param str event_code: One of ``payment.success`` /
            ``payment.pending`` / ``payment.failed`` /
            ``payment.expired`` — already validated by the caller
            against :data:`_STATE_TO_EVENT_CODE`.
        """
        self.ensure_one()

        # Listing-fee payments do not have a buyer/seller relationship
        # tied to a sale.order and are therefore out of scope for
        # task 15.4 (Req 5.11 only concerns checkout payments).
        order = self.sale_order_id
        if not order or self.intent_type != 'order_checkout':
            return

        Notification = self.env['unitrade.notification'].sudo()

        # Buyer is always notified (in-app + email per registry).
        buyer_user_id = self._unitrade_resolve_buyer_user_id(order)
        payload = self._unitrade_build_payment_payload(order)

        if buyer_user_id:
            try:
                Notification.emit(
                    buyer_user_id,
                    event_code,
                    payload=payload,
                    idempotency_discriminator='intent:%s' % self.id,
                )
            except Exception:
                _logger.warning(
                    "Buyer notification emit failed: intent_id=%s "
                    "event_code=%s order_id=%s buyer_user_id=%s",
                    self.id, event_code, order.id, buyer_user_id,
                    exc_info=True,
                )
        else:
            _logger.info(
                "Skipping buyer notification (no resolvable user) "
                "intent_id=%s event_code=%s order_id=%s",
                self.id, event_code, order.id,
            )

    # ------------------------------------------------------------------
    # Resolution helpers
    # ------------------------------------------------------------------
    def _unitrade_build_payment_payload(self, order):
        """Build the payload dict shared by buyer and seller emits.

        The dispatcher uses ``reference_model`` / ``reference_id`` as
        part of the idempotency key, so anchoring on the sale order is
        what guarantees re-deliveries of the same Midtrans webhook
        produce a single notification (Req 5.11 + Req 1.4).
        """
        return {
            'reference_model': 'sale.order',
            'reference_id': order.id,
            # Order status page is internal and starts with ``/`` so
            # ``_validate_action_url`` accepts it without consulting
            # the allow-list.
            'action_url': '/unitrade/order/status/%s' % order.id,
            'recipient_scope': 'user',
        }

    def _unitrade_resolve_buyer_user_id(self, order):
        """Return the buyer's ``res.users`` id for ``order``, or
        ``False`` when no internal user is linked to the partner.

        Mirrors ``unitrade_payment.sale_order._unitrade_voucher_buyer_user``:
        a partner can be linked to multiple users (e.g. portal +
        internal); we pick the first one. ``user_ids`` is the inverse
        of ``res.users.partner_id`` so it is always populated when at
        least one user exists.
        """
        partner = order.partner_id
        if not partner:
            return False
        user = partner.user_ids[:1]
        return user.id if user else False

    def _unitrade_resolve_seller_user_ids(self, order):
        """Return a *deduplicated* list of seller ``res.users`` ids
        derived from the order lines.

        The marketplace stores the seller relationship on
        ``product.template.x_seller_id`` (a ``unitrade.seller`` record
        whose ``user_id`` is the underlying ``res.users``). An order
        may legitimately span multiple sellers, so we collect ids in
        insertion order to make the emission sequence deterministic
        (handy for tests and log readability).

        Lines that have no product (``display_type``-only lines such
        as section headers, or fee/discount auto-lines) are skipped.
        """
        seen = set()
        ordered = []
        for line in order.order_line:
            if line.display_type or not line.product_id:
                continue
            product_tmpl = line.product_id.product_tmpl_id
            seller = getattr(product_tmpl, 'x_seller_id', False)
            if not seller:
                continue
            seller_user = seller.user_id
            if not seller_user:
                continue
            seller_user_id = seller_user.id
            if seller_user_id in seen:
                continue
            seen.add(seller_user_id)
            ordered.append(seller_user_id)
        return ordered
