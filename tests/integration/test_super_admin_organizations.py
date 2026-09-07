"""
Super Admin: organizations, organization administrators, and the one place a
client-supplied organization id is honoured.

The asymmetry under test
------------------------
``organization_for_new_campaign`` takes an optional organization id. Super
Admin may use it -- that is the dashboard's organization selector. An
organization user may not: for them the parameter is inert and their own
organization is returned whatever the request said.

One endpoint, two behaviours, decided by the account. Most of this file exists
to prove the second half, because a gate that opens for the wrong person is
worse than no gate at all.
"""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIRequestFactory, force_authenticate

from api.models.campaign import Campaign
from api.models.organization import Organization, UserRealm, UserRole
from api.services.realms import RealmValidationError, organization_for_new_campaign
from api.views import organizations as views

pytestmark = pytest.mark.django_db

factory = APIRequestFactory()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_user(username, realm=UserRealm.MEMBER, role=None, organization=None, **kwargs):
    user = User.objects.create_user(username=username, password='123456', **kwargs)
    profile = user.profile
    profile.realm = realm
    profile.role = role
    profile.organization = organization
    profile.save(update_fields=['realm', 'role', 'organization'])
    return user


@pytest.fixture
def superadmin():
    return User.objects.create_superuser(username='sa_root', password='x')


@pytest.fixture
def org_a():
    return Organization.objects.create(name='Alpha Co', code='ALPHA', status='active')


@pytest.fixture
def org_b():
    return Organization.objects.create(name='Beta Co', code='BETA', status='active')


@pytest.fixture
def a_admin(org_a):
    return make_user('sa_a_admin', UserRealm.ORGANIZATION, UserRole.ADMIN, org_a)


def call(view, user, method='get', data=None, **kwargs):
    request = getattr(factory, method)('/x/', data or {}, format='json')
    force_authenticate(request, user=user)
    return view(request, **kwargs)


# ---------------------------------------------------------------------------
# The ADMIN role
# ---------------------------------------------------------------------------


def test_admin_is_a_valid_organization_role(org_a):
    from api.services.realms import validate_profile

    validate_profile(UserRealm.ORGANIZATION, UserRole.ADMIN, org_a)


def test_a_member_still_cannot_be_an_admin():
    from api.services.realms import validate_profile

    with pytest.raises(RealmValidationError, match='may not hold'):
        validate_profile(UserRealm.MEMBER, UserRole.ADMIN, None)


def test_an_org_admin_can_author_campaigns(a_admin):
    """ADMIN carries maker rights: running an organization includes authoring
    its campaigns."""
    from api.services.realms import can_author, can_create_campaign

    assert can_author(a_admin) is True
    assert can_create_campaign(a_admin) is True


def test_an_org_admin_is_not_platform_staff(a_admin):
    """
    The distinction that matters.

    An organization admin administers one organization. Django's is_staff
    administers the site. Conflating them hands every organization admin the
    run of the platform.
    """
    from api.services.realms import is_flipstar

    assert a_admin.is_staff is False
    assert is_flipstar(a_admin) is False


def test_the_maker_role_stays_distinct_from_admin(a_admin):
    """Separation of duties asks who authored, not who may -- so `is_maker`
    must remain an exact question."""
    from api.services.realms import is_maker

    assert is_maker(a_admin) is False


# ---------------------------------------------------------------------------
# Super Admin: organizations
# ---------------------------------------------------------------------------


def test_super_admin_can_create_an_organization(superadmin):
    response = call(
        views.organization_list_create,
        superadmin,
        method='post',
        data={'name': 'Gamma Co', 'code': 'gamma', 'contact_email': 'x@gamma.test'},
    )

    assert response.status_code == 201, response.data
    org = Organization.objects.get(name='Gamma Co')
    assert org.code == 'GAMMA', 'code should be normalised to upper case'
    assert org.created_by_id == superadmin.id


def test_creating_an_organization_requires_a_code(superadmin):
    response = call(
        views.organization_list_create, superadmin, method='post', data={'name': 'No Code Co'}
    )

    assert response.status_code == 400
    assert not Organization.objects.filter(name='No Code Co').exists()


