# github_scraper.py
# Racing Odds Scraper - Reliable version with retry, batching, anti-bot
# Works on both GitHub Actions and Digital Ocean

import asyncio
import aiohttp
import re
import os
import gc
import random
import logging
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
from typing import List, Dict, Optional

# =====================================================
# CONFIG
# =====================================================

API_URL = 'https://api.jockeydriverchallenge.com/api/receive-scrape/'

MAX_RETRIES = 2
RETRY_BACKOFF = [2, 4]
MAX_MEETINGS_PER_SCRAPER = 12
BROWSER_TIMEOUT = 30000
NAVIGATION_TIMEOUT = 30000

# Detect low-memory server mode
LOW_MEMORY = os.environ.get('SCRAPER_MODE') == 'sequential'

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

    async def start_browser(self, use_firefox: bool = False):
        self.playwright = await async_playwright().start()

        # On low-memory servers, skip Firefox unless explicitly required
        if use_firefox and LOW_MEMORY:
            self.log("Low-memory mode: using Chromium instead of Firefox")
            use_firefox = False

        if use_firefox:
            try:
                self.browser = await self.playwright.firefox.launch(
                    headless=True,
                )
                # Pick a Firefox-appropriate UA (avoid Chrome UAs on Firefox)
                firefox_uas = [
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0',
                    'Mozilla/5.0 (X11; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0',
                ]
                ua = random.choice(firefox_uas)
                self.context = await self.browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent=ua,
                    locale='en-AU',
                    timezone_id='Australia/Sydney',
                )
                # Stealth for Firefox too - hide automation signals
                await self.context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['en-AU', 'en-US', 'en']
                    });
                    // Firefox-specific: override automation detection
                    if (navigator.userAgent.includes('Firefox')) {
                        Object.defineProperty(navigator, 'plugins', {
                            get: () => [1, 2, 3]
                        });
                    }
                """)
                self.log(f"Browser started [Firefox] (UA: ...{ua[-30:]})")
                return
            except Exception as e:
                self.log(f"Firefox failed: {str(e)[:60]}, falling back to Chromium")

        chromium_args = [
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox',
            '--disable-dev-shm-usage',
            '--disable-gpu',
        ]
        if LOW_MEMORY:
            chromium_args.extend([
                '--single-process',
                '--disable-extensions',
                '--disable-background-networking',
                '--disable-default-apps',
                '--disable-sync',
                '--disable-translate',
                '--no-first-run',
                '--js-flags=--max-old-space-size=128',
            ])
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=chromium_args
        )
        ua = random.choice(USER_AGENTS)
        self.context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent=ua,
            locale='en-AU',
            timezone_id='Australia/Sydney',
        )
        # Comprehensive stealth: hide automation signals
        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-AU', 'en-US', 'en']
            });
            window.chrome = { runtime: {} };
            const origQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (params) =>
                params.name === 'notifications'
                    ? Promise.resolve({ state: Notification.permission })
                    : origQuery(params);
        """)
        self.log(f"Browser started (UA: ...{ua[-30:]})")

    async def close_browser(self):
        try:
            if self.context:
                await self.context.close()
        except Exception:
            pass
        try:
            if self.browser:
                await self.browser.close()
        except Exception:
            pass
        try:
            if self.playwright:
                await self.playwright.stop()
        except Exception:
            pass
        self.browser = None
        self.playwright = None
        self.context = None
        gc.collect()

    async def new_page(self):
        return await self.context.new_page()

    async def safe_goto(self, page, url: str, wait_selector: Optional[str] = None):
        await page.goto(url, timeout=NAVIGATION_TIMEOUT, wait_until='domcontentloaded')
        try:
            await page.wait_for_load_state('networkidle', timeout=8000)
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
        if len(lines) < 3:
            return True
        text_lower = ' '.join(lines[:20]).lower()
        # Only flag as blocked for clear WAF/captcha messages
        block_signals = [
            'captcha', 'access denied', 'please verify',
            'cloudflare', 'you don\'t have permission',
            'ray id', 'error 403', 'error 1020',
        ]
        return any(s in text_lower for s in block_signals)

    def log(self, msg: str):
        logger.info(f"[{self.name}] {msg}")

    def log_diagnostics(self, lines: List[str], context: str = ""):
        """Log page diagnostics when scraping returns 0 results"""
        self.log(f"DIAG ({context}): {len(lines)} lines on page")
        if lines:
            # Show first 30 lines
            for i, l in enumerate(lines[:30]):
                self.log(f"  line {i}: {l[:120]}")
            # Show lines 30-80 (where jockey/driver data usually is)
            if len(lines) > 30:
                self.log(f"  --- lines 30-{min(len(lines), 80)} ---")
                for i in range(30, min(len(lines), 80)):
                    self.log(f"  line {i}: {lines[i][:120]}")
            # Show last 10 lines
            if len(lines) > 80:
                self.log(f"  --- last 10 lines ---")
                for i in range(max(80, len(lines) - 10), len(lines)):
                    self.log(f"  line {i}: {lines[i][:120]}")
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

    async def _scrape_challenge(self, challenge_type: str) -> List[Dict]:
        """Scrape either jockey or driver challenge from TABtouch.
        Click into each meeting from the listing page to get odds."""
        if challenge_type == 'jockey':
            urls = ['https://www.tabtouch.com.au/racing/jockey-challenge']
            label = 'Jockey Challenge'
            key = 'jockeys'
        else:
            # Driver challenge: try multiple URLs since the dedicated page
            # may redirect to generic trots listing
            urls = [
                'https://www.tabtouch.com.au/racing/driver-challenge',
                'https://www.tabtouch.com.au/racing/trots',
            ]
            label = 'Driver Challenge'
            key = 'drivers'

        async def _do_scrape():
            meetings = []
            try:
                await self.start_browser()
                page = await self.new_page()
                self.log(f"Starting {challenge_type}...")

                # Step 1: Load listing page to find meeting names
                # Try each URL until we find challenge content
                lines = []
                url = urls[0]
                for try_url in urls:
                    await self.safe_goto(page, try_url)
                    await random_delay(2.0, 4.0)
                    for _ in range(5):
                        await page.evaluate('window.scrollBy(0, 500)')
                        await random_delay(0.3, 0.5)

                    lines = await self.get_text_lines(page)
                    if self.is_page_blocked(lines):
                        self.log(f"Blocked at {try_url}")
                        continue

                    # Check if we have challenge content
                    page_text = ' '.join(lines).lower()
                    if (label.lower() in page_text
                            or '3,2,1' in page_text
                            or 'challenge' in page_text):
                        url = try_url
                        self.log(f"Found challenge content at {try_url}")
                        break

                    # For driver: if on trots page, look for DC links
                    if challenge_type == 'driver':
                        dc_links = await page.evaluate(r'''() => {
                            const results = [];
                            document.querySelectorAll('a[href]').forEach(
                                a => {
                                const href = a.href || '';
                                const text = (a.textContent || '').trim();
                                if (href.toLowerCase().includes(
                                        'driver-challenge')
                                    || text.toLowerCase().includes(
                                        'driver challenge')) {
                                    results.push(
                                        {href: href, text: text});
                                }
                            });
                            return results;
                        }''')
                        if dc_links:
                            self.log(f"Found {len(dc_links)} DC links "
                                     f"on trots page")
                            url = try_url
                            break
                    self.log(f"No challenge content at {try_url} "
                             f"({len(lines)} lines)")

                if not lines or self.is_page_blocked(lines):
                    self.log("All URLs blocked or empty")
                    return []

                # Find meeting names from listing - try multiple patterns
                patterns_to_try = [
                    re.compile(rf'([A-Za-z ]+) {label} 3,2,1 Points', re.IGNORECASE),
                    re.compile(rf'([A-Za-z ]+) {label}', re.IGNORECASE),
                    re.compile(rf'{label}\s*[-–]\s*([A-Za-z ]+)', re.IGNORECASE),
                    re.compile(rf'([A-Za-z ]+)\s*[-–]\s*{label}', re.IGNORECASE),
                ]
                meeting_names = []
                seen = set()
                for header_pattern in patterns_to_try:
                    for line in lines:
                        m = header_pattern.search(line)
                        if m:
                            name = m.group(1).strip()
                            skip_words = ['any other', 'most points', 'winner',
                                          'same meeting', 'close', 'suspended']
                            if (len(name) > 2 and name.upper() not in seen
                                    and not any(sw in name.lower() for sw in skip_words)):
                                seen.add(name.upper())
                                meeting_names.append(name)
                    if meeting_names:
                        break

                self.log(f"Found {len(meeting_names)} meetings on listing")

                # Extract meeting hrefs from listing page for direct navigation
                # Prioritize "3,2,1 Points" links over Quinella/Jockey Wins
                meeting_hrefs = {}
                try:
                    href_data = await page.evaluate(r'''() => {
                        const results = [];
                        document.querySelectorAll('a[href]').forEach(a => {
                            const text = a.textContent.trim();
                            const href = a.href;
                            if (text && href) {
                                results.push({text: text, href: href});
                            }
                        });
                        return results;
                    }''')
                    # First pass: find "3,2,1 Points" links (preferred)
                    for item in (href_data or []):
                        txt = item['text'].lower()
                        if '3,2,1' not in txt and 'points' not in txt:
                            continue
                        for mn in meeting_names:
                            if mn.lower() in txt and mn not in meeting_hrefs:
                                meeting_hrefs[mn] = item['href']
                                break
                    # Second pass: fall back to any challenge link
                    for item in (href_data or []):
                        txt = item['text'].lower()
                        if any(bad in txt for bad in [
                                'quinella', 'jockey wins', 'driver wins',
                                'wins', 'winner', 'most winner']):
                            continue  # skip wrong sub-markets
                        if not any(kw in txt for kw in [
                                'challenge', 'jockey', 'driver']):
                            continue
                        for mn in meeting_names:
                            if mn.lower() in txt and mn not in meeting_hrefs:
                                meeting_hrefs[mn] = item['href']
                                break
                    if meeting_hrefs:
                        self.log(f"  Extracted {len(meeting_hrefs)} direct URLs")
                except Exception:
                    pass

                # Log page content for debugging if no meetings found
                if not meeting_names and challenge_type == 'driver':
                    self.log(f"Driver page has {len(lines)} lines. Keywords:")
                    for i, l in enumerate(lines):
                        ll = l.lower()
                        if any(kw in ll for kw in ['driver', 'challenge', 'harness', 'trotter', 'pacer']):
                            self.log(f"  [{i}]: {l[:120]}")

                # Step 2: Navigate to each meeting to get odds
                consecutive_failures = 0
                for idx, meeting_name in enumerate(meeting_names):
                    try:
                        # Fresh page after consecutive failures
                        # (combats SPA state degradation)
                        if consecutive_failures >= 2:
                            self.log(f"  Resetting page after "
                                     f"{consecutive_failures} failures...")
                            try:
                                await page.close()
                            except Exception:
                                pass
                            page = await self.new_page()
                            consecutive_failures = 0

                        # Use direct URL if available, otherwise click
                        direct_url = meeting_hrefs.get(meeting_name)
                        if direct_url:
                            await self.safe_goto(page, direct_url)
                        else:
                            # Fall back to listing page click navigation
                            await self.safe_goto(page, url)
                            await random_delay(1.5, 2.5)
                            for _ in range(3):
                                await page.evaluate('window.scrollBy(0, 400)')
                                await random_delay(0.2, 0.4)

                            # Click on the meeting
                            clicked = False
                            click_patterns = [
                                f'{meeting_name} {label} 3,2,1 Points',
                                f'{meeting_name} {label}',
                                f'{label} - {meeting_name}',
                            ]
                            for click_text in click_patterns:
                                clicked = await self.safe_click(
                                    page, f'text="{click_text}"', timeout=3000)
                                if clicked:
                                    break
                            if not clicked:
                                try:
                                    loc = page.locator(
                                        f'text=/{re.escape(meeting_name)}.*{re.escape(label)}/i').first
                                    if await loc.count() > 0:
                                        await loc.click(timeout=3000)
                                        clicked = True
                                except Exception:
                                    pass
                            if not clicked:
                                self.log(f"⚠️ {meeting_name}: click failed")
                                continue

                        await random_delay(2.0, 3.0)

                        # Check URL first - if it contains wrong market
                        current_url = page.url.lower()
                        if any(bad in current_url for bad in [
                                'wins', 'quinella', 'winner']):
                            self.log(f"  {meeting_name}: wrong URL "
                                     f"({current_url}), skipping")
                            continue

                        # Check if we landed on wrong sub-market
                        # (Quinella or Jockey Wins instead of 3,2,1 Points)
                        check_lines = await self.get_text_lines(page)
                        page_text = ' '.join(check_lines).lower()
                        page_header = ' '.join(check_lines[:25]).lower()
                        wrong_market = (
                            'quinella' in page_header
                            or 'jockey wins' in page_header
                            or 'driver wins' in page_header
                            or 'to ride zero' in page_text
                            or 'to ride one' in page_text
                            or 'most winners' in page_text
                            or 'to drive zero' in page_text
                            or 'to drive one' in page_text
                        )
                        if wrong_market:
                            # Go back to listing and click the 3,2,1 Points link
                            self.log(f"  {meeting_name}: wrong sub-market, "
                                     f"looking for 3,2,1 Points...")
                            await self.safe_goto(page, url)
                            await random_delay(1.5, 2.5)
                            for _ in range(3):
                                await page.evaluate('window.scrollBy(0, 400)')
                                await random_delay(0.2, 0.4)
                            pts_clicked = False
                            for sel in [
                                f'text="{meeting_name} {label} 3,2,1 Points"',
                                f'text=/.*{re.escape(meeting_name)}.*3.*2.*1/i',
                            ]:
                                pts_clicked = await self.safe_click(
                                    page, sel, timeout=3000)
                                if pts_clicked:
                                    await random_delay(2.0, 3.0)
                                    break
                            if not pts_clicked:
                                self.log(f"  {meeting_name}: 3,2,1 Points "
                                         f"market not available, skipping")
                                continue

                        # Click FIXED tab to ensure fixed odds display
                        try:
                            for fixed_sel in [
                                'text="FIXED"', 'text="Fixed"',
                                'button:has-text("FIXED")',
                                '[class*="fixed" i]',
                            ]:
                                try:
                                    loc = page.locator(fixed_sel).first
                                    if await loc.count() > 0:
                                        await loc.click(timeout=2000)
                                        await random_delay(1.0, 2.0)
                                        break
                                except Exception:
                                    continue
                        except Exception:
                            pass

                        # Wait for SPA to render odds (poll up to 15s)
                        odds_pattern = re.compile(r'\d+\.\d{2}')
                        detail_lines = []
                        parsed = []
                        for attempt in range(6):
                            # Scroll to trigger lazy loading
                            for _ in range(3):
                                await page.evaluate('window.scrollBy(0, 300)')
                                await random_delay(0.2, 0.4)

                            detail_lines = await self.get_text_lines(page)

                            # Check if odds values are present on page
                            has_odds = any(odds_pattern.search(l) for l in detail_lines)
                            if has_odds:
                                parsed = self._parse(detail_lines)
                                if parsed:
                                    break

                            if attempt < 5:
                                self.log(f"  {meeting_name}: waiting for odds "
                                         f"(attempt {attempt+1}/6)...")
                                await random_delay(2.0, 3.0)

                        # Fallback 0: comprehensive DOM extraction
                        # Queries ALL elements for odds-like text,
                        # including shadow DOM, data attributes, aria
                        if not parsed and detail_lines:
                            try:
                                dom_data = await page.evaluate(r'''() => {
                                    const result = {odds: [], names: [],
                                                    rows: []};
                                    const oddsRe = /^\$?(\d+\.\d{2})$/;
                                    const nameRe = /^[A-Z][A-Z\s]{3,}$/;

                                    // Strategy 1: walk ALL elements for
                                    // odds text (deep traversal)
                                    function walk(root) {
                                        if (!root) return;
                                        const els = root.querySelectorAll
                                            ? root.querySelectorAll('*')
                                            : [];
                                        els.forEach(el => {
                                            // Check textContent
                                            const t = (el.textContent||'')
                                                .trim();
                                            const m = t.match(oddsRe);
                                            if (m && !el.children.length) {
                                                result.odds.push(
                                                    parseFloat(m[1]));
                                            }
                                            // Check data attributes
                                            for (const attr of
                                                    el.attributes || []) {
                                                if (/price|odds|win/i
                                                        .test(attr.name)) {
                                                    const v = parseFloat(
                                                        attr.value);
                                                    if (v > 1 && v < 500) {
                                                        result.odds.push(v);
                                                    }
                                                }
                                            }
                                            // Check aria-label
                                            const aria = el.getAttribute(
                                                'aria-label') || '';
                                            const am = aria.match(
                                                /(\d+\.\d{2})/);
                                            if (am) {
                                                result.odds.push(
                                                    parseFloat(am[1]));
                                            }
                                            // Traverse shadow DOM
                                            if (el.shadowRoot) {
                                                walk(el.shadowRoot);
                                            }
                                        });
                                    }
                                    walk(document.body);

                                    // Strategy 2: find table rows with
                                    // name + odds structure
                                    const rows = document.querySelectorAll(
                                        'tr, [class*="row"],'
                                        + ' [class*="selection"],'
                                        + ' [class*="runner"],'
                                        + ' [class*="competitor"]');
                                    rows.forEach(row => {
                                        const cells = row.querySelectorAll(
                                            'td, [class*="cell"],'
                                            + ' [class*="col"],'
                                            + ' span, div, button, a');
                                        let name = '', odds = 0;
                                        cells.forEach(c => {
                                            const ct = (c.textContent||'')
                                                .trim();
                                            if (nameRe.test(ct) && !name) {
                                                name = ct;
                                            }
                                            const om = ct.match(oddsRe);
                                            if (om) {
                                                odds = parseFloat(om[1]);
                                            }
                                        });
                                        if (name && odds > 1 && odds < 500
                                                && !/ANY OTHER/i.test(name)){
                                            result.rows.push(
                                                {name: name, odds: odds});
                                        }
                                    });

                                    return result;
                                }''')
                                # Prefer structured row data
                                if dom_data.get('rows'):
                                    parsed = [
                                        {'name': r['name'].title(),
                                         'odds': r['odds']}
                                        for r in dom_data['rows']]
                                    self.log(
                                        f"  {meeting_name}: found "
                                        f"{len(parsed)} via DOM rows")
                                elif dom_data.get('odds'):
                                    # Match odds to names from text lines
                                    names = []
                                    np_re = re.compile(
                                        r'^([A-Z][A-Z\s]+)\s+\d+')
                                    for ln in detail_lines:
                                        m = np_re.match(ln)
                                        if m:
                                            n = m.group(1).strip()
                                            if ('ANY OTHER' not in n
                                                    and len(n) > 3):
                                                names.append(n)
                                    valid = [o for o in dom_data['odds']
                                             if 1 < o < 500]
                                    # Deduplicate odds preserving order
                                    seen_odds = []
                                    for o in valid:
                                        if o not in seen_odds:
                                            seen_odds.append(o)
                                    valid = seen_odds
                                    if (names
                                            and len(valid) >= len(names)):
                                        parsed = [
                                            {'name': n.title(),
                                             'odds': valid[i]}
                                            for i, n in enumerate(names)]
                                        self.log(
                                            f"  {meeting_name}: matched "
                                            f"{len(parsed)} via DOM walk")
                            except Exception:
                                pass

                        # Reload fallback: if no odds found, try fresh
                        # page load (not just reload - full new page)
                        if not parsed:
                            try:
                                self.log(f"  {meeting_name}: fresh page "
                                         f"load...")
                                target_url = (direct_url
                                              or page.url)
                                try:
                                    await page.close()
                                except Exception:
                                    pass
                                page = await self.new_page()
                                await self.safe_goto(page, target_url)
                                await random_delay(3.0, 5.0)
                                # Toggle TOTE then FIXED to force re-render
                                for tab_sel in ['text="TOTE"',
                                                'text="Tote"']:
                                    try:
                                        loc = page.locator(tab_sel).first
                                        if await loc.count() > 0:
                                            await loc.click(timeout=2000)
                                            await random_delay(1.0, 2.0)
                                            break
                                    except Exception:
                                        pass
                                for tab_sel in ['text="FIXED"',
                                                'text="Fixed"',
                                                'button:has-text("FIXED")']:
                                    try:
                                        loc = page.locator(tab_sel).first
                                        if await loc.count() > 0:
                                            await loc.click(timeout=2000)
                                            await random_delay(2.0, 3.0)
                                            break
                                    except Exception:
                                        pass
                                # Scroll full page up and down to trigger
                                await page.evaluate(
                                    'window.scrollTo(0, 0)')
                                await random_delay(0.5, 1.0)
                                for _ in range(5):
                                    await page.evaluate(
                                        'window.scrollBy(0, 400)')
                                    await random_delay(0.3, 0.5)
                                detail_lines = await self.get_text_lines(
                                    page)
                                has_odds = any(odds_pattern.search(l)
                                               for l in detail_lines)
                                if has_odds:
                                    parsed = self._parse(detail_lines)
                                    if parsed:
                                        self.log(
                                            f"  {meeting_name}: found "
                                            f"{len(parsed)} after fresh "
                                            f"page")
                                # Try DOM extraction on fresh page too
                                if not parsed:
                                    try:
                                        dom_data = await page.evaluate(
                                            r'''() => {
                                            const rows = [];
                                            const oddsRe =
                                                /^\$?(\d+\.\d{2})$/;
                                            const nameRe =
                                                /^[A-Z][A-Z\s]{3,}$/;
                                            function walk(root) {
                                                if (!root) return;
                                                const els =
                                                    root.querySelectorAll
                                                    ? root.querySelectorAll(
                                                        'tr,[class*="row"]'
                                                        + ',[class*='
                                                        + '"selection"]')
                                                    : [];
                                                els.forEach(row => {
                                                    const cells =
                                                        row.querySelectorAll(
                                                        'td,span,div,'
                                                        + 'button,a');
                                                    let n='', o=0;
                                                    cells.forEach(c => {
                                                        const t =
                                                            (c.textContent
                                                            ||'').trim();
                                                        if (nameRe.test(t)
                                                            && !n) n = t;
                                                        const m =
                                                            t.match(
                                                                oddsRe);
                                                        if (m) o =
                                                            parseFloat(
                                                                m[1]);
                                                    });
                                                    if (n && o > 1
                                                        && o < 500
                                                        && !/ANY OTHER/i
                                                            .test(n))
                                                        rows.push(
                                                            {name:n,
                                                             odds:o});
                                                });
                                                const all =
                                                    root.querySelectorAll
                                                    ? root
                                                        .querySelectorAll(
                                                            '*') : [];
                                                all.forEach(el => {
                                                    if (el.shadowRoot)
                                                        walk(
                                                            el.shadowRoot);
                                                });
                                            }
                                            walk(document.body);
                                            return rows;
                                        }''')
                                        if dom_data:
                                            parsed = [
                                                {'name': r['name'].title(),
                                                 'odds': r['odds']}
                                                for r in dom_data]
                                            if parsed:
                                                self.log(
                                                    f"  {meeting_name}: "
                                                    f"found {len(parsed)}"
                                                    f" via fresh page DOM")
                                    except Exception:
                                        pass
                            except Exception:
                                pass

                        # Fallback: try textContent (captures hidden text)
                        if not parsed and detail_lines:
                            try:
                                tc = await page.evaluate(
                                    'document.body.textContent')
                                tc_lines = [l.strip() for l in
                                            tc.split('\n') if l.strip()]
                                parsed = self._parse(tc_lines)
                                if parsed:
                                    self.log(f"  {meeting_name}: found "
                                             f"{len(parsed)} via textContent")
                            except Exception:
                                pass

                        if parsed:
                            consecutive_failures = 0
                            meetings.append({
                                'meeting': meeting_name.upper(),
                                'type': challenge_type,
                                key: parsed,
                                'source': 'tabtouch',
                                'country': get_country(meeting_name)
                            })
                            self.log(f"✅ {meeting_name}: {len(parsed)} "
                                     f"{challenge_type}s")
                        else:
                            consecutive_failures += 1
                            self.log(f"⚠️ {meeting_name}: parsed 0 "
                                     f"({len(detail_lines)} lines)")
                            if len(detail_lines) > 5:
                                self.log_diagnostics(
                                    detail_lines, f"{meeting_name} detail")

                    except Exception as e:
                        consecutive_failures += 1
                        self.log(f"⚠️ {meeting_name}: {str(e)[:40]}")

            finally:
                await self.close_browser()
            return meetings

        return await with_retry(_do_scrape, name=f"{self.name}-{challenge_type}")

    async def scrape(self) -> List[Dict]:
        """Scrape jockey challenges (backward compat)."""
        return await self._scrape_challenge('jockey')

    async def scrape_driver(self) -> List[Dict]:
        """Scrape driver challenges (harness racing)."""
        return await self._scrape_challenge('driver')

    def _parse(self, lines: List[str]) -> List[Dict]:
        jockeys = []
        # Pattern 1: NAME 123456 12.34 (name + any digits + odds on one line)
        p1 = re.compile(r'^([A-Z][A-Z\s]+)\s+\d+\s+(\d+\.\d{2})$')
        # Pattern 2: NAME 123456 on one line, 12.34 on next
        p2n = re.compile(r'^([A-Z][A-Z\s]+)\s+\d+$')
        p2o = re.compile(r'^(\d+\.\d{2})$')
        # Pattern 3: Just NAME on one line, 12.34 on next (simplest)
        p3n = re.compile(r'^([A-Z][A-Z\s]{2,})$')
        skip_names = ['ANY OTHER', 'JOCKEY CHALLENGE', 'DRIVER CHALLENGE',
                      'POINTS', 'RACE', 'MEETING', 'CLOSE', 'OPEN',
                      'SUSPENDED', 'TO RIDE', 'TO DRIVE', 'WINNER',
                      'WINNERS', 'MOST', 'JOCKEY WINS', 'DRIVER WINS']
        i = 0
        while i < len(lines):
            m1 = p1.match(lines[i])
            if m1:
                name, odds = m1.group(1).strip(), float(m1.group(2))
                if not any(s in name for s in skip_names) and 1 < odds < 500:
                    jockeys.append({'name': name.title(), 'odds': odds})
                i += 1
                continue
            m2n = p2n.match(lines[i])
            if m2n and i + 1 < len(lines):
                m2o = p2o.match(lines[i + 1])
                if m2o:
                    name, odds = m2n.group(1).strip(), float(m2o.group(1))
                    if not any(s in name for s in skip_names) and 1 < odds < 500:
                        jockeys.append({'name': name.title(), 'odds': odds})
                    i += 2
                    continue
            # Pattern 3: ALL CAPS name on its own line, odds on next line
            if i + 1 < len(lines):
                m3n = p3n.match(lines[i])
                m3o = p2o.match(lines[i + 1])
                if m3n and m3o:
                    name, odds = m3n.group(1).strip(), float(m3o.group(1))
                    if (not any(s in name for s in skip_names)
                            and 1 < odds < 500 and len(name) > 3):
                        jockeys.append({'name': name.title(), 'odds': odds})
                    i += 2
                    continue
            # Pattern 4: NAME on line, selection number on next, odds after
            # e.g. "ROCHELLE MILNES" / "508818" / "3.50"
            p_digits = re.compile(r'^\d{4,}$')
            if i + 2 < len(lines):
                m4n = p3n.match(lines[i])
                if m4n and p_digits.match(lines[i + 1]):
                    m4o = p2o.match(lines[i + 2])
                    if m4o:
                        name = m4n.group(1).strip()
                        odds = float(m4o.group(1))
                        if (not any(s in name for s in skip_names)
                                and 1 < odds < 500 and len(name) > 3):
                            jockeys.append({'name': name.title(), 'odds': odds})
                        i += 3
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

    async def _load_extras_page(self, page) -> List[str]:
        """Load Ladbrokes extras page with proper SPA rendering wait."""
        # Step 1: Visit home page first to establish session + cookies
        try:
            await self.safe_goto(page, 'https://www.ladbrokes.com.au')
            await random_delay(3.0, 5.0)
            # Dismiss cookie/age modals
            for sel in ['text="Accept"', 'text="OK"', 'text="Continue"',
                        'button:has-text("Accept")', 'text="I am 18+"',
                        'button:has-text("I am")', '[aria-label="Close"]']:
                try:
                    el = page.locator(sel).first
                    if await el.count() > 0:
                        await el.click(timeout=2000)
                        await random_delay(0.5, 1.0)
                except Exception:
                    pass
            lines = await self.get_text_lines(page)
            self.log(f"Home page: {len(lines)} lines")
        except Exception:
            self.log("Home page visit failed, continuing...")

        # Step 2: Navigate to extras page
        await self.safe_goto(
            page, 'https://www.ladbrokes.com.au/racing/extras')
        await random_delay(3.0, 5.0)

        # Step 3: Wait for SPA to render content (not just skeleton)
        for attempt in range(5):
            lines = await self.get_text_lines(page)
            if len(lines) > 15:
                break
            self.log(f"SPA still loading ({len(lines)} lines), waiting...")
            await random_delay(2.0, 3.0)
            # Scroll to trigger lazy loading
            await page.evaluate('window.scrollBy(0, 500)')

        # Step 4: Scroll full page to load all lazy content
        for _ in range(6):
            await page.evaluate('window.scrollBy(0, 600)')
            await random_delay(0.4, 0.7)

        lines = await self.get_text_lines(page)
        return lines

    async def scrape_jockey(self) -> List[Dict]:
        async def _do_scrape():
            meetings = []
            try:
                await self.start_browser(use_firefox=True)
                page = await self.new_page()
                self.log("Starting jockey...")

                # === Strategy 1: Direct /racing/jockey-challenge URL ===
                # Ladbrokes now has a dedicated JC page
                jc_direct_urls = [
                    'https://www.ladbrokes.com.au/racing/jockey-challenge',
                    'https://www.neds.com.au/racing/jockey-challenge',
                ]
                for jc_url in jc_direct_urls:
                    try:
                        # Visit home page first for session
                        await self.safe_goto(
                            page, jc_url.rsplit('/racing/', 1)[0])
                        await random_delay(2.0, 4.0)
                        # Dismiss modals
                        for sel in ['text="Accept"', 'text="OK"',
                                    'text="Continue"',
                                    'button:has-text("Accept")',
                                    'text="I am 18+"',
                                    '[aria-label="Close"]']:
                            try:
                                el = page.locator(sel).first
                                if await el.count() > 0:
                                    await el.click(timeout=2000)
                                    await random_delay(0.3, 0.5)
                            except Exception:
                                pass

                        await self.safe_goto(page, jc_url)
                        await random_delay(3.0, 5.0)
                        # Wait for SPA
                        for attempt in range(5):
                            lines = await self.get_text_lines(page)
                            if len(lines) > 15:
                                break
                            await random_delay(2.0, 3.0)
                            await page.evaluate('window.scrollBy(0, 500)')
                        if self.is_page_blocked(lines):
                            self.log(f"Blocked at {jc_url}")
                            continue
                        # Scroll to load lazy content
                        for _ in range(6):
                            await page.evaluate('window.scrollBy(0, 600)')
                            await random_delay(0.4, 0.7)
                        lines = await self.get_text_lines(page)
                        page_text = ' '.join(lines).lower()
                        if 'jockey challenge' in page_text or 'jockey' in page_text:
                            self.log(f"JC page loaded at {jc_url}: "
                                     f"{len(lines)} lines")
                            # Parse meetings directly from this page
                            jc_meetings = self._find_meetings_alt(
                                lines, 'Jockey Challenge')
                            if not jc_meetings:
                                # Try section-based finding
                                jc_meetings = self._find_section(
                                    lines, 'Horse Racing', 'Greyhounds')
                            self.log(f"Direct JC page: {len(jc_meetings)} "
                                     f"meetings found")

                            # Find individual meeting links
                            jc_hrefs = await page.evaluate(r'''() => {
                                const results = [];
                                const bad = ['pre-commitment', 'responsible',
                                    'gambling', 'terms', 'privacy', 'help',
                                    'support', 'download', 'betstop',
                                    'deposit limit', 'self-exclu'];
                                document.querySelectorAll('a').forEach(a => {
                                    const href = a.href || '';
                                    const text = (a.innerText || '').trim();
                                    const lh = href.toLowerCase();
                                    const lt = text.toLowerCase();
                                    // Skip anchor-only and footer links
                                    if (lh.endsWith('#') || lh.endsWith('#/')
                                        || bad.some(b => lt.includes(b)))
                                        return;
                                    if (lh.includes('jockey-challenge')
                                        || (lt.includes('jockey challenge')
                                            && !lt.includes('horse racing')
                                            && text.length < 80)) {
                                        results.push(
                                            {href: href, text: text});
                                    }
                                });
                                return results;
                            }''')
                            self.log(f"Found {len(jc_hrefs)} JC links")

                            # Try to parse odds directly (all-in-one page)
                            all_odds = self._parse_odds(lines)
                            if all_odds and jc_meetings:
                                # If we have both names and odds on one page
                                # assume it's all from one meeting
                                if len(jc_meetings) == 1:
                                    meetings.append({
                                        'meeting': jc_meetings[0].upper(),
                                        'type': 'jockey',
                                        'jockeys': all_odds,
                                        'source': 'ladbrokes',
                                        'country': get_country(
                                            jc_meetings[0])
                                    })
                                    self.log(f"✅ {jc_meetings[0]}: "
                                             f"{len(all_odds)} jockeys")

                            # Navigate to each meeting link
                            base_url = page.url
                            for jc in jc_hrefs[:MAX_MEETINGS_PER_SCRAPER]:
                                try:
                                    href = jc['href']
                                    text = jc['text']
                                    meeting_name = None
                                    for pat in [
                                        r'Jockey Challenge\s*[-–]\s*'
                                        r'(\w[\w\s]+)',
                                        r'(\w[\w\s]+?)\s*[-–]\s*'
                                        r'Jockey Challenge',
                                    ]:
                                        m = re.search(pat, text)
                                        if m:
                                            meeting_name = m.group(1).strip()
                                            break
                                    if not meeting_name:
                                        hm = re.search(
                                            r'jockey-challenge[/-](\w+)',
                                            href.lower())
                                        if hm:
                                            meeting_name = (
                                                hm.group(1).title())
                                    if not meeting_name:
                                        meeting_name = text[:30]
                                    meeting_name = re.sub(
                                        r'keyboard_arrow\w*', '',
                                        meeting_name).strip()
                                    meeting_name = meeting_name.rstrip(' -–')
                                    if (not meeting_name
                                            or len(meeting_name) < 3):
                                        continue
                                    # Skip if already scraped
                                    if any(m['meeting'] == meeting_name.upper()
                                           for m in meetings):
                                        continue

                                    self.log(f"JC: {meeting_name} "
                                             f"({href[:60]})")
                                    await self.safe_goto(page, href)
                                    await random_delay(2.0, 3.0)
                                    for _ in range(3):
                                        det_lines = (
                                            await self.get_text_lines(page))
                                        if len(det_lines) > 15:
                                            break
                                        await random_delay(1.5, 2.5)
                                    jockeys = self._parse_odds(det_lines)
                                    if jockeys:
                                        meetings.append({
                                            'meeting': meeting_name.upper(),
                                            'type': 'jockey',
                                            'jockeys': jockeys,
                                            'source': 'ladbrokes',
                                            'country': get_country(
                                                meeting_name)
                                        })
                                        self.log(f"✅ {meeting_name}: "
                                                 f"{len(jockeys)} jockeys")
                                    else:
                                        self.log(f"⚠️ {meeting_name}: "
                                                 f"parsed 0 jockeys")
                                    await self.safe_goto(page, base_url)
                                    await random_delay(2.0, 3.0)
                                except Exception as e:
                                    self.log(f"⚠️ JC href: {str(e)[:50]}")

                            if meetings:
                                break  # Got data from direct URL
                    except Exception as e:
                        self.log(f"Direct JC URL failed: {str(e)[:50]}")

                # === Strategy 2: Extras page fallback ===
                if not meetings:
                    self.log("Direct JC URL didn't work, trying extras...")
                    lines = await self._load_extras_page(page)
                    if not self.is_page_blocked(lines) and len(lines) >= 15:
                        self.log(f"Extras page: {len(lines)} lines")
                        # Expand accordions
                        expanded = await page.evaluate(r'''() => {
                            let count = 0;
                            document.querySelectorAll(
                                '[class*="arrow"], [class*="expand"],'
                                + ' [class*="accordion"], [class*="toggle"]'
                            ).forEach(el => { el.click(); count++; });
                            const allEls = document.querySelectorAll('*');
                            allEls.forEach(el => {
                                const t = el.textContent.trim();
                                if (t === 'keyboard_arrow_down'
                                        && el.previousElementSibling) {
                                    el.previousElementSibling.click();
                                    count++;
                                }
                            });
                            return count;
                        }''')
                        self.log(f"Expanded {expanded} accordions")
                        await random_delay(3.0, 5.0)
                        for _ in range(6):
                            await page.evaluate('window.scrollBy(0, 600)')
                            await random_delay(0.4, 0.7)

                        # Find JC links
                        jc_hrefs = await page.evaluate(r'''() => {
                            const results = [];
                            document.querySelectorAll('a').forEach(a => {
                                const href = a.href || '';
                                const text = (a.innerText || '').trim();
                                const lh = href.toLowerCase();
                                const lt = text.toLowerCase();
                                if (lh.includes('jockey-challenge')
                                    || (lt.includes('jockey challenge')
                                        && !lt.includes('horse racing')
                                        && text.length < 80)) {
                                    results.push({href: href, text: text});
                                }
                            });
                            return results;
                        }''')
                        self.log(f"Extras: {len(jc_hrefs)} JC links")
                        extras_url = page.url
                        for jc in jc_hrefs[:MAX_MEETINGS_PER_SCRAPER]:
                            try:
                                href = jc['href']
                                text = jc['text']
                                meeting_name = None
                                for pat in [
                                    r'Jockey Challenge\s*[-–]\s*(\w[\w\s]+)',
                                    r'(\w[\w\s]+?)\s*[-–]\s*Jockey Challenge',
                                ]:
                                    m = re.search(pat, text)
                                    if m:
                                        meeting_name = m.group(1).strip()
                                        break
                                if not meeting_name:
                                    hm = re.search(
                                        r'jockey-challenge-(\w+)',
                                        href.lower())
                                    if hm:
                                        meeting_name = hm.group(1).title()
                                if not meeting_name:
                                    meeting_name = text[:30]
                                meeting_name = re.sub(
                                    r'keyboard_arrow\w*', '',
                                    meeting_name).strip()
                                meeting_name = meeting_name.rstrip(' -–')
                                if (not meeting_name
                                        or len(meeting_name) < 3):
                                    continue

                                self.log(f"JC: {meeting_name} ({href[:60]})")
                                await self.safe_goto(page, href)
                                await random_delay(2.0, 3.0)
                                for _ in range(3):
                                    det_lines = (
                                        await self.get_text_lines(page))
                                    if len(det_lines) > 15:
                                        break
                                    await random_delay(1.5, 2.5)
                                jockeys = self._parse_odds(det_lines)
                                if jockeys:
                                    meetings.append({
                                        'meeting': meeting_name.upper(),
                                        'type': 'jockey',
                                        'jockeys': jockeys,
                                        'source': 'ladbrokes',
                                        'country': get_country(meeting_name)
                                    })
                                    self.log(f"✅ {meeting_name}: "
                                             f"{len(jockeys)} jockeys")
                                await self.safe_goto(page, extras_url)
                                await random_delay(2.0, 3.0)
                            except Exception as e:
                                self.log(f"⚠️ JC href: {str(e)[:50]}")

                        # Fallback: text-based meeting discovery
                        if not meetings:
                            self.log("No JC hrefs, trying text fallback...")
                            full_lines = await self.get_text_lines(page)
                            horse_meetings = self._find_section(
                                full_lines, 'Horse Racing', 'Greyhounds')
                            if not horse_meetings:
                                horse_meetings = self._find_meetings_alt(
                                    full_lines, 'Jockey Challenge')
                            self.log(f"Fallback: {len(horse_meetings)}")
                            for meeting in (
                                    horse_meetings[:MAX_MEETINGS_PER_SCRAPER]):
                                try:
                                    clicked = await page.evaluate(
                                        r'''(name) => {
                                            const links =
                                                document.querySelectorAll('a');
                                            for (const a of links) {
                                                const t = (a.innerText || '')
                                                    .toLowerCase();
                                                if (t.includes(
                                                        'jockey challenge')
                                                    && t.includes(
                                                        name.toLowerCase())) {
                                                    a.click();
                                                    return true;
                                                }
                                            }
                                            return false;
                                        }''', meeting)
                                    if not clicked:
                                        continue
                                    self.log(f"JS-clicked JC: {meeting}")
                                    await random_delay(2.0, 3.0)
                                    for _ in range(3):
                                        det_lines = (
                                            await self.get_text_lines(page))
                                        if len(det_lines) > 15:
                                            break
                                        await random_delay(1.5, 2.5)
                                    jockeys = self._parse_odds(det_lines)
                                    if jockeys:
                                        meetings.append({
                                            'meeting': meeting.upper(),
                                            'type': 'jockey',
                                            'jockeys': jockeys,
                                            'source': 'ladbrokes',
                                            'country': get_country(meeting)
                                        })
                                        self.log(f"✅ {meeting}: "
                                                 f"{len(jockeys)}")
                                    await self.safe_goto(page, extras_url)
                                    await random_delay(1.5, 2.5)
                                except Exception as e:
                                    self.log(f"⚠️ {meeting}: "
                                             f"{str(e)[:40]}")
            finally:
                await self.close_browser()
            return meetings

        return await with_retry(_do_scrape, name=f"{self.name}-jockey")

    async def scrape_driver(self) -> List[Dict]:
        async def _do_scrape():
            meetings = []
            try:
                await self.start_browser(use_firefox=True)
                page = await self.new_page()
                self.log("Starting driver...")

                # === Strategy 1: Direct /racing/driver-challenge URL ===
                dc_direct_urls = [
                    'https://www.ladbrokes.com.au/racing/driver-challenge',
                    'https://www.neds.com.au/racing/driver-challenge',
                ]
                for dc_url in dc_direct_urls:
                    try:
                        await self.safe_goto(
                            page, dc_url.rsplit('/racing/', 1)[0])
                        await random_delay(2.0, 4.0)
                        for sel in ['text="Accept"', 'text="OK"',
                                    'button:has-text("Accept")',
                                    'text="I am 18+"',
                                    '[aria-label="Close"]']:
                            try:
                                el = page.locator(sel).first
                                if await el.count() > 0:
                                    await el.click(timeout=2000)
                                    await random_delay(0.3, 0.5)
                            except Exception:
                                pass
                        await self.safe_goto(page, dc_url)
                        await random_delay(3.0, 5.0)
                        for attempt in range(5):
                            lines = await self.get_text_lines(page)
                            if len(lines) > 15:
                                break
                            await random_delay(2.0, 3.0)
                            await page.evaluate('window.scrollBy(0, 500)')
                        if self.is_page_blocked(lines):
                            continue
                        for _ in range(6):
                            await page.evaluate('window.scrollBy(0, 600)')
                            await random_delay(0.4, 0.7)
                        lines = await self.get_text_lines(page)
                        page_text = ' '.join(lines).lower()
                        if ('driver challenge' in page_text
                                or 'driver' in page_text):
                            self.log(f"DC page loaded: {dc_url} "
                                     f"({len(lines)} lines)")
                            dc_hrefs = await page.evaluate(r'''() => {
                                const results = [];
                                document.querySelectorAll('a').forEach(a => {
                                    const href = a.href || '';
                                    const text = (a.innerText||'').trim();
                                    const lh = href.toLowerCase();
                                    const lt = text.toLowerCase();
                                    if (lh.includes('driver-challenge')
                                        || (lt.includes('driver challenge')
                                            && text.length < 80)
                                        || (lt.includes('driver watch')
                                            && text.length < 80)) {
                                        results.push(
                                            {href: href, text: text});
                                    }
                                });
                                return results;
                            }''')
                            self.log(f"Found {len(dc_hrefs)} DC links")
                            base_url = page.url
                            for dc in dc_hrefs[:MAX_MEETINGS_PER_SCRAPER]:
                                try:
                                    href = dc['href']
                                    text = dc['text']
                                    meeting_name = None
                                    for pat in [
                                        r'Driver Challenge\s*[-–]\s*'
                                        r'(\w[\w\s]+)',
                                        r'(\w[\w\s]+?)\s*[-–]\s*'
                                        r'Driver Challenge',
                                    ]:
                                        m = re.search(pat, text)
                                        if m:
                                            meeting_name = (
                                                m.group(1).strip())
                                            break
                                    if not meeting_name:
                                        hm = re.search(
                                            r'driver-challenge[/-](\w+)',
                                            href.lower())
                                        if hm:
                                            meeting_name = (
                                                hm.group(1).title())
                                    if not meeting_name:
                                        meeting_name = text[:30]
                                    meeting_name = re.sub(
                                        r'keyboard_arrow\w*', '',
                                        meeting_name).strip()
                                    meeting_name = meeting_name.rstrip(' -–')
                                    if (not meeting_name
                                            or len(meeting_name) < 3):
                                        continue
                                    self.log(f"DC: {meeting_name}")
                                    await self.safe_goto(page, href)
                                    await random_delay(2.0, 3.0)
                                    for _ in range(3):
                                        det_lines = (
                                            await self.get_text_lines(page))
                                        if len(det_lines) > 15:
                                            break
                                        await random_delay(1.5, 2.5)
                                    drivers = self._parse_odds(det_lines)
                                    if drivers:
                                        meetings.append({
                                            'meeting': meeting_name.upper(),
                                            'type': 'driver',
                                            'drivers': drivers,
                                            'source': 'ladbrokes',
                                            'country': get_country(
                                                meeting_name)
                                        })
                                        self.log(f"✅ {meeting_name}: "
                                                 f"{len(drivers)} drivers")
                                    await self.safe_goto(page, base_url)
                                    await random_delay(1.5, 2.5)
                                except Exception as e:
                                    self.log(f"⚠️ DC: {str(e)[:50]}")
                            if meetings:
                                break
                    except Exception as e:
                        self.log(f"Direct DC URL failed: {str(e)[:50]}")

                # === Strategy 2: Extras page fallback ===
                if not meetings:
                    self.log("Direct DC didn't work, trying extras...")
                    lines = await self._load_extras_page(page)
                    if not self.is_page_blocked(lines) and len(lines) >= 15:
                        await page.evaluate(r'''() => {
                            document.querySelectorAll(
                                '[class*="arrow"], [class*="expand"],'
                                + ' [class*="accordion"]'
                            ).forEach(el => el.click());
                            document.querySelectorAll('*').forEach(el => {
                                if (el.textContent.trim()
                                        === 'keyboard_arrow_down'
                                    && el.previousElementSibling)
                                    el.previousElementSibling.click();
                            });
                        }''')
                        await random_delay(3.0, 5.0)
                        for _ in range(6):
                            await page.evaluate('window.scrollBy(0, 600)')
                            await random_delay(0.4, 0.7)
                        dc_hrefs = await page.evaluate(r'''() => {
                            const results = [];
                            document.querySelectorAll('a').forEach(a => {
                                const href = a.href || '';
                                const text = (a.innerText || '').trim();
                                const lh = href.toLowerCase();
                                const lt = text.toLowerCase();
                                if (lh.includes('driver-challenge')
                                    || (lt.includes('driver challenge')
                                        && text.length < 80)
                                    || (lt.includes('driver watch')
                                        && text.length < 80)) {
                                    results.push({href: href, text: text});
                                }
                            });
                            return results;
                        }''')
                        self.log(f"Extras: {len(dc_hrefs)} DC links")
                        if not dc_hrefs:
                            full_lines = await self.get_text_lines(page)
                            harness = self._find_harness(full_lines)
                            if not harness:
                                harness = self._find_meetings_alt(
                                    full_lines, 'Driver Challenge')
                            self.log(f"Harness fallback: {len(harness)}")
                            for hm in harness[:MAX_MEETINGS_PER_SCRAPER]:
                                dc_hrefs.append({
                                    'href': '',
                                    'text': f'Driver Challenge - {hm}',
                                    '_click_meeting': hm
                                })
                        extras_url = page.url
                        for dc in dc_hrefs[:MAX_MEETINGS_PER_SCRAPER]:
                            try:
                                href = dc['href']
                                text = dc['text']
                                meeting_name = None
                                for pat in [
                                    r'Driver Challenge\s*[-–]\s*(\w[\w\s]+)',
                                    r'(\w[\w\s]+?)\s*[-–]\s*Driver Challenge',
                                ]:
                                    m = re.search(pat, text)
                                    if m:
                                        meeting_name = m.group(1).strip()
                                        break
                                if not meeting_name:
                                    meeting_name = text[:30]
                                meeting_name = re.sub(
                                    r'keyboard_arrow\w*', '',
                                    meeting_name).strip()
                                meeting_name = meeting_name.rstrip(' -–')
                                if (not meeting_name
                                        or len(meeting_name) < 3):
                                    continue
                                self.log(f"DC: {meeting_name}")
                                if href:
                                    await self.safe_goto(page, href)
                                elif dc.get('_click_meeting'):
                                    cn = dc['_click_meeting']
                                    clicked = await page.evaluate(
                                        r'''(name) => {
                                            const links =
                                                document.querySelectorAll('a');
                                            for (const a of links) {
                                                const t = (a.innerText||'')
                                                    .toLowerCase();
                                                if (t.includes('driver')
                                                    && t.includes(
                                                        name.toLowerCase())){
                                                    a.click();
                                                    return true;
                                                }
                                            }
                                            return false;
                                        }''', cn)
                                    if not clicked:
                                        continue
                                else:
                                    continue
                                await random_delay(2.0, 3.0)
                                for _ in range(3):
                                    det_lines = (
                                        await self.get_text_lines(page))
                                    if len(det_lines) > 15:
                                        break
                                    await random_delay(1.5, 2.5)
                                drivers = self._parse_odds(det_lines)
                                if drivers:
                                    meetings.append({
                                        'meeting': meeting_name.upper(),
                                        'type': 'driver',
                                        'drivers': drivers,
                                        'source': 'ladbrokes',
                                        'country': get_country(meeting_name)
                                    })
                                    self.log(f"✅ {meeting_name}: "
                                             f"{len(drivers)} drivers")
                                await self.safe_goto(page, extras_url)
                                await random_delay(1.5, 2.5)
                            except Exception as e:
                                self.log(f"⚠️ DC: {str(e)[:50]}")
            finally:
                await self.close_browser()
            return meetings

        return await with_retry(_do_scrape, name=f"{self.name}-driver")

    def _find_section(self, lines, start, end):
        s_idx = e_idx = None
        for i, l in enumerate(lines):
            if l == start and i > 10:
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
            if l == 'Harness Racing' and i > 10:
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

    def _find_meetings_alt(self, lines, challenge_type: str) -> List[str]:
        """Alternate meeting finder - looks for 'Jockey/Driver Challenge - MEETING' patterns."""
        meetings = []
        text = '\n'.join(lines)
        found = re.findall(
            rf'{challenge_type}\s*[-–]\s*([A-Za-z ]+)', text)
        if not found:
            found = re.findall(
                rf'([A-Za-z ]+)\s*[-–]\s*{challenge_type}', text)
        for m in found:
            name = m.strip()
            if name and len(name) > 2 and name not in meetings:
                meetings.append(name)
        return meetings

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
                # Use Firefox for WAF bypass (Elitebet = Ladbrokes sister site)
                await self.start_browser(use_firefox=True)
                page = await self.new_page()
                self.log("Starting...")

                # Visit home page first to establish session + cookies
                # Elitebet rebranded to Neds - try both domains
                home_urls = [
                    'https://www.neds.com.au',
                    'https://www.elitebet.com.au',
                ]
                home_ok = False
                for home_url in home_urls:
                    try:
                        await self.safe_goto(page, home_url)
                        await random_delay(3.0, 5.0)
                        for sel in ['text="Accept"', 'text="OK"',
                                    'text="Continue"',
                                    'button:has-text("Accept")',
                                    'text="I am 18+"',
                                    'button:has-text("I am")',
                                    '[aria-label="Close"]']:
                            try:
                                el = page.locator(sel).first
                                if await el.count() > 0:
                                    await el.click(timeout=2000)
                                    await random_delay(0.5, 1.0)
                            except Exception:
                                pass
                        home_lines = await self.get_text_lines(page)
                        self.log(f"Home page {home_url}: "
                                 f"{len(home_lines)} lines")
                        if not self.is_page_blocked(home_lines):
                            home_ok = True
                            break
                    except Exception as e:
                        self.log(f"Home failed {home_url}: {str(e)[:40]}")
                if not home_ok:
                    self.log("All home pages blocked")
                    return []

                # Try multiple URLs including neds.com.au + elitebet.com.au
                racing_urls = [
                    'https://www.neds.com.au/racing/jockey-challenge',
                    'https://www.neds.com.au/racing/extras',
                    'https://www.neds.com.au/racing/specials',
                    'https://www.neds.com.au/racing',
                    'https://www.elitebet.com.au/racing/extras',
                    'https://www.elitebet.com.au/racing/specials',
                    'https://www.elitebet.com.au/racing',
                ]
                loaded = False
                for url in racing_urls:
                    try:
                        await self.safe_goto(page, url)
                        await random_delay(3.0, 5.0)
                        # Wait for SPA content
                        for _ in range(4):
                            lines = await self.get_text_lines(page)
                            if len(lines) > 15:
                                break
                            await random_delay(2.0, 3.0)
                            await page.evaluate('window.scrollBy(0, 500)')
                        if not self.is_page_blocked(lines) and len(lines) > 10:
                            self.log(f"Loaded {url}: {len(lines)} lines")
                            loaded = True
                            break
                        self.log(f"Blocked or empty at {url} ({len(lines)} lines)")
                    except Exception:
                        pass

                if not loaded:
                    self.log("Page appears blocked")
                    lines = await self.get_text_lines(page)
                    self.log_diagnostics(lines, "all-blocked")
                    return []

                self.log(f"Page loaded: {len(lines)} lines")

                # Neds/Elitebet uses same Extras format as Ladbrokes
                # Expand all accordion sections first
                try:
                    expanded = await page.evaluate(r'''() => {
                        let count = 0;
                        document.querySelectorAll(
                            '[class*="arrow"], [class*="expand"],'
                            + ' [class*="accordion"], [class*="toggle"]'
                        ).forEach(el => { el.click(); count++; });
                        document.querySelectorAll('*').forEach(el => {
                            const t = el.textContent.trim();
                            if (t === 'keyboard_arrow_down'
                                    && el.previousElementSibling) {
                                el.previousElementSibling.click();
                                count++;
                            }
                        });
                        return count;
                    }''')
                    self.log(f"Expanded {expanded} accordions")
                    await random_delay(3.0, 5.0)
                    for _ in range(6):
                        await page.evaluate('window.scrollBy(0, 600)')
                        await random_delay(0.4, 0.7)
                except Exception:
                    pass

                lines = await self.get_text_lines(page)

                # Strategy 1: Find JC links via href/text
                jc_hrefs = await page.evaluate(r'''() => {
                    const results = [];
                    const bad = ['pre-commitment', 'responsible',
                        'gambling', 'terms', 'privacy', 'betstop'];
                    document.querySelectorAll('a').forEach(a => {
                        const href = a.href || '';
                        const text = (a.innerText || '').trim();
                        const lh = href.toLowerCase();
                        const lt = text.toLowerCase();
                        if (lh.endsWith('#') || lh.endsWith('#/')
                            || bad.some(b => lt.includes(b)))
                            return;
                        if (lh.includes('jockey-challenge')
                            || (lt.includes('jockey challenge')
                                && !lt.includes('horse racing')
                                && text.length < 80)) {
                            results.push({href: href, text: text});
                        }
                    });
                    return results;
                }''')
                self.log(f"Found {len(jc_hrefs)} JC links")

                extras_url = page.url

                # Navigate to each JC link
                for jc in jc_hrefs[:MAX_MEETINGS_PER_SCRAPER]:
                    try:
                        href = jc['href']
                        text = jc['text']
                        meeting_name = None
                        for pat in [
                            r'Jockey Challenge\s*[-–]\s*(\w[\w\s]+)',
                            r'(\w[\w\s]+?)\s*[-–]\s*Jockey Challenge',
                        ]:
                            m = re.search(pat, text)
                            if m:
                                meeting_name = m.group(1).strip()
                                break
                        if not meeting_name:
                            hm = re.search(
                                r'jockey-challenge[/-](\w+)',
                                href.lower())
                            if hm:
                                meeting_name = hm.group(1).title()
                        if not meeting_name:
                            meeting_name = text[:30]
                        meeting_name = re.sub(
                            r'keyboard_arrow\w*', '',
                            meeting_name).strip()
                        meeting_name = meeting_name.rstrip(' -–')
                        if not meeting_name or len(meeting_name) < 3:
                            continue
                        self.log(f"JC: {meeting_name} ({href[:60]})")
                        await self.safe_goto(page, href)
                        await random_delay(2.0, 3.0)
                        for _ in range(3):
                            det_lines = await self.get_text_lines(page)
                            if len(det_lines) > 15:
                                break
                            await random_delay(1.5, 2.5)
                        jockeys = self._parse_odds(det_lines)
                        if jockeys:
                            meetings.append({
                                'meeting': meeting_name.upper(),
                                'type': 'jockey',
                                'jockeys': jockeys,
                                'source': 'elitebet',
                                'country': get_country(meeting_name)
                            })
                            self.log(f"✅ {meeting_name}: "
                                     f"{len(jockeys)} jockeys")
                        await self.safe_goto(page, extras_url)
                        await random_delay(2.0, 3.0)
                    except Exception as e:
                        self.log(f"⚠️ JC: {str(e)[:50]}")

                # Strategy 2: Find meetings from section headers
                # (Extras page shows meetings under "Horse Racing")
                if not meetings:
                    names = self._find_meetings(lines)
                    if not names:
                        # Try Ladbrokes-style section finding
                        names = self._find_section_meetings(
                            lines, 'Horse Racing', 'Greyhounds')
                    self.log(f"Section meetings: {len(names)}")
                    for name in names[:MAX_MEETINGS_PER_SCRAPER]:
                        try:
                            # Click meeting name to expand
                            clicked = await page.evaluate(
                                r'''(name) => {
                                    const els = document.querySelectorAll(
                                        'a, [class*="header"],'
                                        + ' [class*="title"]');
                                    for (const el of els) {
                                        const t = (el.textContent||'')
                                            .trim();
                                        if (t === name
                                                || t.includes(name)) {
                                            el.click();
                                            return true;
                                        }
                                    }
                                    return false;
                                }''', name)
                            if not clicked:
                                clicked = await self.safe_click(
                                    page, f'text="{name}"', timeout=3000)
                            if not clicked:
                                continue
                            self.log(f"Clicked: {name}")
                            await random_delay(2.0, 3.0)
                            det_lines = await self.get_text_lines(page)
                            jockeys = self._parse_odds(det_lines)
                            if not jockeys:
                                jockeys = self._parse(det_lines, name)
                            if jockeys:
                                meetings.append({
                                    'meeting': name.upper(),
                                    'type': 'jockey',
                                    'jockeys': jockeys,
                                    'source': 'elitebet',
                                    'country': get_country(name)
                                })
                                self.log(f"✅ {name}: "
                                         f"{len(jockeys)} jockeys")
                            else:
                                self.log(f"⚠️ {name}: parsed 0")
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
        skip = ['Racing', 'Jockey Challenge', 'Results', 'Today',
                'Tomorrow', 'Futures', 'INTL', 'Horse Racing',
                'Greyhounds', 'Harness Racing', 'Extras']
        for i, l in enumerate(lines):
            if dp.match(l) and i > 0:
                prev = lines[i - 1]
                if (prev and 2 < len(prev) < 30
                        and prev not in skip
                        and prev not in names
                        and not any(c.isdigit() for c in prev)):
                    names.append(prev)
        return names

    def _find_section_meetings(self, lines, start, end):
        """Find meetings between section headers (Ladbrokes/Neds format).
        Meetings appear before 'keyboard_arrow_down' lines."""
        s_idx = e_idx = None
        for i, l in enumerate(lines):
            if l == start and i > 5:
                s_idx = i
            elif l == end and s_idx is not None:
                e_idx = i
                break
        result = []
        if s_idx is not None:
            stop = e_idx or min(s_idx + 60, len(lines))
            for i in range(s_idx + 1, stop):
                if (i + 1 < len(lines)
                        and lines[i + 1] == 'keyboard_arrow_down'):
                    name = lines[i]
                    if (name and len(name) > 2
                            and name not in ['INTL', 'Horse Racing',
                                             'Harness Racing']
                            and name not in result):
                        result.append(name)
        return result

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

    async def _load_racing_page(self, page) -> str:
        """Load PointsBet racing page and return page text."""
        await self.safe_goto(page, 'https://pointsbet.com.au/racing')
        await random_delay(2.0, 3.5)

        for _ in range(5):
            await page.evaluate('window.scrollBy(0, 800)')
            await random_delay(0.3, 0.5)

        text = await page.evaluate('document.body.innerText')
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        self.log(f"Racing page loaded: {len(lines)} lines")

        if self.is_page_blocked(lines):
            self.log("Page appears blocked")
            self.log_diagnostics(lines, "blocked")
            return ''

        return text

    async def _navigate_to_specials(self, page, race_type: str) -> str:
        """Navigate to PointsBet specials content.
        Tries: 1) Direct specials URL  2) Click Specials tab on racing page
        Returns page text if challenge content found, else empty string."""
        challenge_kw = ('Jockey Challenge' if race_type == 'jockey'
                        else 'Driver Challenge')
        specials_kw = ('Thoroughbred Specials' if race_type == 'jockey'
                       else 'Harness Specials')

        # Approach 1: Direct specials/challenge URLs
        specials_urls = [
            f'https://pointsbet.com.au/racing/{race_type}-challenge',
            'https://pointsbet.com.au/racing/specials',
            'https://pointsbet.com.au/racing?search=specials',
            'https://pointsbet.com.au/racing/extras',
            'https://pointsbet.com.au/racing?tab=specials',
        ]
        for url in specials_urls:
            try:
                await self.safe_goto(page, url)
                await random_delay(2.5, 4.0)
                for _ in range(5):
                    await page.evaluate('window.scrollBy(0, 800)')
                    await random_delay(0.3, 0.5)
                text = await page.evaluate('document.body.innerText')
                if challenge_kw in text or specials_kw in text:
                    self.log(f"Specials content found at: {url}")
                    return text
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                if not self.is_page_blocked(lines) and len(lines) > 10:
                    self.log(f"Page loaded from {url} ({len(lines)} lines) but no specials content")
            except Exception:
                pass

        # Approach 2: Load racing page and click Specials tab
        self.log("Direct specials URLs didn't work, trying Specials tab click...")
        text = await self._load_racing_page(page)
        if not text:
            return ''

        # Try clicking Specials tab with multiple selectors
        specials_selectors = [
            'text="Specials"',
            'text="SPECIALS"',
            'button:has-text("Specials")',
            'a:has-text("Specials")',
            '[role="tab"]:has-text("Specials")',
            'span:has-text("Specials")',
        ]
        for sel in specials_selectors:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.click(timeout=3000)
                    await random_delay(2.0, 3.5)
                    for _ in range(5):
                        await page.evaluate('window.scrollBy(0, 600)')
                        await random_delay(0.3, 0.5)
                    text = await page.evaluate('document.body.innerText')
                    if challenge_kw in text or specials_kw in text:
                        self.log(f"Found specials after clicking: {sel}")
                        return text
                    self.log(f"Clicked '{sel}' but no challenge content")
                    break  # Don't try more selectors if one worked
            except Exception:
                pass

        # Approach 3: Search DOM for specials-like clickable elements
        try:
            found = await page.evaluate('''() => {
                const els = document.querySelectorAll(
                    'a, button, [role="tab"], div[class*="tab"], span');
                for (const el of els) {
                    const t = (el.textContent || '').trim().toLowerCase();
                    if (t === 'specials' || t === 'racing specials') {
                        el.click();
                        return t;
                    }
                }
                return null;
            }''')
            if found:
                self.log(f"DOM click on '{found}'")
                await random_delay(2.0, 3.0)
                for _ in range(5):
                    await page.evaluate('window.scrollBy(0, 600)')
                    await random_delay(0.3, 0.5)
                text = await page.evaluate('document.body.innerText')
                if challenge_kw in text or specials_kw in text:
                    return text

                # Approach 3b: After clicking specials, try "ALL RACING SPECIALS"
                # or "See All" to expand the specials content
                expand_selectors = [
                    'text="ALL RACING SPECIALS"',
                    'text="All Racing Specials"',
                    'text="See All"',
                    'text="SEE ALL"',
                    'text="View All"',
                    'a:has-text("All Racing")',
                    'a:has-text("See All")',
                    'button:has-text("All Racing")',
                    'button:has-text("See All")',
                ]
                for sel in expand_selectors:
                    try:
                        el = page.locator(sel).first
                        if await el.count() > 0:
                            await el.click(timeout=3000)
                            self.log(f"Clicked expand: {sel}")
                            await random_delay(2.0, 4.0)
                            for _ in range(5):
                                await page.evaluate('window.scrollBy(0, 600)')
                                await random_delay(0.3, 0.5)
                            text = await page.evaluate('document.body.innerText')
                            if challenge_kw in text or specials_kw in text:
                                self.log("Found challenge content after expand!")
                                return text
                            break
                    except Exception:
                        pass

                # Approach 3c: DOM search for "ALL RACING SPECIALS" link
                try:
                    found2 = await page.evaluate('''() => {
                        const els = document.querySelectorAll('a, button, span, div');
                        for (const el of els) {
                            const t = (el.textContent || '').trim().toLowerCase();
                            if (t.includes('all racing specials') || t === 'see all'
                                || t === 'view all') {
                                el.click();
                                return t;
                            }
                        }
                        return null;
                    }''')
                    if found2:
                        self.log(f"DOM click expand: '{found2}'")
                        await random_delay(2.0, 4.0)
                        for _ in range(8):
                            await page.evaluate('window.scrollBy(0, 600)')
                            await random_delay(0.3, 0.5)
                        text = await page.evaluate('document.body.innerText')
                        if challenge_kw in text or specials_kw in text:
                            self.log("Found challenge content after DOM expand!")
                            return text
                except Exception:
                    pass
        except Exception:
            pass

        # Log what we see for debugging
        text = await page.evaluate('document.body.innerText')
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        self.log(f"Could not find specials. Page has {len(lines)} lines. Keywords:")
        for i, l in enumerate(lines[:80]):
            low = l.lower()
            if any(kw in low for kw in ['special', 'extra', 'challenge',
                                         'jockey', 'driver', 'watch']):
                self.log(f"  [{i}]: {l[:100]}")

        # Approach 4: Try clicking AU/NZ tab within specials
        # PointsBet may show INTL specials by default, need AU/NZ filter
        for au_sel in [
            'text="AU/NZ"', 'text="au/nz"', 'text="AUS/NZ"',
            'button:has-text("AU/NZ")', 'a:has-text("AU/NZ")',
            'span:has-text("AU/NZ")', '[data-testid*="au"]',
            'text="Australia"', 'text="Domestic"',
        ]:
            try:
                el = page.locator(au_sel).first
                if await el.count() > 0:
                    await el.click(timeout=3000)
                    self.log(f"Clicked AU/NZ tab: {au_sel}")
                    await random_delay(2.0, 4.0)
                    for _ in range(5):
                        await page.evaluate('window.scrollBy(0, 600)')
                        await random_delay(0.3, 0.5)
                    text = await page.evaluate('document.body.innerText')
                    if challenge_kw in text or specials_kw in text:
                        self.log("Found challenge content after AU/NZ click!")
                        return text
                    break
            except Exception:
                pass

        # Approach 5: Try direct challenge URLs
        challenge_urls = [
            f'https://pointsbet.com.au/racing/{race_type}-challenge',
            'https://pointsbet.com.au/racing/specials/au-nz',
            'https://pointsbet.com.au/racing?tab=specials&region=au',
        ]
        for curl in challenge_urls:
            try:
                await self.safe_goto(page, curl)
                await random_delay(2.0, 3.0)
                for _ in range(3):
                    await page.evaluate('window.scrollBy(0, 500)')
                    await random_delay(0.3, 0.5)
                text = await page.evaluate('document.body.innerText')
                if challenge_kw in text or specials_kw in text:
                    self.log(f"Found content at: {curl}")
                    return text
            except Exception:
                pass

        # Even if no challenge keyword found, return text so caller can
        # attempt to parse whatever content we got
        text = await page.evaluate('document.body.innerText')
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        if len(lines) > 20:
            self.log("Returning page content for best-effort parsing")
            return text

        return ''

    def _find_meetings_from_specials(self, text: str,
                                      race_type: str) -> List[str]:
        """Find meeting names from specials page text."""
        names = []

        if race_type == 'jockey':
            for l in text.split('\n'):
                if 'Thoroughbred Specials' in l and ' - ' in l:
                    m = re.match(r'([A-Za-z\s]+)\s*-\s*Thoroughbred', l.strip())
                    if m:
                        n = m.group(1).strip()
                        if n and n not in names:
                            names.append(n)
            if not names:
                found = re.findall(
                    r'Jockey Challenge\s*[-–]\s*([A-Za-z ]+)', text)
                names = list(dict.fromkeys([m.strip() for m in found]))
            if not names:
                found = re.findall(
                    r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+Jockey Challenge',
                    text)
                names = list(dict.fromkeys([m.strip() for m in found]))
        else:
            for l in text.split('\n'):
                if 'Harness Specials' in l and ' - ' in l:
                    m = re.match(r'([A-Za-z\s]+)\s*-\s*Harness', l.strip())
                    if m:
                        n = m.group(1).strip()
                        if n and n not in names:
                            names.append(n)
            if not names:
                found = re.findall(
                    r'Driver Challenge\s*[-–]\s*([A-Za-z ]+)', text)
                names = list(dict.fromkeys([m.strip() for m in found]))
            if not names:
                found = re.findall(
                    r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+Driver Challenge',
                    text)
                names = list(dict.fromkeys([m.strip() for m in found]))

        return names

    async def _scrape_challenge(self, page, text: str,
                                 race_type: str) -> List[Dict]:
        """Parse challenge data from specials page text.
        Returns list of meeting dicts."""
        challenge_kw = ('Jockey Challenge' if race_type == 'jockey'
                        else 'Driver Challenge')
        specials_kw = ('Thoroughbred Specials' if race_type == 'jockey'
                       else 'Harness Specials')
        key = 'jockeys' if race_type == 'jockey' else 'drivers'

        # Find meeting names
        names = self._find_meetings_from_specials(text, race_type)
        self.log(f"Found {len(names)} {race_type} meetings in specials text")
        if not names:
            return []

        results = []
        for name in names[:MAX_MEETINGS_PER_SCRAPER]:
            try:
                # First, try parsing from current page text
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                parsed = self._parse(lines, challenge_kw)

                # If that gives us data, filter by meeting name context
                if parsed:
                    meeting_section = self._parse_meeting_section(
                        lines, name, challenge_kw)
                    if meeting_section:
                        parsed = meeting_section

                # Also try with specials keyword
                if not parsed:
                    parsed = self._parse(lines, specials_kw)
                    if parsed:
                        meeting_section = self._parse_meeting_section(
                            lines, name, specials_kw)
                        if meeting_section:
                            parsed = meeting_section

                if parsed:
                    results.append({
                        'meeting': name.upper(),
                        'type': race_type,
                        key: parsed,
                        'source': 'pointsbet',
                        'country': get_country(name)
                    })
                    self.log(f"✅ {name}: {len(parsed)} ({race_type})")
                else:
                    # Try clicking into the meeting with more patterns
                    clicked = False
                    for pat in [
                        f'text="{name} - {specials_kw}"',
                        f'text="{challenge_kw} - {name}"',
                        f'text="{name} {challenge_kw}"',
                        f'text="{name} - {challenge_kw}"',
                        f'text=/{re.escape(name)}.*Challenge/i',
                        f'text=/{re.escape(name)}.*Specials/i',
                        f'text=/{re.escape(name)}/i',
                    ]:
                        clicked = await self.safe_click(
                            page, pat, timeout=3000)
                        if clicked:
                            break

                    if clicked:
                        await random_delay(1.5, 2.5)
                        for _ in range(3):
                            await page.evaluate('window.scrollBy(0, 500)')
                            await random_delay(0.2, 0.4)
                        new_lines = await self.get_text_lines(page)
                        parsed = self._parse(new_lines, challenge_kw)
                        if parsed:
                            results.append({
                                'meeting': name.upper(),
                                'type': race_type,
                                key: parsed,
                                'source': 'pointsbet',
                                'country': get_country(name)
                            })
                            self.log(f"✅ {name}: {len(parsed)} ({race_type})")
                        else:
                            self.log(f"⚠️ {name}: parsed 0 after click")

                        # Navigate back
                        await page.go_back()
                        await random_delay(1.0, 2.0)
                    else:
                        self.log(f"⚠️ {name}: could not click meeting")
            except Exception as e:
                self.log(f"⚠️ {name}: {str(e)[:50]}")
            await random_delay(0.5, 1.5)

        return results

    def _parse_meeting_section(self, lines: List[str], meeting: str,
                                challenge_kw: str) -> List[Dict]:
        """Try to parse a specific meeting's jockeys/drivers from a page
        that may contain multiple meetings."""
        # Find the section for this meeting
        start = None
        for i, l in enumerate(lines):
            if meeting.lower() in l.lower() and challenge_kw.lower() in l.lower():
                start = i
                break
            if meeting.lower() in l.lower():
                # Check next few lines for challenge keyword
                for j in range(i, min(i + 5, len(lines))):
                    if challenge_kw.lower() in lines[j].lower():
                        start = j
                        break
                if start:
                    break

        if start is None:
            return []

        # Parse from start until next meeting or section break
        result = []
        for i in range(start + 1, min(start + 50, len(lines))):
            l = lines[i]
            # Stop at next meeting section
            if ('Specials' in l or 'Trainer Challenge' in l
                    or ('Challenge' in l and l != challenge_kw
                        and meeting.lower() not in l.lower())):
                break
            if re.match(r'^\d+\.\d{2}$', l):
                odds = float(l)
                if i > 0 and 1.01 < odds < 500:
                    name = lines[i - 1]
                    if (name and len(name) > 2
                            and not re.match(r'^\d', name)
                            and 'see all' not in name.lower()
                            and not any(p['name'] == name for p in result)):
                        result.append({'name': name, 'odds': odds})
        return result

    async def scrape_jockey(self) -> List[Dict]:
        async def _do_scrape():
            try:
                await self.start_browser(use_firefox=True)
                page = await self.new_page()
                self.log("Starting jockey...")

                text = await self._navigate_to_specials(page, 'jockey')
                if not text:
                    self.log("Could not find specials content")
                    return []

                results = await self._scrape_challenge(page, text, 'jockey')
                self.log(f"Total jockey results: {len(results)} meetings")
                return results
            finally:
                await self.close_browser()

        return await with_retry(_do_scrape, name=f"{self.name}-jockey")

    async def scrape_driver(self) -> List[Dict]:
        async def _do_scrape():
            try:
                await self.start_browser(use_firefox=True)
                page = await self.new_page()
                self.log("Starting driver...")

                text = await self._navigate_to_specials(page, 'driver')
                if not text:
                    self.log("Could not find specials content")
                    return []

                results = await self._scrape_challenge(page, text, 'driver')
                self.log(f"Total driver results: {len(results)} meetings")
                return results
            finally:
                await self.close_browser()

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
                                and not any(p['name'] == name
                                            for p in result)):
                            result.append({'name': name, 'odds': odds})
        return result


