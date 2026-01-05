import asyncio
import re
from datetime import datetime
from playwright.async_api import async_playwright

# =====================================================
# 📦 CACHE
# =====================================================

CACHE = {
    'jockey_challenges': [],
    'driver_challenges': [],
    'last_updated': None,
    'is_scraping': False
}

def get_cached_data():
    return {
        'jockey_challenges': CACHE['jockey_challenges'],
        'driver_challenges': CACHE['driver_challenges'],
        'last_updated': CACHE['last_updated'],
        'from_cache': True
    }

def has_cached_data():
    return len(CACHE['jockey_challenges']) > 0 or len(CACHE['driver_challenges']) > 0


# =====================================================
# 🇳🇿 COUNTRY DETECTION - SMART
# =====================================================

def get_country(track_name):
    """
    Detect country from track name
    - First check if "NZ" is in the name (from bookmaker)
    - Then fallback to known NZ tracks list
    - Default to AU
    """
    track_upper = track_name.upper().strip()
    
    # Method 1: Check if bookmaker added "NZ" suffix
    if ' NZ' in track_upper or '-NZ' in track_upper or track_upper.endswith('NZ'):
        return 'NZ'
    
    # Method 2: Known NZ tracks (fallback - these are physical racecourses)
    NZ_TRACKS = [
        'TE AROHA', 'TRENTHAM', 'ELLERSLIE', 'RICCARTON', 'OTAKI',
        'HASTINGS', 'AWAPUNI', 'WANGANUI', 'ROTORUA', 'TAURANGA',
        'PUKEKOHE', 'RUAKAKA', 'MATAMATA', 'TE RAPA', 'WOODVILLE',
        'ADDINGTON', 'ALEXANDRA PARK', 'CAMBRIDGE', 'FORBURY',
        'ASCOT PARK', 'MANAWATU', 'MANUKAU', 'GREYMOUTH', 'ROXBURGH',
        'WINGATUI', 'OAMARU', 'TIMARU', 'ASHBURTON', 'RANGIORA',
        'FORBURY PARK', 'WYNDHAM', 'METHVEN', 'WASHDYKE', 'KAIKOURA',
        'OMAKAU', 'WINTON', 'CROMWELL', 'RIVERTON', 'KUROW', 'TAPANUI'
    ]
    
    for nz_track in NZ_TRACKS:
        if nz_track in track_upper or track_upper in nz_track:
            return 'NZ'
    
    # Default to AU
    return 'AU'


# =====================================================
# 🌐 BASE SCRAPER
# =====================================================

class BaseScraper:
    async def get_browser(self):
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
        )
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            locale='en-AU',
            timezone_id='Australia/Sydney',
        )
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return playwright, browser, context


# =====================================================
# TABTOUCH - FULLY DYNAMIC + BOTH FORMATS
# =====================================================

