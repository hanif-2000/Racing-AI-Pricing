# racing/scraper.py - WITH CACHING FOR INSTANT LOADING

import asyncio
import re
import json
import os
from datetime import datetime
from playwright.async_api import async_playwright

# =====================================================
# 📦 IN-MEMORY CACHE - Instant response!
# =====================================================

CACHE = {
    'jockey_challenges': [],
    'driver_challenges': [],
    'last_updated': None,
    'is_scraping': False
}


def get_cached_data():
    """Get cached data instantly"""
    return {
        'jockey_challenges': CACHE['jockey_challenges'],
        'driver_challenges': CACHE['driver_challenges'],
        'last_updated': CACHE['last_updated'],
        'from_cache': True
    }


def has_cached_data():
    """Check if we have cached data"""
    return len(CACHE['jockey_challenges']) > 0 or len(CACHE['driver_challenges']) > 0


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


class TABScraper(BaseScraper):
    async def get_all_jockey_data(self):
        meetings = []
        playwright = browser = context = None
        
        try:
            playwright, browser, context = await self.get_browser()
            page = await context.new_page()
            
            await page.goto("https://www.tab.com.au/sports/betting/Jockey%20Challenge/competitions/Jockey%20Challenge", 
                          wait_until='domcontentloaded', timeout=30000)
            
            content = await page.content()
            if 'Access Denied' in content:
                return []
            
            await asyncio.sleep(8)
            
            for _ in range(3):
                await page.evaluate('window.scrollBy(0, 500)')
                await asyncio.sleep(0.5)
            
            text = await page.evaluate('document.body.innerText')
            
            if 'JOCK MstPts' not in text:
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
                            meetings.append({'meeting': current_meeting, 'type': 'jockey', 'jockeys': jockeys.copy(), 'source': 'tab'})
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
                meetings.append({'meeting': current_meeting, 'type': 'jockey', 'jockeys': jockeys, 'source': 'tab'})
            
            print(f"[TAB] ✅ {len(meetings)} meetings")
            
        except Exception as e:
            print(f"[TAB] ❌ Error: {e}")
        finally:
            if browser: await browser.close()
            if playwright: await playwright.stop()
        
        return meetings


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
                return []
            
            text = await page.evaluate('document.body.innerText')
            lines = text.split('\n')
            
            meeting_names = []
            skip_list = ['Jockey Challenge', 'Futures', 'Today', 'Tomorrow', 'Monday', 'Tuesday', 
                        'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday', 'Help', 
                        'Promotions', 'Ice Hockey', 'NBA', 'NFL']
            
            for i, line in enumerate(lines):
                line = line.strip()
                months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
                if any(m in line for m in months):
                    for j in range(i-1, max(0, i-5), -1):
                        prev = lines[j].strip()
                        if prev and len(prev) > 3 and not any(c.isdigit() for c in prev):
                            if prev not in skip_list:
                                meeting_names.append(prev)
                                break
            
            meeting_names = list(dict.fromkeys(meeting_names))[:3]
            
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
                        meetings.append({'meeting': meeting.upper(), 'type': 'jockey', 'jockeys': jockeys, 'source': 'elitebet'})
                        print(f"[Elitebet] ✅ {meeting}: {len(jockeys)} jockeys")
                    
                    await page.goto('https://www.elitebet.com.au/racing')
                    await asyncio.sleep(1)
                    await page.click('text="Jockey Challenge"', timeout=3000)
                    await asyncio.sleep(1)
                    
                except:
                    pass
            
            print(f"[Elitebet] ✅ {len(meetings)} meetings total")
            
        except Exception as e:
            print(f"[Elitebet] ❌ Error: {e}")
        finally:
            if browser: await browser.close()
            if playwright: await playwright.stop()
        
        return meetings


