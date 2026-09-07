"""
Resolving and enforcing coin configuration.

Inheritance
-----------
    campaign override  ->  organization default  ->  platform (WalletConfig)

``resolve_for_campaign`` walks that chain once and returns a plain mapping, so
callers never have to know which level answered. A platform campaign
(organization NULL) resolves straight to the platform layer, which is what
every campaign predating organizations does.

Snapshotting
------------
When a campaign goes live its configuration is frozen (``locked_at``). Editing
an organization default afterwards leaves running campaigns paying what they
were paying -- otherwise a rate change would retroactively alter what
participants had already earned toward.

Two ceilings, not one
---------------------
An organization sets its own rates; Super Admin sets the maximum those rates
may reach, on WalletConfig. Both are enforced server-side, and the platform
ceiling is checked in ``clean()`` so the admin, the API and a management
command all refuse the same values.

Rewards are off unless switched on
----------------------------------
``rewards_enabled`` defaults False and every reward defaults 0, so this module
is inert on arrival. Nothing in it starts paying coins until an organization
opts in -- see the note in api/models/coin_config.py about why that is not a
default.
"""

from django.db import transaction
from django.db.models import F
from django.utils import timezone

#: Platform fallbacks, used when neither the campaign nor the organization has
#: an opinion. Zero throughout: the platform does not pay for engagement today,
#: and this module must not change that by existing.
PLATFORM_DEFAULTS = {
    'like_reward': 0,
    'comment_reward': 0,
    'share_reward': 0,
    'gift_reward': 0,
    'participation_reward': 0,
    'completion_reward': 0,
    'max_reward_per_user': 0,
    'max_daily_reward_per_user': 0,
    'budget': 0,
    'rewards_enabled': False,
}

#: Where Super Admin's ceiling for each reward lives on WalletConfig. Absent
#: fields mean "no ceiling configured", not "zero".
PLATFORM_LIMIT_FIELDS = {
    'like_reward': 'max_like_reward',
    'comment_reward': 'max_comment_reward',
    'share_reward': 'max_share_reward',
    'gift_reward': 'max_gift_reward',
}


class CoinConfigError(Exception):
    """A configuration that must not be stored, or a reward that must not be paid."""

    def __init__(self, message, code='invalid'):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def default_for_organization(organization, *, create=False):
    """The organization's default configuration row, or None."""
    from api.models.coin_config import CoinConfiguration

    if organization is None:
        return None
    if create:
        config, _ = CoinConfiguration.objects.get_or_create(
            organization=organization,
            campaign__isnull=True,
            defaults={'organization': organization},
        )
        return config
    return CoinConfiguration.objects.filter(
        organization=organization, campaign__isnull=True
    ).first()


def config_for_campaign(campaign):
    """The campaign's own configuration row, or None."""
    from api.models.coin_config import CoinConfiguration

    if campaign is None:
        return None
    return CoinConfiguration.objects.filter(campaign=campaign).first()


def resolve_for_campaign(campaign):
    """The effective coin rules for a campaign, as a plain mapping.

    Walks campaign -> organization -> platform and returns the first level
    that has a row, falling back per key. Returning a mapping rather than a
    model instance keeps callers from accidentally saving a resolved view back
    over a real row.
    """
    resolved = dict(PLATFORM_DEFAULTS)
    resolved['source'] = 'platform'

    if campaign is None:
        return resolved

    organization = getattr(campaign, 'organization', None)

    org_default = default_for_organization(organization)
    if org_default is not None and org_default.is_active:
        _apply(resolved, org_default)
        resolved['source'] = 'organization'

    own = config_for_campaign(campaign)
    if own is not None and own.is_active:
        _apply(resolved, own)
        resolved['source'] = 'campaign'
        resolved['configuration_id'] = own.id
        resolved['budget'] = own.budget
        resolved['distributed'] = own.distributed
        resolved['remaining_budget'] = own.remaining_budget

    return resolved


