"""
AUTO RESULTS FETCHER
Automatically fetches race results and updates live trackers

Features:
- Polls for new race results at configurable intervals
- Updates points ledger automatically
- Triggers AI price recalculation
- Can run as background thread or be triggered manually
"""

import asyncio
import threading
import time
import re
from datetime import datetime, date
from typing import List, Dict, Optional

# Try importing playwright (may not be installed)
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("⚠️ Playwright not installed - auto-fetch will use mock data")


class AutoResultsFetcher:
    """
    Fetches race results automatically from Ladbrokes
    """
    
    def __init__(self):
        self.timeout = 30000
        self.is_running = False
    
    async def get_browser(self):
        """Initialize browser"""
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            locale='en-AU',
            timezone_id='Australia/Sydney'
        )
        return playwright, browser, context
    
    async def fetch_results(self, meeting_name: str, last_race_fetched: int = 0) -> Dict:
        """
        Fetch results for races after last_race_fetched
        
        Returns:
        {
            'success': True/False,
            'meeting': 'MEETING_NAME',
            'new_races': [
                {'race': 3, 'results': [{'position': 1, 'jockey': 'Name'}, ...]},
                ...
            ],
            'last_race': 5
        }
        """
        if not PLAYWRIGHT_AVAILABLE:
            return self._mock_fetch(meeting_name, last_race_fetched)
        
        result = {
            'success': False,
            'meeting': meeting_name.upper(),
            'new_races': [],
            'last_race': last_race_fetched,
            'error': None
        }
        
        playwright = browser = context = None
        
        try:
            playwright, browser, context = await self.get_browser()
            page = await context.new_page()
            
            print(f"[AutoFetch] Checking {meeting_name} for new results...")
            
            # Go to results page
            await page.goto('https://www.ladbrokes.com.au/racing/results', timeout=60000)
            await asyncio.sleep(3)
            
            # Scroll to load content
            for _ in range(5):
                await page.evaluate('window.scrollBy(0, 300)')
                await asyncio.sleep(0.2)
            
            text = await page.evaluate('document.body.innerText')
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            
            # Find meeting in results
            meeting_idx = None
            for i, line in enumerate(lines):
                if line.lower() == meeting_name.lower():
                    meeting_idx = i
                    break
            
            if meeting_idx is None:
                result['error'] = f'Meeting {meeting_name} not found in results'
                return result
            
            # Find completed races
            completed_races = []
            i = meeting_idx + 2
            while i < min(meeting_idx + 30, len(lines)):
                line = lines[i]
                # Stop if we hit another state/region
                if line in ['VIC', 'NSW', 'QLD', 'SA', 'WA', 'TAS', 'NT', 'NZ', 'HK'] and i > meeting_idx + 3:
                    break
                
                m = re.match(r'^R(\d+)$', line)
                if m and i + 1 < len(lines):
                    race_num = int(m.group(1))
                    result_cell = lines[i + 1]
                    # Check if race has results (format: "1, 2, 3" or "1/2, 3, 4")
                    if re.match(r'^\d+[/\d]*,\s*\d+', result_cell):
                        if race_num > last_race_fetched:
                            completed_races.append((race_num, result_cell))
                i += 1
            
            print(f"[AutoFetch] Found {len(completed_races)} new completed races")
            
            # Fetch details for each new race
            for race_num, result_cell in completed_races:
                try:
                    race_result = await self._fetch_race_details(page, meeting_name, race_num, result_cell)
                    if race_result:
                        result['new_races'].append(race_result)
                        result['last_race'] = max(result['last_race'], race_num)
                except Exception as e:
                    print(f"[AutoFetch] Error fetching R{race_num}: {e}")
            
            result['success'] = True
            print(f"[AutoFetch] Done - {len(result['new_races'])} new races fetched")
            
        except Exception as e:
            result['error'] = str(e)
            print(f"[AutoFetch] Error: {e}")
        
        finally:
            if browser:
                await browser.close()
            if playwright:
                await playwright.stop()
        
        return result
    
    async def _fetch_race_details(self, page, meeting_name: str, race_num: int, result_cell: str) -> Optional[Dict]:
        """Fetch detailed results for a single race"""
        try:
            # Navigate back to results
            await page.goto('https://www.ladbrokes.com.au/racing/results', timeout=30000)
            await asyncio.sleep(2)
            
            # Scroll
            for _ in range(5):
                await page.evaluate('window.scrollBy(0, 300)')
                await asyncio.sleep(0.2)
            
            # Click on the result cell
            await page.click(f'text="{result_cell}"', timeout=5000)
            await asyncio.sleep(3)
            
            # Get page content
            text = await page.evaluate('document.body.innerText')
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            
            # Extract jockeys from RESULTS section
            results = []
            in_results = False
            
            for line in lines:
                if line == 'RESULTS':
                    in_results = True
                    continue
                if in_results and line in ['EXOTIC RESULTS', 'FINAL MARGINS']:
                    break
                
                # Match jockey line: "J Name" or "J: Name"
                if in_results and (re.match(r'^J\s+[A-Z]', line) or re.match(r'^J:\s*[A-Z]', line)):
                    jockey = re.sub(r'^J[:\s]+', '', line).strip()
                    jockey = re.sub(r'\s*\([^)]+\)$', '', jockey)  # Remove (a3) etc
                    
                    if jockey and jockey not in [r['jockey'] for r in results]:
                        results.append({
                            'position': len(results) + 1,
                            'jockey': jockey
                        })
                    
                    if len(results) >= 3:
                        break
            
            if results:
                print(f"[AutoFetch] R{race_num}: {[r['jockey'] for r in results]}")
                return {
                    'race': race_num,
                    'results': results
                }
            
        except Exception as e:
            print(f"[AutoFetch] R{race_num} error: {str(e)[:50]}")
        
        return None
    
    def _mock_fetch(self, meeting_name: str, last_race_fetched: int) -> Dict:
        """Mock fetch for testing without Playwright"""
        return {
            'success': True,
            'meeting': meeting_name.upper(),
            'new_races': [],
            'last_race': last_race_fetched,
            'mock': True,
            'message': 'Playwright not available - no actual scraping performed'
        }


