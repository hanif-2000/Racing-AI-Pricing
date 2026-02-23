"""
RESULTS FETCHER - Runs in GitHub Actions
Fetches race results from Racing Australia (racingaustralia.horse)
and sends to API. No Playwright needed - uses simple HTTP requests.
"""

import re
import requests
from datetime import datetime

import os
API_URL = os.environ.get("API_URL", "http://localhost:8000")

# Map Australian venues to their state
VENUE_STATE_MAP = {
    # NSW
    'ROSEHILL': 'NSW', 'ROSEHILL GARDENS': 'NSW', 'RANDWICK': 'NSW',
    'ROYAL RANDWICK': 'NSW', 'WARWICK FARM': 'NSW', 'CANTERBURY': 'NSW',
    'NEWCASTLE': 'NSW', 'KEMBLA GRANGE': 'NSW', 'HAWKESBURY': 'NSW',
    'GOSFORD': 'NSW', 'WYONG': 'NSW', 'PORT MACQUARIE': 'NSW',
    'GRAFTON': 'NSW', 'COFFS HARBOUR': 'NSW', 'TAMWORTH': 'NSW',
    'DUBBO': 'NSW', 'BATHURST': 'NSW', 'ORANGE': 'NSW',
    'MUDGEE': 'NSW', 'SCONE': 'NSW', 'MUSWELLBROOK': 'NSW',
    'MOREE': 'NSW', 'NARROMINE': 'NSW', 'NOWRA': 'NSW',
    'QUEANBEYAN': 'NSW', 'WAGGA': 'NSW', 'WAGGA WAGGA': 'NSW',
    'ALBURY': 'NSW', 'SAPPHIRE COAST': 'NSW', 'TAREE': 'NSW',
    'GOULBURN': 'NSW', 'GILGANDRA': 'NSW', 'INVERELL': 'NSW',
    'ARMIDALE': 'NSW', 'BALLINA': 'NSW', 'LISMORE': 'NSW',
    'CASINO': 'NSW', 'CLARENCE RIVER': 'NSW',

    # VIC
    'FLEMINGTON': 'VIC', 'CAULFIELD': 'VIC', 'MOONEE VALLEY': 'VIC',
    'SANDOWN': 'VIC', 'SANDOWN HILLSIDE': 'VIC', 'SANDOWN LAKESIDE': 'VIC',
    'CRANBOURNE': 'VIC', 'PAKENHAM': 'VIC', 'MORNINGTON': 'VIC',
    'GEELONG': 'VIC', 'BALLARAT': 'VIC', 'BENDIGO': 'VIC',
    'WANGARATTA': 'VIC', 'YARRA VALLEY': 'VIC', 'SALE': 'VIC',
    'KILMORE': 'VIC', 'KYNETON': 'VIC', 'SEYMOUR': 'VIC',
    'STONY CREEK': 'VIC', 'HAMILTON': 'VIC', 'COLAC': 'VIC',
    'WARRNAMBOOL': 'VIC', 'STAWELL': 'VIC', 'ARARAT': 'VIC',
    'BAIRNSDALE': 'VIC', 'TRARALGON': 'VIC', 'MOE': 'VIC',
    'ECHUCA': 'VIC', 'SWAN HILL': 'VIC', 'MILDURA': 'VIC',
    'DONALD': 'VIC', 'WODONGA': 'VIC', 'SPORTSBET PAKENHAM': 'VIC',

    # QLD
    'EAGLE FARM': 'QLD', 'DOOMBEN': 'QLD', 'GOLD COAST': 'QLD',
    'SUNSHINE COAST': 'QLD', 'IPSWICH': 'QLD', 'TOOWOOMBA': 'QLD',
    'CALLAGHAN PARK': 'QLD', 'ROCKHAMPTON': 'QLD', 'MACKAY': 'QLD',
    'TOWNSVILLE': 'QLD', 'CAIRNS': 'QLD', 'KILCOY': 'QLD',
    'BEAUDESERT': 'QLD', 'GATTON': 'QLD', 'DALBY': 'QLD',
    'BUNDABERG': 'QLD', 'GLADSTONE': 'QLD', 'EMERALD': 'QLD',
    'LONGREACH': 'QLD', 'ROMA': 'QLD', 'CHINCHILLA': 'QLD',
    'AQUIS PARK': 'QLD', 'AQUIS PARK GOLD COAST': 'QLD',

    # SA
    'MORPHETTVILLE': 'SA', 'MORPHETTVILLE PARKS': 'SA', 'MURRAY BRIDGE': 'SA',
    'GAWLER': 'SA', 'PORT AUGUSTA': 'SA', 'MOUNT GAMBIER': 'SA',
    'BALAKLAVA': 'SA', 'STRATHALBYN': 'SA', 'PORT LINCOLN': 'SA',
    'OAKBANK': 'SA', 'KANGAROO ISLAND': 'SA', 'PENOLA': 'SA',
    'NARACOORTE': 'SA', 'CEDUNA': 'SA', 'ROXBY DOWNS': 'SA',
    'CLARE': 'SA', 'BORDERTOWN': 'SA', 'MINLATON': 'SA',

    # WA
    'ASCOT': 'WA', 'BELMONT': 'WA', 'BELMONT PARK': 'WA',
    'PINJARRA': 'WA', 'BUNBURY': 'WA', 'NORTHAM': 'WA',
    'KALGOORLIE': 'WA', 'GERALDTON': 'WA', 'ALBANY': 'WA',
    'YORK': 'WA', 'NARROGIN': 'WA', 'BROOME': 'WA',
    'CARNARVON': 'WA', 'LARK HILL': 'WA', 'MT BARKER': 'WA',
    'ESPERANCE': 'WA', 'BEVERLEY': 'WA',

    # TAS
    'HOBART': 'TAS', 'LAUNCESTON': 'TAS', 'DEVONPORT': 'TAS',
    'SPREYTON': 'TAS', 'LONGFORD': 'TAS', 'ELWICK': 'TAS',
    'MOWBRAY': 'TAS',

    # NT
    'DARWIN': 'NT', 'ALICE SPRINGS': 'NT', 'FANNIE BAY': 'NT',

    # NZ
    'WANGANUI': 'NZ', 'OTAKI': 'NZ', 'TRENTHAM': 'NZ',
    'ELLERSLIE': 'NZ', 'RICCARTON': 'NZ', 'HASTINGS': 'NZ',
    'TE RAPA': 'NZ', 'RUAKAKA': 'NZ', 'AWAPUNI': 'NZ',
    'MATAMATA': 'NZ', 'PUKEKOHE': 'NZ', 'NEW PLYMOUTH': 'NZ',
    'WINGATUI': 'NZ', 'ASHBURTON': 'NZ', 'ADDINGTON': 'NZ',
    'WAIKATO': 'NZ', 'ROTORUA': 'NZ',
}


