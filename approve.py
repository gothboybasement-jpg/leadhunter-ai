import sqlite3
c = sqlite3.connect('data/leadhunter.db')
c.execute("UPDATE leads SET status='APPROVED' WHERE status='PERSONALIZED'")
c.execute("UPDATE leads SET status='APPROVED' WHERE status='PENDING_APPROVAL'")
c.commit()
rows = c.execute("SELECT id, name, status FROM leads WHERE status='APPROVED'").fetchall()
print("Approved leads:")
for r in rows: print(" ", r)
