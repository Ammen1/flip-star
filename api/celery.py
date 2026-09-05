import os

from celery import Celery
from celery.signals import beat_init, worker_init

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
    'auto-select-winners': {
        'task': 'api.tasks.auto_select_campaign_winners',
        'schedule': 3600.0,  # Run every hour to check for ended campaigns
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
}

# Auto-discover tasks in all registered apps
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
