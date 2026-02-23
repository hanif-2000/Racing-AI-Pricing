"""
RESULTS FETCHER - Runs in GitHub Actions
Fetches race results from Racing Australia (racingaustralia.horse)
Uses simple HTTP requests - no Playwright/browser needed.
"""

import re
import requests
from datetime import datetime

API_URL = "https://api.jockeydriverchallenge.com"
RA_BASE = "https://www.racingaustralia.horse"

STATES = ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT", "ACT"]


def normalize_name(name):
    """Normalize meeting name for comparison - strip sponsors, lowercase, alpha only"""
    # Remove common sponsor prefixes
    cleaned = re.sub(
        r'^(bet365|sportsbet|ladbrokes|picklebet|tab)\s*[-\s]*',
        '', name, flags=re.I
    )
    # Remove state suffixes like "NSW", "VIC" etc
    cleaned = re.sub(r'\s+(NSW|VIC|QLD|SA|WA|TAS|NT|ACT|NZ)\s*$', '', cleaned, flags=re.I)
    # Remove race type suffixes
    cleaned = re.sub(r'\s*[-–]\s*(Professional|Trial|Picnic|JumpOut)\s*(\(.*\))?\s*$', '', cleaned, flags=re.I)
    # Alpha only, lowercase
    return re.sub(r'[^a-z]', '', cleaned.lower())


def match_meeting_name(api_name, ra_venues):
    """Match API meeting name to Racing Australia venue name.

    API names are like: PORT MACQUARIE, EAGLE FARM, CAULFIELD
    RA names are like: Port Macquarie NSW - Professional, Caulfield VIC - Professional

    Returns the matching RA venue dict or None.
    """
    api_norm = normalize_name(api_name)

    # Pass 1: Exact normalized match
    for venue in ra_venues:
        if normalize_name(venue['name']) == api_norm:
            return venue

    # Pass 2: One contains the other
    for venue in ra_venues:
        ra_norm = normalize_name(venue['name'])
        if api_norm in ra_norm or ra_norm in api_norm:
            if len(api_norm) >= 3 and len(ra_norm) >= 3:
                return venue

    # Pass 3: All words of shorter name found in longer name
    api_words = set(re.sub(r'[^a-z\s]', '', api_name.lower()).split())
    for venue in ra_venues:
        ra_words = set(re.sub(r'[^a-z\s]', '', venue['name'].lower()).split())
        # Remove common filler words
        filler = {'park', 'the', 'and', 'of', 'nsw', 'vic', 'qld', 'sa', 'wa', 'tas', 'nt', 'act'}
        api_meaningful = api_words - filler
        ra_meaningful = ra_words - filler
        if api_meaningful and ra_meaningful:
            if api_meaningful.issubset(ra_meaningful) or ra_meaningful.issubset(api_meaningful):
                return venue

    return None


def get_todays_meetings():
    """Scrape Racing Australia calendar to get today's meetings with result URLs."""
    today = datetime.now()
    today_str = today.strftime('%a %d-%b')  # e.g. "Mon 23-Feb"
    today_key = today.strftime('%Y%b%d')  # e.g. "2026Feb23"

    all_venues = []

    for state in STATES:
        try:
            url = f"{RA_BASE}/FreeFields/Calendar_Results.aspx?State={state}"
            resp = requests.get(url, timeout=30)
            if resp.status_code != 200:
                print(f"[RA] Failed to fetch {state} calendar: {resp.status_code}")
                continue

            html = resp.text

            # Find all result links for today
            # Pattern: href="/FreeFields/Results.aspx?Key=2026Feb23,NSW,VenueName"
            pattern = rf'href="(/FreeFields/Results\.aspx\?Key={today_key},{state},[^"]+)"[^>]*>([^<]+)</a>'
            matches = re.findall(pattern, html)

            for href, link_text in matches:
                # Skip "Available Now" type links - we want venue name links
                if 'Available' in link_text or 'interim' in link_text:
                    continue

                # Extract venue name from the key parameter
                key_match = re.search(r'Key=[^,]+,[^,]+,(.+?)(?:,(?:Trial|Professional|Picnic|JumpOut))?$', href)
                if key_match:
                    venue_name = key_match.group(1).replace('%20', ' ')
                else:
                    venue_name = link_text.strip()

                # Skip trials and jump outs - we want professional races
                if ',Trial' in href or ',JumpOut' in href:
                    continue

                result_url = f"{RA_BASE}{href}"

                # Avoid duplicates
                if not any(v['url'] == result_url for v in all_venues):
                    all_venues.append({
                        'name': venue_name,
                        'state': state,
                        'url': result_url,
                        'link_text': link_text.strip()
                    })

        except Exception as e:
            print(f"[RA] Error fetching {state}: {e}")

    return all_venues