def get_state_for_venue(venue_name):
    """Get the state code for a venue"""
    upper = venue_name.upper().strip()
    if upper in VENUE_STATE_MAP:
        return VENUE_STATE_MAP[upper]

    # Try partial match
    for key, state in VENUE_STATE_MAP.items():
        if key in upper or upper in key:
            return state

    return None


def format_date_for_ra(dt=None):
    """Format date as Racing Australia expects: 2026Feb23"""
    if dt is None:
        dt = datetime.now()
    return dt.strftime('%Y%b%d')


def normalize_venue_name(name):
    """Convert API meeting name to Racing Australia venue format"""
    # Title case: "PORT MACQUARIE" -> "Port Macquarie"
    return name.strip().title()


def fetch_meeting_results_from_ra(meeting_name, state):
    """Fetch results from racingaustralia.horse"""
    date_str = format_date_for_ra()
    venue = normalize_venue_name(meeting_name)

    # Try the direct URL first
    url = f"https://racingaustralia.horse/FreeFields/Results.aspx?Key={date_str},{state},{venue}"
    print(f"[ResultsFetcher] Trying: {url}")

    try:
        resp = requests.get(url, timeout=30, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })

        if resp.status_code != 200:
            print(f"[ResultsFetcher] HTTP {resp.status_code} for {venue}")
            # Try finding the correct venue name from calendar
            return try_calendar_search(meeting_name, state, date_str)

        html = resp.text

        # Check if we actually got results
        if 'Race 1' not in html and 'race 1' not in html.lower():
            print(f"[ResultsFetcher] No race data found for {venue}")
            return try_calendar_search(meeting_name, state, date_str)

        return parse_results_html(html, meeting_name)

    except Exception as e:
        print(f"[ResultsFetcher] Error fetching {venue}: {e}")
        return []


