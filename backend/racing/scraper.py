"""
🏇 RACING SCRAPER - PRODUCTION VERSION
- Parallel scraping (20-30 sec instead of 2-3 min)
- Smart caching with TTL
- Proper error handling
- Logging
"""

import asyncio
import re
import os
import logging
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
from typing import List, Dict, Optional

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# =====================================================
# CACHE
# =====================================================

class RacingCache:
    def __init__(self, ttl_minutes: int = 5):
        self.jockey_challenges: List[Dict] = []
        self.driver_challenges: List[Dict] = []
        self.last_updated: Optional[datetime] = None
        self.is_scraping: bool = False
        self.ttl = timedelta(minutes=ttl_minutes)
    
    def is_stale(self) -> bool:
        if not self.last_updated:
            return True
        return datetime.now() - self.last_updated > self.ttl
    
    def has_data(self) -> bool:
        return len(self.jockey_challenges) > 0 or len(self.driver_challenges) > 0
    
    def update(self, jockey: List[Dict], driver: List[Dict]):
        self.jockey_challenges = jockey
        self.driver_challenges = driver
        self.last_updated = datetime.now()
    
    def get_data(self) -> Dict:
        return {
            'jockey_challenges': self.jockey_challenges,
            'driver_challenges': self.driver_challenges,
            'last_updated': self.last_updated.isoformat() if self.last_updated else None,
            'from_cache': True
        }

CACHE = RacingCache(ttl_minutes=5)

def get_cached_data():
    return CACHE.get_data()

def has_cached_data():
    return CACHE.has_data()

def is_cache_stale():
    return CACHE.is_stale()

# =====================================================
# COUNTRY DETECTION
# =====================================================

NZ_TRACKS = [
    'TE AROHA', 'TRENTHAM', 'ELLERSLIE', 'RICCARTON', 'OTAKI',
    'HASTINGS', 'AWAPUNI', 'WANGANUI', 'ROTORUA', 'TAURANGA',
    'PUKEKOHE', 'RUAKAKA', 'MATAMATA', 'TE RAPA', 'WOODVILLE',
    'ADDINGTON', 'ALEXANDRA PARK', 'CAMBRIDGE', 'FORBURY',
    'ASCOT PARK', 'MANAWATU', 'GREYMOUTH', 'WINGATUI', 'OAMARU',
    'TIMARU', 'ASHBURTON', 'RANGIORA', 'FORBURY PARK'
]

def get_country(track_name: str) -> str:
    track = track_name.upper().strip()
    if ' NZ' in track or '-NZ' in track or track.endswith('NZ'):
        return 'NZ'
    for nz in NZ_TRACKS:
        if nz in track or track in nz:
            return 'NZ'
    return 'AU'

# =====================================================
# BASE SCRAPER
# =====================================================

class BaseScraper:
    def __init__(self):
        self.name = "Base"
        self.timeout = 30000
        self.wait_short = 1.5
        self.wait_medium = 2.5
    
    async def get_browser(self):
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox', '--disable-dev-shm-usage']
        )
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            locale='en-AU',
            timezone_id='Australia/Sydney',
        )
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return playwright, browser, context
    
    async def get_text_lines(self, page) -> List[str]:
        text = await page.evaluate('document.body.innerText')
        return [l.strip() for l in text.split('\n') if l.strip()]
    
    def log(self, msg: str, level: str = "info"):
        full = f"[{self.name}] {msg}"
        getattr(logger, level)(full)

# =====================================================
# TABTOUCH SCRAPER
# =====================================================

