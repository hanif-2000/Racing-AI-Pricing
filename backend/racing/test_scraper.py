import asyncio
from playwright.async_api import async_playwright

async def debug_page():
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=False)  # Show browser
    context = await browser.new_context(
        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    )
    page = await context.new_page()
    
    url = "https://www.tab.com.au/sports/betting/Jockey%20Challenge/competitions/Jockey%20Challenge"
    print(f"Opening: {url}")
    
    await page.goto(url, wait_until='domcontentloaded', timeout=30000)
    await asyncio.sleep(5)
    
    # Scroll down
    for _ in range(3):
        await page.evaluate('window.scrollBy(0, 500)')
        await asyncio.sleep(1)
    
    # Get all text
    text = await page.evaluate('document.body.innerText')
    
    # Save to file
    with open('page_content.txt', 'w') as f:
        f.write(text)
    
    print("\n=== PAGE CONTENT (first 3000 chars) ===")
    print(text[:3000])
    print("\n=== Saved full content to page_content.txt ===")
    
    # Keep browser open for 30 seconds to see
    print("\nBrowser open for 30 seconds - check manually...")
    await asyncio.sleep(30)
    
    await browser.close()
    await playwright.stop()

asyncio.run(debug_page())
