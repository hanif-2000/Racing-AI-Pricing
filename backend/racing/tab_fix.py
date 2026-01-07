# Read and fix TAB scraper in scraper.py

with open('scraper.py', 'r') as f:
    content = f.read()

# Find and replace TABScraper class
old_tab_class = '''class TABScraper(BaseScraper):
    async def get_all_jockey_data(self):
        meetings = []
        playwright = browser = context = None
        
        try:
            playwright, browser, context = await self.get_browser()
            page = await context.new_page()
            
            print("[TAB] Navigating...")
            await page.goto("https://www.tab.com.au/sports/betting/Jockey%20Challenge/competitions/Jockey%20Challenge", 
                          wait_until='domcontentloaded', timeout=60000)
            
            content = await page.content()
            if 'Access Denied' in content:
                print("[TAB] ❌ Access Denied")
                return []
            
            await asyncio.sleep(8)'''

new_tab_class = '''class TABScraper(BaseScraper):
    async def get_all_jockey_data(self):
        meetings = []
        playwright = browser = context = None
        
        try:
            # Custom browser setup for TAB (needs extra anti-detection)
            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-web-security',
                    '--disable-features=IsolateOrigins,site-per-process'
                ]
            )
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='en-AU',
                timezone_id='Australia/Sydney',
                java_script_enabled=True,
            )
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-AU', 'en']});
                window.chrome = { runtime: {} };
            """)
            page = await context.new_page()
            
            print("[TAB] Navigating...")
            
            # First load main page to get cookies
            await page.goto("https://www.tab.com.au/", wait_until='domcontentloaded', timeout=60000)
            await asyncio.sleep(3)
            
            # Then navigate to jockey challenge
            await page.goto("https://www.tab.com.au/sports/betting/Jockey%20Challenge/competitions/Jockey%20Challenge", 
                          wait_until='domcontentloaded', timeout=60000)
            
            await asyncio.sleep(8)
            
            content = await page.content()
            if 'Access Denied' in content:
                print("[TAB] ❌ Access Denied")
                return []'''

content = content.replace(old_tab_class, new_tab_class)

with open('scraper.py', 'w') as f:
    f.write(content)

print('✅ TAB scraper updated with better anti-detection!')
