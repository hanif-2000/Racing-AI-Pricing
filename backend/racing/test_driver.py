import asyncio
from playwright.async_api import async_playwright

async def debug_driver():
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=False)
    context = await browser.new_context(
        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    )
    page = await context.new_page()
    
    url = "https://www.tab.com.au/sports/betting/Driver%20Challenge/competitions/Driver%20Challenge"
    print(f"Opening: {url}")
    
    try:
        await page.goto(url, wait_until='commit', timeout=30000)
    except:
        pass
    
    await asyncio.sleep(10)
    
    text = await page.evaluate('document.body.innerText')
    
    print("\n=== FIRST 1500 CHARS ===")
    print(text[:1500])
    
    print("\n=== CHECKING DRIVER PATTERNS ===")
    if 'DRIVER MstPts' in text:
        print("✅ Found 'DRIVER MstPts'")
    elif 'Driver' in text:
        print("⚠️ Found 'Driver' but not 'DRIVER MstPts'")
    else:
        print("❌ No Driver text found")
    
    for line in text.split('\n')[:30]:
        print(f"  {line}")
    
    await browser.close()
    await playwright.stop()

asyncio.run(debug_driver())