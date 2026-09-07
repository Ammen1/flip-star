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

from django.db.models.functions import Coalesce
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
    can_author,
    can_create_campaign,
    can_modify_campaign,
    is_checker,
    organization_of,
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


# ---------------------------------------------------------------------------
# Dashboard, analytics, posts and leaderboard -- all organization-scoped
# ---------------------------------------------------------------------------
#
# These close the gap flagged in the isolation report: the equivalents in
# campaign_admin.py are is_staff-only and carry no ownership check, so opening
# them to organization users would have leaked across organizations. Rather
# than loosen those, the organization-facing versions below resolve every
# campaign through get_campaign_for, which means an id from another
# organization is not found.


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def organization_dashboard(request):
    """Headline numbers for the caller's own organization.

    Every aggregate is computed over `visible_campaigns`, so the totals cannot
    include another organization's work even by accident -- the filter is
    applied before the counting, not after.
    """
    from django.db.models import Count, Q, Sum

    scoped = visible_campaigns(request.user, Campaign.objects.all())

    totals = scoped.aggregate(
        total=Count('id'),
        draft=Count('id', filter=Q(status='draft')),
        submitted=Count('id', filter=Q(status='submitted')),
        approved=Count('id', filter=Q(status='approved')),
        active=Count('id', filter=Q(status='active')),
        completed=Count('id', filter=Q(status='completed')),
        rejected=Count('id', filter=Q(status='rejected')),
        entries=Coalesce(Sum('total_entries'), 0),
    )

    organization = organization_of(request.user)
    return Response(
        {
            'organization': (
                {'id': organization.id, 'name': organization.name, 'code': organization.code}
                if organization
                else None
            ),
            'campaigns': totals,
            'recent': [
                serialize(c)
                for c in scoped.select_related('organization').order_by('-created_at')[:5]
            ],
            # What the signed-in user may do, so the UI can render honestly
            # rather than guessing. Advisory only -- every endpoint re-checks.
            'capabilities': {
                'can_create': can_create_campaign(request.user),
                'can_author': can_author(request.user),
                'can_review': is_checker(request.user),
            },
        }
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def organization_campaign_analytics(request, campaign_id):
    """Engagement analytics for one campaign the caller owns.

    Counts come from api/services/scoring/leaderboard.py, the single
    implementation of what an engagement is -- so these figures and the
    leaderboard agree by construction rather than by coincidence.
    """
    campaign = get_campaign_for(request.user, campaign_id)

    from api.services.scoring.leaderboard import (
        campaign_participant_totals,
        campaign_reels,
        resolve_weights,
    )

    posts = campaign_reels(campaign)
    rows = campaign_participant_totals(campaign, posts)

    totals = {'likes': 0, 'comments': 0, 'shares': 0, 'gifts': 0}
    for row in rows:
        for key in totals:
            totals[key] += row[key]

    return Response(
        {
            'campaign': {'id': campaign.id, 'title': campaign.title, 'status': campaign.status},
            'participants': len(rows),
            'posts': posts.count(),
            'engagement': totals,
            'leaderboard_score': sum(r['leaderboard_score'] for r in rows),
            'weights': {k: float(v) for k, v in resolve_weights(campaign).items()},
        }
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def organization_campaign_leaderboard(request, campaign_id):
    """Leaderboard for one campaign the caller owns.

    Reuses the platform scoring formula unchanged
    (likes x1 + comments x2 + shares x5 + gifts x10); this endpoint only
    decides WHO may read it, never how it is computed.
    """
    campaign = get_campaign_for(request.user, campaign_id)

    from django.contrib.auth import get_user_model

    from api.services.scoring.leaderboard import campaign_participant_totals, campaign_reels

    rows = campaign_participant_totals(campaign, campaign_reels(campaign))
    users = {u.id: u for u in get_user_model().objects.filter(id__in=[r['user_id'] for r in rows])}

    return Response(
        {
            'campaign': {'id': campaign.id, 'title': campaign.title},
            'entries': [
                {
                    **row,
                    'username': getattr(users.get(row['user_id']), 'username', None),
                }
                for row in rows[:100]
            ],
        }
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def organization_campaign_posts(request, campaign_id):
    """Posts entered into one campaign the caller owns.

    The ownership chain in full: the post is reached through the campaign, and
    the campaign through the account. A post id is never accepted directly,
    so there is no path by which one organization can address another's post.
    """
    campaign = get_campaign_for(request.user, campaign_id)

    from api.models.campaign_extended import PostScore
    from api.services.scoring.leaderboard import reel_engagement

    entries = (
        PostScore.objects.filter(campaign=campaign)
        .select_related('reel', 'user')
        .order_by('-created_at')[:100]
    )

    return Response(
        {
            'campaign': {'id': campaign.id, 'title': campaign.title},
            'count': len(entries),
            'results': [
                {
                    'post_id': entry.reel_id,
                    'author': entry.user.username,
                    'moderation_status': entry.moderation_status,
                    'caption': (entry.reel.caption or '')[:140] if entry.reel else '',
                    'engagement': reel_engagement(entry.reel) if entry.reel else None,
                    'created_at': entry.created_at,
                }
                for entry in entries
            ],
        }
    )
