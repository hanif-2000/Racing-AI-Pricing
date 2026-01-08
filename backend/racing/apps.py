from django.apps import AppConfig


class RacingConfig(AppConfig):
    name = 'racing'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        """Start background services when Django starts"""
        import os
        
        # Only run in main process (not in migrations or shell)
        if os.environ.get('RUN_MAIN') == 'true':
            try:
                from .auto_results import start_background_fetcher
                start_background_fetcher()
                print("✅ Auto-fetch background runner started")
            except Exception as e:
                print(f"⚠️ Could not start auto-fetcher: {e}")