def normalize_name(name: str) -> str:
    """Normalize jockey/driver name for matching"""
    name = re.sub(r'\s*\([^)]+\)$', '', name).strip()
    return ' '.join(name.split()).lower()


def match_jockey(result_name: str, challenge_jockeys: List[str]) -> Optional[str]:
    """Match result jockey name to challenge jockey name"""
    result_norm = normalize_name(result_name)
    result_last = result_norm.split()[-1] if result_norm.split() else ''
    
    for cj in challenge_jockeys:
        cj_norm = normalize_name(cj)
        cj_last = cj_norm.split()[-1] if cj_norm.split() else ''
        
        # Exact match
        if result_norm == cj_norm:
            return cj
        
        # Last name match
        if result_last == cj_last and len(result_last) > 2:
            return cj
        
        # Partial match
        if result_norm in cj_norm or cj_norm in result_norm:
            return cj
    
    return None


def fetch_and_update_meeting(meeting_name: str, jockeys_list: List[str], last_race_fetched: int = 0) -> Dict:
    """
    Fetch results and update database
    
    This is the main function to call from views
    """
    from .models import PointsLedger, LiveTrackerState, AutoFetchConfig
    from django.utils import timezone
    
    # Run async fetch
    fetcher = AutoResultsFetcher()

    try:
        # Use existing event loop if available, otherwise create a new one
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("Loop is closed")
        fetch_result = loop.run_until_complete(
            fetcher.fetch_results(meeting_name, last_race_fetched)
        )
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            fetch_result = loop.run_until_complete(
                fetcher.fetch_results(meeting_name, last_race_fetched)
            )
        finally:
            loop.close()
    
    if not fetch_result['success']:
        return fetch_result
    
    today = date.today()
    points_map = {1: 3, 2: 2, 3: 1}
    
    # Process each new race
    for race_data in fetch_result['new_races']:
        race_num = race_data['race']
        results = race_data['results']
        
        # Detect dead heats
        position_counts = {}
        for r in results:
            pos = r.get('position', 0)
            if pos in [1, 2, 3]:
                position_counts[pos] = position_counts.get(pos, 0) + 1
        
        # Award points
        for r in results:
            result_jockey = r.get('jockey', '')
            position = r.get('position', 0)
            
            if position not in [1, 2, 3]:
                continue
            
            # Match to challenge jockey
            matched = match_jockey(result_jockey, jockeys_list)
            
            if not matched:
                continue
            
            # Calculate points
            num_at_position = position_counts.get(position, 1)
            is_dead_heat = num_at_position > 1
            
            if is_dead_heat:
                positions_consumed = list(range(position, min(position + num_at_position, 4)))
                total_points = sum(points_map.get(p, 0) for p in positions_consumed)
                points = round(total_points / num_at_position, 1)
            else:
                points = points_map.get(position, 0)
            
            # Save to points ledger
            PointsLedger.objects.update_or_create(
                meeting_name=meeting_name.upper(),
                meeting_date=today,
                participant_name=matched,
                race_number=race_num,
                defaults={
                    'participant_type': 'jockey',
                    'position': position,
                    'points_earned': points,
                    'is_dead_heat': is_dead_heat
                }
            )
            
            print(f"[AutoFetch] ✅ {matched} R{race_num}: P{position} +{points}")
        
        # Update live tracker if exists
        try:
            tracker = LiveTrackerState.objects.get(meeting_name=meeting_name.upper())
            participants = tracker.get_participants()
            
            # Update participant points
            for r in results:
                result_jockey = r.get('jockey', '')
                position = r.get('position', 0)
                matched = match_jockey(result_jockey, jockeys_list)
                
                if matched and matched in participants and position in [1, 2, 3]:
                    num_at_position = position_counts.get(position, 1)
                    is_dead_heat = num_at_position > 1
                    
                    if is_dead_heat:
                        positions_consumed = list(range(position, min(position + num_at_position, 4)))
                        total_points = sum(points_map.get(p, 0) for p in positions_consumed)
                        points = round(total_points / num_at_position, 1)
                    else:
                        points = points_map.get(position, 0)
                    
                    participants[matched]['current_points'] += points
                    participants[matched]['positions'].append(position)
                    participants[matched]['points_history'].append(points)
                    participants[matched]['rides_remaining'] -= 1
            
            # Mark unplaced jockeys
            placed = [match_jockey(r['jockey'], jockeys_list) for r in results[:3]]
            for name, data in participants.items():
                if name not in placed and data['rides_remaining'] > 0:
                    data['rides_remaining'] -= 1
                    data['positions'].append(0)
                    data['points_history'].append(0)
            
            tracker.set_participants(participants)
            tracker.races_completed = race_num
            tracker.add_race_result({
                'race': race_num,
                'results': results,
                'timestamp': datetime.now().isoformat()
            })
            tracker.save()
            
        except LiveTrackerState.DoesNotExist:
            pass
    
    # Update auto-fetch config
    try:
        config = AutoFetchConfig.objects.get(meeting_name=meeting_name.upper())
        config.last_fetch_at = timezone.now()
        config.last_race_fetched = fetch_result['last_race']
        config.save()
    except AutoFetchConfig.DoesNotExist:
        pass
    
    # Get updated standings
    standings = PointsLedger.get_meeting_standings(meeting_name.upper(), today)
    
    return {
        'success': True,
        'meeting': meeting_name.upper(),
        'new_races': len(fetch_result['new_races']),
        'last_race': fetch_result['last_race'],
        'standings': standings,
        'timestamp': datetime.now().isoformat()
    }


