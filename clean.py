import sqlite3
c = sqlite3.connect('data/leadhunter.db')
c.execute("DELETE FROM leads WHERE name IS NULL OR name = ''")
c.commit()
print("Deleted nameless leads.")