# =====================================================
# TAB SCRAPER
# =====================================================

class TABScraper(BaseScraper):
    def __init__(self):
        super().__init__()
        self.name = "TAB"

    async def scrape(self) -> List[Dict]:
        """Scrape TAB.com.au Jockey Challenge page."""
        async def _do_scrape():
            meetings = []
            try:
                await self.start_browser(use_firefox=True)
                page = await self.new_page()
                self.log("Starting...")

                # Step 1: Visit home page first to establish session (SPA needs this)
                try:
                    await self.safe_goto(page, 'https://www.tab.com.au')
                    await random_delay(3.0, 5.0)
                    # Dismiss any modals/cookies
                    for sel in ['text="Accept"', 'text="OK"', 'text="Close"',
                                'button:has-text("Accept")', '[aria-label="Close"]']:
                        try:
                            el = page.locator(sel).first
                            if await el.count() > 0:
                                await el.click(timeout=2000)
                                await random_delay(0.5, 1.0)
                        except Exception:
                            pass
                except Exception:
                    self.log("Home page visit failed, continuing...")

                # Step 2: Try multiple JC URLs (TAB changes URL format frequently)
                jc_urls = [
                    'https://www.tab.com.au/racing/jockey-challenge',
                    'https://www.tab.com.au/sports/betting/Jockey%20Challenge/competitions/Jockey%20Challenge',
                    'https://www.tab.com.au/sports/betting/Jockey+Challenge',
                    'https://www.tab.com.au/racing/extras',
                    'https://www.tab.com.au/racing/specials',
                    'https://www.tab.com.au/racing?category=jockey-challenge',
                ]
                jc_keywords = ['JOCK MstPts', 'Jockey Challenge',
                               'Jockey Watch', 'jockey challenge']
                text = ''
                for url in jc_urls:
                    try:
                        await self.safe_goto(page, url)
                        await random_delay(4.0, 6.0)
                        # Wait for SPA to render content
                        try:
                            await page.wait_for_selector(
                                'text=/Jockey Challenge|JOCK MstPts|Jockey Watch/i',
                                timeout=10000)
                        except PlaywrightTimeout:
                            pass
                        # Scroll to trigger lazy loading
                        for _ in range(3):
                            await page.evaluate('window.scrollBy(0, 500)')
                            await random_delay(0.3, 0.5)
                        lines = await self.get_text_lines(page)
                        if self.is_page_blocked(lines):
                            self.log(f"Blocked at {url}")
                            continue
                        text = '\n'.join(lines)
                        if any(kw in text for kw in jc_keywords):
                            self.log(f"JC content found at: {url}")
                            break
                        self.log(f"No JC content at {url} ({len(lines)} lines)")
                    except Exception as e:
                        self.log(f"URL failed: {url} - {str(e)[:40]}")

                # Step 3: If direct URLs failed, try navigation through racing section
                if not any(kw in text for kw in jc_keywords):
                    self.log("Direct URLs failed, trying racing section nav...")
                    try:
                        await self.safe_goto(page, 'https://www.tab.com.au/racing')
                        await random_delay(3.0, 5.0)
                        # Scroll to load content
                        for _ in range(5):
                            await page.evaluate('window.scrollBy(0, 500)')
                            await random_delay(0.3, 0.5)

                        # Look for any Jockey Challenge or Specials/Extras link
                        jc_selectors = [
                            'text="Jockey Challenge"',
                            'a:has-text("Jockey Challenge")',
                            'text="JOCKEY CHALLENGE"',
                            'text="Jockey Watch"',
                            'a:has-text("Jockey Watch")',
                            'text="Extras"', 'text="Specials"',
                            'a:has-text("Extras")', 'a:has-text("Specials")',
                        ]
                        for sel in jc_selectors:
                            clicked = await self.safe_click(page, sel, timeout=3000)
                            if clicked:
                                await random_delay(3.0, 5.0)
                                for _ in range(3):
                                    await page.evaluate('window.scrollBy(0, 500)')
                                    await random_delay(0.3, 0.5)
                                lines = await self.get_text_lines(page)
                                text = '\n'.join(lines)
                                if any(kw in text for kw in jc_keywords):
                                    self.log(f"Found JC via nav click: {sel}")
                                    break
                    except Exception:
                        pass

                # Step 4: Last resort - try DOM search for any JC-like link
                if not any(kw in text for kw in jc_keywords):
                    self.log("Nav failed, trying DOM search for JC links...")
                    try:
                        found = await page.evaluate('''() => {
                            const els = document.querySelectorAll('a, button, [role="tab"], span');
                            for (const el of els) {
                                const t = (el.textContent || '').trim().toLowerCase();
                                if (t.includes('jockey') || t.includes('challenge')
                                    || t === 'extras' || t === 'specials') {
                                    el.click();
                                    return t;
                                }
                            }
                            return null;
                        }''')
                        if found:
                            self.log(f"DOM click: '{found}'")
                            await random_delay(3.0, 5.0)
                            lines = await self.get_text_lines(page)
                            text = '\n'.join(lines)
                    except Exception:
                        pass

                if not text:
                    self.log("Could not load any content")
                    return []

                lines = [l.strip() for l in text.split('\n') if l.strip()]
                self.log(f"Page loaded: {len(lines)} lines")

                if 'JOCK MstPts' not in text:
                    # Try alternate parsing - TAB sometimes shows different format
                    if any(kw in text for kw in ['Jockey Challenge', 'Jockey Watch']):
                        self.log("Found JC text (alt format), trying alt parse...")
                        meetings = self._parse_alt(text)
                        if meetings:
                            for m in meetings:
                                self.log(f"✅ {m['meeting']}: {len(m.get('jockeys', []))} jockeys")
                            return meetings

                    self.log("No JOCK MstPts content found")
                    for i, l in enumerate(lines[:30]):
                        self.log(f"  [{i}]: {l[:100]}")
                    return []

                meetings = self._parse(text)
                self.log(f"Found {len(meetings)} meetings")

                for m in meetings:
                    name = m['meeting']
                    count = len(m.get('jockeys', []))
                    self.log(f"✅ {name}: {count} jockeys")

            except Exception as e:
                self.log(f"Error: {str(e)[:60]}")
            finally:
                await self.close_browser()
            return meetings

        return await with_retry(_do_scrape, name=self.name)

    def _parse(self, text: str) -> List[Dict]:
        """Parse TAB page. Format: JOCK MstPts MEETING_NAME, then
        jockey names followed by odds values."""
        meetings = []
        current = None
        jockeys = []
        prev = None
        skip = ['Market', 'SUSP', 'Any Other', 'Bet Slip', 'MENU',
                'AUDIO', 'Jockey Challenge', 'JOCK MstPts']

        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue

            # Detect meeting header: "JOCK MstPts FLEMINGTON"
            if line.startswith('JOCK MstPts '):
                rem = line.replace('JOCK MstPts ', '')
                if rem.isupper() and not any(c.isdigit() for c in rem):
                    if current and jockeys:
                        meetings.append({
                            'meeting': current,
                            'type': 'jockey',
                            'jockeys': jockeys.copy(),
                            'source': 'tab',
                            'country': get_country(current)
                        })
                    current, jockeys, prev = rem, [], None
                    continue

            if any(x.lower() in line.lower() for x in skip):
                prev = None
                continue

            # Try parsing as odds
            try:
                odds = float(line)
                if 1.01 < odds < 500 and prev:
                    jockeys.append({'name': prev, 'odds': odds})
                prev = None
            except ValueError:
                # Jockey name: starts with uppercase, mixed case, no digits
                if (current and len(line) > 2 and line[0].isupper()
                        and not line.isupper()
                        and not any(c.isdigit() for c in line)):
                    prev = line

        # Don't forget last meeting
        if current and jockeys:
            meetings.append({
                'meeting': current,
                'type': 'jockey',
                'jockeys': jockeys,
                'source': 'tab',
                'country': get_country(current)
            })
        return meetings

    async def scrape_driver(self) -> List[Dict]:
        """Scrape TAB.com.au Driver Challenge (harness racing)."""
        async def _do_scrape():
            meetings = []
            try:
                await self.start_browser(use_firefox=True)
                page = await self.new_page()
                self.log("Starting driver...")

                # Visit home page for session
                try:
                    await self.safe_goto(page, 'https://www.tab.com.au')
                    await random_delay(3.0, 5.0)
                    for sel in ['text="Accept"', 'text="OK"', 'text="Close"',
                                'button:has-text("Accept")', '[aria-label="Close"]']:
                        try:
                            el = page.locator(sel).first
                            if await el.count() > 0:
                                await el.click(timeout=2000)
                                await random_delay(0.5, 1.0)
                        except Exception:
                            pass
                except Exception:
                    pass

                # Try URLs that may have driver challenges
                dc_urls = [
                    'https://www.tab.com.au/racing/driver-challenge',
                    'https://www.tab.com.au/sports/betting/Driver%20Challenge/competitions/Driver%20Challenge',
                    'https://www.tab.com.au/racing/extras',
                    'https://www.tab.com.au/racing/specials',
                ]
                dc_keywords = ['DRVR MstPts', 'Driver Challenge',
                               'Driver Watch', 'driver challenge']
                text = ''
                for url in dc_urls:
                    try:
                        await self.safe_goto(page, url)
                        await random_delay(4.0, 6.0)
                        try:
                            await page.wait_for_selector(
                                'text=/Driver Challenge|DRVR MstPts|Driver Watch/i',
                                timeout=10000)
                        except PlaywrightTimeout:
                            pass
                        for _ in range(3):
                            await page.evaluate('window.scrollBy(0, 500)')
                            await random_delay(0.3, 0.5)
                        lines = await self.get_text_lines(page)
                        if self.is_page_blocked(lines):
                            continue
                        text = '\n'.join(lines)
                        if any(kw in text for kw in dc_keywords):
                            self.log(f"DC content found at: {url}")
                            break
                        self.log(f"No DC content at {url} ({len(lines)} lines)")
                    except Exception as e:
                        self.log(f"URL failed: {url} - {str(e)[:40]}")

                if not text or not any(kw in text for kw in dc_keywords):
                    self.log("No driver challenge content found")
                    return []

                # Parse DRVR MstPts format
                if 'DRVR MstPts' in text:
                    meetings = self._parse_driver(text)
                else:
                    # Try alt format: "Driver Challenge - MEETING"
                    meetings = self._parse_driver_alt(text)

                for m in meetings:
                    name = m['meeting']
                    count = len(m.get('drivers', []))
                    self.log(f"✅ {name}: {count} drivers")

            except Exception as e:
                self.log(f"Error: {str(e)[:60]}")
            finally:
                await self.close_browser()
            return meetings

        return await with_retry(_do_scrape, name=f"{self.name}-driver")

    def _parse_driver(self, text: str) -> List[Dict]:
        """Parse TAB driver challenge page (DRVR MstPts format)."""
        meetings = []
        current = None
        drivers = []
        prev = None
        skip = ['Market', 'SUSP', 'Any Other', 'Bet Slip', 'MENU',
                'AUDIO', 'Driver Challenge', 'DRVR MstPts']

        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue
            if line.startswith('DRVR MstPts '):
                rem = line.replace('DRVR MstPts ', '')
                if rem.isupper() and not any(c.isdigit() for c in rem):
                    if current and drivers:
                        meetings.append({
                            'meeting': current,
                            'type': 'driver',
                            'drivers': drivers.copy(),
                            'source': 'tab',
                            'country': get_country(current)
                        })
                    current, drivers, prev = rem, [], None
                    continue
            if any(x.lower() in line.lower() for x in skip):
                prev = None
                continue
            try:
                odds = float(line)
                if 1.01 < odds < 500 and prev:
                    drivers.append({'name': prev, 'odds': odds})
                prev = None
            except ValueError:
                if (current and len(line) > 2 and line[0].isupper()
                        and not line.isupper()
                        and not any(c.isdigit() for c in line)):
                    prev = line

        if current and drivers:
            meetings.append({
                'meeting': current,
                'type': 'driver',
                'drivers': drivers,
                'source': 'tab',
                'country': get_country(current)
            })
        return meetings

    def _parse_driver_alt(self, text: str) -> List[Dict]:
        """Alt parser for Driver Challenge - Meeting format."""
        meetings = []
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        meeting_names = re.findall(
            r'Driver Challenge\s*[-–]\s*([A-Za-z ]+)', text)
        if not meeting_names:
            meeting_names = re.findall(
                r'([A-Z][A-Z ]+)\s*Driver Challenge', text)
        meeting_names = list(dict.fromkeys(
            [m.strip() for m in meeting_names if len(m.strip()) > 2]))
        if not meeting_names:
            return []
        self.log(f"Driver alt parse: {len(meeting_names)} meetings")
        for meeting in meeting_names[:MAX_MEETINGS_PER_SCRAPER]:
            drivers = []
            in_section = False
            prev = None
            for line in lines:
                if meeting.lower() in line.lower() and 'driver' in line.lower():
                    in_section = True
                    continue
                if in_section:
                    if ('Challenge' in line and meeting.lower() not in line.lower()):
                        break
                    try:
                        odds = float(line)
                        if 1.01 < odds < 500 and prev:
                            drivers.append({'name': prev, 'odds': odds})
                        prev = None
                    except ValueError:
                        if (len(line) > 2 and line[0].isupper()
                                and not line.isupper()
                                and 'Any Other' not in line
                                and not any(c.isdigit() for c in line)):
                            prev = line
            if drivers:
                meetings.append({
                    'meeting': meeting.upper(),
                    'type': 'driver',
                    'drivers': drivers,
                    'source': 'tab',
                    'country': get_country(meeting)
                })
        return meetings

    def _parse_alt(self, text: str) -> List[Dict]:
        """Alternate TAB parser for different page format.
        Handles cases where TAB shows 'Jockey Challenge - Meeting' format."""
        meetings = []
        lines = [l.strip() for l in text.split('\n') if l.strip()]

        # Find meeting names: "Jockey Challenge - MEETINGNAME"
        meeting_names = re.findall(
            r'Jockey Challenge\s*[-–]\s*([A-Za-z ]+)', text)
        if not meeting_names:
            meeting_names = re.findall(
                r'([A-Z][A-Z ]+)\s*Jockey Challenge', text)
        meeting_names = list(dict.fromkeys(
            [m.strip() for m in meeting_names if len(m.strip()) > 2]))

        if not meeting_names:
            return []

        self.log(f"Alt parse found {len(meeting_names)} meetings: {meeting_names}")

        for meeting in meeting_names[:MAX_MEETINGS_PER_SCRAPER]:
            jockeys = []
            # Find section for this meeting and parse odds
            in_section = False
            prev = None
            for line in lines:
                if meeting.lower() in line.lower() and 'challenge' in line.lower():
                    in_section = True
                    continue
                if in_section:
                    # Stop at next meeting or unrelated section
                    if ('Challenge' in line and meeting.lower() not in line.lower()):
                        break
                    try:
                        odds = float(line)
                        if 1.01 < odds < 500 and prev:
                            jockeys.append({'name': prev, 'odds': odds})
                        prev = None
                    except ValueError:
                        if (len(line) > 2 and line[0].isupper()
                                and not line.isupper()
                                and 'Any Other' not in line
                                and not any(c.isdigit() for c in line)):
                            prev = line

            if jockeys:
                meetings.append({
                    'meeting': meeting.upper(),
                    'type': 'jockey',
                    'jockeys': jockeys,
                    'source': 'tab',
                    'country': get_country(meeting)
                })

        return meetings