class TABtouchScraper(BaseScraper):
    async def get_all_jockey_data(self):
        meetings = []
        playwright = browser = context = None
        
        try:
            playwright, browser, context = await self.get_browser()
            page = await context.new_page()
            
            print("[TABtouch] Navigating...")
            await page.goto('https://www.tabtouch.com.au/racing/jockey-challenge', timeout=30000)
            await asyncio.sleep(5)
            
            for _ in range(5):
                await page.evaluate('window.scrollBy(0, 500)')
                await asyncio.sleep(0.5)
            
            text = await page.evaluate('document.body.innerText')
            
            # DYNAMIC: Find all meetings from page
            meetings_found = re.findall(r'([A-Za-z ]+) Jockey Challenge 3,2,1 Points', text)
            meetings_found = list(dict.fromkeys([m.strip() for m in meetings_found]))
            
            print(f"[TABtouch] Found {len(meetings_found)} meetings dynamically: {meetings_found}")
            
            for meeting in meetings_found:
                try:
                    await page.goto('https://www.tabtouch.com.au/racing/jockey-challenge', timeout=30000)
                    await asyncio.sleep(3)
                    
                    for _ in range(5):
                        await page.evaluate('window.scrollBy(0, 400)')
                        await asyncio.sleep(0.3)
                    
                    await page.click(f'text="{meeting} Jockey Challenge 3,2,1 Points"', timeout=5000)
                    await asyncio.sleep(4)
                    
                    text = await page.evaluate('document.body.innerText')
                    lines = [l.strip() for l in text.split('\n') if l.strip()]
                    
                    jockeys = []
                    
                    # Format 1: "NAME NUMBER ODDS" same line (closed markets)
                    pattern1 = re.compile(r'^([A-Z][A-Z\s]+)\s+(\d{6})\s+(\d+\.\d{2})$')
                    # Format 2: "NAME NUMBER" then "ODDS" next line (open markets)
                    pattern2_name = re.compile(r'^([A-Z][A-Z\s]+)\s+(\d{6})$')
                    pattern2_odds = re.compile(r'^(\d+\.\d{2})$')
                    
                    i = 0
                    while i < len(lines):
                        line = lines[i]
                        
                        match1 = pattern1.match(line)
                        if match1:
                            name = match1.group(1).strip()
                            odds = float(match1.group(3))
                            if 'ANY OTHER' not in name and 1 < odds < 500:
                                jockeys.append({'name': name.title(), 'odds': odds})
                            i += 1
                            continue
                        
                        match2_name = pattern2_name.match(line)
                        if match2_name and i + 1 < len(lines):
                            match2_odds = pattern2_odds.match(lines[i + 1])
                            if match2_odds:
                                name = match2_name.group(1).strip()
                                odds = float(match2_odds.group(1))
                                if 'ANY OTHER' not in name and 1 < odds < 500:
                                    jockeys.append({'name': name.title(), 'odds': odds})
                                i += 2
                                continue
                        i += 1
                    
                    if jockeys:
                        meetings.append({
                            'meeting': meeting.upper(),
                            'type': 'jockey',
                            'jockeys': jockeys,
                            'source': 'tabtouch',
                            'country': get_country(meeting)
                        })
                        print(f"[TABtouch] ✅ {meeting} ({get_country(meeting)}): {len(jockeys)} jockeys")
                    else:
                        print(f"[TABtouch] ⚠️ {meeting}: No odds (market suspended)")
                        
                except Exception as e:
                    print(f"[TABtouch] ⚠️ {meeting}: {str(e)[:40]}")
            
            print(f"[TABtouch] ✅ {len(meetings)} meetings total")
            
        except Exception as e:
            print(f"[TABtouch] ❌ Error: {str(e)[:80]}")
        finally:
            if browser: await browser.close()
            if playwright: await playwright.stop()
        
        return meetings


# =====================================================
# LADBROKES - FULLY DYNAMIC
# =====================================================

