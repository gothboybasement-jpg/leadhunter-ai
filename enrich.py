"""Email enrichment with junk filtering and domain matching."""
import sqlite3, re, time
from urllib.parse import urlparse
import httpx

DB = 'data/leadhunter.db'
EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
PATHS = ['', '/contact', '/contact-us', '/about', '/about-us', '/reach-us']
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

BAD_PATTERNS = [
    'example', 'placeholder', 'noreply', 'no-reply', 'donotreply',
    'webmaster', 'postmaster', 'abuse@', 'sentry.io', 'wixpress',
    'wix.com', 'godaddy', 'squarespace', 'shopify', 'wordpress',
    'cloudflare', 'schema.org', 'w3.org', 'localhost',
    'email@address', 'your@email', 'youremail', 'test@', 'user@',
    'swissdigitech', 'webdesign', 'webdesigner', 'siteby'
]

# Generic inboxes that get filtered by staff
GENERIC_INBOXES = ['info@', 'contact@', 'admin@', 'support@', 'hello@', 'office@', 'team@', 'sales@']
BAD_TLDS = ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js', '.ico']


def is_junk(email):
    e = email.lower()
    if any(b in e for b in BAD_PATTERNS):
        return True
    if any(e.endswith(t) for t in BAD_TLDS):
        return True
    if len(e) > 60:
        return True
    return False


def domain_of(url):
    if not url:
        return ''
    try:
        if not url.startswith('http'):
            url = 'https://' + url
        d = urlparse(url).netloc.lower()
        if d.startswith('www.'):
            d = d[4:]
        return d
    except Exception:
        return ''


def scrape(base, site_domain):
    if not base:
        return None, None
    if not base.startswith('http'):
        base = 'https://' + base
    base = base.rstrip('/')
    found = []
    for path in PATHS:
        url = base + path
        try:
            with httpx.Client(timeout=10, follow_redirects=True, headers=HEADERS) as c:
                r = c.get(url)
            if r.status_code == 200:
                for m in EMAIL_RE.findall(r.text):
                    m = m.lower()
                    if not is_junk(m) and m not in found:
                        found.append(m)
        except Exception:
            continue
        if found:
            break
        time.sleep(0.3)
    if not found:
        return None, None
    if site_domain:
        domain_root = site_domain.split('.')[0]
        # First, try to find a personal, non-generic email
        for e in found:
            if any(g in e for g in GENERIC_INBOXES):
                continue
            if site_domain in e or domain_root in e:
                return e, 'DOMAIN_MATCH'
        # Fallback to any domain-matched email (even generic)
        for e in found:
            if site_domain in e or domain_root in e:
                return e, 'GENERIC_MATCH'
    return found[0], 'LOW_QUALITY'


def main():
    c = sqlite3.connect(DB)
    rows = c.execute("""
        SELECT id, name, website FROM leads
        WHERE (email IS NULL OR email = '')
        AND website IS NOT NULL AND website != ''
    """).fetchall()
    print(f"Found {len(rows)} leads to enrich")
    updated = 0
    skipped = 0
    for lead_id, name, site in rows:
        domain = domain_of(site)
        print(f"[{lead_id}] {name} (domain: {domain}) -> ", end='', flush=True)
        email, tag = scrape(site, domain)
        if email:
            c.execute("UPDATE leads SET email=? WHERE id=?", (email, lead_id))
            c.commit()
            print(f"{email} [{tag}]")
            updated += 1
        else:
            print("(no valid email found)")
            skipped += 1
    print(f"\nDone. Enriched {updated}/{len(rows)} leads. Skipped {skipped}.")


if __name__ == '__main__':
    main()