# -*- coding: utf-8 -*-
"""Test infrastructure for `unitrade_notification` PBT suite.

Registers and activates the ``'odoo'`` Hypothesis profile so every
property-based test in this module runs with the same iteration budget and
without the default per-example deadline (which would flake against Odoo's
ORM-bound fixtures).

Importing this module is sufficient to make the profile active; tests that
depend on it should ``from .strategies import ...`` (which in turn imports
this module) or import this module directly. The profile parameters mirror
``design.md §Testing Strategy`` and ``tasks.md`` task 1.2.
"""

from hypothesis import HealthCheck, settings


# Public name so test modules can `settings.load_profile(PROFILE_NAME)` in
# rare cases where they want to override and then restore.
PROFILE_NAME = 'odoo'


# Some PBT scenarios exercise the ORM under nested savepoints, which can be
# slower than Hypothesis' default expectation. We disable the related health
# checks so legitimate but slow ORM iterations do not abort the run; the
# correctness signal still comes from the property assertions themselves.
_SUPPRESSED_HEALTH_CHECKS = (
    HealthCheck.too_slow,
    HealthCheck.function_scoped_fixture,
)


settings.register_profile(
    PROFILE_NAME,
    max_examples=100,
    deadline=None,
    suppress_health_check=list(_SUPPRESSED_HEALTH_CHECKS),
)
settings.load_profile(PROFILE_NAME)


# Pytest hook (no-op when running under Odoo's unittest-based runner). Kept
# so that running the same files under pytest also picks up the profile in
# case a future contributor wires `pytest-odoo` into the toolchain.
def pytest_configure(config):  # pragma: no cover - convenience for pytest
    settings.load_profile(PROFILE_NAME)