class LadbrokesScraper(BaseScraper):
    async def get_all_jockey_data(self):
        meetings = []
        playwright = browser = context = None
        
        try:
            playwright, browser, context = await self.get_browser()
            page = await context.new_page()
            
            print("[Ladbrokes] Navigating to Extras...")
            await page.goto('https://www.ladbrokes.com.au/racing/extras', timeout=60000)
            await asyncio.sleep(5)
            
            text = await page.evaluate('document.body.innerText')
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            
            # Find Horse Racing section (skip sidebar, look in main content after line 60)
            horse_start = None
            greyhound_start = None
            
            for i, line in enumerate(lines):
                if line == 'Horse Racing' and i > 60:
                    horse_start = i
                elif line == 'Greyhounds' and horse_start:
                    greyhound_start = i
                    break
            
            # Extract Horse Racing meetings
            horse_meetings = []
            if horse_start and greyhound_start:
                for i in range(horse_start + 1, greyhound_start):
                    line = lines[i]
                    if i + 1 < len(lines) and lines[i + 1] == 'keyboard_arrow_down':
                        if line and len(line) > 2 and line not in ['INTL', 'Horse Racing']:
                            horse_meetings.append(line)
            
            print(f"[Ladbrokes] Found {len(horse_meetings)} Horse meetings: {horse_meetings}")
            
            for meeting in horse_meetings:
                try:
                    await page.goto('https://www.ladbrokes.com.au/racing/extras', timeout=60000)
                    await asyncio.sleep(3)
                    
                    await page.click(f'text="{meeting}"', timeout=3000)
                    await asyncio.sleep(2)
                    
                    text = await page.evaluate('document.body.innerText')
                    jc_text = f'Jockey Challenge - {meeting}'
                    
                    if jc_text in text:
                        await page.click(f'text="{jc_text}"', timeout=3000)
                        await asyncio.sleep(3)
                        
                        text = await page.evaluate('document.body.innerText')
                        lines = [l.strip() for l in text.split('\n') if l.strip()]
                        
                        jockeys = []
                        for i, line in enumerate(lines):
                            if re.match(r'^\d+\.\d{2}$', line):
                                odds = float(line)
                                if i > 0 and 1.01 < odds < 500:
                                    name = lines[i-1]
                                    if name and len(name) > 3 and not re.match(r'^\d', name):
                                        skip = ['Jockey Challenge', 'keyboard', 'Same Meeting', 
                                                'Most Points', 'To Ride', 'Winner', 'arrow']
                                        if not any(s.lower() in name.lower() for s in skip):
                                            if not any(j['name'] == name for j in jockeys):
                                                jockeys.append({'name': name, 'odds': odds})
                        
                        if jockeys:
                            meetings.append({
                                'meeting': meeting.upper(),
                                'type': 'jockey',
                                'jockeys': jockeys,
                                'source': 'ladbrokes',
                                'country': get_country(meeting)
                            })
                            print(f"[Ladbrokes] ✅ {meeting} ({get_country(meeting)}): {len(jockeys)} jockeys")
                    
                except Exception as e:
                    print(f"[Ladbrokes] ⚠️ {meeting}: {str(e)[:40]}")
            
            print(f"[Ladbrokes] ✅ {len(meetings)} jockey meetings total")
            
        except Exception as e:
            print(f"[Ladbrokes] ❌ Error: {str(e)[:80]}")
        finally:
            if browser: await browser.close()
            if playwright: await playwright.stop()
        
        return meetings
    
    async def get_all_driver_data(self):
        meetings = []
        playwright = browser = context = None
        
        try:
            playwright, browser, context = await self.get_browser()
            page = await context.new_page()
            
            print("[Ladbrokes] Navigating for drivers...")
            await page.goto('https://www.ladbrokes.com.au/racing/extras', timeout=60000)
            await asyncio.sleep(5)
            
            text = await page.evaluate('document.body.innerText')
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            
            # Find Harness Racing section
            harness_start = None
            for i, line in enumerate(lines):
                if line == 'Harness Racing' and i > 60:
                    harness_start = i
                    break
            
            # Extract Harness meetings
            harness_meetings = []
            if harness_start:
                for i in range(harness_start + 1, min(harness_start + 30, len(lines))):
                    line = lines[i]
                    if i + 1 < len(lines) and lines[i + 1] == 'keyboard_arrow_down':
                        if line and len(line) > 2:
                            harness_meetings.append(line)
                    if '24/7' in line or 'Responsible' in line:
                        break
            
            print(f"[Ladbrokes] Found {len(harness_meetings)} Harness meetings: {harness_meetings}")
            
            for meeting in harness_meetings:
                try:
                    await page.goto('https://www.ladbrokes.com.au/racing/extras', timeout=60000)
                    await asyncio.sleep(3)
                    
                    await page.click(f'text="{meeting}"', timeout=3000)
                    await asyncio.sleep(2)
                    
                    text = await page.evaluate('document.body.innerText')
                    dc_text = f'Driver Challenge - {meeting}'
                    
                    if dc_text in text:
                        await page.click(f'text="{dc_text}"', timeout=3000)
                        await asyncio.sleep(3)
                        
                        text = await page.evaluate('document.body.innerText')
                        lines = [l.strip() for l in text.split('\n') if l.strip()]
                        
                        drivers = []
                        for i, line in enumerate(lines):
                            if re.match(r'^\d+\.\d{2}$', line):
                                odds = float(line)
                                if i > 0 and 1.01 < odds < 500:
                                    name = lines[i-1]
                                    if name and len(name) > 3 and not re.match(r'^\d', name):
                                        skip = ['Driver Challenge', 'keyboard', 'Same Meeting', 
                                                'Most Points', 'To Drive', 'Winner', 'arrow']
                                        if not any(s.lower() in name.lower() for s in skip):
                                            if not any(d['name'] == name for d in drivers):
                                                drivers.append({'name': name, 'odds': odds})
                        
                        if drivers:
                            meetings.append({
                                'meeting': meeting.upper(),
                                'type': 'driver',
                                'drivers': drivers,
                                'source': 'ladbrokes',
                                'country': get_country(meeting)
                            })
                            print(f"[Ladbrokes] ✅ {meeting} ({get_country(meeting)}) Driver: {len(drivers)} drivers")
                    
                except Exception as e:
                    print(f"[Ladbrokes] ⚠️ Driver {meeting}: {str(e)[:40]}")
            
            print(f"[Ladbrokes] ✅ {len(meetings)} driver meetings total")
            
        except Exception as e:
            print(f"[Ladbrokes] ❌ Driver Error: {str(e)[:80]}")
        finally:
            if browser: await browser.close()
            if playwright: await playwright.stop()
        
        return meetings


