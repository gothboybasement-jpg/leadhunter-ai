import sqlite3, re
c = sqlite3.connect('data/leadhunter.db')
row = c.execute("SELECT email_subject, email_message, whatsapp_message FROM leads WHERE id=2").fetchone()
subject = row[0]
body = row[1]
wa = row[2]

# Remove any line that contains the demo placeholder
body = re.sub(r'[^\n]*\{\{DEMO_URL\}\}[^\n]*\n?', '', body)
wa = re.sub(r'[^\n]*\{\{DEMO_URL\}\}[^\n]*\n?', '', wa)

# Clean up double blank lines
body = re.sub(r'\n\s*\n\s*\n+', '\n\n', body).strip()
wa = re.sub(r'\n\s*\n\s*\n+', '\n\n', wa).strip()

c.execute("UPDATE leads SET email_message=?, whatsapp_message=? WHERE id=2", (body, wa))
c.commit()
print("=== FINAL EMAIL SUBJECT ===")
print(subject)
print()
print("=== FINAL EMAIL BODY ===")
print(body)
print()
print("=== FINAL WHATSAPP ===")
print(wa)
