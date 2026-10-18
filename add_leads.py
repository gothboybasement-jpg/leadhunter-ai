import sqlite3
from datetime import datetime

c = sqlite3.connect('data/leadhunter.db')
now = datetime.now().isoformat()

# Manually add 5 real estate agents in Tampa with emails
leads = [
    ("Smith & Associates Real Estate", "info@smithandassociates.com", "Tampa", "real estate agent"),
    ("Keller Williams Tampa", "tampa@kw.com", "Tampa", "real estate agent"),
    ("RE/MAX Tampa", "info@remax-tampa.com", "Tampa", "real estate agent"),
    ("Century 21 Tampa", "contact@century21tampa.com", "Tampa", "real estate agent"),
    ("Coldwell Banker Tampa", "info@cbtampa.com", "Tampa", "real estate agent"),
]

for name, email, city, cat in leads:
    c.execute(
        "INSERT INTO leads (name, email, city, category, status, source, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, 'DISCOVERED', 'manual', ?, ?)",
        (name, email, city, cat, now, now)
    )
c.commit()
print(f"Added {len(leads)} real estate agents manually.")
