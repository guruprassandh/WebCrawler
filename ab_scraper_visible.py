#!/usr/bin/env python3
"""
ab_scraper_visible.py

AmbitionBox scraper configured for networks that block headless browsers.
Uses VISIBLE browser mode (non-headless) which works on most networks.

Browser windows will briefly appear and auto-close - this is normal!
"""

import argparse
import asyncio
import csv
import json
import random
import time
import sys
import logging
from pathlib import Path
from typing import Optional, Tuple, List, Dict
from datetime import datetime

import aiofiles
import aiohttp
import requests
from playwright.async_api import async_playwright

# ----------------- Configuration -----------------
HEADERS_BASE = {
    "accept": "application/json, text/plain, */*",
    "appid": "931",
    "systemid": "ambitionbox-review-services",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
}

SEO_META_ENDPOINT = "https://www.ambitionbox.com/servicegateway-ambitionbox/review-services/v0/seo/{urlname}/meta-data"
DATA_ENDPOINT = "https://www.ambitionbox.com/servicegateway-ambitionbox/review-services/v0/review/data/{company_id}"

BASE_DIR = Path("reviews_data")
BATCH_CHECKPOINT = Path("batch_progress.json")
ERROR_LOG = Path("scraper_errors.log")
PROGRESS_LOG = Path("scraper_progress.log")

DEFAULT_CONCURRENCY = 5
DEFAULT_LIMIT = 20
DEFAULT_BATCH_SIZE = 10
DEFAULT_DELAY_RANGE = (5, 10)
RETRIES = 5
BACKOFF_BASE = 2.0
MAX_PROBE_PAGES = 10000
BROWSER_TIMEOUT = 45000

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(ERROR_LOG),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ----------------- Utilities -----------------
def ensure_scheme(s: str) -> str:
    if not s.startswith("http://") and not s.startswith("https://"):
        return "https://" + s
    return s

def extract_urlname_from_url(url: str) -> Optional[str]:
    try:
        url = url.rstrip("/")
        parts = url.split("/")
        last = parts[-1]
        if last.endswith("-reviews"):
            return last.replace("-reviews", "")
        return last
    except Exception as e:
        logger.error(f"Failed to extract urlname from {url}: {e}")
        return None

def sanitize_filename(name: str) -> str:
    import re
    safe = re.sub(r'[^\w\s-]', '', name).strip()
    safe = re.sub(r'[-\s]+', '_', safe)
    return safe[:100]

def load_batch_progress() -> Dict:
    if BATCH_CHECKPOINT.exists():
        try:
            return json.loads(BATCH_CHECKPOINT.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"Failed to load batch progress: {e}")
            return {"processed": [], "failed": [], "last_index": -1}
    return {"processed": [], "failed": [], "last_index": -1}

def save_batch_progress(progress: Dict):
    try:
        BATCH_CHECKPOINT.write_text(json.dumps(progress, indent=2), encoding="utf-8")
    except Exception as e:
        logger.error(f"Failed to save batch progress: {e}")