class TABtouchScraper(BaseScraper):
    def __init__(self):
        super().__init__()
        self.name = "TABtouch"
    
    async def get_all_jockey_data(self) -> List[Dict]:
        meetings = []
        playwright = browser = context = None
        try:
            playwright, browser, context = await self.get_browser()
            page = await context.new_page()
            self.log("Starting...")
            await page.goto('https://www.tabtouch.com.au/racing/jockey-challenge', timeout=self.timeout)
            await asyncio.sleep(self.wait_medium)
            
            for _ in range(3):
                await page.evaluate('window.scrollBy(0, 500)')
                await asyncio.sleep(0.3)
            
            lines = await self.get_text_lines(page)
            text = '\n'.join(lines)
            found = re.findall(r'([A-Za-z ]+) Jockey Challenge 3,2,1 Points', text)
            found = list(dict.fromkeys([m.strip() for m in found]))
            self.log(f"Found {len(found)} meetings")
            
            for meeting in found:
                try:
                    await page.goto('https://www.tabtouch.com.au/racing/jockey-challenge', timeout=self.timeout)
                    await asyncio.sleep(self.wait_short)
                    for _ in range(3):
                        await page.evaluate('window.scrollBy(0, 400)')
                        await asyncio.sleep(0.2)
                    await page.click(f'text="{meeting} Jockey Challenge 3,2,1 Points"', timeout=5000)
                    await asyncio.sleep(self.wait_medium)
                    lines = await self.get_text_lines(page)
                    jockeys = self._parse(lines)
                    if jockeys:
                        meetings.append({
                            'meeting': meeting.upper(), 'type': 'jockey',
                            'jockeys': jockeys, 'source': 'tabtouch', 'country': get_country(meeting)
                        })
                        self.log(f"✅ {meeting}: {len(jockeys)}")
                except Exception as e:
                    self.log(f"⚠️ {meeting}: {str(e)[:30]}", "warning")
        except Exception as e:
            self.log(f"❌ {str(e)[:50]}", "error")
        finally:
            if browser: await browser.close()
            if playwright: await playwright.stop()
        return meetings
    
    def _parse(self, lines: List[str]) -> List[Dict]:
        jockeys = []
        p1 = re.compile(r'^([A-Z][A-Z\s]+)\s+(\d{6})\s+(\d+\.\d{2})$')
        p2n = re.compile(r'^([A-Z][A-Z\s]+)\s+(\d{6})$')
        p2o = re.compile(r'^(\d+\.\d{2})$')
        i = 0
        while i < len(lines):
            m1 = p1.match(lines[i])
            if m1:
                name, odds = m1.group(1).strip(), float(m1.group(3))
                if 'ANY OTHER' not in name and 1 < odds < 500:
                    jockeys.append({'name': name.title(), 'odds': odds})
                i += 1
                continue
            m2n = p2n.match(lines[i])
            if m2n and i + 1 < len(lines):
                m2o = p2o.match(lines[i + 1])
                if m2o:
                    name, odds = m2n.group(1).strip(), float(m2o.group(1))
                    if 'ANY OTHER' not in name and 1 < odds < 500:
                        jockeys.append({'name': name.title(), 'odds': odds})
                    i += 2
                    continue
            i += 1
        return jockeys

# =====================================================
# LADBROKES SCRAPER
# =====================================================

