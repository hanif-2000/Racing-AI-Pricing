"""
RESULTS FETCHER - Runs in GitHub Actions
Fetches race results from Ladbrokes and sends to API
"""

import asyncio
import re
import os
import requests
from datetime import datetime
from playwright.async_api import async_playwright

API_URL = "https://api.jockeydriverchallenge.com"


async def fetch_meeting_results(meeting_name: str):
    """Fetch results for a meeting from Ladbrokes"""
    results = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        )
        page = await context.new_page()
        
        try:
            print(f"[ResultsFetcher] Checking {meeting_name}...")
            
            await page.goto('https://www.ladbrokes.com.au/racing/results', timeout=60000)
            await asyncio.sleep(3)
            
            # Scroll to load
            for _ in range(5):
                await page.evaluate('window.scrollBy(0, 300)')
                await asyncio.sleep(0.3)
            
            text = await page.evaluate('document.body.innerText')
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            
            # Find meeting
            meeting_idx = None
            for i, line in enumerate(lines):
                if line.upper() == meeting_name.upper():
                    meeting_idx = i
                    break
            
            if not meeting_idx:
                print(f"[ResultsFetcher] Meeting {meeting_name} not found")
                return results
            
            # Find completed races
            completed_races = []
            i = meeting_idx + 2
            while i < min(meeting_idx + 50, len(lines)):
                line = lines[i]
                if line in ['VIC', 'NSW', 'QLD', 'SA', 'WA', 'TAS', 'NT', 'NZ', 'HK'] and i > meeting_idx + 3:
                    break
                
                m = re.match(r'^R(\d+)$', line)
                if m and i + 1 < len(lines):
                    race_num = int(m.group(1))
                    result_cell = lines[i + 1]
                    if re.match(r'^\d+[/\d]*,\s*\d+', result_cell):
                        completed_races.append((race_num, result_cell))
                i += 1
            
            print(f"[ResultsFetcher] Found {len(completed_races)} completed races")
            
            # Fetch each race details
            for race_num, result_cell in completed_races:
                try:
                    await page.goto('https://www.ladbrokes.com.au/racing/results', timeout=30000)
                    await asyncio.sleep(2)
                    
                    for _ in range(5):
                        await page.evaluate('window.scrollBy(0, 300)')
                        await asyncio.sleep(0.2)
                    
                    await page.click(f'text="{result_cell}"', timeout=5000)
                    await asyncio.sleep(3)
                    
                    text = await page.evaluate('document.body.innerText')
                    lines = [l.strip() for l in text.split('\n') if l.strip()]
                    
                    race_results = []
                    in_results = False
                    
                    for line in lines:
                        if line == 'RESULTS':
                            in_results = True
                            continue
                        if in_results and line in ['EXOTIC RESULTS', 'FINAL MARGINS']:
                            break
                        
                        if in_results and (re.match(r'^J\s+[A-Z]', line) or re.match(r'^J:\s*[A-Z]', line)):
                            jockey = re.sub(r'^J[:\s]+', '', line).strip()
                            jockey = re.sub(r'\s*\([^)]+\)$', '', jockey)
                            
                            if jockey and jockey not in [r['jockey'] for r in race_results]:
                                race_results.append({
                                    'position': len(race_results) + 1,
                                    'jockey': jockey,
                                    'name': jockey
                                })
                            
                            if len(race_results) >= 3:
                                break
                    
                    if race_results:
                        print(f"[ResultsFetcher] R{race_num}: {[r['jockey'] for r in race_results]}")
                        results.append({
                            'race_num': race_num,
                            'results': race_results
                        })
                        
                except Exception as e:
                    print(f"[ResultsFetcher] R{race_num} error: {e}")
                    
        except Exception as e:
            print(f"[ResultsFetcher] Error: {e}")
        
        finally:
            await browser.close()
    
    return results


def send_results_to_api(meeting_name: str, race_num: int, results: list):
    """Send results to production API"""
    try:
        payload = {
            'meeting': meeting_name.upper(),
            'race_num': race_num,
            'results': results
        }
        
        response = requests.post(
            f"{API_URL}/api/live-tracker/update/",
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"[API] ✅ {meeting_name} R{race_num} sent successfully")
            return data
        else:
            print(f"[API] ❌ {meeting_name} R{race_num} failed: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"[API] Error: {e}")
        return None


def get_active_meetings():
    """Get list of meetings being tracked"""
    try:
        response = requests.get(f"{API_URL}/api/live-tracker/", timeout=30)
        if response.status_code == 200:
            data = response.json()
            trackers = data.get('trackers', {})
            meetings = []
            for name, info in trackers.items():
                if info.get('races_completed', 0) < info.get('total_races', 8):
                    meetings.append({
                        'name': name,
                        'races_completed': info.get('races_completed', 0)
                    })
            return meetings
    except Exception as e:
        print(f"[API] Error getting meetings: {e}")
    return []


async def main():
    print(f"\n🏇 Results Fetcher Starting - {datetime.now().isoformat()}")
    
    # Get active meetings
    meetings = get_active_meetings()
    
    if not meetings:
        print("No active meetings to check")
        return
    
    print(f"Found {len(meetings)} active meetings: {[m['name'] for m in meetings]}")
    
    for meeting in meetings:
        meeting_name = meeting['name']
        last_race = meeting['races_completed']
        
        print(f"\n--- Checking {meeting_name} (last race: {last_race}) ---")
        
        results = await fetch_meeting_results(meeting_name)
        
        # Send new results to API
        for race_data in results:
            race_num = race_data['race_num']
            
            # Only send if new race
            if race_num > last_race:
                send_results_to_api(meeting_name, race_num, race_data['results'])
    
    print(f"\n✅ Results Fetcher Complete - {datetime.now().isoformat()}")


if __name__ == "__main__":
    asyncio.run(main())