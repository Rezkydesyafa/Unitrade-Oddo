"""Notification hooks for ``sale.order`` and ``unitrade.escrow.ledger``.

Wires the order lifecycle events (Req 5.6–5.10) into the dispatcher on
``unitrade.notification``. The hooks live inside ``unitrade_notification``
rather than the order/payment modules so the notification dependency
graph stays one-directional (``unitrade_notification`` already depends
on ``unitrade_payment``; adding the reverse coupling would create a
cycle).

Mapping rationale
=================

The UniTrade marketplace does not use the stock Odoo ``shipped`` /
``delivered`` states on ``sale.order``. Instead the escrow ledger holds
the operational status:

* ``sale.order.action_confirm`` is the canonical "order placed"
  transition — it fires after Midtrans/Xendit payment success
  (``models/sale_order.py`` calls ``self.sudo().action_confirm()`` from
  ``_finalize_payment_intent``). We map it to ``order.new_for_seller``
  (one emit per distinct seller in the line items) and
  ``order.confirmed`` (single emit to the buyer).
* ``unitrade.escrow.ledger.action_seller_confirm_handoff`` represents
  the seller handing the goods to the courier. We map this to
  ``order.shipped`` (notifies the buyer; carries the tracking number
  from ``unitrade.delivery`` if one is recorded).
* ``unitrade.escrow.ledger.action_buyer_confirm_received`` represents
  the buyer acknowledging delivery. We map this to ``order.delivered``
  (notifies both the buyer and every distinct seller).
* ``sale.order.action_cancel`` covers ``order.cancelled`` — carries
  ``x_cancel_reason`` from the order record into the payload as a
  ``message_override`` so the buyer/seller see the reason inline.

Every emission is wrapped in :func:`_safe_emit` so a notification
failure (registry miss, mail rendering bug, SMTP outage) can never
abort the surrounding business transaction. The dispatcher's idempotency
key absorbs replay safely, including the case where ``action_confirm``
fires more than once during a payment retry.
"""

import logging

from odoo import models

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------
def _safe_emit(env, user_id, event_code, payload=None,
               idempotency_discriminator=None):
    """Invoke ``unitrade.notification.emit`` and swallow any exception.

    Order/escrow transactions must never be rolled back because of a
    notification problem — in-app delivery is best-effort relative to
    business correctness. Failures are logged at ``warning`` level so
    they remain debuggable without a paging-storm.
    """
    if not user_id:
        return
    Notification = env['unitrade.notification'].sudo()
    try:
        Notification.emit(
            user_id,
            event_code,
            payload=payload,
            idempotency_discriminator=idempotency_discriminator,
        )
    except Exception:  # pylint: disable=broad-except
        _logger.warning(
            "unitrade_notification: emit failed user_id=%s event_code=%s",
            user_id, event_code, exc_info=True,
        )


# ---------------------------------------------------------------------------
# sale.order hooks
# ---------------------------------------------------------------------------
class SaleOrderNotificationHooks(models.Model):
    _inherit = 'sale.order'

    # ------------------------------------------------------------------
    # Recipient resolution helpers (also reused by the escrow ledger
    # hooks below — they call these methods on the order recordset).
    # ------------------------------------------------------------------
    def _unitrade_buyer_user_id(self):
        """Return the buyer's ``res.users`` id, or ``False`` if absent.

        Mirrors the pattern used elsewhere in the codebase (e.g.
        ``_unitrade_voucher_buyer_user`` in ``unitrade_payment``):
        ``order.partner_id.user_ids[:1]``.
        """
        self.ensure_one()
        partner = self.partner_id
        if not partner or not partner.user_ids:
            return False
        return partner.user_ids[:1].id

    def _unitrade_seller_user_ids(self):
        """Return the set of distinct seller ``res.users`` ids in lines.

        Resolution chain:
            order_line → product_id.product_tmpl_id.x_seller_id
            unitrade.seller → user_id (res.users)

        Lines that don't carry a seller (service-fee lines, voucher
        discount lines, etc.) are silently skipped.
        """
        self.ensure_one()
        seller_ids = set()
        for line in self.order_line:
            product = line.product_id
            if not product:
                continue
            tmpl = product.product_tmpl_id
            seller = getattr(tmpl, 'x_seller_id', False)
            if not seller:
                continue
            user = getattr(seller, 'user_id', False)
            if user and user.id:
                seller_ids.add(user.id)
        return seller_ids

    # ------------------------------------------------------------------
    # action_confirm — Req 5.6 (new_for_seller) + Req 5.7 (confirmed)
    # ------------------------------------------------------------------
    def action_confirm(self):
        result = super().action_confirm()
        for order in self:
            buyer_id = order._unitrade_buyer_user_id()
            seller_user_ids = order._unitrade_seller_user_ids()

            # 1. Notify each distinct seller. The seller user id is
            # appended to the discriminator so multi-seller orders
            # produce one record per seller (the dispatcher's
            # idempotency key uses (event_code, ref_model, ref_id,
            # discriminator)).
            for seller_uid in seller_user_ids:
                _safe_emit(
                    self.env,
                    seller_uid,
                    'order.new_for_seller',
                    payload={
                        'reference_model': 'sale.order',
                        'reference_id': order.id,
                        'action_url': '/my/seller/orders/%d' % order.id,
                    },
                    idempotency_discriminator=str(seller_uid),
                )

            # 2. Notify the buyer of the confirmation.
            if buyer_id:
                _safe_emit(
                    self.env,
                    buyer_id,
                    'order.confirmed',
                    payload={
                        'reference_model': 'sale.order',
                        'reference_id': order.id,
                        'action_url': '/my/orders/%d' % order.id,
                    },
                )
        return result

    # ------------------------------------------------------------------
    # action_cancel — Req 5.10 (cancelled, carry reason)
    # ------------------------------------------------------------------
    def action_cancel(self):
        result = super().action_cancel()
        for order in self:
            buyer_id = order._unitrade_buyer_user_id()
            seller_user_ids = order._unitrade_seller_user_ids()
            reason = (
                getattr(order, 'x_cancel_reason', '') or ''
            ).strip()

            payload = {
                'reference_model': 'sale.order',
                'reference_id': order.id,
                'action_url': '/my/orders/%d' % order.id,
            }
            if reason:
                payload['message_override'] = (
                    "Pesanan dibatalkan: %s" % reason
                )

            # Buyer + every distinct seller. Per-recipient discriminator
            # so we get one record per recipient with deterministic
            # idempotency.
            recipients = set(seller_user_ids)
            if buyer_id:
                recipients.add(buyer_id)
            for uid in recipients:
                _safe_emit(
                    self.env,
                    uid,
                    'order.cancelled',
                    payload=payload,
                    idempotency_discriminator=str(uid),
                )
        return result