# =====================================================
# SPORTSBET SCRAPER
# =====================================================

class SportsbetScraper(BaseScraper):
    def __init__(self):
        super().__init__()
        self.name = "Sportsbet"

    async def _load_racing(self, page) -> str:
        """Load Sportsbet racing page with WAF bypass attempts."""
        # Try 1: Visit home page first then navigate (looks more natural)
        try:
            await self.safe_goto(page, 'https://www.sportsbet.com.au')
            await random_delay(2.0, 4.0)
            lines = await self.get_text_lines(page)
            if not self.is_page_blocked(lines):
                # Successfully on home page, now navigate to racing
                await self.safe_goto(
                    page, 'https://www.sportsbet.com.au/horse-racing')
                await random_delay(1.5, 3.0)
                text = await page.evaluate('document.body.innerText')
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                if not self.is_page_blocked(lines):
                    return text
        except Exception:
            pass

        # Try 2: Direct racing URLs (multiple possible paths)
        racing_urls = [
            'https://www.sportsbet.com.au/horse-racing',
            'https://www.sportsbet.com.au/racing',
            'https://www.sportsbet.com.au/horse-racing/extras',
        ]
        for racing_url in racing_urls:
            try:
                await self.safe_goto(page, racing_url)
                await random_delay(1.5, 3.0)
                text = await page.evaluate('document.body.innerText')
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                if not self.is_page_blocked(lines) and len(lines) > 10:
                    self.log(f"Racing page loaded from {racing_url}")
                    return text
            except Exception:
                pass

        self.log("All racing URLs failed or blocked")
        return ''

    async def _click_extras_tab(self, page) -> bool:
        """Try multiple selectors to click the Extras/Specials tab on Sportsbet."""
        # Sportsbet renamed 'Extras' to 'Specials' - try both
        selectors = [
            'text="Specials"',
            'text="SPECIALS"',
            'text="specials"',
            '[data-automation-id="specials-tab"]',
            'button:has-text("Specials")',
            'a:has-text("Specials")',
            '[role="tab"]:has-text("Specials")',
            'li:has-text("Specials")',
            'span:has-text("Specials")',
            # Fallback to old Extras name
            'text="Extras"',
            'text="EXTRAS"',
            '[data-automation-id="extras-tab"]',
            'button:has-text("Extras")',
            'a:has-text("Extras")',
            '[role="tab"]:has-text("Extras")',
        ]
        for sel in selectors:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.click(timeout=3000)
                    await random_delay(1.5, 2.5)
                    self.log(f"Clicked tab via: {sel}")
                    return True
            except Exception:
                pass
        return False

    async def _navigate_to_extras(self, page) -> str:
        """Navigate to Sportsbet Specials/Extras page.
        'Specials' (formerly 'Extras') is a client-side tab in the SPA."""

        # Content keywords that indicate we found the right page
        content_keywords = ['Challenge', 'Jockey Watch', 'Driver Watch',
                           'Jockey Challenge', 'Driver Challenge']

        def has_content(t):
            return any(kw in t for kw in content_keywords)

        # Step 0: Try direct extras/specials URLs first
        direct_urls = [
            'https://www.sportsbet.com.au/horse-racing/extras',
            'https://www.sportsbet.com.au/horse-racing?tab=extras',
            'https://www.sportsbet.com.au/horse-racing?tab=specials',
        ]
        for durl in direct_urls:
            try:
                await self.safe_goto(page, durl)
                await random_delay(2.0, 4.0)
                for _ in range(6):
                    await page.evaluate('window.scrollBy(0, 600)')
                    await random_delay(0.3, 0.5)
                text = await page.evaluate('document.body.innerText')
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                if not self.is_page_blocked(lines) and has_content(text):
                    self.log(f"Found extras content at {durl}")
                    return text
                if not self.is_page_blocked(lines) and len(lines) > 10:
                    self.log(f"Loaded {durl} ({len(lines)} lines) "
                             f"but no challenge content")
            except Exception:
                pass

        # Step 1: Load the racing page
        text = await self._load_racing(page)
        if not text:
            return ''

        lines = [l.strip() for l in text.split('\n') if l.strip()]
        self.log(f"Racing page loaded ({len(lines)} lines), looking for Specials/Extras tab...")

        # Step 2: Wait for SPA to fully render tabs
        await random_delay(1.0, 2.0)

        # Step 3: Try clicking Specials/Extras tab
        if await self._click_extras_tab(page):
            # Wait for content to load after tab click
            await random_delay(2.0, 3.5)
            # Scroll to load lazy content
            for _ in range(6):
                await page.evaluate('window.scrollBy(0, 600)')
                await random_delay(0.4, 0.7)
            text = await page.evaluate('document.body.innerText')
            if has_content(text):
                self.log("Specials tab loaded with challenge content!")
                return text
            self.log("Clicked tab but no challenge content yet, scrolling more...")
            # Try waiting a bit more for dynamic content
            await random_delay(2.0, 3.0)
            for _ in range(5):
                await page.evaluate('window.scrollBy(0, 500)')
                await random_delay(0.3, 0.5)
            text = await page.evaluate('document.body.innerText')
            if has_content(text):
                self.log("Challenge content appeared after scroll!")
                return text

            # Still no content - try clicking sub-tabs within Specials
            sub_selectors = [
                'text="Jockey Challenge"', 'text="Jockey Watch"',
                'text="Driver Challenge"', 'text="Driver Watch"',
                'text="Horse Racing"', 'a:has-text("Horse Racing")',
                'text="Thoroughbred"', 'a:has-text("Thoroughbred")',
            ]
            for sel in sub_selectors:
                try:
                    el = page.locator(sel).first
                    if await el.count() > 0:
                        await el.click(timeout=3000)
                        await random_delay(2.0, 3.0)
                        text = await page.evaluate('document.body.innerText')
                        if has_content(text):
                            self.log(f"Found content after sub-click: {sel}")
                            return text
                except Exception:
                    pass

        # Step 4: If tab click failed, search DOM
        self.log("Tab click failed, searching DOM...")
        try:
            found_tab = await page.evaluate('''() => {
                const elements = document.querySelectorAll(
                    'a, button, [role="tab"], [class*="tab"], li, span, div');
                for (const el of elements) {
                    const text = (el.textContent || '').trim();
                    if (text === 'Specials' || text === 'SPECIALS'
                        || text === 'Extras' || text === 'EXTRAS') {
                        el.click();
                        return text;
                    }
                }
                return null;
            }''')
            if found_tab:
                self.log(f"Clicked via DOM search: '{found_tab}'")
                await random_delay(2.0, 3.5)
                for _ in range(6):
                    await page.evaluate('window.scrollBy(0, 600)')
                    await random_delay(0.3, 0.5)
                text = await page.evaluate('document.body.innerText')
                if has_content(text):
                    return text
        except Exception as e:
            self.log(f"DOM search failed: {str(e)[:50]}")

        # Step 5: Log what we see for debugging
        text = await page.evaluate('document.body.innerText')
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        self.log("Could not find Specials/Extras content. Page navigation:")
        for i, l in enumerate(lines[:80]):
            if any(kw in l.lower() for kw in [
                'extra', 'tab', 'challenge', 'jockey', 'driver',
                'racing', 'special', 'harness', 'watch'
            ]):
                self.log(f"  NAV [{i}]: {l[:100]}")

        # Check if content exists on page without Specials tab
        if has_content(text):
            self.log("Challenge content found on current page!")
            return text

        return text

    async def scrape_jockey(self) -> List[Dict]:
        async def _do_scrape():
            meetings = []
            try:
                await self.start_browser(use_firefox=True)
                page = await self.new_page()
                self.log("Starting jockey...")

                text = await self._navigate_to_extras(page)
                if not text:
                    return []

                # Search for jockey challenge/watch patterns in text
                # Sportsbet uses both "Jockey Challenge" and "Jockey Watch"
                patterns = [
                    r'Jockey Challenge\s*[-–]\s*([A-Za-z ]+)',
                    r'([A-Za-z ]+)\s*[-–]\s*Jockey Challenge',
                    r'Jockey Challenge - ([A-Za-z ]+)',
                    r'Jockey Watch\s*[-–]\s*([A-Za-z ]+)',
                    r'([A-Za-z ]+)\s*[-–]\s*Jockey Watch',
                    r'Jockey Watch - ([A-Za-z ]+)',
                ]
                found = []
                for pat in patterns:
                    found = re.findall(pat, text)
                    if found:
                        break
                found = list(dict.fromkeys([m.strip() for m in found if len(m.strip()) > 2]))
                self.log(f"Found {len(found)} jockey meetings")

                if not found:
                    # Try clicking into JC sections directly
                    for jw_sel in [
                        'text="Jockey Challenge"',
                        'text="JOCKEY CHALLENGE"',
                        'a:has-text("Jockey Challenge")',
                        'text="Jockey Watch"', 'text="JOCKEY WATCH"',
                        'a:has-text("Jockey Watch")',
                        'button:has-text("Jockey Watch")',
                    ]:
                        jw_clicked = await self.safe_click(
                            page, jw_sel, timeout=5000)
                        if jw_clicked:
                            self.log(f"Clicked '{jw_sel}' to expand")
                            await random_delay(2.0, 3.0)
                            for _ in range(6):
                                await page.evaluate(
                                    'window.scrollBy(0, 500)')
                                await random_delay(0.3, 0.5)
                            text = await page.evaluate(
                                'document.body.innerText')
                            # Re-try all patterns including more
                            all_patterns = patterns + [
                                r'(\w[\w ]+?)\s+Jockey Challenge',
                                r'(\w[\w ]+?)\s+Jockey Watch',
                                r'Jockey Challenge\s+(\w[\w ]+?)(?:\s|$)',
                            ]
                            for pat in all_patterns:
                                found = re.findall(pat, text)
                                if found:
                                    break
                            found = list(dict.fromkeys(
                                [m.strip() for m in found
                                 if len(m.strip()) > 2]))
                            if found:
                                self.log(f"After expand: {len(found)}")
                                break
                            # Try direct odds parsing on expanded page
                            exp_lines = [l.strip() for l in
                                         text.split('\n') if l.strip()]
                            jockeys = self._parse(exp_lines)
                            if jockeys:
                                # Find meeting name from page text
                                mname = 'UNKNOWN'
                                for ln in exp_lines:
                                    # "Toowoomba" style or "TOOWOOMBA"
                                    m = re.match(
                                        r'([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)'
                                        r'\s+Jockey', ln)
                                    if m:
                                        mname = m.group(1).strip()
                                        break
                                    m2 = re.match(
                                        r'([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)$',
                                        ln)
                                    if (m2 and len(ln) > 3
                                            and ln not in [
                                                'Jockey Watch',
                                                'Jockey Challenge',
                                                'Horse Racing',
                                                'Extras', 'Specials']):
                                        mname = m2.group(1).strip()
                                        break
                                meetings.append({
                                    'meeting': mname.upper(),
                                    'type': 'jockey',
                                    'jockeys': jockeys,
                                    'source': 'sportsbet',
                                    'country': get_country(mname)
                                })
                                self.log(
                                    f"✅ {mname}: {len(jockeys)} (expanded)")
                            break

                if not found and not meetings:
                    lines = [l.strip() for l in text.split('\n') if l.strip()]
                    for i, l in enumerate(lines):
                        if any(kw in l.lower() for kw in ['jockey', 'challenge', 'watch']):
                            self.log(f"  KEYWORD [{i}]: {l[:100]}")

                for meeting in found[:MAX_MEETINGS_PER_SCRAPER]:
                    try:
                        # Try clicking the meeting entry
                        clicked = False
                        for pat in [
                            f'text="Jockey Challenge - {meeting}"',
                            f'text="{meeting} - Jockey Challenge"',
                            f'text="{meeting} Jockey Challenge"',
                            f'text="Jockey Watch - {meeting}"',
                            f'text="{meeting} - Jockey Watch"',
                            f'text="{meeting} Jockey Watch"',
                        ]:
                            clicked = await self.safe_click(page, pat, timeout=3000)
                            if clicked:
                                break

                        if not clicked:
                            # Try finding and clicking via locator
                            for regex_pat in [
                                f'text=/{re.escape(meeting)}.*Challenge/i',
                                f'text=/{re.escape(meeting)}.*Watch/i',
                                f'text=/Jockey.*{re.escape(meeting)}/i',
                            ]:
                                try:
                                    loc = page.locator(regex_pat).first
                                    if await loc.count() > 0:
                                        await loc.click(timeout=3000)
                                        clicked = True
                                        await random_delay(1.0, 1.5)
                                        break
                                except Exception:
                                    pass

                        if not clicked:
                            continue

                        await random_delay(1.0, 2.0)
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

                        # Navigate back for next meeting
                        await page.go_back()
                        await random_delay(1.0, 1.5)
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
                await self.start_browser(use_firefox=True)
                page = await self.new_page()
                self.log("Starting driver...")

                # Try harness-racing page first (drivers are harness)
                text = ''
                for racing_url in [
                    'https://www.sportsbet.com.au/harness-racing',
                    'https://www.sportsbet.com.au/horse-racing',
                ]:
                    try:
                        await self.safe_goto(page, racing_url)
                        await random_delay(1.5, 3.0)
                        lines = await self.get_text_lines(page)
                        if self.is_page_blocked(lines):
                            continue
                        self.log(f"Loaded {racing_url} ({len(lines)} lines)")
                        # Try clicking Specials/Extras tab
                        if await self._click_extras_tab(page):
                            await random_delay(2.0, 3.5)
                            for _ in range(6):
                                await page.evaluate('window.scrollBy(0, 600)')
                                await random_delay(0.4, 0.7)
                        text = await page.evaluate('document.body.innerText')
                        if any(kw in text for kw in ['Driver Challenge', 'Driver Watch',
                                                      'driver challenge', 'driver watch']):
                            self.log(f"Found driver content at {racing_url}")
                            break
                    except Exception as e:
                        self.log(f"URL failed: {racing_url} - {str(e)[:40]}")

                if not text:
                    # Fallback to the regular extras navigation
                    text = await self._navigate_to_extras(page)
                if not text:
                    return []

                # Search for driver challenge/watch patterns
                patterns = [
                    r'Driver Challenge\s*[-–]\s*([A-Za-z ]+)',
                    r'([A-Za-z ]+)\s*[-–]\s*Driver Challenge',
                    r'([A-Za-z ]+) Driver Challenge',
                    r'Driver Watch\s*[-–]\s*([A-Za-z ]+)',
                    r'([A-Za-z ]+)\s*[-–]\s*Driver Watch',
                    r'([A-Za-z ]+) Driver Watch',
                ]
                found = []
                for pat in patterns:
                    found = re.findall(pat, text)
                    if found:
                        break
                # Only filter generic labels, not track names
                found = [m.strip() for m in found
                         if len(m.strip()) > 2
                         and m.strip().lower() not in ('harness', 'harness racing', '')]
                found = list(dict.fromkeys(found))
                self.log(f"Found {len(found)} driver meetings")

                if not found:
                    lines = [l.strip() for l in text.split('\n') if l.strip()]
                    for i, l in enumerate(lines):
                        if any(kw in l.lower() for kw in ['driver', 'challenge', 'watch']):
                            self.log(f"  KEYWORD [{i}]: {l[:100]}")

                for meeting in found[:MAX_MEETINGS_PER_SCRAPER]:
                    try:
                        clicked = False
                        for pat in [
                            f'text="{meeting} Driver Challenge"',
                            f'text="Driver Challenge - {meeting}"',
                            f'text="{meeting} - Driver Challenge"',
                            f'text="{meeting} Driver Watch"',
                            f'text="Driver Watch - {meeting}"',
                            f'text="{meeting} - Driver Watch"',
                        ]:
                            clicked = await self.safe_click(page, pat, timeout=3000)
                            if clicked:
                                break

                        if not clicked:
                            for regex_pat in [
                                f'text=/{re.escape(meeting)}.*Driver/i',
                                f'text=/Driver.*{re.escape(meeting)}/i',
                            ]:
                                try:
                                    loc = page.locator(regex_pat).first
                                    if await loc.count() > 0:
                                        await loc.click(timeout=3000)
                                        clicked = True
                                        await random_delay(1.0, 1.5)
                                        break
                                except Exception:
                                    pass

                        if not clicked:
                            continue

                        await random_delay(1.0, 2.0)
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

                        await page.go_back()
                        await random_delay(1.0, 1.5)
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


