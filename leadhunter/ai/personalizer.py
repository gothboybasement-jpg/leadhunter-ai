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
    "You are writing a cold email from a small agency to a local med spa. "
    "PRODUCT: Automated Review Request System. We text their happy clients to ask for a 5-star review. "
    "PRICING: $200 per month. "
    "RULES: 4 to 5 sentences maximum. Write a direct subject line like 'Quick question about [Business Name] reviews'. "
    "Mention their exact Google rating and review count. "
    "Paint a scenario: imagine a happy client walking out of the spa. Tell them your system automatically texts the client this exact message: 'Hi [Client Name], thanks for visiting us! If you have 30 seconds, would you mind sharing your experience on Google? It helps other people find us. Here is the link: [Google Review Link]'. "
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
            f"You have {reviews} ({rating}) in {city}. Imagine a client just had a great treatment and walks out of your spa happy. Right now, they probably forget to leave a review.\n\n"
            f"My system automatically texts them that same day: 'Hi [Client Name], thanks for visiting us! If you have 30 seconds, would you mind sharing your experience on Google? It helps other people find us. Here is the link: [Google Review Link]'\n\n"
            f"You get 20+ new 5-star reviews a month without lifting a finger. It's $200/month. Want to see how it works?\n\n"
            f"Best regards"
        ),
        "whatsapp_message": f"Hi {name}! Imagine your happy clients automatically leaving 5-star reviews. I text them the moment they leave your spa. $200/month. Want to see how?",
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

    # Force the query to ignore city and find ALL qualified leads
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