def log_progress(message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_msg = f"[{timestamp}] {message}\n"
    try:
        with open(PROGRESS_LOG, "a", encoding="utf-8") as f:
            f.write(log_msg)
    except Exception:
        pass
    print(message)

# ----------------- Cookie Capture (Non-Headless) -----------------
async def capture_cookies_visible_browser(review_url: str, max_attempts: int = 3) -> Tuple[Optional[str], str]:
    """
    Capture cookies using VISIBLE browser (non-headless mode).
    Browser window will appear briefly - this is normal!
    
    Returns (cookie_string, error_message)
    """
    review_url = ensure_scheme(review_url)
    
    print("      [Browser window will appear briefly - don't close it manually]")
    
    for attempt in range(max_attempts):
        browser = None
        try:
            async with async_playwright() as p:
                # Launch in NON-HEADLESS mode (visible browser)
                browser = await p.chromium.launch(
                    headless=False,  # VISIBLE BROWSER - works on your network!
                    args=["--no-sandbox", "--disable-dev-shm-usage"]
                )
                
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                
                page = await context.new_page()
                
                # Navigate
                print(f"      [Opening {review_url}...]")
                await page.goto(review_url, timeout=BROWSER_TIMEOUT, wait_until="domcontentloaded")
                
                # Wait for page to settle
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass
                
                # Get cookies
                cookies = await context.cookies()
                
                # Close browser
                await browser.close()
                print("      [Browser closed automatically]")
                
                if cookies and len(cookies) > 0:
                    cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
                    print(f"      ✓ Captured {len(cookies)} cookies")
                    return cookie_str, ""
                else:
                    print(f"      ⚠ No cookies captured, retrying...")
                    
        except Exception as e:
            if browser:
                try:
                    await browser.close()
                except:
                    pass
            
            error_msg = f"Attempt {attempt+1}/{max_attempts} failed: {str(e)}"
            logger.warning(error_msg)
            print(f"      ✗ {error_msg}")
            
            if attempt < max_attempts - 1:
                wait_time = 2 ** attempt
                print(f"      → Waiting {wait_time}s before retry...")
                await asyncio.sleep(wait_time)
            else:
                return None, error_msg
    
    return None, "All cookie capture attempts failed"

# ----------------- SEO Probe -----------------
def probe_seo_meta(urlname: str, cookie_str: str, timeout: int = 30) -> Optional[dict]:
    headers = dict(HEADERS_BASE)
    headers["cookie"] = cookie_str
    headers["referer"] = f"https://www.ambitionbox.com/reviews/{urlname}-reviews"
    
    try:
        r = requests.get(
            SEO_META_ENDPOINT.format(urlname=urlname),
            headers=headers,
            params={"page": 1},
            timeout=timeout
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error(f"SEO probe failed for {urlname}: {e}")
        return None

def extract_company_id(seo_json: dict) -> Optional[int]:
    try:
        data = seo_json.get("data") or seo_json
        company = data.get("company") or {}
        cid = company.get("id")
        return int(cid) if cid else None
    except Exception:
        return None

# ----------------- Page Discovery -----------------
async def discover_total_pages(company_id: int, urlname: str, cookie_str: str, limit: int) -> int:
    headers = dict(HEADERS_BASE)
    headers["cookie"] = cookie_str
    headers["referer"] = f"https://www.ambitionbox.com/reviews/{urlname}-reviews"
    
    # Try SEO metadata
    try:
        seo = probe_seo_meta(urlname, cookie_str)
        if seo:
            pagination = (seo.get("data") or {}).get("pagination") or {}
            total = int(pagination.get("totalPages", 0))
            if total > 1:
                return total
    except Exception:
        pass
    
    # Try data endpoint page 1
    try:
        url = DATA_ENDPOINT.format(company_id=company_id)
        r = requests.get(
            url,
            headers=headers,
            params={"page": 1, "limit": limit, "isReviewRequest": "true"},
            timeout=30
        )
        if r.status_code == 200:
            pag = (r.json().get("data") or {}).get("pagination") or {}
            total = int(pag.get("totalPages", 0))
            if total > 1:
                return total
    except Exception:
        pass
    
    return 1

# ----------------- Async Fetcher -----------------
class CompanyFetcher:
    def __init__(self, company_id: int, urlname: str, cookie_str: str, 
                 out_file: Path, concurrency: int = 5, limit: int = 20):
        self.company_id = company_id
        self.urlname = urlname
        self.cookie_str = cookie_str
        self.out_file = out_file
        self.concurrency = concurrency
        self.limit = limit
        
        self.headers = dict(HEADERS_BASE)
        self.headers["cookie"] = cookie_str
        self.headers["referer"] = f"https://www.ambitionbox.com/reviews/{urlname}-reviews"
        
        self.sem = asyncio.Semaphore(concurrency)
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=None, sock_connect=10, sock_read=30)
        self.session = aiohttp.ClientSession(headers=self.headers, timeout=timeout)
        return self
    
    async def __aexit__(self, exc_type, exc, tb):
        if self.session:
            await self.session.close()
    
    async def fetch_page_json(self, page: int):
        url = DATA_ENDPOINT.format(company_id=self.company_id)
        params = {"page": page, "limit": self.limit, "isReviewRequest": "true"}
        
        for attempt in range(RETRIES):
            try:
                async with self.sem:
                    async with self.session.get(url, params=params) as resp:
                        if resp.status == 200:
                            return await resp.json(), None
                        elif resp.status in (429, 503):
                            backoff = BACKOFF_BASE ** attempt + random.random()
                            await asyncio.sleep(backoff)
                            continue
                        else:
                            return None, f"status_{resp.status}"
            except Exception as e:
                if attempt < RETRIES - 1:
                    backoff = BACKOFF_BASE ** attempt + random.random()
                    await asyncio.sleep(backoff)
                else:
                    return None, str(e)
        
        return None, "max_retries_exceeded"
    
    async def process_page(self, page_num: int) -> Tuple[bool, int]:
        data, err = await self.fetch_page_json(page_num)
        
        if data is None:
            return False, 0
        
        try:
            reviews = (data.get("data", {}) or {}).get("reviews", []) or []
            if not isinstance(reviews, list):
                return False, 0
            
            tmp_file = self.out_file.with_suffix(f'.page{page_num}.tmp')
            
            async with aiofiles.open(tmp_file, 'w', encoding='utf-8') as f:
                for review in reviews:
                    try:
                        line = json.dumps({
                            "urlName": self.urlname,
                            "company_id": self.company_id,
                            **review
                        }, ensure_ascii=False)
                        await f.write(line + '\n')
                    except Exception:
                        pass
            
            async with aiofiles.open(self.out_file, 'a', encoding='utf-8') as main_f:
                async with aiofiles.open(tmp_file, 'r', encoding='utf-8') as tmp_f:
                    content = await tmp_f.read()
                    await main_f.write(content)
            
            tmp_file.unlink(missing_ok=True)
            await asyncio.sleep(0.05 + random.random() * 0.1)
            return True, len(reviews)
            
        except Exception as e:
            logger.error(f"Error processing page {page_num}: {e}")
            return False, 0
    
    async def run(self, total_pages: int) -> Tuple[int, int]:
        self.out_file.parent.mkdir(parents=True, exist_ok=True)
        
        pages_fetched = 0
        reviews_written = 0
        
        batch_size = 50
        for start in range(1, total_pages + 1, batch_size):
            end = min(start + batch_size, total_pages + 1)
            tasks = [self.process_page(p) for p in range(start, end)]
            results = await asyncio.gather(*tasks)
            
            for ok, cnt in results:
                if ok:
                    pages_fetched += 1
                    reviews_written += cnt
        
        return pages_fetched, reviews_written

# ----------------- Company Processor -----------------
async def process_company(url: str, index: int, total: int, args) -> Dict:
    result = {
        "url": url,
        "index": index,
        "success": False,
        "urlname": None,
        "reviews": 0,
        "pages": 0,
        "error": None,
        "timestamp": datetime.now().isoformat()
    }
    
    log_progress(f"\n{'='*60}")
    log_progress(f"Processing [{index+1}/{total}]: {url}")
    
    try:
        urlname = extract_urlname_from_url(url)
        if not urlname:
            raise ValueError("Could not extract urlname from URL")
        
        result["urlname"] = urlname
        
        company_dir = BASE_DIR / f"{sanitize_filename(urlname)}_reviews"
        company_dir.mkdir(parents=True, exist_ok=True)
        out_file = company_dir / f"reviews_{urlname}.ndjson"
        
        log_progress(f"  → Capturing cookies for {urlname}...")
        cookie_str, error = await capture_cookies_visible_browser(url)
        
        if not cookie_str:
            raise ValueError(f"Cookie capture failed: {error}")
        
        log_progress(f"  → Fetching company metadata...")
        seo_data = probe_seo_meta(urlname, cookie_str)
        if not seo_data:
            raise ValueError("Failed to fetch SEO metadata")
        
        company_id = extract_company_id(seo_data)
        if not company_id:
            raise ValueError("Could not extract company ID")
        
        total_pages = await discover_total_pages(company_id, urlname, cookie_str, args.limit)
        result["pages"] = total_pages
        
        log_progress(f"  → Found {total_pages} pages, starting download...")
        
        start_time = time.time()
        async with CompanyFetcher(
            company_id=company_id,
            urlname=urlname,
            cookie_str=cookie_str,
            out_file=out_file,
            concurrency=args.concurrency,
            limit=args.limit
        ) as fetcher:
            pages_fetched, reviews_written = await fetcher.run(total_pages)
        
        elapsed = time.time() - start_time
        
        result["success"] = True
        result["reviews"] = reviews_written
        result["output_file"] = str(out_file)
        
        log_progress(f"  ✓ Success: {reviews_written} reviews in {elapsed:.1f}s")
        
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"Failed to process {url}: {e}")
        log_progress(f"  ✗ Failed: {e}")
    
    return result

