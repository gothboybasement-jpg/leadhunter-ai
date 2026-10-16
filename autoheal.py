"""Auto-heal: verify and repair the database on every run."""
import sqlite3
import os
from pathlib import Path

DB_PATH = Path(os.environ.get("DATABASE_PATH", "data/leadhunter.db"))

REQUIRED_COLUMNS = {
    "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
    "external_id": "TEXT",
    "source": "TEXT",
    "run_id": "INTEGER",
    "name": "TEXT",
    "category": "TEXT",
    "city": "TEXT",
    "address": "TEXT",
    "lat": "REAL",
    "lon": "REAL",
    "phone": "TEXT",
    "phone_normalized": "TEXT",
    "email": "TEXT",
    "website": "TEXT",
    "website_verified": "INTEGER DEFAULT 0",
    "website_status": "TEXT",
    "rating": "REAL",
    "reviews_count": "INTEGER",
    "tags_json": "TEXT",
    "status": "TEXT DEFAULT 'DISCOVERED'",
    "score": "INTEGER",
    "score_reasons_json": "TEXT",
    "lead_tier": "TEXT",
    "qualified": "INTEGER DEFAULT 0",
    "qualification_notes": "TEXT",
    "site_profile_json": "TEXT",
    "personalized_message": "TEXT",
    "email_subject": "TEXT",
    "email_message": "TEXT",
    "whatsapp_message": "TEXT",
    "demo_url": "TEXT",
    "demo_path": "TEXT",
    "outreach_channel": "TEXT",
    "outreach_status": "TEXT",
    "fingerprint": "TEXT",
    "stage_status": "TEXT",
    "retry_count": "INTEGER DEFAULT 0",
    "last_error": "TEXT",
    "created_at": "TEXT",
    "updated_at": "TEXT",
    "demo_status": "TEXT",
    "last_contacted_at": "TEXT",
    "next_followup_due": "TEXT",
    "followup_count": "INTEGER DEFAULT 0",
    "sent_at": "TEXT",
}


def heal():
    """Ensure database exists and has all required columns."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    # Create table if missing
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='leads'")
    if not cur.fetchone():
        print("[heal] Creating leads table")
        cols = ", ".join(f'"{k}" {v}' for k, v in REQUIRED_COLUMNS.items())
        cur.execute(f"CREATE TABLE leads ({cols})")
        conn.commit()
        return

    # Get existing columns
    existing = {r[1] for r in cur.execute("PRAGMA table_info(leads)").fetchall()}

    # Add any missing columns
    for col, definition in REQUIRED_COLUMNS.items():
        if col not in existing:
            try:
                cur.execute(f'ALTER TABLE leads ADD COLUMN "{col}" {definition}')
                print(f"[heal] Added missing column: {col}")
            except Exception as e:
                print(f"[heal] Could not add column {col}: {e}")

    conn.commit()
    conn.close()
    print("[heal] Database check complete.")


if __name__ == "__main__":
    heal()