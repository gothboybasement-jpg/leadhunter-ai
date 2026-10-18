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
    # This actor expects "searchStringsArray" or "business_types" depending on version.
    # We also adjust the category name to match Google Maps better.
    if category == "real estate agent":
        search_cat = "real estate agency"
    else:
        search_cat = category

    payload = {
        "business_types": [search_cat],
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
            if email.lower().startswith(("info@", "contact@", "admin@", "hello@", "office@", "staff@", "patientcare@")):
                continue

            # STRICT CATEGORY FILTER
            # If the category doesn't match what we asked for, skip it.
            item_cat = (item.get("category") or "").lower()
            target_cat = category.lower()
            
            # Define keyword matches
            match = False
            if "real estate" in target_cat and ("real estate" in item_cat or "realtor" in item_cat): match = True
            elif "insurance" in target_cat and ("insurance" in item_cat or "agency" in item_cat): match = True
            elif "law firm" in target_cat and ("law" in item_cat or "attorney" in item_cat or "legal" in item_cat): match = True
            elif "med spa" in target_cat and ("spa" in item_cat or "medical" in item_cat or "clinic" in item_cat): match = True
            elif "mortgage" in target_cat and ("mortgage" in item_cat or "broker" in item_cat or "lender" in item_cat): match = True
            elif target_cat in item_cat: match = True

            if not match and item_cat:
                print(f"  Skipping {name} (category mismatch: {item_cat})")
                continue

            phone = item.get("phone") or item.get("phoneNumber") or ""
            rating = item.get("rating") or item.get("totalScore")
            reviews = item.get("reviewsCount") or item.get("reviews") or item.get("userRatingsCount") or 0
            try:
                rating = float(rating) if rating else None
            except (ValueError, TypeError):
                rating = None
            try:
                reviews = int(reviews) if reviews else 0
            except (ValueError, TypeError):
                reviews = 0

            c.execute(
                "INSERT INTO leads (name, email, city, category, status, source, phone, rating, reviews_count, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 'DISCOVERED', 'apify', ?, ?, ?, datetime('now'), datetime('now'))",
                (name, email, city, category, phone, rating, reviews),
            )
            print(f"  + {name} -> {email}")
            total_added += 1
        c.commit()
        time.sleep(2)

    print(f"\nDone. Added {total_added} leads with valid emails.")

if __name__ == '__main__':
    main()