# ----------------- Batch Processor -----------------
async def process_batch(companies: List[str], args):
    progress = load_batch_progress()
    start_index = progress["last_index"] + 1 if args.resume else 0
    
    total = len(companies)
    log_progress(f"\nStarting batch processing: {total} companies")
    log_progress(f"Resume from index: {start_index}")
    log_progress(f"Batch size: {args.batch_size}")
    log_progress(f"Browser mode: VISIBLE (non-headless)")
    log_progress(f"Delay between companies: {args.min_delay}-{args.max_delay}s")
    
    stats = {
        "total": total,
        "processed": len(progress["processed"]),
        "failed": len(progress["failed"]),
        "skipped": 0
    }
    
    try:
        for i in range(start_index, total):
            url = companies[i].strip()
            
            if not url:
                stats["skipped"] += 1
                continue
            
            result = await process_company(url, i, total, args)
            
            if result["success"]:
                progress["processed"].append(result)
            else:
                progress["failed"].append(result)
            
            progress["last_index"] = i
            save_batch_progress(progress)
            
            stats["processed"] = len(progress["processed"])
            stats["failed"] = len(progress["failed"])
            
            if (i + 1) % 10 == 0:
                success_rate = (stats["processed"] / (stats["processed"] + stats["failed"]) * 100) if (stats["processed"] + stats["failed"]) > 0 else 0
                log_progress(f"\nProgress: {i+1}/{total} | Success: {stats['processed']} | Failed: {stats['failed']} | Rate: {success_rate:.1f}%")
            
            if i < total - 1:
                delay = random.uniform(args.min_delay, args.max_delay)
                log_progress(f"  → Waiting {delay:.1f}s before next company...")
                await asyncio.sleep(delay)

            #Batch Delay
            """
            if (i + 1) % args.batch_size == 0 and i < total - 1:
                batch_delay = random.uniform(args.batch_delay_min, args.batch_delay_max)
                log_progress(f"\n  ⏸ Batch rest: {batch_delay:.1f}s\n")
                await asyncio.sleep(batch_delay)
            """
    
    except KeyboardInterrupt:
        log_progress("\n⚠ Interrupted by user. Progress saved.")
        save_batch_progress(progress)
        raise
    
    log_progress(f"\n{'='*60}")
    log_progress("FINAL SUMMARY")
    log_progress(f"{'='*60}")
    log_progress(f"Total companies: {stats['total']}")
    log_progress(f"Successfully processed: {stats['processed']}")
    log_progress(f"Failed: {stats['failed']}")
    log_progress(f"Skipped: {stats['skipped']}")

