"""
The maker/checker approval workflow, and scoped campaign lookup.

Two things live here, because they are the same concern seen from two angles:
getting hold of a campaign you are entitled to, and moving it through approval.

Scoped lookup
-------------
``get_campaign_for(user, campaign_id)`` is the only way an organization-facing
view should fetch a campaign. A bare ``Campaign.objects.get(pk=...)`` answers
"does this row exist"; this answers "does this row exist *for you*", which is
the question authorization actually asks. Out-of-scope campaigns raise Http404
rather than 403 -- see the note on that function for why.

State transitions
-----------------
    DRAFT --submit--> SUBMITTED --approve--> APPROVED
                              \\--reject---> REJECTED --(edit)--> DRAFT

Every transition is a single conditional UPDATE via ``claim_transition``, the
primitive already used for boost cancellation and the subscription bonus. Two
checkers acting at once cannot both win: the first moves the row out of
'submitted' and the second finds nothing to move, so it is told the campaign
was already decided instead of silently overwriting the first decision.

The status is never taken from the request. A client sending
``{"status": "approved"}`` to an update endpoint changes nothing here, because
these functions are the only writers of the approval columns and none of them
reads a status from input.
"""

from django.db import transaction
from django.http import Http404
from django.utils import timezone

from api.models.campaign import Campaign
from api.services.concurrency import claim_transition
from api.services.realms import (
    can_modify_campaign,
    can_review_campaign,
    is_flipstar,
    is_maker,
    visible_campaigns,
)


class WorkflowError(Exception):
    """A transition that the workflow does not permit.

    Carries ``code`` so views can map to a status without string-matching the
    message.
    """

    def __init__(self, message, code='invalid_transition'):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# Scoped lookup
# ---------------------------------------------------------------------------


def get_campaign_for(user, campaign_id, *, queryset=None):
    """Fetch a campaign the user is entitled to, or raise Http404.

    404 rather than 403, deliberately. Answering 403 for a campaign belonging
    to another organization confirms that the id exists, which turns any
    detail endpoint into an enumeration oracle: a caller can walk ids and learn
    how many campaigns a competitor runs. 404 leaks nothing -- to an outsider
    "not yours" and "not a thing" look the same.

    Views must call this instead of Campaign.objects.get(pk=...). Passing the
    id to the ORM directly is how ownership gets bypassed: the row is returned
    on the strength of the URL alone.
    """
    base = queryset if queryset is not None else Campaign.objects.all()
    try:
        return visible_campaigns(user, base).get(pk=campaign_id)
    except Campaign.DoesNotExist as exc:
        raise Http404('Campaign not found.') from exc


# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------

#: Statuses a campaign may be submitted from. A rejected campaign is edited
#: back to draft and resubmitted; resubmitting straight from 'rejected' is
#: allowed so a maker who fixed the problem is not forced through a status
#: change that carries no information.
SUBMITTABLE = ('draft', 'rejected')

#: What a submitted campaign needs before anyone is asked to review it.
#: Checked here rather than in the serializer so it holds for every caller.
REQUIRED_FOR_SUBMISSION = ('title', 'description', 'prize_title', 'campaign_type')


def _require_complete(campaign):
    missing = [
        field for field in REQUIRED_FOR_SUBMISSION if not (getattr(campaign, field, '') or '')
    ]
    if missing:
        raise WorkflowError(
            f'Cannot submit: {", ".join(missing)} must be filled in first.',
            code='incomplete',
        )