class TABScraper(BaseScraper):
    async def get_all_jockey_data(self):
        meetings = []
        playwright = browser = None
        
        try:
            import os
            playwright = await async_playwright().start()
            user_data_dir = '/tmp/tab_chrome_profile'
            os.makedirs(user_data_dir, exist_ok=True)
            
            browser = await playwright.chromium.launch_persistent_context(
                user_data_dir,
                headless=False,
                args=['--disable-blink-features=AutomationControlled'],
                viewport={'width': 1920, 'height': 1080},
                locale='en-AU',
                timezone_id='Australia/Sydney',
            )
            page = browser.pages[0] if browser.pages else await browser.new_page()
            
            print("[TAB] Navigating...")
            await page.goto("https://www.tab.com.au/sports/betting/Jockey%20Challenge/competitions/Jockey%20Challenge", 
                          wait_until='domcontentloaded', timeout=60000)
            await asyncio.sleep(10)
            
            content = await page.content()
            if 'Access Denied' in content:
                print("[TAB] ❌ Access Denied")
                return []
            
            for _ in range(3):
                await page.evaluate('window.scrollBy(0, 500)')
                await asyncio.sleep(0.5)
            
            text = await page.evaluate('document.body.innerText')
            
            if 'JOCK MstPts' not in text:
                print("[TAB] ❌ No content found")
                return []
            
            lines = text.split('\n')
            current_meeting = None
            jockeys = []
            prev_name = None
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                if line.startswith('JOCK MstPts '):
                    remaining = line.replace('JOCK MstPts ', '')
                    if remaining.isupper() and not any(c.isdigit() for c in remaining):
                        if current_meeting and jockeys:
                            meetings.append({
                                'meeting': current_meeting, 
                                'type': 'jockey', 
                                'jockeys': jockeys.copy(), 
                                'source': 'tab',
                                'country': get_country(current_meeting)
                            })
                        current_meeting = remaining
                        jockeys = []
                        prev_name = None
                        continue
                
                skip = ['Market', 'SUSP', 'Any Other', 'Bet Slip', 'MENU', 'AUDIO', 'Jockey Challenge', 'JOCK MstPts']
                if any(x.lower() in line.lower() for x in skip):
                    prev_name = None
                    continue
                
                try:
                    odds = float(line)
                    if 1.01 < odds < 500 and prev_name:
                        jockeys.append({'name': prev_name, 'odds': odds})
                    prev_name = None
                except ValueError:
                    if current_meeting and len(line) > 2 and line[0].isupper() and not line.isupper():
                        if not any(c.isdigit() for c in line):
                            prev_name = line
            
            if current_meeting and jockeys:
                meetings.append({
                    'meeting': current_meeting, 
                    'type': 'jockey', 
                    'jockeys': jockeys, 
                    'source': 'tab',
                    'country': get_country(current_meeting)
                })
            
            print(f"[TAB] ✅ {len(meetings)} meetings")
            
        except Exception as e:
            print(f"[TAB] ❌ Error: {str(e)[:80]}")
        finally:
            if browser: await browser.close()
            if playwright: await playwright.stop()
        
        return meetings


# =====================================================
# ELITEBET - DYNAMIC
# =====================================================

