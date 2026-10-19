import sqlite3
c = sqlite3.connect('data/leadhunter.db')
print("Tiers of qualified Charlotte leads:")
for r in c.execute("SELECT lead_tier, COUNT(*) FROM leads WHERE status='QUALIFIED' AND city='Charlotte' GROUP BY lead_tier"):
    print(f"  tier='{r[0]}': {r[1]}")
