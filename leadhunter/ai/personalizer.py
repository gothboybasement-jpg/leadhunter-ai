"""AI Message Personalization module for LeadHunter AI."""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import anthropic

from ..config import Config, load_env_file, DEFAULT_CONFIG_PATH, DEFAULT_ENV_PATH
from ..db import Database
from ..log import get_logger, setup_logging
from ..models import Lead, LeadStatus

log = get_logger("personalizer")

SYSTEM_PROMPT = (
    "You are writing a cold email from a small agency to a local law firm. "
    "PRODUCT: Google Review Management. We get them more 5-star reviews so they rank higher on Google Maps. "
    "PRICING: $200 per month. "
    "RULES: 3 to 4 sentences maximum. Write a short, curiosity-inducing subject line like 'Quick question about [Business] reviews'. "
    "Mention their exact Google rating and review count. "
    "NEVER ask for a phone call; ask a simple yes or no question instead. "
    "End with 'Best regards' only."
)

MODEL_NAME = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5")


def get_anthropic_key(config: Optional[Config] = None) -> Optional[str]:
    if config:
        key = config.get_secret("ANTHROPIC_API_KEY")
        if key:
            return key
    return os.environ.get("ANTHROPIC_API_KEY")


def build_user_prompt(lead: Lead) -> str:
    tags = lead.tags or {}
    instagram = tags.get("instagram") or "None"
    facebook = tags.get("facebook") or "None"

    lead_data = {
        "business_name": lead.name,
        "city": lead.city,
        "category": lead.category,
        "phone": lead.phone or lead.phone_normalized or "None",
        "website_status": lead.website_status or "NO_WEBSITE",
        "rating": lead.rating if lead.rating is not None else "None",
        "review_count": lead.reviews_count if lead.reviews_count is not None else 0,
        "instagram": str(instagram),
        "facebook": str(facebook),
    }

    return (
        f"Business data:\n{json.dumps(lead_data, indent=2)}\n\n"
        f"Write a cold email to this business. Follow the system prompt rules exactly."
    )


def generate_template_fallback(lead: Lead) -> Dict[str, str]:
    name = lead.name
    city = lead.city
    rating = f"{lead.rating}⭐" if lead.rating else "top-rated"
    reviews = f"{lead.reviews_count} Google reviews" if lead.reviews_count else "great customer reviews"

    return {
        "email_subject": f"Quick question about {name} reviews",
        "email_message": (
            f"Hi Team {name},\n\n"
            f"I noticed you have {reviews} ({rating}) in {city}. But if you want to outrank the firms down the street, you need more 5-star reviews coming in every week.\n\n"
            f"I set up automated review systems for law firms. It gets you 20+ new 5-star reviews per month for $200/month.\n\n"
            f"Would you be open to seeing how it works?\n\n"
            f"Best regards"
        ),
        "whatsapp_message": f"Hi {name}! I help law firms get 20+ new 5-star Google reviews a month. Want to hear how?",
    }


def generate_messages_for_lead(lead: Lead, api_key: Optional[str] = None) -> Dict[str, str]:
    if not api_key:
        api_key = get_anthropic_key()

    if not api_key:
        log.info("No API key; using fallback.")
        return generate_template_fallback(lead)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=MODEL_NAME,
            max_tokens=500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_user_prompt(lead)}]
        )
        text = resp.content[0].text
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0), strict=False)
            return {
                "email_subject": parsed.get("email_subject", f"Quick question about {lead.name} reviews"),
                "email_message": parsed.get("email_message", ""),
                "whatsapp_message": parsed.get("whatsapp_message", ""),
            }
    except Exception as e:
        log.error("Claude error: %s", e)

    return generate_template_fallback(lead)


def personalize_qualified_leads(
    db: Optional[Database] = None,
    config: Optional[Config] = None,
    city: Optional[str] = None,
    limit: int = 100,
    delay_s: float = 0.5,
) -> List[Dict[str, Any]]:
    load_env_file(DEFAULT_ENV_PATH)

    if db is None:
        db = Database(path="data/leadhunter.db")

    query = "SELECT * FROM leads WHERE status = 'QUALIFIED' ORDER BY id ASC LIMIT ?"

    rows = db.conn.execute(query, (limit,)).fetchall()
    leads = [Lead.from_row(dict(r)) for r in rows]

    log.info("Starting AI personalization for %d QUALIFIED leads (limit=%d)...", len(leads), limit)

    api_key = get_anthropic_key(config)
    results: List[Dict[str, Any]] = []

    for idx, lead in enumerate(leads):
        log.info("Generating outreach for Lead [ID %s]: '%s'...", lead.id, lead.name)
        
        messages = generate_messages_for_lead(lead, api_key=api_key)

        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        db.update_lead(lead.id, {
            "email_subject": messages["email_subject"],
            "email_message": messages["email_message"],
            "whatsapp_message": messages["whatsapp_message"],
            "personalized_message": messages["email_message"],
            "updated_at": now,
        })
        db.transition(
            lead_id=lead.id,
            to_status=LeadStatus.PERSONALIZED.value,
            stage="personalizer",
            event=f"Generated messages via {MODEL_NAME}",
            level="INFO",
        )
        
        results.append({
            "id": lead.id, "name": lead.name,
            "email_subject": messages["email_subject"],
            "email_message": messages["email_message"],
        })
        
        if delay_s > 0 and idx < len(leads) - 1:
            time.sleep(delay_s)

    return results