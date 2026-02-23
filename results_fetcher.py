"""
RESULTS FETCHER - Runs in GitHub Actions
Fetches race results from Racing Australia (racingaustralia.horse)
and sends to API. No Playwright needed - uses simple HTTP requests.
"""

import re
import requests
from datetime import datetime

API_URL = "https://api.jockeydriverchallenge.com"

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
}


def format_date_for_ra(dt=None):
    if dt is None:
        dt = datetime.utcnow()
    return dt.strftime('%Y%b%d')


def normalize_venue(name):
    return name.strip().title()


def get_todays_meetings_from_ra():
    """Get all today's meetings from Racing Australia - no API call needed"""
    date_str = format_date_for_ra()
    all_meetings = []

    for state in ['NSW', 'VIC', 'QLD', 'SA', 'WA', 'TAS', 'NT']:
        try:
            url = f"https://racingaustralia.horse/FreeFields/Calendar_Results.aspx?State={state}"
            resp = requests.get(url, timeout=15, headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'
            })
            if resp.status_code != 200:
                continue

            links = re.findall(
                r"href='(/FreeFields/Results\.aspx\?Key=([^']+))'[^>]*>([^<]+)</a>",
                resp.text
            )

            for link_path, key, link_text in links:
                if date_str in key:
                    venue_raw = link_text.strip()
                    # Remove state and type suffixes
                    venue_clean = re.sub(r'\s+(NSW|VIC|QLD|SA|WA|TAS|NT|ACT)\s*(-.*)?$', '', venue_raw).strip()
                    all_meetings.append({
                        'name': venue_clean.upper(),
                        'state': state,
                        'url': f"https://racingaustralia.horse{link_path}",
                        'key': key
                    })

        except Exception as e:
            print(f"[Calendar] Error fetching {state}: {e}")

    return all_meetings


def parse_results_html(html, meeting_name):
    """Parse race results from Racing Australia HTML"""
    results = []

    race_headers = re.findall(r'Race\s+(\d+)\s*-\s*[\d:APMapm]+\s*(.+?)(?:\s*\(\d+)', html)

    if not race_headers:
        race_headers_simple = re.findall(r'Race\s+(\d+)', html)
        race_headers = [(num, '') for num in race_headers_simple] if race_headers_simple else []

    race_sections = re.split(r'Race\s+\d+\s*-\s*', html)

    if len(race_sections) <= 1:
        return results

    for idx, section in enumerate(race_sections[1:]):
        if idx >= len(race_headers):
            break

        race_num = int(race_headers[idx][0]) if isinstance(race_headers[idx], tuple) else int(race_headers[idx])

        # Pattern 1: Finish class + jockey with Hilite
        rows = re.findall(
            r"class='Finish\s+F(\d+)'>\s*(\d+)\s*</span>.*?"
            r"<td\s+class='jockey'>.*?<span\s+class='Hilite'>([^<]+)</span>",
            section, re.DOTALL
        )

        if not rows:
            # Pattern 2: simpler
            positions = re.findall(r"class='Finish[^']*'>\s*(\d+)\s*</span>", section)
            jockeys = re.findall(r"class='jockey'[^>]*>.*?<span[^>]*>([^<]+)</span>", section, re.DOTALL)
            if not jockeys:
                jockeys = re.findall(r"class='jockey'[^>]*>.*?>([^<]+)</a>", section, re.DOTALL)
            if positions and jockeys:
                rows = [(p, p, j.strip()) for p, j in zip(positions[:3], jockeys[:3])]

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
            results.append({
                'race_num': race_num,
                'results': top3
            })
        else:
            if 'Acceptances' in section or 'Scratchings' in section:
                break

    return results


def send_result_to_api(meeting_name, race_num, race_results):
    """Send result to API with retry"""
    payload = {
        'meeting': meeting_name.upper(),
        'race_num': race_num,
        'results': race_results
    }

    for attempt in range(3):
        try:
            resp = requests.post(
                f"{API_URL}/api/live-tracker/update/",
                json=payload,
                timeout=30
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get('success'):
                    print(f"  [API] ✅ R{race_num} sent - {[r['jockey'] for r in race_results]}")
                else:
                    print(f"  [API] ⏭️ R{race_num} - {data.get('message', data.get('error', ''))}")
                return data
            elif resp.status_code == 404:
                # Meeting not tracked - skip silently
                return None
            else:
                print(f"  [API] ❌ R{race_num} HTTP {resp.status_code}")
        except requests.exceptions.Timeout:
            print(f"  [API] ⏱️ R{race_num} timeout (attempt {attempt+1}/3)")
        except Exception as e:
            print(f"  [API] Error R{race_num}: {e}")
            break

    return None


def main():
    print(f"\n🏇 Results Fetcher Starting - {datetime.utcnow().isoformat()}")

    # Get meetings directly from Racing Australia (no API call needed!)
    print("Fetching today's meetings from Racing Australia...")
    meetings = get_todays_meetings_from_ra()

    if not meetings:
        print("No meetings found on Racing Australia today")
        return

    print(f"Found {len(meetings)} meetings: {[m['name'] for m in meetings]}")

    total_sent = 0

    for meeting in meetings:
        name = meeting['name']
        url = meeting['url']

        try:
            resp = requests.get(url, timeout=20, headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'
            })
            if resp.status_code != 200:
                continue

            results = parse_results_html(resp.text, name)

            if not results:
                continue

            print(f"\n{name} ({meeting['state']}): {len(results)} completed races")

            for race_data in results:
                result = send_result_to_api(name, race_data['race_num'], race_data['results'])
                if result and result.get('success'):
                    total_sent += 1

        except Exception as e:
            print(f"[Error] {name}: {e}")

    print(f"\n✅ Results Fetcher Complete - Sent {total_sent} results - {datetime.utcnow().isoformat()}")


if __name__ == "__main__":
    main()
