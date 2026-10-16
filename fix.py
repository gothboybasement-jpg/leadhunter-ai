import sqlite3
c = sqlite3.connect('data/leadhunter.db')
c.execute("UPDATE leads SET status='PERSONALIZED' WHERE id=2")
c.commit()
print("Lead 2 marked PERSONALIZED")
