#!/usr/bin/env python
"""
Test script for Sportsbet and Ladbrokes scrapers
Run this from your backend directory with VPN connected to Australia

Usage:
    python test_scrapers.py
"""

import asyncio
import sys

# Add the path if needed
sys.path.insert(0, '.')

from playwright.async_api import async_playwright


async def test_sportsbet_jockey():
    """Test Sportsbet Jockey Challenge scraping"""
    print("\n" + "="*60)
    print("🏇 TESTING SPORTSBET - JOCKEY CHALLENGES")
    print("="*60)
    
    playwright = browser = context = None
    
    try:
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
        page = await context.new_page()
        
        # Go to Sportsbet racing
        print("[Sportsbet] Navigating to horse-racing...")
        await page.goto('https://www.sportsbet.com.au/horse-racing', timeout=30000)
        await asyncio.sleep(4)
        
        # Check if blocked
        content = await page.content()
        if 'not available' in content.lower() or 'blocked' in content.lower():
            print("[Sportsbet] ❌ BLOCKED - VPN not working or geo-restricted")
            return []
        
        # Click Extras tab
        print("[Sportsbet] Looking for Extras tab...")
        try:
            await page.click('text="Extras"', timeout=5000)
            print("[Sportsbet] ✅ Clicked Extras tab")
            await asyncio.sleep(3)
        except Exception as e:
            print(f"[Sportsbet] ⚠️ Extras tab not found: {e}")
            # Try direct URL
            await page.goto('https://www.sportsbet.com.au/horse-racing/extras', timeout=30000)
            await asyncio.sleep(4)
        
        # Scroll to load content
        for _ in range(5):
            await page.evaluate('window.scrollBy(0, 500)')
            await asyncio.sleep(1)
        
        # Get page text
        text = await page.evaluate('document.body.innerText')
        
        # Check for Jockey Challenge content
        if 'Jockey Challenge' in text:
            print("[Sportsbet] ✅ Found 'Jockey Challenge' in page")
            
            # Find all jockey challenge meetings
            import re
            meetings = re.findall(r'Jockey Challenge - ([A-Za-z ]+)', text)
            meetings = list(dict.fromkeys([m.strip() for m in meetings]))
            
            print(f"[Sportsbet] 📍 Found {len(meetings)} meetings: {meetings}")
            
            # Try clicking on first meeting to get odds
            if meetings:
                first_meeting = meetings[0]
                print(f"\n[Sportsbet] Clicking on '{first_meeting}'...")
                try:
                    await page.click(f'text="Jockey Challenge - {first_meeting}"', timeout=5000)
                    await asyncio.sleep(3)
                    
                    text = await page.evaluate('document.body.innerText')
                    lines = text.split('\n')
                    
                    # Parse jockeys and odds
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
                                                if 'Challenge' not in name and 'Any Other' not in name:
                                                    if not any(j['name'] == name for j in jockeys):
                                                        jockeys.append({'name': name, 'odds': odds})
                                                        break
                        except:
                            pass
                    
                    print(f"[Sportsbet] 🏇 {first_meeting} jockeys:")
                    for j in jockeys[:10]:  # Show first 10
                        print(f"    {j['name']}: ${j['odds']}")
                    
                except Exception as e:
                    print(f"[Sportsbet] ⚠️ Error clicking meeting: {e}")
        else:
            print("[Sportsbet] ❌ 'Jockey Challenge' NOT found in page")
            print("[Sportsbet] Page preview:")
            print(text[:1000])
        
        # Keep browser open for inspection
        print("\n[Sportsbet] Browser open for 30 seconds for inspection...")
        await asyncio.sleep(30)
        
    except Exception as e:
        print(f"[Sportsbet] ❌ Error: {e}")
    finally:
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()


async def test_sportsbet_driver():
    """Test Sportsbet Driver Challenge scraping"""
    print("\n" + "="*60)
    print("🐎 TESTING SPORTSBET - DRIVER CHALLENGES (HARNESS)")
    print("="*60)
    
    playwright = browser = context = None
    
    try:
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
        page = await context.new_page()
        
        # Go to Sportsbet racing
        print("[Sportsbet] Navigating to horse-racing...")
        await page.goto('https://www.sportsbet.com.au/horse-racing', timeout=30000)
        await asyncio.sleep(4)
        
        # Click Extras tab
        try:
            await page.click('text="Extras"', timeout=5000)
            print("[Sportsbet] ✅ Clicked Extras tab")
            await asyncio.sleep(3)
        except:
            pass
        
        # Scroll down to Harness Driver Challenge section
        for _ in range(8):
            await page.evaluate('window.scrollBy(0, 500)')
            await asyncio.sleep(1)
        
        text = await page.evaluate('document.body.innerText')
        
        if 'Driver Challenge' in text or 'Harness Driver' in text:
            print("[Sportsbet] ✅ Found 'Driver Challenge' in page")
            
            import re
            # Pattern: "Cranbourne Driver Challenge" or "Newcastle Driver Challenge"
            meetings = re.findall(r'([A-Za-z ]+) Driver Challenge', text)
            meetings = list(dict.fromkeys([m.strip() for m in meetings if 'Harness' not in m]))
            
            print(f"[Sportsbet] 📍 Found {len(meetings)} driver meetings: {meetings}")
        else:
            print("[Sportsbet] ❌ 'Driver Challenge' NOT found")
        
        print("\n[Sportsbet] Browser open for 20 seconds...")
        await asyncio.sleep(20)
        
    except Exception as e:
        print(f"[Sportsbet] ❌ Error: {e}")
    finally:
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()