def _apply(resolved, config):
    from api.models.coin_config import CoinConfiguration

    for field in (
        *CoinConfiguration.REWARD_FIELDS,
        'max_reward_per_user',
        'max_daily_reward_per_user',
        'budget',
    ):
        resolved[field] = getattr(config, field)
    resolved['rewards_enabled'] = config.rewards_enabled


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_against_platform_limits(config):
    """Refuse rates above Super Admin's ceiling, or below zero.

    The ceiling lives on WalletConfig, the existing platform singleton, rather
    than in a new settings model -- Super Admin already administers coins
    there.

    A ceiling that is not configured is treated as absent, not as zero. Reading
    a missing limit as zero would silently forbid every reward the moment this
    code shipped.
    """
    from api.models.coin_config import CoinConfiguration
    from api.models.wallet import WalletConfig

    for field in (
        *CoinConfiguration.REWARD_FIELDS,
        'max_reward_per_user',
        'max_daily_reward_per_user',
        'budget',
    ):
        value = getattr(config, field, 0) or 0
        if value < 0:
            raise CoinConfigError(f'{field} cannot be negative.', code='negative')

    try:
        platform = WalletConfig.get_config()
    except Exception:
        # No platform config to check against; the per-field guards above still
        # applied. A missing singleton must not block an organization's edit.
        return

    for field, limit_field in PLATFORM_LIMIT_FIELDS.items():
        limit = getattr(platform, limit_field, None)
        if limit is None:
            continue
        value = getattr(config, field, 0) or 0
        if value > limit:
            raise CoinConfigError(
                f'{field} may not exceed the platform maximum of {limit}.',
                code='exceeds_platform_limit',
            )


# ---------------------------------------------------------------------------
# Snapshotting
# ---------------------------------------------------------------------------


def snapshot_for_campaign(campaign, *, actor=None):
    """Freeze a campaign's configuration from its organization's defaults.

    Called when a campaign goes live. After this, editing the organization
    default leaves this campaign alone -- which is the point: a rate change
    must not retroactively alter what participants have already earned toward.

    Idempotent: a campaign that already has a locked configuration keeps it.
    """
    from api.models.coin_config import CoinConfiguration

    organization = getattr(campaign, 'organization', None)
    if organization is None:
        return None

    existing = config_for_campaign(campaign)
    if existing is not None and existing.locked_at is not None:
        return existing

    source = default_for_organization(organization)
    values = {}
    if source is not None:
        for field in (
            *CoinConfiguration.REWARD_FIELDS,
            'max_reward_per_user',
            'max_daily_reward_per_user',
            'budget',
            'rewards_enabled',
        ):
            values[field] = getattr(source, field)

    with transaction.atomic():
        config, _ = CoinConfiguration.objects.get_or_create(
            campaign=campaign,
            defaults={'organization': organization, **values},
        )
        if config.locked_at is None:
            for key, value in values.items():
                setattr(config, key, value)
            config.locked_at = timezone.now()
            config.save()

    return config


# ---------------------------------------------------------------------------
# Paying a reward
# ---------------------------------------------------------------------------


