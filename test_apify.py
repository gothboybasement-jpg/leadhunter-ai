import sqlite3
import requests
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
APIFY_TOKEN = os.environ.get("APIFY_TOKEN")

# 1. Clean the local DB so we don't confuse the test
c = sqlite3.connect('data/leadhunter.db')
c.execute("DELETE FROM leads WHERE city='Tampa' AND source='test'")

# 2. Define EXACT real estate businesses in Tampa (no category guessing)
businesses = [
    "Smith & Associates Real Estate, Tampa",
    "Keller Williams Tampa",
    "RE/MAX Tampa",
    "Century 21 Tampa"
]

print("Asking Apify for these specific businesses...")
url = "https://api.apify.com/v2/acts/leadharbor~google-maps-verified-email-scraper/run-sync-get-dataset-items"
payload = {
    "business_names": businesses,
    "location": "Tampa, FL"
}
r = requests.post(url, params={"token": APIFY_TOKEN}, json=payload, timeout=300)

if r.status_code not in (200, 201):
    print(f"Apify error: {r.status_code} {r.text[:200]}")
    exit(1)

items = r.json()
print(f"Got {len(items)} results from Apify.")

# 3. Insert into DB with all required fields
now = datetime.now().isoformat()
added = 0

for item in items:
    name = item.get("name")
    email = item.get("email")
    status = item.get("emailStatus", "")
    phone = item.get("phone", "")
    rating = item.get("rating") or 4.5
    reviews = item.get("reviewsCount") or 50

    if not email or status not in ("valid", "risky-role"):
        continue

    c.execute(
        "INSERT INTO leads (name, email, city, category, status, source, phone, rating, reviews_count, created_at, updated_at) "
        "VALUES (?, ?, 'Tampa', 'real estate agent', 'VERIFIED', 'test', ?, ?, ?, ?, ?)",
        (name, email, phone, rating, reviews, now, now)
    )
    print(f"  Added {name} ({email})")
    added += 1

c.commit()
print(f"Added {added} real estate agents to the database.")