# ----------------- CSV Reader -----------------
def read_companies_from_csv(csv_path: Path, url_column: str = None) -> List[str]:
    companies = []
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []
            
            # Decide which column to use
            if not url_column:
                url_candidates = [
                    'url', 'company_url', 'link', 'website',
                    'review_url', 'firm_name', 'company_name', 'name'
                ]
                for candidate in url_candidates:
                    if candidate in headers:
                        url_column = candidate
                        break
                
                if not url_column:
                    url_column = headers[0] if headers else None
                
                log_progress(f"Using column '{url_column}' for URLs")
            
            import re
            url_pattern = re.compile(r'(https?://[^\s,]+)')
            
            for row in reader:
                if not url_column:
                    continue
                raw = (row.get(url_column) or "").strip()
                if not raw:
                    continue

                # 1) If the cell contains an explicit http/https URL, extract it
                m = url_pattern.search(raw)
                if m:
                    companies.append(m.group(1))
                    continue

                # 2) If the whole value *starts* with http/https, just use it
                if raw.startswith("http://") or raw.startswith("https://"):
                    companies.append(raw)
                    continue

                # 3) Otherwise, treat the value as a company name and build slug
                name = raw.lower()
                name = name.replace(" ", "-").replace("_", "-")
                name = re.sub(r'[^a-z0-9-]', '', name)
                url = f"https://www.ambitionbox.com/reviews/{name}-reviews"
                companies.append(url)
    
    except Exception as e:
        logger.error(f"Failed to read CSV: {e}")
        raise
    
    log_progress(f"Loaded {len(companies)} companies from {csv_path}")
    return companies