class LadbrokesScraper(BaseScraper):
    def __init__(self):
        super().__init__()
        self.name = "Ladbrokes"
    
    async def get_all_jockey_data(self) -> List[Dict]:
        meetings = []
        playwright = browser = context = None
        try:
            playwright, browser, context = await self.get_browser()
            page = await context.new_page()
            self.log("Starting jockey...")
            await page.goto('https://www.ladbrokes.com.au/racing/extras', timeout=60000)
            await asyncio.sleep(self.wait_medium)
            lines = await self.get_text_lines(page)
            horse_meetings = self._find_section(lines, 'Horse Racing', 'Greyhounds')
            self.log(f"Found {len(horse_meetings)} horse meetings")
            
            for meeting in horse_meetings:
                try:
                    await page.goto('https://www.ladbrokes.com.au/racing/extras', timeout=60000)
                    await asyncio.sleep(self.wait_short)
                    await page.click(f'text="{meeting}"', timeout=3000)
                    await asyncio.sleep(self.wait_short)
                    text = await page.evaluate('document.body.innerText')
                    jc = f'Jockey Challenge - {meeting}'
                    if jc in text:
                        await page.click(f'text="{jc}"', timeout=3000)
                        await asyncio.sleep(self.wait_medium)
                        lines = await self.get_text_lines(page)
                        jockeys = self._parse_odds(lines)
                        if jockeys:
                            meetings.append({
                                'meeting': meeting.upper(), 'type': 'jockey',
                                'jockeys': jockeys, 'source': 'ladbrokes', 'country': get_country(meeting)
                            })
                            self.log(f"✅ {meeting}: {len(jockeys)}")
                except Exception as e:
                    self.log(f"⚠️ {meeting}: {str(e)[:30]}", "warning")
        except Exception as e:
            self.log(f"❌ {str(e)[:50]}", "error")
        finally:
            if browser: await browser.close()
            if playwright: await playwright.stop()
        return meetings
    
    async def get_all_driver_data(self) -> List[Dict]:
        meetings = []
        playwright = browser = context = None
        try:
            playwright, browser, context = await self.get_browser()
            page = await context.new_page()
            self.log("Starting driver...")
            await page.goto('https://www.ladbrokes.com.au/racing/extras', timeout=60000)
            await asyncio.sleep(self.wait_medium)
            lines = await self.get_text_lines(page)
            harness = self._find_harness(lines)
            self.log(f"Found {len(harness)} harness meetings")
            
            for meeting in harness:
                try:
                    await page.goto('https://www.ladbrokes.com.au/racing/extras', timeout=60000)
                    await asyncio.sleep(self.wait_short)
                    await page.click(f'text="{meeting}"', timeout=3000)
                    await asyncio.sleep(self.wait_short)
                    text = await page.evaluate('document.body.innerText')
                    dc = f'Driver Challenge - {meeting}'
                    if dc in text:
                        await page.click(f'text="{dc}"', timeout=3000)
                        await asyncio.sleep(self.wait_medium)
                        lines = await self.get_text_lines(page)
                        drivers = self._parse_odds(lines, True)
                        if drivers:
                            meetings.append({
                                'meeting': meeting.upper(), 'type': 'driver',
                                'drivers': drivers, 'source': 'ladbrokes', 'country': get_country(meeting)
                            })
                            self.log(f"✅ {meeting} driver: {len(drivers)}")
                except Exception as e:
                    self.log(f"⚠️ {meeting}: {str(e)[:30]}", "warning")
        except Exception as e:
            self.log(f"❌ {str(e)[:50]}", "error")
        finally:
            if browser: await browser.close()
            if playwright: await playwright.stop()
        return meetings
    
    def _find_section(self, lines, start, end):
        s_idx = e_idx = None
        for i, l in enumerate(lines):
            if l == start and i > 60: s_idx = i
            elif l == end and s_idx: e_idx = i; break
        result = []
        if s_idx and e_idx:
            for i in range(s_idx + 1, e_idx):
                if i + 1 < len(lines) and lines[i + 1] == 'keyboard_arrow_down':
                    if lines[i] and len(lines[i]) > 2 and lines[i] not in ['INTL', 'Horse Racing']:
                        result.append(lines[i])
        return result
    
    def _find_harness(self, lines):
        start = None
        for i, l in enumerate(lines):
            if l == 'Harness Racing' and i > 60: start = i; break
        result = []
        if start:
            for i in range(start + 1, min(start + 30, len(lines))):
                if i + 1 < len(lines) and lines[i + 1] == 'keyboard_arrow_down':
                    if lines[i] and len(lines[i]) > 2: result.append(lines[i])
                if '24/7' in lines[i] or 'Responsible' in lines[i]: break
        return result
    
    def _parse_odds(self, lines, is_driver=False):
        result = []
        skip = ['Challenge', 'keyboard', 'Same Meeting', 'Most Points', 'Winner', 'arrow']
        for i, l in enumerate(lines):
            if re.match(r'^\d+\.\d{2}$', l):
                odds = float(l)
                if i > 0 and 1.01 < odds < 500:
                    name = lines[i-1]
                    if name and len(name) > 3 and not re.match(r'^\d', name):
                        if not any(s.lower() in name.lower() for s in skip):
                            if not any(p['name'] == name for p in result):
                                result.append({'name': name, 'odds': odds})
        return result

# =====================================================
# TAB SCRAPER
# =====================================================

