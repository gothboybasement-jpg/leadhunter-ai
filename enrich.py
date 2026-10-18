"""Email enrichment: Google Maps via Apify, then scrape email from website."""
import sqlite3
import os
import time
import re
import requests
from urllib.parse import urlparse
from dotenv import load_dotenv
import httpx

load_dotenv()

APIFY_TOKEN = os.environ.get("APIFY_TOKEN")
ACTOR_ID = "compass~crawler-google-places"
DB = 'data/leadhunter.db'
EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
PATHS = ['', '/contact', '/contact-us', '/about', '/team', '/our-team', '/agents']
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
BAD_PATTERNS = ['example', 'noreply', 'sentry', 'wixpress', 'godaddy', 'cloudflare', 'schema.org']
GENERIC = ['info@', 'contact@', 'admin@', 'hello@', 'office@', 'staff@', 'patientcare@']

def run_apify(city, category, limit=20):
    url = f"https://api.apify.com/v2/acts/{ACTOR_ID}/run-sync-get-dataset-items"
    payload = {
        "searchStringsArray": [category],
        "locationQuery": city,
        "maxCrawledPlacesPerSearch": limit,
        "language": "en",
    }
    try:
        r = requests.post(url, params={"token": APIFY_TOKEN}, json=payload, timeout=300)
        if r.status_code not in (200, 201):
            print(f"  Apify error: {r.status_code} {r.text[:200]}")
            return []
        return r.json() or []
    except Exception as e:
        print(f"  Apify exception: {e}")
        return []

def scrape_website(base):
    if not base:
        return None
    if not base.startswith('http'):
        base = 'https://' + base
    base = base.rstrip('/')
    found = []
    for path in PATHS:
        try:
            with httpx.Client(timeout=10, follow_redirects=True, headers=HEADERS) as c:
                r = c.get(base + path)
            if r.status_code == 200:
                for m in EMAIL_RE.findall(r.text):
                    m = m.lower()
                    if any(b in m for b in BAD_PATTERNS) or m in found:
                        continue
                    found.append(m)
        except Exception:
            continue
        if found:
            break
    if not found:
        return None
    # Prefer personal over generic
    for e in found:
        if not any(g in e for g in GENERIC):
            return e
    return found[0]

def main():
    c = sqlite3.connect(DB)
    import datetime
    CITIES = ["Tampa", "Charlotte", "Nashville", "Scottsdale", "Austin", "Raleigh", "Phoenix"]
    CATEGORIES = ["real estate agency", "insurance agency", "law firm", "med spa", "mortgage broker", "real estate agency", "med spa"]
    dow = datetime.datetime.utcnow().isoweekday()
    idx = dow % 7
    city = CITIES[idx]
    category = CATEGORIES[idx]

    print(f"Today ({dow}): {category} in {city}")
    results = run_apify(city, category, limit=20)
    print(f"Got {len(results)} businesses from Google Maps.")

    added = 0
    for item in results:
        name = item.get("title") or item.get("name") or ""
        website = item.get("website") or ""
        phone = item.get("phone") or ""
        rating = item.get("totalScore") or item.get("rating")
        reviews = item.get("reviewsCount") or item.get("reviews") or 0

        if not name:
            continue

        email = scrape_website(website)
        if not email:
            continue

        now = datetime.datetime.now().isoformat()
        c.execute(
            "INSERT INTO leads (name, email, city, category, status, source, phone, rating, reviews_count, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'VERIFIED', 'google_maps', ?, ?, ?, ?, ?)",
            (name, email, city, category, phone, rating, reviews, now, now)
        )
        print(f"  + {name} -> {email}")
        added += 1
        time.sleep(1)

    c.commit()
    print(f"\nDone. Added {added} leads with valid emails.")

if __name__ == '__main__':
    main()