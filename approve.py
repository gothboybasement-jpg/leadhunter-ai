import sqlite3
c = sqlite3.connect('data/leadhunter.db')
# Approve anything with an email message and a real email address,
# but never re-approve anything already sent
c.execute("""UPDATE leads SET status='APPROVED'
             WHERE email IS NOT NULL AND email != ''
             AND email_message IS NOT NULL AND email_message != ''
             AND sent_at IS NULL
             AND status NOT IN ('SENT', 'REJECTED', 'DO_NOT_CONTACT')""")
c.commit()
rows = c.execute("SELECT id, name, status, email FROM leads WHERE status='APPROVED'").fetchall()
print(f"Approved leads: {len(rows)}")
for r in rows: print(" ", r)