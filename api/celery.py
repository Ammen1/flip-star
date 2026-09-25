import os

from celery import Celery
from celery.signals import beat_init, worker_init, worker_shutdown

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('flipstar')

# Load configuration from Django settings. The CELERY_ namespace supplies
# broker_url and result_backend, which config/settings/base.py builds from the
# resolved Redis location -- so the connection details follow the same
# environment -> Vault -> .env chain as everything else.
#
# These were previously rebuilt here by reading REDIS_HOST/REDIS_PORT through
# decouple, which bypassed Vault and could disagree with Django's own settings.
app.config_from_object('django.conf:settings', namespace='CELERY')


@worker_init.connect
@beat_init.connect
def _verify_infrastructure_before_starting(**kwargs):
    """
    Refuses to start the worker/beat process if Redis (this process's own
    broker) OR Vault is configured but unreachable -- checked
    independently, so either one alone failing is enough. Mirrors the same
    check config/wsgi.py and config/asgi.py already run for the API
    process; a worker that started anyway with a dead broker would sit
    idle and silently never pick up a task.

    Deliberately deferred to the worker_init/beat_init signal rather than
    run at module import time: this module is imported as a side effect of
    Django loading config.settings (via config/__init__.py) for every
    process, including the API server -- an eager check here would run
    before Django's settings module has finished importing itself,
    recursing back into django.conf.settings mid-setup. The signal only
    fires once an actual celery worker/beat process is really starting.
    See infrastructure/health/startup.py for the exact conditions checked.
    """
    from infrastructure.health import verify_redis_and_vault

    verify_redis_and_vault()


@worker_init.connect
def _bind_sms_gateway(**kwargs):
    """Open the SMPP session, but only in the worker that owns it.

    Gated on ``SMS_WORKER``, an explicit environment flag set by the SMS
    worker deployment alone -- not inferred from the ``-Q`` options, which
    would mean reading Celery internals that change between versions.

    Binding in every worker would open one session per process: eight, at the
    general workers' two replicas by concurrency four. Operators cap
    concurrent binds, so that is not merely wasteful.

    A gateway unreachable at startup is logged and left. The first delivery
    reconnects, and refusing to start would mean an SMPP outage also stopped
    messages being queued for later.
    """
    import logging

    from django.conf import settings

    logger = logging.getLogger(__name__)

    if not getattr(settings, 'SMS_WORKER', False):
        return

    provider = getattr(settings, 'SMS_PROVIDER', '')
    if provider != 'timwe_smpp':
        logger.info('SMS worker started with SMS_PROVIDER=%s; no SMPP bind needed.', provider)
        return

    from api.integrations.smpp.client import get_client
    from api.services.sms.dlr_listener import attach_dlr_handler

    client = get_client()
    attach_dlr_handler(client)
    try:
        client.connect()
    except Exception as exc:
        logger.warning(
            'SMPP_BIND_DEFERRED reason=%s -- will bind on first send', type(exc).__name__
        )


@worker_shutdown.connect
def _unbind_sms_gateway(**kwargs):
    """Close the SMPP session cleanly on shutdown.

    Unbinding tells the gateway the session ended rather than leaving it to
    time the bind out, which matters when an operator caps concurrent binds:
    a restart would otherwise consume a second slot while the first expires.
    Queued messages are unaffected -- they live in the database and on the
    broker, not in this process.
    """
    from api.integrations.smpp.client import reset_client

    reset_client()


