#!/usr/bin/env python3
"""
diagnose_connection.py

Diagnoses connection issues with AmbitionBox.
Tests different methods to access the site.
"""

import asyncio
import sys
import requests
from playwright.async_api import async_playwright
import ssl
import socket

def test_dns_resolution():
    """Test if DNS resolution works."""
    print("\n1. Testing DNS Resolution...")
    try:
        ip = socket.gethostbyname("www.ambitionbox.com")
        print(f"   ✓ DNS resolved: www.ambitionbox.com → {ip}")
        return True
    except Exception as e:
        print(f"   ✗ DNS resolution failed: {e}")
        return False

def test_basic_connectivity():
    """Test basic HTTP connectivity."""
    print("\n2. Testing Basic HTTP Connectivity...")
    try:
        response = requests.get(
            "https://www.ambitionbox.com",
            timeout=10,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )
        print(f"   ✓ HTTP request successful: Status {response.status_code}")
        return True
    except requests.exceptions.SSLError as e:
        print(f"   ✗ SSL Error: {e}")
        return False
    except requests.exceptions.ConnectionError as e:
        print(f"   ✗ Connection Error: {e}")
        return False
    except Exception as e:
        print(f"   ✗ Request failed: {e}")
        return False

def test_specific_page():
    """Test accessing a specific review page."""
    print("\n3. Testing Specific Review Page...")
    try:
        response = requests.get(
            "https://www.ambitionbox.com/reviews/infosys-reviews",
            timeout=15,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )
        print(f"   ✓ Review page accessible: Status {response.status_code}")
        if response.status_code == 200:
            print(f"   ✓ Content length: {len(response.text)} bytes")
        return True
    except Exception as e:
        print(f"   ✗ Failed to access review page: {e}")
        return False

async def test_playwright_basic():
    """Test basic Playwright browser launch."""
    print("\n4. Testing Playwright Browser...")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            print("   ✓ Browser launched successfully")
            context = await browser.new_context()
            print("   ✓ Browser context created")
            page = await context.new_page()
            print("   ✓ New page created")
            await browser.close()
            return True
    except Exception as e:
        print(f"   ✗ Playwright error: {e}")
        return False

async def test_playwright_ambitionbox():
    """Test Playwright navigation to AmbitionBox."""
    print("\n5. Testing Playwright Navigation to AmbitionBox...")
    
    configs = [
        {
            "name": "Default (headless)",
            "headless": True,
            "args": []
        },
        {
            "name": "With no-sandbox",
            "headless": True,
            "args": ["--no-sandbox", "--disable-dev-shm-usage"]
        },
        {
            "name": "With ignore-certificate-errors",
            "headless": True,
            "args": ["--no-sandbox", "--ignore-certificate-errors", "--disable-web-security"]
        },
        {
            "name": "Non-headless (visible browser)",
            "headless": False,
            "args": ["--no-sandbox"]
        }
    ]
    
    for config in configs:
        print(f"\n   Trying: {config['name']}")
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=config["headless"],
                    args=config["args"]
                )
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    ignore_https_errors=True
                )
                page = await context.new_page()
                
                print(f"      → Navigating to AmbitionBox...")
                response = await page.goto(
                    "https://www.ambitionbox.com/reviews/infosys-reviews",
                    timeout=30000,
                    wait_until="domcontentloaded"
                )
                
                status = response.status if response else "No response"
                print(f"      ✓ SUCCESS! Status: {status}")
                print(f"      ✓ Final URL: {page.url}")
                
                cookies = await context.cookies()
                print(f"      ✓ Cookies captured: {len(cookies)}")
                
                await browser.close()
                
                print(f"\n   ✅ WORKING CONFIG: {config['name']}")
                return config
                
        except Exception as e:
            error_str = str(e)
            if "ERR_HTTP2_PROTOCOL_ERROR" in error_str:
                print(f"      ✗ HTTP2 Protocol Error")
            elif "ERR_NAME_NOT_RESOLVED" in error_str:
                print(f"      ✗ DNS Resolution Failed")
            elif "timeout" in error_str.lower():
                print(f"      ✗ Timeout")
            else:
                print(f"      ✗ Error: {error_str[:100]}")
            await asyncio.sleep(0.5)
    
    print(f"\n   ✗ All Playwright configs failed")
    return None

async def main():
    print("="*60)
    print("AmbitionBox Connection Diagnostic Tool")
    print("="*60)
    
    results = {}
    
    # Test 1: DNS
    results['dns'] = test_dns_resolution()
    
    # Test 2: Basic HTTP
    results['http'] = test_basic_connectivity()
    
    # Test 3: Specific page
    results['page'] = test_specific_page()
    
    # Test 4: Playwright basic
    results['playwright_basic'] = await test_playwright_basic()
    
    # Test 5: Playwright AmbitionBox
    working_config = await test_playwright_ambitionbox()
    results['playwright_ambitionbox'] = working_config is not None
    
    # Summary
    print("\n" + "="*60)
    print("DIAGNOSTIC SUMMARY")
    print("="*60)
    
    for test, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {test}")
    
    print("\n" + "="*60)
    print("RECOMMENDATIONS")
    print("="*60)
    
    if not results['dns']:
        print("\n❌ DNS ISSUE:")
        print("   - Check your internet connection")
        print("   - Try different DNS (8.8.8.8 or 1.1.1.1)")
        print("   - Check if AmbitionBox is blocked by firewall/ISP")
    
    elif not results['http']:
        print("\n❌ CONNECTIVITY ISSUE:")
        print("   - AmbitionBox might be blocking automated requests")
        print("   - Try using a VPN")
        print("   - Check corporate firewall settings")
        print("   - Verify SSL certificates are up to date")
    
    elif not results['playwright_ambitionbox']:
        print("\n❌ PLAYWRIGHT ISSUE:")
        print("   - Requests library works but Playwright doesn't")
        print("   - This suggests AmbitionBox detects/blocks Playwright")
        print("\n   Solutions:")
        print("   1. Use the requests-based scraper (slower but works)")
        print("   2. Add more human-like behavior (delays, mouse movements)")
        print("   3. Try from a different network")
        print("   4. Use residential proxies")
    
    else:
        print("\n✅ ALL TESTS PASSED!")
        if working_config:
            print(f"\n   Working configuration: {working_config['name']}")
            print(f"\n   Use this in your scraper:")
            print(f"   - headless: {working_config['headless']}")
            print(f"   - args: {working_config['args']}")
    
    # Additional suggestions
    print("\n" + "="*60)
    print("NEXT STEPS")
    print("="*60)
    
    if results['http'] and not results['playwright_ambitionbox']:
        print("\n1. Try the requests-based fallback scraper:")
        print("   python scraper_requests_fallback.py --csv test.csv")
        
        print("\n2. Try from a different network:")
        print("   - Mobile hotspot")
        print("   - Different WiFi")
        print("   - VPN")
        
        print("\n3. Try with visible browser (non-headless):")
        print("   - Edit scraper: set headless=False")
        print("   - This helps bypass detection sometimes")
    
    elif results['playwright_ambitionbox']:
        print("\n✓ Connection is working!")
        print("   Run your scraper normally:")
        print("   python ab_batch_scraper.py --csv test.csv")
    
    print("\n" + "="*60)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠ Diagnostic interrupted")