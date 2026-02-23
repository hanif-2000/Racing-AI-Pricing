"""
RESULTS FETCHER - Runs in GitHub Actions
Fetches race results from Racing Australia (racingaustralia.horse)
Uses simple HTTP requests - no Playwright/browser needed.

Strategy:
1. Scrape all state calendars to discover today's venues + result URLs (8 requests)
2. Match active meetings to discovered venues using flexible name matching
3. Fetch results only for matched venues (N requests)
Total: ~8 + N requests = fast, under 1 minute
"""

import re
import requests
from datetime import datetime, timezone, timedelta

API_URL = "https://api.jockeydriverchallenge.com"
RA_BASE = "https://www.racingaustralia.horse"

STATES = ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT", "ACT"]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

# Common sponsor prefixes to strip for matching
SPONSOR_PREFIXES = [
    "picklebet park ", "picklebet ", "sportsbet-", "sportsbet ",
    "bet365 park ", "bet365 ", "ladbrokes ", "southside ",
    "tabtouch park ", "tabtouch ",
]


def get_australian_date():
    """Get current date in Australian Eastern time."""
    now_utc = datetime.now(timezone.utc)
    return now_utc + timedelta(hours=11)  # AEDT


def normalize_venue(name):
    """Normalize venue name by stripping sponsors and lowercasing."""
    n = name.lower().strip()
    # Strip sponsor prefixes
    for prefix in SPONSOR_PREFIXES:
        if n.startswith(prefix):
            n = n[len(prefix):]
            break
    # Strip state suffix
    n = re.sub(r'\s+(nsw|vic|qld|sa|wa|tas|nt|act)\s*$', '', n)
    # Strip race type suffix
    n = re.sub(r'\s*-\s*(professional|trial|picnic|jumpout).*$', '', n)
    # Strip "scarpside", "hillside", "heath", "park" suffixes for broader matching
    n = re.sub(r'\s+(scarpside|hillside|heath)$', '', n)
    return re.sub(r'[^a-z]', '', n)


def discover_todays_venues():
    """Scrape all state calendar pages to discover today's venues with result URLs.
    Returns list of {name, state, url, normalized}.
    """
    aus_now = get_australian_date()
    date_key = aus_now.strftime('%Y%b%d')  # e.g. "2026Feb23"
    venues = []

    for state in STATES:
        try:
            url = f"{RA_BASE}/FreeFields/Calendar_Results.aspx?State={state}"
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                continue

            html = resp.text

            # Find all result links for today's date key
            # Matches: href="/FreeFields/Results.aspx?Key=2026Feb23,QLD,Picklebet Park Warwick"
            # or with race type: Key=2026Feb23,VIC,Sportsbet-Ballarat,Trial
            pattern = rf'Results\.aspx\?Key={re.escape(date_key)},{re.escape(state)},([^"&]+)'
            matches = re.findall(pattern, html)

            seen_urls = set()
            for raw_venue in matches:
                # Decode URL encoding
                venue_with_type = raw_venue.replace('%20', ' ').strip()

                # Skip trials and jump outs
                if ',Trial' in venue_with_type or ',JumpOut' in venue_with_type:
                    continue

                # Remove optional race type suffix from the key
                venue_name = re.sub(r',(?:Professional|Picnic)$', '', venue_with_type)

                result_url = f"{RA_BASE}/FreeFields/Results.aspx?Key={date_key},{state},{venue_with_type}"

                if result_url not in seen_urls:
                    seen_urls.add(result_url)
                    venues.append({
                        'name': venue_name,
                        'state': state,
                        'url': result_url,
                        'normalized': normalize_venue(venue_name),
                    })

        except Exception as e:
            print(f"  [Calendar] Error fetching {state}: {e}")

    return venues


def match_meeting_to_venue(meeting_name, venues):
    """Match API meeting name to a discovered RA venue."""
    api_norm = normalize_venue(meeting_name)

    # Pass 1: Exact normalized match
    for v in venues:
        if v['normalized'] == api_norm:
            return v

    # Pass 2: One contains the other
    for v in venues:
        if api_norm in v['normalized'] or v['normalized'] in api_norm:
            if len(api_norm) >= 3 and len(v['normalized']) >= 3:
                return v

    # Pass 3: All significant words match
    api_words = set(api_norm)  # Already stripped, this is character set - not useful
    # Better: use word-level matching
    api_words = set(re.sub(r'[^a-z\s]', '', meeting_name.lower()).split())
    filler = {'park', 'the', 'and', 'of'}
    api_words -= filler
    for v in venues:
        v_words = set(re.sub(r'[^a-z\s]', '', v['name'].lower()).split())
        v_words -= filler
        if api_words and v_words and (api_words.issubset(v_words) or v_words.issubset(api_words)):
            return v

    return None


