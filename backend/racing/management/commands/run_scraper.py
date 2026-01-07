# backend/racing/management/commands/run_scraper.py

from django.core.management.base import BaseCommand
import asyncio
from racing.scraper import fetch_all_data

class Command(BaseCommand):
    help = 'Run the racing scraper'

    def handle(self, *args, **options):
        self.stdout.write('🏇 Starting scraper...')
        
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(fetch_all_data())
            loop.close()
            
            jockey_count = len(result.get('jockey_challenges', []))
            driver_count = len(result.get('driver_challenges', []))
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'✅ Scraper complete! Jockey: {jockey_count}, Driver: {driver_count}'
                )
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Scraper failed: {str(e)}')
            )