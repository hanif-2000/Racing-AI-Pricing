import re

# Read current scraper
with open('scraper.py', 'r') as f:
    content = f.read()

# Find PointsBetScraper class and check current implementation
# We need to update the URL and parsing logic

# New PointsBet scraper implementation
new_pointsbet = '''class PointsBetScraper(BaseScraper):
    async def get_jockey_data(self):
        meetings = []
        playwright = browser = context = None
        
        try:
            playwright, browser, context = await self.get_browser()
            page = await context.new_page()
            
            print("[PointsBet] Navigating to specials...")
            await page.goto("https://pointsbet.com.au/racing?search=specials", 
                          wait_until='domcontentloaded', timeout=60000)
            await asyncio.sleep(5)
            
            # Get text to find Thoroughbred meetings
            text = await page.evaluate('document.body.innerText')
            
            # Find meeting names
            meeting_names = []
            for line in text.split('\\n'):
                if 'Thoroughbred Specials' in line and ' - ' in line:
                    match = re.match(r'([A-Za-z\\s]+)\\s*-\\s*Thoroughbred', line)
                    if match:
                        meeting_names.append(match.group(1).strip())
            
            print(f"[PointsBet] Found meetings: {meeting_names}")
            
            # Scrape each meeting
            for meeting_name in meeting_names:
                try:
                    # Navigate back to search
                    await page.goto("https://pointsbet.com.au/racing?search=specials", 
                                  wait_until='domcontentloaded', timeout=60000)
                    await asyncio.sleep(3)
                    
                    # Click on meeting
                    await page.click(f'text={meeting_name} - Thoroughbred Specials', timeout=5000)
                    await asyncio.sleep(3)
                    
                    # Get content
                    text = await page.evaluate('document.body.innerText')
                    lines = [l.strip() for l in text.split('\\n') if l.strip()]
                    
                    # Parse jockeys
                    jockeys = []
                    in_jockey = False
                    
                    for i, line in enumerate(lines):
                        if 'Jockey Challenge' in line:
                            in_jockey = True
                            continue
                        
                        if in_jockey:
                            if 'Trainer Challenge' in line or 'Jockey Win Specials' in line:
                                break
                            
                            if re.match(r'^\\d+\\.\\d{2}$', line):
                                odds = float(line)
                                if i > 0:
                                    name = lines[i-1]
                                    if name and len(name) > 2 and not re.match(r'^\\d', name):
                                        if 'see all' not in name.lower() and 'outcomes' not in name.lower():
                                            jockeys.append({'name': name, 'odds': odds})
                    
                    if jockeys:
                        country = 'NZ' if meeting_name.upper() in NZ_TRACKS else 'AU'
                        meetings.append({
                            'meeting': meeting_name.upper(),
                            'type': 'jockey',
                            'jockeys': jockeys,
                            'source': 'pointsbet',
                            'country': country
                        })
                        print(f"[PointsBet] ✅ {meeting_name} ({country}): {len(jockeys)} jockeys")
                    
                except Exception as e:
                    print(f"[PointsBet] ⚠️ {meeting_name}: {e}")
            
            print(f"[PointsBet] ✅ {len(meetings)} jockey meetings total")
            
        except Exception as e:
            print(f"[PointsBet] ❌ Error: {str(e)[:50]}")
        finally:
            if browser:
                await browser.close()
            if playwright:
                await playwright.stop()
        
        return meetings
    
    async def get_driver_data(self):
        # PointsBet doesn't have driver challenges
        print("[PointsBet] Driver challenges not available")
        return []'''

# Find and replace the PointsBetScraper class
# Look for the class definition
import re as regex
pattern = r'class PointsBetScraper\(BaseScraper\):.*?(?=class \w+Scraper\(|def fetch_all_data|$)'
match = regex.search(pattern, content, regex.DOTALL)

if match:
    old_class = match.group(0)
    # Keep any trailing content that might be needed
    content = content.replace(old_class, new_pointsbet + '\n\n')
    
    with open('scraper.py', 'w') as f:
        f.write(content)
    print('✅ PointsBetScraper updated!')
else:
    print('❌ Could not find PointsBetScraper class')
