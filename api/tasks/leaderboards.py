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
        period_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
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
        if Leaderboard.objects.filter(campaign=campaign, period_type=period_type, period_start=period_start).exists():
            continue

        Leaderboard.objects.filter(campaign=campaign, period_type=period_type).update(is_current=False)

        leaderboard = Leaderboard.objects.create(
            campaign=campaign, period_type=period_type, period_start=period_start, period_end=period_end,
            is_current=True,
        )

        stats = UserCampaignStats.objects.filter(campaign=campaign).order_by('-total_score')
        for rank, stat in enumerate(stats, start=1):
            LeaderboardEntry.objects.create(
                leaderboard=leaderboard, user=stat.user, rank=rank, score=stat.total_score,
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
            'daily', ['daily', 'weekly', 'monthly', 'grand'], 'daily_rank',
        )
        return f'Generated {count} daily leaderboards for {period_start.date()}'
    except Exception as e:
        return f'Error generating daily leaderboards: {str(e)}'


@shared_task
def generate_weekly_leaderboards():
    """Generate weekly leaderboards for all active campaigns."""
    try:
        period_start, _period_end, count = _generate_period_leaderboard(
            'weekly', ['weekly', 'monthly', 'grand'], 'weekly_rank',
        )
        return f'Generated {count} weekly leaderboards for week of {period_start.date()}'
    except Exception as e:
        return f'Error generating weekly leaderboards: {str(e)}'


@shared_task
def generate_monthly_leaderboards():
    """Generate monthly leaderboards for all active campaigns."""
    try:
        period_start, _period_end, count = _generate_period_leaderboard(
            'monthly', ['monthly', 'grand'], 'monthly_rank',
        )
        return f"Generated {count} monthly leaderboards for {period_start.strftime('%B %Y')}"
    except Exception as e:
        return f'Error generating monthly leaderboards: {str(e)}'


@shared_task
def auto_select_campaign_winners():
    """Automatically select winners for campaigns that have ended.

    Ported as-is from master, including a real gap there: this only looks
    at Leaderboard rows with period_type='overall', but nothing in this
    codebase -- not generate_{daily,weekly,monthly}_leaderboards above, not
    anything else searched for in master -- ever creates one. In practice
    the `if not leaderboard: continue` below always fires, so this task
    currently never selects a winner for any campaign. Left matching
    master's actual (non-)behavior rather than guessing at which leaderboard
    period_type it was meant to read, since master gives no signal either
    way and inventing one risks picking wrong winners.
    """
    try:
        now = timezone.now()

        ended_campaigns = Campaign.objects.filter(
            status='active', entry_deadline__lt=now,
        ).exclude(winner_selections__isnull=False)

        count = 0
        for campaign in ended_campaigns:
            leaderboard = Leaderboard.objects.filter(
                campaign=campaign, period_type='overall',
            ).order_by('-period_start').first()

            if not leaderboard:
                continue

            selection_type = campaign.campaign_type if campaign.campaign_type in ('daily', 'weekly', 'monthly') else 'grand'

            winner_selection = WinnerSelection.objects.create(
                campaign=campaign, selection_type=selection_type, leaderboard=leaderboard,
                is_finalized=True, finalized_at=now,
            )

            for entry in leaderboard.entries.order_by('rank')[:3]:
                SelectedWinner.objects.create(
                    selection=winner_selection, user=entry.user, rank=entry.rank,
                    final_score=entry.score, selection_method='top_scorer',
                )

            campaign.status = 'completed'
            campaign.winners_announced = True
            campaign.save(update_fields=['status', 'winners_announced'])

            count += 1

        return f'Auto-selected winners for {count} ended campaigns'
    except Exception as e:
        return f'Error auto-selecting winners: {str(e)}'