async def test_ladbrokes_both():
    """Test Ladbrokes Jockey + Driver Challenge scraping"""
    print("\n" + "="*60)
    print("🔴 TESTING LADBROKES - JOCKEY + DRIVER CHALLENGES")
    print("="*60)
    
    playwright = browser = context = None
    
    try:
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
        page = await context.new_page()
        
        # Go to Ladbrokes extras
        print("[Ladbrokes] Navigating to racing/extras...")
        await page.goto('https://www.ladbrokes.com.au/racing/extras', timeout=30000)
        await asyncio.sleep(5)
        
        # Check if blocked
        content = await page.content()
        if 'not available' in content.lower() or 'cannot be accessed' in content.lower():
            print("[Ladbrokes] ❌ BLOCKED - VPN not working")
            return
        
        # Scroll to load
        for _ in range(5):
            await page.evaluate('window.scrollBy(0, 500)')
            await asyncio.sleep(1)
        await page.evaluate('window.scrollTo(0, 0)')
        await asyncio.sleep(2)
        
        text = await page.evaluate('document.body.innerText')
        
        # Check sections
        if 'Horse Racing' in text:
            print("[Ladbrokes] ✅ Found 'Horse Racing' section")
        if 'Harness Racing' in text:
            print("[Ladbrokes] ✅ Found 'Harness Racing' section")
        if 'Jockey Challenge' in text:
            print("[Ladbrokes] ✅ Found 'Jockey Challenge'")
        if 'Driver Challenge' in text:
            print("[Ladbrokes] ✅ Found 'Driver Challenge'")
        
        # Parse meetings
        lines = text.split('\n')
        
        # Find venue names
        venues = []
        for line in lines:
            line = line.strip()
            if line and len(line) > 2 and line[0].isupper():
                if not any(skip in line for skip in ['keyboard', 'INTL', 'Horse', 'Harness', 'Grey', 'Jockey', 'Driver', 'To Ride', 'Winners']):
                    if not any(c.isdigit() for c in line):
                        if len(line.split()) <= 3:
                            venues.append(line)
        
        venues = list(dict.fromkeys(venues))[:15]  # First 15 unique
        print(f"[Ladbrokes] 📍 Potential venues: {venues}")
        
        print("\n[Ladbrokes] Browser open for 30 seconds...")
        await asyncio.sleep(30)
        
    except Exception as e:
        print(f"[Ladbrokes] ❌ Error: {e}")
    finally:
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()


async def quick_test_all():
    """Quick connectivity test for all bookmakers"""
    print("\n" + "="*60)
    print("⚡ QUICK CONNECTIVITY TEST - ALL BOOKMAKERS")
    print("="*60)
    
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
    page = await context.new_page()
    
    sites = [
        ('Sportsbet', 'https://www.sportsbet.com.au/horse-racing'),
        ('Ladbrokes', 'https://www.ladbrokes.com.au/racing/extras'),
        ('TAB', 'https://www.tab.com.au/sports/betting/Jockey%20Challenge/competitions/Jockey%20Challenge'),
        ('Elitebet', 'https://www.elitebet.com.au/racing'),
        ('TABtouch', 'https://www.tabtouch.com.au/racing/jockey-challenge'),
    ]
    
    results = {}
    
    for name, url in sites:
        try:
            print(f"\n[{name}] Testing {url}...")
            await page.goto(url, timeout=15000)
            await asyncio.sleep(3)
            
            content = await page.content()
            text = await page.evaluate('document.body.innerText')
            
            if 'not available' in content.lower() or 'cannot be accessed' in content.lower() or 'Access Denied' in text:
                print(f"[{name}] ❌ BLOCKED")
                results[name] = 'BLOCKED'
            elif 'jockey' in text.lower() or 'racing' in text.lower():
                print(f"[{name}] ✅ WORKING")
                results[name] = 'WORKING'
            else:
                print(f"[{name}] ⚠️ UNKNOWN")
                results[name] = 'UNKNOWN'
                
        except Exception as e:
            print(f"[{name}] ❌ ERROR: {e}")
            results[name] = 'ERROR'
    
    await browser.close()
    await playwright.stop()
    
    print("\n" + "="*60)
    print("📊 RESULTS SUMMARY")
    print("="*60)
    for name, status in results.items():
        emoji = '✅' if status == 'WORKING' else '❌' if status in ['BLOCKED', 'ERROR'] else '⚠️'
        print(f"  {emoji} {name}: {status}")
    print("="*60)


async def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║          RACING SCRAPER TEST SUITE                           ║
║          Make sure VPN is connected to AUSTRALIA!            ║
╚══════════════════════════════════════════════════════════════╝
    
Select test to run:
    1. Quick connectivity test (all bookmakers)
    2. Test Sportsbet Jockey Challenges
    3. Test Sportsbet Driver Challenges  
    4. Test Ladbrokes (Jockey + Driver)
    5. Run all tests
    
    """)
    
    choice = input("Enter choice (1-5): ").strip()
    
    if choice == '1':
        await quick_test_all()
    elif choice == '2':
        await test_sportsbet_jockey()
    elif choice == '3':
        await test_sportsbet_driver()
    elif choice == '4':
        await test_ladbrokes_both()
    elif choice == '5':
        await quick_test_all()
        await test_sportsbet_jockey()
        await test_sportsbet_driver()
        await test_ladbrokes_both()
    else:
        print("Invalid choice. Running quick test...")
        await quick_test_all()


if __name__ == '__main__':
    asyncio.run(main())