def test_a_duplicate_code_is_refused(superadmin, org_a):
    response = call(
        views.organization_list_create,
        superadmin,
        method='post',
        data={'name': 'Different Name', 'code': 'ALPHA'},
    )

    assert response.status_code == 409


def test_super_admin_can_list_and_search(superadmin, org_a, org_b):
    listing = call(views.organization_list_create, superadmin)
    assert listing.data['count'] == 2

    request = factory.get('/x/', {'search': 'alpha'})
    force_authenticate(request, user=superadmin)
    filtered = views.organization_list_create(request)

    assert [o['code'] for o in filtered.data['results']] == ['ALPHA']


def test_super_admin_can_deactivate_an_organization(superadmin, org_a):
    response = call(
        views.organization_detail,
        superadmin,
        method='patch',
        data={'status': 'suspended'},
        organization_id=org_a.id,
    )

    assert response.status_code == 200
    org_a.refresh_from_db()
    assert org_a.status == 'suspended'


def test_organization_detail_reports_campaign_statistics(superadmin, org_a):
    from datetime import timedelta

    from django.utils import timezone

    for status_value in ('draft', 'active', 'completed'):
        Campaign.objects.create(
            title=f'{status_value} one',
            description='d',
            prize_title='p',
            prize_description='pd',
            campaign_type='daily',
            start_date=timezone.now(),
            entry_deadline=timezone.now() + timedelta(days=1),
            organization=org_a,
            status=status_value,
        )

    response = call(views.organization_detail, superadmin, organization_id=org_a.id)

    stats = response.data['campaign_stats']
    assert stats['total'] == 3
    assert stats['active'] == 1
    assert stats['draft'] == 1
    assert stats['completed'] == 1


def test_an_organization_admin_cannot_reach_the_organization_endpoints(a_admin):
    """
    Creating organizations is not something an organization may do for itself.
    """
    response = call(views.organization_list_create, a_admin)

    assert response.status_code == 403


def test_a_member_cannot_reach_the_organization_endpoints():
    member = make_user('sa_member', UserRealm.MEMBER)

    response = call(views.organization_list_create, member)

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Super Admin: organization administrators
# ---------------------------------------------------------------------------


def test_super_admin_can_create_an_organization_admin(superadmin, org_a):
    response = call(
        views.create_organization_admin,
        superadmin,
        method='post',
        data={'username': 'alpha_admin', 'email': 'admin@alpha.test', 'password': 'sup3rsecret'},
        organization_id=org_a.id,
    )

    assert response.status_code == 201, response.data
    created = User.objects.get(username='alpha_admin')
    assert created.profile.realm == UserRealm.ORGANIZATION
    assert created.profile.role == UserRole.ADMIN
    assert created.profile.organization_id == org_a.id


def test_the_password_is_hashed_and_never_returned(superadmin, org_a):
    """
    Never store or echo a plaintext credential.

    The response body ends up in logs, browser history and proxies; a live
    password there is a leak regardless of who requested it.
    """
    response = call(
        views.create_organization_admin,
        superadmin,
        method='post',
        data={'username': 'alpha_admin2', 'password': 'sup3rsecret'},
        organization_id=org_a.id,
    )

    assert 'password' not in response.data
    assert 'sup3rsecret' not in str(response.data)

    created = User.objects.get(username='alpha_admin2')
    assert created.password != 'sup3rsecret'
    assert created.check_password('sup3rsecret'), 'the password must still work'


def test_the_new_admin_can_authenticate(superadmin, org_a):
    """No second auth system: this is an ordinary auth.User."""
    from django.contrib.auth import authenticate

    call(
        views.create_organization_admin,
        superadmin,
        method='post',
        data={'username': 'alpha_admin3', 'password': 'sup3rsecret'},
        organization_id=org_a.id,
    )

    assert authenticate(username='alpha_admin3', password='sup3rsecret') is not None


def test_a_duplicate_username_is_refused(superadmin, org_a):
    User.objects.create_user(username='taken', password='x')

    response = call(
        views.create_organization_admin,
        superadmin,
        method='post',
        data={'username': 'taken', 'password': 'y'},
        organization_id=org_a.id,
    )

    assert response.status_code == 409


