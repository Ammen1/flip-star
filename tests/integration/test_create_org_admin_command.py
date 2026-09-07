"""
The bootstrap command: creating the first organization administrator.

Why it exists
-------------
Appointing organization administrators is a Super-Admin-only API act, which is
correct -- but it leaves a chicken and egg on a fresh install. This command is
the way in, and these tests are what make it safe to hand to an operator.
"""

import pytest
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.core.management import CommandError, call_command

from api.models.organization import Organization, UserRealm, UserRole

pytestmark = pytest.mark.django_db


def run(**kwargs):
    kwargs.setdefault('org_name', 'ABC Company')
    kwargs.setdefault('org_code', 'abc')
    kwargs.setdefault('username', 'abc_admin')
    kwargs.setdefault('password', 'sup3rsecret')
    call_command('create_org_admin', **kwargs)


def test_it_creates_the_organization_and_the_admin():
    run()

    org = Organization.objects.get(code='ABC')
    user = User.objects.get(username='abc_admin')
    assert org.name == 'ABC Company'
    assert user.profile.realm == UserRealm.ORGANIZATION
    assert user.profile.role == UserRole.ADMIN
    assert user.profile.organization_id == org.id


def test_the_code_is_upper_cased():
    """So `abc` and `ABC` cannot become two organizations."""
    run(org_code='abc')

    assert Organization.objects.filter(code='ABC').exists()


def test_the_account_can_actually_log_in():
    """The whole point -- an ordinary auth.User, no second auth system."""
    run()

    assert authenticate(username='abc_admin', password='sup3rsecret') is not None


def test_the_account_is_not_staff():
    """
    It must land on the organization dashboard, not the Super Admin console.

    AdminApp routes on realm; staff would take a different branch entirely.
    """
    run()

    user = User.objects.get(username='abc_admin')
    assert user.is_staff is False
    assert user.is_superuser is False


def test_rerunning_updates_rather_than_duplicating():
    run()
    run(org_name='ABC Company Renamed')

    assert Organization.objects.filter(code='ABC').count() == 1
    assert User.objects.filter(username='abc_admin').count() == 1
    assert Organization.objects.get(code='ABC').name == 'ABC Company Renamed'


def test_rerunning_resets_the_password():
    """How a forgotten password is recovered."""
    run()
    run(password='a-new-password')

    assert authenticate(username='abc_admin', password='a-new-password') is not None
    assert authenticate(username='abc_admin', password='sup3rsecret') is None


def test_the_password_is_hashed():
    run()

    user = User.objects.get(username='abc_admin')
    assert user.password != 'sup3rsecret'
    assert user.check_password('sup3rsecret')


def test_a_maker_role_is_accepted():
    run(role='MAKER')

    assert User.objects.get(username='abc_admin').profile.role == UserRole.MAKER


def test_a_suspended_organization_can_be_created_deliberately():
    run(status='suspended')

    assert Organization.objects.get(code='ABC').status == 'suspended'


def test_an_empty_password_is_refused():
    """
    No defaulted password, for the same reason create_superadmin has none: a
    literal default once created accounts with a password published in this
    repository.
    """
    with pytest.raises(CommandError):
        run(password='')

    assert not User.objects.filter(username='abc_admin').exists()


def test_a_failure_leaves_nothing_behind():
    """
    One transaction.

    A rejected realm/role must not leave an organization created and a user
    half-configured.
    """
    before_orgs = Organization.objects.count()
    before_users = User.objects.count()

    with pytest.raises(CommandError):
        run(password='')

    assert Organization.objects.count() == before_orgs
    assert User.objects.count() == before_users