def try_calendar_search(meeting_name, state, date_str):
    """Search the calendar page to find the correct venue URL"""
    states_to_try = [state] if state else ['NSW', 'VIC', 'QLD', 'SA', 'WA', 'TAS', 'NT']

    target = meeting_name.upper().strip()

    for st in states_to_try:
        try:
            cal_url = f"https://racingaustralia.horse/FreeFields/Calendar_Results.aspx?State={st}"
            resp = requests.get(cal_url, timeout=30, headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            })

            if resp.status_code != 200:
                continue

            # Find meeting links matching our venue
            # Links look like: href='/FreeFields/Results.aspx?Key=2026Feb23,NSW,Port Macquarie'
            links = re.findall(
                r"href='(/FreeFields/Results\.aspx\?Key=[^']+)'[^>]*>([^<]+)</a>",
                resp.text
            )

            for link_path, link_text in links:
                link_venue = link_text.strip().upper()
                # Remove state suffix like "PORT MACQUARIE NSW"
                link_venue_clean = re.sub(r'\s+(NSW|VIC|QLD|SA|WA|TAS|NT|ACT)\s*(-.*)?$', '', link_venue).strip()
                # Remove sponsor prefixes like "Sportsbet-"
                link_venue_clean = re.sub(r'^(SPORTSBET|BET365|LADBROKES|TAB|TABCORP)\s*[-]?\s*', '', link_venue_clean, flags=re.I).strip()

                if (target in link_venue_clean or
                    link_venue_clean in target or
                    target.replace(' ', '') == link_venue_clean.replace(' ', '')):

                    # Found matching venue
                    result_url = f"https://racingaustralia.horse{link_path}"
                    print(f"[ResultsFetcher] Found via calendar: {link_text.strip()} -> {result_url}")

                    resp2 = requests.get(result_url, timeout=30, headers={
                        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                    })

                    if resp2.status_code == 200:
                        return parse_results_html(resp2.text, meeting_name)

        except Exception as e:
            print(f"[ResultsFetcher] Calendar search error for {st}: {e}")
            continue

    print(f"[ResultsFetcher] Could not find {meeting_name} in any calendar")
    return []


