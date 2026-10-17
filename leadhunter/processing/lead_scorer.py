"""Lead scoring and qualification module for LeadHunter AI.

Evaluates leads sitting at status 'VERIFIED' against website and business signals:
- Website signals:
    NO_WEBSITE = 40 points
    BROKEN_WEBSITE = 35 points
    SOCIAL_ONLY = 30 points
    DIRECTORY_ONLY = 28 points
    DOMAIN_ONLY = 20 points
    VALID_WEBSITE = 0 points (skip as lead)
- Business signals:
    Has phone number = +15
    Has email = +10
    Rating 4.0+ with 20+ reviews = +15 (strong local presence, needs web)
    Rating 3.0–3.9 with reviews = +8
    Has Instagram = +5
    Target Category (restaurant/hotel/clinic/salon/gym/shop/etc.) = +10

Assigns lead_tier:
    Score 70+ = HOT   -> status = QUALIFIED (qualified = 1)
    Score 45–69 = WARM -> status = QUALIFIED (qualified = 1)
    Score < 45 = LOW  -> saved with qualified = 0 (not processed further)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from ..config import Config, load_env_file, DEFAULT_CONFIG_PATH, DEFAULT_ENV_PATH
from ..db import Database
from ..log import get_logger, setup_logging
from ..models import Lead, LeadStatus
from .website_checker import (
    STATUS_BROKEN_WEBSITE,
    STATUS_DIRECTORY_ONLY,
    STATUS_DOMAIN_ONLY,
    STATUS_NO_WEBSITE,
    STATUS_SOCIAL_ONLY,
    STATUS_UNKNOWN,
    STATUS_VALID_WEBSITE,
)

log = get_logger("lead_scorer")

# Target commercial SMB categories that benefit heavily from web presence
TARGET_CATEGORIES: Set[str] = {
    "restaurant",
    "cafe",
    "hotel",
    "resort",
    "clinic",
    "hospital",
    "doctor",
    "dentist",
    "salon",
    "spa",
    "beauty",
    "gym",
    "fitness",
    "shop",
    "store",
    "bakery",
    "dhaba",
    "bar",
    "boutique",
    "jeweller",
    "coaching",
    "academy",
}

# Tier constants
TIER_HOT = "HOT"
TIER_WARM = "WARM"
TIER_LOW = "LOW"


def evaluate_lead(lead: Lead) -> Tuple[int, str, List[str], str]:
    """Score a lead for AI receptionist fit.

    Target: solo/small business owners who miss calls because they have
    no staff and no system. Signals:
    - Has phone (they take calls)
    - Has rating 4.0+ (they care about reputation)
    - LOW review count (solo operator, not a team)
    - Small/medium web presence (not established enterprise)
    """
    score = 0
    reasons: List[str] = []

    # 1. Phone (must have — they answer calls themselves)
    phone = lead.phone or lead.phone_normalized
    if not phone or not str(phone).strip():
        reasons.append("NO_PHONE (disqualified)")
        return 0, TIER_LOW, reasons, "No phone - not a fit"
    score += 30
    reasons.append(f"has_phone (+30): {phone}")

    # 2. Review count — this is the KEY signal for solo vs. team
    reviews = lead.reviews_count or 0
    if reviews >= 200:
        # Big operation, likely has staff or answering service
        score -= 20
        reasons.append(f"TOO_BIG (-20): {reviews} reviews - already has a system")
    elif reviews >= 100:
        score -= 10
        reasons.append(f"large_operation (-10): {reviews} reviews")
    elif reviews >= 20:
        # Sweet spot — some success, no team yet
        score += 25
        reasons.append(f"sweet_spot_reviews (+25): {reviews} reviews - solo operator likely")
    elif reviews >= 5:
        score += 15
        reasons.append(f"small_operator (+15): {reviews} reviews")
    else:
        score += 5
        reasons.append(f"new_or_tiny (+5): {reviews} reviews")

    # 3. Rating — must have good reputation
    rating = lead.rating
    if rating is not None and rating >= 4.5:
        score += 20
        reasons.append(f"excellent_rating (+20): {rating}")
    elif rating is not None and rating >= 4.0:
        score += 15
        reasons.append(f"good_rating (+15): {rating}")
    elif rating is not None and rating >= 3.5:
        score += 5
        reasons.append(f"ok_rating (+5): {rating}")
    else:
        reasons.append(f"low_rating (0): {rating}")

    # 4. Category match
    cat = (lead.category or "").lower()
    target_cats = ["real estate", "realtor", "mortgage", "insurance",
                   "law firm", "attorney", "med spa", "dentist", "dental",
                   "chiropractor", "plumber", "hvac", "electrician"]
    if any(t in cat for t in target_cats):
        score += 10
        reasons.append(f"target_category (+10): {lead.category}")

    # 5. Email present (must — we send pitches)
    if not lead.email or not str(lead.email).strip():
        reasons.append("NO_EMAIL (disqualified)")
        return 0, TIER_LOW, reasons, "No email - cannot contact"
    score += 5
    reasons.append("has_email (+5)")

    # Determine tier
    if score >= 60:
        tier = TIER_HOT
    elif score >= 40:
        tier = TIER_WARM
    else:
        tier = TIER_LOW

    qualified = score >= 40
    qual_reason = (
        f"Score {score} - qualified: solo operator with phone and good reputation"
        if qualified else
        f"Score {score} - below threshold (40)"
    )
    return score, tier, reasons, qual_reason

def score_and_qualify_leads(
    db: Optional[Database] = None,
    config: Optional[Config] = None,
    city: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Score all leads at status VERIFIED, assign tier, and qualify HOT/WARM leads."""
    load_env_file(DEFAULT_ENV_PATH)
    if config is None:
        try:
            config = Config.load()
        except Exception:
            config = None

    if config:
        config.ensure_dirs()
        log_file = config.get("logging.file", "./data/logs/leadhunter.log")
        log_path = Path(log_file) if Path(log_file).is_absolute() else config.config_path.parent / log_file
    else:
        log_path = Path("./data/logs/leadhunter.log")

    setup_logging(
        level=config.get("logging.level", "INFO") if config else "INFO",
        log_file=log_path,
    )

    if db is None:
        data_dir = config.data_dir if config else os.path.join(os.getcwd(), "data")
        db_path = os.path.join(data_dir, "leadhunter.db")
        db = Database(db_path)

    query = "SELECT * FROM leads WHERE status = 'VERIFIED' ORDER BY id ASC LIMIT ?"
    if city:
        query = "SELECT * FROM leads WHERE status = 'VERIFIED' ORDER BY id ASC LIMIT ?"

    rows = db.conn.execute(query, (limit,)).fetchall()
    leads = [Lead.from_row(dict(r)) for r in rows]

    log.info("Starting scoring and qualification for %d verified leads...", len(leads))
    results: List[Dict[str, Any]] = []

    for lead in leads:
        score, tier, reasons, qual_reason = evaluate_lead(lead)
        is_qualified = tier in (TIER_HOT, TIER_WARM)

        update_fields: Dict[str, Any] = {
            "score": score,
            "score_reasons_json": json.dumps(reasons),
            "lead_tier": tier,
            "qualified": 1 if is_qualified else 0,
            "qualification_notes": qual_reason,
        }

        if is_qualified:
            # Transition to QUALIFIED
            db.update_lead(lead.id, update_fields)
            db.transition(
                lead_id=lead.id,
                to_status=LeadStatus.QUALIFIED.value,
                stage="lead_scorer",
                event=f"Qualified as {tier} lead (Score: {score}) — {qual_reason}",
                level="INFO",
                extra_fields=update_fields,
            )
            lead.status = LeadStatus.QUALIFIED
            log.info(
                "Lead [ID %d] '%s' -> %s (Score: %d) [QUALIFIED]",
                lead.id,
                lead.name,
                tier,
                score,
            )
        else:
            # LOW leads are saved with qualified=0 and not processed further
            db.update_lead(lead.id, update_fields)
            lead.score = score
            lead.lead_tier = tier
            lead.qualified = False
            lead.qualification_notes = qual_reason
            log.info(
                "Lead [ID %d] '%s' -> %s (Score: %d) [Unqualified / Skipped]",
                lead.id,
                lead.name,
                tier,
                score,
            )

        results.append({
            "id": lead.id,
            "name": lead.name,
            "category": lead.category,
            "city": lead.city,
            "website_status": lead.website_status,
            "lead_score": score,
            "lead_tier": tier,
            "qualified": is_qualified,
            "status": lead.status.value,
            "reasons": reasons,
            "qualification_reason": qual_reason,
        })

    return results


