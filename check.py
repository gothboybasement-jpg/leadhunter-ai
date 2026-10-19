import sqlite3
c = sqlite3.connect('data/leadhunter.db')
print("Qualified leads by city:")
for r in c.execute("SELECT city, COUNT(*) FROM leads WHERE status='QUALIFIED' GROUP BY city"):
    print(f"  {r[0]}: {r[1]}")
