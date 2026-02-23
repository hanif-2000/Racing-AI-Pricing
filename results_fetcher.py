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


def normalize_name(name):
    """Normalize meeting name for comparison"""
    return re.sub(r'[^a-z]', '', name.lower())


def find_meeting_in_lines(lines, meeting_name):
    """Find meeting index using flexible matching"""
    target = normalize_name(meeting_name)

    # Pass 1: Exact match (case-insensitive)
    for i, line in enumerate(lines):
        if line.upper().strip() == meeting_name.upper().strip():
            return i

    # Pass 2: Normalized match (ignore spaces, hyphens, etc)
    for i, line in enumerate(lines):
        if normalize_name(line) == target:
            return i

    # Pass 3: Line contains meeting name or vice versa
    for i, line in enumerate(lines):
        line_upper = line.upper().strip()
        name_upper = meeting_name.upper().strip()
        if name_upper in line_upper or line_upper in name_upper:
            # Skip very short lines that might false-match
            if len(line.strip()) >= 3:
                return i

    # Pass 4: Check if meeting name words appear together
    words = meeting_name.upper().split()
    if len(words) >= 1:
        for i, line in enumerate(lines):
            line_upper = line.upper()
            if all(w in line_upper for w in words):
                if len(line.strip()) >= 3:
                    return i

    return None


async def fetch_meeting_results(meeting_name: str):
    """Fetch results for a meeting from Ladbrokes"""
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = await context.new_page()

        try:
            print(f"[ResultsFetcher] Checking {meeting_name}...")

            # Try the results page
            await page.goto('https://www.ladbrokes.com.au/racing/results', timeout=60000)
            await asyncio.sleep(5)

            # Scroll more aggressively to load all content
            for _ in range(15):
                await page.evaluate('window.scrollBy(0, 500)')
                await asyncio.sleep(0.3)

            # Scroll back to top
            await page.evaluate('window.scrollTo(0, 0)')
            await asyncio.sleep(1)

            text = await page.evaluate('document.body.innerText')
            lines = [l.strip() for l in text.split('\n') if l.strip()]

            # Debug: Print potential meeting names (lines that look like venue names)
            potential_meetings = []
            for line in lines:
                # Meeting names are typically capitalized words, no numbers
                if (re.match(r'^[A-Z][a-zA-Z\s\-\.]+$', line.strip()) and
                    len(line.strip()) >= 3 and
                    line.strip() not in ['Racing', 'Results', 'Home', 'Sports', 'Live Betting',
                                         'Promotions', 'Login', 'Join', 'Help', 'Thoroughbred',
                                         'Harness', 'Greyhound', 'Next To Jump', 'RESULTS',
                                         'Upcoming', 'Completed', 'All', 'Today', 'Yesterday']):
                    potential_meetings.append(line.strip())

            if potential_meetings:
                print(f"[ResultsFetcher] Meetings on page: {potential_meetings[:20]}")
            else:
                # Debug: print some lines to understand page structure
                print(f"[ResultsFetcher] DEBUG - First 40 lines of page:")
                for idx, line in enumerate(lines[:40]):
                    print(f"  [{idx}] {line[:100]}")

            # Find meeting using flexible matching
            meeting_idx = find_meeting_in_lines(lines, meeting_name)

            if meeting_idx is None:
                print(f"[ResultsFetcher] Meeting {meeting_name} not found on results page")

                # Try alternative: direct race result URL
                alt_results = await try_direct_race_urls(page, meeting_name)
                if alt_results:
                    return alt_results

                return results

            print(f"[ResultsFetcher] Found {meeting_name} at line {meeting_idx}: '{lines[meeting_idx]}'")

            # Find completed races - search more broadly
            completed_races = []
            i = meeting_idx + 1
            state_names = ['VIC', 'NSW', 'QLD', 'SA', 'WA', 'TAS', 'NT', 'NZ', 'HK',
                          'Victoria', 'New South Wales', 'Queensland', 'South Australia',
                          'Western Australia', 'Tasmania', 'Northern Territory', 'New Zealand']

            while i < min(meeting_idx + 60, len(lines)):
                line = lines[i]

                # Stop if we hit another state/section
                if line.strip() in state_names and i > meeting_idx + 3:
                    break

                # Stop if we hit another meeting name (all caps, no numbers)
                if (i > meeting_idx + 3 and
                    re.match(r'^[A-Z][a-zA-Z\s\-]+$', line.strip()) and
                    len(line.strip()) >= 4 and
                    not re.match(r'^R\d', line)):
                    # Check if this looks like another meeting
                    if any(normalize_name(line) == normalize_name(pm) for pm in potential_meetings if pm != lines[meeting_idx]):
                        break

                # Match race numbers in various formats
                m = re.match(r'^R(\d+)$', line) or re.match(r'^Race\s+(\d+)$', line, re.I)
                if m and i + 1 < len(lines):
                    race_num = int(m.group(1))
                    result_cell = lines[i + 1]
                    # Check if next line looks like results (numbers with commas/slashes)
                    if re.match(r'^\d+[/\d]*[\s,]+\d+', result_cell) or 'Paid' in result_cell:
                        completed_races.append((race_num, result_cell, i))

                i += 1

            print(f"[ResultsFetcher] Found {len(completed_races)} completed races for {meeting_name}")

            # Fetch each race details
            for race_num, result_cell, line_idx in completed_races:
                try:
                    # Try clicking on the race result
                    await page.goto('https://www.ladbrokes.com.au/racing/results', timeout=30000)
                    await asyncio.sleep(3)

                    for _ in range(10):
                        await page.evaluate('window.scrollBy(0, 400)')
                        await asyncio.sleep(0.2)

                    # Try multiple click strategies
                    clicked = False
                    try:
                        await page.click(f'text="{result_cell}"', timeout=5000)
                        clicked = True
                    except Exception:
                        pass

                    if not clicked:
                        try:
                            # Try clicking the race number near the meeting
                            race_links = await page.query_selector_all(f'text=/R{race_num}/')
                            for link in race_links:
                                try:
                                    await link.click(timeout=3000)
                                    clicked = True
                                    break
                                except Exception:
                                    continue
                        except Exception:
                            pass

                    if not clicked:
                        print(f"[ResultsFetcher] Could not click R{race_num} for {meeting_name}")
                        continue

                    await asyncio.sleep(3)

                    text = await page.evaluate('document.body.innerText')
                    detail_lines = [l.strip() for l in text.split('\n') if l.strip()]

                    race_results = extract_jockey_results(detail_lines)

                    if race_results:
                        print(f"[ResultsFetcher] R{race_num}: {[r['jockey'] for r in race_results]}")
                        results.append({
                            'race_num': race_num,
                            'results': race_results
                        })
                    else:
                        print(f"[ResultsFetcher] R{race_num}: No jockey results found")

                except Exception as e:
                    print(f"[ResultsFetcher] R{race_num} error: {e}")

        except Exception as e:
            print(f"[ResultsFetcher] Error: {e}")

        finally:
            await browser.close()

    return results


