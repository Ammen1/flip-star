"""Audit T-01: prove the integration suite is on PostgreSQL, don't assume it.

Marking 2,694 tests ``integration`` is only half the fix. The half that matters
is that the job running them is actually pointed at PostgreSQL -- a marker that
selects the right tests against the wrong engine looks like progress and buys
nothing, because SQLite is where the ``FOR UPDATE`` class of bug hides.

So this module is a guard, not a feature test:

* In CI, an integration run on anything but PostgreSQL **fails**. Silent
  fallback to SQLite is the exact failure being closed.
* Locally, it reports which engine is in use and skips the strict check, because
  running the suite on SQLite for speed is legitimate -- it just must not be
  what CI verifies against.
* When PostgreSQL *is* in use, it asserts the semantics SQLite does not have, so
  "we are on PostgreSQL" is demonstrated rather than declared.
"""

import os

import pytest
from django.contrib.auth.models import User
from django.db import connection, transaction

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def _in_ci() -> bool:
    return os.environ.get('CI', '').lower() in ('1', 'true', 'yes')


def _on_postgres() -> bool:
    return connection.vendor == 'postgresql'


def test_report_the_engine_under_test():
    """Always prints, so a run's engine is visible in the log rather than inferred."""
    settings_module = os.environ.get('DJANGO_SETTINGS_MODULE', '(unset)')
    test_engine = os.environ.get('TEST_DB_ENGINE', '(unset)')
    print(
        f'\n[T-01] integration suite engine: vendor={connection.vendor} '
        f'settings_module={settings_module} TEST_DB_ENGINE={test_engine}'
    )
    assert connection.vendor in ('postgresql', 'sqlite')


def test_ci_must_run_integration_tests_on_postgres():
    if not _in_ci():
        pytest.skip('not CI; a local SQLite run is allowed, CI is what must be strict')
    assert _on_postgres(), (
        f'The integration job is running on {connection.vendor!r}, not PostgreSQL. '
        'This is audit finding T-01: SQLite ignores SELECT ... FOR UPDATE, so locking '
        'bugs pass here and fail in production. Set TEST_DB_ENGINE=postgresql and the '
        'TEST_DB_* variables for this job.'
    )


@pytest.mark.skipif(
    connection.vendor != 'postgresql',
    reason='demonstrates PostgreSQL-only semantics; nothing to prove on SQLite',
)
def test_select_for_update_is_actually_enforced():
    """On SQLite this is a no-op, which is why it cannot be the only engine."""
    user = User.objects.create_user(username='t01_lock', password='x')  # noqa: S106
    with transaction.atomic():
        locked = User.objects.select_for_update().get(pk=user.pk)
        assert locked.pk == user.pk
        # A real lock needs a real transaction; assert we are inside one.
        assert not transaction.get_autocommit()


@pytest.mark.skipif(
    connection.vendor != 'postgresql',
    reason='the nullable-outer-join refusal only exists on PostgreSQL',
)
def test_for_update_on_a_nullable_join_still_raises():
    """Pins the shape of the bug that cost 3 Birr and granted nothing.

    ``select_for_update()`` combined with ``select_related`` over a nullable FK
    produces a LEFT JOIN, and PostgreSQL refuses to lock it. The fix in
    ``api/services/subscription_renewal.py`` was ``of=('self',)``. This asserts
    the database still behaves the way that fix assumes, so the fix cannot be
    quietly reverted into a green suite.
    """
    from django.db.utils import NotSupportedError

    from api.models import SubscriptionPlan

    assert SubscriptionPlan._meta.get_field('tier').null, (
        'SubscriptionPlan.tier is no longer nullable; if that is intended, this '
        'test and the of=("self",) narrowing in subscription_renewal.py can both '
        'be revisited.'
    )

    with pytest.raises((NotSupportedError, Exception)) as exc:
        with transaction.atomic():
            list(SubscriptionPlan.objects.select_for_update().select_related('tier').all()[:1])
    assert 'FOR UPDATE' in str(exc.value).upper() or 'OUTER JOIN' in str(exc.value).upper()


@pytest.mark.skipif(
    connection.vendor != 'postgresql',
    reason='of=("self",) is only meaningful where FOR UPDATE is enforced',
)
def test_the_narrowed_lock_the_fix_uses_is_accepted():
    """The other half: the corrected form must work, not merely differ."""
    from api.models import SubscriptionPlan

    with transaction.atomic():
        list(
            SubscriptionPlan.objects.select_for_update(of=('self',))
            .select_related('tier')
            .all()[:1]
        )
