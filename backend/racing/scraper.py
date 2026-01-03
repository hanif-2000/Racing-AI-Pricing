# racing/scraper.py - SIMPLIFIED & WORKING

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
# 🇳🇿 NZ TRACKS LIST
# =====================================================

NZ_TRACKS = [
    # Thoroughbred (Gallops)
    'TE AROHA', 'TRENTHAM', 'ELLERSLIE', 'RICCARTON', 'OTAKI',
    'HASTINGS', 'AWAPUNI', 'WANGANUI', 'ROTORUA', 'TAURANGA',
    'PUKEKOHE', 'RUAKAKA', 'MATAMATA', 'TE RAPA', 'WOODVILLE',
    'ASHBURTON', 'WINGATUI', 'OAMARU', 'TIMARU', 'WAVERLEY',
    'KUROW', 'CROMWELL', 'RIVERTON', 'WAIKOUAITI', 'TAPANUI',
    
    # Harness Racing
    'ADDINGTON', 'ALEXANDRA PARK', 'CAMBRIDGE', 'FORBURY PARK',
    'ASCOT PARK', 'MANAWATU', 'WYNDHAM', 'OAMARU HARNESS',
    'ASHBURTON HARNESS', 'METHVEN', 'RANGIORA', 'WASHDYKE',
    'BANKS PENINSULA', 'KAIKOURA', 'OMAKAU', 'WINTON',
    
    # Greyhounds
    'MANUKAU', 'WANGANUI GREYHOUNDS'
]

def get_country(track_name):
    """Identify if track is AU or NZ"""
    track_upper = track_name.upper().strip()
    
    # Check exact match
    if track_upper in NZ_TRACKS:
        return 'NZ'
    
    # Check partial match (for variations like "Te Aroha (NZ)")
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
# SPORTSBET - WORKING!
# =====================================================