class TABScraper(BaseScraper):
    def __init__(self):
        super().__init__()
        self.name = "TAB"
    
    async def get_all_jockey_data(self) -> List[Dict]:
        meetings = []
        playwright = browser = None
        try:
            playwright = await async_playwright().start()
            user_dir = '/tmp/tab_profile'
            os.makedirs(user_dir, exist_ok=True)
            browser = await playwright.chromium.launch_persistent_context(
                user_dir, headless=False,
                args=['--disable-blink-features=AutomationControlled'],
                viewport={'width': 1920, 'height': 1080}, locale='en-AU', timezone_id='Australia/Sydney'
            )
            page = browser.pages[0] if browser.pages else await browser.new_page()
            self.log("Starting...")
            await page.goto("https://www.tab.com.au/sports/betting/Jockey%20Challenge/competitions/Jockey%20Challenge",
                          wait_until='domcontentloaded', timeout=60000)
            await asyncio.sleep(6)
            content = await page.content()
            if 'Access Denied' in content:
                self.log("❌ Access Denied", "error")
                return []
            for _ in range(3):
                await page.evaluate('window.scrollBy(0, 500)')
                await asyncio.sleep(0.3)
            text = await page.evaluate('document.body.innerText')
            if 'JOCK MstPts' not in text:
                self.log("❌ No content", "error")
                return []
            meetings = self._parse(text)
            self.log(f"✅ {len(meetings)} meetings")
        except Exception as e:
            self.log(f"❌ {str(e)[:50]}", "error")
        finally:
            if browser: await browser.close()
            if playwright: await playwright.stop()
        return meetings
    
    def _parse(self, text: str) -> List[Dict]:
        meetings = []
        current = None
        jockeys = []
        prev = None
        for line in text.split('\n'):
            line = line.strip()
            if not line: continue
            if line.startswith('JOCK MstPts '):
                rem = line.replace('JOCK MstPts ', '')
                if rem.isupper() and not any(c.isdigit() for c in rem):
                    if current and jockeys:
                        meetings.append({'meeting': current, 'type': 'jockey', 'jockeys': jockeys.copy(),
                                        'source': 'tab', 'country': get_country(current)})
                    current, jockeys, prev = rem, [], None
                    continue
            skip = ['Market', 'SUSP', 'Any Other', 'Bet Slip', 'MENU', 'AUDIO', 'Jockey Challenge', 'JOCK MstPts']
            if any(x.lower() in line.lower() for x in skip):
                prev = None
                continue
            try:
                odds = float(line)
                if 1.01 < odds < 500 and prev:
                    jockeys.append({'name': prev, 'odds': odds})
                prev = None
            except ValueError:
                if current and len(line) > 2 and line[0].isupper() and not line.isupper():
                    if not any(c.isdigit() for c in line):
                        prev = line
        if current and jockeys:
            meetings.append({'meeting': current, 'type': 'jockey', 'jockeys': jockeys,
                            'source': 'tab', 'country': get_country(current)})
        return meetings

# =====================================================
# SPORTSBET SCRAPER
# =====================================================