def count_total_races(html):
    """Count actual number of races from HTML."""
    race_nums = re.findall(r'<a\s+name="Race(\d+)"', html)
    return max(int(n) for n in race_nums) if race_nums else 0


def fetch_race_results(result_url, meeting_name):
    """Fetch and parse results from a RA results page."""
    results = []

    try:
        resp = requests.get(result_url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return results, 0

        html = resp.text

        if 'Results for this meeting are not currently available' in html:
            return results, 0

        total_races = count_total_races(html)
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
            pattern = r'(?:JockeyLastRuns|DriverLastStarts)\.aspx\?\w+=[^"]*"[^>]*>\s*([^<]+?)\s*</a>'
            names = re.findall(pattern, section)

            race_results = []
            seen = set()
            for raw in names:
                name = re.sub(r'\s*\([^)]*\)\s*$', '', raw).strip()
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
                results.append({'race_num': race_num, 'results': race_results})
                pos = ', '.join(f"{r['position']}. {r['jockey']}" for r in race_results)
                print(f"  R{race_num}: {pos}")

    except Exception as e:
        print(f"  Error: {e}")
        return results, 0

    return results, total_races


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
            print(f"  [API] Sent R{race_num}")
            return response.json()
        else:
            print(f"  [API] Failed R{race_num}: {response.status_code}")
            return None

    except Exception as e:
        print(f"  [API] Error: {e}")
        return None


def get_active_meetings():
    """Get meetings being tracked from API."""
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
        print(f"[API] Error: {e}")
    return []


def main():
    aus_now = get_australian_date()

    print(f"\n{'='*60}")
    print(f"Results Fetcher")
    print(f"UTC:  {datetime.now(timezone.utc).isoformat()}")
    print(f"AEDT: {aus_now.isoformat()}")
    print(f"{'='*60}")

    # Step 1: Get active meetings
    meetings = get_active_meetings()
    if not meetings:
        print("No active meetings")
        return

    jockey_meetings = [m for m in meetings if m['type'] == 'jockey']
    driver_meetings = [m for m in meetings if m['type'] == 'driver']

    print(f"\nActive: {len(jockey_meetings)} jockey, {len(driver_meetings)} driver")
    for m in meetings:
        print(f"  - {m['name']} [{m['type']}] ({m['races_completed']}/{m['total_races']})")

    if driver_meetings:
        print(f"\n  Note: {len(driver_meetings)} harness meetings skipped (RA = thoroughbred only)")

    if not jockey_meetings:
        print("No jockey meetings to process")
        return

    # Step 2: Discover today's venues from RA calendars (8 requests)
    print(f"\nDiscovering today's venues from Racing Australia...")
    venues = discover_todays_venues()
    print(f"Found {len(venues)} venues:")
    for v in venues:
        print(f"  - {v['name']} ({v['state']}) [{v['normalized']}]")

    if not venues:
        print("No venues found on RA for today")
        return

    # Step 3: Match and fetch
    print(f"\n{'='*60}")
    print("Matching & fetching results...")
    print(f"{'='*60}")

    total_sent = 0

    for meeting in jockey_meetings:
        name = meeting['name']
        last_race = meeting['races_completed']
        tracker_total = meeting['total_races']

        print(f"\n--- {name} ({last_race}/{tracker_total}) ---")

        matched = match_meeting_to_venue(name, venues)
        if not matched:
            print(f"  No match (norm: '{normalize_venue(name)}')")
            continue

        print(f"  Matched: {matched['name']} ({matched['state']})")

        results, actual_total = fetch_race_results(matched['url'], name)
        if not results:
            print(f"  No results yet")
            continue

        actual_total_to_send = None
        if actual_total > 0 and actual_total != tracker_total:
            print(f"  Races: tracker={tracker_total}, actual={actual_total}")
            actual_total_to_send = actual_total

        for rd in results:
            rn = rd['race_num']
            if rn > last_race:
                res = send_results_to_api(name, rn, rd['results'], actual_total_to_send)
                if res:
                    total_sent += 1
                    actual_total_to_send = None

    print(f"\n{'='*60}")
    print(f"Done! Sent {total_sent} new results")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