def main():
    import argparse

    parser = argparse.ArgumentParser(description="LeadHunter AI Scoring and Qualification")
    parser.add_argument("--city", default="Vadodara", help="City name filter")
    parser.add_argument("--limit", type=int, default=100, help="Max leads to score")
    args = parser.parse_args()

    print(f"\n=== Running Lead Scoring & Qualification (city='{args.city}', limit={args.limit}) ===")
    results = score_and_qualify_leads(city=args.city, limit=args.limit)

    print("\n==========================================================================================")
    print("                      LEADHUNTER AI — SCORING & QUALIFICATION RESULTS                     ")
    print("==========================================================================================")
    for r in results:
        tier_symbol = "🔥" if r["lead_tier"] == TIER_HOT else ("⚡" if r["lead_tier"] == TIER_WARM else "❄️")
        qual_tag = "[QUALIFIED]" if r["qualified"] else "[LOW / SKIPPED]"
        print(f"\nID {r['id']:2d} | {r['name']:<38} | Score: {r['lead_score']:2d}/100 | Tier: {tier_symbol} {r['lead_tier']:<4} {qual_tag}")
        print(f"      Website Status : {r['website_status']}")
        print(f"      Reason         : {r['qualification_reason']}")
        print(f"      Signal Details :")
        for sig in r["reasons"]:
            print(f"        + {sig}")


if __name__ == "__main__":
    main()