class SportsbetScraper(BaseScraper):
    def __init__(self):
        super().__init__()
        self.name = "Sportsbet"
    
    async def get_all_jockey_data(self) -> List[Dict]:
        meetings = []
        playwright = browser = context = None
        try:
            playwright, browser, context = await self.get_browser()
            page = await context.new_page()
            self.log("Starting jockey...")
            await page.goto('https://www.sportsbet.com.au/horse-racing', timeout=self.timeout)
            await asyncio.sleep(self.wait_short)
            try:
                await page.click('text="Extras"', timeout=5000)
                await asyncio.sleep(self.wait_short)
            except: pass
            for _ in range(3):
                await page.evaluate('window.scrollBy(0, 500)')
                await asyncio.sleep(0.2)
            text = await page.evaluate('document.body.innerText')
            found = re.findall(r'Jockey Challenge - ([A-Za-z ]+)', text)
            found = list(dict.fromkeys([m.strip() for m in found]))
            self.log(f"Found {len(found)} meetings")
            for meeting in found[:10]:
                try:
                    await page.click(f'text="Jockey Challenge - {meeting}"', timeout=3000)
                    await asyncio.sleep(self.wait_short)
                    lines = await self.get_text_lines(page)
                    jockeys = self._parse(lines)
                    if jockeys:
                        meetings.append({'meeting': meeting.upper(), 'type': 'jockey',
                                        'jockeys': jockeys, 'source': 'sportsbet', 'country': get_country(meeting)})
                        self.log(f"✅ {meeting}: {len(jockeys)}")
                    await page.goto('https://www.sportsbet.com.au/horse-racing')
                    await asyncio.sleep(0.5)
                    try:
                        await page.click('text="Extras"', timeout=3000)
                        await asyncio.sleep(0.5)
                    except: pass
                except Exception as e:
                    self.log(f"⚠️ {meeting}: {str(e)[:30]}", "warning")
        except Exception as e:
            self.log(f"❌ {str(e)[:50]}", "error")
        finally:
            if browser: await browser.close()
            if playwright: await playwright.stop()
        return meetings
    
    async def get_all_driver_data(self) -> List[Dict]:
        meetings = []
        playwright = browser = context = None
        try:
            playwright, browser, context = await self.get_browser()
            page = await context.new_page()
            self.log("Starting driver...")
            await page.goto('https://www.sportsbet.com.au/horse-racing', timeout=self.timeout)
            await asyncio.sleep(self.wait_short)
            try:
                await page.click('text="Extras"', timeout=5000)
                await asyncio.sleep(self.wait_short)
            except: pass
            for _ in range(5):
                await page.evaluate('window.scrollBy(0, 500)')
                await asyncio.sleep(0.2)
            text = await page.evaluate('document.body.innerText')
            found = re.findall(r'([A-Za-z ]+) Driver Challenge', text)
            found = [m.strip() for m in found if 'Harness' not in m]
            found = list(dict.fromkeys(found))
            self.log(f"Found {len(found)} driver meetings")
            for meeting in found[:10]:
                try:
                    await page.click(f'text="{meeting} Driver Challenge"', timeout=3000)
                    await asyncio.sleep(self.wait_short)
                    lines = await self.get_text_lines(page)
                    drivers = self._parse(lines, True)
                    if drivers:
                        meetings.append({'meeting': meeting.upper(), 'type': 'driver',
                                        'drivers': drivers, 'source': 'sportsbet', 'country': get_country(meeting)})
                        self.log(f"✅ {meeting} driver: {len(drivers)}")
                except: pass
        except Exception as e:
            self.log(f"❌ {str(e)[:50]}", "error")
        finally:
            if browser: await browser.close()
            if playwright: await playwright.stop()
        return meetings
    
    def _parse(self, lines, is_driver=False):
        result = []
        for i, l in enumerate(lines):
            try:
                odds = float(l)
                if 1.01 < odds < 500:
                    for off in [1, 2, 3]:
                        if i >= off:
                            name = lines[i - off]
                            if name and ' ' in name and len(name) > 4:
                                if not any(c.isdigit() for c in name):
                                    skip = ['Challenge', 'Any Other', 'Back', 'Lay', 'Extras']
                                    if not any(s in name for s in skip):
                                        if not any(p['name'] == name for p in result):
                                            result.append({'name': name, 'odds': odds})
                                            break
            except: pass
        return result

# =====================================================
# ELITEBET SCRAPER
# =====================================================

