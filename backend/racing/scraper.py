# racing/scraper.py - Full Code with Dynamic Meetings

import asyncio
import re
from playwright.async_api import async_playwright


class BaseScraper:
    async def get_browser(self):
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            headless=False,
            args=['--disable-blink-features=AutomationControlled']
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
    """TAB.com.au - WORKING"""
    
    async def get_all_jockey_data(self):
        for attempt in range(3):
            print(f"[TAB] Attempt {attempt + 1}/3...")
            meetings = await self._fetch()
            if meetings:
                return meetings
            await asyncio.sleep(3)
        return []
    
    async def _fetch(self):
        meetings = []
        playwright = browser = context = None
        
        try:
            playwright, browser, context = await self.get_browser()
            page = await context.new_page()
            print(f"[TAB] Navigating...")
            
            await page.goto("https://www.tab.com.au/sports/betting/Jockey%20Challenge/competitions/Jockey%20Challenge", 
                          wait_until='domcontentloaded', timeout=30000)
            
            content = await page.content()
            if 'Access Denied' in content:
                print(f"[TAB] ❌ Access Denied")
                return []
            
            print(f"[TAB] Waiting for content...")
            await asyncio.sleep(10)
            
            for _ in range(5):
                await page.evaluate('window.scrollBy(0, 500)')
                await asyncio.sleep(1)
            
            text = await page.evaluate('document.body.innerText')
            
            if 'JOCK MstPts' not in text:
                print(f"[TAB] ❌ Content not found")
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
    """Elitebet - WORKING"""
    
    async def get_all_jockey_data(self):
        meetings = []
        playwright = browser = context = None
        
        try:
            playwright, browser, context = await self.get_browser()
            page = await context.new_page()
            
            print(f"[Elitebet] Navigating...")
            await page.goto('https://www.elitebet.com.au/racing', timeout=30000)
            await asyncio.sleep(4)
            
            await page.click('text="Jockey Challenge"')
            print(f"[Elitebet] Clicked Jockey Challenge")
            await asyncio.sleep(3)
            
            text = await page.evaluate('document.body.innerText')
            lines = text.split('\n')
            
            meeting_names = []
            for i, line in enumerate(lines):
                line = line.strip()
                if 'Jan' in line or 'Feb' in line or 'Mar' in line or 'Apr' in line or 'May' in line or 'Jun' in line or 'Jul' in line or 'Aug' in line or 'Sep' in line or 'Oct' in line or 'Nov' in line or 'Dec' in line:
                    for j in range(i-1, max(0, i-5), -1):
                        prev = lines[j].strip()
                        if prev and len(prev) > 3 and not any(c.isdigit() for c in prev):
                            if prev not in ['Jockey Challenge', 'Futures', 'Today', 'Tomorrow', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday', 'Help']:
                                meeting_names.append(prev)
                                break
            
            meeting_names = list(dict.fromkeys(meeting_names))
            print(f"[Elitebet] Found meetings: {meeting_names}")
            
            for meeting in meeting_names:
                try:
                    await page.click(f'text="{meeting}"', timeout=5000)
                    await asyncio.sleep(3)
                    
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
                                    jockeys.append({'name': name, 'odds': odds})
                        except:
                            pass
                    
                    if jockeys:
                        meetings.append({'meeting': meeting.upper(), 'type': 'jockey', 'jockeys': jockeys, 'source': 'elitebet'})
                        print(f"[Elitebet] ✅ {meeting}: {len(jockeys)} jockeys")
                    
                    await page.goto('https://www.elitebet.com.au/racing')
                    await asyncio.sleep(2)
                    await page.click('text="Jockey Challenge"')
                    await asyncio.sleep(2)
                    
                except Exception as e:
                    print(f"[Elitebet] ⏭️ {meeting}: skipped")
            
            print(f"[Elitebet] ✅ {len(meetings)} meetings total")
            
        except Exception as e:
            print(f"[Elitebet] ❌ Error: {e}")
        finally:
            if browser: await browser.close()
            if playwright: await playwright.stop()
        
        return meetings


class LadbrokesScraper(BaseScraper):
    """Ladbrokes - WORKING - Dynamic Meetings"""
    
    async def get_all_jockey_data(self):
        meetings = []
        playwright = browser = context = None
        
        try:
            playwright, browser, context = await self.get_browser()
            page = await context.new_page()
            
            print(f"[Ladbrokes] Navigating...")
            await page.goto('https://www.ladbrokes.com.au/racing/extras', timeout=30000)
            await asyncio.sleep(5)
            
            # Scroll to load all content
            for _ in range(3):
                await page.evaluate('window.scrollBy(0, 500)')
                await asyncio.sleep(1)
            await page.evaluate('window.scrollTo(0, 0)')
            await asyncio.sleep(2)
            
            # Get meeting names dynamically from Horse Racing section
            text = await page.evaluate('document.body.innerText')
            
            # Find meetings under Horse Racing that have Jockey Challenge
            meeting_names = []
            lines = text.split('\n')
            in_horse_racing = False
            
            for i, line in enumerate(lines):
                line = line.strip()
                if 'Horse Racing' in line:
                    in_horse_racing = True
                    continue
                if 'Greyhounds' in line or 'Harness Racing' in line:
                    in_horse_racing = False
                    continue
                if in_horse_racing and line and len(line) > 2:
                    # Skip non-meeting lines
                    skip_words = ['keyboard_arrow', 'INTL', 'Horse Racing', 'Jockey Challenge', 'To Ride', 'Winners', 'Finishes']
                    if not any(skip in line for skip in skip_words):
                        if line[0].isupper() and not any(c.isdigit() for c in line):
                            meeting_names.append(line)
            
            meeting_names = list(dict.fromkeys(meeting_names))
            print(f"[Ladbrokes] Found meetings: {meeting_names}")
            
            for meeting in meeting_names:
                try:
                    # Fresh page each time
                    await page.goto('https://www.ladbrokes.com.au/racing/extras')
                    await asyncio.sleep(3)
                    
                    # Click meeting row to expand
                    row = page.locator(f'div:has-text("{meeting}"):has-text("keyboard_arrow")').first
                    await row.click(timeout=3000)
                    await asyncio.sleep(2)
                    
                    # Check if Jockey Challenge exists
                    text = await page.evaluate('document.body.innerText')
                    if 'Jockey Challenge' not in text:
                        continue
                    
                    # Click Jockey Challenge
                    await page.click('text=/Jockey Challenge/i', timeout=3000)
                    await asyncio.sleep(3)
                    
                    text = await page.evaluate('document.body.innerText')
                    lines = text.split('\n')
                    
                    jockeys = []
                    for i, line in enumerate(lines):
                        line = line.strip()
                        try:
                            odds = float(line)
                            if 1 < odds < 200:
                                for offset in [1, 2, 3]:
                                    if i >= offset:
                                        name = lines[i-offset].strip()
                                        if name and ' ' in name and len(name) > 5:
                                            if not any(c.isdigit() for c in name):
                                                if name not in ['Win', 'Place', 'Jockey Challenge']:
                                                    if not any(j['name'] == name for j in jockeys):
                                                        jockeys.append({'name': name, 'odds': odds})
                                                        break
                        except:
                            pass
                    
                    if jockeys:
                        meetings.append({'meeting': meeting.upper(), 'type': 'jockey', 'jockeys': jockeys, 'source': 'ladbrokes'})
                        print(f"[Ladbrokes] ✅ {meeting}: {len(jockeys)} jockeys")
                    
                except Exception as e:
                    print(f"[Ladbrokes] ⏭️ {meeting}: skipped")
            
            print(f"[Ladbrokes] ✅ {len(meetings)} meetings total")
            
        except Exception as e:
            print(f"[Ladbrokes] ❌ Error: {e}")
        finally:
            if browser: await browser.close()
            if playwright: await playwright.stop()
        
        return meetings


class TABtouchScraper(BaseScraper):
    """TABtouch - WORKING - Dynamic Meetings"""
    
    async def get_all_jockey_data(self):
        meetings = []
        playwright = browser = context = None
        
        try:
            playwright, browser, context = await self.get_browser()
            page = await context.new_page()
            
            print(f"[TABtouch] Navigating...")
            await page.goto('https://www.tabtouch.com.au/racing/jockey-challenge', timeout=30000)
            await asyncio.sleep(5)
            
            # Scroll to load all
            for _ in range(5):
                await page.evaluate('window.scrollBy(0, 500)')
                await asyncio.sleep(1)
            await page.evaluate('window.scrollTo(0, 0)')
            await asyncio.sleep(2)
            
            text = await page.evaluate('document.body.innerText')
            meetings_found = re.findall(r'([A-Za-z ]+) Jockey Challenge 3,2,1 Points', text)
            meetings_found = list(dict.fromkeys([m.strip() for m in meetings_found]))
            print(f"[TABtouch] Found meetings: {meetings_found}")
            
            for meeting in meetings_found:
                try:
                    await page.goto('https://www.tabtouch.com.au/racing/jockey-challenge')
                    await asyncio.sleep(4)
                    
                    await page.click(f'text="{meeting} Jockey Challenge 3,2,1 Points"', timeout=5000)
                    await asyncio.sleep(3)
                    
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
                                if name and 'ANY OTHER' not in name and len(name) > 3:
                                    jockeys.append({'name': name, 'odds': odds})
                        except:
                            pass
                    
                    if jockeys:
                        meetings.append({'meeting': meeting.upper(), 'type': 'jockey', 'jockeys': jockeys, 'source': 'tabtouch'})
                        print(f"[TABtouch] ✅ {meeting}: {len(jockeys)} jockeys")
                    
                except Exception as e:
                    print(f"[TABtouch] ⏭️ {meeting}: skipped")
            
            print(f"[TABtouch] ✅ {len(meetings)} meetings total")
            
        except Exception as e:
            print(f"[TABtouch] ❌ Error: {e}")
        finally:
            if browser: await browser.close()
            if playwright: await playwright.stop()
        
        return meetings


class AllBookmakersScraper:
    """Fetch from all bookmakers and combine"""
    
    async def get_all_odds(self):
        all_meetings = []
        
        # TAB
        tab = TABScraper()
        tab_data = await tab.get_all_jockey_data()
        all_meetings.extend(tab_data)
        
        # Elitebet
        elite = ElitebetScraper()
        elite_data = await elite.get_all_jockey_data()
        all_meetings.extend(elite_data)
        
        # Ladbrokes
        ladbrokes = LadbrokesScraper()
        ladbrokes_data = await ladbrokes.get_all_jockey_data()
        all_meetings.extend(ladbrokes_data)
        
        # TABtouch
        tabtouch = TABtouchScraper()
        tabtouch_data = await tabtouch.get_all_jockey_data()
        all_meetings.extend(tabtouch_data)
        
        return all_meetings