def extract_jockey_results(lines):
    """Extract jockey names from race result page with multiple patterns"""
    race_results = []
    in_results = False

    for i, line in enumerate(lines):
        # Look for results section markers
        if line in ['RESULTS', 'Results', 'Result']:
            in_results = True
            continue
        if in_results and line in ['EXOTIC RESULTS', 'FINAL MARGINS', 'Exotic Results',
                                     'Final Margins', 'Dividends', 'DIVIDENDS']:
            break

        if in_results:
            # Pattern 1: "J Name" or "J: Name"
            if re.match(r'^J[:\s]+[A-Z]', line):
                jockey = re.sub(r'^J[:\s]+', '', line).strip()
                jockey = re.sub(r'\s*\([^)]+\)$', '', jockey)
                if jockey and jockey not in [r['jockey'] for r in race_results]:
                    race_results.append({
                        'position': len(race_results) + 1,
                        'jockey': jockey,
                        'name': jockey
                    })

            # Pattern 2: "Jockey: Name"
            elif re.match(r'^Jockey[:\s]+', line, re.I):
                jockey = re.sub(r'^Jockey[:\s]+', '', line, flags=re.I).strip()
                jockey = re.sub(r'\s*\([^)]+\)$', '', jockey)
                if jockey and jockey not in [r['jockey'] for r in race_results]:
                    race_results.append({
                        'position': len(race_results) + 1,
                        'jockey': jockey,
                        'name': jockey
                    })

            # Pattern 3: Position number followed by horse/jockey info
            # e.g., "1st", "2nd", "3rd" on their own line
            elif re.match(r'^(1st|2nd|3rd|1ST|2ND|3RD)$', line):
                # Look ahead for jockey info
                for j in range(i+1, min(i+5, len(lines))):
                    if re.match(r'^J[:\s]+[A-Z]', lines[j]):
                        jockey = re.sub(r'^J[:\s]+', '', lines[j]).strip()
                        jockey = re.sub(r'\s*\([^)]+\)$', '', jockey)
                        if jockey and jockey not in [r['jockey'] for r in race_results]:
                            race_results.append({
                                'position': len(race_results) + 1,
                                'jockey': jockey,
                                'name': jockey
                            })
                        break

        if len(race_results) >= 3:
            break

    return race_results


async def try_direct_race_urls(page, meeting_name):
    """Try accessing race results via direct URL patterns"""
    results = []

    # Convert meeting name to URL slug
    slug = meeting_name.lower().replace(' ', '-')

    # Try Ladbrokes race result URL patterns
    today = datetime.now().strftime('%Y-%m-%d')

    for race_num in range(1, 9):
        try:
            url = f'https://www.ladbrokes.com.au/racing/thoroughbred/{slug}/race-{race_num}'
            print(f"[ResultsFetcher] Trying direct URL: {url}")

            response = await page.goto(url, timeout=15000)
            if response and response.status == 200:
                await asyncio.sleep(2)

                text = await page.evaluate('document.body.innerText')

                # Check if this race has results
                if 'RESULTS' in text.upper() or 'Result' in text:
                    lines = [l.strip() for l in text.split('\n') if l.strip()]
                    race_results = extract_jockey_results(lines)

                    if race_results:
                        print(f"[ResultsFetcher] Direct URL R{race_num}: {[r['jockey'] for r in race_results]}")
                        results.append({
                            'race_num': race_num,
                            'results': race_results
                        })
                else:
                    # Race hasn't completed yet or no results
                    break
            else:
                break

        except Exception as e:
            print(f"[ResultsFetcher] Direct URL R{race_num} error: {e}")
            continue

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
            print(f"[API] ❌ {meeting_name} R{race_num} failed: {response.status_code} - {response.text[:200]}")
            return None

    except Exception as e:
        print(f"[API] Error: {e}")
        return None


def get_active_meetings():
    """Get list of meetings being tracked"""
    try:
        response = requests.get(f"{API_URL}/api/live-tracker/", timeout=60)
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
        sent_count = 0
        for race_data in results:
            race_num = race_data['race_num']

            # Only send if new race
            if race_num > last_race:
                result = send_results_to_api(meeting_name, race_num, race_data['results'])
                if result:
                    sent_count += 1

        if sent_count > 0:
            print(f"[ResultsFetcher] Sent {sent_count} new results for {meeting_name}")

    print(f"\n✅ Results Fetcher Complete - {datetime.now().isoformat()}")


if __name__ == "__main__":
    asyncio.run(main())
