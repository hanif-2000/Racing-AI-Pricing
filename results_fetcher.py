"""
RESULTS FETCHER - Runs in GitHub Actions
Fetches race results from:
  - Racing Australia (racingaustralia.horse) for thoroughbred/jockey challenges
  - HRNZ (infohorse.hrnz.co.nz) for NZ harness/driver challenges
Uses simple HTTP requests - no Playwright/browser needed.
"""

import re
import requests
import urllib3
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

# Suppress SSL warnings for HRNZ (self-signed cert)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

API_URL = "https://api.jockeydriverchallenge.com"
RA_BASE = "https://www.racingaustralia.horse"
HRNZ_BASE = "https://infohorse.hrnz.co.nz/datahrs/results"

STATES = ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT", "ACT"]

# Known HRNZ club name mappings (bookmaker name -> HRNZ club name patterns)
HRNZ_VENUE_ALIASES = {
    'wanganui': ['manawatu', 'wanganui'],
    'otaki': ['otaki'],
    'auckland': ['auckland'],
    'ashburton': ['ashburton'],
    'addington': ['addington', 'nz metropolitan'],
    'cambridge': ['cambridge', 'waikato'],
    'winton': ['winton'],
    'gore': ['gore'],
    'wyndham': ['wyndham'],
    'invercargill': ['southland', 'invercargill'],
    'manawatu': ['manawatu'],
    'forbury': ['forbury', 'otago'],
    'rangiora': ['rangiora', 'amberley'],
    'banks peninsula': ['banks peninsula'],
    'oamaru': ['oamaru', 'north otago'],
    'methven': ['methven'],
    'cromwell': ['cromwell', 'central otago'],
    'kaikoura': ['kaikoura'],
    'geraldine': ['geraldine'],
    'reefton': ['reefton'],
    'nelson': ['nelson'],
    'westport': ['westport'],
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

# Sponsor prefixes to strip for matching
SPONSOR_PREFIXES = [
    "picklebet park ", "picklebet ", "sportsbet-", "sportsbet ",
    "bet365 park ", "bet365 ", "ladbrokes ", "southside ",
    "tabtouch park ", "tabtouch ",
]


def get_australian_date():
    """Get current Australian Eastern time (handles AEST/AEDT automatically)."""
    now_utc = datetime.now(timezone.utc)
    # Determine if AEDT (daylight saving): first Sunday of April to first Sunday of October = AEST (UTC+10)
    # Otherwise AEDT (UTC+11)
    month = now_utc.month
    if 4 <= month <= 9:
        offset = 10  # AEST
    else:
        # For Oct/Nov/Dec/Jan/Feb/Mar, check exact DST transition dates
        # Simplified: use +11 (AEDT) for Oct-Mar, +10 (AEST) for Apr-Sep
        offset = 11  # AEDT
    return now_utc + timedelta(hours=offset)


def normalize_venue(name):
    """Normalize venue name for matching."""
    n = name.lower().strip()
    for prefix in SPONSOR_PREFIXES:
        if n.startswith(prefix):
            n = n[len(prefix):]
            break
    n = re.sub(r'\s+(nsw|vic|qld|sa|wa|tas|nt|act)\s*$', '', n)
    n = re.sub(r'\s*-\s*(professional|trial|picnic|jumpout).*$', '', n)
    n = re.sub(r'\s+(scarpside|hillside|heath)$', '', n)
    return re.sub(r'[^a-z]', '', n)


def to_title_case(name):
    return ' '.join(word.capitalize() for word in name.split())


def build_ra_url(date_key, state, venue_key):
    """Build properly encoded Racing Australia results URL."""
    encoded_venue = quote(venue_key, safe=',')
    return f"{RA_BASE}/FreeFields/Results.aspx?Key={date_key},{state},{encoded_venue}"


def discover_venues_for_date(date_key):
    """Scrape all state calendar pages to find venues for a given date key."""
    venues = []

    for state in STATES:
        try:
            url = f"{RA_BASE}/FreeFields/Calendar_Results.aspx?State={state}"
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                continue

            html = resp.text

            # Match href with BOTH single and double quotes
            pattern = rf"""Results\.aspx\?Key={re.escape(date_key)},{re.escape(state)},([^"'&<>]+)"""
            matches = re.findall(pattern, html)

            seen = set()
            for raw in matches:
                venue_key = raw.replace('%20', ' ').strip()

                if ',Trial' in venue_key or ',JumpOut' in venue_key:
                    continue

                venue_name = re.sub(r',(?:Professional|Picnic)$', '', venue_key)

                result_url = build_ra_url(date_key, state, venue_key)

                if venue_name not in seen:
                    seen.add(venue_name)
                    venues.append({
                        'name': venue_name,
                        'state': state,
                        'url': result_url,
                        'normalized': normalize_venue(venue_name),
                        'date_key': date_key,
                    })

        except Exception as e:
            print(f"  [Calendar] {state} error: {e}")

    return venues


def discover_todays_venues():
    """Discover venues for today AND yesterday (for stale meetings)."""
    aus_now = get_australian_date()
    today_key = aus_now.strftime('%Y%b%d')
    yesterday_key = (aus_now - timedelta(days=1)).strftime('%Y%b%d')

    print(f"  Checking today ({today_key}) and yesterday ({yesterday_key})...")

    venues = discover_venues_for_date(today_key)
    yesterday_venues = discover_venues_for_date(yesterday_key)

    # Add yesterday's venues that aren't already in today's list
    today_norms = {v['normalized'] for v in venues}
    for v in yesterday_venues:
        if v['normalized'] not in today_norms:
            v['name'] = f"{v['name']} (yesterday)"
            venues.append(v)

    return venues, today_key


def match_meeting_to_venue(meeting_name, venues):
    """Match API meeting name to a discovered RA venue."""
    api_norm = normalize_venue(meeting_name)

    # Pass 1: Exact normalized match
    for v in venues:
        if v['normalized'] == api_norm:
            return v

    # Pass 2: One contains the other
    for v in venues:
        if len(api_norm) >= 3 and len(v['normalized']) >= 3:
            if api_norm in v['normalized'] or v['normalized'] in api_norm:
                return v

    # Pass 3: Word-level matching
    api_words = set(meeting_name.lower().split()) - {'park', 'the', 'and', 'of'}
    for v in venues:
        v_words = set(re.sub(r'[^a-z\s]', '', v['name'].lower()).split()) - {'park', 'the', 'and', 'of'}
        if api_words and v_words and (api_words.issubset(v_words) or v_words.issubset(api_words)):
            return v

    return None


def try_direct_url(meeting_name, date_key):
    """Fallback: try direct URL construction for unmatched meetings."""
    venue = to_title_case(meeting_name)

    for state in STATES:
        url = build_ra_url(date_key, state, venue)
        try:
            resp = requests.get(url, headers=HEADERS, timeout=8)
            if resp.status_code != 200:
                continue
            html = resp.text
            if 'Results for this meeting are not currently available' in html:
                continue
            if '<a name="Race1"' not in html:
                continue
            return html, url, state
        except Exception:
            continue

    return None, None, None


def count_total_races(html):
    race_nums = re.findall(r'<a\s+name="Race(\d+)"', html)
    return max(int(n) for n in race_nums) if race_nums else 0


def fetch_race_results(result_url_or_html, meeting_name, is_html=False):
    """Parse results from RA results page."""
    results = []

    try:
        if is_html:
            html = result_url_or_html
        else:
            print(f"  Fetching: {result_url_or_html}")
            resp = requests.get(result_url_or_html, headers=HEADERS, timeout=15)
            print(f"  Status: {resp.status_code}, Length: {len(resp.text)}")
            if resp.status_code != 200:
                return results, 0
            html = resp.text

        if 'Results for this meeting are not currently available' in html:
            print(f"  Page says: results not available")
            return results, 0

        total_races = count_total_races(html)
        race_sections = re.split(r'<a\s+name="Race(\d+)"', html)
        print(f"  Found {total_races} races in HTML, {len(race_sections)//2} sections")

        for i in range(1, len(race_sections), 2):
            race_num = int(race_sections[i])
            if i + 1 >= len(race_sections):
                break

            section = race_sections[i + 1]
            for marker in ['<a name="Race', 'id="ExoticDiv']:
                idx = section.find(marker)
                if idx > 0:
                    section = section[:idx]

            # Extract jockey/driver names from results
            names = []

            # Pattern 1: JockeyLastRuns with name inside <span class='Hilite'>
            # Actual HTML: <a ...JockeyLastRuns...><span class='Hilite'>Name</span></a>
            p1 = r"JockeyLastRuns[^>]+><span[^>]*>([^<]+)</span>"
            names = re.findall(p1, section)

            # Pattern 2: JockeyLastRuns with name directly in <a> tag (fallback)
            if not names:
                p2 = r'JockeyLastRuns[^>]+>\s*([^<]+?)\s*</a>'
                names = re.findall(p2, section)

            # Pattern 3: DriverLastStarts with <span> wrapper
            if not names:
                p3 = r"DriverLastStarts[^>]+><span[^>]*>([^<]+)</span>"
                names = re.findall(p3, section)

            # Pattern 4: DriverLastStarts direct (fallback)
            if not names:
                p4 = r'DriverLastStarts[^>]+>\s*([^<]+?)\s*</a>'
                names = re.findall(p4, section)

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
        print(f"  Parse error: {e}")
        return results, 0

    return results, total_races


# =====================================================
# HRNZ (NZ Harness Racing) Functions
# =====================================================

def discover_hrnz_meetings():
    """Discover today's harness meetings from HRNZ results index."""
    aus_now = get_australian_date()
    # NZ is always 2 hours ahead of Australian Eastern time
    nz_now = aus_now + timedelta(hours=2)
    month_abbr = nz_now.strftime('%b').lower()
    today_str = nz_now.strftime('%d %b %Y')  # e.g., "23 Feb 2026"
    today_dd = nz_now.strftime('%d')
    today_mm = nz_now.strftime('%m')

    meetings = []

    try:
        url = f"{HRNZ_BASE}/rlts_{month_abbr}.htm"
        print(f"  Fetching HRNZ index: {url}")
        resp = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        if resp.status_code != 200:
            print(f"  HRNZ index failed: {resp.status_code}")
            return meetings

        html = resp.text

        # Find meeting links for today - pattern: <a href="MMDD##rs.htm">Club Name</a>
        # The date column has format like "23 Feb 2026" or just the date
        pattern = rf'href=["\']({today_mm}{today_dd}\d{{2}}rs\.htm)["\'][^>]*>([^<]+)</a>'
        matches = re.findall(pattern, html, re.IGNORECASE)

        if not matches:
            # Try broader: find all result links with today's MMDD prefix
            pattern2 = rf'href=["\']({today_mm}{today_dd}\d{{2}}rs\.htm)["\']'
            links = re.findall(pattern2, html, re.IGNORECASE)
            # Get club names from surrounding context
            for link in links:
                # Find the club name near this link
                idx = html.find(link)
                if idx >= 0:
                    snippet = html[idx:idx+200]
                    name_match = re.search(r'>([^<]+)</a>', snippet)
                    if name_match:
                        matches.append((link, name_match.group(1)))

        for filename, club_name in matches:
            club_name = club_name.strip()
            result_url = f"{HRNZ_BASE}/{filename}"
            norm = re.sub(r'[^a-z]', '', club_name.lower().replace('h.r.c.', '').replace('t.c.', '').replace('r.c.', ''))
            meetings.append({
                'name': club_name,
                'url': result_url,
                'normalized': norm,
            })
            print(f"  HRNZ meeting: {club_name} -> {result_url}")

    except Exception as e:
        print(f"  HRNZ discovery error: {e}")

    return meetings


def match_driver_to_hrnz(meeting_name, hrnz_meetings):
    """Match a driver challenge meeting name to HRNZ meeting."""
    name_lower = meeting_name.lower().strip()
    name_norm = re.sub(r'[^a-z]', '', name_lower)

    # Check aliases first
    aliases = HRNZ_VENUE_ALIASES.get(name_lower, [name_lower])

    for hm in hrnz_meetings:
        for alias in aliases:
            alias_norm = re.sub(r'[^a-z]', '', alias)
            if alias_norm in hm['normalized'] or hm['normalized'] in alias_norm:
                return hm

    # Direct normalized match
    for hm in hrnz_meetings:
        if name_norm in hm['normalized'] or hm['normalized'] in name_norm:
            return hm

    return None


def fetch_hrnz_results(result_url, meeting_name):
    """Parse results from HRNZ results page."""
    results = []

    try:
        print(f"  Fetching: {result_url}")
        resp = requests.get(result_url, headers=HEADERS, timeout=15, verify=False)
        print(f"  Status: {resp.status_code}, Length: {len(resp.text)}")
        if resp.status_code != 200:
            return results, 0

        html = resp.text

        # Count races - HRNZ uses <h3> tags with "Race X" or race headers
        race_headers = re.findall(r'Race\s+(\d+)', html)
        total_races = max(int(n) for n in race_headers) if race_headers else 0

        # Split by race sections - look for "Race X" headers
        sections = re.split(r'(?=Race\s+\d+\s)', html)

        for section in sections:
            race_match = re.match(r'Race\s+(\d+)', section)
            if not race_match:
                continue

            race_num = int(race_match.group(1))

            # Extract drivers from result table rows
            # HRNZ HTML: <td data-label="Placing">1</td> ... <td data-label="Driver"><a ...>Name</a></td>
            rows = re.findall(
                r'data-label="Placing"[^>]*>\s*(\d+)\s*</td>.*?data-label="Driver"[^>]*>\s*<a[^>]*>([^<]+)</a>',
                section, re.DOTALL
            )

            race_results = []
            for placing, driver in rows:
                pos = int(placing)
                if pos <= 3:
                    driver = driver.strip()
                    # Remove junior marker like "(J)"
                    driver = re.sub(r'\s*\([^)]*\)\s*$', '', driver).strip()
                    if driver:
                        race_results.append({
                            'position': pos,
                            'jockey': driver,
                            'name': driver
                        })

            if race_results:
                results.append({'race_num': race_num, 'results': race_results[:3]})
                pos = ', '.join(f"{r['position']}. {r['jockey']}" for r in race_results[:3])
                print(f"  R{race_num}: {pos}")

    except Exception as e:
        print(f"  HRNZ parse error: {e}")
        return results, 0

    return results, total_races


def send_results_to_api(meeting_name, race_num, results, actual_total_races=None):
    try:
        payload = {
            'meeting': meeting_name.upper(),
            'race_num': race_num,
            'results': results
        }
        if actual_total_races is not None:
            payload['actual_total_races'] = actual_total_races

        response = requests.post(
            f"{API_URL}/api/live-tracker/update/",
            json=payload, timeout=30
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

    meetings = get_active_meetings()
    if not meetings:
        print("No active meetings")
        return

    jockey_meetings = [m for m in meetings if m['type'] == 'jockey']
    driver_meetings = [m for m in meetings if m['type'] == 'driver']

    print(f"\nActive: {len(jockey_meetings)} jockey, {len(driver_meetings)} driver")
    for m in meetings:
        print(f"  - {m['name']} [{m['type']}] ({m['races_completed']}/{m['total_races']})")

    if not jockey_meetings and not driver_meetings:
        print("No meetings to process")
        return

    total_sent = 0

    # =========================================================
    # THOROUGHBRED / JOCKEY MEETINGS (Racing Australia)
    # =========================================================
    if jockey_meetings:
        print(f"\nDiscovering today's venues from Racing Australia...")
        venues, date_key = discover_todays_venues()
        print(f"Found {len(venues)} venues:")
        for v in venues:
            print(f"  - {v['name']} ({v['state']}) [norm: {v['normalized']}]")

        print(f"\n{'='*60}")
        print("Matching & fetching jockey results...")
        print(f"{'='*60}")

    for meeting in jockey_meetings:
        name = meeting['name']
        last_race = meeting['races_completed']
        tracker_total = meeting['total_races']

        print(f"\n--- {name} ({last_race}/{tracker_total}) ---")

        # Try calendar match first
        matched = match_meeting_to_venue(name, venues)

        html = None
        result_url = None

        if matched:
            print(f"  Matched: {matched['name']} ({matched['state']})")
            result_url = matched['url']
        else:
            # Fallback: try direct URL with base name across all states
            print(f"  No calendar match (norm: '{normalize_venue(name)}'), trying direct URL...")
            html, result_url, state = try_direct_url(name, date_key)
            if html:
                print(f"  Found via direct URL ({state})")
            else:
                # Try yesterday
                yesterday_key = (aus_now - timedelta(days=1)).strftime('%Y%b%d')
                html, result_url, state = try_direct_url(name, yesterday_key)
                if html:
                    print(f"  Found via direct URL yesterday ({state})")
                else:
                    print(f"  Not found on RA")
                    continue

        # Fetch and parse results
        if html:
            results, actual_total = fetch_race_results(html, name, is_html=True)
        else:
            results, actual_total = fetch_race_results(result_url, name)

        if not results:
            print(f"  No results yet")
            continue

        # Check total races mismatch
        actual_total_to_send = None
        if actual_total > 0 and actual_total != tracker_total:
            print(f"  Races: tracker={tracker_total}, actual={actual_total}")
            actual_total_to_send = actual_total

        # Send ALL results - backend will skip duplicates or detect corrections
        reset_needed = False
        for rd in results:
            rn = rd['race_num']
            res = send_results_to_api(name, rn, rd['results'], actual_total_to_send)
            if res:
                if res.get('reset'):
                    # Backend detected wrong results and reset the meeting
                    print(f"  Meeting reset for correction - re-sending all results")
                    reset_needed = True
                    break
                if rn > last_race:
                    total_sent += 1
                actual_total_to_send = None

        # If reset was triggered, re-send all results to the now-clean meeting
        if reset_needed:
            for rd in results:
                res = send_results_to_api(name, rd['race_num'], rd['results'], actual_total_to_send)
                if res and not res.get('reset'):
                    total_sent += 1
                    actual_total_to_send = None

    # =========================================================
    # HARNESS / DRIVER MEETINGS (HRNZ - New Zealand)
    # =========================================================
    if driver_meetings:
        print(f"\n{'='*60}")
        print(f"Processing {len(driver_meetings)} driver meetings (HRNZ)...")
        print(f"{'='*60}")

        hrnz_meetings = discover_hrnz_meetings()
        if not hrnz_meetings:
            print("  No HRNZ meetings found for today")
        else:
            for meeting in driver_meetings:
                name = meeting['name']
                last_race = meeting['races_completed']
                tracker_total = meeting['total_races']

                print(f"\n--- {name} ({last_race}/{tracker_total}) [driver] ---")

                matched = match_driver_to_hrnz(name, hrnz_meetings)
                if not matched:
                    print(f"  Not found on HRNZ")
                    continue

                print(f"  Matched: {matched['name']}")
                results, actual_total = fetch_hrnz_results(matched['url'], name)

                if not results:
                    print(f"  No results yet")
                    continue

                actual_total_to_send = None
                if actual_total > 0 and actual_total != tracker_total:
                    print(f"  Races: tracker={tracker_total}, actual={actual_total}")
                    actual_total_to_send = actual_total

                # Send ALL results - backend handles duplicates/corrections
                reset_needed = False
                for rd in results:
                    rn = rd['race_num']
                    res = send_results_to_api(name, rn, rd['results'], actual_total_to_send)
                    if res:
                        if res.get('reset'):
                            print(f"  Meeting reset for correction - re-sending all results")
                            reset_needed = True
                            break
                        if rn > last_race:
                            total_sent += 1
                        actual_total_to_send = None

                if reset_needed:
                    for rd in results:
                        res = send_results_to_api(name, rd['race_num'], rd['results'], actual_total_to_send)
                        if res and not res.get('reset'):
                            total_sent += 1
                            actual_total_to_send = None

    print(f"\n{'='*60}")
    print(f"Done! Sent {total_sent} new results")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