class ElitebetScraper(BaseScraper):
    def __init__(self):
        super().__init__()
        self.name = "Elitebet"
    
    async def get_all_jockey_data(self) -> List[Dict]:
        meetings = []
        playwright = browser = context = None
        try:
            playwright, browser, context = await self.get_browser()
            page = await context.new_page()
            self.log("Starting...")
            await page.goto('https://www.elitebet.com.au/racing', timeout=self.timeout)
            await asyncio.sleep(self.wait_medium)
            jt = page.locator('text=Jockey Challenge')
            if await jt.count() > 0:
                await jt.click()
                await asyncio.sleep(self.wait_medium)
            else:
                return []
            lines = await self.get_text_lines(page)
            names = self._find_meetings(lines)
            self.log(f"Found {len(names)} meetings")
            for name in names:
                try:
                    elem = page.locator(f'text={name}').first
                    if await elem.count() > 0:
                        await elem.click()
                        await asyncio.sleep(self.wait_short)
                        lines = await self.get_text_lines(page)
                        jockeys = self._parse(lines, name)
                        if jockeys:
                            meetings.append({'meeting': name.upper(), 'type': 'jockey',
                                            'jockeys': jockeys, 'source': 'elitebet', 'country': get_country(name)})
                            self.log(f"✅ {name}: {len(jockeys)}")
                except Exception as e:
                    self.log(f"⚠️ {name}: {e}", "warning")
        except Exception as e:
            self.log(f"❌ {e}", "error")
        finally:
            if browser: await browser.close()
            if playwright: await playwright.stop()
        return meetings
    
    def _find_meetings(self, lines):
        names = []
        dp = re.compile(r'^\d{2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{2}$')
        skip = ['Racing', 'Jockey Challenge', 'Results', 'Today', 'Tomorrow', 'Futures',
                'Join', 'Log In', 'Home', 'Sports', 'HOT Bets', 'Promotions', 'Help', 'Horses', 'Greys', 'Harness']
        for i, l in enumerate(lines):
            if dp.match(l) and i > 0:
                prev = lines[i - 1]
                if prev and 2 < len(prev) < 30 and prev not in skip and prev not in names:
                    if not any(c.isdigit() for c in prev):
                        names.append(prev)
        return names
    
    def _parse(self, lines, meeting):
        result = []
        in_m = False
        for i, l in enumerate(lines):
            if l == meeting: in_m = True; continue
            if in_m and re.match(r'^\d+\.\d{2}$', l):
                odds = float(l)
                if i > 0:
                    name = lines[i - 1]
                    if name and len(name) > 3 and 'Any Other' not in name:
                        if not any(j['name'] == name for j in result):
                            result.append({'name': name, 'odds': odds})
        return result

# =====================================================
# POINTSBET SCRAPER
# =====================================================

class PointsBetScraper(BaseScraper):
    def __init__(self):
        super().__init__()
        self.name = "PointsBet"
    
    async def get_all_jockey_data(self) -> List[Dict]:
        meetings = []
        playwright = browser = context = None
        try:
            playwright, browser, context = await self.get_browser()
            page = await context.new_page()
            self.log("Starting jockey...")
            await page.goto('https://pointsbet.com.au/racing?search=specials', timeout=60000)
            await asyncio.sleep(self.wait_medium)
            text = await page.evaluate('document.body.innerText')
            names = []
            for l in text.split('\n'):
                if 'Thoroughbred Specials' in l and ' - ' in l:
                    m = re.match(r'([A-Za-z\s]+)\s*-\s*Thoroughbred', l)
                    if m:
                        n = m.group(1).strip()
                        if n and n not in names: names.append(n)
            self.log(f"Found {len(names)} meetings")
            for name in names[:10]:
                try:
                    await page.goto('https://pointsbet.com.au/racing?search=specials', timeout=60000)
                    await asyncio.sleep(self.wait_short)
                    await page.click(f'text={name} - Thoroughbred Specials', timeout=5000)
                    await asyncio.sleep(self.wait_short)
                    lines = await self.get_text_lines(page)
                    jockeys = self._parse(lines, 'Jockey Challenge')
                    if jockeys:
                        meetings.append({'meeting': name.upper(), 'type': 'jockey',
                                        'jockeys': jockeys, 'source': 'pointsbet', 'country': get_country(name)})
                        self.log(f"✅ {name}: {len(jockeys)}")
                except Exception as e:
                    self.log(f"⚠️ {name}: {str(e)[:30]}", "warning")
        except Exception as e:
            self.log(f"❌ {str(e)[:50]}", "error")
        finally:
            if browser: await browser.close()
            if playwright: await playwright.stop()
        return meetings
    
    async def get_all_driver_data(self) -> List[Dict]:
        meetings = []
        playwright = browser = context = None
        try:
            playwright, browser, context = await self.get_browser()
            page = await context.new_page()
            self.log("Starting driver...")
            await page.goto('https://pointsbet.com.au/racing?search=specials', timeout=60000)
            await asyncio.sleep(self.wait_medium)
            text = await page.evaluate('document.body.innerText')
            names = []
            for l in text.split('\n'):
                if 'Harness Specials' in l and ' - ' in l:
                    m = re.match(r'([A-Za-z\s]+)\s*-\s*Harness', l)
                    if m:
                        n = m.group(1).strip()
                        if n and n not in names: names.append(n)
            self.log(f"Found {len(names)} driver meetings")
            for name in names[:10]:
                try:
                    await page.goto('https://pointsbet.com.au/racing?search=specials', timeout=60000)
                    await asyncio.sleep(self.wait_short)
                    await page.click(f'text={name} - Harness Specials', timeout=5000)
                    await asyncio.sleep(self.wait_short)
                    lines = await self.get_text_lines(page)
                    drivers = self._parse(lines, 'Driver Challenge')
                    if drivers:
                        meetings.append({'meeting': name.upper(), 'type': 'driver',
                                        'drivers': drivers, 'source': 'pointsbet', 'country': get_country(name)})
                        self.log(f"✅ {name} driver: {len(drivers)}")
                except Exception as e:
                    self.log(f"⚠️ {name}: {str(e)[:30]}", "warning")
        except Exception as e:
            self.log(f"❌ {str(e)[:50]}", "error")
        finally:
            if browser: await browser.close()
            if playwright: await playwright.stop()
        return meetings
    
    def _parse(self, lines, section):
        result = []
        in_s = False
        for i, l in enumerate(lines):
            if section in l: in_s = True; continue
            if in_s:
                if 'Trainer Challenge' in l or 'Win' in l: break
                if re.match(r'^\d+\.\d{2}$', l):
                    odds = float(l)
                    if i > 0:
                        name = lines[i - 1]
                        if name and len(name) > 2 and not re.match(r'^\d', name):
                            if 'see all' not in name.lower():
                                result.append({'name': name, 'odds': odds})
        return result

