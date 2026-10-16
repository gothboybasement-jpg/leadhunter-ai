"""Email enrichment: scrape contact emails from business websites."""
import sqlite3, re, sys, time
import httpx

DB = 'data/leadhunter.db'
EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
BAD = ('example.com', 'sentry.io', 'wixpress.com', 'wix.com', 'godaddy.com',
       'cloudflare.com', 'google.com', 'schema.org', 'w3.org', 'sample.com')
PATHS = ['', '/contact', '/contact-us', '/about', '/about-us', '/reach-us']
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

def good(email):
    e = email.lower()
    if any(b in e for b in BAD):
        return False
    if e.endswith(('.png', '.jpg', '.gif', '.svg', '.webp', '.css', '.js')):
        return False
    return True

def scrape(base):
    if not base:
        return None
    if not base.startswith('http'):
        base = 'https://' + base
    base = base.rstrip('/')
    found = set()
    for path in PATHS:
        url = base + path
        try:
            with httpx.Client(timeout=10, follow_redirects=True, headers=HEADERS) as c:
                r = c.get(url)
            if r.status_code == 200:
                for m in EMAIL_RE.findall(r.text):
                    if good(m):
                        found.add(m.lower())
        except Exception:
            continue
        if found:
            break
        time.sleep(0.3)
    return sorted(found)[0] if found else None

def main():
    c = sqlite3.connect(DB)
    rows = c.execute("SELECT id, name, website FROM leads WHERE (email IS NULL OR email='') AND website IS NOT NULL AND website != ''").fetchall()
    print(f"Found {len(rows)} leads to enrich")
    updated = 0
    for lead_id, name, site in rows:
        print(f"[{lead_id}] {name} -> ", end='', flush=True)
        email = scrape(site)
        if email:
            c.execute("UPDATE leads SET email=? WHERE id=?", (email, lead_id))
            c.commit()
            print(email)
            updated += 1
        else:
            print("(none)")
    print(f"\nDone. Enriched {updated}/{len(rows)} leads.")

if __name__ == '__main__':
    main()