class SportsbetScraper(BaseScraper):
    async def get_all_jockey_data(self):
        meetings = []
        playwright = browser = context = None
        
        try:
            playwright, browser, context = await self.get_browser()
            page = await context.new_page()
            
            print("[Sportsbet] Navigating for jockey challenges...")
            await page.goto('https://www.sportsbet.com.au/horse-racing', timeout=30000)
            await asyncio.sleep(3)
            
            try:
                await page.click('text="Extras"', timeout=5000)
                await asyncio.sleep(2)
                print("[Sportsbet] Clicked Extras tab")
            except:
                pass
            
            for _ in range(5):
                await page.evaluate('window.scrollBy(0, 500)')
                await asyncio.sleep(0.3)
            
            text = await page.evaluate('document.body.innerText')
            
            pattern = r'Jockey Challenge - ([A-Za-z ]+)'
            meeting_names = re.findall(pattern, text)
            meeting_names = list(dict.fromkeys([m.strip() for m in meeting_names]))[:5]
            
            print(f"[Sportsbet] Found jockey meetings: {meeting_names}")
            
            for meeting in meeting_names:
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
                                                skip = ['Jockey Challenge', 'Driver Challenge', 'Any Other', 'Back', 'Lay', 'Extras']
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
            
            print(f"[Sportsbet] ✅ {len(meetings)} jockey meetings total")
            
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
            
            print("[Sportsbet] Navigating for driver challenges...")
            await page.goto('https://www.sportsbet.com.au/horse-racing', timeout=30000)
            await asyncio.sleep(3)
            
            try:
                await page.click('text="Extras"', timeout=5000)
                await asyncio.sleep(2)
                print("[Sportsbet] Clicked Extras tab")
            except:
                pass
            
            for _ in range(8):
                await page.evaluate('window.scrollBy(0, 500)')
                await asyncio.sleep(0.3)
            
            text = await page.evaluate('document.body.innerText')
            
            pattern = r'([A-Za-z ]+) Driver Challenge'
            meeting_names = re.findall(pattern, text)
            meeting_names = [m.strip() for m in meeting_names if 'Harness' not in m]
            meeting_names = list(dict.fromkeys(meeting_names))[:5]
            
            print(f"[Sportsbet] Found driver meetings: {meeting_names}")
            
            for meeting in meeting_names:
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
# TABTOUCH - WORKING!
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
            await asyncio.sleep(4)
            
            for _ in range(3):
                await page.evaluate('window.scrollBy(0, 500)')
                await asyncio.sleep(0.5)
            
            text = await page.evaluate('document.body.innerText')
            meetings_found = re.findall(r'([A-Za-z ]+) Jockey Challenge 3,2,1 Points', text)
            meetings_found = list(dict.fromkeys([m.strip() for m in meetings_found]))[:5]
            
            print(f"[TABtouch] Found meetings: {meetings_found}")
            
            for meeting in meetings_found:
                try:
                    await page.goto('https://www.tabtouch.com.au/racing/jockey-challenge')
                    await asyncio.sleep(2)
                    
                    await page.click(f'text="{meeting} Jockey Challenge 3,2,1 Points"', timeout=3000)
                    await asyncio.sleep(2)
                    
                    text = await page.evaluate('document.body.innerText')
                    lines = text.split('\n')
                    
                    jockeys = []
                    for i, line in enumerate(lines):
                        line = line.strip()
                        try:
                            odds = float(line)
                            if 1 < odds < 200 and i >= 1:
                                name_line = lines[i-1].strip()
                                name = re.sub(r'\s*\d+\s*$', '', name_line).strip()
                                if name and 'ANY OTHER' not in name.upper() and len(name) > 3:
                                    if not any(j['name'] == name for j in jockeys):
                                        jockeys.append({'name': name, 'odds': odds})
                        except:
                            pass
                    
                    if jockeys:
                        meetings.append({
                            'meeting': meeting.upper(), 
                            'type': 'jockey', 
                            'jockeys': jockeys, 
                            'source': 'tabtouch',
                            'country': get_country(meeting)
                        })
                        print(f"[TABtouch] ✅ {meeting} ({get_country(meeting)}): {len(jockeys)} jockeys")
                    
                except:
                    pass
            
            print(f"[TABtouch] ✅ {len(meetings)} meetings total")
            
        except Exception as e:
            print(f"[TABtouch] ❌ Error: {str(e)[:80]}")
        finally:
            if browser: await browser.close()
            if playwright: await playwright.stop()
        
        return meetings


# =====================================================
# ELITEBET
# =====================================================

class ElitebetScraper(BaseScraper):
    async def get_all_jockey_data(self):
        meetings = []
        playwright = browser = context = None
        
        try:
            playwright, browser, context = await self.get_browser()
            page = await context.new_page()
            
            await page.goto('https://www.elitebet.com.au/racing', timeout=30000)
            await asyncio.sleep(3)
            
            try:
                await page.click('text="Jockey Challenge"', timeout=5000)
                await asyncio.sleep(2)
            except:
                print("[Elitebet] ❌ No Jockey Challenge link")
                return []
            
            text = await page.evaluate('document.body.innerText')
            lines = text.split('\n')
            
            meeting_names = []
            skip_list = ['Jockey Challenge', 'Futures', 'Today', 'Tomorrow', 'Help', 'Promotions']
            months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
            
            for i, line in enumerate(lines):
                line = line.strip()
                if any(m in line for m in months) and len(line) < 20:
                    for j in range(i-1, max(0, i-5), -1):
                        prev = lines[j].strip()
                        if prev and len(prev) > 3 and not any(c.isdigit() for c in prev):
                            if prev not in skip_list and prev not in meeting_names:
                                meeting_names.append(prev)
                                break
            
            meeting_names = meeting_names[:3]
            
            for meeting in meeting_names:
                try:
                    await page.click(f'text="{meeting}"', timeout=3000)
                    await asyncio.sleep(2)
                    
                    text = await page.evaluate('document.body.innerText')
                    lines = text.split('\n')
                    
                    jockeys = []
                    for i, line in enumerate(lines):
                        line = line.strip()
                        try:
                            odds = float(line)
                            if 1.01 < odds < 500 and i >= 2:
                                name = lines[i-2].strip()
                                if name and 'Any Other' not in name and len(name) > 3:
                                    if not any(j['name'] == name for j in jockeys):
                                        jockeys.append({'name': name, 'odds': odds})
                        except:
                            pass
                    
                    if jockeys:
                        meetings.append({
                            'meeting': meeting.upper(),
                            'type': 'jockey',
                            'jockeys': jockeys,
                            'source': 'elitebet',
                            'country': get_country(meeting)
                        })
                        print(f"[Elitebet] ✅ {meeting} ({get_country(meeting)}): {len(jockeys)} jockeys")
                    
                except:
                    pass
            
            print(f"[Elitebet] ✅ {len(meetings)} meetings total")
            
        except Exception as e:
            print(f"[Elitebet] ❌ Error: {str(e)[:80]}")
        finally:
            if browser: await browser.close()
            if playwright: await playwright.stop()
        
        return meetings