# =====================================================
# 🚀 PARALLEL FETCH - MAIN FUNCTION
# =====================================================

async def fetch_all_data():
    """Run all scrapers in PARALLEL - 20-30 sec instead of 2-3 min"""
    global CACHE
    
    if CACHE.is_scraping:
        logger.info("⏳ Already scraping...")
        return CACHE.get_data()
    
    CACHE.is_scraping = True
    logger.info("🚀 Starting PARALLEL scrape...")
    start = datetime.now()
    
    try:
        results = await asyncio.gather(
            TABScraper().get_all_jockey_data(),
            ElitebetScraper().get_all_jockey_data(),
            SportsbetScraper().get_all_jockey_data(),
            SportsbetScraper().get_all_driver_data(),
            TABtouchScraper().get_all_jockey_data(),
            LadbrokesScraper().get_all_jockey_data(),
            LadbrokesScraper().get_all_driver_data(),
            PointsBetScraper().get_all_jockey_data(),
            PointsBetScraper().get_all_driver_data(),
            return_exceptions=True
        )
        
        jockey, driver = [], []
        driver_idx = {3, 6, 8}
        
        for i, data in enumerate(results):
            if isinstance(data, Exception):
                logger.error(f"Scraper {i} failed: {data}")
                continue
            if not isinstance(data, list): continue
            if i in driver_idx:
                driver.extend(data)
            else:
                jockey.extend(data)
        
        CACHE.update(jockey, driver)
        elapsed = (datetime.now() - start).seconds
        logger.info(f"✅ Done in {elapsed}s! Jockey: {len(jockey)} | Driver: {len(driver)}")
        
    except Exception as e:
        logger.error(f"❌ {e}")
    finally:
        CACHE.is_scraping = False
    
    return {
        'jockey_challenges': CACHE.jockey_challenges,
        'driver_challenges': CACHE.driver_challenges,
        'last_updated': CACHE.last_updated.isoformat() if CACHE.last_updated else None
    }

def run_scraper_background():
    """Run scraper in background"""
    import threading
    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(fetch_all_data())
        loop.close()
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t