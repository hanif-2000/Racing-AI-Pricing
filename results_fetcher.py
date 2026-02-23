"""
RESULTS FETCHER - Runs in GitHub Actions
Fetches race results from Racing Australia (racingaustralia.horse)
Uses simple HTTP requests - no Playwright/browser needed.
Uses direct URL construction - no calendar scraping needed.
"""

import re
import requests
from datetime import datetime, timezone, timedelta

API_URL = "https://api.jockeydriverchallenge.com"
RA_BASE = "https://www.racingaustralia.horse"

# Australian Eastern timezone (UTC+11 AEDT / UTC+10 AEST)
AEST = timezone(timedelta(hours=10))
AEDT = timezone(timedelta(hours=11))

STATES = ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT", "ACT"]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}


def get_australian_date():
    """Get current date in Australian Eastern time."""
    now_utc = datetime.now(timezone.utc)
    now_aest = now_utc + timedelta(hours=11)  # AEDT
    return now_aest


def to_title_case(name):
    """Convert API meeting name to title case for RA URL.
    PORT MACQUARIE -> Port Macquarie
    EAGLE FARM -> Eagle Farm
    """
    return ' '.join(word.capitalize() for word in name.split())


def try_results_url(meeting_name, date_key, state):
    """Try to fetch results from a directly constructed URL."""
    venue = to_title_case(meeting_name)
    url = f"{RA_BASE}/FreeFields/Results.aspx?Key={date_key},{state},{venue}"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            return None, url

        html = resp.text

        # Check if the page has actual race results (not "Results not available")
        if 'Results for this meeting are not currently available' in html:
            return None, url

        # Check if there are any race anchors
        if '<a name="Race1"' not in html and 'Race 1' not in html:
            return None, url

        return html, url

    except Exception:
        return None, url


def fetch_race_results_from_html(html, meeting_name):
    """Parse jockey results from Racing Australia results HTML."""
    results = []

    # Find all race sections - they start with <a name="Race1">
    race_sections = re.split(r'<a\s+name="Race(\d+)"', html)

    # race_sections[0] is before first race, then alternating: race_num, content
    for i in range(1, len(race_sections), 2):
        race_num = int(race_sections[i])
        if i + 1 >= len(race_sections):
            break

        section = race_sections[i + 1]

        # Limit section to just this race
        for marker in ['<a name="Race', 'id="ExoticDiv']:
            idx = section.find(marker)
            if idx > 0:
                section = section[:idx]

        # Extract jockey names from jockey profile links
        jockey_pattern = r'JockeyLastRuns\.aspx\?jockeycode=[^"]*"[^>]*>\s*([^<]+?)\s*</a>'
        jockey_matches = re.findall(jockey_pattern, section)

        race_results = []
        seen_jockeys = set()

        for jockey_raw in jockey_matches:
            # Clean jockey name - remove weight/claim info like "(a1.5/51kg)"
            jockey = re.sub(r'\s*\([^)]*\)\s*$', '', jockey_raw).strip()

            if jockey and jockey not in seen_jockeys:
                seen_jockeys.add(jockey)
                race_results.append({
                    'position': len(race_results) + 1,
                    'jockey': jockey,
                    'name': jockey
                })

            if len(race_results) >= 3:
                break

        if race_results:
            results.append({
                'race_num': race_num,
                'results': race_results
            })
            positions = ', '.join(f"{r['position']}. {r['jockey']}" for r in race_results)
            print(f"  R{race_num}: {positions}")

    return results


def find_meeting_results(meeting_name):
    """Try to find results for a meeting by constructing direct URLs.
    Tries all Australian states with today's date.
    """
    aus_now = get_australian_date()
    date_key = aus_now.strftime('%Y%b%d')  # e.g. "2026Feb23"

    print(f"  Trying date key: {date_key}")

    # Try each state
    for state in STATES:
        html, url = try_results_url(meeting_name, date_key, state)
        if html:
            print(f"  Found on RA: {state} - {url}")
            return fetch_race_results_from_html(html, meeting_name), url

    # Also try yesterday (in case meeting was yesterday but still active in tracker)
    yesterday = aus_now - timedelta(days=1)
    date_key_yesterday = yesterday.strftime('%Y%b%d')
    print(f"  Not found for today, trying yesterday: {date_key_yesterday}")

    for state in STATES:
        html, url = try_results_url(meeting_name, date_key_yesterday, state)
        if html:
            print(f"  Found on RA (yesterday): {state} - {url}")
            return fetch_race_results_from_html(html, meeting_name), url

    print(f"  Not found on Racing Australia for any state")
    return [], None


def send_results_to_api(meeting_name, race_num, results):
    """Send results to production API."""
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
            print(f"  [API] Sent R{race_num} for {meeting_name}")
            return response.json()
        else:
            print(f"  [API] Failed R{race_num}: {response.status_code} - {response.text[:200]}")
            return None

    except Exception as e:
        print(f"  [API] Error: {e}")
        return None


def get_active_meetings():
    """Get list of meetings being tracked from API."""
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
                        'races_completed': info.get('races_completed', 0),
                        'total_races': info.get('total_races', 8)
                    })
            return meetings
    except Exception as e:
        print(f"[API] Error getting meetings: {e}")
    return []


def main():
    aus_now = get_australian_date()

    print(f"\n{'='*60}")
    print(f"Results Fetcher")
    print(f"UTC:  {datetime.now(timezone.utc).isoformat()}")
    print(f"AEDT: {aus_now.isoformat()}")
    print(f"{'='*60}")

    # Step 1: Get active meetings from API
    meetings = get_active_meetings()
    if not meetings:
        print("No active meetings to check")
        return

    print(f"\nActive meetings ({len(meetings)}):")
    for m in meetings:
        print(f"  - {m['name']} ({m['races_completed']}/{m['total_races']} completed)")

    # Step 2: For each meeting, try direct URL to Racing Australia
    print(f"\n{'='*60}")
    print("Fetching results from Racing Australia...")
    print(f"{'='*60}")

    total_sent = 0

    for meeting in meetings:
        meeting_name = meeting['name']
        last_race = meeting['races_completed']

        print(f"\n--- {meeting_name} (completed: {last_race}) ---")

        results, url = find_meeting_results(meeting_name)

        if not results:
            print(f"  No results available")
            continue

        print(f"  Found {len(results)} races with results")

        # Send new results to API
        for race_data in results:
            race_num = race_data['race_num']

            if race_num > last_race:
                result = send_results_to_api(meeting_name, race_num, race_data['results'])
                if result:
                    total_sent += 1

    print(f"\n{'='*60}")
    print(f"Done! Sent {total_sent} new race results to API")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
