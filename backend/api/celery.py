import os
from celery import Celery
from decouple import config

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('flipstar')

# Load configuration from Django settings
app.config_from_object('django.conf:settings', namespace='CELERY')

# Redis configuration
app.conf.broker_url = f"redis://{config('REDIS_HOST', default='127.0.0.1')}:{config('REDIS_PORT', default=6379)}/0"
app.conf.result_backend = f"redis://{config('REDIS_HOST', default='127.0.0.1')}:{config('REDIS_PORT', default=6379)}/0"

# Celery beat configuration
app.conf.beat_schedule = {
    'cleanup-typing-indicators': {
        'task': 'api.tasks.cleanup_typing_indicators',
        'schedule': 60.0,  # Run every 60 seconds
    },
}

# Auto-discover tasks in all registered apps
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
