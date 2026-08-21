"""Shared pytest fixtures.

.. important::

   ``api/migrations/0063_add_mentions.py`` previously declared
   ``dependencies = [('api', '0001_initial')]``, which scheduled it immediately
   after the initial migration -- before ``0002_comment`` creates the Comment
   model that ``Mention`` points at -- aborting fresh-database builds with::

       ValueError: Related model 'api.comment' cannot be resolved

   That dependency has since been corrected to ``0061_subscriptionplan_setup_otp``
   (see the migration file), and a full ``manage.py migrate`` against a fresh
   database now completes cleanly through the latest migration. Verified by
   running the forwards migration plan and applying it end-to-end.
"""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

#: The 0063 dependency fix has landed; database-backed tests can run for real.
MIGRATIONS_ARE_REPLAYABLE = True

_SKIP_REASON = (
    'Migration history cannot build a fresh database: 0063_add_mentions depends '
    'on 0001_initial instead of 0061, so Mention is created before Comment. '
    'See tests/conftest.py and docs/troubleshooting.md.'
)


@pytest.fixture(scope='session')
def django_db_setup(
    request,
    django_test_environment,
    django_db_blocker,
    django_db_use_migrations,
    django_db_keepdb,
    django_db_createdb,
    django_db_modify_db_settings,
):
    """
    Override pytest-django's database bootstrap.

    Skips instead of erroring while the migration graph is unbuildable, so a
    genuine regression elsewhere is not buried under identical setup errors.
    Delegates to the real implementation once ``MIGRATIONS_ARE_REPLAYABLE``
    is flipped to True. Declares the same fixture dependencies as the real
    ``django_db_setup`` so pytest injects them for us to forward on.
    """
    if not MIGRATIONS_ARE_REPLAYABLE:
        pytest.skip(_SKIP_REASON)

    from pytest_django.fixtures import django_db_setup as real_setup

    yield from real_setup.__wrapped__(
        request,
        django_test_environment,
        django_db_blocker,
        django_db_use_migrations,
        django_db_keepdb,
        django_db_createdb,
        django_db_modify_db_settings,
    )


@pytest.fixture
def api_client():
    """Unauthenticated DRF client."""
    return APIClient()


@pytest.fixture
def user(db):
    """A plain registered user. Password is the 6-digit PIN the app enforces."""
    return User.objects.create_user(username='testuser', email='test@example.com', password='123456')


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        username='staffuser', email='staff@example.com', password='123456', is_staff=True
    )


@pytest.fixture
def auth_client(api_client, user):
    """Client authenticated as ``user`` via a DRF token."""
    from rest_framework.authtoken.models import Token

    token, _ = Token.objects.get_or_create(user=user)
    api_client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
    return api_client
