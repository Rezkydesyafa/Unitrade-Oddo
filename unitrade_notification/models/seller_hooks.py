"""Caller-side wiring for seller lifecycle notifications.

This module *inherits* (`_inherit`) the two existing seller models
shipped by ``unitrade_seller`` so the notification dispatcher can be
wired in without ``unitrade_seller`` having to import
``unitrade_notification`` (which would create a circular module
dependency since ``unitrade_notification.__manifest__`` already lists
``unitrade_seller`` in ``depends``).

Three seller events are emitted per task 15.2 of the design (Req 5.3 /
5.4 / 5.5):

* ``seller.application_received`` — when a user submits a seller
  application. Fired from two code paths to support both onboarding
  flows that exist in the project:

  - Legacy flow on ``unitrade.seller`` via
    :meth:`UnitradeSeller.action_submit_verification` (``draft`` →
    ``pending``).
  - New OCR-driven flow on ``unitrade.seller.verification`` whose
    ``state`` lands on ``pending`` or ``manual_review`` after the
    upload is processed (auto-``approved`` and instant-``rejected``
    states are not "received-and-awaiting-review" so they do not emit
    this event from this hook).

* ``seller.approved`` — emitted from ``unitrade.seller.write/create``
  whenever the canonical seller record's ``status`` lands on
  ``verified``. This single source-of-truth covers all three approval
  paths in the codebase (legacy ``action_verify``, OCR-auto-approve in
  the public controller, and admin approval via
  ``unitrade.seller.verification.action_approve`` which itself writes
  ``status='verified'`` on the seller record).

* ``seller.rejected`` — emitted from two code paths because rejection
  can happen on either model independently:

  - Legacy ``unitrade.seller`` rejection (``status='rejected'``) via
    :meth:`UnitradeSeller.action_reject`.
  - ``unitrade.seller.verification`` rejection
    (``state='rejected'``) via :meth:`SellerVerification.action_reject`,
    which never touches a ``unitrade.seller`` row and would otherwise
    be silent.

  The rejection reason from the seller / verification record is
  forwarded as ``payload['message_override']`` so the in-app card and
  the email body show the actual reason instead of the generic default
  message.

Each emission is wrapped in ``try/except`` and only logs a warning on
failure: notification delivery must never abort a seller workflow
(Req 9.5 / Property 19).
"""

from odoo import api, models
import logging

_logger = logging.getLogger(__name__)


def _emit_safely(env, user_id, event_code, payload, discriminator):
    """Call ``unitrade.notification.emit`` and swallow any error.

    The dispatcher itself is defensive (it raises only on programming
    errors such as an unknown event code), but the caller-side wiring
    must be doubly safe: a failed seller notification must never
    abort the seller submit / approve / reject transaction the user
    is performing.
    """
    if not user_id:
        return
    try:
        env['unitrade.notification'].sudo().emit(
            user_id,
            event_code,
            payload=payload,
            idempotency_discriminator=discriminator,
        )
    except Exception:  # pylint: disable=broad-except
        _logger.warning(
            "unitrade_notification seller hook: emit failed "
            "user_id=%s event_code=%s discriminator=%s",
            user_id, event_code, discriminator, exc_info=True,
        )


class UnitradeSellerNotificationHooks(models.Model):
    """Wires lifecycle notifications onto the existing ``unitrade.seller``."""

    _inherit = 'unitrade.seller'

    # ------------------------------------------------------------------
    # seller.application_received — legacy onboarding path
    # ------------------------------------------------------------------
    def action_submit_verification(self):
        """Emit ``seller.application_received`` after the parent submit.

        ``super()`` does the actual ``draft`` → ``pending`` transition,
        OCR run, and existing email template. We fire the dispatcher
        only if the parent call did not raise, so a validation error
        on the seller does not produce a misleading "we received your
        application" notification.
        """
        result = super().action_submit_verification()
        for record in self:
            user_id = record.user_id.id if record.user_id else False
            _emit_safely(
                self.env, user_id, 'seller.application_received',
                payload={
                    'reference_model': self._name,
                    'reference_id': record.id,
                    'action_url': '/seller-onboarding',
                },
                discriminator='seller:%s' % record.id,
            )
        return result

    # ------------------------------------------------------------------
    # seller.approved / seller.rejected — canonical status transitions
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        """Emit lifecycle events when sellers are *created* in a final state.

        Required because the public OCR auto-approve flow in
        ``controllers/seller_verification.py`` constructs a brand-new
        ``unitrade.seller`` row with ``status='verified'`` directly,
        bypassing :meth:`action_verify` entirely. The ``write`` hook
        below would not see that transition (there is no "before"
        record) so we cover it here.
        """
        records = super().create(vals_list)
        for record in records:
            self._emit_for_status(record, old_status=None,
                                  new_status=record.status)
        return records

    def write(self, vals):
        """Emit lifecycle events when ``status`` transitions on existing rows.

        Snapshots ``status`` *before* delegating to ``super().write`` so
        we can compare and emit only on real transitions. This catches
        both :meth:`action_verify` (legacy admin approval) and
        :meth:`unitrade.seller.verification.action_approve` (new flow)
        because both ultimately write ``status='verified'`` on this
        model.
        """
        track_status = 'status' in vals
        before = {r.id: r.status for r in self} if track_status else {}
        result = super().write(vals)
        if track_status:
            for record in self:
                old_status = before.get(record.id)
                new_status = record.status
                if old_status == new_status:
                    continue
                self._emit_for_status(record, old_status=old_status,
                                      new_status=new_status)
        return result

    def _emit_for_status(self, record, old_status, new_status):
        """Map a seller status transition to the matching event code.

        Centralised so :meth:`create` and :meth:`write` share exactly
        the same payload-building / idempotency-key logic. Returns
        early when the transition does not correspond to a notifiable
        event (e.g. ``draft`` → ``pending`` is handled by
        :meth:`action_submit_verification` instead).
        """
        if not record.user_id:
            return
        if new_status == 'verified':
            event_code = 'seller.approved'
            payload = {
                'reference_model': self._name,
                'reference_id': record.id,
                'action_url': '/unitrade/seller/dashboard',
            }
        elif new_status == 'rejected':
            event_code = 'seller.rejected'
            payload = {
                'reference_model': self._name,
                'reference_id': record.id,
                'action_url': '/seller-onboarding',
            }
            reason = record.rejection_reason
            if reason:
                payload['message_override'] = reason
        else:
            return
        _emit_safely(
            self.env, record.user_id.id, event_code, payload,
            # Discriminator includes the target status so re-entering
            # ``verified`` after a revoke -> re-approve cycle produces
            # a fresh notification rather than collapsing into the
            # earlier idempotency key.
            discriminator='seller:%s:%s' % (record.id, new_status),
        )