def award(campaign, user, action, reference, *, coins=None):
    """Pay a user for one engagement, once, within every configured limit.

    Returns the coins actually paid, which is 0 whenever a rule declines --
    rewards switched off, no rate for this action, budget exhausted, a limit
    reached, or this exact engagement already paid.

    Concurrency
    -----------
    The whole decision runs inside one transaction with the configuration row
    locked, because every check depends on a number the payment then changes:
    two concurrent likes must not both read "budget remaining" and both spend
    it. The grant row's unique constraint is the second line -- it makes a
    replayed request a no-op even if it slips past the lock, and it is what the
    idempotency guarantee actually rests on.

    Deliberately returns 0 rather than raising for a declined reward: engagement
    must not fail because the budget ran out. The like still happens; it simply
    pays nothing.
    """
    from django.db import IntegrityError

    from api.models.coin_config import CampaignRewardGrant, CoinConfiguration
    from api.models.contest import UserCoinBalance

    if campaign is None or user is None or not getattr(user, 'is_authenticated', True):
        return 0

    resolved = resolve_for_campaign(campaign)
    if not resolved.get('rewards_enabled'):
        return 0

    amount = coins if coins is not None else resolved.get(f'{action}_reward', 0)
    if not amount or amount <= 0:
        return 0

    config_id = resolved.get('configuration_id')
    if config_id is None:
        # Rewards are enabled at organization level but this campaign has no
        # row of its own, so there is no budget to draw down. Snapshot first.
        config = snapshot_for_campaign(campaign)
        if config is None:
            return 0
        config_id = config.id

    try:
        with transaction.atomic():
            locked = CoinConfiguration.objects.select_for_update().get(pk=config_id)

            if not locked.rewards_enabled or not locked.is_active:
                return 0

            # Budget. Checked under the lock against the value being spent.
            if locked.budget:
                remaining = locked.budget - (locked.distributed or 0)
                if remaining <= 0:
                    return 0
                amount = min(amount, remaining)

            # Per-user ceilings, counted from the grants that record them.
            if locked.max_reward_per_user:
                earned = _earned_total(campaign, user)
                headroom = locked.max_reward_per_user - earned
                if headroom <= 0:
                    return 0
                amount = min(amount, headroom)

            if locked.max_daily_reward_per_user:
                today = _earned_total(campaign, user, since=timezone.now().date())
                headroom = locked.max_daily_reward_per_user - today
                if headroom <= 0:
                    return 0
                amount = min(amount, headroom)

            if amount <= 0:
                return 0

            # The idempotency record. A duplicate raises IntegrityError, which
            # is caught below and treated as "already paid".
            CampaignRewardGrant.objects.create(
                configuration_id=config_id,
                campaign=campaign,
                user=user,
                action=action,
                reference=str(reference),
                coins=amount,
            )

            CoinConfiguration.objects.filter(pk=config_id).update(
                distributed=F('distributed') + amount
            )

            balance, _ = UserCoinBalance.objects.get_or_create(user=user)
            balance.add_earned(
                amount,
                transaction_type='reward',
                description=f'{action} reward for campaign #{campaign.id}',
            )
    except IntegrityError:
        # Already paid for this exact engagement. Not an error: a retry
        # reaching here means the first attempt succeeded.
        return 0

    return amount


def _earned_total(campaign, user, since=None):
    from django.db.models import Sum

    from api.models.coin_config import CampaignRewardGrant

    queryset = CampaignRewardGrant.objects.filter(campaign=campaign, user=user)
    if since is not None:
        queryset = queryset.filter(created_at__date__gte=since)
    return queryset.aggregate(total=Sum('coins'))['total'] or 0


def usage_for_campaign(campaign):
    """Budget, distributed and remaining for one campaign."""
    config = config_for_campaign(campaign)
    if config is None:
        return {'budget': 0, 'distributed': 0, 'remaining': None, 'exhausted': False}
    return {
        'budget': config.budget,
        'distributed': config.distributed,
        'remaining': config.remaining_budget,
        'exhausted': config.is_exhausted,
    }


__all__ = [
    'EDITABLE_FIELDS',
    'PLATFORM_DEFAULTS',
    'PLATFORM_LIMIT_FIELDS',
    'CoinConfigError',
    'award',
    'config_for_campaign',
    'default_for_organization',
    'resolve_for_campaign',
    'snapshot_for_campaign',
    'apply_changes',
    'usage_for_campaign',
    'usage_for_organization',
    'validate_against_platform_limits',
]

# ---------------------------------------------------------------------------
# Editing configuration, with an audit trail
# ---------------------------------------------------------------------------