# =====================================================
# TAB SCRAPER - WORKING!
# =====================================================

class TABScraper(BaseScraper):
    async def get_all_jockey_data(self):
        meetings = []
        playwright = browser = context = None
        
        try:
            playwright, browser, context = await self.get_browser()
            page = await context.new_page()
            
            print("[TAB] Navigating...")
            await page.goto("https://www.tab.com.au/sports/betting/Jockey%20Challenge/competitions/Jockey%20Challenge", 
                          wait_until='domcontentloaded', timeout=30000)
            
            content = await page.content()
            if 'Access Denied' in content:
                print("[TAB] ❌ Access Denied")
                return []
            
            await asyncio.sleep(5)
            
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
# LADBROKES SCRAPER - UPDATED FOR EXACT PATTERNS!
# =====================================================

class LadbrokesScraper(BaseScraper):
    async def get_all_jockey_data(self):
        meetings = []
        playwright = browser = context = None
        
        try:
            playwright, browser, context = await self.get_browser()
            page = await context.new_page()
            
            print("[Ladbrokes] Navigating to Extras...")
            await page.goto('https://www.ladbrokes.com.au/racing/extras', timeout=30000)
            await asyncio.sleep(4)
            
            # Scroll to load all content
            for _ in range(5):
                await page.evaluate('window.scrollBy(0, 500)')
                await asyncio.sleep(0.3)
            
            text = await page.evaluate('document.body.innerText')
            
            # Pattern: "Jockey Challenge - Ipswich" format
            pattern = r'Jockey Challenge - ([A-Za-z ]+)'
            meeting_names = re.findall(pattern, text)
            meeting_names = list(dict.fromkeys([m.strip() for m in meeting_names]))[:10]
            
            print(f"[Ladbrokes] Found jockey meetings: {meeting_names}")
            
            for meeting in meeting_names:
                try:
                    # Click exact text "Jockey Challenge - {Meeting}"
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
                                # Look back for jockey name
                                for offset in [1, 2]:
                                    if i >= offset:
                                        name = lines[i-offset].strip()
                                        if name and len(name) > 3:
                                            if not any(c.isdigit() for c in name):
                                                skip = ['Jockey Challenge', 'Any Other', 'Win', 'Place', 'Back', 'Lay']
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
                            'source': 'ladbrokes',
                            'country': get_country(meeting)
                        })
                        print(f"[Ladbrokes] ✅ {meeting} ({get_country(meeting)}): {len(jockeys)} jockeys")
                    
                    # Go back to extras page
                    await page.goto('https://www.ladbrokes.com.au/racing/extras')
                    await asyncio.sleep(2)
                    
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
            
            print("[Ladbrokes] Navigating to Extras for drivers...")
            await page.goto('https://www.ladbrokes.com.au/racing/extras', timeout=30000)
            await asyncio.sleep(4)
            
            # Scroll more for harness racing section
            for _ in range(10):
                await page.evaluate('window.scrollBy(0, 500)')
                await asyncio.sleep(0.3)
            
            text = await page.evaluate('document.body.innerText')
            
            # Pattern: "Driver Challenge - Newcastle" or "Driver Challenge - Cranbourne (H)"
            pattern = r'Driver Challenge - ([A-Za-z0-9 \(\)]+)'
            meeting_names = re.findall(pattern, text)
            meeting_names = list(dict.fromkeys([m.strip() for m in meeting_names]))[:10]
            
            print(f"[Ladbrokes] Found driver meetings: {meeting_names}")
            
            for meeting in meeting_names:
                try:
                    # Click exact text "Driver Challenge - {Meeting}"
                    await page.click(f'text="Driver Challenge - {meeting}"', timeout=3000)
                    await asyncio.sleep(2)
                    
                    text = await page.evaluate('document.body.innerText')
                    lines = text.split('\n')
                    
                    drivers = []
                    for i, line in enumerate(lines):
                        line = line.strip()
                        try:
                            odds = float(line)
                            if 1.01 < odds < 500:
                                for offset in [1, 2]:
                                    if i >= offset:
                                        name = lines[i-offset].strip()
                                        if name and len(name) > 3:
                                            if not any(c.isdigit() for c in name):
                                                skip = ['Driver Challenge', 'Any Other', 'Win', 'Place', 'Back', 'Lay']
                                                if not any(s in name for s in skip):
                                                    if not any(d['name'] == name for d in drivers):
                                                        drivers.append({'name': name, 'odds': odds})
                                                        break
                        except:
                            pass
                    
                    if drivers:
                        # Clean meeting name (remove (H) suffix for display)
                        clean_meeting = meeting.replace(' (H)', '').upper()
                        meetings.append({
                            'meeting': clean_meeting,
                            'type': 'driver',
                            'drivers': drivers,
                            'source': 'ladbrokes',
                            'country': get_country(clean_meeting)
                        })
                        print(f"[Ladbrokes] ✅ {meeting} ({get_country(clean_meeting)}) Driver: {len(drivers)} drivers")
                    
                    # Go back to extras page
                    await page.goto('https://www.ladbrokes.com.au/racing/extras')
                    await asyncio.sleep(2)
                    
                except Exception as e:
                    print(f"[Ladbrokes] ⚠️ Driver {meeting}: {str(e)[:40]}")
            
            print(f"[Ladbrokes] ✅ {len(meetings)} driver meetings total")
            
        except Exception as e:
            print(f"[Ladbrokes] ❌ Driver Error: {str(e)[:80]}")
        finally:
            if browser: await browser.close()
            if playwright: await playwright.stop()
        
        return meetings


