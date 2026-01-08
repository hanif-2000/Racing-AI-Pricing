# github_scraper.py
# GitHub Actions Scraper - Sends data to cPanel API
# Place this in root of your repo

import asyncio
import aiohttp
import re
import os
import logging
from datetime import datetime
from playwright.async_api import async_playwright
from typing import List, Dict

# =====================================================
# CONFIG
# =====================================================

API_URL = 'https://api.jockeydriverchallenge.com/api/receive-scrape/'
# API_URL = 'http://localhost:8000/api/receive-scrape/'

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

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
    
    def log(self, msg: str):
        logger.info(f"[{self.name}] {msg}")

# =====================================================
# TABTOUCH SCRAPER
# =====================================================

class TABtouchScraper(BaseScraper):
    def __init__(self):
        super().__init__()
        self.name = "TABtouch"
    
    async def scrape(self) -> List[Dict]:
        meetings = []
        playwright = browser = context = None
        try:
            playwright, browser, context = await self.get_browser()
            page = await context.new_page()
            self.log("Starting...")
            await page.goto('https://www.tabtouch.com.au/racing/jockey-challenge', timeout=self.timeout)
            await asyncio.sleep(3)
            
            for _ in range(3):
                await page.evaluate('window.scrollBy(0, 500)')
                await asyncio.sleep(0.3)
            
            lines = await self.get_text_lines(page)
            text = '\n'.join(lines)
            found = re.findall(r'([A-Za-z ]+) Jockey Challenge 3,2,1 Points', text)
            found = list(dict.fromkeys([m.strip() for m in found]))
            self.log(f"Found {len(found)} meetings")
            
            for meeting in found[:8]:
                try:
                    await page.goto('https://www.tabtouch.com.au/racing/jockey-challenge', timeout=self.timeout)
                    await asyncio.sleep(2)
                    await page.click(f'text="{meeting} Jockey Challenge 3,2,1 Points"', timeout=5000)
                    await asyncio.sleep(2)
                    lines = await self.get_text_lines(page)
                    jockeys = self._parse(lines)
                    if jockeys:
                        meetings.append({
                            'meeting': meeting.upper(), 'type': 'jockey',
                            'jockeys': jockeys, 'source': 'tabtouch', 'country': get_country(meeting)
                        })
                        self.log(f"✅ {meeting}: {len(jockeys)}")
                except Exception as e:
                    self.log(f"⚠️ {meeting}: {str(e)[:30]}")
        except Exception as e:
            self.log(f"❌ {str(e)[:50]}")
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
    
    async def scrape_jockey(self) -> List[Dict]:
        meetings = []
        playwright = browser = context = None
        try:
            playwright, browser, context = await self.get_browser()
            page = await context.new_page()
            self.log("Starting jockey...")
            await page.goto('https://www.ladbrokes.com.au/racing/extras', timeout=60000)
            await asyncio.sleep(3)
            lines = await self.get_text_lines(page)
            horse_meetings = self._find_section(lines, 'Horse Racing', 'Greyhounds')
            self.log(f"Found {len(horse_meetings)} horse meetings")
            
            for meeting in horse_meetings[:8]:
                try:
                    await page.goto('https://www.ladbrokes.com.au/racing/extras', timeout=60000)
                    await asyncio.sleep(2)
                    await page.click(f'text="{meeting}"', timeout=3000)
                    await asyncio.sleep(2)
                    text = await page.evaluate('document.body.innerText')
                    jc = f'Jockey Challenge - {meeting}'
                    if jc in text:
                        await page.click(f'text="{jc}"', timeout=3000)
                        await asyncio.sleep(2)
                        lines = await self.get_text_lines(page)
                        jockeys = self._parse_odds(lines)
                        if jockeys:
                            meetings.append({
                                'meeting': meeting.upper(), 'type': 'jockey',
                                'jockeys': jockeys, 'source': 'ladbrokes', 'country': get_country(meeting)
                            })
                            self.log(f"✅ {meeting}: {len(jockeys)}")
                except Exception as e:
                    self.log(f"⚠️ {meeting}: {str(e)[:30]}")
        except Exception as e:
            self.log(f"❌ {str(e)[:50]}")
        finally:
            if browser: await browser.close()
            if playwright: await playwright.stop()
        return meetings
    
    async def scrape_driver(self) -> List[Dict]:
        meetings = []
        playwright = browser = context = None
        try:
            playwright, browser, context = await self.get_browser()
            page = await context.new_page()
            self.log("Starting driver...")
            await page.goto('https://www.ladbrokes.com.au/racing/extras', timeout=60000)
            await asyncio.sleep(3)
            lines = await self.get_text_lines(page)
            harness = self._find_harness(lines)
            self.log(f"Found {len(harness)} harness meetings")
            
            for meeting in harness[:5]:
                try:
                    await page.goto('https://www.ladbrokes.com.au/racing/extras', timeout=60000)
                    await asyncio.sleep(2)
                    await page.click(f'text="{meeting}"', timeout=3000)
                    await asyncio.sleep(2)
                    text = await page.evaluate('document.body.innerText')
                    dc = f'Driver Challenge - {meeting}'
                    if dc in text:
                        await page.click(f'text="{dc}"', timeout=3000)
                        await asyncio.sleep(2)
                        lines = await self.get_text_lines(page)
                        drivers = self._parse_odds(lines)
                        if drivers:
                            meetings.append({
                                'meeting': meeting.upper(), 'type': 'driver',
                                'drivers': drivers, 'source': 'ladbrokes', 'country': get_country(meeting)
                            })
                            self.log(f"✅ {meeting} driver: {len(drivers)}")
                except Exception as e:
                    self.log(f"⚠️ {meeting}: {str(e)[:30]}")
        except Exception as e:
            self.log(f"❌ {str(e)[:50]}")
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
    
    def _parse_odds(self, lines):
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
# ELITEBET SCRAPER
# =====================================================