class ElitebetScraper(BaseScraper):
    async def get_all_jockey_data(self):
        meetings = []
        playwright = browser = context = None
        
        try:
            playwright, browser, context = await self.get_browser()
            page = await context.new_page()
            
            print("[Elitebet] Navigating...")
            await page.goto('https://www.elitebet.com.au/racing', timeout=30000)
            await asyncio.sleep(4)
            
            jockey_tab = page.locator('text=Jockey Challenge')
            if await jockey_tab.count() > 0:
                await jockey_tab.click()
                await asyncio.sleep(4)
            else:
                return []
            
            text = await page.evaluate('document.body.innerText')
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            
            meeting_names = []
            date_pattern = re.compile(r'^\d{2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{2}$')
            skip_words = ['Racing', 'Jockey Challenge', 'Results', 'Today', 'Tomorrow',
                          'Futures', 'Join', 'Log In', 'Home', 'Sports', 'HOT Bets', 
                          'Promotions', 'Help', 'Horses', 'Greys', 'Harness']
            
            for i, line in enumerate(lines):
                if date_pattern.match(line) and i > 0:
                    prev_line = lines[i-1]
                    if prev_line and 2 < len(prev_line) < 30:
                        if prev_line not in skip_words and prev_line not in meeting_names:
                            if not any(c.isdigit() for c in prev_line):
                                meeting_names.append(prev_line)
            
            print(f"[Elitebet] Found {len(meeting_names)} meetings: {meeting_names}")
            
            for meeting_name in meeting_names:
                try:
                    meeting_elem = page.locator(f'text={meeting_name}').first
                    if await meeting_elem.count() > 0:
                        await meeting_elem.click()
                        await asyncio.sleep(3)
                        
                        text = await page.evaluate('document.body.innerText')
                        lines = [l.strip() for l in text.split('\n') if l.strip()]
                        
                        jockeys = []
                        odds_pattern = re.compile(r'^\d+\.\d{2}$')
                        
                        in_meeting = False
                        for i, line in enumerate(lines):
                            if line == meeting_name:
                                in_meeting = True
                                continue
                            
                            if in_meeting:
                                if odds_pattern.match(line):
                                    odds = float(line)
                                    if i > 0:
                                        jockey_name = lines[i - 1]
                                        if jockey_name and len(jockey_name) > 3 and 'Any Other' not in jockey_name:
                                            if not any(j['name'] == jockey_name for j in jockeys):
                                                jockeys.append({'name': jockey_name, 'odds': odds})
                        
                        if jockeys:
                            meetings.append({
                                'meeting': meeting_name.upper(),
                                'type': 'jockey',
                                'jockeys': jockeys,
                                'source': 'elitebet',
                                'country': get_country(meeting_name)
                            })
                            print(f"[Elitebet] ✅ {meeting_name} ({get_country(meeting_name)}): {len(jockeys)} jockeys")
                        
                except Exception as e:
                    print(f"[Elitebet] ⚠️ {meeting_name}: {e}")
            
            print(f"[Elitebet] ✅ {len(meetings)} meetings total")
            
        except Exception as e:
            print(f"[Elitebet] ❌ Error: {e}")
        finally:
            if browser: await browser.close()
            if playwright: await playwright.stop()
        
        return meetings


# =====================================================
# SPORTSBET - DYNAMIC
# =====================================================