# =====================================================
# POINTSBET SCRAPER - SPECIALS SECTION!
# =====================================================

class PointsBetScraper(BaseScraper):
    async def get_all_jockey_data(self):
        meetings = []
        playwright = browser = context = None
        
        try:
            playwright, browser, context = await self.get_browser()
            page = await context.new_page()
            
            print("[PointsBet] Navigating to racing...")
            await page.goto('https://pointsbet.com.au/racing', timeout=30000)
            await asyncio.sleep(4)
            
            # Click on Specials tab
            try:
                await page.click('text="Specials"', timeout=5000)
                await asyncio.sleep(2)
                print("[PointsBet] Clicked Specials tab")
            except:
                # Try alternative
                try:
                    await page.click('[data-testid="specials-tab"]', timeout=3000)
                    await asyncio.sleep(2)
                except:
                    print("[PointsBet] ⚠️ Could not find Specials tab")
            
            # Scroll to load content
            for _ in range(5):
                await page.evaluate('window.scrollBy(0, 500)')
                await asyncio.sleep(0.3)
            
            text = await page.evaluate('document.body.innerText')
            
            # Find Jockey Challenge patterns
            patterns = [
                r'Jockey Challenge - ([A-Za-z ]+)',
                r'([A-Za-z]+) Jockey Challenge',
            ]
            
            meeting_names = []
            for pattern in patterns:
                found = re.findall(pattern, text)
                meeting_names.extend(found)
            
            meeting_names = list(dict.fromkeys([m.strip() for m in meeting_names if len(m) > 2]))[:5]
            print(f"[PointsBet] Found jockey meetings: {meeting_names}")
            
            for meeting in meeting_names:
                try:
                    # Try different click patterns
                    try:
                        await page.click(f'text="Jockey Challenge - {meeting}"', timeout=2000)
                    except:
                        await page.click(f'text="{meeting} Jockey Challenge"', timeout=2000)
                    
                    await asyncio.sleep(2)
                    
                    text = await page.evaluate('document.body.innerText')
                    lines = text.split('\n')
                    
                    jockeys = []
                    for i, line in enumerate(lines):
                        line = line.strip()
                        try:
                            odds = float(line)
                            if 1.01 < odds < 500:
                                for offset in [1, 2]:
                                    if i >= offset:
                                        name = lines[i-offset].strip()
                                        if name and len(name) > 3 and ' ' in name:
                                            if not any(c.isdigit() for c in name):
                                                if 'Challenge' not in name and 'Any Other' not in name:
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
                            'source': 'pointsbet',
                            'country': get_country(meeting)
                        })
                        print(f"[PointsBet] ✅ {meeting} ({get_country(meeting)}): {len(jockeys)} jockeys")
                    
                    # Go back
                    await page.goto('https://pointsbet.com.au/racing')
                    await asyncio.sleep(1)
                    try:
                        await page.click('text="Specials"', timeout=3000)
                        await asyncio.sleep(1)
                    except:
                        pass
                    
                except Exception as e:
                    print(f"[PointsBet] ⚠️ {meeting}: {str(e)[:40]}")
            
            print(f"[PointsBet] ✅ {len(meetings)} jockey meetings total")
            
        except Exception as e:
            print(f"[PointsBet] ❌ Error: {str(e)[:80]}")
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
            
            print("[PointsBet] Navigating for driver challenges...")
            await page.goto('https://pointsbet.com.au/racing', timeout=30000)
            await asyncio.sleep(4)
            
            # Click Specials
            try:
                await page.click('text="Specials"', timeout=5000)
                await asyncio.sleep(2)
            except:
                pass
            
            # Scroll more
            for _ in range(8):
                await page.evaluate('window.scrollBy(0, 500)')
                await asyncio.sleep(0.3)
            
            text = await page.evaluate('document.body.innerText')
            
            # Find Driver Challenge patterns
            patterns = [
                r'Driver Challenge - ([A-Za-z0-9 \(\)]+)',
                r'([A-Za-z]+) Driver Challenge',
            ]
            
            meeting_names = []
            for pattern in patterns:
                found = re.findall(pattern, text)
                meeting_names.extend(found)
            
            meeting_names = list(dict.fromkeys([m.strip() for m in meeting_names if len(m) > 2]))[:5]
            print(f"[PointsBet] Found driver meetings: {meeting_names}")
            
            for meeting in meeting_names:
                try:
                    try:
                        await page.click(f'text="Driver Challenge - {meeting}"', timeout=2000)
                    except:
                        await page.click(f'text="{meeting} Driver Challenge"', timeout=2000)
                    
                    await asyncio.sleep(2)
                    
                    text = await page.evaluate('document.body.innerText')
                    lines = text.split('\n')
                    
                    drivers = []
                    for i, line in enumerate(lines):
                        line = line.strip()
                        try:
                            odds = float(line)
                            if 1.01 < odds < 500:
                                for offset in [1, 2]:
                                    if i >= offset:
                                        name = lines[i-offset].strip()
                                        if name and len(name) > 3:
                                            if not any(c.isdigit() for c in name):
                                                if 'Challenge' not in name:
                                                    if not any(d['name'] == name for d in drivers):
                                                        drivers.append({'name': name, 'odds': odds})
                                                        break
                        except:
                            pass
                    
                    if drivers:
                        clean_meeting = meeting.replace(' (H)', '').upper()
                        meetings.append({
                            'meeting': clean_meeting,
                            'type': 'driver',
                            'drivers': drivers,
                            'source': 'pointsbet',
                            'country': get_country(clean_meeting)
                        })
                        print(f"[PointsBet] ✅ {meeting} ({get_country(clean_meeting)}) Driver: {len(drivers)} drivers")
                    
                except Exception as e:
                    print(f"[PointsBet] ⚠️ Driver {meeting}: {str(e)[:40]}")
            
            print(f"[PointsBet] ✅ {len(meetings)} driver meetings total")
            
        except Exception as e:
            print(f"[PointsBet] ❌ Driver Error: {str(e)[:80]}")
        finally:
            if browser: await browser.close()
            if playwright: await playwright.stop()
        
        return meetings