async def run_sequential(scrapers_config: List[tuple]) -> tuple:
    """Run scrapers one at a time (for low-RAM servers like 1GB DO droplet).
    scrapers_config: list of (scraper_callable, 'jockey'|'driver') tuples."""
    jockey, driver = [], []
    for scraper_fn, data_type in scrapers_config:
        try:
            logger.info(f"  Running {scraper_fn.__self__.name} ({data_type})...")
            result = await scraper_fn()
            if isinstance(result, list):
                if data_type == 'jockey':
                    jockey.extend(result)
                else:
                    driver.extend(result)
                logger.info(f"  → Got {len(result)} meetings")
        except Exception as e:
            logger.error(f"  → Failed: {str(e)[:60]}")
        # Force memory cleanup between scrapers on low-RAM server
        gc.collect()
        await asyncio.sleep(2)
    return jockey, driver


async def run_all_scrapers():
    logger.info(f"\n🏇 Starting Scraper at {datetime.now()}")
    start = datetime.now()

    # Detect mode: sequential for server (LOW_RAM), parallel for GitHub Actions
    sequential = os.environ.get('SCRAPER_MODE') == 'sequential'

    if sequential:
        logger.info("📌 Sequential mode (server)")
        scrapers = [
            (TABtouchScraper().scrape, 'jockey'),
            (TABScraper().scrape, 'jockey'),
            (ElitebetScraper().scrape, 'jockey'),
            (LadbrokesScraper().scrape_jockey, 'jockey'),
            (SportsbetScraper().scrape_jockey, 'jockey'),
            (PointsBetScraper().scrape_jockey, 'jockey'),
            (TABtouchScraper().scrape_driver, 'driver'),
            (TABScraper().scrape_driver, 'driver'),
            (LadbrokesScraper().scrape_driver, 'driver'),
            (SportsbetScraper().scrape_driver, 'driver'),
            (PointsBetScraper().scrape_driver, 'driver'),
        ]
        jockey, driver = await run_sequential(scrapers)
    else:
        logger.info("📌 Parallel mode (GitHub Actions)")
        # Batch 1: Jockey scrapers
        batch1_results = await run_batch([
            TABtouchScraper().scrape(),
            LadbrokesScraper().scrape_jockey(),
            ElitebetScraper().scrape(),
            SportsbetScraper().scrape_jockey(),
            TABScraper().scrape(),
        ], "Batch 1")

        await asyncio.sleep(2)

        # Batch 2: Driver + PointsBet jockey
        batch2_results = await run_batch([
            TABtouchScraper().scrape_driver(),
            TABScraper().scrape_driver(),
            LadbrokesScraper().scrape_driver(),
            PointsBetScraper().scrape_jockey(),
            PointsBetScraper().scrape_driver(),
            SportsbetScraper().scrape_driver(),
        ], "Batch 2")

        jockey, driver = [], []
        for data in batch1_results:
            jockey.extend(data)
        if len(batch2_results) > 0:
            driver.extend(batch2_results[0])  # TABtouch driver
        if len(batch2_results) > 1:
            driver.extend(batch2_results[1])  # TAB driver
        if len(batch2_results) > 2:
            driver.extend(batch2_results[2])  # Ladbrokes driver
        if len(batch2_results) > 3:
            jockey.extend(batch2_results[3])  # PointsBet jockey
        if len(batch2_results) > 4:
            driver.extend(batch2_results[4])  # PointsBet driver
        if len(batch2_results) > 5:
            driver.extend(batch2_results[5])  # Sportsbet driver

    elapsed = int((datetime.now() - start).total_seconds())
    logger.info(f"✅ Done in {elapsed}s! Jockey: {len(jockey)} | Driver: {len(driver)}")

    # Per-scraper diagnostic summary
    source_counts = {}
    for m in jockey + driver:
        src = m.get('source', 'unknown')
        mtype = m.get('type', 'unknown')
        key = f"{src} ({mtype})"
        source_counts[key] = source_counts.get(key, 0) + 1

    logger.info("📊 Per-scraper results:")
    expected = ['tabtouch', 'tab', 'ladbrokes', 'sportsbet', 'pointsbet', 'elitebet']
    found_sources = {m.get('source', '') for m in jockey + driver}
    for src in sorted(source_counts):
        logger.info(f"  {src}: {source_counts[src]} meetings")
    for src in expected:
        if src not in found_sources:
            logger.warning(f"  ⚠️ {src}: 0 meetings (NO DATA)")

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


async def check_network():
    """Quick network check before starting scrapers."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('https://www.google.com',
                                   timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    logger.info("✅ Network OK")
                    return True
    except Exception as e:
        logger.error(f"❌ Network check failed: {str(e)[:60]}")
    return False


async def main():
    if not await check_network():
        logger.error("❌ No network connectivity - aborting")
        return

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