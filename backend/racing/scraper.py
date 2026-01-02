import asyncio
from playwright.async_api import async_playwright
import re

class TABScraper:
    def __init__(self):
        self.jockey_url = "https://www.tab.com.au/sports/betting/Jockey%20Challenge"
        self.driver_url = "https://www.tab.com.au/sports/betting/Driver%20Challenge"
    
    async def get_browser(self):
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        )
        return playwright, browser, context
    
    async def get_all_jockey_data(self):
        playwright, browser, context = await self.get_browser()
        meetings = []
        
        try:
            page = await context.new_page()
            await page.goto(self.jockey_url, wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(5)
            
            for _ in range(3):
                await page.evaluate('window.scrollBy(0, 500)')
                await asyncio.sleep(1)
            
            text = await page.evaluate('document.body.innerText')
            lines = text.split('\n')
            
            current_meeting = None
            jockeys = []
            
            for line in lines:
                line = line.strip()
                
                if 'MstPts' in line:
                    if current_meeting and jockeys:
                        meetings.append({
                            'meeting': current_meeting,
                            'type': 'jockey',
                            'jockeys': jockeys.copy()
                        })
                    
                    match = re.search(r'MstPts\s+([A-Z][A-Za-z\s]+?)(?:\s|$)', line)
                    if match:
                        current_meeting = match.group(1).strip()[:20]
                    jockeys = []
                    continue
                
                skip_words = ['MENU', 'Market', 'Challenge', 'Next', 'Featured', 
                             'Competitions', 'In-Play', 'Flucs', 'Entrant', 'Win', 'Place',
                             'TAB', 'Login', 'Join', 'Bet', 'Search', 'JOCK']
                if any(skip in line for skip in skip_words):
                    continue
                
                if current_meeting and line:
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            odds = float(parts[-1])
                            if 1.01 < odds < 500:
                                name = ' '.join(parts[:-1])
                                if len(name) > 2 and not name.isdigit():
                                    jockeys.append({'name': name, 'odds': odds})
                        except ValueError:
                            pass
            
            if current_meeting and jockeys:
                meetings.append({
                    'meeting': current_meeting,
                    'type': 'jockey',
                    'jockeys': jockeys
                })
        
        except Exception as e:
            print(f"TAB Jockey Error: {e}")
        finally:
            await browser.close()
            await playwright.stop()
        
        return meetings

    async def get_all_driver_data(self):
        playwright, browser, context = await self.get_browser()
        meetings = []
        
        try:
            page = await context.new_page()
            await page.goto(self.driver_url, wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(5)
            
            for _ in range(3):
                await page.evaluate('window.scrollBy(0, 500)')
                await asyncio.sleep(1)
            
            text = await page.evaluate('document.body.innerText')
            lines = text.split('\n')
            
            current_meeting = None
            drivers = []
            
            for line in lines:
                line = line.strip()
                
                if 'MstPts' in line:
                    if current_meeting and drivers:
                        meetings.append({
                            'meeting': current_meeting,
                            'type': 'driver',
                            'jockeys': drivers.copy()
                        })
                    
                    match = re.search(r'MstPts\s+([A-Z][A-Za-z\s]+?)(?:\s|$)', line)
                    if match:
                        current_meeting = match.group(1).strip()[:20]
                    drivers = []
                    continue
                
                skip_words = ['MENU', 'Market', 'Challenge', 'Next', 'Featured', 
                             'Competitions', 'In-Play', 'Flucs', 'Entrant', 'Win', 'Place',
                             'TAB', 'Login', 'Join', 'Bet', 'Search', 'DRIVER']
                if any(skip in line for skip in skip_words):
                    continue
                
                if current_meeting and line:
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            odds = float(parts[-1])
                            if 1.01 < odds < 500:
                                name = ' '.join(parts[:-1])
                                if len(name) > 2 and not name.isdigit():
                                    drivers.append({'name': name, 'odds': odds})
                        except ValueError:
                            pass
            
            if current_meeting and drivers:
                meetings.append({
                    'meeting': current_meeting,
                    'type': 'driver',
                    'jockeys': drivers
                })
        
        except Exception as e:
            print(f"TAB Driver Error: {e}")
        finally:
            await browser.close()
            await playwright.stop()
        
        return meetings


if __name__ == "__main__":
    async def main():
        scraper = TABScraper()
        print("Testing Jockey...")
        j = await scraper.get_all_jockey_data()
        print(f"Found {len(j)} jockey meetings")
        for m in j:
            print(f"  {m['meeting']}: {len(m['jockeys'])} jockeys")
        
        print("\nTesting Driver...")
        d = await scraper.get_all_driver_data()
        print(f"Found {len(d)} driver meetings")
        for m in d:
            print(f"  {m['meeting']}: {len(m['jockeys'])} drivers")
    
    asyncio.run(main())
