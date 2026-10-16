import sqlite3
c = sqlite3.connect('data/leadhunter.db')
rows = c.execute("SELECT name, email_subject, email_message FROM leads WHERE status='PERSONALIZED'").fetchall()
for name, subject, body in rows:
    print("=" * 70)
    print("TO:", name)
    print("SUBJECT:", subject)
    print("-" * 70)
    print(body)
    print()