# =====================================================
# 🚀 MAIN FETCH - ALL BOOKMAKERS!
# =====================================================

async def fetch_all_data():
    global CACHE
    
    if CACHE['is_scraping']:
        print("⏳ Already scraping, returning cached data...")
        return get_cached_data()
    
    CACHE['is_scraping'] = True
    print("\n🚀 Starting scrape from ALL bookmakers...\n")
    
    jockey_meetings = []
    driver_meetings = []
    
    try:
        # TAB
        try:
            data = await TABScraper().get_all_jockey_data()
            jockey_meetings.extend(data)
        except Exception as e:
            print(f"TAB error: {e}")
        
        # Elitebet
        try:
            data = await ElitebetScraper().get_all_jockey_data()
            jockey_meetings.extend(data)
        except Exception as e:
            print(f"Elitebet error: {e}")
        
        # Sportsbet Jockey
        try:
            data = await SportsbetScraper().get_all_jockey_data()
            jockey_meetings.extend(data)
        except Exception as e:
            print(f"Sportsbet jockey error: {e}")
        
        # Sportsbet Driver
        try:
            data = await SportsbetScraper().get_all_driver_data()
            driver_meetings.extend(data)
        except Exception as e:
            print(f"Sportsbet driver error: {e}")
        
        # TABtouch
        try:
            data = await TABtouchScraper().get_all_jockey_data()
            jockey_meetings.extend(data)
        except Exception as e:
            print(f"TABtouch error: {e}")
        
        # Ladbrokes Jockey
        try:
            data = await LadbrokesScraper().get_all_jockey_data()
            jockey_meetings.extend(data)
        except Exception as e:
            print(f"Ladbrokes jockey error: {e}")
        
        # Ladbrokes Driver
        try:
            data = await LadbrokesScraper().get_all_driver_data()
            driver_meetings.extend(data)
        except Exception as e:
            print(f"Ladbrokes driver error: {e}")
        
        # PointsBet Jockey
        try:
            data = await PointsBetScraper().get_all_jockey_data()
            jockey_meetings.extend(data)
        except Exception as e:
            print(f"PointsBet jockey error: {e}")
        
        # PointsBet Driver
        try:
            data = await PointsBetScraper().get_all_driver_data()
            driver_meetings.extend(data)
        except Exception as e:
            print(f"PointsBet driver error: {e}")
        
        # Update cache
        CACHE['jockey_challenges'] = jockey_meetings
        CACHE['driver_challenges'] = driver_meetings
        CACHE['last_updated'] = datetime.now().isoformat()
        
        print(f"\n✅ SCRAPE COMPLETE!")
        print(f"   Jockey meetings: {len(jockey_meetings)}")
        print(f"   Driver meetings: {len(driver_meetings)}\n")
        
    except Exception as e:
        print(f"❌ Scrape error: {e}")
    finally:
        CACHE['is_scraping'] = False
    
    return {
        'jockey_challenges': jockey_meetings,
        'driver_challenges': driver_meetings,
        'last_updated': CACHE['last_updated']
    }