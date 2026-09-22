"""Celery tasks.

Celery's ``autodiscover_tasks()`` imports ``api.tasks``; every task must be
reachable from this module for it to be registered.

Task functions are thin: they resolve arguments, call into ``api/services`` or
``api/integrations``, and handle retries. Business rules do not live here.
"""

from api.tasks.boost import expire_boost_campaigns
from api.tasks.leaderboards import (
    auto_select_campaign_winners,
    generate_daily_leaderboards,
    generate_monthly_leaderboards,
    generate_weekly_leaderboards,
)
from api.tasks.media import (
    cleanup_typing_indicators,
    delete_post_media,
    generate_reel_blurhash,
    optimize_profile_image,
    process_reel_media,
    purge_processed_sources,
    redrive_stuck_media,
    send_push_notification,
)
from api.tasks.sms import deliver_sms
from api.tasks.subscription_gifts import grant_daily_subscription_gifts
from api.tasks.subscription_renewal import renew_expired_subscription, sweep_expired_subscriptions

__all__ = [
    'deliver_sms',
    'grant_daily_subscription_gifts',
    'renew_expired_subscription',
    'sweep_expired_subscriptions',
    'expire_boost_campaigns',
    'auto_select_campaign_winners',
    'cleanup_typing_indicators',
    'delete_post_media',
    'generate_daily_leaderboards',
    'generate_monthly_leaderboards',
    'generate_reel_blurhash',
    'generate_weekly_leaderboards',
    'optimize_profile_image',
    'process_reel_media',
    'purge_processed_sources',
    'redrive_stuck_media',
    'send_push_notification',
]