class SportsbetScraper(BaseScraper):
    async def get_all_jockey_data(self):
        meetings = []
        playwright = browser = context = None
        
        try:
            playwright, browser, context = await self.get_browser()
            page = await context.new_page()
            
            await page.goto('https://www.sportsbet.com.au/horse-racing', timeout=30000)
            await asyncio.sleep(3)
            
            try:
                await page.click('text="Extras"', timeout=5000)
                await asyncio.sleep(2)
            except:
                pass
            
            for _ in range(3):
                await page.evaluate('window.scrollBy(0, 500)')
                await asyncio.sleep(0.5)
            
            text = await page.evaluate('document.body.innerText')
            
            pattern = r'Jockey Challenge - ([A-Za-z ]+)'
            meeting_names = re.findall(pattern, text)
            meeting_names = list(dict.fromkeys([m.strip() for m in meeting_names]))[:3]
            
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
                                                skip = ['Jockey Challenge', 'Driver Challenge', 'Any Other', 'Back', 'Lay']
                                                if not any(s in name for s in skip):
                                                    if not any(j['name'] == name for j in jockeys):
                                                        jockeys.append({'name': name, 'odds': odds})
                                                        break
                        except:
                            pass
                    
                    if jockeys:
                        meetings.append({'meeting': meeting.upper(), 'type': 'jockey', 'jockeys': jockeys, 'source': 'sportsbet'})
                        print(f"[Sportsbet] ✅ {meeting}: {len(jockeys)} jockeys")
                    
                    await page.goto('https://www.sportsbet.com.au/horse-racing')
                    await asyncio.sleep(1)
                    try:
                        await page.click('text="Extras"', timeout=3000)
                        await asyncio.sleep(1)
                    except:
                        pass
                        
                except:
                    pass
            
            print(f"[Sportsbet] ✅ {len(meetings)} jockey meetings total")
            
        except Exception as e:
            print(f"[Sportsbet] ❌ Error: {e}")
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
            
            await page.goto('https://www.sportsbet.com.au/horse-racing', timeout=30000)
            await asyncio.sleep(3)
            
            try:
                await page.click('text="Extras"', timeout=5000)
                await asyncio.sleep(2)
            except:
                pass
            
            for _ in range(5):
                await page.evaluate('window.scrollBy(0, 500)')
                await asyncio.sleep(0.5)
            
            text = await page.evaluate('document.body.innerText')
            
            pattern = r'([A-Za-z ]+) Driver Challenge'
            meeting_names = re.findall(pattern, text)
            meeting_names = [m.strip() for m in meeting_names if 'Harness' not in m]
            meeting_names = list(dict.fromkeys(meeting_names))[:3]
            
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
                        meetings.append({'meeting': meeting.upper(), 'type': 'driver', 'drivers': drivers, 'source': 'sportsbet'})
                        print(f"[Sportsbet] ✅ {meeting} (Driver): {len(drivers)} drivers")
                        
                except:
                    pass
            
            print(f"[Sportsbet] ✅ {len(meetings)} driver meetings total")
            
        except Exception as e:
            print(f"[Sportsbet] ❌ Driver Error: {e}")
        finally:
            if browser: await browser.close()
            if playwright: await playwright.stop()
        
        return meetings


class TABtouchScraper(BaseScraper):
    async def get_all_jockey_data(self):
        meetings = []
        playwright = browser = context = None
        
        try:
            playwright, browser, context = await self.get_browser()
            page = await context.new_page()
            
            await page.goto('https://www.tabtouch.com.au/racing/jockey-challenge', timeout=30000)
            await asyncio.sleep(4)
            
            for _ in range(3):
                await page.evaluate('window.scrollBy(0, 500)')
                await asyncio.sleep(0.5)
            
            text = await page.evaluate('document.body.innerText')
            meetings_found = re.findall(r'([A-Za-z ]+) Jockey Challenge 3,2,1 Points', text)
            meetings_found = list(dict.fromkeys([m.strip() for m in meetings_found]))[:5]
            
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
                            if 1 < odds < 100 and i >= 1:
                                name_line = lines[i-1].strip()
                                name = re.sub(r'\s*\d+\s*$', '', name_line).strip()
                                if name and 'ANY OTHER' not in name.upper() and len(name) > 3:
                                    if not any(j['name'] == name for j in jockeys):
                                        jockeys.append({'name': name, 'odds': odds})
                        except:
                            pass
                    
                    if jockeys:
                        meetings.append({'meeting': meeting.upper(), 'type': 'jockey', 'jockeys': jockeys, 'source': 'tabtouch'})
                        print(f"[TABtouch] ✅ {meeting}: {len(jockeys)} jockeys")
                    
                except:
                    pass
            
            print(f"[TABtouch] ✅ {len(meetings)} meetings total")
            
        except Exception as e:
            print(f"[TABtouch] ❌ Error: {e}")
        finally:
            if browser: await browser.close()
            if playwright: await playwright.stop()
        
        return meetings


class LadbrokesScraper(BaseScraper):
    async def get_all_jockey_data(self):
        # Simplified - just return empty for now to speed up
        return []
    
    async def get_all_driver_data(self):
        return []


# =====================================================
# 🚀 MAIN FETCH FUNCTION - WITH CACHING
# =====================================================

async def fetch_all_data():
    """Fetch from all bookmakers and update cache"""
    global CACHE
    
    if CACHE['is_scraping']:
        print("⏳ Already scraping, returning cached data...")
        return get_cached_data()
    
    CACHE['is_scraping'] = True
    print("\n🚀 Starting scrape from all bookmakers...\n")
    
    jockey_meetings = []
    driver_meetings = []
    
    try:
        # TAB
        try:
            tab = TABScraper()
            data = await tab.get_all_jockey_data()
            jockey_meetings.extend(data)
        except Exception as e:
            print(f"TAB error: {e}")
        
        # Elitebet
        try:
            elite = ElitebetScraper()
            data = await elite.get_all_jockey_data()
            jockey_meetings.extend(data)
        except Exception as e:
            print(f"Elitebet error: {e}")
        
        # Sportsbet Jockey
        try:
            sportsbet = SportsbetScraper()
            data = await sportsbet.get_all_jockey_data()
            jockey_meetings.extend(data)
        except Exception as e:
            print(f"Sportsbet jockey error: {e}")
        
        # Sportsbet Driver
        try:
            sportsbet = SportsbetScraper()
            data = await sportsbet.get_all_driver_data()
            driver_meetings.extend(data)
        except Exception as e:
            print(f"Sportsbet driver error: {e}")
        
        # TABtouch
        try:
            tabtouch = TABtouchScraper()
            data = await tabtouch.get_all_jockey_data()
            jockey_meetings.extend(data)
        except Exception as e:
            print(f"TABtouch error: {e}")
        
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