class SportsbetScraper(BaseScraper):
    async def get_all_jockey_data(self):
        meetings = []
        playwright = browser = context = None
        
        try:
            playwright, browser, context = await self.get_browser()
            page = await context.new_page()
            
            print("[Sportsbet] Navigating...")
            await page.goto('https://www.sportsbet.com.au/horse-racing', timeout=30000)
            await asyncio.sleep(3)
            
            try:
                await page.click('text="Extras"', timeout=5000)
                await asyncio.sleep(2)
            except:
                pass
            
            for _ in range(5):
                await page.evaluate('window.scrollBy(0, 500)')
                await asyncio.sleep(0.3)
            
            text = await page.evaluate('document.body.innerText')
            
            pattern = r'Jockey Challenge - ([A-Za-z ]+)'
            meeting_names = re.findall(pattern, text)
            meeting_names = list(dict.fromkeys([m.strip() for m in meeting_names]))
            
            print(f"[Sportsbet] Found {len(meeting_names)} jockey meetings: {meeting_names}")
            
            for meeting in meeting_names[:10]:
                try:
                    await page.click(f'text="Jockey Challenge - {meeting}"', timeout=3000)
                    await asyncio.sleep(2)
                    
                    text = await page.evaluate('document.body.innerText')
                    lines = text.split('\n')
                    
                    jockeys = []
                    for i, line in enumerate(lines):
                        line = line.strip()
                        try:
                            odds = float(line)
                            if 1.01 < odds < 500:
                                for offset in [1, 2, 3]:
                                    if i >= offset:
                                        name = lines[i-offset].strip()
                                        if name and ' ' in name and len(name) > 4:
                                            if not any(c.isdigit() for c in name):
                                                skip = ['Jockey Challenge', 'Any Other', 'Back', 'Lay', 'Extras']
                                                if not any(s in name for s in skip):
                                                    if not any(j['name'] == name for j in jockeys):
                                                        jockeys.append({'name': name, 'odds': odds})
                                                        break
                        except:
                            pass
                    
                    if jockeys:
                        meetings.append({
                            'meeting': meeting.upper(), 
                            'type': 'jockey', 
                            'jockeys': jockeys, 
                            'source': 'sportsbet',
                            'country': get_country(meeting)
                        })
                        print(f"[Sportsbet] ✅ {meeting} ({get_country(meeting)}): {len(jockeys)} jockeys")
                    
                    await page.goto('https://www.sportsbet.com.au/horse-racing')
                    await asyncio.sleep(1)
                    try:
                        await page.click('text="Extras"', timeout=3000)
                        await asyncio.sleep(1)
                    except:
                        pass
                        
                except Exception as e:
                    print(f"[Sportsbet] ⚠️ {meeting}: {str(e)[:40]}")
            
            print(f"[Sportsbet] ✅ {len(meetings)} meetings total")
            
        except Exception as e:
            print(f"[Sportsbet] ❌ Error: {str(e)[:80]}")
        finally:
            if browser: await browser.close()
            if playwright: await playwright.stop()
        
        return meetings
    
    async def get_all_driver_data(self):
        meetings = []
        playwright = browser = context = None
        
        try:
            playwright, browser, context = await self.get_browser()
            page = await context.new_page()
            
            print("[Sportsbet] Navigating for drivers...")
            await page.goto('https://www.sportsbet.com.au/horse-racing', timeout=30000)
            await asyncio.sleep(3)
            
            try:
                await page.click('text="Extras"', timeout=5000)
                await asyncio.sleep(2)
            except:
                pass
            
            for _ in range(8):
                await page.evaluate('window.scrollBy(0, 500)')
                await asyncio.sleep(0.3)
            
            text = await page.evaluate('document.body.innerText')
            
            pattern = r'([A-Za-z ]+) Driver Challenge'
            meeting_names = re.findall(pattern, text)
            meeting_names = [m.strip() for m in meeting_names if 'Harness' not in m]
            meeting_names = list(dict.fromkeys(meeting_names))
            
            print(f"[Sportsbet] Found {len(meeting_names)} driver meetings: {meeting_names}")
            
            for meeting in meeting_names[:10]:
                try:
                    await page.click(f'text="{meeting} Driver Challenge"', timeout=3000)
                    await asyncio.sleep(2)
                    
                    text = await page.evaluate('document.body.innerText')
                    lines = text.split('\n')
                    
                    drivers = []
                    for i, line in enumerate(lines):
                        line = line.strip()
                        try:
                            odds = float(line)
                            if 1.01 < odds < 500:
                                for offset in [1, 2, 3]:
                                    if i >= offset:
                                        name = lines[i-offset].strip()
                                        if name and ' ' in name and len(name) > 4:
                                            if not any(c.isdigit() for c in name):
                                                if 'Challenge' not in name and 'Any Other' not in name:
                                                    if not any(d['name'] == name for d in drivers):
                                                        drivers.append({'name': name, 'odds': odds})
                                                        break
                        except:
                            pass
                    
                    if drivers:
                        meetings.append({
                            'meeting': meeting.upper(), 
                            'type': 'driver', 
                            'drivers': drivers, 
                            'source': 'sportsbet',
                            'country': get_country(meeting)
                        })
                        print(f"[Sportsbet] ✅ {meeting} ({get_country(meeting)}) Driver: {len(drivers)} drivers")
                        
                except:
                    pass
            
            print(f"[Sportsbet] ✅ {len(meetings)} driver meetings total")
            
        except Exception as e:
            print(f"[Sportsbet] ❌ Driver Error: {str(e)[:80]}")
        finally:
            if browser: await browser.close()
            if playwright: await playwright.stop()
        
        return meetings


# =====================================================
# POINTSBET - DYNAMIC
# =====================================================

