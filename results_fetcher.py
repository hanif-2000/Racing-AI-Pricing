"""
RESULTS FETCHER - Runs in GitHub Actions
Fetches race results from Racing Australia (racingaustralia.horse)
Uses simple HTTP requests - no Playwright/browser needed.
Uses direct URL construction with sponsored venue name fallbacks.
"""

import re
import requests
from datetime import datetime, timezone, timedelta

API_URL = "https://api.jockeydriverchallenge.com"
RA_BASE = "https://www.racingaustralia.horse"

STATES = ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT", "ACT"]

# Common sponsor prefixes used on Racing Australia venue names
SPONSOR_PREFIXES = [
    "Picklebet Park ",
    "Sportsbet-",
    "Sportsbet ",
    "bet365 ",
    "bet365 Park ",
    "Ladbrokes ",
    "Southside ",
    "Picklebet ",
    "TABtouch ",
    "TABtouch Park ",
    "Caulfield Heath",  # special case: Caulfield Heath = Caulfield
]

# Known venue name mappings (API name -> RA venue names to try)
VENUE_ALIASES = {
    "SANDOWN": ["Sportsbet Sandown Hillside", "Sandown", "Sandown Hillside"],
    "PAKENHAM": ["Southside Pakenham", "Pakenham"],
    "CRANBOURNE": ["Southside Cranbourne", "Cranbourne"],
    "MOONEE VALLEY": ["bet365 Moonee Valley", "Moonee Valley"],
    "GEELONG": ["Ladbrokes Geelong", "Geelong"],
    "WERRIBEE": ["Picklebet Park Werribee", "Werribee"],
    "BALLARAT": ["Sportsbet-Ballarat", "Ballarat"],
    "PINJARRA": ["Pinjarra Scarpside", "Pinjarra"],
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}


def get_australian_date():
    """Get current date in Australian Eastern time."""
    now_utc = datetime.now(timezone.utc)
    return now_utc + timedelta(hours=11)  # AEDT


def to_title_case(name):
    """Convert API meeting name to title case for RA URL."""
    return ' '.join(word.capitalize() for word in name.split())


def get_venue_names_to_try(meeting_name):
    """Generate list of venue name variations to try on RA.

    For WARWICK, tries: Warwick, Picklebet Park Warwick, Sportsbet-Warwick, etc.
    """
    base = to_title_case(meeting_name)
    names = [base]

    # Check known aliases first
    if meeting_name.upper() in VENUE_ALIASES:
        names = VENUE_ALIASES[meeting_name.upper()] + names

    # Add sponsor prefix variations
    for prefix in SPONSOR_PREFIXES:
        sponsored = f"{prefix}{base}"
        if sponsored not in names:
            names.append(sponsored)

    return names


def try_results_url(venue_name, date_key, state):
    """Try to fetch results from a directly constructed URL."""
    url = f"{RA_BASE}/FreeFields/Results.aspx?Key={date_key},{state},{venue_name}"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            return None, url

        html = resp.text

        if 'Results for this meeting are not currently available' in html:
            return None, url

        if '<a name="Race1"' not in html and 'Race 1' not in html:
            return None, url

        return html, url

    except Exception:
        return None, url


def count_total_races(html):
    """Count the actual number of races in the meeting from HTML."""
    race_nums = re.findall(r'<a\s+name="Race(\d+)"', html)
    if race_nums:
        return max(int(n) for n in race_nums)
    return 0


