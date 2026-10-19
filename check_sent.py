import sqlite3
c = sqlite3.connect('data/leadhunter.db')
rows = c.execute("SELECT name, email, email_subject FROM leads WHERE status = 'SENT' OR status = 'DRY_RUN_SENT' ORDER BY id DESC LIMIT 15").fetchall()
for r in rows:
    print(f"To: {r[1]:<35} | Subject: {r[2]}")
