# -*- coding: utf-8 -*-
"""Shared Hypothesis strategies for `unitrade_notification` PBT suite.

Why this module is self-contained
---------------------------------
Per ``tasks.md`` (task 1.2), the event registry lives in a sibling task that
ships in parallel with this one. To break the import-time circular dependency
(strategies → registry → models package, which is partially initialized while
the registry task is being built), the canonical event-code list is mirrored
here as a frozen tuple. Once both tasks are merged the registry remains the
runtime source of truth; this list is the test-time mirror.

If a future event_code is added to ``EVENT_REGISTRY``, append it to
``ALL_EVENT_CODES`` below and re-categorize it in
``CRITICAL_EVENT_CODES`` / ``NON_CRITICAL_EVENT_CODES``. A smoke test in
task 10.2 will catch drift between the two lists.

Strategies exposed
------------------
- ``event_codes()`` — any registered event_code.
- ``critical_event_codes()`` — event_codes whose category is in
  ``{account, order, payment}`` (Property 4).
- ``non_critical_event_codes()`` — the complement.
- ``payloads()`` — typical dispatcher payload dicts.
- ``urls()`` — mix of valid/invalid action_url candidates (Property 16).
- ``counts()`` — non-negative integers up to 10_000 (Property 8).
- ``build_notification(env, ...)`` — savepoint-friendly factory used by
  ``setUp`` of property tests (Property 5–7).

Importing this module also activates the ``'odoo'`` Hypothesis profile via
:mod:`unitrade_notification.tests.conftest`.
"""

from hypothesis import strategies as st

# Side-effect import: registers and loads the ``'odoo'`` Hypothesis profile
# (max_examples=100, deadline=None) so any test module that imports the
# strategies inherits the right runtime configuration.
from . import conftest  # noqa: F401


# ---------------------------------------------------------------------------
# Event-code mirror (kept in sync with models/event_registry.py via 10.2).
# Source of truth at runtime: EVENT_REGISTRY in models/event_registry.py.
# ---------------------------------------------------------------------------

#: 18 event_codes covering the 7 categories of design §Event_Registry.
ALL_EVENT_CODES = (
    # account
    'account.welcome',
    'account.password_reset',
    # seller
    'seller.application_received',
    'seller.approved',
    'seller.rejected',
    # order
    'order.new_for_seller',
    'order.confirmed',
    'order.shipped',
    'order.delivered',
    'order.cancelled',
    # payment
    'payment.success',
    'payment.pending',
    'payment.failed',
    'payment.expired',
    # chat
    'chat.new_message',
    # review
    'review.reminder',
    'review.new_for_seller',
    # system
    'system.announcement',
)

#: Categories whose in-app notifications cannot be disabled by user
#: preference (design §Event_Registry → CRITICAL_CATEGORIES, Property 4).
CRITICAL_CATEGORIES = frozenset({'account', 'order', 'payment'})


def _category_of(event_code):
    """Return the category prefix of an event_code (substring before '.')."""
    return event_code.split('.', 1)[0]


CRITICAL_EVENT_CODES = tuple(
    code for code in ALL_EVENT_CODES if _category_of(code) in CRITICAL_CATEGORIES
)
NON_CRITICAL_EVENT_CODES = tuple(
    code for code in ALL_EVENT_CODES if _category_of(code) not in CRITICAL_CATEGORIES
)


# ---------------------------------------------------------------------------
# Public Hypothesis strategies.
# ---------------------------------------------------------------------------

def event_codes():
    """Strategy: any event_code present in the registry."""
    return st.sampled_from(ALL_EVENT_CODES)


def critical_event_codes():
    """Strategy: event_codes whose category is critical (account/order/payment)."""
    return st.sampled_from(CRITICAL_EVENT_CODES)


def non_critical_event_codes():
    """Strategy: event_codes whose category is *not* critical."""
    return st.sampled_from(NON_CRITICAL_EVENT_CODES)


# Sensitive keys are intentionally NOT generated here — Property 14 has its
# own focused strategy. This generic payload strategy keeps the input space
# small and realistic so unrelated properties stay fast.
_PAYLOAD_REFERENCE_MODELS = st.sampled_from((
    'sale.order',
    'res.partner',
    'unitrade.seller.application',
    'unitrade.chat.message',
    'unitrade.review',
    False,  # absent reference
))

_PAYLOAD_EXTRA_VALUES = st.one_of(
    st.text(max_size=32),
    st.integers(min_value=-1_000_000, max_value=1_000_000),
    st.booleans(),
)


def payloads():
    """Strategy: typical dispatcher payload dicts.

    Keys mirror the documented contract in ``models/notification.py``:
    ``reference_model`` (str | False), ``reference_id`` (int >= 0),
    ``title_override`` / ``message_override`` (optional), and a free-form
    ``extra`` mapping. Values are bounded so each example stays cheap.
    """
    return st.fixed_dictionaries(
        mapping={
            'reference_model': _PAYLOAD_REFERENCE_MODELS,
            'reference_id': st.integers(min_value=0, max_value=2 ** 31 - 1),
        },
        optional={
            'title_override': st.text(min_size=0, max_size=80),
            'message_override': st.text(min_size=0, max_size=240),
            'extra': st.dictionaries(
                keys=st.text(
                    alphabet=st.characters(min_codepoint=33, max_codepoint=126),
                    min_size=1,
                    max_size=24,
                ),
                values=_PAYLOAD_EXTRA_VALUES,
                max_size=5,
            ),
        },
    )