# ----------------- CLI -----------------
def parse_args():
    parser = argparse.ArgumentParser(
        description="AmbitionBox scraper using VISIBLE browser (works on all networks)"
    )
    
    parser.add_argument("--csv", required=True, type=Path, help="CSV file with company URLs")
    parser.add_argument("--url-column", help="Name of URL column (auto-detected if not provided)")
    
    parser.add_argument("--concurrency", type=int, default=5, 
                       help="Concurrent requests per company (default: 5)")
    parser.add_argument("--limit", type=int, default=20,
                       help="Reviews per page (20/50/100, default: 20)")
    
    parser.add_argument("--batch-size", type=int, default=10,
                       help="Companies per batch before long rest (default: 10)")
    parser.add_argument("--delay", type=str, default="5-10",
                       help="Delay range between companies in seconds (default: 5-10)")
    parser.add_argument("--batch-delay", type=str, default="30-60",
                       help="Delay range after each batch in seconds (default: 30-60)")
    
    parser.add_argument("--resume", action="store_true",
                       help="Resume from last checkpoint")
    parser.add_argument("--reset", action="store_true",
                       help="Reset all progress and start fresh")
    
    return parser.parse_args()

# ----------------- Main -----------------
async def main_async():
    args = parse_args()
    
    # Parse delay ranges
    try:
        min_d, max_d = map(float, args.delay.split('-'))
        args.min_delay, args.max_delay = min_d, max_d
    except:
        args.min_delay, args.max_delay = 5, 10
    
    try:
        min_bd, max_bd = map(float, args.batch_delay.split('-'))
        args.batch_delay_min, args.batch_delay_max = min_bd, max_bd
    except:
        args.batch_delay_min, args.batch_delay_max = 30, 60
    
    BASE_DIR.mkdir(exist_ok=True)
    
    if args.reset:
        if BATCH_CHECKPOINT.exists():
            BATCH_CHECKPOINT.unlink()
        log_progress("Progress reset. Starting fresh.")
    
    companies = read_companies_from_csv(args.csv, args.url_column)
    
    if not companies:
        logger.error("No companies found in CSV")
        return
    
    await process_batch(companies, args)

def main():
    print("\n" + "="*60)
    print("AmbitionBox Scraper - VISIBLE Browser Mode")
    print("="*60)
    print("\n⚠️  IMPORTANT NOTES:")
    print("   • Browser windows will appear briefly (3-5 seconds each)")
    print("   • This is NORMAL - they auto-close after capturing cookies")
    print("   • Don't manually close the browser windows")
    print("   • You can minimize them - they'll still work")
    print("\n" + "="*60 + "\n")
    
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        log_progress("\n⚠ Gracefully shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()