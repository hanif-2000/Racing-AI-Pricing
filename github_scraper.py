# github_scraper.py
# Racing Odds Scraper - Reliable version with retry, batching, anti-bot
# Works on both GitHub Actions and Digital Ocean

import asyncio
import aiohttp
import re
import os
import random
import logging
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
from typing import List, Dict, Optional

# =====================================================
# CONFIG
# =====================================================

API_URL = 'https://api.jockeydriverchallenge.com/api/receive-scrape/'

MAX_RETRIES = 3
RETRY_BACKOFF = [2, 4, 8]
MAX_MEETINGS_PER_SCRAPER = 12
BROWSER_TIMEOUT = 45000
NAVIGATION_TIMEOUT = 60000

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

USER_AGENTS = [
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
]

# =====================================================
# COUNTRY DETECTION
# =====================================================

NZ_TRACKS = [
    # Gallops
    'TE AROHA', 'TRENTHAM', 'ELLERSLIE', 'RICCARTON', 'OTAKI',
    'HASTINGS', 'AWAPUNI', 'WANGANUI', 'ROTORUA', 'TAURANGA',
    'PUKEKOHE', 'RUAKAKA', 'MATAMATA', 'TE RAPA', 'WOODVILLE',
    'WINGATUI',
    # Harness
    'ADDINGTON', 'ALEXANDRA PARK', 'CAMBRIDGE', 'FORBURY',
    'ASCOT PARK', 'MANAWATU', 'GREYMOUTH', 'OAMARU',
    'TIMARU', 'ASHBURTON', 'RANGIORA', 'FORBURY PARK',
    'WINTON', 'GORE', 'WYNDHAM', 'INVERCARGILL',
    'BANKS PENINSULA', 'METHVEN', 'CROMWELL', 'KAIKOURA',
    'GERALDINE', 'REEFTON', 'NELSON', 'WESTPORT',
]


def get_country(track_name: str) -> str:
    track = track_name.upper().strip()
    if ' NZ' in track or '-NZ' in track or track.endswith('NZ'):
        return 'NZ'
    for nz in NZ_TRACKS:
        if nz == track or nz in track:
            return 'NZ'
    return 'AU'


async def random_delay(min_s: float = 1.0, max_s: float = 3.0):
    await asyncio.sleep(random.uniform(min_s, max_s))


