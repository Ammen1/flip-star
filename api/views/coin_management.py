"""
Coin management endpoints for Super Admin and organization administrators.

One module, two audiences
-------------------------
Both read and write the same configuration; what differs is which rows they can
reach. Rather than duplicate every handler, each one resolves its target
through ``_organization_for`` or ``_config_for_campaign``, which answer 404 for
anything outside the caller's scope.

    Super Admin          may name an organization; sees every row.
    Organization admin   never names one -- it comes from their account, and
                         an organization_id in the request is not read.

Rewards stay off
----------------
Nothing here enables payouts. ``rewards_enabled`` is editable so an
administrator can eventually switch it on deliberately, but it defaults False,
no endpoint sets it implicitly, and no engagement path calls ``award()``.

Validation rejects, it does not clamp
-------------------------------------
A rate above the platform ceiling returns 400 with the ceiling named. Silently
lowering 100 to 50 would leave an administrator believing their campaign pays
100.
"""

from django.http import Http404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.models.campaign import Campaign
from api.models.coin_config import CampaignRewardGrant, CoinConfiguration, CoinConfigurationAudit
from api.models.organization import Organization
from api.models.wallet import WalletConfig
from api.services.campaign_workflow import get_campaign_for
from api.services.coin_config import (
    CoinConfigError,
    apply_changes,
    default_for_organization,
    resolve_for_campaign,
    usage_for_campaign,
    usage_for_organization,
)
from api.services.realms import is_flipstar, organization_of, visible_campaigns
from common.permissions.realms import IsFlipstarUser

#: Ceilings Super Admin controls, on the existing WalletConfig singleton.
PLATFORM_LIMIT_FIELDS = (
    'max_like_reward',
    'max_comment_reward',
    'max_share_reward',
    'max_gift_reward',
)


def _is_platform(user):
    return bool(getattr(user, 'is_superuser', False) or is_flipstar(user))


def _organization_for(user, organization_id=None):
    """The organization a request may act on, or 404.

    Platform staff may name one. An organization user may not: their own is
    returned and ``organization_id`` is never consulted, so a request carrying
    another organization's id changes nothing.
    """
    if _is_platform(user):
        if organization_id is None:
            raise Http404('No organization specified.')
        try:
            return Organization.objects.get(pk=organization_id)
        except Organization.DoesNotExist as exc:
            raise Http404('Organization not found.') from exc

    own = organization_of(user)
    if own is None:
        raise Http404('No organization for this account.')
    return own


def serialize_config(config, organization=None):
    """A configuration row, or the organization's zeroes when none exists yet."""
    if config is None:
        return {
            'exists': False,
            'organization': organization.id if organization else None,
            'campaign': None,
            'rewards_enabled': False,
            **{field: 0 for field in CoinConfiguration.REWARD_FIELDS},
            'max_reward_per_user': 0,
            'max_daily_reward_per_user': 0,
            'budget': 0,
            'distributed': 0,
            'remaining_budget': None,
            'is_active': True,
            'locked_at': None,
        }
    return {
        'exists': True,
        'id': config.id,
        'organization': config.organization_id,
        'campaign': config.campaign_id,
        'rewards_enabled': config.rewards_enabled,
        **{field: getattr(config, field) for field in CoinConfiguration.REWARD_FIELDS},
        'max_reward_per_user': config.max_reward_per_user,
        'max_daily_reward_per_user': config.max_daily_reward_per_user,
        'budget': config.budget,
        'distributed': config.distributed,
        'remaining_budget': config.remaining_budget,
        'is_active': config.is_active,
        'locked_at': config.locked_at,
    }


