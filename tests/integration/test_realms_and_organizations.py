"""
Realms, roles, organization ownership and isolation.

The security property under test
--------------------------------
An organization user reaches their own organization's campaigns and nothing
else, and the owner of a campaign they create is decided by their account
rather than by their request. Everything else here supports those two.

Why so many tests are about what is REFUSED
-------------------------------------------
Access control is defined by its negative space. A test that an organization
maker can create a campaign proves the feature works; a test that they cannot
create one under a different organization proves the feature is worth having.
"""

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from api.models.campaign import Campaign
from api.models.organization import Organization, UserRealm, UserRole
from api.services.realms import (
    RealmValidationError,
    can_create_campaign,
    can_review_campaign,
    organization_for_new_campaign,
    validate_profile,
    visible_campaigns,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_user(username, realm=UserRealm.MEMBER, role=None, organization=None, **kwargs):
    """A user whose profile carries the given realm/role/organization.

    The profile itself is created by a post_save signal, so this updates the
    existing row rather than creating a second one.
    """
    user = User.objects.create_user(username=username, password='123456', **kwargs)
    profile = user.profile
    profile.realm = realm
    profile.role = role
    profile.organization = organization
    profile.save(update_fields=['realm', 'role', 'organization'])
    user.refresh_from_db()
    return user


@pytest.fixture
def org_a():
    return Organization.objects.create(name='Organization A', code='ORG-A', status='active')


@pytest.fixture
def org_b():
    return Organization.objects.create(name='Organization B', code='ORG-B', status='active')


@pytest.fixture
def member():
    return make_user('plain_member', realm=UserRealm.MEMBER)


@pytest.fixture
def flipstar_maker():
    return make_user('fs_maker', realm=UserRealm.FLIPSTAR, role=UserRole.MAKER)


@pytest.fixture
def a_maker(org_a):
    return make_user(
        'a_maker', realm=UserRealm.ORGANIZATION, role=UserRole.MAKER, organization=org_a
    )


@pytest.fixture
def a_checker(org_a):
    return make_user(
        'a_checker', realm=UserRealm.ORGANIZATION, role=UserRole.CHECKER, organization=org_a
    )


@pytest.fixture
def b_maker(org_b):
    return make_user(
        'b_maker', realm=UserRealm.ORGANIZATION, role=UserRole.MAKER, organization=org_b
    )


def campaign_for(organization, created_by=None, **kwargs):
    from datetime import timedelta

    from django.utils import timezone

    return Campaign.objects.create(
        title=kwargs.pop('title', f'Campaign {organization.name if organization else "platform"}'),
        description='d',
        prize_title='p',
        prize_description='pd',
        campaign_type='daily',
        start_date=timezone.now(),
        entry_deadline=timezone.now() + timedelta(days=7),
        organization=organization,
        created_by=created_by,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Realms exist and default safely
# ---------------------------------------------------------------------------


def test_a_new_user_defaults_to_member():
    """
    The migration-safety property, as behaviour.

    MEMBER is the least-privileged realm, so an account that should have been
    something else is merely under-powered until corrected. Defaulting to
    FLIPSTAR would hand platform access to every row that already exists.
    """
    user = User.objects.create_user(username='fresh', password='x')

    assert user.profile.realm == UserRealm.MEMBER
    assert user.profile.role is None
    assert user.profile.organization is None


def test_the_three_realms_are_the_documented_ones():
    assert [r[0] for r in UserRealm.choices] == ['FLIPSTAR', 'MEMBER', 'ORGANIZATION']


def test_role_is_optional_and_defaults_to_none(member):
    """No role is the normal state, not a gap."""
    assert member.profile.role is None


# ---------------------------------------------------------------------------
# Valid and invalid combinations
# ---------------------------------------------------------------------------


def test_flipstar_may_hold_either_role_or_none():
    for role in (UserRole.MAKER, UserRole.CHECKER, None):
        validate_profile(UserRealm.FLIPSTAR, role, None)


def test_organization_may_hold_either_role_or_none(org_a):
    for role in (UserRole.MAKER, UserRole.CHECKER, None):
        validate_profile(UserRealm.ORGANIZATION, role, org_a)


def test_a_member_may_not_be_a_maker():
    """
    Maker and checker are approval responsibilities over campaigns and money.
    An ordinary app user has no standing to carry either.
    """
    with pytest.raises(RealmValidationError, match='may not hold'):
        validate_profile(UserRealm.MEMBER, UserRole.MAKER, None)


def test_a_member_may_not_be_a_checker():
    with pytest.raises(RealmValidationError, match='may not hold'):
        validate_profile(UserRealm.MEMBER, UserRole.CHECKER, None)


def test_an_organization_account_without_an_organization_is_invalid():
    """
    The invariant the ownership model rests on.

    Such an account could be scoped to nothing and excluded from nothing.
    """
    with pytest.raises(RealmValidationError, match='must belong to an organization'):
        validate_profile(UserRealm.ORGANIZATION, UserRole.MAKER, None)


def test_a_member_may_not_belong_to_an_organization(org_a):
    """The converse: a member carrying an organization would silently sit
    inside that organization's data scope."""
    with pytest.raises(RealmValidationError, match='must not belong'):
        validate_profile(UserRealm.MEMBER, None, org_a)


def test_a_flipstar_account_may_not_belong_to_an_organization(org_a):
    with pytest.raises(RealmValidationError, match='must not belong'):
        validate_profile(UserRealm.FLIPSTAR, UserRole.MAKER, org_a)


def test_model_clean_surfaces_the_same_rules(member, org_a):
    """The admin and any ModelForm get the rule too, as a ValidationError."""
    member.profile.organization = org_a

    with pytest.raises(ValidationError):
        member.profile.full_clean()


def test_the_database_refuses_an_organization_user_without_an_organization(org_a, a_maker):
    """
    The constraint, not just the validation.

    clean() never runs for a bulk update or a psql session; the CheckConstraint
    does.
    """
    from django.db import IntegrityError, transaction

    from api.models import UserProfile

    with pytest.raises(IntegrityError), transaction.atomic():
        UserProfile.objects.filter(pk=a_maker.profile.pk).update(organization=None)


# ---------------------------------------------------------------------------
# Who may create a campaign
# ---------------------------------------------------------------------------


def test_an_organization_maker_may_create(a_maker):
    assert can_create_campaign(a_maker) is True


def test_a_flipstar_maker_may_create(flipstar_maker):
    assert can_create_campaign(flipstar_maker) is True


def test_a_flipstar_account_without_a_role_may_not_create():
    """
    Staff are not automatically campaign authors.

    Stated because it is the requirement most easily lost: "is Flipstar" is
    not the same as "may run campaigns".
    """
    plain_staff = make_user('fs_plain', realm=UserRealm.FLIPSTAR, role=None)

    assert can_create_campaign(plain_staff) is False


def test_a_checker_may_not_create(a_checker):
    """Makers author, checkers review. Keeping those apart is the point."""
    assert can_create_campaign(a_checker) is False


def test_a_member_may_not_create(member):
    assert can_create_campaign(member) is False


def test_an_existing_staff_admin_keeps_campaign_creation():
    """
    The regression this guards.

    admin_campaign_create was IsAdminUser before realms existed, and the admin
    dashboard still calls it. Every pre-existing account migrates to
    realm=MEMBER, so a realm-only check would refuse every staff admin who is
    not a superuser -- breaking a working screen. Staff access is kept as a
    documented bridge until staff carry FLIPSTAR + MAKER explicitly.
    """
    staff = User.objects.create_user(username='legacy_staff', password='x', is_staff=True)

    assert staff.profile.realm == UserRealm.MEMBER
    assert can_create_campaign(staff) is True


def test_a_non_staff_member_still_cannot_create():
    """The bridge is for staff only -- it must not widen to ordinary users."""
    ordinary = User.objects.create_user(username='not_staff', password='x')

    assert can_create_campaign(ordinary) is False


def test_a_superuser_may_create():
    su = User.objects.create_superuser(username='root', password='x')

    assert can_create_campaign(su) is True


# ---------------------------------------------------------------------------
# Ownership comes from the account
# ---------------------------------------------------------------------------


def test_a_campaign_belongs_to_its_creators_organization(a_maker, org_a):
    assert organization_for_new_campaign(a_maker) == org_a


def test_a_flipstar_campaign_has_no_organization(flipstar_maker):
    """NULL organization means a platform campaign -- which is also what every
    campaign predating this feature is."""
    assert organization_for_new_campaign(flipstar_maker) is None


def test_a_member_cannot_be_given_a_campaign_owner(member):
    with pytest.raises(RealmValidationError):
        organization_for_new_campaign(member)


def test_the_api_ignores_a_supplied_organization_id(a_maker, org_a, org_b):
    """
    The spoofing case, end to end.

    An organization A maker posts organization_id = B. The campaign must
    belong to A. The request is not rejected over the field -- it simply has
    no effect, because nothing reads it.
    """
    # The view is called directly rather than through the URL: a security
    # middleware rejects unauthenticated-looking requests with a plain 401
    # before DRF runs, which force_authenticate on APIClient does not satisfy.
    # This is the pattern the other API tests in this suite use.
    from rest_framework.test import APIRequestFactory, force_authenticate

    from api.views.campaign import admin_campaign_create

    request = APIRequestFactory().post(
        '/admin/campaigns/create/',
        {
            'title': 'Spoof attempt',
            'description': 'd',
            'prize_title': 'p',
            'prize_description': 'pd',
            'campaign_type': 'daily',
            # The spoof: this maker belongs to A and is naming B.
            'organization': org_b.id,
            'organization_id': org_b.id,
        },
        format='json',
    )
    force_authenticate(request, user=a_maker)
    response = admin_campaign_create(request)

    assert response.status_code in (200, 201), response.data
    campaign = Campaign.objects.get(title='Spoof attempt')
    assert campaign.organization_id == org_a.id, 'campaign was created under the wrong organization'


def test_a_member_cannot_reach_the_create_endpoint(member):
    from rest_framework.test import APIRequestFactory, force_authenticate

    from api.views.campaign import admin_campaign_create

    request = APIRequestFactory().post(
        '/admin/campaigns/create/', {'title': 'nope', 'description': 'd'}, format='json'
    )
    force_authenticate(request, user=member)
    response = admin_campaign_create(request)

    assert response.status_code in (401, 403)
    assert not Campaign.objects.filter(title='nope').exists()


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------


def test_an_organization_sees_only_its_own_campaigns(a_maker, org_a, org_b):
    campaign_for(org_a, title='A campaign')
    campaign_for(org_b, title='B campaign')
    campaign_for(None, title='Platform campaign')

    visible = visible_campaigns(a_maker, Campaign.objects.all())

    assert [c.title for c in visible] == ['A campaign']


def test_platform_campaigns_are_not_an_organizations_either(a_maker, org_a):
    """A NULL owner is Flipstar's, not "unowned and therefore everyone's"."""
    campaign_for(None, title='Platform only')

    assert visible_campaigns(a_maker, Campaign.objects.all()).count() == 0


def test_flipstar_sees_everything(flipstar_maker, org_a, org_b):
    campaign_for(org_a)
    campaign_for(org_b)
    campaign_for(None)

    assert visible_campaigns(flipstar_maker, Campaign.objects.all()).count() == 3


def test_a_member_sees_no_administrable_campaigns(member, org_a):
    """Public browsing goes through the existing public endpoints, which are
    untouched; this is the administrative scope."""
    campaign_for(org_a)

    assert visible_campaigns(member, Campaign.objects.all()).count() == 0


def test_an_organization_user_cannot_access_another_organizations_campaign(a_maker, org_b):
    from api.services.realms import can_access_campaign

    foreign = campaign_for(org_b)

    assert can_access_campaign(a_maker, foreign) is False


def test_an_organization_user_cannot_modify_another_organizations_campaign(a_maker, org_b):
    from api.services.realms import can_modify_campaign

    foreign = campaign_for(org_b)

    assert can_modify_campaign(a_maker, foreign) is False


def test_a_checker_cannot_approve_another_organizations_campaign(a_checker, org_b, b_maker):
    foreign = campaign_for(org_b, created_by=b_maker, status='submitted')

    assert can_review_campaign(a_checker, foreign) is False


# ---------------------------------------------------------------------------
# Separation of duties
# ---------------------------------------------------------------------------


def test_a_checker_may_approve_a_colleagues_campaign(a_checker, a_maker, org_a):
    campaign = campaign_for(org_a, created_by=a_maker, status='submitted')

    assert can_review_campaign(a_checker, campaign) is True


def test_a_checker_may_not_approve_their_own_campaign(a_checker, org_a):
    """
    An approval step the author can perform is not an approval step.

    Reached when one person holds both roles over time, or when a checker
    authors a campaign directly.
    """
    own = campaign_for(org_a, created_by=a_checker, status='submitted')

    assert can_review_campaign(a_checker, own) is False


def test_a_checker_may_not_approve_a_campaign_they_submitted(a_checker, a_maker, org_a):
    """Submitting is authorship too, for this purpose."""
    campaign = campaign_for(org_a, created_by=a_maker, status='submitted')
    campaign.submitted_by = a_checker
    campaign.save(update_fields=['submitted_by'])

    assert can_review_campaign(a_checker, campaign) is False


def test_a_maker_cannot_approve_at_all(a_maker, org_a):
    """Reviewing requires the checker role, whoever wrote the campaign."""
    campaign = campaign_for(org_a, created_by=None, status='submitted')

    assert can_review_campaign(a_maker, campaign) is False


# ---------------------------------------------------------------------------
# The API contract
# ---------------------------------------------------------------------------


def test_the_user_payload_carries_realm_role_and_organization(a_maker, org_a):
    from api.serializers.core import UserSerializer

    data = UserSerializer(a_maker).data

    assert data['realm'] == 'ORGANIZATION'
    assert data['role'] == 'MAKER'
    assert data['organization'] == {'id': org_a.id, 'name': 'Organization A'}


def test_a_members_payload_reports_null_role_and_organization(member):
    from api.serializers.core import UserSerializer

    data = UserSerializer(member).data

    assert data['realm'] == 'MEMBER'
    assert data['role'] is None
    assert data['organization'] is None


def test_the_organization_payload_exposes_nothing_internal(a_maker):
    """Only id and name. Not status, not who created it."""
    from api.serializers.core import UserSerializer

    organization = UserSerializer(a_maker).data['organization']

    assert set(organization) == {'id', 'name'}


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


def test_existing_campaigns_without_an_organization_remain_valid():
    """
    Every campaign that predates this feature has organization NULL, which
    means "platform campaign" -- the truth for those rows. Inventing an owner
    for them would be a guess with access-control consequences.
    """
    campaign = campaign_for(None)

    assert campaign.organization_id is None
    assert campaign.pk is not None


def test_the_original_campaign_statuses_still_exist():
    """The approval states were added alongside, not instead of."""
    values = {c[0] for c in Campaign.STATUS_CHOICES}

    assert {'draft', 'active', 'voting', 'completed', 'cancelled'} <= values
    assert {'submitted', 'approved', 'rejected'} <= values


def test_an_ordinary_user_is_unaffected_by_any_of_this():
    """
    Registration, login and the profile all behave as before for a member.

    This is the regression that would matter most: the feature must be
    invisible to the users who are not part of it.
    """
    user = User.objects.create_user(username='ordinary', password='123456')

    assert user.profile.realm == UserRealm.MEMBER
    assert user.profile.role is None
    assert user.profile.organization is None
    assert user.check_password('123456')