# ---------------------------------------------------------------------------
# unitrade.escrow.ledger hooks (shipped + delivered)
# ---------------------------------------------------------------------------
class UnitradeEscrowLedgerNotificationHooks(models.Model):
    _inherit = 'unitrade.escrow.ledger'

    def _unitrade_resi_for_order(self, order):
        """Best-effort tracking number lookup via ``unitrade.delivery``.

        Returns the most recent delivery's ``tracking_number`` for the
        order, or an empty string when the delivery model isn't loaded
        or no delivery has been recorded yet. Used to enrich the
        ``order.shipped`` notification body so the buyer sees the resi
        inline (Req 5.8).
        """
        Delivery = self.env.get('unitrade.delivery')
        if Delivery is None or not order:
            return ''
        delivery = Delivery.sudo().search(
            [('order_id', '=', order.id)],
            order='create_date desc',
            limit=1,
        )
        if not delivery:
            return ''
        return (delivery.tracking_number or '').strip()

    # ------------------------------------------------------------------
    # action_seller_confirm_handoff — Req 5.8 (order.shipped)
    # ------------------------------------------------------------------
    def action_seller_confirm_handoff(self, evidence=False, filename=False,
                                      location=False):
        # Capture the pre-call ``seller_confirmed_at`` so we can detect
        # the actual transition. Re-runs of the same action (the user
        # double-clicks the button, a retry on idempotent webhook, etc.)
        # already-confirmed ledgers are skipped, matching the design's
        # "shipped state transition" semantics.
        before = {
            ledger.id: bool(ledger.seller_confirmed_at)
            for ledger in self.sudo().exists()
        }
        result = super().action_seller_confirm_handoff(
            evidence=evidence, filename=filename, location=location,
        )
        for ledger in self.sudo().exists():
            if before.get(ledger.id):
                continue  # already shipped previously
            if not ledger.seller_confirmed_at:
                continue  # super may have refused
            order = ledger.order_id
            if not order:
                continue
            buyer_id = order._unitrade_buyer_user_id()
            if not buyer_id:
                continue

            payload = {
                'reference_model': 'sale.order',
                'reference_id': order.id,
                'action_url': '/my/orders/%d' % order.id,
            }
            resi = self._unitrade_resi_for_order(order)
            if resi:
                payload['message_override'] = (
                    "Pesanan dikirim. No. resi: %s" % resi
                )

            # Discriminator on the ledger id so multi-line orders with
            # one ledger per seller produce one shipped notification
            # per shipment — matches the "per-seller fulfilment" model.
            _safe_emit(
                self.env,
                buyer_id,
                'order.shipped',
                payload=payload,
                idempotency_discriminator=str(ledger.id),
            )
        return result

    # ------------------------------------------------------------------
    # action_buyer_confirm_received — Req 5.9 (order.delivered)
    # ------------------------------------------------------------------
    def action_buyer_confirm_received(self, evidence=False, filename=False):
        before = {
            ledger.id: bool(ledger.buyer_confirmed_at)
            for ledger in self.sudo().exists()
        }
        result = super().action_buyer_confirm_received(
            evidence=evidence, filename=filename,
        )
        for ledger in self.sudo().exists():
            if before.get(ledger.id):
                continue
            if not ledger.buyer_confirmed_at:
                continue
            order = ledger.order_id
            if not order:
                continue

            buyer_id = order._unitrade_buyer_user_id()
            seller_user_ids = order._unitrade_seller_user_ids()
            recipients = set(seller_user_ids)
            if buyer_id:
                recipients.add(buyer_id)

            payload = {
                'reference_model': 'sale.order',
                'reference_id': order.id,
                'action_url': '/my/orders/%d' % order.id,
            }
            for uid in recipients:
                # Per-(ledger, recipient) discriminator so each party
                # gets exactly one delivered notification per shipment.
                _safe_emit(
                    self.env,
                    uid,
                    'order.delivered',
                    payload=payload,
                    idempotency_discriminator='%d:%d' % (ledger.id, uid),
                )
        return result
