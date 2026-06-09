"""Review notification hooks for the UniTrade Notification System.

Task 15.6 — wire ``review.new_for_seller`` emissions to the dispatcher
whenever a buyer publishes a product review on ``unitrade.review``.

The hook lives inside ``unitrade_notification`` (rather than in
``unitrade_review``) because ``unitrade_notification`` already declares
``unitrade_review`` in its manifest ``depends``; placing the hook here
avoids the reverse dependency and the import cycle that would result.

Schema notes (cf. ``unitrade_review/models/review.py``)
------------------------------------------------------
* ``unitrade.review`` has no ``state`` field. Visibility is controlled
  by the boolean ``is_visible`` (default ``True``).
* The buyer is on ``user_id`` (``res.users``).
* The seller is reached through
  ``product_id.x_seller_id.user_id`` (``unitrade.seller.user_id``).
  ``product_template`` also exposes a stored related field
  ``x_seller_user_id`` which we prefer when present because it remains
  meaningful even after the seller record is unlinked.

Lifecycle
---------
Most reviews are visible the moment they are created (``is_visible``
defaults to ``True``), so the ``create`` override is the primary
trigger. A ``write`` override additionally covers the moderation flow
where a review may be hidden first (``is_visible=False``) and later
made visible — that is the second moment in which the seller should
learn about it. Re-running ``write`` with the same flip is a no-op
because the dispatcher's deterministic idempotency key collapses the
duplicate.

Failure handling
----------------
Any exception raised during the dispatcher call is caught and logged
at ``WARNING`` level. A failed bell ping must never break the buyer's
review submission.

Skipped cases
-------------
* The seller cannot be resolved from the review (missing product,
  missing seller link, or seller has no backing ``res.users``).
* The reviewer is the seller themselves (defensive — should not
  normally happen because constraint ``order_unique`` ties the review
  to a sale order, and a seller cannot buy their own product, but the
  guard keeps the hook safe under future schema changes).
"""

import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class UnitradeReviewNotificationHook(models.Model):
    """Inherit ``unitrade.review`` to emit ``review.new_for_seller``.

    The hook only adds behaviour to ``create`` and ``write``; no new
    fields and no new storage. Inheritance is via the standard
    ``_inherit`` form so the underlying table is unchanged.
    """

    _inherit = 'unitrade.review'

    # ------------------------------------------------------------------
    # ORM overrides
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        reviews = super().create(vals_list)
        for review in reviews:
            if not review.is_visible:
                # Hidden on creation (e.g. awaiting moderation). The
                # ``write`` override below will fire when it is flipped
                # to visible.
                continue
            self._unitrade_notification_emit_review(review)
        return reviews

    def write(self, vals):
        # Only inspect transitions when ``is_visible`` is actually being
        # written. Capturing ``before`` for every ``write`` would be
        # unnecessary overhead.
        track_visibility = 'is_visible' in vals
        before = (
            {r.id: bool(r.is_visible) for r in self}
            if track_visibility else {}
        )
        result = super().write(vals)
        if track_visibility:
            for review in self:
                was_visible = before.get(review.id, False)
                now_visible = bool(review.is_visible)
                if not was_visible and now_visible:
                    self._unitrade_notification_emit_review(review)
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _unitrade_notification_emit_review(self, review):
        """Emit ``review.new_for_seller`` for the seller of ``review``.

        Wraps the dispatcher call in ``try/except`` so a notification
        failure can never abort the buyer's review submission.
        """
        try:
            review_su = review.sudo()
            seller_user_id = self._unitrade_resolve_seller_user_id(review_su)
            if not seller_user_id:
                return

            # Defensive: don't ping the seller about their own review.
            reviewer = review_su.user_id
            if reviewer and reviewer.id == seller_user_id:
                return

            product = review_su.product_id
            product_name = product.name if product else 'produk Anda'
            reviewer_name = (reviewer.name if reviewer else None) or 'pembeli'

            payload = {
                'reference_model': 'unitrade.review',
                'reference_id': review_su.id,
                'recipient_scope': 'seller',
                'title_override': 'Ulasan baru untuk %s' % product_name,
                'message_override': '%s memberikan ulasan %d bintang.' % (
                    reviewer_name, review_su.rating or 0,
                ),
            }
            if product:
                payload['action_url'] = '/unitrade/seller/products/%s' % product.id

            Notification = self.env['unitrade.notification'].sudo()
            Notification.emit(
                seller_user_id,
                'review.new_for_seller',
                payload=payload,
            )
        except Exception:  # pylint: disable=broad-except
            _logger.warning(
                "review.new_for_seller emit failed for review_id=%s",
                review.id,
                exc_info=True,
            )

    def _unitrade_resolve_seller_user_id(self, review):
        """Return the ``res.users`` id of the seller of ``review``.

        Walks the standard UniTrade product → seller → user chain:
        ``review.product_id`` → ``product.template.x_seller_id``
        (``unitrade.seller``) → ``unitrade.seller.user_id``. The stored
        related shortcut ``product.template.x_seller_user_id`` is
        preferred when present because it survives even when the
        seller record itself is later archived.

        Returns ``False`` when any link in the chain is missing — the
        caller treats that as "skip this emission".
        """
        product = getattr(review, 'product_id', False)
        if not product:
            return False

        # Preferred path: stored related field on product.template.
        seller_user = getattr(product, 'x_seller_user_id', False)
        if seller_user and seller_user.id:
            return seller_user.id

        # Fallback path: traverse via the seller record.
        seller = getattr(product, 'x_seller_id', False)
        if seller and getattr(seller, 'user_id', False) and seller.user_id.id:
            return seller.user_id.id

        return False
