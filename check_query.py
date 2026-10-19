import sqlite3
c = sqlite3.connect('data/leadhunter.db')
query = "SELECT * FROM leads WHERE status = 'QUALIFIED' AND (lead_tier = 'HOT' OR lead_tier = 'WARM') ORDER BY id ASC LIMIT ?"
rows = c.execute(query, (100,)).fetchall()
print(f"Query returned {len(rows)} leads.")
for r in rows[:3]:
    print(f"  {r[1]} | {r[3]} | {r[19]}")