class UnitradeSellerVerificationNotificationHooks(models.Model):
    """Wires the OCR-driven onboarding path's notifications.

    The ``unitrade.seller.verification`` model is the entry point for
    new-style seller onboarding: a partner uploads their KTM, OCR runs,
    and the record's ``state`` lands on ``approved`` / ``manual_review``
    / ``rejected`` / ``pending``. Approvals eventually reach
    ``unitrade.seller`` (where the lifecycle hook above takes over)
    but two cases need explicit wiring on the verification model:

    1. ``application_received`` — the verification row may sit in
       ``pending`` or ``manual_review`` for hours/days waiting for an
       admin. The user should be told "we got your KTM" immediately,
       even though no ``unitrade.seller`` row exists yet.

    2. ``rejected`` — the verification model's
       :meth:`SellerVerification.action_reject` only writes the
       verification row and never creates / updates a
       ``unitrade.seller`` record, so the seller-side hook would
       never fire.
    """

    _inherit = 'unitrade.seller.verification'

    # State values that mean "we have your application and it is
    # awaiting review". ``approved`` and ``rejected`` are terminal
    # outcomes handled by their own events.
    _APPLICATION_RECEIVED_STATES = frozenset({'pending', 'manual_review'})

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if record.state in self._APPLICATION_RECEIVED_STATES:
                self._emit_application_received(record)
        return records

    def write(self, vals):
        """Catch state transitions into ``pending``/``manual_review``.

        Re-uploads after a rejection write the existing verification
        row back to ``pending``; emitting again is harmless because
        the dispatcher's idempotency key (anchored on
        ``unitrade.seller.verification`` + record id) collapses
        repeats into the existing notification record (Property 1).
        """
        track_state = 'state' in vals
        before = {r.id: r.state for r in self} if track_state else {}
        result = super().write(vals)
        if track_state:
            for record in self:
                old_state = before.get(record.id)
                new_state = record.state
                if old_state == new_state:
                    continue
                if new_state in self._APPLICATION_RECEIVED_STATES:
                    self._emit_application_received(record)
        return result

    def action_reject(self):
        """Emit ``seller.rejected`` after the parent rejection logic.

        The parent implementation writes ``state='rejected'`` and the
        ``rejection_reason``, so by the time we run the record holds
        the final reason text we want to forward in
        ``payload['message_override']``.
        """
        result = super().action_reject()
        for record in self:
            user_id = self._resolve_verification_user_id(record)
            if not user_id:
                continue
            payload = {
                'reference_model': self._name,
                'reference_id': record.id,
                'action_url': '/seller-onboarding',
            }
            reason = record.rejection_reason
            if reason:
                payload['message_override'] = reason
            _emit_safely(
                self.env, user_id, 'seller.rejected', payload,
                discriminator='verification:%s:rejected' % record.id,
            )
        return result

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _emit_application_received(self, record):
        user_id = self._resolve_verification_user_id(record)
        if not user_id:
            return
        _emit_safely(
            self.env, user_id, 'seller.application_received',
            payload={
                'reference_model': self._name,
                'reference_id': record.id,
                'action_url': '/seller-onboarding',
            },
            # Anchor the discriminator on the record id only — multiple
            # state transitions on the same verification row (e.g.
            # rejected -> re-uploaded -> pending) collapse onto the
            # same idempotency key so the user does not receive a
            # second "received" notification.
            discriminator='verification:%s' % record.id,
        )

    def _resolve_verification_user_id(self, record):
        """Map the verification record's ``partner_id`` to a ``res.users``.

        The verification model stores only a partner; UniTrade
        partners always have at most one portal user attached via
        ``res.partner.user_ids``. Returns ``False`` when no user is
        resolvable, which the safe-emit helper treats as a no-op.
        """
        partner = record.partner_id
        if not partner:
            return False
        user = partner.user_ids[:1]
        return user.id if user else False