def test_an_organization_admin_cannot_create_another_admin(a_admin, org_a):
    """Appointing administrators is a platform-level act."""
    response = call(
        views.create_organization_admin,
        a_admin,
        method='post',
        data={'username': 'self_appointed', 'password': 'x'},
        organization_id=org_a.id,
    )

    assert response.status_code == 403
    assert not User.objects.filter(username='self_appointed').exists()


def test_a_failed_profile_assignment_leaves_no_account(superadmin, org_a):
    """
    The account and its realm move together.

    A signal creates the profile on user creation, so without a transaction a
    failure while assigning realm would leave a live account holding a
    password its intended owner had been given.
    """
    response = call(
        views.create_organization_admin,
        superadmin,
        method='post',
        data={'username': 'bad_role', 'password': 'x', 'role': 'NOT_A_ROLE'},
        organization_id=org_a.id,
    )

    assert response.status_code == 400
    assert not User.objects.filter(username='bad_role').exists()


# ---------------------------------------------------------------------------
# The asymmetry
# ---------------------------------------------------------------------------


def test_super_admin_may_choose_the_organization(superadmin, org_a, org_b):
    """The dashboard's organization selector."""
    assert organization_for_new_campaign(superadmin, org_a.id) == org_a
    assert organization_for_new_campaign(superadmin, org_b.id) == org_b


def test_super_admin_choosing_a_missing_organization_is_refused(superadmin):
    with pytest.raises(RealmValidationError, match='does not exist'):
        organization_for_new_campaign(superadmin, 99999)


def test_an_org_admin_cannot_choose_another_organization(a_admin, org_a, org_b):
    """
    The security-critical half.

    Same function, same parameter, different account: the requested id is
    ignored entirely and the user's own organization comes back.
    """
    assert organization_for_new_campaign(a_admin, org_b.id) == org_a


def test_an_org_admin_cannot_even_choose_their_own_organization_explicitly(a_admin, org_a):
    """The parameter is inert for them -- not validated, not consulted."""
    assert organization_for_new_campaign(a_admin, org_a.id) == org_a
    assert organization_for_new_campaign(a_admin, None) == org_a


def test_the_create_endpoint_honours_the_selector_for_super_admin(superadmin, org_b):
    from api.views.campaign import admin_campaign_create

    request = factory.post(
        '/admin/campaigns/create/',
        {
            'title': 'Platform-made for Beta',
            'description': 'd',
            'prize_title': 'p',
            'prize_description': 'pd',
            'campaign_type': 'daily',
            'organization': org_b.id,
        },
        format='json',
    )
    force_authenticate(request, user=superadmin)
    response = admin_campaign_create(request)

    assert response.status_code in (200, 201), response.data
    campaign = Campaign.objects.get(title='Platform-made for Beta')
    assert campaign.organization_id == org_b.id


def test_the_create_endpoint_ignores_the_selector_for_an_org_admin(a_admin, org_a, org_b):
    """The spoof, through the endpoint, with the selector now a real feature."""
    from api.views.campaign import admin_campaign_create

    request = factory.post(
        '/admin/campaigns/create/',
        {
            'title': 'Attempted cross-org',
            'description': 'd',
            'prize_title': 'p',
            'prize_description': 'pd',
            'campaign_type': 'daily',
            'organization': org_b.id,
            'organization_id': org_b.id,
        },
        format='json',
    )
    force_authenticate(request, user=a_admin)
    response = admin_campaign_create(request)

    assert response.status_code in (200, 201), response.data
    campaign = Campaign.objects.get(title='Attempted cross-org')
    assert campaign.organization_id == org_a.id, 'the selector was honoured for a non-staff user'


def test_a_flipstar_maker_may_also_choose(org_b):
    """Platform staff, not only superusers."""
    staff = make_user('sa_fs', UserRealm.FLIPSTAR, UserRole.MAKER)

    assert organization_for_new_campaign(staff, org_b.id) == org_b


def test_a_member_cannot_choose_at_all(org_b):
    member = make_user('sa_member2', UserRealm.MEMBER)

    with pytest.raises(RealmValidationError):
        organization_for_new_campaign(member, org_b.id)