class PointsBetScraper(BaseScraper):
    async def get_all_jockey_data(self):
        meetings = []
        playwright = browser = context = None
        
        try:
            playwright, browser, context = await self.get_browser()
            page = await context.new_page()
            
            print("[PointsBet] Navigating...")
            await page.goto('https://pointsbet.com.au/racing?search=specials', timeout=60000)
            await asyncio.sleep(5)
            
            text = await page.evaluate('document.body.innerText')
            
            meeting_names = []
            for line in text.split('\n'):
                if 'Thoroughbred Specials' in line and ' - ' in line:
                    match = re.match(r'([A-Za-z\s]+)\s*-\s*Thoroughbred', line)
                    if match:
                        name = match.group(1).strip()
                        if name and name not in meeting_names:
                            meeting_names.append(name)
            
            print(f"[PointsBet] Found {len(meeting_names)} meetings: {meeting_names}")
            
            for meeting_name in meeting_names[:10]:
                try:
                    await page.goto('https://pointsbet.com.au/racing?search=specials', timeout=60000)
                    await asyncio.sleep(3)
                    
                    await page.click(f'text={meeting_name} - Thoroughbred Specials', timeout=5000)
                    await asyncio.sleep(3)
                    
                    text = await page.evaluate('document.body.innerText')
                    lines = [l.strip() for l in text.split('\n') if l.strip()]
                    
                    jockeys = []
                    in_jockey = False
                    
                    for i, line in enumerate(lines):
                        if 'Jockey Challenge' in line:
                            in_jockey = True
                            continue
                        
                        if in_jockey:
                            if 'Trainer Challenge' in line or 'Jockey Win' in line:
                                break
                            
                            if re.match(r'^\d+\.\d{2}$', line):
                                odds = float(line)
                                if i > 0:
                                    name = lines[i-1]
                                    if name and len(name) > 2 and not re.match(r'^\d', name):
                                        if 'see all' not in name.lower():
                                            jockeys.append({'name': name, 'odds': odds})
                    
                    if jockeys:
                        meetings.append({
                            'meeting': meeting_name.upper(),
                            'type': 'jockey',
                            'jockeys': jockeys,
                            'source': 'pointsbet',
                            'country': get_country(meeting_name)
                        })
                        print(f"[PointsBet] ✅ {meeting_name} ({get_country(meeting_name)}): {len(jockeys)} jockeys")
                    
                except Exception as e:
                    print(f"[PointsBet] ⚠️ {meeting_name}: {str(e)[:40]}")
            
            print(f"[PointsBet] ✅ {len(meetings)} meetings total")
            
        except Exception as e:
            print(f"[PointsBet] ❌ Error: {str(e)[:50]}")
        finally:
            if browser: await browser.close()
            if playwright: await playwright.stop()
        
        return meetings
    
    async def get_all_driver_data(self):
        meetings = []
        playwright = browser = context = None
        
        try:
            playwright, browser, context = await self.get_browser()
            page = await context.new_page()
            
            print("[PointsBet] Navigating for drivers...")
            await page.goto('https://pointsbet.com.au/racing?search=specials', timeout=60000)
            await asyncio.sleep(5)
            
            text = await page.evaluate('document.body.innerText')
            
            meeting_names = []
            for line in text.split('\n'):
                if 'Harness Specials' in line and ' - ' in line:
                    match = re.match(r'([A-Za-z\s]+)\s*-\s*Harness', line)
                    if match:
                        name = match.group(1).strip()
                        if name and name not in meeting_names:
                            meeting_names.append(name)
            
            print(f"[PointsBet] Found {len(meeting_names)} driver meetings: {meeting_names}")
            
            for meeting_name in meeting_names[:10]:
                try:
                    await page.goto('https://pointsbet.com.au/racing?search=specials', timeout=60000)
                    await asyncio.sleep(3)
                    
                    await page.click(f'text={meeting_name} - Harness Specials', timeout=5000)
                    await asyncio.sleep(3)
                    
                    text = await page.evaluate('document.body.innerText')
                    lines = [l.strip() for l in text.split('\n') if l.strip()]
                    
                    drivers = []
                    in_driver = False
                    
                    for i, line in enumerate(lines):
                        if 'Driver Challenge' in line:
                            in_driver = True
                            continue
                        
                        if in_driver:
                            if 'Trainer Challenge' in line or 'Driver Win' in line:
                                break
                            
                            if re.match(r'^\d+\.\d{2}$', line):
                                odds = float(line)
                                if i > 0:
                                    name = lines[i-1]
                                    if name and len(name) > 2 and not re.match(r'^\d', name):
                                        if 'see all' not in name.lower():
                                            drivers.append({'name': name, 'odds': odds})
                    
                    if drivers:
                        meetings.append({
                            'meeting': meeting_name.upper(),
                            'type': 'driver',
                            'drivers': drivers,
                            'source': 'pointsbet',
                            'country': get_country(meeting_name)
                        })
                        print(f"[PointsBet] ✅ {meeting_name} ({get_country(meeting_name)}) Driver: {len(drivers)} drivers")
                    
                except Exception as e:
                    print(f"[PointsBet] ⚠️ Driver {meeting_name}: {str(e)[:40]}")
            
            print(f"[PointsBet] ✅ {len(meetings)} driver meetings total")
            
        except Exception as e:
            print(f"[PointsBet] ❌ Driver Error: {str(e)[:50]}")
        finally:
            if browser: await browser.close()
            if playwright: await playwright.stop()
        
        return meetings


