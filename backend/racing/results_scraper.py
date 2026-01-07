import asyncio
import re
from datetime import datetime
from playwright.async_api import async_playwright

class ResultsScraper:
    
    async def get_browser(self):
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=True, args=['--no-sandbox'])
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            locale='en-AU', timezone_id='Australia/Sydney'
        )
        return playwright, browser, context
    
    async def get_meeting_results(self, meeting_name):
        playwright = browser = context = None
        meeting_results = {'meeting': meeting_name.upper(), 'races': [], 'last_updated': datetime.now().isoformat()}
        
        try:
            playwright, browser, context = await self.get_browser()
            page = await context.new_page()
            
            print(f"[Results] Fetching {meeting_name}...")
            await page.goto('https://www.ladbrokes.com.au/racing/results', timeout=60000)
            await asyncio.sleep(5)
            
            text = await page.evaluate('document.body.innerText')
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            
            # Find meeting
            meeting_idx = None
            for i, line in enumerate(lines):
                if line.lower() == meeting_name.lower():
                    meeting_idx = i
                    break
            
            if not meeting_idx:
                print(f"[Results] {meeting_name} not found")
                return meeting_results
            
            print(f"[Results] Found at line {meeting_idx}")
            
            # Get completed races
            completed = []
            for i in range(meeting_idx + 2, min(meeting_idx + 20, len(lines))):
                if lines[i] in ['VIC','NSW','QLD','SA','WA','TAS','NT','NZ','HK'] and i > meeting_idx + 2:
                    break
                m = re.match(r'^R(\d+)$', lines[i])
                if m and i+1 < len(lines):
                    if re.match(r'^\d+[/\d]*,\s*\d+,\s*\d+', lines[i+1]) or lines[i+1] == 'Final':
                        completed.append(int(m.group(1)))
            
            print(f"[Results] Completed races: {completed}")
            
            # Fetch each race
            for rnum in completed:
                try:
                    await page.goto('https://www.ladbrokes.com.au/racing/results', timeout=30000)
                    await asyncio.sleep(2)
                    await page.click(f'text="{meeting_name.title()}"', timeout=5000)
                    await asyncio.sleep(2)
                    await page.click(f'text="R{rnum}"', timeout=3000)
                    await asyncio.sleep(2)
                    
                    txt = await page.evaluate('document.body.innerText')
                    lns = [l.strip() for l in txt.split('\n') if l.strip()]
                    
                    results = []
                    for idx, ln in enumerate(lns):
                        pm = re.match(r'^(\d+)\.$', ln)
                        if pm:
                            pos = int(pm.group(1))
                            for k in range(idx+1, min(idx+12, len(lns))):
                                jm = re.match(r'^J:\s*(.+?)(?:\s*\([^)]+\))?$', lns[k])
                                if jm:
                                    results.append({'position': pos, 'jockey': jm.group(1).strip()})
                                    break
                    
                    results.sort(key=lambda x: x['position'])
                    if results:
                        meeting_results['races'].append({'race': rnum, 'results': results[:3]})
                        print(f"[Results] R{rnum}: {[r['jockey'] for r in results[:3]]}")
                except Exception as e:
                    print(f"[Results] R{rnum} err: {str(e)[:30]}")
            
            print(f"[Results] Done: {len(meeting_results['races'])} races")
        except Exception as e:
            print(f"[Results] Error: {e}")
        finally:
            if browser: await browser.close()
            if playwright: await playwright.stop()
        return meeting_results

async def fetch_race_results(meeting_name):
    return await ResultsScraper().get_meeting_results(meeting_name)
