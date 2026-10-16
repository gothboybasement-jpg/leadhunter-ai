import sqlite3
c = sqlite3.connect('data/leadhunter.db')
c.execute("UPDATE leads SET status='QUALIFIED', email_subject=NULL, email_message=NULL, whatsapp_message=NULL WHERE status='PERSONALIZED'")
c.commit()
print("Reset")