# Celery beat configuration
app.conf.beat_schedule = {
    'cleanup-typing-indicators': {
        'task': 'api.tasks.cleanup_typing_indicators',
        'schedule': 60.0,  # Run every 60 seconds
    },
    'generate-daily-leaderboards': {
        'task': 'api.tasks.generate_daily_leaderboards',
        'schedule': 86400.0,  # Run every 24 hours
    },
    'generate-weekly-leaderboards': {
        'task': 'api.tasks.generate_weekly_leaderboards',
        'schedule': 604800.0,  # Run every 7 days
    },
    'generate-monthly-leaderboards': {
        'task': 'api.tasks.generate_monthly_leaderboards',
        'schedule': 2592000.0,  # Run every 30 days
    },
    # Subscription gift coins, paid a day at a time rather than all on the
    # day of the charge. Hourly, not daily: the task pays only what each plan
    # is owed and has already been paid nothing twice, so running it often
    # costs one indexed query and means a subscriber whose day ticks over at
    # 14:20 waits an hour rather than until tomorrow. It also catches up any
    # day missed while the worker was down.
    'grant-daily-subscription-gifts': {
        'task': 'api.tasks.grant_daily_subscription_gifts',
        'schedule': 3600.0,
    },
    'auto-select-winners': {
        'task': 'api.tasks.auto_select_campaign_winners',
        'schedule': 3600.0,  # Run every hour to check for ended campaigns
    },
    # Winner selection records what each winner is owed; this is what sends
    # it. Without this nothing ever delivered a prize on its own -- every
    # one sat 'pending' until somebody opened the admin -- while the
    # requirement promises delivery within 10 days (20 for the Grand Final).
    #
    # Every guard is in the delivery service, so running it often cannot pay
    # anybody twice: a settled or in-flight prize is refused there. Every 15
    # minutes, because a winner waiting on 300,000 ETB notices the
    # difference between minutes and hours, and the query is one indexed
    # filter that finds nothing on most runs.
    # Points not withdrawn or converted within 180 days of inactivity are
    # lost. Daily: the rule is measured in days, so a shorter period would
    # only re-examine the same accounts. Coins are never touched.
    'expire-inactive-points': {
        'task': 'api.tasks.expire_inactive_points',
        'schedule': 86400.0,
    },
    'deliver-pending-prizes': {
        'task': 'api.tasks.deliver_pending_prizes',
        'schedule': 900.0,
    },
    # What delivery cannot fix by itself: prizes past their deadline,
    # payouts Telebirr accepted and never confirmed, and deliveries that
    # have failed as often as the scheduler will try. Reported hourly so the
    # gap between "this broke" and "somebody knows" is an hour, not however
    # long until the next time a person looks.
    # Campaign entries queue as 'pending' and only a person clears them,
    # while eligibility counts them towards a prize. Reported every two
    # hours so a neglected campaign is noticed while there is still time to
    # moderate it, rather than after it has decided a winner.
    'report-moderation-backlog': {
        'task': 'api.tasks.report_moderation_backlog',
        'schedule': 7200.0,
    },
    'report-prize-delivery-problems': {
        'task': 'api.tasks.report_prize_delivery_problems',
        'schedule': 3600.0,
    },
    # Nothing retired finished boost campaigns, so they stayed status='active'
    # indefinitely -- leaving Reel.is_boosted set and any consumer that trusts
    # status alone treating a finished boost as live. Every 5 minutes because
    # the granularity a buyer notices is "my boost ended", not "some time
    # today"; the query is a single indexed filter, so the cost is negligible.
    'expire-boost-campaigns': {
        'task': 'api.tasks.expire_boost_campaigns',
        'schedule': 300.0,
    },
    # A post is queued for processing after its transaction commits. If the
    # broker was unreachable at that moment, or a worker died holding the
    # post, nothing else would ever pick it up; this finds and re-queues both.
    'redrive-stuck-media': {
        'task': 'api.tasks.redrive_stuck_media',
        'schedule': 600.0,
    },
    # Originals past MEDIA_SOURCE_RETENTION_DAYS. A no-op while that is 0,
    # which is the default: originals are kept until someone decides otherwise.
    'purge-processed-sources': {
        'task': 'api.tasks.purge_processed_sources',
        'schedule': 86400.0,
    },
    # Lapsed TIMWE airtime subscriptions: charge each one due a renewal, and
    # try again an hour after TIMWE refused one (too little airtime), for
    # TIMWE_RENEWAL_WINDOW_DAYS. A no-op unless both renewal switches are on.
    # Expires before the next run, so a backlog after an outage is one sweep,
    # not one per missed hour.
    'renew-expired-airtime-subscriptions': {
        'task': 'api.tasks.subscription_renewal.sweep_expired_subscriptions',
        'schedule': 3600.0,
        'options': {'expires': 3300},
    },
}

# Auto-discover tasks in all registered apps
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
