import requests
import os
from dotenv import load_dotenv

load_dotenv()
APIFY_TOKEN = os.environ.get("APIFY_TOKEN")
ACTOR_ID = "compass~crawler-google-places"

categories = [
    "real estate agency",
    "insurance agency",
    "law firm",
    "med spa",
    "mortgage broker"
]

city = "Tampa"

for cat in categories:
    print(f"\n=== Testing: {cat} in {city} ===")
    url = f"https://api.apify.com/v2/acts/{ACTOR_ID}/run-sync-get-dataset-items"
    payload = {
        "searchStringsArray": [cat],
        "locationQuery": city,
        "maxCrawledPlacesPerSearch": 3,
        "language": "en",
    }
    
    try:
        r = requests.post(url, params={"token": APIFY_TOKEN}, json=payload, timeout=300)
        if r.status_code not in (200, 201):
            print(f"  ERROR: {r.status_code} - {r.text[:100]}")
            continue
            
        results = r.json()
        print(f"  Got {len(results)} businesses.")
        for item in results:
            name = item.get("title", "Unknown")
            print(f"    - {name}")
    except Exception as e:
        print(f"  EXCEPTION: {e}")