def submit(campaign, user):
    """Move a campaign from draft/rejected to submitted.

    Only a maker may submit, and only within their own scope. The submitter is
    recorded from the authenticated user, never from input -- it is half of
    the separation-of-duties check that follows at approval.
    """
    if not is_maker(user):
        raise WorkflowError('Only a maker can submit a campaign for approval.', code='forbidden')
    if not can_modify_campaign(user, campaign):
        raise WorkflowError('You cannot submit this campaign.', code='forbidden')

    _require_complete(campaign)

    with transaction.atomic():
        claimed = claim_transition(
            Campaign,
            campaign.pk,
            expect=list(SUBMITTABLE),
            to='submitted',
            submitted_by=user,
            submitted_at=timezone.now(),
            # A resubmission clears the previous decision, so a stale
            # rejection reason cannot sit on a campaign now awaiting review.
            rejection_reason='',
            approved_by=None,
            approved_at=None,
        )
        if not claimed:
            campaign.refresh_from_db()
            raise WorkflowError(
                f'Campaign is {campaign.status} and cannot be submitted.',
                code='invalid_transition',
            )

    campaign.refresh_from_db()
    return campaign


def approve(campaign, user):
    """Approve a submitted campaign.

    ``can_review_campaign`` carries all three conditions: checker role, inside
    the user's scope, and not the author. The last is why an approval step
    means anything.
    """
    if not can_review_campaign(user, campaign):
        raise WorkflowError(
            'You cannot approve this campaign. Approval requires the checker role, and a '
            'campaign cannot be approved by the person who created or submitted it.',
            code='forbidden',
        )

    with transaction.atomic():
        claimed = claim_transition(
            Campaign,
            campaign.pk,
            expect='submitted',
            to='approved',
            approved_by=user,
            approved_at=timezone.now(),
            rejection_reason='',
        )
        if not claimed:
            campaign.refresh_from_db()
            raise WorkflowError(
                f'Campaign is {campaign.status}; only a submitted campaign can be approved.',
                code='already_decided',
            )

    campaign.refresh_from_db()
    return campaign


def reject(campaign, user, reason=''):
    """Reject a submitted campaign, recording why."""
    if not can_review_campaign(user, campaign):
        raise WorkflowError(
            'You cannot reject this campaign. Rejection requires the checker role, and a '
            'campaign cannot be reviewed by the person who created or submitted it.',
            code='forbidden',
        )

    with transaction.atomic():
        claimed = claim_transition(
            Campaign,
            campaign.pk,
            expect='submitted',
            to='rejected',
            approved_by=user,
            approved_at=timezone.now(),
            rejection_reason=(reason or '').strip(),
        )
        if not claimed:
            campaign.refresh_from_db()
            raise WorkflowError(
                f'Campaign is {campaign.status}; only a submitted campaign can be rejected.',
                code='already_decided',
            )

    campaign.refresh_from_db()
    return campaign


def activate(campaign, user):
    """Take an approved campaign live.

    Separate from approval so that "this passed review" and "this is running"
    stay distinct: a campaign can be approved today and started next week.
    Restricted to Flipstar, because going live affects the whole platform.
    """
    if not (getattr(user, 'is_superuser', False) or is_flipstar(user)):
        raise WorkflowError('Only Flipstar staff can activate a campaign.', code='forbidden')

    with transaction.atomic():
        claimed = claim_transition(Campaign, campaign.pk, expect='approved', to='active')
        if not claimed:
            campaign.refresh_from_db()
            raise WorkflowError(
                f'Campaign is {campaign.status}; only an approved campaign can be activated.',
                code='invalid_transition',
            )

    campaign.refresh_from_db()
    return campaign


def audit_trail(campaign):
    """The approval history, as stored. Every field is written by the backend.

    Exposed for the detail endpoint so a reviewer can see who did what without
    a separate query, and so the values a client sees are the ones the server
    recorded -- there is no path by which a request can set them.
    """
    return {
        'status': campaign.status,
        'created_by': getattr(campaign.created_by, 'username', None),
        'submitted_by': getattr(campaign.submitted_by, 'username', None),
        'submitted_at': campaign.submitted_at,
        'reviewed_by': getattr(campaign.approved_by, 'username', None),
        'reviewed_at': campaign.approved_at,
        'rejection_reason': campaign.rejection_reason or '',
    }


__all__ = [
    'REQUIRED_FOR_SUBMISSION',
    'SUBMITTABLE',
    'WorkflowError',
    'activate',
    'approve',
    'audit_trail',
    'get_campaign_for',
    'reject',
    'submit',
]
