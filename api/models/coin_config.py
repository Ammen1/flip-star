"""
Per-organization and per-campaign coin economy configuration.

What already existed, and why this is not a duplicate of it
-----------------------------------------------------------
Three separate things were already in the codebase, and they are easy to
confuse because they all involve coins:

  CampaignScoringConfig   LEADERBOARD SCORE weights, already per-campaign
                          (likes x1, comments x2, shares x5, gifts x10).
                          Untouched by this module. Score is not coins.

  WalletConfig.cost_*     What an engagement COSTS the person doing it.
                          A global singleton; read by charge_engagement.
                          All default 0, so engagement is currently free.

  WalletConfig.*_reward   What an engagement is supposed to PAY. Also global.
                          Configured, surfaced in the admin -- and never
                          credited to anyone: nothing in the codebase reads
                          these to add coins. See the report accompanying this
                          change.

This model adds the missing axis: those numbers, per organization, with
per-campaign overrides. It does not restate the leaderboard weights and it
does not replace WalletConfig, which stays the platform-wide default and the
safety ceiling.

Rewards are off by default
--------------------------
Every reward field defaults to 0 and ``rewards_enabled`` defaults to False.
Switching engagement rewards on means the platform begins minting coins on
every like, which is a business decision with real economic consequences --
so this ships inert, and an organization opts in deliberately.

Score and reward are deliberately separate
------------------------------------------
A campaign may weight comments heavily on the leaderboard while paying nothing
for them, or pay for shares without ranking on them. Collapsing the two would
make one impossible to change without moving the other.
"""

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models


