from django.apps import AppConfig


class RacingConfig(AppConfig):
    name = 'racing'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        """Start background services when Django starts"""
        import os
        import sys

        # Skip during migrations, shell, or collectstatic
        skip_commands = {'migrate', 'makemigrations', 'collectstatic', 'shell', 'createsuperuser'}
        if any(cmd in sys.argv for cmd in skip_commands):
            return

        # RUN_MAIN is set by runserver reloader (avoid double-start).
        # For gunicorn/WSGI, RUN_MAIN is never set, so we always start.
        is_runserver = 'runserver' in sys.argv
        if is_runserver and os.environ.get('RUN_MAIN') != 'true':
            return  # Wait for reloader child process

        try:
            from .auto_results import start_background_fetcher
            start_background_fetcher()
            print("Auto-fetch background runner started")
        except Exception as e:
            print(f"Could not start auto-fetcher: {e}")