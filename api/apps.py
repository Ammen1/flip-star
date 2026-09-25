from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api'

    def ready(self):
        import api.checks  # noqa: F401  -- registers deployment config checks
        import api.signals  # noqa: F401
