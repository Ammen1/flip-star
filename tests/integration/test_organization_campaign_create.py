"""
An organization creating a campaign.

Why these go through the full stack
-----------------------------------
The bug this covers was not in a permission class -- it was
``AdminPathGuardMiddleware``, which refuses every ``/api/v1/admin/`` path to
non-staff accounts. An organization admin is deliberately not staff, so the
dashboard's Create Campaign button was rejected before any view or permission
class ran, with a bare "You do not have permission to perform this action."

``APIRequestFactory`` calls a view directly and never runs middleware, so a
test written that way passes whether or not the bug is present. Everything
here uses ``APIClient`` against the real URL instead.
"""

import pytest
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from api.models.campaign import Campaign
from api.models.organization import Organization, UserRealm, UserRole

pytestmark = pytest.mark.django_db

CREATE_URL = '/api/v1/organization/campaigns/create/'
ADMIN_CREATE_URL = '/api/v1/admin/campaigns/create/'

PAYLOAD = {
    'title': 'Summer Campaign',
    'description': 'A description',
    'prize_title': 'Cash',
    'prize_description': '10k',
    'campaign_type': 'daily',
}


@pytest.fixture
def organization():
    return Organization.objects.create(name='ABC Company', code='ABC', status='active')


@pytest.fixture
def other_organization():
    return Organization.objects.create(name='Rival Ltd', code='RIV', status='active')


def make_client(user):
    client = APIClient()
    token, _ = Token.objects.get_or_create(user=user)
    client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
    return client


def org_user(username, organization, role):
    user = User.objects.create_user(username=username, password='x')
    profile = user.profile
    profile.realm = UserRealm.ORGANIZATION
    profile.role = role
    profile.organization = organization
    profile.save(update_fields=['realm', 'role', 'organization'])
    return user


@pytest.fixture
def admin_user(organization):
    return org_user('abc_admin', organization, UserRole.ADMIN)


# ---------------------------------------------------------------------------
# The bug
# ---------------------------------------------------------------------------


def test_the_admin_prefix_is_what_blocked_them(admin_user):
    """The failure being fixed, pinned so it cannot be misdiagnosed again.

    This is the guard doing its job -- the endpoint is staff-only. It is
    recorded here because the message it returns says nothing about staff, and
    that is what made the cause hard to see.
    """
    response = make_client(admin_user).post(ADMIN_CREATE_URL, PAYLOAD)

    assert response.status_code == 403
    assert response.json()['detail'] == 'You do not have permission to perform this action.'


def test_an_organization_admin_can_create_a_campaign(admin_user):
    response = make_client(admin_user).post(CREATE_URL, PAYLOAD)

    assert response.status_code == 201, response.json()
    assert response.json()['title'] == 'Summer Campaign'


def test_a_maker_can_create_a_campaign(organization):
    maker = org_user('abc_maker', organization, UserRole.MAKER)

    response = make_client(maker).post(CREATE_URL, PAYLOAD)

    assert response.status_code == 201, response.json()


def test_a_checker_cannot(organization):
    """Checkers review; they do not author."""
    checker = org_user('abc_checker', organization, UserRole.CHECKER)

    response = make_client(checker).post(CREATE_URL, PAYLOAD)

    assert response.status_code == 403


def test_an_ordinary_member_cannot():
    member = User.objects.create_user(username='nobody', password='x')

    response = make_client(member).post(CREATE_URL, PAYLOAD)

    assert response.status_code == 403


def test_it_still_needs_authentication():
    response = APIClient().post(CREATE_URL, PAYLOAD)

    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Ownership comes from the account
# ---------------------------------------------------------------------------


def test_the_campaign_belongs_to_the_creators_organization(admin_user, organization):
    response = make_client(admin_user).post(CREATE_URL, PAYLOAD)

    campaign = Campaign.objects.get(pk=response.json()['id'])
    assert campaign.organization_id == organization.id
    assert campaign.created_by_id == admin_user.id


def test_an_organization_in_the_body_is_ignored(admin_user, organization, other_organization):
    """The isolation guarantee: no request can file a campaign under another org."""
    response = make_client(admin_user).post(
        CREATE_URL, {**PAYLOAD, 'organization': other_organization.id}
    )

    assert response.status_code == 201, response.json()
    campaign = Campaign.objects.get(pk=response.json()['id'])
    assert campaign.organization_id == organization.id


def test_a_platform_superuser_is_told_to_use_the_admin_endpoint():
    """A platform campaign is unowned, which this endpoint cannot express."""
    root = User.objects.create_superuser(username='root', email='r@x.com', password='x')

    response = make_client(root).post(CREATE_URL, PAYLOAD)

    assert response.status_code == 403
    assert response.json()['code'] == 'not_an_organization_account'


# ---------------------------------------------------------------------------
# The approval workflow cannot be skipped
# ---------------------------------------------------------------------------


def test_a_new_campaign_is_a_draft(admin_user):
    response = make_client(admin_user).post(CREATE_URL, PAYLOAD)

    assert response.json()['status'] == 'draft'


def test_a_requested_status_is_refused_entry(admin_user):
    """
    The one that matters.

    If `status` were accepted, a maker could create an already-active campaign
    and never face a checker -- an approval step the author can skip is not an
    approval step.
    """
    response = make_client(admin_user).post(CREATE_URL, {**PAYLOAD, 'status': 'active'})

    assert response.status_code == 201, response.json()
    assert Campaign.objects.get(pk=response.json()['id']).status == 'draft'


def test_an_approved_status_cannot_be_smuggled_in(admin_user):
    response = make_client(admin_user).post(CREATE_URL, {**PAYLOAD, 'status': 'approved'})

    assert Campaign.objects.get(pk=response.json()['id']).status == 'draft'


# ---------------------------------------------------------------------------
# Input handling
# ---------------------------------------------------------------------------


def test_a_title_is_required(admin_user):
    response = make_client(admin_user).post(CREATE_URL, {**PAYLOAD, 'title': ''})

    assert response.status_code == 400
    assert not Campaign.objects.exists()


def test_a_whitespace_title_is_still_blank(admin_user):
    response = make_client(admin_user).post(CREATE_URL, {**PAYLOAD, 'title': '   '})

    assert response.status_code == 400


def test_omitted_text_fields_do_not_crash(admin_user):
    """
    description/prize_title/prize_description are NOT NULL with no default.

    Without the '' fallback this reaches the database as None and surfaces as
    an IntegrityError rather than a created campaign.
    """
    response = make_client(admin_user).post(CREATE_URL, {'title': 'Bare minimum'})

    assert response.status_code == 201, response.json()


def test_blank_dates_do_not_reach_the_database(admin_user):
    """A form posting empty optional fields must not write '' into a date column."""
    response = make_client(admin_user).post(
        CREATE_URL, {**PAYLOAD, 'start_date': '', 'entry_deadline': ''}
    )

    assert response.status_code == 201, response.json()
    campaign = Campaign.objects.get(pk=response.json()['id'])
    assert campaign.start_date is None
