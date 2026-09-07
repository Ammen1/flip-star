"""
Campaign management for organization users.

Why these are separate from the existing admin endpoints
--------------------------------------------------------
The endpoints in campaign_admin.py are guarded by ``IsAdminUser``, i.e.
``is_staff``. An ORGANIZATION-realm user is not staff, so they cannot reach any
of them -- which is why organization users could not previously manage
campaigns at all, and why the isolation gap there was latent rather than live.

Rather than loosening ``IsAdminUser`` on views that also expose
platform-wide operations, organization access gets its own surface, scoped
from the first line. Every lookup here goes through ``get_campaign_for``,
which resolves against ``visible_campaigns`` -- so an id belonging to another
organization is simply not found. Nothing in this module calls
``Campaign.objects.get(pk=...)``.

Ownership on write
------------------
No handler reads ``organization`` or ``organization_id`` from the request. On
create it comes from the account; on update the field is not writable at all,
so a campaign cannot be moved between organizations by any request.
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.models.campaign import Campaign
from api.services.campaign_workflow import (
    WorkflowError,
    approve,
    audit_trail,
    get_campaign_for,
    reject,
    submit,
)
from api.services.realms import (
    can_modify_campaign,
    visible_campaigns,
)

#: Fields a maker may change through the update endpoint.
#:
#: An allowlist, not a blocklist. `organization` is absent, so ownership cannot
#: be reassigned; `status` is absent, so the approval workflow cannot be
#: short-circuited by PATCHing {"status": "approved"} -- status moves only
#: through the submit/approve/reject endpoints below. Anything not named here
#: is ignored rather than rejected, so a client sending extra keys gets a
#: successful update of the fields it was allowed to touch.
EDITABLE_FIELDS = (
    'title',
    'description',
    'prize_title',
    'prize_description',
    'prize_value',
    'campaign_type',
    'min_followers',
    'min_level',
    'min_votes_per_reel',
    'required_hashtags',
    'start_date',
    'entry_deadline',
    'voting_start',
    'voting_end',
    'winner_count',
)

#: Editing is confined to states where a campaign is not under or past review.
#: Allowing edits while 'submitted' would let a maker change a campaign after
#: a checker began reviewing it, so the thing approved is not the thing
#: submitted.
EDITABLE_STATUSES = ('draft', 'rejected')


def serialize(campaign, *, detail=False):
    """The campaign payload. Organization is reported, never accepted."""
    data = {
        'id': campaign.id,
        'title': campaign.title,
        'description': campaign.description,
        'status': campaign.status,
        'campaign_type': campaign.campaign_type,
        'prize_title': campaign.prize_title,
        'prize_value': str(campaign.prize_value),
        'start_date': campaign.start_date,
        'entry_deadline': campaign.entry_deadline,
        'total_entries': campaign.total_entries,
        'organization': (
            {'id': campaign.organization_id, 'name': campaign.organization.name}
            if campaign.organization_id
            else None
        ),
    }
    if detail:
        data['approval'] = audit_trail(campaign)
    return data


def _workflow_response(exc):
    """Map a workflow refusal onto a status code.

    'forbidden' is a permissions answer (403); everything else is a statement
    about the campaign's current state, which is a conflict (409) rather than
    a malformed request -- the caller did nothing wrong, they were second.
    """
    if exc.code == 'forbidden':
        code = status.HTTP_403_FORBIDDEN
    elif exc.code in ('already_decided', 'invalid_transition'):
        code = status.HTTP_409_CONFLICT
    else:
        code = status.HTTP_400_BAD_REQUEST
    return Response({'error': str(exc), 'code': exc.code}, status=code)


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def organization_campaign_list(request):
    """Campaigns the caller may see.

    Filtered at the queryset, not per row. A per-object check would still let
    another organization's campaigns influence the count and the pagination,
    which leaks their number even when their contents stay hidden.
    """
    queryset = visible_campaigns(request.user, Campaign.objects.select_related('organization'))

    status_filter = request.query_params.get('status')
    if status_filter:
        queryset = queryset.filter(status=status_filter)

    return Response(
        {
            'count': queryset.count(),
            'results': [serialize(c) for c in queryset.order_by('-created_at')[:200]],
        }
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def organization_campaign_detail(request, campaign_id):
    """One campaign, or 404 if it is not the caller's."""
    campaign = get_campaign_for(
        request.user, campaign_id, queryset=Campaign.objects.select_related('organization')
    )
    return Response(serialize(campaign, detail=True))


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def organization_campaign_update(request, campaign_id):
    """Edit a campaign in the caller's own organization."""
    campaign = get_campaign_for(request.user, campaign_id)

    if not can_modify_campaign(request.user, campaign):
        return Response(
            {'error': 'You do not have permission to modify this campaign.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    if campaign.status not in EDITABLE_STATUSES:
        return Response(
            {
                'error': (
                    f'A {campaign.status} campaign cannot be edited. '
                    'Only draft or rejected campaigns are editable.'
                ),
                'code': 'not_editable',
            },
            status=status.HTTP_409_CONFLICT,
        )

    # Allowlist. `organization` and `status` are not in EDITABLE_FIELDS, so no
    # request can reassign ownership or jump the approval workflow.
    changed = []
    for field in EDITABLE_FIELDS:
        if field in request.data:
            setattr(campaign, field, request.data[field])
            changed.append(field)

    if changed:
        campaign.save(update_fields=[*changed, 'updated_at'])

    return Response({'updated': changed, 'campaign': serialize(campaign, detail=True)})


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def organization_campaign_delete(request, campaign_id):
    """Delete a campaign that has not yet been approved.

    An approved or live campaign is not deletable here: entries, engagement
    and rewards may already hang off it, and removing it would take those with
    it. Cancelling is the operation for a running campaign.
    """
    campaign = get_campaign_for(request.user, campaign_id)

    if not can_modify_campaign(request.user, campaign):
        return Response(
            {'error': 'You do not have permission to delete this campaign.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    if campaign.status not in EDITABLE_STATUSES:
        return Response(
            {
                'error': f'A {campaign.status} campaign cannot be deleted.',
                'code': 'not_deletable',
            },
            status=status.HTTP_409_CONFLICT,
        )

    campaign.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Maker / checker workflow
# ---------------------------------------------------------------------------


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def organization_campaign_submit(request, campaign_id):
    """Maker submits a campaign for review."""
    campaign = get_campaign_for(request.user, campaign_id)
    try:
        submit(campaign, request.user)
    except WorkflowError as exc:
        return _workflow_response(exc)
    return Response({'status': campaign.status, 'approval': audit_trail(campaign)})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def organization_campaign_approve(request, campaign_id):
    """Checker approves a submitted campaign.

    Two checkers racing here is expected, not exceptional: the transition is a
    single conditional UPDATE, so the second gets 409 with the decision that
    actually stands rather than overwriting it.
    """
    campaign = get_campaign_for(request.user, campaign_id)
    try:
        approve(campaign, request.user)
    except WorkflowError as exc:
        return _workflow_response(exc)
    return Response({'status': campaign.status, 'approval': audit_trail(campaign)})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def organization_campaign_reject(request, campaign_id):
    """Checker rejects a submitted campaign, with a reason."""
    campaign = get_campaign_for(request.user, campaign_id)
    try:
        reject(campaign, request.user, reason=request.data.get('reason', ''))
    except WorkflowError as exc:
        return _workflow_response(exc)
    return Response({'status': campaign.status, 'approval': audit_trail(campaign)})