class ElitebetScraper(BaseScraper):
    def __init__(self):
        super().__init__()
        self.name = "Elitebet"
    
    async def scrape(self) -> List[Dict]:
        meetings = []
        playwright = browser = context = None
        try:
            playwright, browser, context = await self.get_browser()
            page = await context.new_page()
            self.log("Starting...")
            await page.goto('https://www.elitebet.com.au/racing', timeout=self.timeout)
            await asyncio.sleep(3)
            jt = page.locator('text=Jockey Challenge')
            if await jt.count() > 0:
                await jt.click()
                await asyncio.sleep(3)
            else:
                return []
            lines = await self.get_text_lines(page)
            names = self._find_meetings(lines)
            self.log(f"Found {len(names)} meetings")
            for name in names[:5]:
                try:
                    elem = page.locator(f'text={name}').first
                    if await elem.count() > 0:
                        await elem.click()
                        await asyncio.sleep(2)
                        lines = await self.get_text_lines(page)
                        jockeys = self._parse(lines, name)
                        if jockeys:
                            meetings.append({'meeting': name.upper(), 'type': 'jockey',
                                            'jockeys': jockeys, 'source': 'elitebet', 'country': get_country(name)})
                            self.log(f"✅ {name}: {len(jockeys)}")
                except Exception as e:
                    self.log(f"⚠️ {name}: {e}")
        except Exception as e:
            self.log(f"❌ {e}")
        finally:
            if browser: await browser.close()
            if playwright: await playwright.stop()
        return meetings
    
    def _find_meetings(self, lines):
        names = []
        dp = re.compile(r'^\d{2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{2}$')
        skip = ['Racing', 'Jockey Challenge', 'Results', 'Today', 'Tomorrow', 'Futures']
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
    
    async def scrape_jockey(self) -> List[Dict]:
        meetings = []
        playwright = browser = context = None
        try:
            playwright, browser, context = await self.get_browser()
            page = await context.new_page()
            self.log("Starting jockey...")
            await page.goto('https://pointsbet.com.au/racing?search=specials', timeout=60000)
            await asyncio.sleep(3)
            text = await page.evaluate('document.body.innerText')
            names = []
            for l in text.split('\n'):
                if 'Thoroughbred Specials' in l and ' - ' in l:
                    m = re.match(r'([A-Za-z\s]+)\s*-\s*Thoroughbred', l)
                    if m:
                        n = m.group(1).strip()
                        if n and n not in names: names.append(n)
            self.log(f"Found {len(names)} meetings")
            for name in names[:5]:
                try:
                    await page.goto('https://pointsbet.com.au/racing?search=specials', timeout=60000)
                    await asyncio.sleep(2)
                    await page.click(f'text={name} - Thoroughbred Specials', timeout=5000)
                    await asyncio.sleep(2)
                    lines = await self.get_text_lines(page)
                    jockeys = self._parse(lines, 'Jockey Challenge')
                    if jockeys:
                        meetings.append({'meeting': name.upper(), 'type': 'jockey',
                                        'jockeys': jockeys, 'source': 'pointsbet', 'country': get_country(name)})
                        self.log(f"✅ {name}: {len(jockeys)}")
                except Exception as e:
                    self.log(f"⚠️ {name}: {str(e)[:30]}")
        except Exception as e:
            self.log(f"❌ {str(e)[:50]}")
        finally:
            if browser: await browser.close()
            if playwright: await playwright.stop()
        return meetings
    
    async def scrape_driver(self) -> List[Dict]:
        meetings = []
        playwright = browser = context = None
        try:
            playwright, browser, context = await self.get_browser()
            page = await context.new_page()
            self.log("Starting driver...")
            await page.goto('https://pointsbet.com.au/racing?search=specials', timeout=60000)
            await asyncio.sleep(3)
            text = await page.evaluate('document.body.innerText')
            names = []
            for l in text.split('\n'):
                if 'Harness Specials' in l and ' - ' in l:
                    m = re.match(r'([A-Za-z\s]+)\s*-\s*Harness', l)
                    if m:
                        n = m.group(1).strip()
                        if n and n not in names: names.append(n)
            self.log(f"Found {len(names)} driver meetings")
            for name in names[:5]:
                try:
                    await page.goto('https://pointsbet.com.au/racing?search=specials', timeout=60000)
                    await asyncio.sleep(2)
                    await page.click(f'text={name} - Harness Specials', timeout=5000)
                    await asyncio.sleep(2)
                    lines = await self.get_text_lines(page)
                    drivers = self._parse(lines, 'Driver Challenge')
                    if drivers:
                        meetings.append({'meeting': name.upper(), 'type': 'driver',
                                        'drivers': drivers, 'source': 'pointsbet', 'country': get_country(name)})
                        self.log(f"✅ {name} driver: {len(drivers)}")
                except Exception as e:
                    self.log(f"⚠️ {name}: {str(e)[:30]}")
        except Exception as e:
            self.log(f"❌ {str(e)[:50]}")
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
# MAIN FUNCTIONS
# =====================================================

