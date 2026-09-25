"""
Leaderboard snapshot generation and automatic campaign winner selection.

Ported from the master branch, missing entirely in the current project
before this change -- current had the Leaderboard/LeaderboardEntry/
WinnerSelection/SelectedWinner models (api/models/campaign_extended.py) and
the beat schedule entry point, but none of the tasks that actually populate
them, so leaderboards and winner selections were never generated.
"""

from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from api.models.campaign import Campaign
from api.models.campaign_extended import (
    Leaderboard,
    LeaderboardEntry,
    SelectedWinner,
    UserCampaignStats,
    WinnerSelection,
)


def _period_bounds(period_type, now):
    if period_type == 'daily':
        yesterday = now - timedelta(days=1)
        period_start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        period_end = period_start + timedelta(days=1)
    elif period_type == 'weekly':
        period_start = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        period_end = period_start + timedelta(days=7)
    else:  # monthly
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        period_end = (period_start + timedelta(days=32)).replace(day=1)
    return period_start, period_end


def _generate_period_leaderboard(period_type, campaign_types, rank_field):
    """Shared body for generate_{daily,weekly,monthly}_leaderboards -- they
    differ only in period math, which campaign types are eligible, and
    which UserCampaignStats rank field to update."""
    now = timezone.now()
    period_start, period_end = _period_bounds(period_type, now)

    campaigns = Campaign.objects.filter(status='active', campaign_type__in=campaign_types)

    count = 0
    for campaign in campaigns:
        if Leaderboard.objects.filter(
            campaign=campaign, period_type=period_type, period_start=period_start
        ).exists():
            continue

        Leaderboard.objects.filter(campaign=campaign, period_type=period_type).update(
            is_current=False
        )

        leaderboard = Leaderboard.objects.create(
            campaign=campaign,
            period_type=period_type,
            period_start=period_start,
            period_end=period_end,
            is_current=True,
        )

        stats = UserCampaignStats.objects.filter(campaign=campaign).order_by('-total_score')
        for rank, stat in enumerate(stats, start=1):
            LeaderboardEntry.objects.create(
                leaderboard=leaderboard,
                user=stat.user,
                rank=rank,
                score=stat.total_score,
                posts_count=stat.approved_posts,
            )
            setattr(stat, rank_field, rank)
            stat.save(update_fields=[rank_field])

        count += 1

    return period_start, period_end, count


@shared_task
def generate_daily_leaderboards():
    """Generate daily leaderboards for all active campaigns."""
    try:
        period_start, _period_end, count = _generate_period_leaderboard(
            'daily',
            ['daily', 'weekly', 'monthly', 'grand'],
            'daily_rank',
        )
        return f'Generated {count} daily leaderboards for {period_start.date()}'
    except Exception as e:
        return f'Error generating daily leaderboards: {str(e)}'


@shared_task
def generate_weekly_leaderboards():
    """Generate weekly leaderboards for all active campaigns."""
    try:
        period_start, _period_end, count = _generate_period_leaderboard(
            'weekly',
            ['weekly', 'monthly', 'grand'],
            'weekly_rank',
        )
        return f'Generated {count} weekly leaderboards for week of {period_start.date()}'
    except Exception as e:
        return f'Error generating weekly leaderboards: {str(e)}'


@shared_task
def generate_monthly_leaderboards():
    """Generate monthly leaderboards for all active campaigns."""
    try:
        period_start, _period_end, count = _generate_period_leaderboard(
            'monthly',
            ['monthly', 'grand'],
            'monthly_rank',
        )
        return f"Generated {count} monthly leaderboards for {period_start.strftime('%B %Y')}"
    except Exception as e:
        return f'Error generating monthly leaderboards: {str(e)}'


def _leaderboard_for(campaign):
    """The leaderboard a campaign's winners should be read from.

    This used to look only for period_type='overall', and nothing in this
    codebase creates one -- generate_{daily,weekly,monthly}_leaderboards
    above write 'daily', 'weekly' and 'monthly'. So the lookup never matched
    and the task below selected a winner for no campaign, ever.

    A campaign's own type names the period it runs over, so that is what is
    read, with 'overall' still accepted in case one is ever created and the
    most recent of any type as a last resort. Grand campaigns have no
    period of their own and fall through to that.
    """
    period_types = []
    if campaign.campaign_type in ('daily', 'weekly', 'monthly'):
        period_types.append(campaign.campaign_type)
    period_types.append('overall')

    for period_type in period_types:
        leaderboard = (
            Leaderboard.objects.filter(campaign=campaign, period_type=period_type)
            .order_by('-period_start')
            .first()
        )
        if leaderboard:
            return leaderboard

    return Leaderboard.objects.filter(campaign=campaign).order_by('-period_start').first()


@shared_task
def auto_select_campaign_winners():
    """Automatically select winners for campaigns that have ended.

    Winners are chosen through CampaignScoringEngine rather than by reading
    ranks straight off the leaderboard, so the participation rules (5 of 7,
    20 of 30) and the 30-day win restriction apply here exactly as they do
    to an admin selecting winners by hand. Taking the top three by score
    alone, as this did, would hand prizes to subscribers who never qualified.
    """
    from api.services.concurrency import claim_transition
    from api.services.prize_delivery import award_all
    from api.services.scoring.engine import CampaignScoringEngine

    try:
        now = timezone.now()

        ended_campaigns = Campaign.objects.filter(
            status='active',
            entry_deadline__lt=now,
        ).exclude(winner_selections__isnull=False)

        count = 0
        for campaign in ended_campaigns:
            leaderboard = _leaderboard_for(campaign)

            if not leaderboard:
                continue

            selection_type = (
                campaign.campaign_type
                if campaign.campaign_type in ('daily', 'weekly', 'monthly')
                else 'grand'
            )

            # One runner completes a campaign. Two overlapping beats -- or a
            # retried task -- would otherwise both pass the filter above and
            # announce two sets of winners.
            if not claim_transition(
                Campaign, campaign.pk, expect='active', to='completed', winners_announced=True
            ):
                continue

            entries = list(leaderboard.entries.order_by('rank'))
            winners = CampaignScoringEngine(campaign).select_winners(entries)

            winner_selection = WinnerSelection.objects.create(
                campaign=campaign,
                selection_type=selection_type,
                leaderboard=leaderboard,
                is_finalized=True,
                finalized_at=now,
            )

            for winner in winners:
                SelectedWinner.objects.create(
                    selection=winner_selection,
                    user=winner['user'],
                    rank=winner['rank'],
                    final_score=winner.get('score', winner.get('final_score', 0)),
                    selection_method=winner.get('method', 'top_scorer'),
                )

            # Record what each winner is owed, with its delivery deadline,
            # before anything is sent. Awarding is idempotent, so a re-run
            # reuses the existing prize rows rather than creating a second
            # set to pay.
            award_all(
                campaign,
                [winner['user'] for winner in winners],
                selection_type,
                closed_at=campaign.entry_deadline,
            )

            count += 1

        return f'Auto-selected winners for {count} ended campaigns'
    except Exception as e:
        return f'Error auto-selecting winners: {str(e)}'