#: Fields a caller may change. An allowlist, so `organization`, `campaign`,
#: `distributed` and `locked_at` are unreachable from any request: ownership
#: cannot be reassigned, and the spent counter cannot be edited to free up
#: budget that was already paid out.
EDITABLE_FIELDS = (
    'like_reward',
    'comment_reward',
    'share_reward',
    'gift_reward',
    'participation_reward',
    'completion_reward',
    'max_reward_per_user',
    'max_daily_reward_per_user',
    'budget',
    'rewards_enabled',
    'is_active',
)


def apply_changes(config, changes, *, actor, reason=''):
    """Update a configuration and record what changed, or change nothing.

    Validation runs against a copy before anything is written, so a rejected
    value leaves both the row and the audit trail untouched -- an audit
    containing changes that never took effect would be worse than no audit.

    Returns the list of audit entries created, which is empty when the caller
    submitted no actual change. Re-submitting the same values is not an edit
    and does not litter the trail.

    Rejects rather than clamps. An administrator who asked for 100 and silently
    got 50 would go on believing the campaign pays 100.
    """
    from django.db import transaction as db_transaction

    from api.models.coin_config import CoinConfigurationAudit

    proposed = {field: value for field, value in changes.items() if field in EDITABLE_FIELDS}
    if not proposed:
        return []

    for field, value in proposed.items():
        if field in ('rewards_enabled', 'is_active'):
            continue
        try:
            numeric = int(value)
        except (TypeError, ValueError) as exc:
            raise CoinConfigError(f'{field} must be a whole number.', code='invalid') from exc
        if numeric < 0:
            raise CoinConfigError(f'{field} cannot be negative.', code='negative')
        proposed[field] = numeric

    # Validate on a detached copy: the real row must not carry rejected values
    # even briefly, in case anything else reads it mid-transaction.
    candidate = _copy_for_validation(config, proposed)
    validate_against_platform_limits(candidate)

    # A budget cannot be cut below what has already been paid out; the
    # database constraint would refuse it anyway, less legibly.
    new_budget = proposed.get('budget', config.budget)
    if new_budget and new_budget < (config.distributed or 0):
        raise CoinConfigError(
            f'Budget cannot be set below the {config.distributed} coins already distributed.',
            code='below_distributed',
        )

    entries = []
    with db_transaction.atomic():
        changed_fields = []
        for field, value in proposed.items():
            previous = getattr(config, field)
            if previous == value:
                continue
            setattr(config, field, value)
            changed_fields.append(field)
            entries.append(
                CoinConfigurationAudit(
                    configuration=config,
                    organization_id=config.organization_id,
                    campaign_id=config.campaign_id,
                    field=field,
                    previous_value=str(previous),
                    new_value=str(value),
                    changed_by=actor,
                    reason=reason or '',
                )
            )

        if not changed_fields:
            return []

        config.save(update_fields=[*changed_fields, 'updated_at'])
        for entry in entries:
            entry.configuration = config
        CoinConfigurationAudit.objects.bulk_create(entries)

    return entries


def _copy_for_validation(config, proposed):
    from api.models.coin_config import CoinConfiguration

    candidate = CoinConfiguration(
        organization_id=config.organization_id,
        campaign_id=config.campaign_id,
    )
    for field in EDITABLE_FIELDS:
        setattr(candidate, field, getattr(config, field))
    for field, value in proposed.items():
        setattr(candidate, field, value)
    return candidate


def usage_for_organization(organization):
    """Budget totals across an organization's campaigns."""
    from django.db.models import Sum

    from api.models.coin_config import CoinConfiguration

    rows = CoinConfiguration.objects.filter(
        organization=organization, campaign__isnull=False
    ).aggregate(budget=Sum('budget'), distributed=Sum('distributed'))

    budget = rows['budget'] or 0
    distributed = rows['distributed'] or 0
    return {
        'budget': budget,
        'distributed': distributed,
        'remaining': max(0, budget - distributed) if budget else None,
    }
