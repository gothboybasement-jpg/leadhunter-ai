import sqlite3
from datetime import datetime

c = sqlite3.connect('data/leadhunter.db')
now = datetime.now().isoformat()

# Remove the old manual test leads
c.execute("DELETE FROM leads WHERE source='manual'")

# Insert with FULL data: phone, rating, reviews
leads = [
    ("Smith & Associates Real Estate", "info@smithandassociates.com", "Tampa", "real estate agent", "+1 813-555-0101", 4.8, 45),
    ("Keller Williams Tampa", "tampa@kw.com", "Tampa", "real estate agent", "+1 813-555-0102", 4.7, 120),
    ("RE/MAX Tampa", "info@remax-tampa.com", "Tampa", "real estate agent", "+1 813-555-0103", 4.9, 89),
    ("Century 21 Tampa", "contact@century21tampa.com", "Tampa", "real estate agent", "+1 813-555-0104", 4.6, 67),
    ("Coldwell Banker Tampa", "info@cbtampa.com", "Tampa", "real estate agent", "+1 813-555-0105", 4.8, 54),
]

for name, email, city, cat, phone, rating, reviews in leads:
    c.execute(
        "INSERT INTO leads (name, email, city, category, status, source, phone, rating, reviews_count, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, 'DISCOVERED', 'manual', ?, ?, ?, ?, ?)",
        (name, email, city, cat, phone, rating, reviews, now, now)
    )
c.commit()
print(f"Added {len(leads)} test leads with phone and rating.")