def _config_error(exc):
    return Response({'error': str(exc), 'code': exc.code}, status=status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Platform ceilings -- Super Admin only
# ---------------------------------------------------------------------------


@api_view(['GET', 'PUT'])
@permission_classes([IsFlipstarUser])
def platform_coin_limits(request):
    """The ceilings every organization rate is checked against.

    Stored on WalletConfig, the existing platform singleton, rather than a new
    settings model -- Super Admin already administers coins there.
    """
    config = WalletConfig.get_config()

    if request.method == 'GET':
        return Response({field: getattr(config, field) for field in PLATFORM_LIMIT_FIELDS})

    changed = []
    for field in PLATFORM_LIMIT_FIELDS:
        if field not in request.data:
            continue
        try:
            value = int(request.data[field])
        except (TypeError, ValueError):
            return Response(
                {'error': f'{field} must be a whole number.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if value < 0:
            return Response(
                {'error': f'{field} cannot be negative.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        setattr(config, field, value)
        changed.append(field)

    if changed:
        config.save(update_fields=[*changed, 'updated_at'])

    return Response(
        {
            'updated': changed,
            **{field: getattr(config, field) for field in PLATFORM_LIMIT_FIELDS},
        }
    )


# ---------------------------------------------------------------------------
# Organization defaults
# ---------------------------------------------------------------------------


@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def organization_coin_config(request, organization_id=None):
    """An organization's default coin configuration.

    Super Admin reaches any organization by id. An organization admin reaches
    only their own, and the id in the URL is ignored for them -- there is no
    request shape that lets one organization read or write another's rates.
    """
    organization = _organization_for(request.user, organization_id)

    if request.method == 'GET':
        config = default_for_organization(organization)
        return Response(
            {
                'organization': {
                    'id': organization.id,
                    'name': organization.name,
                    'code': organization.code,
                },
                'configuration': serialize_config(config, organization),
                'usage': usage_for_organization(organization),
            }
        )

    if organization.status == 'suspended' and not _is_platform(request.user):
        return Response(
            {'error': 'This organization is suspended.', 'code': 'suspended'},
            status=status.HTTP_403_FORBIDDEN,
        )

    config = default_for_organization(organization, create=True)
    try:
        entries = apply_changes(
            config,
            request.data,
            actor=request.user,
            reason=request.data.get('reason', ''),
        )
    except CoinConfigError as exc:
        return _config_error(exc)

    return Response(
        {
            'configuration': serialize_config(config, organization),
            'changes_recorded': len(entries),
        }
    )


# ---------------------------------------------------------------------------
# Campaign configuration
# ---------------------------------------------------------------------------


@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def campaign_coin_config(request, campaign_id):
    """One campaign's coin configuration.

    ``get_campaign_for`` resolves through ``visible_campaigns``, so a campaign
    belonging to another organization is not found rather than refused -- the
    same 404-not-403 convention the rest of the campaign API uses, so ids
    cannot be enumerated.
    """
    campaign = get_campaign_for(request.user, campaign_id)

    if request.method == 'GET':
        config = CoinConfiguration.objects.filter(campaign=campaign).first()
        return Response(
            {
                'campaign': {'id': campaign.id, 'title': campaign.title, 'status': campaign.status},
                'configuration': serialize_config(config, campaign.organization),
                'effective': resolve_for_campaign(campaign),
                'usage': usage_for_campaign(campaign),
            }
        )

    if campaign.organization_id is None:
        return Response(
            {'error': 'Platform campaigns have no organization coin configuration.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Seeded from the organization's defaults on first write, so a campaign
    # starts where its organization stands rather than at zero.
    config = CoinConfiguration.objects.filter(campaign=campaign).first()
    if config is None:
        source = default_for_organization(campaign.organization)
        seed = {}
        if source is not None:
            for field in (
                *CoinConfiguration.REWARD_FIELDS,
                'max_reward_per_user',
                'max_daily_reward_per_user',
                'budget',
            ):
                seed[field] = getattr(source, field)
        config = CoinConfiguration.objects.create(
            organization=campaign.organization, campaign=campaign, **seed
        )

    try:
        entries = apply_changes(
            config,
            request.data,
            actor=request.user,
            reason=request.data.get('reason', ''),
        )
    except CoinConfigError as exc:
        return _config_error(exc)

    return Response(
        {
            'configuration': serialize_config(config, campaign.organization),
            'changes_recorded': len(entries),
        }
    )


# ---------------------------------------------------------------------------
# Usage, grants and audit
# ---------------------------------------------------------------------------


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def coin_usage_overview(request):
    """Budget usage per campaign, scoped to the caller.

    Built from ``visible_campaigns``, so an organization admin's totals cannot
    include another organization even in the aggregate.
    """
    campaigns = visible_campaigns(request.user, Campaign.objects.select_related('organization'))
    configs = {c.campaign_id: c for c in CoinConfiguration.objects.filter(campaign__in=campaigns)}

    rows = []
    for campaign in campaigns.order_by('-created_at')[:200]:
        config = configs.get(campaign.id)
        rows.append(
            {
                'campaign': {'id': campaign.id, 'title': campaign.title, 'status': campaign.status},
                'organization': (
                    {'id': campaign.organization_id, 'name': campaign.organization.name}
                    if campaign.organization_id
                    else None
                ),
                'budget': config.budget if config else 0,
                'distributed': config.distributed if config else 0,
                'remaining': config.remaining_budget if config else None,
                'rewards_enabled': config.rewards_enabled if config else False,
            }
        )

    organization = organization_of(request.user)
    return Response(
        {
            'organization': (
                {'id': organization.id, 'name': organization.name} if organization else None
            ),
            'totals': usage_for_organization(organization) if organization else None,
            # Surfaced so a dashboard can say "rewards are currently disabled"
            # rather than showing zeroes that look like a reporting bug.
            'rewards_enabled_anywhere': any(r['rewards_enabled'] for r in rows),
            'campaigns': rows,
        }
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def reward_transactions(request):
    """Reward grants, scoped to campaigns the caller may see.

    Empty today: nothing calls ``award()`` from an engagement path, so no
    grants exist. The endpoint is here so the dashboard has a real source
    rather than a placeholder that would need replacing later.
    """
    campaigns = visible_campaigns(request.user, Campaign.objects.all())
    grants = (
        CampaignRewardGrant.objects.filter(campaign__in=campaigns)
        .select_related('user', 'campaign')
        .order_by('-created_at')[:200]
    )

    return Response(
        {
            'count': len(grants),
            'results': [
                {
                    'id': g.id,
                    'user': g.user.username,
                    'campaign': {'id': g.campaign_id, 'title': g.campaign.title},
                    'action': g.action,
                    'coins': g.coins,
                    'reference': g.reference,
                    'created_at': g.created_at,
                }
                for g in grants
            ],
        }
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def coin_config_audit(request):
    """Who changed which coin value, from what to what.

    Scoped by organization: platform staff see everything, an organization
    admin sees only their own history.
    """
    entries = CoinConfigurationAudit.objects.select_related(
        'changed_by', 'organization', 'campaign'
    )

    if not _is_platform(request.user):
        organization = organization_of(request.user)
        if organization is None:
            entries = entries.none()
        else:
            entries = entries.filter(organization=organization)

    organization_id = request.query_params.get('organization')
    if organization_id and _is_platform(request.user):
        entries = entries.filter(organization_id=organization_id)

    return Response(
        {
            'count': entries.count(),
            'results': [
                {
                    'id': e.id,
                    'organization': {'id': e.organization_id, 'name': e.organization.name},
                    'campaign': (
                        {'id': e.campaign_id, 'title': e.campaign.title} if e.campaign_id else None
                    ),
                    'field': e.field,
                    'previous_value': e.previous_value,
                    'new_value': e.new_value,
                    'changed_by': getattr(e.changed_by, 'username', None),
                    'reason': e.reason,
                    'changed_at': e.changed_at,
                }
                for e in entries[:200]
            ],
        }
    )


@api_view(['GET'])
@permission_classes([IsFlipstarUser])
def organizations_coin_overview(request):
    """Every organization's coin position. Super Admin only."""
    rows = []
    for organization in Organization.objects.all().order_by('name'):
        usage = usage_for_organization(organization)
        rows.append(
            {
                'organization': {
                    'id': organization.id,
                    'name': organization.name,
                    'code': organization.code,
                    'status': organization.status,
                },
                'campaigns': Campaign.objects.filter(organization=organization).count(),
                **usage,
            }
        )
    return Response({'count': len(rows), 'results': rows})
