import asyncio
import re
from datetime import datetime
from playwright.async_api import async_playwright

def normalize_name(name):
    name = re.sub(r'\s*\([^)]+\)$', '', name).strip()
    return ' '.join(name.split()).lower()

def match_jockey(result_name, challenge_jockeys):
    result_norm = normalize_name(result_name)
    result_last = result_norm.split()[-1] if result_norm.split() else ''
    
    for cj in challenge_jockeys:
        cj_norm = normalize_name(cj)
        cj_last = cj_norm.split()[-1] if cj_norm.split() else ''
        
        if result_norm == cj_norm:
            return cj
        if result_last == cj_last and len(result_last) > 2:
            return cj
        if result_norm in cj_norm or cj_norm in result_norm:
            return cj
    return None

async def fetch_meeting_results(meeting_name, challenge_jockeys):
    results = {
        'meeting': meeting_name.upper(),
        'jockeys': {j: {'points': 0, 'wins': 0, 'seconds': 0, 'thirds': 0, 'races': {}} for j in challenge_jockeys},
        'completed_races': [],
        'race_results': [],
        'last_updated': datetime.now().isoformat()
    }
    
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
    page = await context.new_page()
    
    try:
        print(f"[Auto] Fetching {meeting_name}...")
        await page.goto('https://www.ladbrokes.com.au/racing/results', timeout=60000)
        await asyncio.sleep(5)
        
        # MORE scrolling to load all content
        for _ in range(10):
            await page.evaluate('window.scrollBy(0, 300)')
            await asyncio.sleep(0.3)
        
        # Scroll back to top
        await page.evaluate('window.scrollTo(0, 0)')
        await asyncio.sleep(1)
        
        text = await page.evaluate('document.body.innerText')
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        
        # Find meeting (case insensitive)
        meeting_idx = None
        for i, line in enumerate(lines):
            if line.lower() == meeting_name.lower():
                meeting_idx = i
                print(f"[Auto] Found {meeting_name} at line {i}")
                break
        
        if not meeting_idx:
            print(f"[Auto] {meeting_name} not found in {len(lines)} lines")
            # Debug: show some lines
            for i, ln in enumerate(lines[120:145]):
                print(f"  {i+120}: {ln}")
            return results
        
        # Get race result cells
        race_results_map = {}
        i = meeting_idx + 2
        while i < min(meeting_idx + 30, len(lines)):
            line = lines[i]
            if line in ['VIC', 'NSW', 'QLD', 'SA', 'WA', 'TAS', 'NT', 'NZ', 'HK'] and i > meeting_idx + 3:
                break
            m = re.match(r'^R(\d+)$', line)
            if m and i + 1 < len(lines):
                race_num = int(m.group(1))
                result_cell = lines[i + 1]
                if re.match(r'^\d+[/\d]*,\s*\d+', result_cell):
                    race_results_map[race_num] = result_cell
            i += 1
        
        results['completed_races'] = sorted(race_results_map.keys())
        print(f"[Auto] Completed: {results['completed_races']}")
        
        for race_num, result_cell in race_results_map.items():
            try:
                await page.goto('https://www.ladbrokes.com.au/racing/results', timeout=30000)
                await asyncio.sleep(2)
                
                # Scroll to load all
                for _ in range(8):
                    await page.evaluate('window.scrollBy(0, 300)')
                    await asyncio.sleep(0.2)
                
                await page.click(f'text="{result_cell}"', timeout=5000)
                await asyncio.sleep(3)
                
                # Scroll on race page
                for _ in range(3):
                    await page.evaluate('window.scrollBy(0, 300)')
                    await asyncio.sleep(0.2)
                
                text = await page.evaluate('document.body.innerText')
                page_lines = [l.strip() for l in text.split('\n') if l.strip()]
                
                # Extract jockeys - format: "J Name" after RESULTS section
                race_jockeys = []
                in_results = False
                
                for ln in page_lines:
                    if ln == 'RESULTS':
                        in_results = True
                        continue
                    if in_results and ln in ['EXOTIC RESULTS', 'FINAL MARGINS']:
                        break
                    
                    # Match "J Name" (jockey line starts with "J ")
                    if in_results and re.match(r'^J\s+[A-Z]', ln):
                        jockey = ln[2:].strip()
                        jockey = re.sub(r'\s*\([^)]+\)$', '', jockey)
                        if jockey and jockey not in race_jockeys:
                            race_jockeys.append(jockey)
                        if len(race_jockeys) >= 3:
                            break
                
                race_detail = {'race': race_num, 'top3': race_jockeys, 'points': []}
                print(f"[Auto] R{race_num}: {race_jockeys}")
                
                # Award points
                points_map = {0: 3, 1: 2, 2: 1}
                for pos, jockey_name in enumerate(race_jockeys[:3]):
                    matched = match_jockey(jockey_name, challenge_jockeys)
                    if matched:
                        pts = points_map[pos]
                        results['jockeys'][matched]['points'] += pts
                        results['jockeys'][matched]['races'][f'R{race_num}'] = pts
                        if pos == 0: results['jockeys'][matched]['wins'] += 1
                        elif pos == 1: results['jockeys'][matched]['seconds'] += 1
                        elif pos == 2: results['jockeys'][matched]['thirds'] += 1
                        race_detail['points'].append({'jockey': matched, 'pos': pos+1, 'pts': pts})
                        print(f"[Auto]   ✅ {matched} +{pts}")
                
                results['race_results'].append(race_detail)
                
            except Exception as e:
                print(f"[Auto] R{race_num} err: {str(e)[:40]}")
        
        print(f"[Auto] Done: {len(results['race_results'])} races")
        
    except Exception as e:
        print(f"[Auto] Error: {str(e)[:60]}")
    finally:
        await browser.close()
        await playwright.stop()
    
    return results


async def auto_update_meeting(meeting_name, jockeys_list):
    results = await fetch_meeting_results(meeting_name, jockeys_list)
    
    standings = []
    for jockey, data in results['jockeys'].items():
        standings.append({
            'name': jockey,
            'points': data['points'],
            'wins': data['wins'],
            'seconds': data['seconds'],
            'thirds': data['thirds'],
            'races': data['races'],
            'is_leader': False
        })
    
    standings.sort(key=lambda x: (-x['points'], -x['wins']))
    if standings and standings[0]['points'] > 0:
        standings[0]['is_leader'] = True
    
    return {
        'success': True,
        'meeting': results['meeting'],
        'standings': standings,
        'completed_races': results['completed_races'],
        'race_results': results['race_results'],
        'last_updated': results['last_updated']
    }


if __name__ == '__main__':
    async def test():
        jockeys = ['Campbell Rawiller', 'Jason Holder', 'Kayla Crowther', 
                   'Connor Murtagh', 'Sophie Potter', 'Brooke King', 'Ben Price']
        
        result = await auto_update_meeting('Strathalbyn', jockeys)
        
        print('\n' + '='*60)
        print(f"📊 {result['meeting']} STANDINGS")
        print('='*60)
        
        for s in result['standings']:
            leader = '👑' if s['is_leader'] else '  '
            races = ' '.join([f"R{k[1:]}:+{v}" for k,v in s['races'].items()])
            print(f"{leader} {s['name']}: {s['points']} pts (W:{s['wins']} 2:{s['seconds']} 3:{s['thirds']}) | {races}")
    
    asyncio.run(test())