def parse_results_html(html, meeting_name):
    """Parse race results from Racing Australia HTML"""
    results = []

    # Find all race sections
    # Race headers look like: "Race 1 - 12:30PM Race Name (1200m)"
    race_headers = re.findall(r'Race\s+(\d+)\s*-\s*[\d:APMapm]+\s*(.+?)(?:\s*\(\d+)', html)

    if not race_headers:
        # Try alternative pattern
        race_headers = re.findall(r'Race\s+(\d+)', html)
        race_headers = [(num, '') for num in (race_headers if isinstance(race_headers[0], str) else race_headers)] if race_headers else []

    # Split HTML by race sections
    race_sections = re.split(r'Race\s+\d+\s*-\s*', html)

    if len(race_sections) <= 1:
        print(f"[ResultsFetcher] No race sections found for {meeting_name}")
        return results

    for idx, section in enumerate(race_sections[1:]):
        if idx >= len(race_headers):
            break

        race_num = int(race_headers[idx][0]) if isinstance(race_headers[idx], tuple) else int(race_headers[idx])

        # Extract jockey results from the table
        # Pattern: Finish position + horse + jockey with Hilite span
        rows = re.findall(
            r"class='Finish\s+F(\d+)'>\s*(\d+)\s*</span>.*?"
            r"<td\s+class='jockey'>.*?<span\s+class='Hilite'>([^<]+)</span>",
            section, re.DOTALL
        )

        if not rows:
            # Try alternative patterns
            # Pattern 2: simpler jockey extraction
            rows = re.findall(
                r"<span class='Finish[^']*'>(\d+)</span>.*?"
                r"class='jockey'[^>]*>.*?>([^<]+)</(?:span|a)>",
                section, re.DOTALL
            )
            if rows:
                rows = [(pos, pos, jockey) for pos, jockey in rows]

        if not rows:
            # Pattern 3: any table with positions and jockeys
            positions = re.findall(r"class='Finish[^']*'>\s*(\d+)\s*</span>", section)
            jockeys = re.findall(r"class='jockey'[^>]*>.*?<span[^>]*>([^<]+)</span>", section, re.DOTALL)

            if not jockeys:
                jockeys = re.findall(r"class='jockey'[^>]*>.*?>([^<]+)</a>", section, re.DOTALL)

            if positions and jockeys:
                rows = [(p, p, j.strip()) for p, j in zip(positions[:3], jockeys[:3])]

        # Get top 3 results
        top3 = []
        for row in rows[:3]:
            position = int(row[1]) if len(row) > 2 else int(row[0])
            jockey = row[2].strip() if len(row) > 2 else row[1].strip()

            if jockey and jockey not in [r['jockey'] for r in top3]:
                top3.append({
                    'position': position,
                    'jockey': jockey,
                    'name': jockey
                })

        if top3:
            print(f"[ResultsFetcher] {meeting_name} R{race_num}: {[r['jockey'] for r in top3]}")
            results.append({
                'race_num': race_num,
                'results': top3
            })
        else:
            # Race might not have finished yet
            if 'Acceptances' in section or 'Scratchings' in section:
                print(f"[ResultsFetcher] {meeting_name} R{race_num}: Race not yet completed")
                break  # Stop checking subsequent races

    return results


def send_results_to_api(meeting_name, race_num, race_results):
    """Send results to production API"""
    try:
        payload = {
            'meeting': meeting_name.upper(),
            'race_num': race_num,
            'results': race_results
        }

        response = requests.post(
            f"{API_URL}/api/live-tracker/update/",
            json=payload,
            timeout=60
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


def main():
    print(f"\n🏇 Results Fetcher Starting - {datetime.now().isoformat()}")

    # Get active meetings
    meetings = get_active_meetings()

    if not meetings:
        print("No active meetings to check")
        return

    print(f"Found {len(meetings)} active meetings: {[m['name'] for m in meetings]}")

    total_sent = 0

    for meeting in meetings:
        meeting_name = meeting['name']
        last_race = meeting['races_completed']

        print(f"\n--- Checking {meeting_name} (last race: {last_race}) ---")

        # Get state for this venue
        state = get_state_for_venue(meeting_name)
        if not state:
            print(f"[ResultsFetcher] Unknown state for {meeting_name}, searching all states...")

        # Fetch results from Racing Australia
        results = fetch_meeting_results_from_ra(meeting_name, state)

        # Send new results to API
        for race_data in results:
            race_num = race_data['race_num']

            # Only send if new race
            if race_num > last_race:
                result = send_results_to_api(meeting_name, race_num, race_data['results'])
                if result:
                    total_sent += 1

    print(f"\n✅ Results Fetcher Complete - Sent {total_sent} new results - {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