# =====================================================
# 🚀 MAIN FETCH - ALL BOOKMAKERS
# =====================================================

async def fetch_all_data():
    global CACHE
    
    if CACHE['is_scraping']:
        print("⏳ Already scraping...")
        return get_cached_data()
    
    CACHE['is_scraping'] = True
    print("\n🚀 Starting FULLY DYNAMIC scrape...\n")
    
    jockey_meetings = []
    driver_meetings = []
    
    try:
        for scraper_name, scraper_class, method in [
            ('TAB', TABScraper, 'get_all_jockey_data'),
            ('Elitebet', ElitebetScraper, 'get_all_jockey_data'),
            ('Sportsbet Jockey', SportsbetScraper, 'get_all_jockey_data'),
            ('Sportsbet Driver', SportsbetScraper, 'get_all_driver_data'),
            ('TABtouch', TABtouchScraper, 'get_all_jockey_data'),
            ('Ladbrokes Jockey', LadbrokesScraper, 'get_all_jockey_data'),
            ('Ladbrokes Driver', LadbrokesScraper, 'get_all_driver_data'),
            ('PointsBet Jockey', PointsBetScraper, 'get_all_jockey_data'),
            ('PointsBet Driver', PointsBetScraper, 'get_all_driver_data'),
        ]:
            try:
                data = await getattr(scraper_class(), method)()
                if 'Driver' in scraper_name:
                    driver_meetings.extend(data)
                else:
                    jockey_meetings.extend(data)
            except Exception as e:
                print(f"{scraper_name} error: {e}")
        
        CACHE['jockey_challenges'] = jockey_meetings
        CACHE['driver_challenges'] = driver_meetings
        CACHE['last_updated'] = datetime.now().isoformat()
        
        au_j = len([m for m in jockey_meetings if m.get('country') == 'AU'])
        nz_j = len([m for m in jockey_meetings if m.get('country') == 'NZ'])
        au_d = len([m for m in driver_meetings if m.get('country') == 'AU'])
        nz_d = len([m for m in driver_meetings if m.get('country') == 'NZ'])
        
        # Auto-save to database
        try:
            save_meetings_to_db(jockey_meetings, driver_meetings)
        except Exception as e:
            print(f"💾 DB Error: {e}")
        
        print(f"\n✅ COMPLETE! Jockey: {len(jockey_meetings)} (AU:{au_j}, NZ:{nz_j}) | Driver: {len(driver_meetings)} (AU:{au_d}, NZ:{nz_d})\n")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        CACHE['is_scraping'] = False
    
    return {
        'jockey_challenges': jockey_meetings,
        'driver_challenges': driver_meetings,
        'last_updated': CACHE['last_updated']
    }

# =====================================================
# 💾 AUTO-SAVE MEETINGS TO DATABASE
# =====================================================

def save_meetings_to_db(jockey_meetings, driver_meetings):
    """Save scraped meetings to database - thread safe"""
    import threading
    import os
    
    def _save_sync():
        try:
            os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
            import django
            django.setup()
            
            from racing.models import Meeting, Participant, MeetingOdds
            from datetime import date as dt_date
            
            today = dt_date.today()
            saved_count = 0
            odds_count = 0
            
            for meeting_data in jockey_meetings + driver_meetings:
                try:
                    meeting, created = Meeting.objects.get_or_create(
                        name=meeting_data['meeting'].upper(),
                        date=today,
                        type=meeting_data.get('type', 'jockey'),
                        defaults={
                            'country': meeting_data.get('country', 'AU'),
                            'status': 'upcoming'
                        }
                    )
                    
                    participants = meeting_data.get('jockeys') or meeting_data.get('drivers') or []
                    bookmaker = meeting_data.get('source', 'unknown')
                    
                    for p in participants:
                        Participant.objects.get_or_create(meeting=meeting, name=p['name'])
                        MeetingOdds.objects.create(
                            meeting=meeting,
                            participant_name=p['name'],
                            bookmaker=bookmaker,
                            odds=p['odds']
                        )
                        odds_count += 1
                    
                    if created:
                        saved_count += 1
                except Exception as e:
                    pass
            
            print(f"💾 Saved {saved_count} new meetings, {odds_count} odds to DB")
        except Exception as e:
            print(f"💾 DB Error: {e}")
    
    # Run in separate thread to avoid async conflict
    thread = threading.Thread(target=_save_sync, daemon=True)
    thread.start()