# =====================================================
# BACKGROUND AUTO-FETCH RUNNER
# =====================================================

class AutoFetchRunner:
    """
    Runs auto-fetch in background for all enabled meetings
    """
    
    def __init__(self, check_interval: int = 30):
        self.check_interval = check_interval  # Seconds between checks
        self.is_running = False
        self.thread = None
    
    def start(self):
        """Start background thread"""
        if self.is_running:
            print("[AutoFetchRunner] Already running")
            return
        
        self.is_running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        print("[AutoFetchRunner] Started")
    
    def stop(self):
        """Stop background thread"""
        self.is_running = False
        print("[AutoFetchRunner] Stopped")
    
    def _run_loop(self):
        """Main loop"""
        from .models import AutoFetchConfig
        from django.utils import timezone
        from datetime import timedelta
        
        while self.is_running:
            try:
                # Get all enabled configs
                configs = AutoFetchConfig.objects.filter(is_enabled=True)
                
                for config in configs:
                    # Check if due for fetch
                    if config.last_fetch_at:
                        next_fetch = config.last_fetch_at + timedelta(seconds=config.fetch_interval_seconds)
                        if timezone.now() < next_fetch:
                            continue
                    
                    # Skip if meeting complete
                    if config.last_race_fetched >= config.total_races:
                        continue
                    
                    print(f"[AutoFetchRunner] Fetching {config.meeting_name}...")
                    
                    try:
                        result = fetch_and_update_meeting(
                            config.meeting_name,
                            config.get_jockeys_list(),
                            config.last_race_fetched
                        )
                        
                        if result.get('success'):
                            print(f"[AutoFetchRunner] ✅ {config.meeting_name}: {result.get('new_races', 0)} new races")
                        
                    except Exception as e:
                        print(f"[AutoFetchRunner] ❌ {config.meeting_name}: {e}")
                
            except Exception as e:
                print(f"[AutoFetchRunner] Loop error: {e}")
            
            # Wait before next check
            time.sleep(self.check_interval)


# Global runner instance
AUTO_FETCH_RUNNER = AutoFetchRunner()


def start_background_fetcher():
    """Start the background fetcher"""
    AUTO_FETCH_RUNNER.start()


def stop_background_fetcher():
    """Stop the background fetcher"""
    AUTO_FETCH_RUNNER.stop()