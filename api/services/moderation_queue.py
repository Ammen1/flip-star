"""How long campaign entries have been waiting to be moderated.

Why this exists
---------------
``PostScore.moderation_status`` defaults to ``pending`` and moderation is
entirely manual: an admin opens the campaign page and approves or rejects.
Nothing scheduled ever looked at the queue, so entries could sit pending
indefinitely -- and eligibility counts pending entries, which means an
unreviewed entry can carry someone to a prize.

Excluding pending entries from eligibility would be the other fix, and it is
the wrong one: it penalises a subscriber for a moderation backlog they did
not cause and cannot clear. So the entries still count, and this module
makes the backlog visible *before* it decides a winner rather than after.

What this does not do
---------------------
It does not moderate anything, and it does not block winner selection.
Automated screening and a hard gate on unreviewed entries are both product
decisions with their own trade-offs; neither is a gap to close quietly
inside a reporting helper. This reports an age, in the same shape as the
prize sweep's overdue report.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

#: An entry older than this has been waiting long enough to be worth saying
#: out loud. Chosen to be well inside the shortest competition period -- a
#: Daily Sprint closes in a day -- so a backlog is reported while there is
#: still time to clear it before it counts towards a prize.
STALE_AFTER_HOURS = 12

#: Louder threshold: at this age an entry is very likely to be judged by the
#: scoring engine before anybody looks at it.
CRITICAL_AFTER_HOURS = 24


def pending_entries(*, campaign=None):
    """Campaign entries awaiting a moderation decision, oldest first."""
    from api.models.campaign_extended import PostScore

    queryset = PostScore.objects.filter(moderation_status='pending')
    if campaign is not None:
        queryset = queryset.filter(campaign=campaign)
    return queryset.order_by('created_at')


def stale_entries(*, hours=STALE_AFTER_HOURS, now=None, campaign=None):
    """Pending entries that have been pending longer than ``hours``."""
    now = now or timezone.now()
    cutoff = now - timedelta(hours=hours)
    return pending_entries(campaign=campaign).filter(created_at__lt=cutoff)


def age_hours(entry, *, now=None):
    """How long this entry has been waiting, in hours."""
    now = now or timezone.now()
    if entry.created_at is None:
        return 0.0
    return (now - entry.created_at).total_seconds() / 3600.0


def queue_report(*, now=None, campaign=None):
    """A summary of the pending queue.

    Returns a dict rather than logging, so the task can log it, the admin can
    render it, and a test can assert on it without parsing log lines.

    ``oldest_hours`` is the number that matters: a large queue that is all
    minutes old is a busy campaign, and a small queue that is two days old is
    a campaign nobody is moderating.
    """
    now = now or timezone.now()
    pending = list(
        pending_entries(campaign=campaign).select_related('campaign', 'user')
    )

    stale = [e for e in pending if age_hours(e, now=now) >= STALE_AFTER_HOURS]
    critical = [e for e in pending if age_hours(e, now=now) >= CRITICAL_AFTER_HOURS]
    oldest = pending[0] if pending else None

    return {
        'pending': len(pending),
        'stale': len(stale),
        'critical': len(critical),
        'oldest_hours': round(age_hours(oldest, now=now), 1) if oldest else 0.0,
        'oldest_entry_id': oldest.pk if oldest else None,
        'oldest_campaign_id': oldest.campaign_id if oldest else None,
    }


def per_campaign_report(*, now=None):
    """The same summary, split by campaign.

    A single total hides the case this exists to catch: one neglected
    campaign inside an otherwise healthy queue.
    """
    from api.models.campaign_extended import PostScore

    now = now or timezone.now()
    campaign_ids = (
        PostScore.objects.filter(moderation_status='pending')
        .values_list('campaign_id', flat=True)
        .distinct()
    )

    reports = {}
    for campaign_id in campaign_ids:
        entries = list(
            PostScore.objects.filter(
                moderation_status='pending', campaign_id=campaign_id
            ).order_by('created_at')
        )
        if not entries:
            continue
        reports[campaign_id] = {
            'pending': len(entries),
            'stale': sum(1 for e in entries if age_hours(e, now=now) >= STALE_AFTER_HOURS),
            'critical': sum(1 for e in entries if age_hours(e, now=now) >= CRITICAL_AFTER_HOURS),
            'oldest_hours': round(age_hours(entries[0], now=now), 1),
        }
    return reports