# ---------------------------------------------------------------------------
# URL strategy — mixed inputs for Property 16 (Action URL Whitelist).
# ---------------------------------------------------------------------------

_RELATIVE_PATH_SEGMENT = st.text(
    alphabet=st.characters(
        whitelist_categories=('Ll', 'Lu', 'Nd'),
        whitelist_characters='-_',
    ),
    min_size=1,
    max_size=12,
)

_ALLOWED_HOSTS = st.sampled_from((
    'unitrade.example.com',
    'app.unitrade.example.com',
))

_DISALLOWED_HOSTS = st.sampled_from((
    'evil.example.org',
    'phisher.test',
    '127.0.0.1',
    'attacker.unitrade-fake.com',
))

_VALID_RELATIVE_URLS = st.builds(
    lambda segs: '/' + '/'.join(segs),
    st.lists(_RELATIVE_PATH_SEGMENT, min_size=1, max_size=4),
)

_VALID_HTTPS_ALLOWLIST_URLS = st.builds(
    lambda host, segs: 'https://' + host + '/' + '/'.join(segs),
    _ALLOWED_HOSTS,
    st.lists(_RELATIVE_PATH_SEGMENT, min_size=0, max_size=3),
)

_HTTPS_OUTSIDE_ALLOWLIST_URLS = st.builds(
    lambda host, segs: 'https://' + host + '/' + '/'.join(segs),
    _DISALLOWED_HOSTS,
    st.lists(_RELATIVE_PATH_SEGMENT, min_size=0, max_size=3),
)

_JAVASCRIPT_URLS = st.builds(
    lambda body: 'javascript:' + body,
    st.text(max_size=32),
)

_MALFORMED_URLS = st.one_of(
    st.just(''),
    st.just('   '),
    st.just('not a url'),
    st.just('http://'),
    st.just('://missing-scheme'),
    st.just('ftp://example.com/file'),
    st.text(
        alphabet=st.characters(min_codepoint=33, max_codepoint=126),
        min_size=1,
        max_size=24,
    ),
)


def urls():
    """Strategy: mix of url candidates designed to exercise the whitelist.

    Yields, with roughly balanced weight:

    - relative internal paths (``/foo/bar``) — should be accepted unchanged,
    - https URLs whose host is in ``unitrade.notification.allowed_url_prefixes``
      — should be accepted unchanged,
    - https URLs whose host is *not* in the allowlist — should be rejected,
    - ``javascript:...`` URIs — should be rejected,
    - malformed strings (empty, whitespace, missing scheme, garbage) —
      should be rejected.
    """
    return st.one_of(
        _VALID_RELATIVE_URLS,
        _VALID_HTTPS_ALLOWLIST_URLS,
        _HTTPS_OUTSIDE_ALLOWLIST_URLS,
        _JAVASCRIPT_URLS,
        _MALFORMED_URLS,
    )


def counts():
    """Strategy: non-negative integers up to 10_000 (Property 8 badge)."""
    return st.integers(min_value=0, max_value=10_000)


# ---------------------------------------------------------------------------
# Record-building helper for property setUp.
# ---------------------------------------------------------------------------

def build_notification(env, user_id, **overrides):
    """Create one ``unitrade.notification`` record under a savepoint.

    Intended use::

        with self.env.cr.savepoint():
            rec = build_notification(self.env, user_id=self.user.id,
                                     event_code='order.confirmed')
            ... assertions ...
        # savepoint rolled back automatically

    The savepoint context is the caller's responsibility — Hypothesis'
    ``@given`` runs each example in isolation and the surrounding
    ``TransactionCase`` already wraps the whole test in one. Keeping the
    helper savepoint-agnostic lets it be reused in both modes.

    Required arg:
        ``env`` — an ``odoo.api.Environment`` (typically ``self.env``).
        ``user_id`` — int, the target ``res.users`` id.

    Optional kwargs (passed through to ``create``):
        ``title`` — defaults to ``'Test notification'``.
        ``message`` — defaults to ``''``.
        ``category`` — defaults to ``'system'``.
        ``event_code`` — defaults to ``'system.announcement'``.
        Any other key supported by the model schema.
    """
    vals = {
        'user_id': user_id,
        'title': overrides.pop('title', 'Test notification'),
        'message': overrides.pop('message', ''),
        'category': overrides.pop('category', 'system'),
        'event_code': overrides.pop('event_code', 'system.announcement'),
    }
    vals.update(overrides)
    return env['unitrade.notification'].create(vals)


__all__ = (
    'ALL_EVENT_CODES',
    'CRITICAL_CATEGORIES',
    'CRITICAL_EVENT_CODES',
    'NON_CRITICAL_EVENT_CODES',
    'event_codes',
    'critical_event_codes',
    'non_critical_event_codes',
    'payloads',
    'urls',
    'counts',
    'build_notification',
)