def fetch_race_results(result_url, meeting_name):
    """Fetch results for a meeting from Racing Australia."""
    results = []

    try:
        resp = requests.get(result_url, timeout=30)
        if resp.status_code != 200:
            print(f"[RA] Failed to fetch results for {meeting_name}: {resp.status_code}")
            return results

        html = resp.text

        # Find all race sections - they start with <a name="Race1">
        race_sections = re.split(r'<a\s+name="Race(\d+)"', html)

        # race_sections[0] is before first race, then alternating: race_num, content
        for i in range(1, len(race_sections), 2):
            race_num = int(race_sections[i])
            if i + 1 >= len(race_sections):
                break

            section = race_sections[i + 1]

            # Limit section to just this race (stop at next race or end markers)
            end_markers = ['<a name="Race', 'id="ExoticDiv']
            for marker in end_markers:
                idx = section.find(marker)
                if idx > 0:
                    section = section[:idx]

            # Extract results - find jockey links in order of appearance
            # Pattern: JockeyLastRuns.aspx?jockeycode=...">Jockey Name (weight)</a>
            jockey_pattern = r'JockeyLastRuns\.aspx\?jockeycode=[^"]*"[^>]*>\s*([^<]+?)\s*</a>'
            jockey_matches = re.findall(jockey_pattern, section)

            race_results = []
            seen_jockeys = set()

            for jockey_raw in jockey_matches:
                # Clean jockey name - remove weight/claim info like "(a1.5/51kg)"
                jockey = re.sub(r'\s*\([^)]*\)\s*$', '', jockey_raw).strip()
                # Remove leading "Ms " or "Mr " is fine to keep
                jockey = jockey.strip()

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

    except Exception as e:
        print(f"[RA] Error fetching results for {meeting_name}: {e}")

    return results


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
    print(f"\n{'='*60}")
    print(f"Results Fetcher - {datetime.now().isoformat()}")
    print(f"{'='*60}")

    # Step 1: Get active meetings from API
    meetings = get_active_meetings()
    if not meetings:
        print("No active meetings to check")
        return

    print(f"\nActive meetings ({len(meetings)}):")
    for m in meetings:
        print(f"  - {m['name']} ({m['races_completed']}/{m['total_races']} completed)")

    # Step 2: Get today's meetings from Racing Australia
    print(f"\nFetching today's meetings from Racing Australia...")
    ra_venues = get_todays_meetings()

    if not ra_venues:
        print("No meetings found on Racing Australia for today")
        return

    print(f"\nRacing Australia venues ({len(ra_venues)}):")
    for v in ra_venues:
        print(f"  - {v['name']} ({v['state']})")

    # Step 3: Match and fetch results
    print(f"\n{'='*60}")
    print("Matching meetings and fetching results...")
    print(f"{'='*60}")

    total_sent = 0

    for meeting in meetings:
        meeting_name = meeting['name']
        last_race = meeting['races_completed']

        print(f"\n--- {meeting_name} (completed: {last_race}) ---")

        # Match to Racing Australia venue
        matched = match_meeting_name(meeting_name, ra_venues)

        if not matched:
            print(f"  No match found on Racing Australia")
            print(f"  API name normalized: '{normalize_name(meeting_name)}'")
            print(f"  RA venues normalized: {[normalize_name(v['name']) for v in ra_venues]}")
            continue

        print(f"  Matched: {matched['name']} ({matched['state']})")
        print(f"  URL: {matched['url']}")

        # Fetch results
        results = fetch_race_results(matched['url'], meeting_name)

        if not results:
            print(f"  No results available yet")
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