class BaseScraper:
    def __init__(self):
        self.name = "Base"
        self.playwright = None
        self.browser = None
        self.context = None

    async def start_browser(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--single-process',
            ]
        )
        ua = random.choice(USER_AGENTS)
        self.context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent=ua,
            locale='en-AU',
            timezone_id='Australia/Sydney',
        )
        await self.context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        self.log(f"Browser started (UA: ...{ua[-30:]})")

    async def close_browser(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        self.browser = None
        self.playwright = None
        self.context = None

    async def new_page(self):
        return await self.context.new_page()

    async def safe_goto(self, page, url: str, wait_selector: Optional[str] = None):
        await page.goto(url, timeout=NAVIGATION_TIMEOUT, wait_until='domcontentloaded')
        try:
            await page.wait_for_load_state('networkidle', timeout=15000)
        except PlaywrightTimeout:
            self.log("Network idle timeout - continuing anyway")
        if wait_selector:
            try:
                await page.wait_for_selector(wait_selector, timeout=10000)
            except PlaywrightTimeout:
                self.log(f"Selector '{wait_selector[:40]}' not found - continuing")

    async def safe_click(self, page, selector: str, timeout: int = 8000):
        try:
            await page.wait_for_selector(selector, timeout=timeout)
            await page.click(selector, timeout=timeout)
            await random_delay(1.0, 2.5)
            return True
        except PlaywrightTimeout:
            self.log(f"Click timeout: {selector[:50]}")
            return False

    async def get_text_lines(self, page) -> List[str]:
        text = await page.evaluate('document.body.innerText')
        return [l.strip() for l in text.split('\n') if l.strip()]

    def is_page_blocked(self, lines: List[str]) -> bool:
        if len(lines) < 5:
            return True
        block_signals = ['captcha', 'access denied', 'blocked', 'please verify', 'cloudflare']
        text_lower = ' '.join(lines[:20]).lower()
        return any(s in text_lower for s in block_signals)

    def log(self, msg: str):
        logger.info(f"[{self.name}] {msg}")

    def log_diagnostics(self, lines: List[str], context: str = ""):
        """Log page diagnostics when scraping returns 0 results"""
        self.log(f"DIAG ({context}): {len(lines)} lines on page")
        if lines:
            preview = lines[:30]
            for i, l in enumerate(preview):
                self.log(f"  line {i}: {l[:100]}")
        else:
            self.log("  (empty page)")


async def with_retry(func, retries: int = MAX_RETRIES, name: str = ""):
    for attempt in range(retries):
        try:
            result = await func()
            return result
        except Exception as e:
            backoff = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
            if attempt < retries - 1:
                logger.warning(
                    f"[{name}] Attempt {attempt + 1} failed: {str(e)[:60]} "
                    f"- retrying in {backoff}s"
                )
                await asyncio.sleep(backoff)
            else:
                logger.error(f"[{name}] All {retries} attempts failed: {str(e)[:80]}")
                return []


# =====================================================
# TABTOUCH SCRAPER
# =====================================================

class TABtouchScraper(BaseScraper):
    def __init__(self):
        super().__init__()
        self.name = "TABtouch"

    async def scrape(self) -> List[Dict]:
        async def _do_scrape():
            meetings = []
            try:
                await self.start_browser()
                page = await self.new_page()
                self.log("Starting...")

                await self.safe_goto(page, 'https://www.tabtouch.com.au/racing/jockey-challenge')
                await random_delay(1.5, 3.0)

                for _ in range(3):
                    await page.evaluate('window.scrollBy(0, 500)')
                    await random_delay(0.2, 0.5)

                lines = await self.get_text_lines(page)
                if self.is_page_blocked(lines):
                    self.log("Page appears blocked")
                    return []

                self.log(f"Page loaded: {len(lines)} lines")
                text = '\n'.join(lines)
                found = re.findall(r'([A-Za-z ]+) Jockey Challenge 3,2,1 Points', text)
                found = list(dict.fromkeys([m.strip() for m in found]))
                self.log(f"Found {len(found)} meetings")
                if not found:
                    self.log_diagnostics(lines, "no-meetings")

                for meeting in found[:MAX_MEETINGS_PER_SCRAPER]:
                    try:
                        await self.safe_goto(
                            page,
                            'https://www.tabtouch.com.au/racing/jockey-challenge'
                        )
                        await random_delay(1.0, 2.0)

                        clicked = await self.safe_click(
                            page,
                            f'text="{meeting} Jockey Challenge 3,2,1 Points"'
                        )
                        if not clicked:
                            continue

                        lines = await self.get_text_lines(page)
                        jockeys = self._parse(lines)
                        if jockeys:
                            meetings.append({
                                'meeting': meeting.upper(),
                                'type': 'jockey',
                                'jockeys': jockeys,
                                'source': 'tabtouch',
                                'country': get_country(meeting)
                            })
                            self.log(f"✅ {meeting}: {len(jockeys)} jockeys")
                        else:
                            self.log(f"⚠️ {meeting}: parsed 0 jockeys")
                    except Exception as e:
                        self.log(f"⚠️ {meeting}: {str(e)[:50]}")
                    await random_delay(1.0, 2.5)
            finally:
                await self.close_browser()
            return meetings

        return await with_retry(_do_scrape, name=self.name)

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
        async def _do_scrape():
            meetings = []
            try:
                await self.start_browser()
                page = await self.new_page()
                self.log("Starting jockey...")

                await self.safe_goto(
                    page,
                    'https://www.ladbrokes.com.au/racing/extras'
                )
                await random_delay(1.5, 3.0)

                lines = await self.get_text_lines(page)
                if self.is_page_blocked(lines):
                    self.log("Page appears blocked")
                    return []

                self.log(f"Page loaded: {len(lines)} lines")
                horse_meetings = self._find_section(lines, 'Horse Racing', 'Greyhounds')
                self.log(f"Found {len(horse_meetings)} horse meetings")
                if not horse_meetings:
                    self.log_diagnostics(lines, "jockey-no-meetings")

                for meeting in horse_meetings[:MAX_MEETINGS_PER_SCRAPER]:
                    try:
                        await self.safe_goto(
                            page,
                            'https://www.ladbrokes.com.au/racing/extras'
                        )
                        await random_delay(1.0, 2.0)

                        clicked = await self.safe_click(page, f'text="{meeting}"')
                        if not clicked:
                            continue

                        text = await page.evaluate('document.body.innerText')
                        jc = f'Jockey Challenge - {meeting}'
                        if jc in text:
                            clicked = await self.safe_click(page, f'text="{jc}"')
                            if not clicked:
                                continue
                            lines = await self.get_text_lines(page)
                            jockeys = self._parse_odds(lines)
                            if jockeys:
                                meetings.append({
                                    'meeting': meeting.upper(),
                                    'type': 'jockey',
                                    'jockeys': jockeys,
                                    'source': 'ladbrokes',
                                    'country': get_country(meeting)
                                })
                                self.log(f"✅ {meeting}: {len(jockeys)} jockeys")
                            else:
                                self.log(f"⚠️ {meeting}: parsed 0 jockeys")
                    except Exception as e:
                        self.log(f"⚠️ {meeting}: {str(e)[:50]}")
                    await random_delay(1.0, 2.5)
            finally:
                await self.close_browser()
            return meetings

        return await with_retry(_do_scrape, name=f"{self.name}-jockey")

    async def scrape_driver(self) -> List[Dict]:
        async def _do_scrape():
            meetings = []
            try:
                await self.start_browser()
                page = await self.new_page()
                self.log("Starting driver...")

                await self.safe_goto(
                    page,
                    'https://www.ladbrokes.com.au/racing/extras'
                )
                await random_delay(1.5, 3.0)

                lines = await self.get_text_lines(page)
                if self.is_page_blocked(lines):
                    self.log("Page appears blocked")
                    return []

                self.log(f"Page loaded: {len(lines)} lines")
                harness = self._find_harness(lines)
                self.log(f"Found {len(harness)} harness meetings")
                if not harness:
                    self.log_diagnostics(lines, "driver-no-meetings")

                for meeting in harness[:MAX_MEETINGS_PER_SCRAPER]:
                    try:
                        await self.safe_goto(
                            page,
                            'https://www.ladbrokes.com.au/racing/extras'
                        )
                        await random_delay(1.0, 2.0)

                        clicked = await self.safe_click(page, f'text="{meeting}"')
                        if not clicked:
                            continue

                        text = await page.evaluate('document.body.innerText')
                        dc = f'Driver Challenge - {meeting}'
                        if dc in text:
                            clicked = await self.safe_click(page, f'text="{dc}"')
                            if not clicked:
                                continue
                            lines = await self.get_text_lines(page)
                            drivers = self._parse_odds(lines)
                            if drivers:
                                meetings.append({
                                    'meeting': meeting.upper(),
                                    'type': 'driver',
                                    'drivers': drivers,
                                    'source': 'ladbrokes',
                                    'country': get_country(meeting)
                                })
                                self.log(f"✅ {meeting} driver: {len(drivers)}")
                            else:
                                self.log(f"⚠️ {meeting}: parsed 0 drivers")
                    except Exception as e:
                        self.log(f"⚠️ {meeting}: {str(e)[:50]}")
                    await random_delay(1.0, 2.5)
            finally:
                await self.close_browser()
            return meetings

        return await with_retry(_do_scrape, name=f"{self.name}-driver")

    def _find_section(self, lines, start, end):
        s_idx = e_idx = None
        for i, l in enumerate(lines):
            if l == start and i > 30:
                s_idx = i
            elif l == end and s_idx is not None:
                e_idx = i
                break
        result = []
        if s_idx is not None and e_idx is not None:
            for i in range(s_idx + 1, e_idx):
                if i + 1 < len(lines) and lines[i + 1] == 'keyboard_arrow_down':
                    if (lines[i] and len(lines[i]) > 2
                            and lines[i] not in ['INTL', 'Horse Racing']):
                        result.append(lines[i])
        return result

    def _find_harness(self, lines):
        start = None
        for i, l in enumerate(lines):
            if l == 'Harness Racing' and i > 30:
                start = i
                break
        result = []
        if start is not None:
            for i in range(start + 1, min(start + 80, len(lines))):
                if i + 1 < len(lines) and lines[i + 1] == 'keyboard_arrow_down':
                    if lines[i] and len(lines[i]) > 2:
                        result.append(lines[i])
                if '24/7' in lines[i] or 'Responsible' in lines[i] or 'Greyhounds' in lines[i]:
                    break
        return result

    def _parse_odds(self, lines):
        result = []
        skip = ['Challenge', 'keyboard', 'Same Meeting', 'Most Points', 'Winner', 'arrow']
        for i, l in enumerate(lines):
            if re.match(r'^\d+\.\d{2}$', l):
                odds = float(l)
                if i > 0 and 1.01 < odds < 500:
                    name = lines[i - 1]
                    if (name and len(name) > 3
                            and not re.match(r'^\d', name)
                            and not any(s.lower() in name.lower() for s in skip)
                            and not any(p['name'] == name for p in result)):
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
        async def _do_scrape():
            meetings = []
            try:
                await self.start_browser()
                page = await self.new_page()
                self.log("Starting...")

                await self.safe_goto(page, 'https://www.elitebet.com.au/racing')
                await random_delay(1.5, 3.0)

                lines = await self.get_text_lines(page)
                if self.is_page_blocked(lines):
                    self.log("Page appears blocked")
                    return []

                lines = await self.get_text_lines(page)
                self.log(f"Page loaded: {len(lines)} lines")

                jt = page.locator('text=Jockey Challenge')
                if await jt.count() > 0:
                    await jt.click()
                    await random_delay(1.5, 3.0)
                else:
                    self.log("No Jockey Challenge section found")
                    self.log_diagnostics(lines, "no-jc-section")
                    return []

                lines = await self.get_text_lines(page)
                names = self._find_meetings(lines)
                self.log(f"Found {len(names)} meetings")
                if not names:
                    self.log_diagnostics(lines, "no-meetings")

                for name in names[:MAX_MEETINGS_PER_SCRAPER]:
                    try:
                        elem = page.locator(f'text={name}').first
                        if await elem.count() > 0:
                            await elem.click()
                            await random_delay(1.5, 2.5)
                            lines = await self.get_text_lines(page)
                            jockeys = self._parse(lines, name)
                            if jockeys:
                                meetings.append({
                                    'meeting': name.upper(),
                                    'type': 'jockey',
                                    'jockeys': jockeys,
                                    'source': 'elitebet',
                                    'country': get_country(name)
                                })
                                self.log(f"✅ {name}: {len(jockeys)} jockeys")
                            else:
                                self.log(f"⚠️ {name}: parsed 0 jockeys")
                    except Exception as e:
                        self.log(f"⚠️ {name}: {str(e)[:50]}")
                    await random_delay(1.0, 2.5)
            finally:
                await self.close_browser()
            return meetings

        return await with_retry(_do_scrape, name=self.name)

    def _find_meetings(self, lines):
        names = []
        dp = re.compile(
            r'^\d{2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{2}$'
        )
        skip = ['Racing', 'Jockey Challenge', 'Results', 'Today', 'Tomorrow', 'Futures']
        for i, l in enumerate(lines):
            if dp.match(l) and i > 0:
                prev = lines[i - 1]
                if (prev and 2 < len(prev) < 30
                        and prev not in skip
                        and prev not in names
                        and not any(c.isdigit() for c in prev)):
                    names.append(prev)
        return names

    def _parse(self, lines, meeting):
        result = []
        in_m = False
        for i, l in enumerate(lines):
            if l == meeting:
                in_m = True
                continue
            if in_m and re.match(r'^\d+\.\d{2}$', l):
                odds = float(l)
                if i > 0:
                    name = lines[i - 1]
                    if (name and len(name) > 3
                            and 'Any Other' not in name
                            and not any(j['name'] == name for j in result)):
                        result.append({'name': name, 'odds': odds})
        return result


# =====================================================
# POINTSBET SCRAPER
# =====================================================

class PointsBetScraper(BaseScraper):
    def __init__(self):
        super().__init__()
        self.name = "PointsBet"

    async def _load_specials_page(self, page) -> str:
        """Load PointsBet racing page and navigate to specials content.
        Returns page text or empty string if blocked."""

        # Try 1: Direct specials URL
        await self.safe_goto(page, 'https://pointsbet.com.au/racing?search=specials')
        await random_delay(2.0, 4.0)

        # Scroll to trigger lazy loading
        for _ in range(3):
            await page.evaluate('window.scrollBy(0, 500)')
            await random_delay(0.3, 0.5)

        text = await page.evaluate('document.body.innerText')
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        self.log(f"Page loaded: {len(lines)} lines")

        if self.is_page_blocked(lines):
            self.log("Page appears blocked")
            self.log_diagnostics(lines, "blocked")
            return ''

        # Check if specials content loaded
        if 'Thoroughbred Specials' in text or 'Harness Specials' in text:
            self.log("Specials content found on direct URL")
            return text
        if 'Jockey Challenge' in text or 'Driver Challenge' in text:
            self.log("Challenge content found on direct URL")
            return text

        # Try 2: Click through navigation tabs to find specials
        self.log("Specials not on direct URL, trying nav clicks...")
        nav_tabs = ['Specials', 'Extras', 'TODAY', 'AU/NZ']
        for tab in nav_tabs:
            clicked = await self.safe_click(page, f'text="{tab}"', timeout=3000)
            if clicked:
                self.log(f"Clicked '{tab}', checking content...")
                await random_delay(1.5, 2.5)
                for _ in range(3):
                    await page.evaluate('window.scrollBy(0, 500)')
                    await random_delay(0.2, 0.4)
                text = await page.evaluate('document.body.innerText')
                if ('Thoroughbred Specials' in text or 'Harness Specials' in text
                        or 'Jockey Challenge' in text or 'Driver Challenge' in text):
                    self.log(f"Found specials content after clicking '{tab}'")
                    return text

        # Try 3: Different URL paths
        alt_urls = [
            'https://pointsbet.com.au/racing/horse-racing',
            'https://pointsbet.com.au/horse-racing',
        ]
        for url in alt_urls:
            try:
                await self.safe_goto(page, url)
                await random_delay(2.0, 3.0)
                for _ in range(3):
                    await page.evaluate('window.scrollBy(0, 500)')
                    await random_delay(0.2, 0.4)
                text = await page.evaluate('document.body.innerText')
                if ('Thoroughbred Specials' in text or 'Harness Specials' in text
                        or 'Jockey Challenge' in text or 'Driver Challenge' in text):
                    self.log(f"Found specials content at {url}")
                    return text
            except Exception as e:
                self.log(f"Alt URL {url} failed: {str(e)[:40]}")

        # Nothing worked - log extended diagnostics
        self.log("Could not find specials content anywhere")
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        self.log(f"DIAG (no-specials): {len(lines)} lines on final page")
        # Show more lines for debugging (30 instead of 15)
        for i, l in enumerate(lines[:30]):
            self.log(f"  line {i}: {l[:100]}")
        # Also search for any jockey/racing keywords
        for i, l in enumerate(lines):
            ll = l.lower()
            if any(kw in ll for kw in ['jockey', 'driver', 'challenge', 'special', 'harness']):
                self.log(f"  KEYWORD at line {i}: {l[:100]}")
        return text

    def _find_meetings(self, text: str, race_type: str) -> List[str]:
        """Find meeting names from page text using multiple patterns."""
        names = []

        if race_type == 'jockey':
            # Pattern 1: "Meeting - Thoroughbred Specials"
            for l in text.split('\n'):
                if 'Thoroughbred Specials' in l and ' - ' in l:
                    m = re.match(r'([A-Za-z\s]+)\s*-\s*Thoroughbred', l.strip())
                    if m:
                        n = m.group(1).strip()
                        if n and n not in names:
                            names.append(n)

            # Pattern 2: "Jockey Challenge - Meeting"
            if not names:
                found = re.findall(r'Jockey Challenge\s*[-–]\s*([A-Za-z ]+)', text)
                names = list(dict.fromkeys([m.strip() for m in found]))

            # Pattern 3: "Meeting Jockey Challenge"
            if not names:
                found = re.findall(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+Jockey Challenge', text)
                names = list(dict.fromkeys([m.strip() for m in found]))

        elif race_type == 'driver':
            # Pattern 1: "Meeting - Harness Specials"
            for l in text.split('\n'):
                if 'Harness Specials' in l and ' - ' in l:
                    m = re.match(r'([A-Za-z\s]+)\s*-\s*Harness', l.strip())
                    if m:
                        n = m.group(1).strip()
                        if n and n not in names:
                            names.append(n)

            # Pattern 2: "Driver Challenge - Meeting"
            if not names:
                found = re.findall(r'Driver Challenge\s*[-–]\s*([A-Za-z ]+)', text)
                names = list(dict.fromkeys([m.strip() for m in found]))

            # Pattern 3: "Meeting Driver Challenge"
            if not names:
                found = re.findall(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+Driver Challenge', text)
                names = list(dict.fromkeys([m.strip() for m in found]))

        return names

    async def scrape_jockey(self) -> List[Dict]:
        async def _do_scrape():
            meetings = []
            try:
                await self.start_browser()
                page = await self.new_page()
                self.log("Starting jockey...")

                text = await self._load_specials_page(page)
                if not text:
                    return []

                names = self._find_meetings(text, 'jockey')
                self.log(f"Found {len(names)} jockey meetings")

                for name in names[:MAX_MEETINGS_PER_SCRAPER]:
                    try:
                        # Navigate back to specials page
                        await self.safe_goto(
                            page,
                            'https://pointsbet.com.au/racing?search=specials'
                        )
                        await random_delay(1.0, 2.0)

                        # Try multiple click patterns
                        clicked = await self.safe_click(
                            page,
                            f'text={name} - Thoroughbred Specials'
                        )
                        if not clicked:
                            clicked = await self.safe_click(
                                page,
                                f'text="Jockey Challenge - {name}"',
                                timeout=3000
                            )
                        if not clicked:
                            clicked = await self.safe_click(
                                page,
                                f'text="{name} Jockey Challenge"',
                                timeout=3000
                            )
                        if not clicked:
                            continue

                        lines = await self.get_text_lines(page)
                        jockeys = self._parse(lines, 'Jockey Challenge')
                        if jockeys:
                            meetings.append({
                                'meeting': name.upper(),
                                'type': 'jockey',
                                'jockeys': jockeys,
                                'source': 'pointsbet',
                                'country': get_country(name)
                            })
                            self.log(f"✅ {name}: {len(jockeys)} jockeys")
                        else:
                            self.log(f"⚠️ {name}: parsed 0 jockeys")
                    except Exception as e:
                        self.log(f"⚠️ {name}: {str(e)[:50]}")
                    await random_delay(1.0, 2.5)
            finally:
                await self.close_browser()
            return meetings

        return await with_retry(_do_scrape, name=f"{self.name}-jockey")

    async def scrape_driver(self) -> List[Dict]:
        async def _do_scrape():
            meetings = []
            try:
                await self.start_browser()
                page = await self.new_page()
                self.log("Starting driver...")

                text = await self._load_specials_page(page)
                if not text:
                    return []

                names = self._find_meetings(text, 'driver')
                self.log(f"Found {len(names)} driver meetings")

                for name in names[:MAX_MEETINGS_PER_SCRAPER]:
                    try:
                        await self.safe_goto(
                            page,
                            'https://pointsbet.com.au/racing?search=specials'
                        )
                        await random_delay(1.0, 2.0)

                        clicked = await self.safe_click(
                            page,
                            f'text={name} - Harness Specials'
                        )
                        if not clicked:
                            clicked = await self.safe_click(
                                page,
                                f'text="Driver Challenge - {name}"',
                                timeout=3000
                            )
                        if not clicked:
                            clicked = await self.safe_click(
                                page,
                                f'text="{name} Driver Challenge"',
                                timeout=3000
                            )
                        if not clicked:
                            continue

                        lines = await self.get_text_lines(page)
                        drivers = self._parse(lines, 'Driver Challenge')
                        if drivers:
                            meetings.append({
                                'meeting': name.upper(),
                                'type': 'driver',
                                'drivers': drivers,
                                'source': 'pointsbet',
                                'country': get_country(name)
                            })
                            self.log(f"✅ {name} driver: {len(drivers)}")
                        else:
                            self.log(f"⚠️ {name}: parsed 0 drivers")
                    except Exception as e:
                        self.log(f"⚠️ {name}: {str(e)[:50]}")
                    await random_delay(1.0, 2.5)
            finally:
                await self.close_browser()
            return meetings

        return await with_retry(_do_scrape, name=f"{self.name}-driver")

    def _parse(self, lines, section):
        result = []
        in_s = False
        for i, l in enumerate(lines):
            if section in l:
                in_s = True
                continue
            if in_s:
                if 'Trainer Challenge' in l or 'Win' in l:
                    break
                if re.match(r'^\d+\.\d{2}$', l):
                    odds = float(l)
                    if i > 0:
                        name = lines[i - 1]
                        if (name and len(name) > 2
                                and not re.match(r'^\d', name)
                                and 'see all' not in name.lower()
                                and not any(p['name'] == name for p in result)):
                            result.append({'name': name, 'odds': odds})
        return result


# =====================================================
# SPORTSBET SCRAPER
# =====================================================

class SportsbetScraper(BaseScraper):
    def __init__(self):
        super().__init__()
        self.name = "Sportsbet"

    async def scrape_jockey(self) -> List[Dict]:
        async def _do_scrape():
            meetings = []
            try:
                await self.start_browser()
                page = await self.new_page()
                self.log("Starting jockey...")

                await self.safe_goto(page, 'https://www.sportsbet.com.au/horse-racing')
                await random_delay(1.5, 3.0)

                # Click Extras tab
                try:
                    await self.safe_click(page, 'text="Extras"', timeout=5000)
                    await random_delay(1.0, 2.0)
                except Exception:
                    self.log("No Extras tab found, trying page as-is")

                for _ in range(3):
                    await page.evaluate('window.scrollBy(0, 500)')
                    await random_delay(0.2, 0.5)

                text = await page.evaluate('document.body.innerText')
                lines = [l.strip() for l in text.split('\n') if l.strip()]

                if self.is_page_blocked(lines):
                    self.log("Page appears blocked")
                    self.log_diagnostics(lines, "jockey-blocked")
                    return []

                found = re.findall(r'Jockey Challenge - ([A-Za-z ]+)', text)
                found = list(dict.fromkeys([m.strip() for m in found]))
                self.log(f"Found {len(found)} jockey meetings")

                if not found:
                    self.log_diagnostics(lines, "jockey-no-meetings")

                for meeting in found[:MAX_MEETINGS_PER_SCRAPER]:
                    try:
                        await self.safe_goto(
                            page,
                            'https://www.sportsbet.com.au/horse-racing'
                        )
                        await random_delay(0.5, 1.0)
                        try:
                            await self.safe_click(page, 'text="Extras"', timeout=3000)
                            await random_delay(0.5, 1.0)
                        except Exception:
                            pass

                        clicked = await self.safe_click(
                            page,
                            f'text="Jockey Challenge - {meeting}"',
                            timeout=5000
                        )
                        if not clicked:
                            continue

                        lines = await self.get_text_lines(page)
                        jockeys = self._parse(lines)
                        if jockeys:
                            meetings.append({
                                'meeting': meeting.upper(),
                                'type': 'jockey',
                                'jockeys': jockeys,
                                'source': 'sportsbet',
                                'country': get_country(meeting)
                            })
                            self.log(f"✅ {meeting}: {len(jockeys)} jockeys")
                        else:
                            self.log(f"⚠️ {meeting}: parsed 0 jockeys")
                            self.log_diagnostics(lines, f"jockey-{meeting}")
                    except Exception as e:
                        self.log(f"⚠️ {meeting}: {str(e)[:50]}")
                    await random_delay(1.0, 2.5)
            finally:
                await self.close_browser()
            return meetings

        return await with_retry(_do_scrape, name=f"{self.name}-jockey")

    async def scrape_driver(self) -> List[Dict]:
        async def _do_scrape():
            meetings = []
            try:
                await self.start_browser()
                page = await self.new_page()
                self.log("Starting driver...")

                await self.safe_goto(page, 'https://www.sportsbet.com.au/horse-racing')
                await random_delay(1.5, 3.0)

                try:
                    await self.safe_click(page, 'text="Extras"', timeout=5000)
                    await random_delay(1.0, 2.0)
                except Exception:
                    self.log("No Extras tab found, trying page as-is")

                for _ in range(5):
                    await page.evaluate('window.scrollBy(0, 500)')
                    await random_delay(0.2, 0.5)

                text = await page.evaluate('document.body.innerText')
                lines = [l.strip() for l in text.split('\n') if l.strip()]

                if self.is_page_blocked(lines):
                    self.log("Page appears blocked")
                    self.log_diagnostics(lines, "driver-blocked")
                    return []

                found = re.findall(r'([A-Za-z ]+) Driver Challenge', text)
                found = [m.strip() for m in found if 'Harness' not in m]
                found = list(dict.fromkeys(found))
                self.log(f"Found {len(found)} driver meetings")

                if not found:
                    self.log_diagnostics(lines, "driver-no-meetings")

                for meeting in found[:MAX_MEETINGS_PER_SCRAPER]:
                    try:
                        clicked = await self.safe_click(
                            page,
                            f'text="{meeting} Driver Challenge"',
                            timeout=5000
                        )
                        if not clicked:
                            continue

                        lines = await self.get_text_lines(page)
                        drivers = self._parse(lines)
                        if drivers:
                            meetings.append({
                                'meeting': meeting.upper(),
                                'type': 'driver',
                                'drivers': drivers,
                                'source': 'sportsbet',
                                'country': get_country(meeting)
                            })
                            self.log(f"✅ {meeting} driver: {len(drivers)}")
                        else:
                            self.log(f"⚠️ {meeting}: parsed 0 drivers")
                    except Exception as e:
                        self.log(f"⚠️ {meeting}: {str(e)[:50]}")
                    await random_delay(1.0, 2.5)
            finally:
                await self.close_browser()
            return meetings

        return await with_retry(_do_scrape, name=f"{self.name}-driver")

    def _parse(self, lines):
        """Parse odds - name appears 1-3 lines before odds value"""
        result = []
        skip = ['Challenge', 'Any Other', 'Back', 'Lay', 'Extras', 'Driver',
                'Jockey', 'Market', 'Trainer']
        for i, l in enumerate(lines):
            if re.match(r'^\d+\.\d{2}$', l):
                odds = float(l)
                if 1.01 < odds < 500:
                    # Look back 1-3 lines for a name
                    for off in [1, 2, 3]:
                        if i >= off:
                            name = lines[i - off]
                            if (name and ' ' in name and len(name) > 4
                                    and not any(c.isdigit() for c in name)
                                    and not any(s.lower() in name.lower() for s in skip)
                                    and not any(p['name'] == name for p in result)):
                                result.append({'name': name, 'odds': odds})
                                break
        return result


# =====================================================
# MAIN FUNCTIONS
# =====================================================

async def run_batch(scrapers, batch_name: str) -> List:
    logger.info(f"🔄 Running {batch_name}: {len(scrapers)} scrapers")
    results = await asyncio.gather(*scrapers, return_exceptions=True)
    valid = []
    for i, data in enumerate(results):
        if isinstance(data, Exception):
            logger.error(f"{batch_name} scraper {i} failed: {data}")
        elif isinstance(data, list):
            valid.append(data)
        else:
            valid.append([])
    return valid


async def run_all_scrapers():
    logger.info(f"\n🏇 Starting Scraper at {datetime.now()}")
    start = datetime.now()

    # Batch 1: TABtouch + Ladbrokes jockey + Elitebet + Sportsbet jockey
    batch1_results = await run_batch([
        TABtouchScraper().scrape(),
        LadbrokesScraper().scrape_jockey(),
        ElitebetScraper().scrape(),
        SportsbetScraper().scrape_jockey(),
    ], "Batch 1")

    await asyncio.sleep(2)

    # Batch 2: Ladbrokes driver + PointsBet jockey + PointsBet driver + Sportsbet driver
    batch2_results = await run_batch([
        LadbrokesScraper().scrape_driver(),
        PointsBetScraper().scrape_jockey(),
        PointsBetScraper().scrape_driver(),
        SportsbetScraper().scrape_driver(),
    ], "Batch 2")

    jockey, driver = [], []

    # Batch 1: all jockey (indices 0,1,2,3)
    for data in batch1_results:
        jockey.extend(data)

    # Batch 2: index 0 = driver, index 1 = jockey, index 2 = driver, index 3 = driver
    if len(batch2_results) > 0:
        driver.extend(batch2_results[0])
    if len(batch2_results) > 1:
        jockey.extend(batch2_results[1])
    if len(batch2_results) > 2:
        driver.extend(batch2_results[2])
    if len(batch2_results) > 3:
        driver.extend(batch2_results[3])

    elapsed = int((datetime.now() - start).total_seconds())
    logger.info(f"✅ Done in {elapsed}s! Jockey: {len(jockey)} | Driver: {len(driver)}")

    return {
        'jockey_challenges': jockey,
        'driver_challenges': driver,
        'last_updated': datetime.now().isoformat(),
        'total_meetings': len(jockey) + len(driver)
    }


async def send_to_api(data, retries: int = 3):
    logger.info(f"\n📤 Sending to API: {API_URL}")

    for attempt in range(retries):
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
                        logger.error(f"❌ API Error {response.status}: {text[:100]}")
        except Exception as e:
            logger.error(f"❌ API attempt {attempt + 1} failed: {str(e)[:60]}")

        if attempt < retries - 1:
            backoff = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
            logger.info(f"Retrying API in {backoff}s...")
            await asyncio.sleep(backoff)

    logger.error("❌ All API attempts failed")
    return False


async def main():
    data = await run_all_scrapers()

    logger.info(f"\n📊 Results:")
    logger.info(f"   Jockey Challenges: {len(data['jockey_challenges'])}")
    logger.info(f"   Driver Challenges: {len(data['driver_challenges'])}")

    if data['total_meetings'] > 0:
        await send_to_api(data)
    else:
        logger.warning("⚠️ No data scraped - skipping API call")

    logger.info(f"\n✅ Completed at {datetime.now()}")


if __name__ == '__main__':
    asyncio.run(main())