async def run_all_scrapers():
    """Run scrapers in parallel"""
    logger.info(f"\n🏇 Starting GitHub Actions Scraper at {datetime.now()}")
    start = datetime.now()
    
    results = await asyncio.gather(
        TABtouchScraper().scrape(),
        LadbrokesScraper().scrape_jockey(),
        LadbrokesScraper().scrape_driver(),
        ElitebetScraper().scrape(),
        PointsBetScraper().scrape_jockey(),
        PointsBetScraper().scrape_driver(),
        return_exceptions=True
    )
    
    jockey, driver = [], []
    driver_idx = {2, 5}  # Indices for driver scrapers
    
    for i, data in enumerate(results):
        if isinstance(data, Exception):
            logger.error(f"Scraper {i} failed: {data}")
            continue
        if not isinstance(data, list):
            continue
        if i in driver_idx:
            driver.extend(data)
        else:
            jockey.extend(data)
    
    elapsed = (datetime.now() - start).seconds
    logger.info(f"✅ Done in {elapsed}s! Jockey: {len(jockey)} | Driver: {len(driver)}")
    
    return {
        'jockey_challenges': jockey,
        'driver_challenges': driver,
        'last_updated': datetime.now().isoformat(),
        'total_meetings': len(jockey) + len(driver)
    }


async def send_to_api(data):
    """Send scraped data to cPanel API"""
    logger.info(f"\n📤 Sending to API: {API_URL}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                API_URL,
                json=data,
                headers={'Content-Type': 'application/json'},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"✅ API Response: {result}")
                    return True
                else:
                    text = await response.text()
                    logger.error(f"❌ API Error {response.status}: {text}")
                    return False
    except Exception as e:
        logger.error(f"❌ Failed to send: {e}")
        return False


async def main():
    """Main entry point"""
    # Run scrapers
    data = await run_all_scrapers()
    
    logger.info(f"\n📊 Results:")
    logger.info(f"   Jockey Challenges: {len(data['jockey_challenges'])}")
    logger.info(f"   Driver Challenges: {len(data['driver_challenges'])}")
    
    # Send to cPanel API
    if data['total_meetings'] > 0:
        await send_to_api(data)
    else:
        logger.warning("⚠️ No data scraped")
    
    logger.info(f"\n✅ Completed at {datetime.now()}")


if __name__ == '__main__':
    asyncio.run(main())
