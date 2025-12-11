# WebCrawler-Scalable-Data-Extractor
A reliable scraper that extracts company reviews from AmbitionBox.com using a visible Playwright browser (bypasses headless restrictions). Includes a network diagnostic tool to debug DNS, SSL, and browser issues.

This project provides a **robust, network-resilient scraping solution** for extracting company reviews from **AmbitionBox.com**, even on networks where headless automation is blocked.
It includes:

* **Visible-browser review scraper** (`ab_scraper_visible.py`)
* **Network diagnostic tool** (`diagnose_connection.py`)
* **Cookie-based authenticated data extraction**
* **Batch processing with resume support**
* **Asynchronous fetching for high-speed downloads**

---

## ✨ Features

### 🔍 1. Visible-Browser Cookie Capture

AmbitionBox blocks many headless browsers.
This scraper launches **Chromium in visible mode**, captures auth cookies, then uses API endpoints to fetch structured review data.

### 🚀 2. Fully Asynchronous Review Extraction

* Fetches review pages using `aiohttp`
* Handles retries, rate limits, exponential backoff
* Concurrency control for fast + stable scraping
* Writes reviews in **NDJSON** for easy downstream processing

### 📦 3. Batch-Oriented Architecture

* Resume progress after interruptions
* Save processed/failed companies
* Configurable random delays to mimic human behavior
* Safe file-writing with temp chunks to avoid corruption

### 🛠 4. Diagnostic Tool

`diagnose_connection.py` detects issues across:

* DNS resolution
* Basic HTTP availability
* SSL problems
* Playwright browser launch
* Site navigation tests with multiple configs

It tells you exactly *why* scraping is failing and what to do next.

---

## 📁 Project Structure

```
.
├── ab_scraper_visible.py       # Main scraper (visible-browser cookie capture)
├── diagnose_connection.py      # Connectivity + Playwright diagnostic tool
├── reviews_data/               # Scraped review outputs (auto-created)
├── batch_progress.json         # Auto-managed resume checkpoint
├── scraper_errors.log          # Error logs
├── scraper_progress.log        # Progress logs
└── README.md
```


## ⚙️ Installation

### 1. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate     # macOS/Linux
.venv\Scripts\activate        # Windows
```

### 2. Install requirements

```bash
pip install -r requirements.txt
```

### 3. Install Playwright browsers

```bash
playwright install chromium
```


## 🧪 Run Connectivity Diagnostics

Before scraping, ensure your network supports Playwright:

```bash
python diagnose_connection.py
```

If a configuration is marked **SUCCESS**, the scraper will use the same logic.



## 🕷️ Running the Scraper

### Basic command

```bash
python ab_scraper_visible.py --csv companies.csv
```

### CSV Format

Your CSV must contain at least one column with company URLs or names.
The script automatically detects:

```
url, company_url, link, website, review_url, firm_name, company_name, name
```

If only the company name is provided, the scraper constructs:

```
https://www.ambitionbox.com/reviews/{slug}-reviews
```

### Useful flags

| Flag              | Description                                    |
| ----------------- | ---------------------------------------------- |
| `--concurrency 5` | Requests per company (default: 5)              |
| `--limit 20`      | Reviews per page (20/50/100)                   |
| `--batch-size 10` | Optional chunk size for long scraping sessions |
| `--delay 5-10`    | Random delay between companies                 |
| `--resume`        | Continue from checkpoint                       |
| `--reset`         | Fresh start (clears progress)                  |

### Example: high-speed mode

```bash
python ab_scraper_visible.py --csv companies.csv --concurrency 10 --delay 1-5
```



## 📝 Output Format

Each company gets its own directory:

```
reviews_data/
   tcs_reviews/
      reviews_tcs.ndjson
```

Each line in `.ndjson` is a JSON review object:

```json
{
  "urlName": "tcs",
  "company_id": 12345,
  "reviewId": 98765,
  "rating": 4,
  "review": "Good work culture...",
  "location": "Bangalore",
  ...
}
```

## 🛡️ Error Handling & Resume Logic

The scraper:

* Logs all errors into `scraper_errors.log`
* Continues scraping even if individual companies fail
* Saves progress in `batch_progress.json`
* Can resume scraping using:

```bash
python ab_scraper_visible.py --csv companies.csv --resume
```

## 🧭 Best Practices & Notes
* **Do not close the visible browser windows manually.** They close automatically.
* You may minimize them—they still work.
* Some networks block headless scraping; this method bypasses such blocks.
* Always run `diagnose_connection.py` if the scraper is stuck.

## 🧑‍💻 Contributing
Pull requests are welcome!
Enhancements to bypass rate limits, improve cookie handling, or add proxies are appreciated.

## 📄 License
MIT License — free to use, modify, and distribute.



It tells you exactly why scraping is failing and what to do next.