def fetch_race_results_from_html(html, meeting_name):
    """Parse jockey results from Racing Australia results HTML."""
    results = []

    race_sections = re.split(r'<a\s+name="Race(\d+)"', html)

    for i in range(1, len(race_sections), 2):
        race_num = int(race_sections[i])
        if i + 1 >= len(race_sections):
            break

        section = race_sections[i + 1]

        for marker in ['<a name="Race', 'id="ExoticDiv']:
            idx = section.find(marker)
            if idx > 0:
                section = section[:idx]

        # Extract jockey/driver names from profile links
        jockey_pattern = r'(?:JockeyLastRuns|DriverLastStarts)\.aspx\?\w+=[^"]*"[^>]*>\s*([^<]+?)\s*</a>'
        jockey_matches = re.findall(jockey_pattern, section)

        race_results = []
        seen = set()

        for raw_name in jockey_matches:
            name = re.sub(r'\s*\([^)]*\)\s*$', '', raw_name).strip()

            if name and name not in seen:
                seen.add(name)
                race_results.append({
                    'position': len(race_results) + 1,
                    'jockey': name,
                    'name': name
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


def find_meeting_results(meeting_name, meeting_type):
    """Try to find results for a meeting by constructing direct URLs."""
    if meeting_type == 'driver':
        print(f"  Skipping harness meeting (not on Racing Australia)")
        return [], None, 0

    aus_now = get_australian_date()
    date_key = aus_now.strftime('%Y%b%d')

    venue_names = get_venue_names_to_try(meeting_name)
    print(f"  Date: {date_key}, trying {len(venue_names)} name variations")

    # Try today with all name variations across all states
    for venue in venue_names:
        for state in STATES:
            html, url = try_results_url(venue, date_key, state)
            if html:
                total = count_total_races(html)
                print(f"  Found: {venue} ({state}) - {total} races")
                results = fetch_race_results_from_html(html, meeting_name)
                return results, url, total

    # Try yesterday
    yesterday = aus_now - timedelta(days=1)
    date_key_y = yesterday.strftime('%Y%b%d')
    print(f"  Not found today, trying yesterday ({date_key_y})...")

    for venue in venue_names:
        for state in STATES:
            html, url = try_results_url(venue, date_key_y, state)
            if html:
                total = count_total_races(html)
                print(f"  Found (yesterday): {venue} ({state}) - {total} races")
                results = fetch_race_results_from_html(html, meeting_name)
                return results, url, total

    print(f"  Not found on Racing Australia")
    return [], None, 0


def send_results_to_api(meeting_name, race_num, results, actual_total_races=None):
    """Send results to production API."""
    try:
        payload = {
            'meeting': meeting_name.upper(),
            'race_num': race_num,
            'results': results
        }
        if actual_total_races:
            payload['actual_total_races'] = actual_total_races

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
                        'type': info.get('type', 'jockey'),
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

    meetings = get_active_meetings()
    if not meetings:
        print("No active meetings to check")
        return

    print(f"\nActive meetings ({len(meetings)}):")
    for m in meetings:
        print(f"  - {m['name']} [{m['type']}] ({m['races_completed']}/{m['total_races']})")

    print(f"\n{'='*60}")
    print("Fetching results...")
    print(f"{'='*60}")

    total_sent = 0

    for meeting in meetings:
        meeting_name = meeting['name']
        meeting_type = meeting['type']
        last_race = meeting['races_completed']
        tracker_total = meeting['total_races']

        print(f"\n--- {meeting_name} [{meeting_type}] ({last_race}/{tracker_total}) ---")

        results, url, actual_total = find_meeting_results(meeting_name, meeting_type)

        if not results:
            continue

        # Determine actual total races
        actual_total_to_send = None
        if actual_total > 0 and actual_total != tracker_total:
            print(f"  Total races mismatch: tracker={tracker_total}, actual={actual_total}")
            actual_total_to_send = actual_total

        print(f"  Found {len(results)} races with results")

        for race_data in results:
            race_num = race_data['race_num']

            if race_num > last_race:
                result = send_results_to_api(
                    meeting_name, race_num, race_data['results'],
                    actual_total_races=actual_total_to_send
                )
                if result:
                    total_sent += 1
                    # Only send actual_total once
                    actual_total_to_send = None

    print(f"\n{'='*60}")
    print(f"Done! Sent {total_sent} new race results")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
