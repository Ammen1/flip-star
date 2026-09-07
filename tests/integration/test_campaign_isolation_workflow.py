"""
Organization isolation across campaign operations, and the maker/checker
workflow.

Companion to test_realms_and_organizations.py, which covers the realm model
itself. This covers what an organization user can and cannot *do* through the
endpoints.

The property being defended
---------------------------
A campaign id is not an authorization token. Knowing that campaign 123 exists
must not let anyone read, edit, delete, submit, approve or reject it -- only
belonging to the organization that owns it does. Every "cannot" test below is
the same claim aimed at a different verb.

Why the refusals are 404 and not 403
------------------------------------
403 on someone else's campaign confirms the id exists, which turns any detail
endpoint into an enumeration oracle: walk the ids and learn how many campaigns
a competitor runs. 404 tells an outsider nothing -- "not yours" and "not a
thing" look identical.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.http import Http404
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from api.models.campaign import Campaign
from api.models.organization import Organization, UserRealm, UserRole
from api.services.campaign_workflow import (
    WorkflowError,
    approve,
    get_campaign_for,
    reject,
    submit,
)
from api.views import organization_campaigns as views

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
def org_a():
    return Organization.objects.create(name='Org A', code='ORG-A', status='active')


@pytest.fixture
def org_b():
    return Organization.objects.create(name='Org B', code='ORG-B', status='active')


@pytest.fixture
def a_maker(org_a):
    return make_user('iso_a_maker', UserRealm.ORGANIZATION, UserRole.MAKER, org_a)


@pytest.fixture
def a_checker(org_a):
    return make_user('iso_a_checker', UserRealm.ORGANIZATION, UserRole.CHECKER, org_a)


@pytest.fixture
def b_maker(org_b):
    return make_user('iso_b_maker', UserRealm.ORGANIZATION, UserRole.MAKER, org_b)


@pytest.fixture
def b_checker(org_b):
    return make_user('iso_b_checker', UserRealm.ORGANIZATION, UserRole.CHECKER, org_b)


@pytest.fixture
def member():
    return make_user('iso_member', UserRealm.MEMBER)


def make_campaign(organization, created_by=None, status='draft', title=None):
    return Campaign.objects.create(
        title=title or f'{organization.name if organization else "Platform"} campaign',
        description='a description',
        prize_title='Prize',
        prize_description='pd',
        campaign_type='daily',
        start_date=timezone.now(),
        entry_deadline=timezone.now() + timedelta(days=7),
        organization=organization,
        created_by=created_by,
        status=status,
    )


def call(view, user, method='get', path='/x/', data=None, **kwargs):
    request = getattr(factory, method)(path, data or {}, format='json')
    force_authenticate(request, user=user)
    return view(request, **kwargs)


# ---------------------------------------------------------------------------
# 1-4  list and detail
# ---------------------------------------------------------------------------


def test_org_a_can_list_its_campaigns(a_maker, org_a):
    make_campaign(org_a, title='A one')

    response = call(views.organization_campaign_list, a_maker)

    assert response.status_code == 200
    assert [c['title'] for c in response.data['results']] == ['A one']


def test_org_a_cannot_list_org_b_campaigns(a_maker, org_a, org_b):
    make_campaign(org_a, title='A one')
    make_campaign(org_b, title='B one')

    response = call(views.organization_campaign_list, a_maker)

    titles = [c['title'] for c in response.data['results']]
    assert titles == ['A one']
    assert response.data['count'] == 1, 'the count leaked another organization'


def test_org_a_can_view_its_campaign(a_maker, org_a):
    campaign = make_campaign(org_a)

    response = call(views.organization_campaign_detail, a_maker, campaign_id=campaign.id)

    assert response.status_code == 200
    assert response.data['id'] == campaign.id


def test_org_a_cannot_view_org_b_campaign(a_maker, org_b):
    foreign = make_campaign(org_b)

    response = call(views.organization_campaign_detail, a_maker, campaign_id=foreign.id)

    assert response.status_code == 404, 'another organization campaign was returned'


# ---------------------------------------------------------------------------
# 5-8  update and delete
# ---------------------------------------------------------------------------


def test_org_a_can_update_its_campaign(a_maker, org_a):
    campaign = make_campaign(org_a)

    response = call(
        views.organization_campaign_update,
        a_maker,
        method='patch',
        data={'title': 'Renamed'},
        campaign_id=campaign.id,
    )

    assert response.status_code == 200
    campaign.refresh_from_db()
    assert campaign.title == 'Renamed'


def test_org_a_cannot_update_org_b_campaign(a_maker, org_b):
    foreign = make_campaign(org_b, title='Untouched')

    response = call(
        views.organization_campaign_update,
        a_maker,
        method='patch',
        data={'title': 'Hacked'},
        campaign_id=foreign.id,
    )

    assert response.status_code == 404
    foreign.refresh_from_db()
    assert foreign.title == 'Untouched'


def test_org_a_can_delete_its_draft_campaign(a_maker, org_a):
    campaign = make_campaign(org_a)

    response = call(
        views.organization_campaign_delete, a_maker, method='delete', campaign_id=campaign.id
    )

    assert response.status_code == 204
    assert not Campaign.objects.filter(pk=campaign.pk).exists()


def test_org_a_cannot_delete_org_b_campaign(a_maker, org_b):
    foreign = make_campaign(org_b)

    response = call(
        views.organization_campaign_delete,
        a_maker,
        method='delete',
        campaign_id=foreign.id,
    )

    assert response.status_code == 404
    assert Campaign.objects.filter(pk=foreign.pk).exists()


def test_an_approved_campaign_cannot_be_deleted(a_maker, org_a):
    """Entries, engagement and rewards may already hang off it."""
    campaign = make_campaign(org_a, status='approved')

    response = call(
        views.organization_campaign_delete, a_maker, method='delete', campaign_id=campaign.id
    )

    assert response.status_code == 409
    assert Campaign.objects.filter(pk=campaign.pk).exists()


# ---------------------------------------------------------------------------
# 17-20  spoofing
# ---------------------------------------------------------------------------


def test_update_cannot_reassign_ownership(a_maker, org_a, org_b):
    """
    The headline spoof.

    `organization` is absent from EDITABLE_FIELDS, so the key is ignored --
    the request succeeds and the campaign stays where it was.
    """
    campaign = make_campaign(org_a)

    call(
        views.organization_campaign_update,
        a_maker,
        method='patch',
        data={'title': 'ok', 'organization': org_b.id, 'organization_id': org_b.id},
        campaign_id=campaign.id,
    )

    campaign.refresh_from_db()
    assert campaign.organization_id == org_a.id, 'ownership was reassigned by the client'


def test_update_cannot_set_status_directly(a_maker, org_a):
    """
    The workflow bypass.

    A client PATCHing {"status": "approved"} must not skip review. Status is
    not editable; it moves only through submit/approve/reject.
    """
    campaign = make_campaign(org_a, status='draft')

    call(
        views.organization_campaign_update,
        a_maker,
        method='patch',
        data={'status': 'approved'},
        campaign_id=campaign.id,
    )

    campaign.refresh_from_db()
    assert campaign.status == 'draft', 'status was changed without review'


def test_a_foreign_campaign_id_does_not_bypass_the_lookup(a_maker, org_b):
    """The service-level guarantee the views rest on."""
    foreign = make_campaign(org_b)

    with pytest.raises(Http404):
        get_campaign_for(a_maker, foreign.id)


def test_the_lookup_finds_a_campaign_in_the_users_own_organization(a_maker, org_a):
    campaign = make_campaign(org_a)

    assert get_campaign_for(a_maker, campaign.id).pk == campaign.pk


# ---------------------------------------------------------------------------
# 21-29  maker / checker workflow
# ---------------------------------------------------------------------------


def test_a_maker_can_submit(a_maker, org_a):
    campaign = make_campaign(org_a, created_by=a_maker)

    response = call(
        views.organization_campaign_submit, a_maker, method='post', campaign_id=campaign.id
    )

    assert response.status_code == 200
    campaign.refresh_from_db()
    assert campaign.status == 'submitted'
    assert campaign.submitted_by_id == a_maker.id


def test_the_submitter_is_recorded_from_the_account_not_the_request(a_maker, org_a, a_checker):
    """The audit trail is written by the backend, so it cannot be forged."""
    campaign = make_campaign(org_a, created_by=a_maker)

    call(
        views.organization_campaign_submit,
        a_maker,
        method='post',
        data={'submitted_by': a_checker.id},
        campaign_id=campaign.id,
    )

    campaign.refresh_from_db()
    assert campaign.submitted_by_id == a_maker.id


def test_an_incomplete_campaign_cannot_be_submitted(a_maker, org_a):
    campaign = make_campaign(org_a, created_by=a_maker)
    Campaign.objects.filter(pk=campaign.pk).update(prize_title='')
    campaign.refresh_from_db()

    with pytest.raises(WorkflowError, match='must be filled in'):
        submit(campaign, a_maker)


def test_a_member_cannot_submit(member, org_a):
    campaign = make_campaign(org_a)

    with pytest.raises(WorkflowError, match='maker'):
        submit(campaign, member)


def test_a_checker_cannot_submit(a_checker, org_a):
    """Makers author and submit; checkers review. Keeping those apart is the
    whole point of the workflow."""
    campaign = make_campaign(org_a)

    with pytest.raises(WorkflowError, match='maker'):
        submit(campaign, a_checker)


def test_a_checker_can_approve_a_colleagues_campaign(a_maker, a_checker, org_a):
    campaign = make_campaign(org_a, created_by=a_maker, status='submitted')

    response = call(
        views.organization_campaign_approve, a_checker, method='post', campaign_id=campaign.id
    )

    assert response.status_code == 200
    campaign.refresh_from_db()
    assert campaign.status == 'approved'
    assert campaign.approved_by_id == a_checker.id


def test_a_checker_can_reject_with_a_reason(a_maker, a_checker, org_a):
    campaign = make_campaign(org_a, created_by=a_maker, status='submitted')

    call(
        views.organization_campaign_reject,
        a_checker,
        method='post',
        data={'reason': 'Prize value is wrong'},
        campaign_id=campaign.id,
    )

    campaign.refresh_from_db()
    assert campaign.status == 'rejected'
    assert campaign.rejection_reason == 'Prize value is wrong'


def test_a_maker_cannot_approve_their_own_campaign(a_maker, org_a):
    """Separation of duties: an approval the author can perform is not one."""
    campaign = make_campaign(org_a, created_by=a_maker, status='submitted')

    response = call(
        views.organization_campaign_approve, a_maker, method='post', campaign_id=campaign.id
    )

    assert response.status_code == 403
    campaign.refresh_from_db()
    assert campaign.status == 'submitted'


def test_a_checker_cannot_approve_their_own_campaign(a_checker, org_a):
    """Reached when one person holds both roles, or a checker authors
    directly."""
    campaign = make_campaign(org_a, created_by=a_checker, status='submitted')

    with pytest.raises(WorkflowError, match='cannot be approved by the person'):
        approve(campaign, a_checker)


def test_a_checker_cannot_approve_another_organizations_campaign(a_checker, org_b, b_maker):
    foreign = make_campaign(org_b, created_by=b_maker, status='submitted')

    with pytest.raises(WorkflowError):
        approve(foreign, a_checker)

    foreign.refresh_from_db()
    assert foreign.status == 'submitted'


def test_the_approve_endpoint_cannot_be_reached_for_a_foreign_campaign(a_checker, org_b, b_maker):
    """The endpoint refuses before the workflow is even consulted."""
    foreign = make_campaign(org_b, created_by=b_maker, status='submitted')

    response = call(
        views.organization_campaign_approve,
        a_checker,
        method='post',
        campaign_id=foreign.id,
    )

    assert response.status_code == 404
    foreign.refresh_from_db()
    assert foreign.status == 'submitted'


def test_a_member_cannot_approve(member, org_a, a_maker):
    campaign = make_campaign(org_a, created_by=a_maker, status='submitted')

    with pytest.raises(WorkflowError):
        approve(campaign, member)


def test_a_draft_campaign_cannot_be_approved(a_checker, a_maker, org_a):
    """Only a submitted campaign is reviewable."""
    campaign = make_campaign(org_a, created_by=a_maker, status='draft')

    with pytest.raises(WorkflowError, match='only a submitted campaign'):
        approve(campaign, a_checker)


def test_an_already_approved_campaign_cannot_be_approved_again(a_checker, a_maker, org_a):
    campaign = make_campaign(org_a, created_by=a_maker, status='approved')

    with pytest.raises(WorkflowError, match='only a submitted campaign'):
        approve(campaign, a_checker)


def test_a_rejected_campaign_can_be_resubmitted(a_maker, a_checker, org_a):
    """A maker fixes the problem and sends it back, and the stale rejection
    reason does not follow it."""
    campaign = make_campaign(org_a, created_by=a_maker, status='submitted')
    reject(campaign, a_checker, reason='Needs work')
    campaign.refresh_from_db()
    assert campaign.status == 'rejected'

    submit(campaign, a_maker)

    campaign.refresh_from_db()
    assert campaign.status == 'submitted'
    assert campaign.rejection_reason == ''
    assert campaign.approved_by_id is None


def test_a_submitted_campaign_cannot_be_edited(a_maker, org_a):
    """Otherwise the thing approved is not the thing submitted."""
    campaign = make_campaign(org_a, created_by=a_maker, status='submitted')

    response = call(
        views.organization_campaign_update,
        a_maker,
        method='patch',
        data={'title': 'Changed after review started'},
        campaign_id=campaign.id,
    )

    assert response.status_code == 409
    campaign.refresh_from_db()
    assert campaign.title != 'Changed after review started'


# ---------------------------------------------------------------------------
# 30  concurrency
# ---------------------------------------------------------------------------


def test_approve_and_reject_racing_produce_one_decision(a_maker, a_checker, org_a, org_b):
    """
    Checker A approves while checker B rejects, on the same campaign.

    Both transitions are conditional UPDATEs against status='submitted', so
    exactly one finds the row in that state. The loser is told the campaign was
    already decided rather than overwriting the decision that stands.

    Sequential here, not threaded: the guarantee under test is that the SECOND
    call is refused, which is a property of the conditional UPDATE rather than
    of timing. The threaded version needs PostgreSQL and lives with the other
    concurrency tests.
    """
    second_checker = make_user('iso_a_checker2', UserRealm.ORGANIZATION, UserRole.CHECKER, org_a)
    campaign = make_campaign(org_a, created_by=a_maker, status='submitted')

    approve(campaign, a_checker)

    with pytest.raises(WorkflowError) as exc:
        reject(campaign, second_checker, reason='too late')

    assert exc.value.code == 'already_decided'
    campaign.refresh_from_db()
    assert campaign.status == 'approved'
    assert campaign.approved_by_id == a_checker.id
    assert campaign.rejection_reason == ''


def test_a_double_submit_is_refused(a_maker, org_a):
    campaign = make_campaign(org_a, created_by=a_maker)
    submit(campaign, a_maker)

    with pytest.raises(WorkflowError, match='cannot be submitted'):
        submit(campaign, a_maker)


def test_the_second_approval_returns_a_conflict_not_a_silent_success(a_maker, a_checker, org_a):
    """Through the endpoint: 409, carrying the standing decision."""
    second_checker = make_user('iso_a_checker3', UserRealm.ORGANIZATION, UserRole.CHECKER, org_a)
    campaign = make_campaign(org_a, created_by=a_maker, status='submitted')

    call(views.organization_campaign_approve, a_checker, method='post', campaign_id=campaign.id)
    response = call(
        views.organization_campaign_approve, second_checker, method='post', campaign_id=campaign.id
    )

    assert response.status_code == 409
    assert response.data['code'] == 'already_decided'


# ---------------------------------------------------------------------------
# Flipstar and members
# ---------------------------------------------------------------------------


def test_flipstar_sees_every_organizations_campaigns(org_a, org_b):
    staff = make_user('iso_fs', UserRealm.FLIPSTAR, UserRole.CHECKER)
    make_campaign(org_a)
    make_campaign(org_b)

    response = call(views.organization_campaign_list, staff)

    assert response.data['count'] == 2


def test_a_member_sees_nothing_here(member, org_a):
    make_campaign(org_a)

    response = call(views.organization_campaign_list, member)

    assert response.data['count'] == 0


def test_a_member_cannot_reach_a_campaign_detail(member, org_a):
    campaign = make_campaign(org_a)

    response = call(views.organization_campaign_detail, member, campaign_id=campaign.id)

    assert response.status_code == 404
