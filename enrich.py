"""Email enrichment using Apify Google Maps Email Scraper."""
import sqlite3
import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

APIFY_TOKEN = os.environ.get("APIFY_TOKEN")
ACTOR_ID = "leadharbor~google-maps-verified-email-scraper"
DB = 'data/leadhunter.db'

def run_apify(city, category, limit=20):
    """Run Apify. 200 and 201 are both success codes."""
    url = f"https://api.apify.com/v2/acts/{ACTOR_ID}/run-sync-get-dataset-items"
    payload = {
        "business_types": [category],
        "location": city,
        "max_results": limit,
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

def parse_emails(email_string):
    """Extract valid personal emails from Apify output."""
    if not email_string:
        return None
    if isinstance(email_string, list):
        for e in email_string:
            if isinstance(e, dict):
                if e.get("emailStatus") == "valid":
                    email = e.get("email", "")
                    if email and not email.lower().startswith(("info@", "contact@", "admin@", "hello@")):
                        return email
            elif isinstance(e, str) and "(valid)" in e:
                email = e.split("(")[0].strip()
                if not email.lower().startswith(("info@", "contact@", "admin@", "hello@")):
                    return email
        return None
    # String format: "email (valid); other (risky)"
    parts = str(email_string).split(";")
    for part in parts:
        part = part.strip()
        if "(valid)" in part:
            email = part.split("(")[0].strip()
            if not email.lower().startswith(("info@", "contact@", "admin@", "hello@")):
                return email
    return None

def main():
    if not APIFY_TOKEN:
        print("APIFY_TOKEN not set in .env")
        return

    c = sqlite3.connect(DB)

    # Use only clean target categories
    import datetime

    # Same rotation as the GitHub workflow
    CITIES = ["Tampa", "Charlotte", "Nashville", "Scottsdale", "Austin", "Raleigh", "Phoenix"]
    CATEGORIES = ["real estate agent", "insurance agency", "law firm", "med spa", "mortgage broker", "real estate agent", "med spa"]

    # %u = Monday is 1, Sunday is 7 (matches workflow)
    dow = datetime.datetime.utcnow().isoweekday()
    idx = dow % 7
    city = CITIES[idx]
    category = CATEGORIES[idx]

    print(f"Today ({dow}): {category} in {city}")
    targets = [(city, category)]

    total_added = 0
    for city, category in targets:
        print(f"\n=== Searching {category} in {city} ===")
        results = run_apify(city, category, limit=20)
        print(f"  Got {len(results)} results")

        for item in results:
            name = item.get("name") or ""
            email_status = item.get("emailStatus") or ""
            email = item.get("email") or ""

            if not email or email_status not in ("valid", "risky-role") or not name:
                continue
            if email.lower().startswith(("info@", "contact@", "admin@", "hello@", "office@")):
                continue

            c.execute(
                "INSERT INTO leads (name, email, city, category, status, source, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 'DISCOVERED', 'apify', datetime('now'), datetime('now'))",
                (name, email, city, category),
            )
            print(f"  + {name} -> {email}")
            total_added += 1
        c.commit()
        time.sleep(2)

    print(f"\nDone. Added {total_added} leads with valid emails.")

if __name__ == '__main__':
    main()