class CoinConfiguration(models.Model):
    """Coin rules for an organization, or for one of its campaigns.

    ``campaign`` NULL means "the organization's defaults". A row with a
    campaign is that campaign's override. Resolution walks campaign ->
    organization -> platform, in api/services/coin_config.py.

    Why a row per campaign rather than fields on Campaign
    -----------------------------------------------------
    A campaign's configuration is snapshotted when it goes live, and history
    matters: changing an organization default must not silently repay a
    running campaign at a new rate. A separate row can be created, frozen and
    audited without touching the campaign table.
    """

    organization = models.ForeignKey(
        'api.Organization',
        on_delete=models.CASCADE,
        related_name='coin_configurations',
    )
    # NULL = the organization's default configuration.
    campaign = models.OneToOneField(
        'api.Campaign',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='coin_configuration',
    )

    # ── Rewards paid for engagement ──────────────────────────────────────────
    # Zero means "pays nothing", which is the shipped default and the current
    # behaviour of the platform.
    like_reward = models.PositiveIntegerField(default=0)
    comment_reward = models.PositiveIntegerField(default=0)
    share_reward = models.PositiveIntegerField(default=0)
    gift_reward = models.PositiveIntegerField(default=0)
    participation_reward = models.PositiveIntegerField(
        default=0, help_text='Coins for joining the campaign.'
    )
    completion_reward = models.PositiveIntegerField(
        default=0, help_text='Coins for completing the campaign.'
    )

    # ── Limits ───────────────────────────────────────────────────────────────
    # 0 means "no limit", so an unconfigured row does not accidentally cap
    # anything at zero.
    max_reward_per_user = models.PositiveIntegerField(
        default=0, help_text='Total coins one user may earn from this campaign. 0 = no limit.'
    )
    max_daily_reward_per_user = models.PositiveIntegerField(
        default=0, help_text='Coins one user may earn per day. 0 = no limit.'
    )

    # ── Budget ───────────────────────────────────────────────────────────────
    # The ceiling on what a campaign may pay out in total. distributed is
    # moved with F() under the reward transaction, never read-modify-written.
    budget = models.PositiveIntegerField(
        default=0, help_text='Total coins this campaign may distribute. 0 = no budget set.'
    )
    distributed = models.PositiveIntegerField(
        default=0, help_text='Coins paid out so far. Maintained by the reward path.'
    )

    rewards_enabled = models.BooleanField(
        default=False,
        help_text='Off by default: enabling this starts minting coins on engagement.',
    )
    is_active = models.BooleanField(default=True)

    # Set when a campaign goes live, freezing the numbers it will pay at.
    # Changing an organization default afterwards must not repay a running
    # campaign at a new rate.
    locked_at = models.DateTimeField(
        null=True, blank=True, help_text='When this configuration was frozen for a live campaign.'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    REWARD_FIELDS = (
        'like_reward',
        'comment_reward',
        'share_reward',
        'gift_reward',
        'participation_reward',
        'completion_reward',
    )

    class Meta:
        constraints = [
            # One default row per organization. Two would make "the
            # organization's defaults" ambiguous, and resolution would depend
            # on row order.
            models.UniqueConstraint(
                fields=['organization'],
                condition=models.Q(campaign__isnull=True),
                name='one_default_coin_config_per_organization',
            ),
            # Spent cannot exceed the budget it is checked against. The
            # application enforces this under a lock; the constraint is what
            # holds when something bypasses that path.
            models.CheckConstraint(
                check=models.Q(budget=0) | models.Q(distributed__lte=models.F('budget')),
                name='coin_config_distributed_within_budget',
            ),
        ]
        indexes = [
            models.Index(fields=['organization', 'campaign']),
        ]

    def __str__(self):
        if self.campaign_id:
            return f'Coin config for campaign #{self.campaign_id}'
        return f'Default coin config for {self.organization_id}'

    @property
    def remaining_budget(self):
        """Coins still available. None when no budget is set."""
        if not self.budget:
            return None
        return max(0, self.budget - (self.distributed or 0))

    @property
    def is_exhausted(self):
        return bool(self.budget) and (self.distributed or 0) >= self.budget

    def clean(self):
        """Reject values the platform ceiling forbids.

        Super Admin's limits live on WalletConfig and are enforced here rather
        than in a view, so the admin, a management command and the API all get
        the same answer.
        """
        from api.services.coin_config import CoinConfigError, validate_against_platform_limits

        try:
            validate_against_platform_limits(self)
        except CoinConfigError as exc:
            raise ValidationError(str(exc)) from exc

        if self.campaign_id and self.organization_id:
            # A campaign override must belong to the organization it is filed
            # under, or resolution would hand one organization another's rates.
            if self.campaign.organization_id != self.organization_id:
                raise ValidationError('This campaign belongs to a different organization.')


class CoinConfigurationAudit(models.Model):
    """Who changed a coin value, from what, to what, and when.

    Coin values move real balances, so a change to one is a financial event.
    Recorded as its own row rather than a log line: it has to be queryable
    when someone asks why a campaign paid what it paid.

    ``changed_by`` is always taken from the authenticated user by the service
    layer -- there is no path by which a request supplies it.
    """

    configuration = models.ForeignKey(
        CoinConfiguration, on_delete=models.CASCADE, related_name='audit_entries'
    )
    organization = models.ForeignKey(
        'api.Organization', on_delete=models.CASCADE, related_name='coin_config_audits'
    )
    campaign = models.ForeignKey(
        'api.Campaign',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='coin_config_audits',
    )
    field = models.CharField(max_length=64)
    previous_value = models.CharField(max_length=64)
    new_value = models.CharField(max_length=64)
    changed_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, related_name='coin_config_changes'
    )
    reason = models.TextField(blank=True, default='')
    changed_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-changed_at']
        indexes = [
            models.Index(fields=['organization', '-changed_at']),
            models.Index(fields=['configuration', '-changed_at']),
        ]

    def __str__(self):
        return f'{self.field}: {self.previous_value} -> {self.new_value}'


class CampaignRewardGrant(models.Model):
    """One reward paid to one user for one engagement.

    The idempotency record. A reward is identified by
    (campaign, user, action, reference) -- the reference being the reel,
    comment or gift that earned it -- and the unique constraint is what makes a
    retried request, a double-tap or a redelivered task pay once.

    Without this, "have we already paid for this like?" would be a count over
    transactions, which two concurrent requests can both answer "no".
    """

    configuration = models.ForeignKey(
        CoinConfiguration, on_delete=models.CASCADE, related_name='grants'
    )
    campaign = models.ForeignKey(
        'api.Campaign', on_delete=models.CASCADE, related_name='reward_grants'
    )
    user = models.ForeignKey(
        'auth.User', on_delete=models.CASCADE, related_name='campaign_reward_grants'
    )
    action = models.CharField(max_length=32)
    reference = models.CharField(
        max_length=64,
        help_text='What earned it: reel id, comment id, gift transaction id.',
    )
    coins = models.PositiveIntegerField(validators=[MinValueValidator(0)])
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['campaign', 'user', 'action', 'reference'],
                name='one_reward_per_engagement',
            ),
        ]
        indexes = [
            models.Index(fields=['campaign', 'user']),
            models.Index(fields=['user', '-created_at']),
        ]

    def __str__(self):
        return f'{self.coins} coins to {self.user_id} for {self.action}'
